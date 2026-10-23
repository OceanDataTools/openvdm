"""Tests for the trackline scripts, bin/build_cruise_tracks.py and bin/build_lowering_tracks.py (#514).

Each script's ``main()`` runs with a command line, the fake ``OpenVDM`` and a
temporary cruise whose Dashboard_Data manifest lists two GGA files; the
trackline code they share (``server/lib/tracks.py``) is tested in
``test_tracks.py``. Ownership changes are recorded.
"""

import json
import sys
from types import SimpleNamespace

import pytest

from server.lib import tracks

GGA = {'gga_1.json': ([[-120.0, 45.0], [-120.1, 45.1]], ['2026-10-22T10:00:00Z', '2026-10-22T10:01:00Z']),
       'gga_2.json': ([[-120.2, 45.2]], ['2026-10-22T10:02:00Z'])}
EXTENT = {'westernmost': -120.2, 'easternmost': -120.0, 'southernmost': 45.0, 'northernmost': 45.2}


def _write_dashboard_files(dashboard, subdir, prefix, data_type):
    """Write the GGA dashboard files and their manifest; return the manifest's path."""
    folder = dashboard / subdir / 'Nav'
    folder.mkdir(parents=True)
    for name, (coords, times) in GGA.items():
        (folder / name).write_text(json.dumps({data_type: {'visualizerData': [{
            'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {
                'type': 'LineString', 'coordinates': coords}, 'properties': {'coordTimes': times}}]}]}}))
    manifest = [{'type': data_type, 'dd_json': f'{prefix}/Nav/{name}', 'raw_data': 'x'} for name in GGA]
    (dashboard / subdir / 'manifest.json').write_text(json.dumps(manifest))


@pytest.fixture
def chown(monkeypatch):
    """Record set_owner_group_permissions() calls."""
    calls = []
    monkeypatch.setattr(tracks, 'set_owner_group_permissions', lambda user, path: calls.append((user, path)))
    return calls


@pytest.fixture
def site(fake_ovdm, warehouse, chown):
    """The cruise TEST001 and its lowering DIVE01: dashboard files, the Tracklines extra directory,
    and the fake API's answers."""
    dashboard = warehouse.cruise_dir / 'Dashboard_Data'
    _write_dashboard_files(dashboard, '', 'TEST001/Dashboard_Data', 'gga')
    _write_dashboard_files(dashboard, 'Vehicle/DIVE01', 'TEST001/Dashboard_Data/Vehicle/DIVE01', 'usbl_pri_gga')
    tracklines = warehouse.cruise_dir / 'Tracklines'
    tracklines.mkdir()
    (warehouse.cruise_dir / 'Vehicle' / 'DIVE01' / 'Tracklines').mkdir(parents=True)
    fake_ovdm.get_lowering_id.return_value = 'DIVE01'
    fake_ovdm.get_data_dashboard_manifest_fn.return_value = 'manifest.json'
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'destDir': 'Dashboard_Data'}
    fake_ovdm.get_extra_directory_by_name.side_effect = lambda name: {
        'Tracklines': {'name': 'Tracklines', 'destDir': 'Tracklines', 'enable': 1, 'cruiseOrLowering': 0},
        'LoweringTracks': {'name': 'LoweringTracks', 'destDir': 'Tracklines', 'enable': 1, 'cruiseOrLowering': 1},
    }.get(name)
    fake_ovdm.get_collection_system_transfer_by_name.side_effect = lambda name: {
        'OpenRVDAS': {'name': 'OpenRVDAS', 'cruiseOrLowering': 0},
        'ROV_OpenRVDAS': {'name': 'ROV_OpenRVDAS', 'cruiseOrLowering': 1},
    }.get(name)
    return SimpleNamespace(ovdm=fake_ovdm, tracklines=tracklines, cruise_dir=warehouse.cruise_dir, chown=chown)


@pytest.fixture
def run(load_dist, monkeypatch, site):
    """Return a function that runs a script's main() with *args*; returns its exit status."""
    def run_script(script, *args):
        module = load_dist(f'bin/{script}.py.dist', name=script)
        monkeypatch.setattr(module, 'OpenVDM', lambda: site.ovdm)
        monkeypatch.setattr(sys, 'argv', [script, *args])
        try:
            module.main()
        except SystemExit as exc:
            return exc.code
        return 0
    return run_script


def _cruise(run, *args):
    return run('build_cruise_tracks', *args, 'OpenRVDAS')


def _lowering(run, *args):
    return run('build_lowering_tracks', *args, 'ROV_OpenRVDAS')


# --- Cruise -------------------------------------------------------------------------

def test_cruise_tracks(run, site, warehouse) -> None:
    """The default position source's trackline is written to Tracklines, given to the warehouse
    user, added to the MD5 summary, and sets the cruise extent."""
    assert _cruise(run) == 0
    files = sorted(path.name for path in site.tracklines.iterdir())
    assert files == ['TEST001_POSMV_Trackline.json', 'TEST001_POSMV_Trackline.kml']
    assert [user for user, _ in site.chown] == ['survey', 'survey']
    site.ovdm.set_cruise_extent.assert_called_once_with(EXTENT)
    kwargs = site.ovdm.update_md5_summary.call_args.kwargs
    assert sorted(kwargs['new']) == sorted(str(site.tracklines / name) for name in files)
    assert kwargs['updated'] == [] and kwargs['cruise_id'] == 'TEST001'


