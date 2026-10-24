"""Tests for the GeoTIFF parsers in server/plugins/parsers (#513 part 3b).

- ``geotiff_parser`` reprojects the GeoTIFF and builds map tiles with GDAL's
  command-line tools, and reads its bounds with GDAL's Python bindings.
  Neither is in requirements.txt, so the tests give it a fake ``osgeo.gdal``
  and the ``fake_run`` fixture; one test runs real GDAL, skipped without it.
- ``geotiff_titiler_parser`` asks a TiTiler server for the bounds and band
  statistics; the tests give it a fake ``requests.get``.

Bugs the tests found are strict xfails at the end.
"""

import json
import os
import shutil
import sys
from types import ModuleType, SimpleNamespace

import pytest

from server.tests.helpers import parse_output, stat_value


def _real_gdal():
    """Whether GDAL's Python bindings and command-line tools work here."""
    try:
        from osgeo import gdal  # noqa: F401  pylint: disable=import-outside-toplevel,unused-import
    except ImportError:
        return False
    return all(shutil.which(tool) for tool in ('gdalwarp', 'gdal_translate', 'gdal2tiles.py'))


# --- GDAL -----------------------------------------------------------------------

class FakeDataset:  # pylint: disable=invalid-name
    """A GDAL dataset 200 by 100 pixels of 0.01 degrees, from 10 W, 20 N."""

    RasterXSize = 200
    RasterYSize = 100

    @staticmethod
    def GetGeoTransform():
        return (-10.0, 0.01, 0.0, 20.0, 0.0, -0.01)


@pytest.fixture
def gdal_parser(load_dist, monkeypatch):
    """The GDAL GeoTIFF parser module, with a fake ``osgeo.gdal``.

    ``gdal.Open`` returns a :class:`FakeDataset`, or ``None`` (as GDAL does
    for a file it can't open) once ``opened`` is set to ``None``; the paths it
    opened are in ``opened``.
    """
    opened = []
    gdal = ModuleType('osgeo.gdal')
    gdal.Open = lambda path: opened.append(path) or (FakeDataset() if gdal.dataset else None)
    gdal.dataset = True
    osgeo = ModuleType('osgeo')
    osgeo.gdal = gdal
    monkeypatch.setitem(sys.modules, 'osgeo', osgeo)
    monkeypatch.setitem(sys.modules, 'osgeo.gdal', gdal)
    module = load_dist('server/plugins/parsers/geotiff_parser.py.dist')
    module.opened, module.fake_gdal = opened, gdal
    return module


@pytest.fixture
def geotiff(tmp_path):
    """A GeoTIFF's path in a cruise's EM302 directory (an empty file: GDAL is faked)."""
    path = tmp_path / 'CruiseData' / 'TEST001' / 'EM302' / 'proc' / 'bathy_50m.tif'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'')
    return path


def test_gdal_output(gdal_parser, geotiff, fake_run, tmp_path) -> None:
    """The bounds come from the reprojected GeoTIFF; the tiles go in the output directory."""
    out = tmp_path / 'tiles'
    out.mkdir()
    data = parse_output(gdal_parser.GeoTIFFParser(output_dir=str(out)), geotiff)
    assert data == {
        'visualizerData': [{'label': 'bathy_50m', 'tileDirectory': str(out / 'bathy_50m'),
                            'mapBounds': '-10.0,19.0,-8.0,20.0'}],
        'qualityTests': [],
        'stats': [{'statName': 'Geographic Bounds', 'statType': 'geoBounds', 'statUnit': 'ddeg',
                   'statValue': [20.0, -8.0, 19.0, -10.0]}],
    }


def test_gdal_commands(gdal_parser, geotiff, fake_run, tmp_path) -> None:
    """gdalwarp reprojects to WGS84, gdal_translate makes a VRT, gdal2tiles.py the tiles; the
    temporary files are removed."""
    gdal_parser.GeoTIFFParser(output_dir=str(tmp_path)).process_file(str(geotiff))
    warp, translate, tiles = fake_run.commands()
    assert warp[:3] == ['gdalwarp', '-t_srs', '+proj=latlong +datum=WGS84'] and warp[3] == str(geotiff)
    reprojected = warp[4]
    assert reprojected.endswith('/bathy_50m_LL.tif') and gdal_parser.opened == [reprojected]
    assert translate[:3] == ['gdal_translate', '-of', 'vrt'] and translate[3] == reprojected
    assert tiles[:5] == ['gdal2tiles.py', '-v', '--profile=mercator', '--zoom=5-12', '--webviewer=none']
    assert tiles[5] == translate[4] and tiles[6] == str(tmp_path / 'bathy_50m')
    assert not os.path.exists(os.path.dirname(reprojected))


