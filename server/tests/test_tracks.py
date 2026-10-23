"""Tests for trackline building: geojson_utils.py and tracks.py (#507).

The trackline scripts (``bin/build_cruise_tracks.py`` and
``bin/build_lowering_tracks.py``) find a position source's data dashboard
files through the manifest, combine their GeoJSON tracks, and write
``<prefix>_<device>_Trackline.json`` and ``.kml``, plus the cruise's or
lowering's extent (bounding box).
"""

import argparse
import json
import logging
import os
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from server.lib import geojson_utils as gj
from server.lib import tracks

KML = '{http://www.opengis.net/kml/2.2}'


def _track(coords, times, name='t'):
    """A GeoJSON FeatureCollection with one LineString, as a parser produces."""
    return {'type': 'FeatureCollection', 'features': [{
        'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coords},
        'properties': {'name': name, 'coordTimes': times}}]}


def _legacy_file(path, coords, times):
    """A dashboard file in the old format: visualizerData at the top level."""
    path.write_text(json.dumps({'visualizerData': [_track(coords, times)], 'stats': []}))
    return str(path)


def _file(path, coords, times, data_type='gga'):
    """A dashboard file as the data dashboard writes it today: one entry per data type."""
    path.write_text(json.dumps({data_type: {'visualizerData': [_track(coords, times)], 'stats': []}}))
    return str(path)


# --- Combining tracks ---------------------------------------------------------

def test_combine_files_in_order(tmp_path) -> None:
    """Each file's coordinates and times are appended, in the old and new formats alike."""
    first = _legacy_file(tmp_path / 'a.json', [[-120, 45], [-120.1, 45.1]], ['t1', 't2'])
    second = _file(tmp_path / 'b.json', [[-120.2, 45.2]], ['t3'])

    combined = gj.combine_geojson_files([first, second], 'TEST001', 'gps')

    feature = combined['features'][0]
    assert feature['properties'] == {'name': 'TEST001_gps', 'coordTimes': ['t1', 't2', 't3']}
    assert feature['geometry'] == {'type': 'LineString', 'coordinates': [[-120, 45], [-120.1, 45.1], [-120.2, 45.2]]}


def test_visualizer_entries() -> None:
    """Every visualizerData entry, from the old format and the current one (keyed by data type) (#602)."""
    assert list(gj.visualizer_entries({'visualizerData': [1, 2], 'gga': {'visualizerData': [3]},
                                       'stats': [], 'hdt': {'stats': []}, 'x': 'not a dict'})) == [1, 2, 3]
    assert list(gj.visualizer_entries({'visualizerData': 'not a list'})) == []
    assert list(gj.visualizer_entries(['not', 'a', 'dict'])) == []


def test_combine_skips_other_data(tmp_path) -> None:
    """Visualizer data that isn't a GeoJSON LineString (charts, points, bad values) is skipped."""
    path = tmp_path / 'mixed.json'
    path.write_text(json.dumps({'visualizerData': [
        {'type': 'chart', 'data': []},
        'not a dict',
        {'type': 'FeatureCollection', 'features': 'not a list'},
        {'type': 'FeatureCollection', 'features': [
            {'geometry': {'type': 'Point', 'coordinates': [1, 2]}},
            {'geometry': {'type': 'LineString', 'coordinates': 'bad'}, 'properties': {}},
            {'geometry': {'type': 'LineString', 'coordinates': [[1, 2]]}, 'properties': {'coordTimes': ['t']}},
        ]},
    ]}))
    combined = gj.combine_geojson_files([str(path)], 'P', 'gps')
    assert combined['features'][0]['geometry']['coordinates'] == [[1, 2]]


def test_combine_without_tracks(tmp_path, caplog) -> None:
    """No files, or files without GeoJSON tracks, give no trackline."""
    assert gj.combine_geojson_files([], 'P', 'gps') is None
    path = tmp_path / 'chart.json'
    path.write_text(json.dumps({'visualizerData': [{'type': 'chart'}]}))
    assert gj.combine_geojson_files([str(path)], 'P', 'gps') is None
    assert 'No GeoJSON track data found for gps' in caplog.text