def test_cruise_tracks_rewritten(run, site) -> None:
    """A second run updates the files in the MD5 summary instead of adding them."""
    _cruise(run)
    _cruise(run)
    kwargs = site.ovdm.update_md5_summary.call_args.kwargs
    assert kwargs['new'] == [] and len(kwargs['updated']) == 2


@pytest.mark.parametrize('option, kept', [('-k', '.kml'), ('-g', '.json')])
def test_cruise_tracks_one_format(run, site, option, kept) -> None:
    """-k and -g write only the KML or the GeoJSON."""
    assert _cruise(run, option) == 0
    assert [path.suffix for path in site.tracklines.iterdir()] == [kept]


def test_cruise_tracks_output_dir(run, site, tmp_path) -> None:
    """-o writes to a folder instead: not given to the warehouse user, not in the MD5 summary."""
    out = tmp_path / 'out'
    out.mkdir()
    assert _cruise(run, '-o', str(out)) == 0
    assert len(list(out.iterdir())) == 2
    assert site.chown == []
    site.ovdm.update_md5_summary.assert_not_called()


def test_cruise_tracks_other_extra_directory(run, site, tmp_path) -> None:
    """-e names another extra directory."""
    site.ovdm.get_extra_directory_by_name.side_effect = lambda name: {
        'Products': {'name': 'Products', 'destDir': 'Products/Tracks', 'enable': 1}}.get(name)
    (site.cruise_dir / 'Products' / 'Tracks').mkdir(parents=True)
    assert _cruise(run, '-e', 'Products') == 0
    assert len(list((site.cruise_dir / 'Products' / 'Tracks').iterdir())) == 2


def test_cruise_tracks_position_sources_file(run, site, tmp_path) -> None:
    """--position-sources replaces the default sources."""
    path = tmp_path / 'sources.yaml'
    path.write_text('PositionSources:\n  - device: GPS2\n    type: gga\n')
    assert _cruise(run, '--position-sources', str(path)) == 0
    assert sorted(p.name for p in site.tracklines.iterdir())[0] == 'TEST001_GPS2_Trackline.json'


def test_cruise_tracks_no_set_extent(run, site) -> None:
    """--no-set-extent leaves the cruise extent alone."""
    assert _cruise(run, '--no-set-extent') == 0
    site.ovdm.set_cruise_extent.assert_not_called()


def test_cruise_tracks_other_cruise(run, site, warehouse, caplog) -> None:
    """For a cruise that isn't the current one (-c), the extent isn't set."""
    site.ovdm.get_cruise_id.return_value = 'TEST002'
    assert _cruise(run, '-v', '-c', 'TEST001') == 0
    site.ovdm.set_cruise_extent.assert_not_called()
    assert "TEST001 isn't the current cruise" in caplog.text


def test_cruise_tracks_no_positions(run, site, tmp_path, caplog) -> None:
    """A source with no dashboard files writes nothing and sets no extent."""
    path = tmp_path / 'sources.yaml'
    path.write_text('PositionSources:\n  - device: GPS2\n    type: hdt\n')
    assert _cruise(run, '--position-sources', str(path)) == 0
    assert list(site.tracklines.iterdir()) == []
    site.ovdm.set_cruise_extent.assert_not_called()
    site.ovdm.update_md5_summary.assert_not_called()
    assert 'the cruise extent isn' in caplog.text


@pytest.mark.parametrize('setup, args, message', [
    (lambda site: setattr(site.ovdm.get_cruise_id, 'return_value', None), (), 'Unable to determine CruiseID'),
    (lambda site: None, ('-o', '/no/such/folder'), 'Trackline directory not found'),
    (lambda site: setattr(site.ovdm.get_extra_directory_by_name, 'side_effect', lambda name: None), (),
     'No extra directory named Tracklines'),
    (lambda site: setattr(site.ovdm.get_data_dashboard_manifest_fn, 'return_value', 'missing.json'), (),
     'Manifest not found'),
])
def test_cruise_tracks_setup_fails(run, site, caplog, setup, args, message) -> None:
    """Without a cruise, the output folder or extra directory, or the manifest, the script exits 1."""
    setup(site)
    assert _cruise(run, *args) == 1
    assert message in caplog.text


def test_cruise_tracks_unknown_collection_system(run, caplog) -> None:
    """A collection system OpenVDM doesn't have exits 1."""
    assert run('build_cruise_tracks', 'NoSuchSystem') == 1
    assert 'Collection System not found: NoSuchSystem' in caplog.text


def test_cruise_tracks_extent_refused(run, site, capsys) -> None:
    """If OpenVDM refuses the extent, the script exits 1 saying so; the tracklines are still added to
    the MD5 summary."""
    site.ovdm.set_cruise_extent.side_effect = OSError('403 Forbidden')
    assert _cruise(run) == 1
    assert 'Unable to set the cruise extent: 403 Forbidden' in capsys.readouterr().err
    site.ovdm.update_md5_summary.assert_called_once()


