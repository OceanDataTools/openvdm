"""Tests for bin/plot_ctd_casts.py (#514 part 2).

The script saves the CTD profile parser's plot of each new or updated cast in
an extra directory (a ``postCollectionSystemTransfer`` hook). ``main()`` runs
with a command line and the fake ``OpenVDM``. Most tests replace the parser
with one that writes a PNG, so they don't need matplotlib; one plots a real
cast, and is skipped without it.
"""

import os
import shutil
import sys
from types import SimpleNamespace

import pytest

from server.tests.helpers import PARSER_DATA


class FakeParser:
    """A CTD profile parser that saves a "plot" for casts whose name doesn't start with "bad"."""

    def __init__(self, plot_dir):
        self.plot_dir = plot_dir

    def parse(self, cast):
        name = cast.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        if name.startswith('bad'):
            raise ValueError(f'No calibration file for {cast}')
        if name.startswith('noplot'):
            return
        with open(f'{self.plot_dir}/{name}.png', 'wb') as png:
            png.write(b'\x89PNG')


@pytest.fixture
def site(fake_ovdm, warehouse):
    """The cruise's CTD folder with two casts, and the CTD_Plots extra directory."""
    ctd = warehouse.cruise_dir / 'CTD'
    (ctd / 'raw').mkdir(parents=True)
    for name in ('CTD001.hex', 'CTD001.XMLCON', 'CTD002.HEX', 'CTD002.xmlcon', 'CTD002.bl'):
        (ctd / 'raw' / name).write_text('x')
    plots = warehouse.cruise_dir / 'Products' / 'CTD_Plots'
    plots.mkdir(parents=True)
    fake_ovdm.get_extra_directory_by_name.side_effect = lambda name: {
        'CTD_Plots': {'name': 'CTD_Plots', 'destDir': 'Products/CTD_Plots', 'enable': 1}}.get(name)
    fake_ovdm.get_collection_system_transfer_by_name.side_effect = lambda name: {
        'CTD': {'name': 'CTD', 'destDir': 'CTD'}}.get(name)
    return SimpleNamespace(ovdm=fake_ovdm, ctd=ctd, plots=plots, cruise_dir=warehouse.cruise_dir, owners=[])


@pytest.fixture
def module(load_dist, monkeypatch, site):
    """The script module, using the fake API and recording ownership changes."""
    module = load_dist('bin/plot_ctd_casts.py.dist', name='plot_ctd_casts')
    monkeypatch.setattr(module, 'OpenVDM', lambda: site.ovdm)

    def owner(user, path):
        site.owners.append((user, path))
        return {'verdict': True}
    monkeypatch.setattr(module, 'set_owner_group_permissions', owner)
    return module


@pytest.fixture
def run(module, monkeypatch):
    """Return a function that runs main() with *args*, with the fake parser; returns the exit status."""
    monkeypatch.setattr(module, 'check_requirements', lambda: FakeParser)

    def run_script(*args):
        monkeypatch.setattr(sys, 'argv', ['plot_ctd_casts.py', *args])
        try:
            return module.main()
        except SystemExit as exc:
            return exc.code
    return run_script


def test_plot_new_casts(run, site) -> None:
    """Each new .hex cast, and the cast of each new .xmlcon (any case), is plotted once, given to the
    warehouse user and added to the MD5 summary; other files are ignored."""
    assert run('CTD/raw/CTD001.hex CTD/raw/CTD001.XMLCON', 'CTD/raw/CTD002.xmlcon', 'CTD/raw/CTD002.bl') == 0
    assert sorted(path.name for path in site.plots.iterdir()) == ['CTD001.png', 'CTD002.png']
    assert [user for user, _ in site.owners] == ['survey', 'survey']
    kwargs = site.ovdm.update_md5_summary.call_args.kwargs
    assert sorted(kwargs['new']) == [str(site.plots / 'CTD001.png'), str(site.plots / 'CTD002.png')]
    assert kwargs['updated'] == [] and kwargs['cruise_id'] == 'TEST001'


def test_replot_is_updated(run, site, monkeypatch) -> None:
    """A cast plotted again is an update in the MD5 summary."""
    run('CTD/raw/CTD001.hex')
    os.utime(site.plots / 'CTD001.png', ns=(0, 0))
    assert run('CTD/raw/CTD001.hex') == 0
    assert site.ovdm.update_md5_summary.call_args.kwargs['updated'] == [str(site.plots / 'CTD001.png')]


def test_all(run, site) -> None:
    """--all plots every cast in the collection system's folder."""
    assert run('--all', '--collection-system', 'CTD') == 0
    assert sorted(path.name for path in site.plots.iterdir()) == ['CTD001.png', 'CTD002.png']


def test_all_needs_collection_system(run, capsys) -> None:
    """--all without --collection-system is a usage error."""
    assert run('--all') == 2
    assert '--all needs --collection-system' in capsys.readouterr().err


def test_no_casts(run, site) -> None:
    """Without casts among the files, nothing is plotted or queued."""
    assert run('CTD/raw/CTD002.bl') == 0
    site.ovdm.update_md5_summary.assert_not_called()