def test_combine_fails_on_an_unreadable_file(tmp_path, caplog) -> None:
    """One file that can't be read fails the whole trackline (as documented)."""
    good = _file(tmp_path / 'good.json', [[1, 2]], ['t'])
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json')
    assert gj.combine_geojson_files([good, str(bad)], 'P', 'gps') is None
    assert f'Could not process file: {bad}' in caplog.text


# --- Extent -------------------------------------------------------------------

@pytest.mark.parametrize('coords, expected', [
    ([[-120, 45], [-121.5, 44], [-119, 46.25]], (-121.5, -119, 44, 46.25)),
    ([[179, -10], [-179, -11], [178.5, -9]], (178.5, -179, -11, -9)),
    ([[180, 0], [-179.5, 1]], (-180, -179.5, 0, 1)),
    ([[10.1234567, 20.7654321]], (10.123457, 10.123457, 20.765432, 20.765432)),
])
def test_geojson_extent(coords, expected) -> None:
    """The box leaves out the largest gap in longitude, so one across the antimeridian has west > east (#366)."""
    extent = gj.geojson_extent(_track(coords, []))
    assert (extent['westernmost'], extent['easternmost'], extent['southernmost'], extent['northernmost']) == expected


def test_geojson_extent_of_any_geometry() -> None:
    """Positions are found in features, geometry collections and nested coordinates; bad ones skipped."""
    obj = [
        {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [2, 0], [2, 3], [0, 0]]]}},
        {'type': 'GeometryCollection', 'geometries': [{'type': 'Point', 'coordinates': [-1, -1, 50]}]},
        {'type': 'Point', 'coordinates': [200, 0]},
        {'type': 'Point', 'coordinates': [True, False]},
        {'type': 'Point', 'coordinates': ['1', '2']},
    ]
    assert gj.geojson_extent(obj) == {'westernmost': -1, 'easternmost': 2, 'southernmost': -1, 'northernmost': 3}
    assert gj.geojson_extent(_track([], [])) is None
    assert gj.geojson_extent(None) is None


# --- KML ----------------------------------------------------------------------

def _parse_kml(text):
    """Check the XML declaration and parse the KML."""
    assert text.startswith('<?xml version="1.0" encoding="utf-8"?>')
    return ElementTree.fromstring(text.split('?>', 1)[1])


@pytest.mark.parametrize('times, begin, end', [
    (['2026-10-22T10:00:00Z', '2026-10-22T11:00:00Z'], '2026-10-22T10:00:00Z', '2026-10-22T11:00:00Z'),
    ([1792663200, 1792666800], '2026-10-22T10:00:00Z', '2026-10-22T11:00:00Z'),
    ([1792663200000, 1792666800000.0], '2026-10-22T10:00:00Z', '2026-10-22T11:00:00Z'),
])
def test_convert_to_kml(times, begin, end) -> None:
    """A Placemark with the track's coordinates and a TimeSpan from ISO, epoch s or epoch ms times."""
    root = _parse_kml(gj.convert_to_kml(_track([[-120.5, 45.25, 3], [-120.6, 45.3]], times, name='TEST001_gps')))
    assert root.find(f'{KML}Document/{KML}name').text == 'TEST001_gps_Trackline.kml'
    placemark = root.find(f'{KML}Document/{KML}Placemark')
    assert placemark.find(f'{KML}LineString/{KML}coordinates').text == '-120.5,45.25,0 -120.6,45.3,0'
    assert placemark.find(f'{KML}TimeSpan/{KML}begin').text == begin
    assert placemark.find(f'{KML}TimeSpan/{KML}end').text == end


