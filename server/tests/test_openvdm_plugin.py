"""Tests for the parser and plugin base classes in openvdm_plugin.py (#507).

Every parser and plugin builds on these: the stats and quality tests a parser
reports, the CSV/NMEA line reading, cropping, resampling and rounding, and the
plugin's file matching and JSON output.
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from server.lib import openvdm_plugin as op
from server.lib.condense_to_ranges import condense_to_ranges


# --- Helpers ------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [
    (datetime(2012, 4, 28, 12, 35, 0, 400000), '2012-04-28T12:35:00Z'),
    (datetime(2012, 4, 28, 12, 35, 0, 500000), '2012-04-28T12:35:01Z'),
    (datetime(2012, 4, 28, 23, 59, 59, 600000), '2012-04-29T00:00:00Z'),
    (datetime(2012, 4, 28, 8, 35, tzinfo=timezone(timedelta(hours=-4))), '2012-04-28T12:35:00Z'),
])
def test_format_iso8601(value, expected) -> None:
    """To the nearest second, in UTC; a naive time is taken to be UTC."""
    assert op.format_iso8601(value) == expected


@pytest.mark.parametrize('numbers, expected', [
    ([1, 2, 3, 5, 7, 8, 9], ['1-3', '5', '7-9']),
    ([9, 3, 1, 2], ['1-3', '9']),
    ([4], ['4']),
    ([], []),
])
def test_condense_to_ranges(numbers, expected) -> None:
    """Consecutive numbers become ranges, in order; single numbers stay single."""
    assert list(condense_to_ranges(numbers)) == expected


# --- Quality tests and stats --------------------------------------------------

@pytest.mark.parametrize('cls, result', [
    (op.OpenVDMParserQualityTestFailed, 'Failed'),
    (op.OpenVDMParserQualityTestWarning, 'Warning'),
    (op.OpenVDMParserQualityTestPassed, 'Passed'),
])
def test_quality_tests(cls, result) -> None:
    """Each result class records its result."""
    test = cls('DeltaT')
    assert test.get_test_data() == {'testName': 'DeltaT', 'results': result}
    assert json.loads(test.to_json()) == {'testName': 'DeltaT', 'results': result}


def test_quality_test_rejects_other_results() -> None:
    """Only Failed, Warning and Passed are results."""
    with pytest.raises(ValueError, match='Failed, Warning, Passed'):
        op.OpenVDMParserQualityTest('Rows', 'Maybe')


START, END = datetime(2026, 10, 22, 10), datetime(2026, 10, 22, 11)


@pytest.mark.parametrize('stat, expected', [
    (op.OpenVDMParserBoundsStat([1.5, 9], 'Depth Bounds', 'm'),
     {'statName': 'Depth Bounds', 'statType': 'bounds', 'statUnit': 'm', 'statValue': [1.5, 9]}),
    (op.OpenVDMParserGeoBoundsStat([45.1, -120, 44.9, -121]),
     {'statName': 'Geographic Bounds', 'statType': 'geoBounds', 'statUnit': 'ddeg',
      'statValue': [45.1, -120, 44.9, -121]}),
    (op.OpenVDMParserRowValidityStat([98, 2]),
     {'statName': 'Row Validity', 'statType': 'rowValidity', 'statUnit': '', 'statValue': [98, 2]}),
    (op.OpenVDMParserTimeBoundsStat([START, END]),
     {'statName': 'Temporal Bounds', 'statType': 'timeBounds', 'statUnit': 'seconds', 'statValue': [START, END]}),
    (op.OpenVDMParserTotalValueStat([12.5], 'Distance', 'km'),
     {'statName': 'Distance', 'statType': 'totalValue', 'statUnit': 'km', 'statValue': [12.5]}),
    (op.OpenVDMParserValueValidityStat([10, 0], 'DeltaT Validity'),
     {'statName': 'DeltaT Validity', 'statType': 'valueValidity', 'statUnit': '', 'statValue': [10, 0]}),
])
def test_stats(stat, expected) -> None:
    """Each stat class records its type, default name and unit, and value."""
    assert stat.get_stat_data() == expected


def test_stat_numpy_numbers_become_python_numbers() -> None:
    """pandas results (numpy scalars) are accepted and stored as Python numbers."""
    stat = op.OpenVDMParserBoundsStat([np.int64(1), np.float64(2.5)], 'B')
    assert stat.get_stat_data()['statValue'] == [1, 2.5]
    assert [type(v) for v in stat.get_stat_data()['statValue']] == [int, float]
    assert op.OpenVDMParserRowValidityStat([np.int32(3), np.int64(0)]).get_stat_data()['statValue'] == [3, 0]


@pytest.mark.parametrize('stat_type, value', [
    ('bounds', [1]), ('bounds', [1, 'x']), ('bounds', 'not a list'),
    ('geoBounds', [1, 2, 3]), ('geoBounds', [1, 2, 3, None]),
    ('rowValidity', [1]), ('rowValidity', [1, 2.5]),
    ('timeBounds', [START]), ('timeBounds', [START, '2026-10-22']),
    ('totalValue', [1, 2]), ('totalValue', ['1']),
    ('valueValidity', [1]), ('valueValidity', [1, 'x']),
    ('median', [1]),
])
def test_stat_rejects_wrong_values(stat_type, value) -> None:
    """Each stat type checks its value's shape; unknown types are rejected."""
    with pytest.raises(ValueError):
        op.OpenVDMParserStat('S', stat_type, value)


