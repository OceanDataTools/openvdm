"""Tests for the plugins in server/plugins (#513 part 3b).

A plugin maps a file's name to the parsers for it, with their options, and
returns each parser's plugin data by data type. The tests check the mapping,
that the plugin's output is its parsers' output for the same input files
(server/tests/data/parsers, saved as the parsers' expected output), and how a
plugin handles files it doesn't know and parsers that fail.

The plugins import their parsers as ``server.plugins.parsers.<name>_parser``,
which only a site's copies are; the tests load the ``.dist`` parsers under
those names first.
"""

import json
import logging
import shutil
import sys
from types import SimpleNamespace

import pytest

from server.lib.openvdm_plugin import NpEncoder, OpenVDMParser
from server.tests.helpers import PARSER_DATA


@pytest.fixture
def load_plugin(load_dist):
    """Return a function that loads ``server/plugins/<plugin>_plugin.py.dist`` with its *parsers*."""
    def load(plugin, *parsers):
        for parser in parsers:
            load_dist(f'server/plugins/parsers/{parser}_parser.py.dist', name=f'server.plugins.parsers.{parser}_parser')
        return load_dist(f'server/plugins/{plugin}_plugin.py.dist')
    return load


def _as_saved(data):
    """*data* (a parser's plugin data) as JSON would save it."""
    return json.loads(json.dumps(data, cls=NpEncoder))


def _expected(name):
    return json.loads((PARSER_DATA / 'expected' / f'{name}.json').read_text())


def _copy(source, dest):
    """Copy the test input *source* (relative to PARSER_DATA) to *dest*, making its directory."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(PARSER_DATA / source, dest)
    return dest


class FailingParser:  # pylint: disable=too-few-public-methods
    """A parser whose parse() raises."""

    def __init__(self, **options):
        self.plugin_data = None

    def parse(self, filepath):
        raise RuntimeError(f'cannot parse {filepath}')


class EmptyParser(OpenVDMParser):
    """A parser that finds no data."""

    def __init__(self, **options):
        super().__init__()

    def parse(self, filepath):
        return None


def _broken(**options):
    raise TypeError('unexpected option')


# --- OpenRVDAS --------------------------------------------------------------------

OPENRVDAS_PARSERS = ('gga', 'met', 'ssv', 'tsg45', 'twind')


@pytest.fixture
def openrvdas(load_plugin):
    """The OpenRVDAS plugin module."""
    return load_plugin('openrvdas', *OPENRVDAS_PARSERS)


@pytest.mark.parametrize('path, data_types', [
    ('OpenRVDAS/raw/POSMV_GGA-2012-04-28-000000.txt', ['gga']),
    ('OpenRVDAS/raw/MET-2012-04-28-000000.txt', ['met']),
    ('OpenRVDAS/raw/SVP-2012-04-28-000000.txt', ['ssv']),
    ('OpenRVDAS/raw/TSG_Raw-2012-04-28-000000.txt', ['tsg']),
    ('OpenRVDAS/proc/TrueWind-2012-04-28-000000.txt', ['twind']),
    ('OpenRVDAS/raw/TrueWind-2012-04-28-000000.txt', []),     # true wind is a proc file
    ('OpenRVDAS/raw/POSMV-2012-04-28-000000.txt', []),        # HDT and VTG are commented out
    ('OpenRVDAS/raw/notes.txt', []),
])
def test_openrvdas_data_types(openrvdas, path, data_types) -> None:
    """Each OpenRVDAS log goes to its parser's data type; others to none."""
    assert openrvdas.OpenRVDASPlugin().get_data_types(f'/data/CruiseData/TEST001/{path}') == data_types


