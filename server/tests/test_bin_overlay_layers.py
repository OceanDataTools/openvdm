"""Tests for bin/build_overlay_layers.py (#514 part 2).

The script writes ``overlay_layers.json``, the TiTiler tile layers the web
UI's map offers, from the GeoTIFF sources' data dashboard files. ``main()``
runs with a command line, the fake ``OpenVDM`` and a temporary cruise.
"""

import json
import sys
from types import SimpleNamespace
from urllib.parse import quote

import pytest

TILES = 'http://localhost/titiler/cog/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?url='


def _dashboard_file(path, label, tile_url, keyed=False):
    """A GeoTIFF parser's dashboard file: the old format, or keyed by data type as written today."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {'visualizerData': [{'label': label, 'tileURL': tile_url, 'mapBounds': '-1,-1,1,1'}],
            'qualityTests': [], 'stats': []}
    path.write_text(json.dumps({'geotiff': data} if keyed else data))


@pytest.fixture
def site(fake_ovdm, warehouse, tmp_path):
    """The cruise's Dashboard_Data with EM302 GeoTIFF dashboard files, and the web root."""
    dashboard = warehouse.cruise_dir / 'Dashboard_Data'
    _dashboard_file(dashboard / 'EM302' / 'proc' / 'b_bathy.json', 'b_bathy', 'http://ship/CruiseData/TEST001/b.tif')
    _dashboard_file(dashboard / 'EM302' / 'a_bathy.json', 'a_bathy', 'http://ship/CruiseData/TEST001/a.tif')
    web = tmp_path / 'www'
    web.mkdir()
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'destDir': 'Dashboard_Data'}
    fake_ovdm.get_collection_system_transfer_by_name.side_effect = lambda name: {
        'EM302': {'name': 'EM302', 'destDir': 'EM302'}, 'EM712': {'name': 'EM712', 'destDir': 'EM712'}}.get(name)
    return SimpleNamespace(ovdm=fake_ovdm, dashboard=dashboard, web=web, output=web / 'overlay_layers.json')


@pytest.fixture
def run(load_dist, monkeypatch, site):
    """Return a function that runs main() with *args* (and ``-o`` the web root); returns the exit status."""
    module = load_dist('bin/build_overlay_layers.py.dist', name='build_overlay_layers')
    monkeypatch.setattr(module, 'OpenVDM', lambda: site.ovdm)

    def run_script(*args, output=True):
        monkeypatch.setattr(sys, 'argv', ['build_overlay_layers', *(['-o', str(site.web)] if output else []), *args])
        try:
            module.main()
        except SystemExit as exc:
            return exc.code
        return 0
    return run_script


def test_overlay_layers(run, site, caplog) -> None:
    """Each GeoTIFF dashboard file becomes a layer, sorted by path, with a TiTiler tile URL; a
    source whose collection system has no dashboard folder (EM712) is logged."""
    assert run() == 0
    assert json.loads(site.output.read_text()) == [
        {'name': 'a_bathy', 'url': TILES + quote('http://ship/CruiseData/TEST001/a.tif', safe='')},
        {'name': 'b_bathy', 'url': TILES + quote('http://ship/CruiseData/TEST001/b.tif', safe='')}]
    assert 'Dashboard data directory for EM712 not found' in caplog.text


def test_sources_file(run, site, tmp_path, caplog) -> None:
    """--geotiff-sources replaces the default sources; its regex picks the files."""
    path = tmp_path / 'sources.yaml'
    path.write_text('GeoTiffSources:\n  - CollectionSystem: EM302\n    device: EM302\n    regex: "proc/*.json"\n'
                    '  - CollectionSystem: Missing\n    device: Missing\n    regex: "*.json"\n')
    assert run('--geotiff-sources', str(path)) == 0
    assert [layer['name'] for layer in json.loads(site.output.read_text())] == ['b_bathy']
    assert 'Collection System: Missing not found' in caplog.text