def test_stat_to_json_handles_datetimes() -> None:
    """Datetimes are written in OpenVDM's ISO 8601 form, with microseconds and Z."""
    stat = op.OpenVDMParserTimeBoundsStat([START, END])
    assert json.loads(stat.to_json())['statValue'] == ['2026-10-22T10:00:00.000000Z', '2026-10-22T11:00:00.000000Z']


# --- OpenVDMParser ------------------------------------------------------------

def test_parser_without_data() -> None:
    """A parser that produced nothing returns None and serializes to null."""
    parser = op.OpenVDMParser()
    assert parser.openvdm is None
    assert parser.get_plugin_data() is None and parser.get_results() is None and parser.to_json() == 'null'


def test_parser_collects_results() -> None:
    """Visualizer data, quality tests and stats are collected in plugin_data."""
    parser = op.OpenVDMParser()
    parser.add_visualization_data({'type': 'FeatureCollection', 'features': []})
    parser.add_quality_test_failed('Rows')
    parser.add_quality_test_warning('DeltaT')
    parser.add_quality_test_passed('Bounds')
    parser.add_bounds_stat([0, 10], 'Depth Bounds', 'm')
    parser.add_geobounds_stat([1, 2, 0, 1])
    parser.add_row_validity_stat([5, 0])
    parser.add_time_bounds_stat([START, END])
    parser.add_total_value_stat([3], 'Total')
    parser.add_value_validity_stat([4, 1], 'Depth Validity')

    data = parser.get_plugin_data()
    assert len(data['visualizerData']) == 1
    assert [t['results'] for t in data['qualityTests']] == ['Failed', 'Warning', 'Passed']
    assert [s['statType'] for s in data['stats']] == ['bounds', 'geoBounds', 'rowValidity', 'timeBounds',
                                                       'totalValue', 'valueValidity']


def test_parser_with_the_openvdm_api(monkeypatch, fake_ovdm) -> None:
    """use_openvdm_api connects to OpenVDM, for error messages."""
    monkeypatch.setattr(op, 'OpenVDM', lambda: fake_ovdm)
    assert op.OpenVDMParser(use_openvdm_api=True).openvdm is fake_ovdm


class NewStyleParser(op.OpenVDMCSVParser):  # pylint: disable=too-few-public-methods
    """A parser that overrides parse() and returns its data."""

    def parse(self, filepath):
        """Record the file as a stat and return the data."""
        self.add_total_value_stat([1], filepath)
        return self.get_plugin_data()


class LegacyParser(op.OpenVDMParser):  # pylint: disable=too-few-public-methods
    """A parser written before parse(): it implements process_file() and returns nothing."""

    def process_file(self, filepath):
        """Fill plugin_data, returning None as older parsers do."""
        self.add_row_validity_stat([1, 0])


class LegacyReturningParser(op.OpenVDMParser):  # pylint: disable=too-few-public-methods
    """A legacy parser that returns its data from process_file()."""

    def process_file(self, filepath):
        """Return the data directly."""
        return {'returned': filepath}


def test_parse_new_style() -> None:
    """A parser that overrides parse() is used directly, and process_file() reaches it."""
    parser = NewStyleParser([], [])
    assert parser.parse('a.txt')['stats'][0]['statName'] == 'a.txt'
    assert parser.process_file('b.txt')['stats'][-1]['statName'] == 'b.txt'


