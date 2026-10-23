"""Tests for the profile parsers in server/plugins/parsers (#513 part 3).

Each parser's output for a small cast (server/tests/data/parsers/profiles) is
compared with its saved expected output; ``pytest --update-expected`` saves
the new output after a change that's intended.

- CTD (``ctd_profile``): CTD002 from openvdm_sample_data, its header and 960
  scans (40 s) of the downcast, with a line that isn't hex, and its XMLCON.
  Other tests change copies of them: the XMLCON's settings, the header's
  position, lost or short scans.
- XBT: two casts from openvdm_sample_data. The tests need the xbt-edf-qc
  library, which requirements.txt doesn't install (see the parser), and are
  skipped without it.
- SV profile: a Valeport-style file written for the test, with two bad rows.

Bugs the tests found are strict xfails at the end.
"""

import argparse
import re
import sys
from datetime import datetime

import pytest

from server.tests.helpers import PARSER_DATA, parse_output, stat_value

PROFILES = PARSER_DATA / 'profiles'

# The CTD input's header ends on line 36; the line that isn't hex is line 137
CTD_SCANS = 960
CTD_BAD_LINE = 137


@pytest.fixture
def ctd(load_dist):
    """The CTD profile parser module."""
    return load_dist('server/plugins/parsers/ctd_profile_parser.py.dist')


@pytest.fixture
def xbt(load_dist):
    """The XBT parser module (skipped without xbt-edf-qc)."""
    pytest.importorskip('parse_xbt_edf')
    return load_dist('server/plugins/parsers/xbt_parser.py.dist')


@pytest.fixture
def svp(load_dist):
    """The SV profile parser module."""
    return load_dist('server/plugins/parsers/sv_profile_parser.py.dist')


def _tests(data):
    """The output's quality test results by name."""
    return {test['testName']: test['results'] for test in data['qualityTests']}


def _stat_names(data):
    return [stat['statName'] for stat in data['stats']]


# --- CTD ------------------------------------------------------------------------

def _ctd_copy(tmp_path, scans=None, header=None, xmlcon=None, name='cast'):
    """A copy of the CTD input in *tmp_path*, changed by the functions given.

    Args:
        scans: Takes and returns the data lines.
        header: Takes and returns the header lines.
        xmlcon: Takes and returns the XMLCON's text.
    """
    lines = (PROFILES / 'ctd002.hex').read_text(encoding='latin-1').splitlines()
    end = lines.index('*END*') + 1
    head, data = lines[:end], [line for line in lines[end:] if line != 'NOT A HEX SCAN LINE']
    head, data = (header or list)(head), (scans or list)(data)
    (tmp_path / f'{name}.hex').write_text('\n'.join(head + data) + '\n', encoding='latin-1')
    text = (PROFILES / 'ctd002.XMLCON').read_text(encoding='latin-1')
    (tmp_path / f'{name}.xmlcon').write_text((xmlcon or str)(text), encoding='latin-1')
    return tmp_path / f'{name}.hex'


def _set_xml(tag, value):
    """An *xmlcon* function that sets ``<tag>`` to *value*."""
    return lambda text: re.sub(f'<{tag}>[^<]*</{tag}>', f'<{tag}>{value}</{tag}>', text)


def _no_header_position(head):
    return [line for line in head if 'NMEA Latitude' not in line and 'NMEA Longitude' not in line]


def test_ctd_output(ctd, expected, monkeypatch) -> None:
    """The CTD cast's output is the expected output."""
    monkeypatch.chdir(PARSER_DATA)
    expected('profiles_ctd', parse_output(ctd.CTDProfileParser(), 'profiles/ctd002.hex'))


def test_ctd_position_output(ctd, expected, monkeypatch) -> None:
    """The CTD cast's map point is the expected output."""
    monkeypatch.chdir(PARSER_DATA)
    expected('profiles_ctd_position', parse_output(ctd.CTDPositionParser(), 'profiles/ctd002.hex'))