def test_gdal_tiles_beside_the_file(gdal_parser, geotiff, fake_run) -> None:
    """Without an output directory or the API, the tiles go beside the GeoTIFF."""
    parser = gdal_parser.GeoTIFFParser()
    data = parse_output(parser, geotiff)
    assert data['visualizerData'][0]['tileDirectory'] == str(geotiff.parent / 'bathy_50m')
    assert fake_run.commands('gdal2tiles.py')[0][-1] == str(geotiff.parent / 'bathy_50m')


@pytest.mark.parametrize('dest_dir, dashboard', [('OpenVDM/DashboardData', 'OpenVDM/DashboardData'),
                                                 ('/{cruiseID}_Dashboard/', 'TEST001_Dashboard')])
def test_gdal_tiles_in_dashboard_data(fake_ovdm, gdal_parser, geotiff, fake_run, monkeypatch, tmp_path,
                                      dest_dir, dashboard) -> None:
    """With the API, the tiles go in the cruise's Dashboard_Data directory (with its placeholders
    filled in, #635), under the file's collection system directory, and the tile directory is
    relative to CruiseData."""
    monkeypatch.setattr('server.lib.openvdm_plugin.OpenVDM', lambda: fake_ovdm)
    base = tmp_path / 'CruiseData'
    fake_ovdm.get_shipboard_data_warehouse_config.return_value = {'shipboardDataWarehouseBaseDir': str(base),
                                                                  'loweringDataBaseDir': 'Vehicle'}
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'destDir': dest_dir}
    fake_ovdm.get_cruise_id.return_value = 'TEST001'
    data = parse_output(gdal_parser.GeoTIFFParser(use_openvdm_api=True), geotiff)
    assert data['visualizerData'][0]['tileDirectory'] == f'TEST001/{dashboard}/EM302/proc/bathy_50m'
    assert fake_run.commands('gdal2tiles.py')[0][-1] == str(base / 'TEST001' / dashboard / 'EM302' / 'proc' / 'bathy_50m')
    fake_ovdm.get_required_extra_directory_by_name.assert_called_with('Dashboard_Data')


def test_gdal_output_dir_must_exist(gdal_parser, tmp_path) -> None:
    """An output directory that doesn't exist is an error."""
    with pytest.raises(FileNotFoundError, match='Output directory does not exist'):
        gdal_parser.GeoTIFFParser(output_dir=str(tmp_path / 'missing'))


@pytest.mark.skipif(not _real_gdal(), reason="needs GDAL's Python bindings and command-line tools")
def test_gdal_real(load_dist, tmp_path) -> None:
    """With real GDAL, a small RGBA GeoTIFF (like EM302's) gets its WGS84 bounds and a tile pyramid."""
    from osgeo import gdal, osr  # pylint: disable=import-outside-toplevel
    path = tmp_path / 'grid.tif'
    dataset = gdal.GetDriverByName('GTiff').Create(str(path), 40, 20, 4, gdal.GDT_Byte)
    dataset.SetGeoTransform((-10.0, 0.05, 0.0, 20.0, 0.0, -0.05))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    dataset.SetProjection(srs.ExportToWkt())
    for band, value in zip(range(1, 5), (30, 90, 200, 255)):
        dataset.GetRasterBand(band).Fill(value)
    dataset = None  # pylint: disable=unused-variable
    out = tmp_path / 'tiles'
    out.mkdir()
    module = load_dist('server/plugins/parsers/geotiff_parser.py.dist')
    data = parse_output(module.GeoTIFFParser(output_dir=str(out)), path)
    assert [round(value, 6) for value in stat_value(data, 'Geographic Bounds')] == [20.0, -8.0, 19.0, -10.0]
    assert any((out / 'grid' / '5').iterdir())