def test_convert_to_kml_without_usable_times(caplog) -> None:
    """Fewer than two times, or times of another type, give no TimeSpan."""
    for times in ([], ['2026-10-22T10:00:00Z'], [None, None]):
        placemark = _parse_kml(gj.convert_to_kml(_track([[0, 0]], times))).find(f'{KML}Document/{KML}Placemark')
        assert placemark.find(f'{KML}TimeSpan') is None
    assert 'Skipping TimeSpan due to invalid coordTimes' in caplog.text

    unnamed = {'features': [{'geometry': {'coordinates': []}}]}
    assert _parse_kml(gj.convert_to_kml(unnamed)).find(f'{KML}Document/{KML}name').text == 'Trackline_Trackline.kml'


# --- Position sources ---------------------------------------------------------

SOURCES = """
PositionSources:
  - device: gps
    type: gga
  - device: usbl
    type: usbl_pos
    extent: true
"""


def test_load_position_sources() -> None:
    """The sources from a string or a file; CollectionSystem is optional (#412)."""
    sources = tracks.load_position_sources_from_yaml(yaml_str=SOURCES, collection_system='OpenRVDAS')
    assert [src['device'] for src in sources] == ['gps', 'usbl']
    assert tracks.load_position_sources_from_yaml(
        yaml_str='CollectionSystem: OpenRVDAS\nGPSSources: [{device: gps, type: gga}]',
        collection_system='OpenRVDAS') == [{'device': 'gps', 'type': 'gga'}]


def test_load_position_sources_from_a_file(tmp_path) -> None:
    """From a file; a missing file is a RuntimeError."""
    path = tmp_path / 'sources.yaml'
    path.write_text(SOURCES)
    assert len(tracks.load_position_sources_from_yaml(yaml_path=str(path), collection_system='x')) == 2
    with pytest.raises(RuntimeError, match='not found'):
        tracks.load_position_sources_from_yaml(yaml_path=str(tmp_path / 'missing.yaml'), collection_system='x')


@pytest.mark.parametrize('yaml_str, message', [
    ('', 'Either yaml_str or yaml_path'),
    ('PositionSources: [unclosed', 'Invalid position sources YAML'),
    ('- just a list', 'must be a mapping'),
    ('CollectionSystem: SCS\nPositionSources: []', 'CollectionSystem mismatch: SCS != OpenRVDAS'),
    ('PositionSources: {device: gps}', 'must be a list'),
    ('PositionSources: [{device: gps}]', "exactly one 'device' and one 'type'"),
    ('PositionSources: [{device: gps, type: a}, {device: gps, type: b}]', 'Duplicate position source device: gps'),
    ('PositionSources: [{device: a, type: gga}, {device: b, type: gga}]', 'Manifest type reused across devices'),
    ('PositionSources: [gps]', "exactly one 'device' and one 'type'"),   # #537
    ('PositionSources: []', 'must list at least one source'),             # #537
])
def test_load_position_sources_errors(yaml_str, message) -> None:
    """Every problem with the YAML is a RuntimeError that says what's wrong."""
    with pytest.raises(RuntimeError, match=message):
        tracks.load_position_sources_from_yaml(yaml_str=yaml_str, collection_system='OpenRVDAS')


def test_get_position_sources(tmp_path) -> None:
    """--position-sources, else the script's embedded default."""
    path = tmp_path / 's.yaml'
    path.write_text('PositionSources: [{device: from_file, type: t}]')
    args = argparse.Namespace(position_sources_file=str(path), collectionSystem='x')
    assert tracks.get_position_sources(args, SOURCES)[0]['device'] == 'from_file'
    args.position_sources_file = None
    assert tracks.get_position_sources(args, SOURCES)[0]['device'] == 'gps'


def test_extent_position_source() -> None:
    """The source marked extent: true, else the first; only one may be marked (#399)."""
    sources = tracks.load_position_sources_from_yaml(yaml_str=SOURCES, collection_system='x')
    assert tracks.extent_position_source(sources)['device'] == 'usbl'
    assert tracks.extent_position_source(sources[:1])['device'] == 'gps'
    with pytest.raises(RuntimeError, match='Only one'):
        tracks.extent_position_source([{'device': 'a', 'extent': True}, {'device': 'b', 'extent': True}])


# --- Manifest -----------------------------------------------------------------