def test_ctd_bad_rows(ctd, caplog) -> None:
    """The line that isn't hex is a bad row, reported by line number (one-based)."""
    data = parse_output(ctd.CTDProfileParser(), PROFILES / 'ctd002.hex')
    assert stat_value(data, 'Row Validity') == [CTD_SCANS, 1]
    assert f"on row(s): {CTD_BAD_LINE}" in caplog.text


def test_ctd_wrong_length_scan(ctd, tmp_path) -> None:
    """A scan longer than the header's bytes per scan is a bad row."""
    path = _ctd_copy(tmp_path, scans=lambda data: data[:50] + [data[50] + '00'] + data[51:])
    assert stat_value(parse_output(ctd.CTDProfileParser(), path), 'Row Validity') == [CTD_SCANS - 1, 1]


def test_ctd_no_xmlcon(ctd, tmp_path) -> None:
    """A cast without its XMLCON can't be parsed."""
    path = _ctd_copy(tmp_path)
    (tmp_path / 'cast.xmlcon').unlink()
    with pytest.raises(FileNotFoundError, match='No calibration file'):
        ctd.CTDProfileParser().parse(str(path))


def test_ctd_xmlcon_not_xml(ctd, tmp_path) -> None:
    """An XMLCON that isn't XML is an error."""
    path = _ctd_copy(tmp_path, xmlcon=lambda text: text[:500])
    with pytest.raises(ValueError, match="isn't valid XML"):
        ctd.CTDProfileParser().parse(str(path))


def test_ctd_xmlcon_missing_coefficient(ctd, tmp_path) -> None:
    """An XMLCON without a calibration coefficient the parser needs is an error naming it."""
    path = _ctd_copy(tmp_path, xmlcon=lambda text: re.sub(r'<AD590M>[^<]*</AD590M>', '', text))
    with pytest.raises(ValueError, match='missing coefficients: P_AD590M'):
        ctd.CTDProfileParser().parse(str(path))


def test_ctd_no_start_time(ctd, tmp_path) -> None:
    """A header without System UTC or System UpLoad Time is an error."""
    path = _ctd_copy(tmp_path, header=lambda head: [line for line in head if 'System U' not in line])
    with pytest.raises(ValueError, match='No start time'):
        ctd.CTDProfileParser().parse(str(path))


def test_ctd_no_scans_averaged(ctd, tmp_path, caplog) -> None:
    """Without ScansToAverage in the XMLCON or the header, a line is taken to be one scan (24 Hz)."""
    path = _ctd_copy(tmp_path, xmlcon=lambda text: re.sub(r'<ScansToAverage>[^<]*</ScansToAverage>', '', text),
                     header=lambda head: [line for line in head if 'Scans Averaged' not in line])
    data = parse_output(ctd.CTDProfileParser(), path)
    assert 'assuming 1' in caplog.text
    assert stat_value(data, 'Temporal Bounds') == ['2012-04-28T12:35:00+00:00', '2012-04-28T12:35:39.958333+00:00']


def test_ctd_without_scan_positions(ctd, tmp_path) -> None:
    """Without the deck unit appending positions, that test fails; depth uses the header's position."""
    path = _ctd_copy(tmp_path, xmlcon=_set_xml('NmeaPositionDataAdded', 0))
    data = parse_output(ctd.CTDProfileParser(), path)
    assert _tests(data) == {'Rows': 'Passed', 'XMLCON NMEA Position': 'Failed', 'HEX Header Position': 'Passed',
                            'HEX Lost Scans': 'Passed', 'Ranges': 'Passed'}
    assert 'Depth' in _stat_names(data)
    assert stat_value(data, 'Geographic Bounds') == [27.56283, -93.77267, 27.56283, -93.77267]


def test_ctd_without_header_position(ctd, tmp_path) -> None:
    """Without the header's position, that test fails; the scans' positions are used."""
    data = parse_output(ctd.CTDProfileParser(), _ctd_copy(tmp_path, header=_no_header_position))
    assert _tests(data)['HEX Header Position'] == 'Failed'
    assert _tests(data)['HEX Scan Positions'] == 'Passed'
    assert 'Depth' in _stat_names(data)