def test_cast_fails(run, site, capsys) -> None:
    """A cast that can't be plotted is reported and the script exits 1; the others are still plotted."""
    (site.ctd / 'raw' / 'bad003.hex').write_text('x')
    (site.ctd / 'raw' / 'noplot004.hex').write_text('x')
    assert run('CTD/raw/CTD001.hex', 'CTD/raw/bad003.hex', 'CTD/raw/noplot004.hex') == 1
    err = capsys.readouterr().err
    assert 'CTD plots: 2 problem(s) with 3 cast(s):' in err
    assert 'bad003.hex: No calibration file' in err and 'noplot004.hex: no plot saved; see the log' in err
    assert [path.name for path in site.plots.iterdir()] == ['CTD001.png']


def test_ownership_and_md5_failures(run, site, module, monkeypatch, capsys) -> None:
    """Failing to set a plot's ownership or queue the MD5 summary update exits 1, saying so."""
    monkeypatch.setattr(module, 'set_owner_group_permissions', lambda user, path: {'verdict': False,
                                                                                    'reason': 'chown failed'})
    site.ovdm.update_md5_summary.side_effect = OSError('gearman down')
    assert run('CTD/raw/CTD001.hex') == 1
    err = capsys.readouterr().err
    assert 'CTD001.png: chown failed' in err and 'MD5 summary update: gearman down' in err


@pytest.mark.parametrize('setup, args, message', [
    (lambda site: setattr(site.ovdm.get_extra_directory_by_name, 'side_effect', lambda name: None), (),
     'No extra directory named CTD_Plots'),
    (lambda site: setattr(site.ovdm.get_extra_directory_by_name, 'side_effect',
                          lambda name: {'destDir': 'x', 'enable': 0}), (), "The CTD_Plots extra directory isn't enabled"),
    (lambda site: setattr(site.ovdm.get_extra_directory_by_name, 'side_effect',
                          lambda name: {'destDir': 'missing', 'enable': '1'}), (), "folder doesn't exist"),
    (lambda site: setattr(site.ovdm.get_extra_directory_by_name, 'side_effect',
                          lambda name: {'destDir': 'Vehicle/{loweringID}/Plots', 'enable': 1}), (),
     "is a per-lowering directory, which isn't supported"),
    (lambda site: None, ('--all', '--collection-system', 'Nope'), 'No collection system transfer named Nope'),
    (lambda site: setattr(site.ovdm.get_shipboard_data_warehouse_config, 'side_effect', OSError('API down')), (),
     "Unable to get OpenVDM's configuration: API down"),
])
def test_setup_fails(run, site, capsys, setup, args, message) -> None:
    """If the extra directory can't be used, the collection system doesn't exist or the API is
    down, the script exits 1 before plotting."""
    setup(site)
    assert run('CTD/raw/CTD001.hex', *args) == 1
    assert message in capsys.readouterr().err


def test_other_extra_directory_and_cruise(run, site, fake_ovdm, warehouse) -> None:
    """-e names another extra directory ({cruiseID} filled in), and -c another cruise."""
    other = warehouse.base_dir / 'TEST002'
    (other / 'CTD').mkdir(parents=True)
    (other / 'CTD' / 'CTD009.hex').write_text('x')
    (other / 'TEST002_plots').mkdir()
    site.ovdm.get_extra_directory_by_name.side_effect = lambda name: {'destDir': '{cruiseID}_plots', 'enable': 1}
    assert run('-c', 'TEST002', '-e', 'Plots', 'CTD/CTD009.hex') == 0
    assert (other / 'TEST002_plots' / 'CTD009.png').is_file()
    assert site.ovdm.update_md5_summary.call_args.kwargs['cruise_id'] == 'TEST002'


def test_requirements_without_matplotlib(module, monkeypatch) -> None:
    """Without matplotlib, the script says how to install it."""
    monkeypatch.setitem(sys.modules, 'matplotlib', None)
    with pytest.raises(module.PlotError, match="matplotlib isn't installed.*pip install matplotlib"):
        module.check_requirements()


def test_requirements_without_parser(module, monkeypatch) -> None:
    """Without the CTD profile parser copied from its .dist, the script says so."""
    monkeypatch.setitem(sys.modules, 'matplotlib', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'server.plugins.parsers.ctd_profile_parser', None)
    with pytest.raises(module.PlotError, match="copy server/plugins/parsers/ctd_profile_parser.py.dist"):
        module.check_requirements()


def test_main_without_matplotlib(module, monkeypatch, capsys) -> None:
    """Without matplotlib, main() exits 1 before plotting anything."""
    monkeypatch.setitem(sys.modules, 'matplotlib', None)
    monkeypatch.setattr(sys, 'argv', ['plot_ctd_casts.py', 'CTD/raw/CTD001.hex'])
    assert module.main() == 1
    assert "matplotlib isn't installed" in capsys.readouterr().err


def test_real_plot(module, load_dist, monkeypatch, site) -> None:
    """With matplotlib and the parser, a real cast is plotted."""
    pytest.importorskip('matplotlib')
    load_dist('server/plugins/parsers/ctd_profile_parser.py.dist', name='server.plugins.parsers.ctd_profile_parser')
    for name in ('ctd002.hex', 'ctd002.XMLCON'):
        shutil.copy(PARSER_DATA / 'profiles' / name, site.ctd / 'raw' / name)
    monkeypatch.setattr(sys, 'argv', ['plot_ctd_casts.py', 'CTD/raw/ctd002.hex'])
    assert module.main() == 0
    assert (site.plots / 'ctd002.png').read_bytes()[:4] == b'\x89PNG'