# --- TiTiler ----------------------------------------------------------------------

class FakeTiTiler:
    """A fake ``requests.get`` for TiTiler's ``/cog/info.geojson`` and ``/cog/statistics``.

    Attributes:
        info: The ``info.geojson`` response; ``None`` makes it fail.
        stats: The ``statistics`` response; ``None`` makes it fail.
        requests: Each request's URL and parameters.
    """

    def __init__(self):
        self.info = {'bbox': [-94.0123456789, 26.5, -93.25, 27.1234567],
                     'properties': {'colorinterp': ['gray'], 'nodata_type': 'Nodata'}}
        self.stats = {'b1': {'min': -1234.56789, 'max': -20.1, 'valid_pixels': 900.0, 'masked_pixels': 100.0,
                             'description': None}}
        self.requests = []

    def __call__(self, url, params=None, timeout=None):
        self.requests.append((url, params))
        body = self.info if url.endswith('/cog/info.geojson') else self.stats
        if body is None:
            raise OSError('connection refused')
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: json.loads(json.dumps(body)))


@pytest.fixture
def titiler(load_dist, monkeypatch):
    """The TiTiler GeoTIFF parser module, with a :class:`FakeTiTiler` as ``requests.get``."""
    module = load_dist('server/plugins/parsers/geotiff_titiler_parser.py.dist')
    server = FakeTiTiler()
    monkeypatch.setattr(module.requests, 'get', server)
    module.server = server
    return module


def _titiler_parse(module, **options):
    parser = module.GeoTIFFParser(cruisedata_path='/data/CruiseData', cruisedata_url='http://ship/CruiseData',
                                  titiler_url='http://ship/titiler', **options)
    parser.process_file('/data/CruiseData/TEST001/EM302/bathy_50m.tif')
    return json.loads(parser.to_json())


def test_titiler_output(titiler) -> None:
    """The bounds are TiTiler's, rounded; TiTiler reads the file from the CruiseData URL; an
    unnamed band with nodata gets bounds and validity."""
    assert _titiler_parse(titiler) == {
        'visualizerData': [{'label': 'bathy_50m', 'tileURL': 'http://ship/CruiseData/TEST001/EM302/bathy_50m.tif',
                            'mapBounds': '-94.012346,26.5,-93.25,27.123457'}],
        'qualityTests': [],
        'stats': [
            {'statName': 'Geographic Bounds', 'statType': 'geoBounds', 'statUnit': 'ddeg',
             'statValue': [27.123457, -93.25, 26.5, -94.012346]},
            {'statName': 'Band 1 Bounds', 'statType': 'bounds', 'statUnit': '', 'statValue': [-1234.568, -20.1]},
            {'statName': 'Band 1 Validity', 'statType': 'valueValidity', 'statUnit': '',
             'statValue': [900, 100]},
        ],
    }
    file_url = 'http://ship/CruiseData/TEST001/EM302/bathy_50m.tif'
    assert titiler.server.requests == [('http://ship/titiler/cog/info.geojson', {'url': file_url}),
                                       ('http://ship/titiler/cog/statistics', {'url': file_url})]


def test_titiler_named_band_without_nodata(titiler) -> None:
    """A band's description names its stats; without nodata there's no validity stat."""
    titiler.server.info['properties']['nodata_type'] = 'None'
    titiler.server.stats['b1']['description'] = 'Depth'
    names = [stat['statName'] for stat in _titiler_parse(titiler)['stats']]
    assert names == ['Geographic Bounds', 'Depth Bounds']


def test_titiler_imagery(titiler) -> None:
    """An RGB GeoTIFF's bands are display imagery: no band stats, and statistics isn't asked for."""
    titiler.server.info['properties']['colorinterp'] = ['red', 'green', 'blue', 'alpha']
    assert [stat['statName'] for stat in _titiler_parse(titiler)['stats']] == ['Geographic Bounds']
    assert len(titiler.server.requests) == 1