def test_parse_legacy() -> None:
    """parse() runs a legacy parser's process_file() and returns plugin_data, or what it returns."""
    assert LegacyParser().parse('a.txt')['stats'][0]['statType'] == 'rowValidity'
    assert LegacyReturningParser().parse('a.txt') == {'returned': 'a.txt'}


def test_parse_legacy_with_empty_plugin_data() -> None:
    """A legacy parser that leaves plugin_data falsy parses to None."""
    parser = LegacyParser()
    parser.process_file = lambda filepath: None
    parser.plugin_data = {}  # pylint: disable=attribute-defined-outside-init
    assert parser.parse('a.txt') is None


def test_parser_implementing_neither_method() -> None:
    """A parser with neither parse() nor process_file() says what's missing, not RecursionError (#533)."""
    with pytest.raises(NotImplementedError, match='must implement parse'):
        op.OpenVDMParser().parse('a.txt')
    with pytest.raises(NotImplementedError, match='OpenVDMParser must implement parse'):
        op.OpenVDMParser().process_file('a.txt')


def test_parse_calling_super() -> None:
    """A parser whose parse() calls super().parse() gets the NotImplementedError, not RecursionError (#533)."""
    class SuperParser(op.OpenVDMParser):
        def parse(self, filepath):
            return super().parse(filepath)
    with pytest.raises(NotImplementedError, match='SuperParser must implement parse'):
        SuperParser().parse('a.txt')


# --- NMEA checks --------------------------------------------------------------

GGA = '$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47'
GGA_NO_CHECKSUM = GGA[:GGA.index('*')]


@pytest.mark.parametrize('sentence, required, expected', [
    (GGA, False, True),
    ('  ' + GGA + '\r\n', False, True),
    (GGA[:-2] + '48', False, False),
    (GGA[:-2] + '4', False, False),
    (GGA[:-2] + '4G', False, False),
    (GGA_NO_CHECKSUM, False, True),
    (GGA_NO_CHECKSUM, True, False),
    ('!AIVDM,1,1,,A,13aG?P0P00PD;88MD5MTDww@2<0L,0*71', False, True),
])
def test_nmea_checksum_ok(sentence, required, expected) -> None:
    """The XOR of the characters between $ (or !) and *; optional unless required (#416, #418)."""
    assert op.OpenVDMCSVParser.nmea_checksum_ok(sentence, required=required) is expected


def test_check_nmea_sentence() -> None:
    """Checksum, field count (one or several allowed) and fixed field values."""
    fields = GGA.split(',')
    check = op.OpenVDMCSVParser.check_nmea_sentence
    check(GGA, fields, num_fields=15, field_values={10: 'M', 12: 'M', 3: ('N', 'S')})
    check(GGA, fields, num_fields=(14, 15))
    check(GGA)

    with pytest.raises(ValueError, match='bad checksum'):
        check(GGA[:-2] + '00')
    with pytest.raises(ValueError, match='bad or missing checksum'):
        check(GGA_NO_CHECKSUM, required=True)
    with pytest.raises(ValueError, match='15 fields, not 14'):
        check(GGA, fields, num_fields=14)
    with pytest.raises(ValueError, match="field 10 is 'M', not F"):
        check(GGA, fields, field_values={10: 'F'})
    with pytest.raises(ValueError, match="field 20 is None"):
        check(GGA, fields, field_values={20: 'X'})


# --- CSV parser: reading lines ------------------------------------------------

LINES = """\
# a comment
2026-10-22T10:00:00.000Z,$GPGGA,1,2
2026-10-22T10:00:01.000Z,$GPHDT,90.0,T

no timestamp here
2026-10-22T10:00:02.000Z,$PSXN,23,1,2
2026-10-22T10:00:03.000Z,$PSXN,24,1,2
2026-10-22T10:00:04.000Z,
"""


@pytest.fixture
def data_file(tmp_path):
    """A log file with comments, blank lines and lines without timestamps."""
    path = tmp_path / 'nmea.txt'
    path.write_text(LINES, encoding='utf-8')
    return str(path)


def _read(parser, path, **kwargs):
    """The (line number, timestamp, first field) of each line read."""
    return [(lineno, ts, fields[0]) for lineno, ts, _, fields in parser.read_lines_with_timestamps(path, **kwargs)]