def test_invalid_and_empty(run, site, tmp_path, caplog) -> None:
    """A dashboard file that isn't a GeoTIFF's is logged and left out; no files writes an empty list."""
    (site.dashboard / 'EM302' / 'bad.json').write_text('{"visualizerData": []}')
    (site.dashboard / 'EM302' / 'broken.json').write_text('{cut short')
    assert run() == 0
    assert len(json.loads(site.output.read_text())) == 2
    assert 'Invalid dashboard file' in caplog.text
    path = tmp_path / 'sources.yaml'
    path.write_text('GeoTiffSources:\n  - CollectionSystem: EM302\n    device: EM302\n    regex: "*.tif"\n')
    assert run('--geotiff-sources', str(path)) == 0
    assert json.loads(site.output.read_text()) == []
    assert 'No files found for GeoTIFF source: EM302' in caplog.text


@pytest.mark.parametrize('content, message', [
    (None, 'GeoTIFF sources YAML not found'),
    ('GeoTiffSources: [unclosed', 'Invalid GeoTIFF sources YAML'),
    ('- a list', 'must be a mapping'),
    ('GeoTiffSources: EM302', 'GeoTiffSources must be a list'),
    ('GeoTiffSources:\n  - device: EM302\n    regex: "*"', "must define 'CollectionSystem', 'device', and 'regex'"),
    ('GeoTiffSources:\n  - {CollectionSystem: A, device: X, regex: "*"}\n  - {CollectionSystem: B, device: X, regex: "*"}',
     'Duplicate GeoTIFF device: X'),
])
def test_bad_sources_file(run, tmp_path, caplog, content, message) -> None:
    """A sources file that's missing or invalid exits 1, saying why."""
    path = tmp_path / 'sources.yaml'
    if content is not None:
        path.write_text(content)
    assert run('--geotiff-sources', str(path)) == 1
    assert message in caplog.text


@pytest.mark.parametrize('setup, message', [
    (lambda site: setattr(site.ovdm.get_cruise_id, 'return_value', None), 'Unable to determine CruiseID'),
    (lambda site: setattr(site.ovdm.get_cruise_id, 'return_value', 'NOPE'), 'Cruise data directory not found'),
    (lambda site: setattr(site.ovdm.get_required_extra_directory_by_name, 'return_value', None),
     'Unable to find extra directory: Dashboard_Data'),
    (lambda site: setattr(site.ovdm.get_required_extra_directory_by_name, 'return_value', {'destDir': 'nope'}),
     'Dashboard data directory not found'),
])
def test_setup_fails(run, site, caplog, setup, message) -> None:
    """Without the cruise, its folder, or the Dashboard_Data extra directory, the script exits 1."""
    setup(site)
    assert run() == 1
    assert message in caplog.text


def test_output_dir_missing(run, caplog, tmp_path) -> None:
    """An output folder that doesn't exist exits 1."""
    assert run('-o', str(tmp_path / 'missing'), output=False) == 1
    assert 'Output directory not found' in caplog.text


def test_cant_write(run, site, caplog) -> None:
    """If the overlay file can't be written, the script exits 1."""
    site.output.mkdir()
    assert run() == 1
    assert 'Failed to write overlay file' in caplog.text


def test_load_sources_needs_input(load_dist) -> None:
    """The sources loader needs a YAML string or file."""
    module = load_dist('bin/build_overlay_layers.py.dist', name='build_overlay_layers')
    with pytest.raises(RuntimeError, match='Either yaml_str or yaml_path must be provided'):
        module.load_geotiff_sources_from_yaml()


# --- Bugs ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="only the old dashboard file format is read (#602)")
def test_current_dashboard_format(run, site) -> None:
    """Dashboard files as the data dashboard writes them today (keyed by data type) are read."""
    _dashboard_file(site.dashboard / 'EM302' / 'a_bathy.json', 'a_bathy', 'http://ship/a.tif', keyed=True)
    assert run() == 0
    assert 'a_bathy' in [layer['name'] for layer in json.loads(site.output.read_text())]