@pytest.mark.parametrize('source, name, data_type, expected', [
    ('nmea/gga.txt', 'raw/POSMV_GGA-2012-04-28-000000.txt', 'gga', 'nmea_gga'),
    ('instruments/met.txt', 'raw/MET-2012-04-28-000000.txt', 'met', 'instruments_met'),
    ('instruments/ssv.txt', 'raw/SVP-2012-04-28-000000.txt', 'ssv', 'instruments_ssv'),
    ('instruments/tsg45.txt', 'raw/TSG_Raw-2012-04-28-000000.txt', 'tsg', 'instruments_tsg45_sbe38'),
    ('instruments/twind.txt', 'proc/TrueWind-2012-04-28-000000.txt', 'twind', 'instruments_twind'),
])
def test_openrvdas_parse_file(openrvdas, tmp_path, source, name, data_type, expected) -> None:
    """The plugin's output is its parser's, with the filter's options (TSG: column names and SBE38)."""
    path = _copy(source, tmp_path / 'OpenRVDAS' / name)
    result = _as_saved(openrvdas.process_file(str(path)))
    assert list(result) == [data_type]
    assert result[data_type]['stats'] == _expected(expected)['stats']
    assert result[data_type]['qualityTests'] == _expected(expected)['qualityTests']


def test_openrvdas_unknown_file(openrvdas) -> None:
    """A file no filter matches gives no output."""
    assert openrvdas.OpenRVDASPlugin().parse_file('/data/CruiseData/TEST001/OpenRVDAS/raw/notes.txt') == {}


def test_openrvdas_parser_fails(openrvdas, tmp_path, monkeypatch, caplog) -> None:
    """A parser that raises is logged, and the file's other data types are still returned."""
    plugin = openrvdas.OpenRVDASPlugin()
    monkeypatch.setitem(plugin.PARSER_MAP, 'GGA', FailingParser)
    path = _copy('nmea/gga.txt', tmp_path / 'OpenRVDAS' / 'raw' / 'POSMV_GGA-2012-04-28-000000.txt')
    assert plugin.parse_file(str(path)) == {}
    assert "Parser 'gga' failed" in caplog.text and 'cannot parse' in caplog.text


@pytest.mark.parametrize('parser, logged', [(None, "Unknown parser 'GGA'"), (_broken, 'Failed to instantiate parser GGA')])
def test_openrvdas_parser_missing_or_broken(openrvdas, monkeypatch, caplog, parser, logged) -> None:
    """A filter whose parser isn't in PARSER_MAP, or can't be made with its options, is logged and skipped."""
    plugin = openrvdas.OpenRVDASPlugin()
    if parser:
        monkeypatch.setitem(plugin.PARSER_MAP, 'GGA', parser)
    else:
        monkeypatch.delitem(plugin.PARSER_MAP, 'GGA')
    assert plugin.parse_file('/data/OpenRVDAS/raw/POSMV_GGA-2012-04-28-000000.txt') == {}
    assert logged in caplog.text


# --- ROV OpenRVDAS ----------------------------------------------------------------