def test_read_lines(data_file) -> None:
    """Comments, blank lines and lines without a timestamp or payload are skipped."""
    lines = _read(op.OpenVDMCSVParser([], []), data_file)
    assert [lineno for lineno, _, _ in lines] == [1, 2, 5, 6]
    assert lines[0] == (1, '2026-10-22T10:00:00.000Z', '$GPGGA')


def test_read_lines_errors(data_file) -> None:
    """Lines without a timestamp or payload are added to the errors list given, so the parser
    counts them as bad rows (#534, #554); comments and blank lines aren't."""
    errors = []
    lines = _read(op.OpenVDMCSVParser([], []), data_file, errors=errors)
    assert [lineno for lineno, _, _ in lines] == [1, 2, 5, 6]
    assert errors == [4, 7]


@pytest.mark.parametrize('nmea_filter, expected', [
    ('GGA', [1]),
    ('gga', [1]),
    ('PSXN,23', [5]),
    (lambda fields: fields[0] == '$GPHDT', [2]),
])
def test_read_lines_filtered(data_file, nmea_filter, expected) -> None:
    """A sentence name, a proprietary name and type, or a callable."""
    lines = _read(op.OpenVDMCSVParser([], []), data_file, nmea_filter=nmea_filter)
    assert [lineno for lineno, _, _ in lines] == expected


def test_read_lines_rejects_other_filters(data_file) -> None:
    """A filter must be a string or a callable."""
    with pytest.raises(TypeError):
        _read(op.OpenVDMCSVParser([], []), data_file, nmea_filter=23)


def test_read_lines_skips_the_header(tmp_path) -> None:
    """skip_header skips the first line."""
    path = tmp_path / 'with_header.txt'
    path.write_text('2026-10-22T10:00:00.000Z,header\n2026-10-22T10:00:01.000Z,data\n')
    assert [f for _, _, f in _read(op.OpenVDMCSVParser([], [], skip_header=True), str(path))] == ['data']


def test_read_lines_missing_file(tmp_path, caplog) -> None:
    """A file that can't be read yields nothing, and is logged."""
    assert _read(op.OpenVDMCSVParser([], []), str(tmp_path / 'missing.txt')) == []
    assert 'Failed to read file' in caplog.text


def test_extract_timestamp_and_payload() -> None:
    """The timestamp anywhere in the line; the separator after it is dropped."""
    parser = op.OpenVDMCSVParser([], [])
    assert parser.extract_timestamp_and_payload('ship 2026-10-22T10:00:00.5Z,$GPHDT,90') == (
        '2026-10-22T10:00:00.5Z', '$GPHDT,90')
    assert parser.extract_timestamp_and_payload('nothing') == (None, None)

    spaced = op.OpenVDMCSVParser([], [], timestamp_separator=' ')
    assert spaced.extract_timestamp_and_payload('2026-10-22T10:00:00.5Z  21.83 1487.9') == (
        '2026-10-22T10:00:00.5Z', '21.83 1487.9')


def test_extract_timestamp_with_a_capture_group() -> None:
    """A parser's timestamp pattern may capture the timestamp in a group."""
    parser = op.OpenVDMCSVParser([], [])
    parser.timestamp_re = op.re.compile(r'time=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d);')
    assert parser.extract_timestamp_and_payload('time=2026-10-22 10:00:00;12.5') == ('2026-10-22 10:00:00', '12.5')

    unseparated = op.OpenVDMCSVParser([], [])
    unseparated.timestamp_separator = ''
    assert unseparated.extract_timestamp_and_payload('2026-10-22T10:00:00.1Z,x')[1] == ',x'


# --- CSV parser: cropping, resampling, rounding --------------------------------

def _frame(times, **columns):
    """A DataFrame with UTC date_time and the given columns."""
    return pd.DataFrame({'date_time': pd.to_datetime(times, utc=True), **columns})


TIMES = ['2026-10-22T10:00:00Z', '2026-10-22T10:30:00Z', '2026-10-22T11:00:00Z', '2026-10-22T11:30:00Z']


@pytest.mark.parametrize('start, stop, expected', [
    (None, None, 4),
    (datetime(2026, 10, 22, 10, 30), None, 3),
    (None, datetime(2026, 10, 22, 11), 3),
    (datetime(2026, 10, 22, 10, 30), datetime(2026, 10, 22, 11), 2),
    (datetime(2026, 10, 22, 6, 30, tzinfo=timezone(timedelta(hours=-4))), None, 3),
])
def test_crop_data(start, stop, expected) -> None:
    """Inclusive; naive bounds are UTC, aware ones converted, against UTC timestamps."""
    parser = op.OpenVDMCSVParser([], [], start_dt=start, stop_dt=stop)
    assert len(parser.crop_data(_frame(TIMES, depth=[1, 2, 3, 4]))) == expected