def test_cruise_tracks_md5_fails(run, site, capsys) -> None:
    """If the MD5 summary update can't be queued, the script exits 1 saying so."""
    site.ovdm.update_md5_summary.side_effect = OSError('gearman down')
    assert _cruise(run) == 1
    assert 'gearman down' in capsys.readouterr().err


# --- Lowering -----------------------------------------------------------------------

def test_lowering_tracks(run, site, tmp_path) -> None:
    """The lowering's trackline goes to the cruise-level Tracklines folder, named after the lowering;
    it sets the lowering extent and is added to the cruise's MD5 summary."""
    assert _lowering(run) == 0
    assert sorted(path.name for path in site.tracklines.iterdir()) == [
        'DIVE01_USBL-PRI_Trackline.json', 'DIVE01_USBL-PRI_Trackline.kml']
    site.ovdm.set_lowering_extent.assert_called_once_with(EXTENT)
    assert site.ovdm.update_md5_summary.call_args.kwargs['cruise_id'] == 'TEST001'


def test_lowering_tracks_lowering_extra_directory(run, site) -> None:
    """A lowering-level extra directory is inside the lowering."""
    assert _lowering(run, '-e', 'LoweringTracks') == 0
    assert len(list((site.cruise_dir / 'Vehicle' / 'DIVE01' / 'Tracklines').iterdir())) == 2


def test_lowering_tracks_other_lowering(run, site, caplog) -> None:
    """For a lowering that isn't the current one (-l), the extent isn't set."""
    site.ovdm.get_lowering_id.return_value = 'DIVE02'
    assert _lowering(run, '-v', '-l', 'DIVE01') == 0
    site.ovdm.set_lowering_extent.assert_not_called()
    assert "DIVE01 isn't the current lowering" in caplog.text


def test_lowering_tracks_no_positions(run, site, tmp_path, caplog) -> None:
    """A source with no positions sets no lowering extent."""
    path = tmp_path / 'sources.yaml'
    path.write_text('PositionSources:\n  - device: SPRINT\n    type: sprint\n')
    assert _lowering(run, '--position-sources', str(path)) == 0
    site.ovdm.set_lowering_extent.assert_not_called()
    assert 'the lowering extent isn' in caplog.text


def test_lowering_tracks_output_dir_and_no_extent(run, site, tmp_path) -> None:
    """-o and --no-set-extent: a folder, no MD5 summary, no extent."""
    out = tmp_path / 'out'
    out.mkdir()
    assert _lowering(run, '-o', str(out), '--no-set-extent') == 0
    assert len(list(out.iterdir())) == 2
    site.ovdm.set_lowering_extent.assert_not_called()
    site.ovdm.update_md5_summary.assert_not_called()


@pytest.mark.parametrize('setup, args, message', [
    (lambda site: setattr(site.ovdm.get_cruise_id, 'return_value', None), (), 'Unable to determine CruiseID'),
    (lambda site: setattr(site.ovdm.get_lowering_id, 'return_value', None), (),
     'Unable to find LoweringID within Cruise: TEST001'),
    (lambda site: None, ('-o', '/no/such/folder'), 'Trackline directory not found'),
])
def test_lowering_tracks_setup_fails(run, site, caplog, setup, args, message) -> None:
    """Without a cruise, a lowering or the output folder, the script exits 1."""
    setup(site)
    assert _lowering(run, *args) == 1
    assert message in caplog.text


@pytest.mark.parametrize('name, message', [('NoSuchSystem', 'Collection System not found: NoSuchSystem'),
                                           ('OpenRVDAS', 'Collection System: OpenRVDAS is not related to a lowering')])
def test_lowering_tracks_wrong_collection_system(run, caplog, name, message) -> None:
    """A collection system that doesn't exist, or isn't a lowering's, exits 1."""
    assert run('build_lowering_tracks', name) == 1
    assert message in caplog.text


@pytest.mark.parametrize('error, message', [('extent', 'Unable to set the lowering extent'),
                                            ('md5', 'Unable to queue the MD5 summary update')])
def test_lowering_tracks_failures(run, site, capsys, error, message) -> None:
    """If the extent is refused or the MD5 summary update can't be queued, the script exits 1."""
    getattr(site.ovdm, {'extent': 'set_lowering_extent', 'md5': 'update_md5_summary'}[error]).side_effect = \
        OSError('refused')
    assert _lowering(run) == 1
    assert message in capsys.readouterr().err


@pytest.mark.parametrize('cruise_or_lowering', [1, '1'])
def test_lowering_collection_system(run, site, cruise_or_lowering) -> None:
    """A lowering's collection system is accepted with cruiseOrLowering 1, a number as the API sends
    it, or a string (#600)."""
    site.ovdm.get_collection_system_transfer_by_name.side_effect = lambda name: {
        'name': name, 'cruiseOrLowering': cruise_or_lowering}
    assert _lowering(run) == 0