@pytest.fixture
def rov(load_plugin, fake_ovdm, monkeypatch):
    """The ROV OpenRVDAS plugin module, using the fake API (current lowering DIVE02)."""
    module = load_plugin('rov_openrvdas', 'comp_pres', 'ctd', 'gga', 'o2', 'paro', 'sprint')
    monkeypatch.setattr(module, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_lowering_id.return_value = 'DIVE02'
    fake_ovdm.get_lowering_config_fn.return_value = 'lowering_config.json'
    return module


class FakeSealog:
    """A fake ``requests.get`` for Sealog's lowerings API: ``lowerings`` by ID."""

    def __init__(self):
        self.lowerings = {}
        self.requests = []

    def __call__(self, url, headers=None, timeout=None):
        self.requests.append((url, headers))
        lowering_id = url.split('lowering_id=')[1]
        return SimpleNamespace(text=json.dumps([self.lowerings[lowering_id]] if lowering_id in self.lowerings else []))


@pytest.fixture
def sealog(rov, monkeypatch):
    """A :class:`FakeSealog` as the ROV plugin's ``requests.get``."""
    server = FakeSealog()
    monkeypatch.setattr(rov.requests, 'get', server)
    return server


@pytest.mark.parametrize('name, data_type', [
    ('Mech_Comps_Raw', 'rov-comp-pres'), ('CTD_Raw', 'rov-ctd'), ('O2_Raw', 'rov-o2'),
    ('Paro_Depth_Raw', 'rov-paro'), ('Sprint_Raw', 'rov-sprint'), ('USBL_Pri_GGA_Raw', 'rov-usbl-pri'),
    ('USBL_Sec_GGA_Raw', 'rov-usbl-sec'),
])
def test_rov_data_types(rov, name, data_type) -> None:
    """Each ROV OpenRVDAS log goes to its parser's data type."""
    assert rov.ROVOpenRVDASPlugin().get_data_types(f'/data/Vehicle/DIVE01/OpenRVDAS/raw/{name}-2019-08-11-190335.txt') \
        == [data_type]


@pytest.mark.parametrize('lowering, path, expected', [
    ('DIVE09', 'Vehicle/DIVE01/OpenRVDAS/raw/CTD_Raw-x.txt', 'DIVE09'),   # the lowering option wins
    (None, 'Vehicle/DIVE01/OpenRVDAS/raw/CTD_Raw-x.txt', 'DIVE01'),       # from the path
    (None, 'ROV/OpenRVDAS/raw/CTD_Raw-x.txt', 'DIVE02'),                  # the current lowering
    (None, 'Vehicle/CTD_Raw-x.txt', 'DIVE02'),                            # Vehicle/ with no lowering in it
])
def test_rov_lowering_for(rov, warehouse, lowering, path, expected) -> None:
    """A file's lowering is the lowering option's, else the one in its path, else the current one."""
    plugin = rov.ROVOpenRVDASPlugin(lowering=lowering)
    assert plugin._lowering_for(str(warehouse.cruise_dir / path)) == expected


def test_rov_sealog_window(rov, sealog) -> None:
    """With Sealog, the lowering's window is from its descending and on-surface milestones; it's cached."""
    sealog.lowerings['DIVE01'] = {'start_ts': '2019-08-11T19:00:00.000Z', 'stop_ts': '2019-08-12T01:00:00.000Z',
                                  'lowering_additional_meta': {'milestones': {
                                      'lowering_descending': '2019-08-11T20:13:00.000Z',
                                      'lowering_floats_on_surface': '2019-08-11T23:00:00.000Z'}}}
    plugin = rov.ROVOpenRVDASPlugin()
    start, stop = plugin.get_lowering_window('DIVE01')
    assert (start.isoformat(), stop.isoformat()) == ('2019-08-11T20:13:00+00:00', '2019-08-11T23:00:00+00:00')
    plugin.get_lowering_window('DIVE01')
    assert len(sealog.requests) == 1
    assert sealog.requests[0] == ('http://localhost:8000/sealog-server/api/v1/lowerings?lowering_id=DIVE01',
                                  {'authorization': '<TOKEN>'})


def test_rov_sealog_window_without_milestones(rov, sealog) -> None:
    """Without the milestones, the lowering's start and stop times are used."""
    sealog.lowerings['DIVE01'] = {'start_ts': '2019-08-11T19:00:00.000Z', 'stop_ts': '2019-08-12T01:00:00.000Z'}
    start, stop = rov.ROVOpenRVDASPlugin().get_lowering_window('DIVE01')
    assert (start.isoformat(), stop.isoformat()) == ('2019-08-11T19:00:00+00:00', '2019-08-12T01:00:00+00:00')


def test_rov_sealog_lowering_not_found(rov, sealog, caplog) -> None:
    """A lowering Sealog doesn't have gives no window: the data isn't cropped."""
    assert rov.ROVOpenRVDASPlugin().get_lowering_window('DIVE01') == (None, None)
    assert 'Lowering DIVE01 not found in Sealog' in caplog.text
    assert "data won't be cropped" in caplog.text


def test_rov_openvdm_window(rov, warehouse) -> None:
    """Without Sealog, the window is from the lowering's OpenVDM lowering config file."""
    lowering_dir = warehouse.cruise_dir / 'Vehicle' / 'DIVE01'
    lowering_dir.mkdir(parents=True)
    (lowering_dir / 'lowering_config.json').write_text(json.dumps(
        {'loweringStartDate': '2019/08/11 20:13', 'loweringEndDate': '2019/08/11 23:00:30'}))
    start, stop = rov.ROVOpenRVDASPlugin(use_sealog_api=False).get_lowering_window('DIVE01')
    assert (start.isoformat(), stop.isoformat()) == ('2019-08-11T20:13:00+00:00', '2019-08-11T23:00:30+00:00')


def test_rov_openvdm_window_no_config(rov) -> None:
    """Without the lowering config file, there's no window."""
    assert rov.ROVOpenRVDASPlugin(use_sealog_api=False).get_lowering_window('DIVE01') == (None, None)


def test_rov_no_lowering(rov) -> None:
    """Without a lowering, there's no window."""
    assert rov.ROVOpenRVDASPlugin().get_lowering_window(None) == (None, None)


def test_rov_unrecognised_time(rov, caplog) -> None:
    """A lowering time in another format is logged and ignored."""
    assert rov.ROVOpenRVDASPlugin._parse_time('11 Aug 2019') is None
    assert 'Unrecognised lowering time: 11 Aug 2019' in caplog.text


def test_rov_parse_file_crops_to_lowering(rov, sealog, warehouse) -> None:
    """The file is cropped to its lowering's window."""
    sealog.lowerings['DIVE01'] = {'start_ts': '2019-08-11T20:40:00.000Z', 'stop_ts': '2019-08-11T20:41:00.000Z'}
    path = _copy('instruments/ctd.txt', warehouse.cruise_dir / 'Vehicle' / 'DIVE01' / 'OpenRVDAS' / 'raw'
                 / 'CTD_Raw-2019-08-11-190335.txt')
    result = _as_saved(rov.process_file(str(path)))
    bounds = next(stat['statValue'] for stat in result['rov-ctd']['stats'] if stat['statName'] == 'Temporal Bounds')
    assert '2019-08-11T20:40:00' <= bounds[0] <= bounds[1] <= '2019-08-11T20:41:00'


def test_rov_parse_file_uncropped(rov, sealog, warehouse) -> None:
    """Without a window, the file's output is its parser's."""
    path = _copy('instruments/o2.txt', warehouse.cruise_dir / 'Vehicle' / 'DIVE01' / 'OpenRVDAS' / 'raw'
                 / 'O2_Raw-2019-08-11-190335.txt')
    result = _as_saved(rov.process_file(str(path)))
    assert result['rov-o2']['stats'] == _expected('instruments_o2')['stats']


def test_rov_parser_fails(rov, sealog, monkeypatch, caplog) -> None:
    """A parser that raises is logged and its data type left out."""
    plugin = rov.ROVOpenRVDASPlugin()
    monkeypatch.setitem(plugin.PARSER_MAP, 'CTD', FailingParser)
    assert plugin.parse_file('/data/Vehicle/DIVE01/OpenRVDAS/raw/CTD_Raw-x.txt') == {}
    assert "Parser 'rov-ctd' failed" in caplog.text


@pytest.mark.parametrize('parser, logged', [(None, "Unknown parser 'CTD'"), (_broken, 'Failed to instantiate parser CTD')])
def test_rov_parser_missing_or_broken(rov, sealog, monkeypatch, caplog, parser, logged) -> None:
    """A filter whose parser isn't in PARSER_MAP, or can't be made, is logged and skipped."""
    plugin = rov.ROVOpenRVDASPlugin()
    if parser:
        monkeypatch.setitem(plugin.PARSER_MAP, 'CTD', parser)
    else:
        monkeypatch.delitem(plugin.PARSER_MAP, 'CTD')
    assert plugin.parse_file('/data/Vehicle/DIVE01/OpenRVDAS/raw/CTD_Raw-x.txt') == {}
    assert logged in caplog.text


def test_rov_unknown_file(rov) -> None:
    """A file no filter matches gives no output."""
    assert rov.ROVOpenRVDASPlugin().parse_file('/data/Vehicle/DIVE01/notes.txt') == {}


# --- CTD --------------------------------------------------------------------------

@pytest.fixture
def ctd_plugin(load_plugin):
    """The CTD plugin module."""
    return load_plugin('ctd', 'ctd_profile')


@pytest.fixture
def cast(tmp_path):
    """A copy of the CTD test cast, ``CTD002.HEX`` and ``CTD002.XMLCON``, in *tmp_path*."""
    _copy('profiles/ctd002.XMLCON', tmp_path / 'CTD002.XMLCON')
    return _copy('profiles/ctd002.hex', tmp_path / 'CTD002.HEX')


@pytest.mark.parametrize('name, data_types', [
    ('CTD002.hex', ['ctd', 'ctd-position']), ('CTD002.HEX', ['ctd', 'ctd-position']),
    ('CTD002.xmlcon', []), ('CTD002.bl', []),
])
def test_ctd_data_types(ctd_plugin, name, data_types) -> None:
    """A cast's .hex file, in any case, is both a profile and a position."""
    assert ctd_plugin.CTDPlugin().get_data_types(f'/data/CTD/{name}') == data_types


def test_ctd_source_files(ctd_plugin, cast) -> None:
    """A cast's .xmlcon means its .hex (in any case); other files mean themselves."""
    assert ctd_plugin.get_source_files(str(cast.with_suffix('.XMLCON'))) == [str(cast)]
    assert ctd_plugin.get_source_files(str(cast)) == [str(cast)]
    assert ctd_plugin.get_source_files(str(cast.with_name('CTD003.xmlcon'))) == []


def test_ctd_parse_file(ctd_plugin, cast) -> None:
    """The cast's profile and position are the parsers' output."""
    result = _as_saved(ctd_plugin.process_file(str(cast)))
    assert result['ctd']['stats'] == _expected('profiles_ctd')['stats']
    point = result['ctd-position']['visualizerData'][0]['features'][0]
    assert point['properties']['cast'] == 'CTD002'
    assert point['geometry'] == _expected('profiles_ctd_position')['visualizerData'][0]['features'][0]['geometry']


def test_ctd_cast_without_xmlcon(ctd_plugin, cast, caplog) -> None:
    """A cast without its XMLCON is skipped, with the reason; its position is still returned."""
    cast.with_suffix('.XMLCON').unlink()
    assert list(ctd_plugin.process_file(str(cast))) == ['ctd-position']
    assert f'CTD cast {cast} skipped: No calibration file' in caplog.text


def test_ctd_cast_without_data(ctd_plugin, cast, caplog) -> None:
    """A cast with only its header has no profile; that's logged."""
    text = cast.read_text(encoding='latin-1')
    cast.write_text(text[:text.index('*END*') + 6], encoding='latin-1')
    assert list(ctd_plugin.process_file(str(cast))) == ['ctd-position']
    assert f'CTD cast {cast} has no data' in caplog.text


def test_ctd_parser_fails(ctd_plugin, cast, monkeypatch, caplog) -> None:
    """Any other error is logged with its traceback, and the other data type kept."""
    plugin = ctd_plugin.CTDPlugin()
    monkeypatch.setitem(plugin.PARSER_MAP, 'CTDProfile', FailingParser)
    assert list(plugin.parse_file(str(cast))) == ['ctd-position']
    assert "Parser 'ctd' failed" in caplog.text


@pytest.mark.parametrize('parser, logged', [(None, "Unknown parser 'CTDProfile'"),
                                            (_broken, 'Failed to instantiate parser CTDProfile')])
def test_ctd_parser_missing_or_broken(ctd_plugin, cast, monkeypatch, caplog, parser, logged) -> None:
    """A filter whose parser isn't in PARSER_MAP, or can't be made, is logged and skipped."""
    plugin = ctd_plugin.CTDPlugin()
    if parser:
        monkeypatch.setitem(plugin.PARSER_MAP, 'CTDProfile', parser)
    else:
        monkeypatch.delitem(plugin.PARSER_MAP, 'CTDProfile')
    assert list(plugin.parse_file(str(cast))) == ['ctd-position']
    assert logged in caplog.text


def test_ctd_unknown_file(ctd_plugin) -> None:
    """A file that isn't a cast gives no output."""
    assert ctd_plugin.CTDPlugin().parse_file('/data/CTD/CTD002.bl') == {}


# --- XBT --------------------------------------------------------------------------

@pytest.fixture
def xbt_plugin(load_plugin):
    """The XBT plugin module (skipped without xbt-edf-qc)."""
    pytest.importorskip('parse_xbt_edf')
    return load_plugin('xbt', 'xbt')


@pytest.mark.parametrize('name, data_types', [
    ('XBT001.EDF', ['xbt', 'xbt-position']), ('XBT001.edf', ['xbt', 'xbt-position']), ('XBT001.RDF', []),
])
def test_xbt_data_types(xbt_plugin, name, data_types) -> None:
    """A cast's .EDF export, in any case, is both a profile and a position."""
    assert xbt_plugin.XBTPlugin().get_data_types(f'/data/XBT/{name}') == data_types


def test_xbt_parse_file(xbt_plugin, tmp_path) -> None:
    """The cast's profile and position are the parsers' output."""
    path = _copy('profiles/xbt001.EDF', tmp_path / 'XBT001.EDF')
    result = _as_saved(xbt_plugin.process_file(str(path)))
    assert result['xbt']['stats'] == _expected('profiles_xbt001')['stats']
    assert result['xbt-position']['visualizerData'][0]['features'][0]['properties']['cast'] == 'XBT001'


def test_xbt_not_an_edf(xbt_plugin, tmp_path, caplog) -> None:
    """A file that isn't an EDF export is skipped, with the reason."""
    path = tmp_path / 'XBT001.EDF'
    path.write_text('not an EDF file\n')
    assert xbt_plugin.process_file(str(path)) == {}
    assert f'XBT cast {path} skipped' in caplog.text


def test_xbt_test_probe(xbt_plugin, tmp_path, caplog) -> None:
    """A test probe cast has no data; that's logged."""
    path = tmp_path / 'XBT001.EDF'
    path.write_text((PARSER_DATA / 'profiles' / 'xbt001.EDF').read_text(encoding='cp1252')
                    .replace('Serial Number    :  ', 'Serial Number    :  TestProbe'), encoding='cp1252')
    assert xbt_plugin.process_file(str(path)) == {}
    assert f'XBT cast {path} has no data' in caplog.text


def test_xbt_parser_fails(xbt_plugin, tmp_path, monkeypatch, caplog) -> None:
    """Any other error is logged with its traceback, and the other data type kept."""
    plugin = xbt_plugin.XBTPlugin()
    monkeypatch.setitem(plugin.PARSER_MAP, 'XBTProfile', FailingParser)
    path = _copy('profiles/xbt001.EDF', tmp_path / 'XBT001.EDF')
    assert list(plugin.parse_file(str(path))) == ['xbt-position']
    assert "Parser 'xbt' failed" in caplog.text


@pytest.mark.parametrize('parser, logged', [(None, "Unknown parser 'XBTProfile'"),
                                            (_broken, 'Failed to instantiate parser XBTProfile')])
def test_xbt_parser_missing_or_broken(xbt_plugin, tmp_path, monkeypatch, caplog, parser, logged) -> None:
    """A filter whose parser isn't in PARSER_MAP, or can't be made, is logged and skipped."""
    plugin = xbt_plugin.XBTPlugin()
    if parser:
        monkeypatch.setitem(plugin.PARSER_MAP, 'XBTProfile', parser)
    else:
        monkeypatch.delitem(plugin.PARSER_MAP, 'XBTProfile')
    path = _copy('profiles/xbt001.EDF', tmp_path / 'XBT001.EDF')
    assert list(plugin.parse_file(str(path))) == ['xbt-position']
    assert logged in caplog.text


def test_xbt_unknown_file(xbt_plugin) -> None:
    """A file that isn't an EDF export gives no output."""
    assert xbt_plugin.XBTPlugin().parse_file('/data/XBT/XBT001.RDF') == {}


# --- EM302 ------------------------------------------------------------------------

@pytest.fixture
def em302(load_plugin, monkeypatch):
    """The EM302 plugin module, with its TiTiler parser asking a fake TiTiler."""
    module = load_plugin('em302', 'geotiff_titiler')
    parser_module = sys.modules['server.plugins.parsers.geotiff_titiler_parser']
    info = {'bbox': [-94.0, 26.5, -93.25, 27.1], 'properties': {'colorinterp': ['red', 'green', 'blue', 'alpha']}}
    monkeypatch.setattr(parser_module.requests, 'get',
                        lambda url, params=None, timeout=None: SimpleNamespace(raise_for_status=lambda: None,
                                                                               json=lambda: info))
    return module


def test_em302_data_types(em302) -> None:
    """A GeoTIFF is the geotiff data type."""
    assert em302.EM302Plugin().get_data_types('/data/CruiseData/TEST001/EM302/proc/bathy.tif') == ['geotiff']
    assert em302.EM302Plugin().get_data_types('/data/CruiseData/TEST001/EM302/raw/0001.all') == []


def test_em302_parse_file(em302) -> None:
    """The GeoTIFF's output is the TiTiler parser's."""
    result = _as_saved(em302.process_file('/data/CruiseData/TEST001/EM302/proc/bathy.tif'))
    assert result['geotiff']['visualizerData'] == [{
        'label': 'bathy', 'tileURL': 'http://localhost/CruiseData/TEST001/EM302/proc/bathy.tif',
        'mapBounds': '-94.0,26.5,-93.25,27.1'}]


def test_em302_parser_fails(em302, monkeypatch, caplog) -> None:
    """A parser that raises (TiTiler unreachable) is logged, and there's no output."""
    plugin = em302.EM302Plugin()
    monkeypatch.setitem(plugin.PARSER_MAP, 'GeoTIFF', FailingParser)
    assert plugin.parse_file('/data/EM302/proc/bathy.tif') == {}
    assert "Parser 'geotiff' failed" in caplog.text


@pytest.mark.parametrize('parser, logged', [(None, "Unknown parser 'GeoTIFF'"),
                                            (_broken, 'Failed to instantiate parser GeoTIFF')])
def test_em302_parser_missing_or_broken(em302, monkeypatch, caplog, parser, logged) -> None:
    """A filter whose parser isn't in PARSER_MAP, or can't be made, is logged and skipped."""
    plugin = em302.EM302Plugin()
    if parser:
        monkeypatch.setitem(plugin.PARSER_MAP, 'GeoTIFF', parser)
    else:
        monkeypatch.delitem(plugin.PARSER_MAP, 'GeoTIFF')
    assert plugin.parse_file('/data/EM302/proc/bathy.tif') == {}
    assert logged in caplog.text


def test_em302_unknown_file(em302) -> None:
    """A file no filter matches gives no output."""
    assert em302.EM302Plugin().parse_file('/data/EM302/raw/0001.all') == {}


@pytest.mark.parametrize('plugin', ['openrvdas', 'rov_openrvdas', 'em302'])
def test_file_without_data(load_plugin, fake_ovdm, monkeypatch, tmp_path, caplog, plugin) -> None:
    """A file its parser finds no data in gives no output, not an empty data set (#574)."""
    caplog.set_level(logging.WARNING)
    if plugin == 'em302':
        module = load_plugin('em302', 'geotiff_titiler')
        instance = module.EM302Plugin()
        monkeypatch.setitem(instance.PARSER_MAP, 'GeoTIFF', EmptyParser)
        assert instance.parse_file('/data/EM302/proc/bathy.tif') == {}
        return
    if plugin == 'openrvdas':
        module = load_plugin('openrvdas', *OPENRVDAS_PARSERS)
        instance, name = module.OpenRVDASPlugin(), 'OpenRVDAS/raw/POSMV_GGA-2012-04-28-000000.txt'
    else:
        module = load_plugin('rov_openrvdas', 'comp_pres', 'ctd', 'gga', 'o2', 'paro', 'sprint')
        monkeypatch.setattr(module, 'OpenVDM', lambda: fake_ovdm)
        instance, name = module.ROVOpenRVDASPlugin(lowering='DIVE01', use_sealog_api=False), \
            'Vehicle/DIVE01/OpenRVDAS/raw/USBL_Pri_GGA_Raw-2019-08-11-190335.txt'
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_text('')
    assert instance.parse_file(str(path)) == {}