def test_crop_data_on_the_index_and_naive_times() -> None:
    """The timestamps can be the index, and naive (taken as UTC)."""
    frame = pd.DataFrame({'depth': [1, 2, 3, 4]}, index=pd.to_datetime(TIMES).tz_localize(None))
    parser = op.OpenVDMCSVParser([], [], start_dt=datetime(2026, 10, 22, 11, tzinfo=timezone.utc))
    assert list(parser.crop_data(frame)['depth']) == [3, 4]


def test_crop_data_without_timestamps(caplog) -> None:
    """Data without timestamps cannot be cropped."""
    with pytest.raises(ValueError, match="no 'date_time'"):
        op.OpenVDMCSVParser([], [], start_dt=START).crop_data(pd.DataFrame({'depth': [1]}))
    assert 'Could not crop data' in caplog.text


def test_resample_data() -> None:
    """Averaged per interval, labelled by its end; timestamps back in a column."""
    frame = pd.DataFrame({'depth': [1.0, 3.0, 10.0]},
                         index=pd.to_datetime(['2026-10-22T10:00:10Z', '2026-10-22T10:00:50Z',
                                               '2026-10-22T10:01:30Z']))
    result = op.OpenVDMCSVParser.resample_data(frame)
    assert list(result.columns) == ['index', 'depth'] or list(result.columns)[1:] == ['depth']
    assert list(result['depth']) == [2.0, 10.0]


def test_resample_data_averages_angles() -> None:
    """359° and 1° average to 0°, not 180°, and columns keep their order (#410)."""
    frame = pd.DataFrame({'heading': [359.0, 1.0], 'speed': [4.0, 6.0], 'course': [90.0, 90.0]},
                         index=pd.to_datetime(['2026-10-22T10:00:10Z', '2026-10-22T10:00:20Z']))
    result = op.OpenVDMCSVParser.resample_data(frame, angle_cols=['heading', 'course', 'missing'])
    assert list(result.columns)[1:] == ['heading', 'speed', 'course']
    assert result['heading'].iloc[0] == pytest.approx(0.0) and result['speed'].iloc[0] == 5.0
    assert result['course'].iloc[0] == pytest.approx(90.0)


def test_resample_data_failure(caplog) -> None:
    """Data that can't be resampled (no time index) raises, after logging."""
    with pytest.raises(TypeError):
        op.OpenVDMCSVParser.resample_data(pd.DataFrame({'depth': [1.0]}))
    assert 'Could not resample data' in caplog.text


def test_round_data(caplog) -> None:
    """Per-column decimals; no precision leaves the data unchanged; a bad one raises."""
    frame = pd.DataFrame({'depth': [1.23456], 'temp': [20.98765]})
    assert op.OpenVDMCSVParser.round_data(frame, {'depth': 1, 'temp': 2}).iloc[0].tolist() == [1.2, 20.99]
    assert op.OpenVDMCSVParser.round_data(frame) is frame
    assert op.OpenVDMCSVParser.round_data(frame, {}) is frame
    with pytest.raises(Exception):
        op.OpenVDMCSVParser.round_data(frame, {'depth': 'one'})
    assert 'Could not round data' in caplog.text


# --- CSV parser: errors and output --------------------------------------------

def test_send_error_msg(fake_ovdm, monkeypatch, caplog) -> None:
    """Bad rows are condensed into ranges, logged, and posted when the API is used."""
    monkeypatch.setattr(op, 'OpenVDM', lambda: fake_ovdm)
    parser = op.OpenVDMCSVParser([], [], use_openvdm_api=True)
    parser.send_error_msg([7, 3, 4, 5], '/d/file.txt')
    message = 'Error(s) parsing datafile /d/file.txt on row(s): 3-5, 7'
    assert message in caplog.text
    fake_ovdm.send_msg.assert_called_once_with('Parsing Error', message)

    parser.send_error_msg([], '/d/file.txt')
    assert fake_ovdm.send_msg.call_count == 1


def test_send_error_msg_without_the_api(caplog) -> None:
    """Without the API, the message is only logged."""
    op.OpenVDMCSVParser([], []).send_error_msg([1], 'f')
    assert 'row(s): 1' in caplog.text