@pytest.fixture
def cruise(tmp_path, fake_ovdm):
    """A cruise with a Dashboard_Data manifest listing two GGA files and one other."""
    base = tmp_path / 'CruiseData'
    dashboard = base / 'TEST001' / 'Dashboard_Data'
    (dashboard / 'OpenRVDAS').mkdir(parents=True)
    files = {
        'gga_2.json': ([[-120.2, 45.2]], ['2026-10-22T10:02:00Z']),
        'gga_1.json': ([[-120.0, 45.0], [-120.1, 45.1]], ['2026-10-22T10:00:00Z', '2026-10-22T10:01:00Z']),
    }
    for name, (coords, times) in files.items():
        _file(dashboard / 'OpenRVDAS' / name, coords, times)
    manifest = [{'type': 'gga', 'dd_json': f'TEST001/Dashboard_Data/OpenRVDAS/{name}', 'raw_data': 'x'}
                for name in files]
    manifest.append({'type': 'met', 'dd_json': 'TEST001/Dashboard_Data/OpenRVDAS/met.json'})
    (dashboard / 'manifest.json').write_text(json.dumps(manifest))
    fake_ovdm.get_data_dashboard_manifest_fn.return_value = 'manifest.json'
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'destDir': 'Dashboard_Data'}
    return SimpleNamespace(base=str(base), dashboard=dashboard, manifest=manifest, ovdm=fake_ovdm)


def test_resolve_and_load_manifest(cruise) -> None:
    """The cruise's manifest, in the Dashboard_Data extra directory."""
    path = tracks.resolve_manifest_path(cruise.ovdm, cruise.base, 'TEST001')
    assert path == str(cruise.dashboard / 'manifest.json')
    assert tracks.load_manifest(path) == cruise.manifest


def test_lowering_manifest_path(cruise) -> None:
    """A lowering's manifest is in its folder inside Dashboard_Data."""
    (cruise.dashboard / 'Vehicle' / 'DIVE01').mkdir(parents=True)
    (cruise.dashboard / 'Vehicle' / 'DIVE01' / 'manifest.json').write_text('[]')
    assert tracks.resolve_manifest_path(cruise.ovdm, cruise.base, 'TEST001', 'Vehicle/DIVE01').endswith(
        'Dashboard_Data/Vehicle/DIVE01/manifest.json')


@pytest.mark.parametrize('manifest_fn, extra_dir, message', [
    ('', {'destDir': 'Dashboard_Data'}, 'no manifest filename'),
    ('manifest.json', None, 'Unable to find extra directory: Dashboard_Data'),
    ('other.json', {'destDir': 'Dashboard_Data'}, 'Manifest not found'),
])
def test_resolve_manifest_errors(cruise, manifest_fn, extra_dir, message) -> None:
    """No manifest name, no Dashboard_Data extra directory, or no file."""
    cruise.ovdm.get_data_dashboard_manifest_fn.return_value = manifest_fn
    cruise.ovdm.get_required_extra_directory_by_name.return_value = extra_dir
    with pytest.raises(RuntimeError, match=message):
        tracks.resolve_manifest_path(cruise.ovdm, cruise.base, 'TEST001')


@pytest.mark.parametrize('content, message', [
    ('{bad', 'Invalid manifest JSON'),
    ('{"type": "gga"}', 'must be a list'),
    ('[{"type": "gga"}]', "missing 'type' or 'dd_json'"),
])
def test_load_manifest_errors(tmp_path, content, message) -> None:
    """Invalid JSON, not a list, or entries missing a key."""
    path = tmp_path / 'manifest.json'
    path.write_text(content)
    with pytest.raises(RuntimeError, match=message):
        tracks.load_manifest(str(path))


def test_files_for_a_position_source(cruise) -> None:
    """The source's type only, sorted, as absolute paths."""
    files = tracks.get_dd_json_files_for_position_source(cruise.manifest, {'type': 'gga'}, cruise.base)
    assert [os.path.basename(f) for f in files] == ['gga_1.json', 'gga_2.json']
    assert files[0].startswith(cruise.base)


# --- Writing tracklines -------------------------------------------------------