@pytest.mark.parametrize('latitude, depth', [(None, False), (27.5, True)])
def test_ctd_without_any_position(ctd, tmp_path, caplog, latitude, depth) -> None:
    """With no position at all, depth needs the latitude option; there's no Depth series without it."""
    path = _ctd_copy(tmp_path, header=_no_header_position, xmlcon=_set_xml('NmeaPositionDataAdded', 0))
    data = parse_output(ctd.CTDProfileParser(latitude=latitude), path)
    assert ('Depth' in _stat_names(data)) is depth
    assert ('Depth' in [viz['label'] for viz in data['visualizerData']]) is depth
    assert 'Geographic Bounds' not in _stat_names(data)
    assert ('no depth' in caplog.text) is not depth


def test_ctd_scans_without_a_fix(ctd, tmp_path) -> None:
    """Scans whose position bytes are zero (no fix) make HEX Scan Positions a warning."""
    def no_fix(data):
        offset = 2 * 30  # the position's offset in these scans
        return [line[:offset] + '0' * 14 + line[offset + 14:] if n % 10 == 0 else line
                for n, line in enumerate(data)]
    data = parse_output(ctd.CTDProfileParser(), _ctd_copy(tmp_path, scans=no_fix))
    assert _tests(data)['HEX Scan Positions'] == 'Warning'


def test_ctd_scans_too_short_for_position(ctd, tmp_path, caplog) -> None:
    """Scans too short for the position the XMLCON describes fail HEX Scan Positions."""
    path = _ctd_copy(tmp_path, scans=lambda data: [line[:54] + line[-6:] for line in data],
                     header=lambda head: [line.replace('Bytes Per Scan = 40', 'Bytes Per Scan = 30')
                                          for line in head])
    data = parse_output(ctd.CTDProfileParser(), path)
    assert _tests(data)['HEX Scan Positions'] == 'Failed'
    assert 'too short for the NMEA position' in caplog.text


@pytest.mark.parametrize('scans, result', [
    (lambda data: data[:500] + data[501:], 'Failed'),    # one lost: more than 0.1%
    (lambda data: data[:500] + [data[500]] + data[500:], 'Passed'),  # a repeated scan isn't lost
], ids=['lost', 'repeated'])
def test_ctd_lost_scans(ctd, tmp_path, caplog, scans, result) -> None:
    """A gap in the scan count is lost scans; HEX Lost Scans fails above 0.1%."""
    data = parse_output(ctd.CTDProfileParser(), _ctd_copy(tmp_path, scans=scans))
    assert _tests(data)['HEX Lost Scans'] == result
    if result == 'Failed':
        assert f'1 of {CTD_SCANS} scans lost' in caplog.text


def test_ctd_ranges_option(ctd, caplog) -> None:
    """The ranges option replaces a variable's plausible range for the Ranges test."""
    data = parse_output(ctd.CTDProfileParser(ranges={'temperature': [30, 35]}), PROFILES / 'ctd002.hex')
    assert _tests(data)['Ranges'] == 'Failed'
    assert stat_value(data, 'Temperature Validity')[0] == 0
    assert 'temperature values outside 30 to 35' in caplog.text


@pytest.mark.parametrize('ranges, message', [
    ({'oxygen': [0, 10]}, "Unknown range 'oxygen'"),
    ({'salinity': [0]}, 'must be two numbers'),
    ({'salinity': ['a', 'b']}, 'must be two numbers'),
    ({'salinity': [42, 0]}, 'must be min then max'),
])
def test_ctd_bad_ranges(ctd, ranges, message) -> None:
    """A range for an unknown variable, or that isn't min then max, is an error."""
    with pytest.raises(ValueError, match=message):
        ctd.CTDProfileParser(ranges=ranges)


def test_ctd_crop(ctd) -> None:
    """start_dt and stop_dt crop the cast to the window, inclusive."""
    parser = ctd.CTDProfileParser(start_dt='2012-04-28T12:35:10Z', stop_dt='2012-04-28T12:35:20Z')
    data = parse_output(parser, PROFILES / 'ctd002.hex')
    assert stat_value(data, 'Temporal Bounds') == ['2012-04-28T12:35:10+00:00', '2012-04-28T12:35:20+00:00']