def test_titiler_imagery_band_skipped(titiler) -> None:
    """In a mixed GeoTIFF, the imagery bands are skipped and the data bands kept."""
    titiler.server.info['properties']['colorinterp'] = ['gray', 'alpha']
    titiler.server.stats['b2'] = dict(titiler.server.stats['b1'])
    names = [stat['statName'] for stat in _titiler_parse(titiler)['stats']]
    assert names == ['Geographic Bounds', 'Band 1 Bounds', 'Band 1 Validity']


def test_titiler_statistics_fail(titiler, caplog) -> None:
    """If the band statistics fail, the warning is logged and the bounds are still returned."""
    titiler.server.stats = None
    assert [stat['statName'] for stat in _titiler_parse(titiler)['stats']] == ['Geographic Bounds']
    assert 'Unable to retrieve band statistics' in caplog.text


def test_titiler_info_fails(titiler, caplog) -> None:
    """If TiTiler can't give the file's bounds, the error is logged and raised."""
    titiler.server.info = None
    with pytest.raises(OSError, match='connection refused'):
        _titiler_parse(titiler)
    assert 'Unable to retrieve metadata' in caplog.text


def test_titiler_defaults(titiler) -> None:
    """Without options or the API, the parser uses the default URLs and CruiseData path."""
    parser = titiler.GeoTIFFParser()
    assert (parser.titiler_url, parser.cruisedata_url, parser.cruisedata_path) == \
        ('http://localhost/titiler', 'http://localhost/CruiseData', '/data/CruiseData')


def test_titiler_urls_from_api(titiler, fake_ovdm, monkeypatch) -> None:
    """With the API, the CruiseData URL and path come from OpenVDM, unless given."""
    monkeypatch.setattr('server.lib.openvdm_plugin.OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_cruisedata_url.return_value = 'https://vessel.example/CruiseData'
    fake_ovdm.get_cruisedata_path.return_value = '/mnt/CruiseData'
    parser = titiler.GeoTIFFParser(use_openvdm_api=True)
    assert (parser.cruisedata_url, parser.cruisedata_path) == ('https://vessel.example/CruiseData', '/mnt/CruiseData')
    parser = titiler.GeoTIFFParser(use_openvdm_api=True, cruisedata_path='/data/CruiseData')
    assert parser.cruisedata_path == '/data/CruiseData'


def test_gdal_command_fails(gdal_parser, geotiff, fake_run, tmp_path, caplog) -> None:
    """If gdalwarp can't read the file, the parser fails with GDAL's error, not an AttributeError
    on None, and the temporary directory is removed (#573)."""
    fake_run.on('gdalwarp', returncode=1, stderr='ERROR 4: not recognized as a supported file format\n')
    gdal_parser.fake_gdal.dataset = False
    with pytest.raises(RuntimeError, match='gdalwarp failed \\(exit status 1\\): ERROR 4: not recognized'):
        gdal_parser.GeoTIFFParser(output_dir=str(tmp_path)).process_file(str(geotiff))
    assert 'not recognized as a supported file format' in caplog.text
    assert not os.path.exists(os.path.dirname(fake_run.commands('gdalwarp')[0][4]))


def test_gdal_cant_open_output(gdal_parser, geotiff, fake_run, tmp_path) -> None:
    """If GDAL can't open the reprojected GeoTIFF, the parser says so (#573)."""
    gdal_parser.fake_gdal.dataset = False
    with pytest.raises(RuntimeError, match='GDAL could not open reprojected GeoTIFF'):
        gdal_parser.GeoTIFFParser(output_dir=str(tmp_path)).process_file(str(geotiff))


def test_gdal_tiles_fail(gdal_parser, geotiff, fake_run, tmp_path) -> None:
    """If gdal2tiles.py fails (it exits 2 for a GeoTIFF that isn't 8-bit, saying so on stdout), the
    parser fails with that message instead of pointing the dashboard at tiles that aren't there (#573)."""
    fake_run.on('gdal2tiles.py', returncode=2, stdout='Generating Base Tiles:\nTo scale pixel values you can use: ...\n')
    parser = gdal_parser.GeoTIFFParser(output_dir=str(tmp_path))
    with pytest.raises(RuntimeError, match='gdal2tiles.py failed \\(exit status 2\\): To scale pixel values'):
        parser.process_file(str(geotiff))
    assert parser.get_plugin_data() is None