def _args(**options):
    """The trackline scripts' parsed output options."""
    return argparse.Namespace(**{'no_combine': False, 'kml_only': False, 'geojson_only': False, **options})


@pytest.fixture
def chown(monkeypatch):
    """Record set_owner_group_permissions() calls instead of changing ownership."""
    calls = []
    monkeypatch.setattr(tracks, 'set_owner_group_permissions', lambda user, path: calls.append((user, path)))
    return calls


def test_process_position_source_combines(cruise, tmp_path, chown) -> None:
    """The source's files become one trackline, written as JSON and KML and owned by the user."""
    out = tmp_path / 'Tracklines'
    out.mkdir()
    written = []

    combined = tracks.process_position_source({'device': 'gps', 'type': 'gga'}, cruise.manifest, cruise.base,
                                              'TEST001', str(out), _args(), 'survey', written)

    assert combined['features'][0]['geometry']['coordinates'] == [[-120.0, 45.0], [-120.1, 45.1], [-120.2, 45.2]]
    assert sorted(os.listdir(out)) == ['TEST001_gps_Trackline.json', 'TEST001_gps_Trackline.kml']
    assert json.loads((out / 'TEST001_gps_Trackline.json').read_text()) == combined
    assert written == [(str(out / 'TEST001_gps_Trackline.json'), False), (str(out / 'TEST001_gps_Trackline.kml'), False)]
    assert [user for user, _ in chown] == ['survey', 'survey']


@pytest.mark.parametrize('option, kept', [('kml_only', '.kml'), ('geojson_only', '.json')])
def test_write_one_format(cruise, tmp_path, chown, option, kept) -> None:
    """--kml-only and --geojson-only write one file; -o (no user) leaves ownership alone."""
    tracks.process_position_source({'device': 'gps', 'type': 'gga'}, cruise.manifest, cruise.base, 'TEST001',
                                   str(tmp_path), _args(**{option: True}), None)
    assert [os.path.splitext(name)[1] for name in os.listdir(tmp_path) if 'Trackline' in name] == [kept]
    assert chown == []


def test_rewritten_files_are_updated_not_new(cruise, tmp_path, chown) -> None:
    """Files that existed are 'updated' for the MD5 summary."""
    for _ in range(2):
        written = []
        tracks.process_position_source({'device': 'gps', 'type': 'gga'}, cruise.manifest, cruise.base, 'TEST001',
                                       str(tmp_path), _args(), None, written)
    assert [existed for _, existed in written] == [True, True]


def test_write_failures(tmp_path, monkeypatch, caplog) -> None:
    """A JSON or KML file that can't be written is logged and not reported as written."""
    monkeypatch.setattr(tracks, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'disk full'})
    written = []
    tracks.write_outputs(_track([[0, 0]], []), 'gps', 'P', str(tmp_path / 'missing_dir'), _args(), None, written)
    assert written == []
    assert 'Write failed: disk full' in caplog.text and 'KML write failed' in caplog.text


def test_write_outputs_without_a_list(tmp_path) -> None:
    """The written-files list is optional."""
    tracks.write_outputs(_track([[0, 0]], []), 'gps', 'P', str(tmp_path), _args(geojson_only=True), None)
    assert os.listdir(tmp_path) == ['P_gps_Trackline.json']


def test_process_position_source_without_files(cruise, tmp_path, caplog) -> None:
    """A source without manifest entries writes nothing."""
    assert tracks.process_position_source({'device': 'ctd', 'type': 'ctd'}, cruise.manifest, cruise.base, 'P',
                                          str(tmp_path), _args(), None) is None
    assert 'No manifest entries found for ctd' in caplog.text


def test_process_position_source_combine_fails(cruise, tmp_path, caplog) -> None:
    """A source whose files cannot be combined writes nothing."""
    (cruise.dashboard / 'OpenRVDAS' / 'gga_1.json').write_text('{bad')
    assert tracks.process_position_source({'device': 'gps', 'type': 'gga'}, cruise.manifest, cruise.base, 'P',
                                          str(tmp_path), _args(), None) is None
    assert 'Failed to combine files for gps' in caplog.text