def test_ctd_crop_to_nothing(ctd, caplog) -> None:
    """A window with none of the cast in it gives no output."""
    assert parse_output(ctd.CTDProfileParser(start_dt='2030-01-01T00:00:00Z'), PROFILES / 'ctd002.hex') is None
    assert 'empty after cropping' in caplog.text


def test_ctd_no_scans(ctd, tmp_path, caplog) -> None:
    """A cast with only a header has no output."""
    assert parse_output(ctd.CTDProfileParser(), _ctd_copy(tmp_path, scans=lambda data: [])) is None
    assert 'No valid data' in caplog.text


def test_ctd_plot_without_matplotlib(ctd, tmp_path, monkeypatch, caplog) -> None:
    """Without matplotlib, plot_dir logs a warning and the cast is still parsed."""
    monkeypatch.setitem(sys.modules, 'matplotlib', None)
    data = parse_output(ctd.CTDProfileParser(plot_dir=str(tmp_path)), PROFILES / 'ctd002.hex')
    assert data is not None
    assert "matplotlib isn't installed" in caplog.text
    assert not list(tmp_path.iterdir())


def test_ctd_plot(ctd, tmp_path) -> None:
    """plot_dir saves a PNG plot of the cast, named after it."""
    pytest.importorskip('matplotlib')
    parse_output(ctd.CTDProfileParser(plot_dir=str(tmp_path)), PROFILES / 'ctd002.hex')
    assert (tmp_path / 'ctd002.png').read_bytes()[:4] == b'\x89PNG'


@pytest.mark.parametrize('cli_args, kwargs', [
    ([], {'plot_dir': None, 'latitude': None, 'ranges': {}}),
    (['--plotDir', '/tmp/plots', '--latitude', '27.5', '--salinityRange', '0', '42'],
     {'plot_dir': '/tmp/plots', 'latitude': 27.5, 'ranges': {'salinity': [0.0, 42.0]}}),
])
def test_ctd_cli_options(ctd, cli_args, kwargs) -> None:
    """--plotDir, --latitude and the range options become the parser's options."""
    parser = argparse.ArgumentParser()
    ctd.CTDProfileParser.add_cli_arguments(parser)
    assert ctd.CTDProfileParser._extract_custom_cli_kwargs(parser.parse_args(cli_args)) == kwargs


def test_ctd_position_parser_has_no_options(ctd) -> None:
    """The position parser takes none of the profile parser's options."""
    parser = argparse.ArgumentParser()
    ctd.CTDPositionParser.add_cli_arguments(parser)
    assert ctd.CTDPositionParser._extract_custom_cli_kwargs(parser.parse_args([])) == {}


def test_ctd_position_without_header_position(ctd, tmp_path, caplog) -> None:
    """The position parser has no output for a cast without the header's position."""
    caplog.set_level('INFO')
    assert parse_output(ctd.CTDPositionParser(), _ctd_copy(tmp_path, header=_no_header_position)) is None
    assert 'No NMEA position in the header' in caplog.text


@pytest.mark.parametrize('window', [{'start_dt': '2012-04-28T12:36:00'}, {'stop_dt': '2012-04-28T12:34:00'}])
def test_ctd_position_outside_window(ctd, window) -> None:
    """The position parser has no output for a cast outside start_dt/stop_dt."""
    window = {key: datetime.fromisoformat(value) for key, value in window.items()}
    assert parse_output(ctd.CTDPositionParser(**window), PROFILES / 'ctd002.hex') is None


# --- XBT ------------------------------------------------------------------------

def _xbt_copy(tmp_path, change, name='cast001.EDF'):
    path = tmp_path / name
    path.write_text(change((PROFILES / 'xbt001.EDF').read_text(encoding='cp1252')), encoding='cp1252')
    return path