def test_sanitize_and_to_json() -> None:
    """numpy values and datetimes become JSON types."""
    parser = op.OpenVDMCSVParser([], [])
    assert parser._sanitize_for_json({'a': [np.int64(1), {'b': np.float32(0.5)}], 't': START, 's': 'x'}) == {  # pylint: disable=protected-access
        'a': [1, {'b': 0.5}], 't': START.isoformat(), 's': 'x'}
    parser.add_bounds_stat([np.float64(1.5), 2], 'B')
    assert json.loads(parser.to_json())['stats'][0]['statValue'] == [1.5, 2]
    assert op.OpenVDMCSVParser.add_cli_arguments(None) is None


class CliParser(op.OpenVDMCSVParser):
    """A parser with its own command-line option."""

    def __init__(self, scale=1, **kwargs):
        super().__init__([], [], **kwargs)
        self.scale = scale

    @classmethod
    def add_cli_arguments(cls, parser):
        """Add --scale."""
        parser.add_argument('--scale', type=int, default=1)

    @classmethod
    def _extract_custom_cli_kwargs(cls, args):
        """Pass --scale to the constructor."""
        return {'scale': args.scale}

    def process_file(self, filepath):
        """Report the options as stats."""
        self.add_total_value_stat([self.scale], 'scale')
        self.add_time_bounds_stat([self.start_dt, self.start_dt])


def test_run_cli(monkeypatch, capsys) -> None:
    """The standard options and a parser's own are passed in; the JSON is printed."""
    monkeypatch.setattr(sys, 'argv', ['parser', '-vv', '--startDT', '2026-10-22T10:00:00.000Z', '--scale', '3',
                                      'data.txt'])
    CliParser.run_cli()
    output = json.loads(capsys.readouterr().out)
    assert output['stats'][0]['statValue'] == [3]
    assert output['stats'][1]['statValue'][0] == '2026-10-22T10:00:00.000000Z'
    assert logging.getLogger().level == logging.DEBUG


def test_run_cli_failure(monkeypatch, caplog) -> None:
    """A parser that raises is logged and the error re-raised."""
    class Broken(op.OpenVDMCSVParser):  # pylint: disable=too-few-public-methods
        """A parser whose process_file() fails."""

        def __init__(self, **kwargs):
            super().__init__([], [], **kwargs)

        def process_file(self, filepath):
            """Fail."""
            raise OSError('unreadable')

    monkeypatch.setattr(sys, 'argv', ['parser', 'data.txt'])
    with pytest.raises(OSError):
        Broken.run_cli()
    assert 'unreadable' in caplog.text


# --- OpenVDMPlugin ------------------------------------------------------------

class Plugin(op.OpenVDMPlugin):  # pylint: disable=too-few-public-methods
    """A plugin returning scripted data."""

    def __init__(self, data):
        super().__init__([{'regex': '*/SCS/*GGA*.txt', 'data_type': 'gga'},
                          {'regex': '*/SCS/*.txt', 'data_type': 'raw'}])
        self.data = data

    def parse_file(self, filepath):
        """Return the scripted data."""
        return self.data


def test_plugin_data_types() -> None:
    """Every filter that matches the path, in order."""
    plugin = Plugin(None)
    assert plugin.get_data_types('/cruise/SCS/GGA_20261022.txt') == ['gga', 'raw']
    assert plugin.get_data_types('/cruise/SCS/notes.csv') == []


def test_plugin_json() -> None:
    """The parsed data as JSON, numpy values converted; nothing parsed is None."""
    assert json.loads(Plugin({'gga': {'stats': [np.int64(4)]}}).get_json_str('f')) == {'gga': {'stats': [4]}}
    assert Plugin(None).get_json_str('f') is None
    assert Plugin({}).get_json_str('f') is None


def test_plugin_json_from_legacy_plugin_data() -> None:
    """A legacy plugin that returns nothing but fills plugin_data."""
    plugin = Plugin(None)
    plugin.plugin_data = {'raw': {'stats': []}}  # pylint: disable=attribute-defined-outside-init
    assert json.loads(plugin.get_json_str('f')) == {'raw': {'stats': []}}


def test_plugin_base_needs_parse_file() -> None:
    """The base plugin has no parse_file()."""
    with pytest.raises(NotImplementedError):
        op.OpenVDMPlugin([]).parse_file('f')