def test_no_combine_legacy_files(tmp_path, chown) -> None:
    """--no-combine writes one trackline per dashboard file, named after it."""
    base = tmp_path / 'base'
    base.mkdir()
    _legacy_file(base / 'gga_1.json', [[1, 2]], ['t'])
    (base / 'broken.json').write_text('{}')
    (base / 'unreadable.json').write_text('{not json')
    manifest = [{'type': 'gga', 'dd_json': name} for name in ('gga_1.json', 'broken.json', 'unreadable.json')]

    assert tracks.process_position_source({'device': 'gps', 'type': 'gga'}, manifest, str(base), 'P',
                                          str(tmp_path), _args(no_combine=True), None) is None
    assert sorted(name for name in os.listdir(tmp_path) if 'Trackline' in name) == [
        'P_gga_1_Trackline.json', 'P_gga_1_Trackline.kml']


def test_no_combine_current_files(cruise, tmp_path, chown) -> None:
    """--no-combine writes one trackline per dashboard file in today's per-data-type format (#536)."""
    tracks.process_position_source({'device': 'gps', 'type': 'gga'}, cruise.manifest, cruise.base, 'TEST001',
                                   str(tmp_path), _args(no_combine=True), None)
    assert sorted(name for name in os.listdir(tmp_path) if name.endswith('.json')) == [
        'TEST001_gga_1_Trackline.json', 'TEST001_gga_2_Trackline.json']


# --- Extent and MD5 -----------------------------------------------------------

def test_track_extent(cruise) -> None:
    """From the combined trackline, or by combining the files (--no-combine)."""
    source = {'device': 'gps', 'type': 'gga'}
    expected = {'westernmost': -120.2, 'easternmost': -120.0, 'southernmost': 45.0, 'northernmost': 45.2}
    assert tracks.track_extent(source, None, cruise.manifest, cruise.base, 'TEST001') == expected
    assert tracks.track_extent(source, _track([[1, 2]], []), [], cruise.base, 'P') == {
        'westernmost': 1, 'easternmost': 1, 'southernmost': 2, 'northernmost': 2}
    assert tracks.track_extent({'device': 'x', 'type': 'none'}, None, cruise.manifest, cruise.base, 'P') is None


def test_queue_md5_update(fake_ovdm) -> None:
    """New and rewritten files go to the MD5 summary update; a failure is a message, not an exception."""
    written = [('/c/a.json', False), ('/c/a.kml', True)]
    assert tracks.queue_md5_update(fake_ovdm, written, 'TEST001') is None
    fake_ovdm.update_md5_summary.assert_called_once_with(new=['/c/a.json'], updated=['/c/a.kml'], cruise_id='TEST001')

    fake_ovdm.update_md5_summary.side_effect = RuntimeError('gearman down')
    assert tracks.queue_md5_update(fake_ovdm, written, 'TEST001') == \
        'Unable to queue the MD5 summary update for the tracklines: gearman down'


# --- Setup --------------------------------------------------------------------

@pytest.fixture
def extra_dir(fake_ovdm, warehouse):
    """Return a function giving the Tracklines extra directory the settings passed."""
    def set_dir(**settings):
        fake_ovdm.get_extra_directory_by_name.return_value = {'enable': '1', 'cruiseOrLowering': '0', **settings}
    return set_dir


def test_resolve_extra_directory(fake_ovdm, warehouse, extra_dir) -> None:
    """{cruiseID} and {loweringDataBaseDir} are filled in; the folder must exist."""
    extra_dir(destDir='/Tracks/{cruiseID}/')
    (warehouse.cruise_dir / 'Tracks' / 'TEST001').mkdir(parents=True)
    assert tracks.resolve_extra_directory(fake_ovdm, 'Tracklines', str(warehouse.cruise_dir), 'TEST001',
                                          warehouse.config) == str(warehouse.cruise_dir / 'Tracks' / 'TEST001')