@pytest.mark.parametrize('cast', ['xbt001', 'xbt002'])
def test_xbt_output(xbt, expected, cast) -> None:
    """Each XBT cast's output is the expected output (xbt001's spikes make a warning)."""
    expected(f'profiles_{cast}', parse_output(xbt.XBTParser(), PROFILES / f'{cast}.EDF'))


def test_xbt_position_output(xbt, expected) -> None:
    """The XBT cast's map point is the expected output."""
    expected('profiles_xbt001_position', parse_output(xbt.XBTPositionParser(), PROFILES / 'xbt001.EDF'))


@pytest.mark.parametrize('parser', ['XBTParser', 'XBTPositionParser'])
def test_xbt_test_probe(xbt, tmp_path, caplog, parser) -> None:
    """A test probe cast (the recorder's self-test) has no output."""
    caplog.set_level('INFO')
    path = _xbt_copy(tmp_path, lambda text: text.replace('Serial Number    :  ', 'Serial Number    :  TestProbe'))
    assert parse_output(getattr(xbt, parser)(), path) is None
    assert 'Skipping test probe cast' in caplog.text


@pytest.mark.parametrize('parser', ['XBTParser', 'XBTPositionParser'])
@pytest.mark.parametrize('window', [{'start_dt': '2013-06-12T00:00:00'}, {'stop_dt': '2013-06-11T20:00:00'}])
def test_xbt_outside_window(xbt, parser, window) -> None:
    """A cast outside start_dt/stop_dt has no output."""
    window = {key: datetime.fromisoformat(value) for key, value in window.items()}
    assert parse_output(getattr(xbt, parser)(**window), PROFILES / 'xbt001.EDF') is None


def test_xbt_position_on_land(xbt, tmp_path) -> None:
    """A cast positioned on land fails the Position test."""
    path = _xbt_copy(tmp_path, lambda text: text.replace('36 22.110N', '39 00.000N').replace('74 38.110W', '100 00.000W'))
    assert _tests(parse_output(xbt.XBTParser(), path))['Position'] == 'Failed'


def test_xbt_not_an_edf(xbt, tmp_path) -> None:
    """A file that isn't an EDF export is an error."""
    path = tmp_path / 'cast.EDF'
    path.write_text('not an EDF file\n')
    with pytest.raises(xbt.EDFParseError):
        xbt.XBTParser().parse(str(path))


# --- SV profile -----------------------------------------------------------------

def test_svp_output(svp, expected) -> None:
    """The SV profile's output is the expected output: its two bad rows are counted."""
    data = parse_output(svp.SVProfileParser(), PROFILES / 'svp.txt')
    assert stat_value(data, 'Row Validity') == [40, 2]
    expected('profiles_svp', data)


@pytest.mark.parametrize('text', ['', 'Model Name : MIDAS SVX2 6000\nno data section\n'],
                         ids=['empty', 'no-data-section'])
def test_svp_no_data(svp, tmp_path, caplog, text) -> None:
    """A file without a [Data] section, or empty, has no output."""
    path = tmp_path / 'svp.txt'
    path.write_text(text)
    assert parse_output(svp.SVProfileParser(), path) is None
    assert 'empty' in caplog.text


def test_svp_missing_file(svp, tmp_path, caplog) -> None:
    """A file that can't be read has no output; the error is logged."""
    assert parse_output(svp.SVProfileParser(), tmp_path / 'missing.txt') is None
    assert 'Problem accessing input file' in caplog.text


# --- Bugs -----------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="a short scan's last characters are read as its scan count (#571)")
def test_ctd_short_scan_isnt_lost_scans(ctd, tmp_path) -> None:
    """A short (corrupt) scan is a bad row, not hundreds of lost scans."""
    path = _ctd_copy(tmp_path, scans=lambda data: data[:100] + [data[100][:30]] + data[100:])
    data = parse_output(ctd.CTDProfileParser(), path)
    assert stat_value(data, 'Row Validity') == [CTD_SCANS, 1]
    assert _tests(data)['HEX Lost Scans'] == 'Passed'