def test_resolve_lowering_extra_directory(fake_ovdm, warehouse, extra_dir) -> None:
    """For a lowering, {loweringID} is filled in, and a lowering-level directory is inside the lowering."""
    extra_dir(destDir='Tracks', cruiseOrLowering='1')
    (warehouse.cruise_dir / 'Vehicle' / 'DIVE01' / 'Tracks').mkdir(parents=True)
    assert tracks.resolve_extra_directory(fake_ovdm, 'Tracklines', str(warehouse.cruise_dir), 'TEST001',
                                          warehouse.config, 'DIVE01').endswith('Vehicle/DIVE01/Tracks')

    extra_dir(destDir='{loweringDataBaseDir}/{loweringID}/Tracks')
    assert tracks.resolve_extra_directory(fake_ovdm, 'Tracklines', str(warehouse.cruise_dir), 'TEST001',
                                          warehouse.config, 'DIVE01').endswith('Vehicle/DIVE01/Tracks')


@pytest.mark.parametrize('settings, message', [
    (None, 'No extra directory named Tracklines'),
    ({'enable': '0', 'destDir': 'Tracks'}, "isn't enabled"),
    ({'enable': '1', 'destDir': 'Tracks/{loweringID}'}, 'is per lowering'),
    ({'enable': '1', 'destDir': 'Missing'}, "folder doesn't exist"),
])
def test_resolve_extra_directory_errors(fake_ovdm, warehouse, settings, message) -> None:
    """Missing, disabled, per-lowering for a cruise, or without a folder."""
    fake_ovdm.get_extra_directory_by_name.return_value = settings
    with pytest.raises(RuntimeError, match=message):
        tracks.resolve_extra_directory(fake_ovdm, 'Tracklines', str(warehouse.cruise_dir), 'TEST001', warehouse.config)


def test_output_arguments_are_exclusive() -> None:
    """-e and -o can't be used together."""
    parser = argparse.ArgumentParser()
    tracks.add_output_arguments(parser)
    assert parser.parse_args(['-e', 'Nav']).extraDirectory == 'Nav'
    assert parser.parse_args(['-o', '/tmp/x']).outputDir == '/tmp/x'
    with pytest.raises(SystemExit):
        parser.parse_args(['-e', 'Nav', '-o', '/tmp/x'])


@pytest.mark.parametrize('verbosity, level', [(0, logging.WARNING), (1, logging.INFO), (2, logging.DEBUG),
                                              (5, logging.DEBUG)])
def test_setup_logging(verbosity, level) -> None:
    """WARNING, INFO with -v, DEBUG with -vv or more."""
    tracks.setup_logging(verbosity)
    assert logging.getLogger().level == level


def test_source_geojson() -> None:
    """The source's data type, or the old top-level format; the first FeatureCollection (#536)."""
    track = _track([[1, 2]], ['t'])
    chart = {'type': 'chart', 'data': []}
    assert tracks.source_geojson({'gga': {'visualizerData': [chart, track]}, 'hdt': {}}, 'gga') is track
    assert tracks.source_geojson({'visualizerData': [track]}, 'gga') is track
    assert tracks.source_geojson({'hdt': {'visualizerData': [track]}}, 'gga') is None
    assert tracks.source_geojson({'gga': {'visualizerData': 'bad'}}, 'gga') is None
    assert tracks.source_geojson([], 'gga') is None


def test_no_combine_skips_files_without_the_sources_track(tmp_path, chown, caplog) -> None:
    """A file with no GeoJSON for the source's data type is skipped with a message."""
    base = tmp_path / 'base'
    base.mkdir()
    _file(base / 'hdt_1.json', [[1, 2]], ['t'], data_type='hdt')
    manifest = [{'type': 'gga', 'dd_json': 'hdt_1.json'}]
    tracks.process_position_source({'device': 'gps', 'type': 'gga'}, manifest, str(base), 'P', str(tmp_path),
                                   _args(no_combine=True), None)
    assert not [name for name in os.listdir(tmp_path) if 'Trackline' in name]
    assert 'No GeoJSON track for gga in dashboard file' in caplog.text

