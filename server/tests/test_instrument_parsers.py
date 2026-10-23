"""Tests for the instrument parsers in server/plugins/parsers (#513 part 2).

Each parser's output for a small input file (server/tests/data/parsers/instruments)
is compared with its saved expected output: the stats, Validity and DeltaT
included, the quality tests and the charted data. After a change to a
parser's output that's intended, ``pytest --update-expected`` saves the new
output, so the change shows in the diff.

The Met, SSV, TSG45, TWind, Paro, CTD, O2, Sprint and compensator pressure
inputs are lines from openvdm_sample_data, about one every 5 s, with a gap.
The others are written for the test: a line every 5 s, a 30 s gap and, for
some, a value out of range. Each input has these rows added: a value that
isn't a number (a bad row), a line cut short (a bad row only for parsers
that need every field) and a line without a timestamp (not counted, #554).
Bugs the tests found are strict xfails at the end.
"""

import argparse
import logging

import pandas as pd
import pytest

from server.tests.helpers import PARSER_DATA, parse_output, stat_value

# Each parser's .py.dist (server/plugins/parsers/<name>_parser.py.dist) and class
PARSERS = {
    'comp_pres': 'CompPresParser',
    'ctd': 'CTDParser',
    'flowrate': 'FlowrateParser',
    'flowrate_krohne': 'OPTIFLUXParser',
    'fluoro': 'FluoroParser',
    'fluoro_triplet': 'ECOTripletParser',
    'met': 'MetParser',
    'metpakpro': 'MetPakProParser',
    'o2': 'O2Parser',
    'par': 'PARParser',
    'par2': 'PAR2Parser',
    'paro': 'ParoParser',
    'ph': 'PHParser',
    'sbe38': 'SBE38Parser',
    'sprint': 'SprintParser',
    'ssv': 'SSVParser',
    'ssv_valeport': 'SSVValeportParser',
    'tsg21': 'SBE21TSGParser',
    'tsg45': 'SBE45TSGParser',
    'twind': 'TWindParser',
    'wind_gill_wo75': 'GillWO75Parser',
}

# The options each input file needs: the TSG45 sample has the column names
# in each row (t1= ...), as the OpenRVDAS plugin's TSG filter says
OPTIONS = {'tsg45': {'col_names': True}}

# Each input file's bad rows by line number: the value that isn't a number
# (6) and, unless the fields the parser reads are all before the cut or it
# takes missing fields as no value, the line cut short (12)
BAD_ROWS = {name: '6' for name in PARSERS}
BAD_ROWS.update({name: '6, 12' for name in ('flowrate_krohne', 'fluoro', 'fluoro_triplet', 'met', 'par2', 'ph',
                                             'ssv_valeport', 'tsg21', 'tsg45', 'wind_gill_wo75')})


@pytest.fixture
def make_parser(load_dist):
    """Return a function that makes a parser by name, with *options*."""
    def make(name, **options):
        module = load_dist(f'server/plugins/parsers/{name}_parser.py.dist')
        return getattr(module, PARSERS[name])(**{**OPTIONS.get(name, {}), **options})
    return make


def _input(name):
    return PARSER_DATA / 'instruments' / f'{name}.txt'


def _lines(name):
    """The input file's timestamped lines."""
    return [line for line in _input(name).read_text().splitlines() if line[:4].isdigit()]


def _first_good(name):
    """The input file's first line's payload (a good row)."""
    return _lines(name)[0].split(',', 1)[1]


def _write(tmp_path, *payloads):
    """A log file of *payloads*, timestamped 5 s apart."""
    path = tmp_path / 'log.txt'
    path.write_text(''.join(f'2026-10-01T00:00:{5 * n:02d}.000000Z,{payload}\n'
                            for n, payload in enumerate(payloads)))
    return path


# --- Output -------------------------------------------------------------------

@pytest.mark.parametrize('case, name, options', [(name, name, {}) for name in PARSERS] + [
    ('tsg45_sbe38', 'tsg45', {'sbe38': True}),
], ids=lambda value: value if isinstance(value, str) else '')
def test_output(make_parser, expected, monkeypatch, case, name, options) -> None:
    """Each parser's output for its input file is the expected output."""
    monkeypatch.chdir(PARSER_DATA)  # the Sprint track is named after the file
    expected(f'instruments_{case}', parse_output(make_parser(name, **options), f'instruments/{name}.txt'))


@pytest.mark.parametrize('name', PARSERS)
def test_bad_rows(make_parser, caplog, name) -> None:
    """The input file's bad rows are counted and reported by line number (zero-based)."""
    caplog.set_level(logging.ERROR)
    bad = BAD_ROWS[name]
    data = parse_output(make_parser(name), _input(name))
    assert stat_value(data, 'Row Validity')[1] == len(bad.split(', '))
    assert f'Error(s) parsing datafile {_input(name)} on row(s): {bad}' in caplog.text


# --- Bad input ----------------------------------------------------------------

@pytest.mark.parametrize('name', PARSERS)
def test_not_a_number(make_parser, tmp_path, name) -> None:
    """A value that isn't a number is a bad row; the good rows around it are read."""
    good = _first_good(name)
    bad = _input(name).read_text().splitlines()[6].split(',', 1)[1]
    data = parse_output(make_parser(name), _write(tmp_path, good, bad, good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('name, line', [
    ('fluoro', '10/01/26\t00:00:00\t695\t149'),
    ('tsg21', '5.32000 24.5000 35.4800 24.3500 0.2100'),
    ('ssv_valeport', '24.500 1533.400 7'),
    ('ph', '10/01/2026,00:00:00,274.000,24.500'),
])
def test_wrong_number_of_fields(make_parser, tmp_path, name, line) -> None:
    """A line with too few or too many fields is a bad row, for parsers that need them all."""
    good = _first_good(name)
    assert stat_value(parse_output(make_parser(name), _write(tmp_path, good, line, good)), 'Row Validity') == [2, 1]


def test_sprint_skips_no_position(make_parser, tmp_path) -> None:
    """A Sprint line with position 0, 0 (no fix) is skipped: neither read nor a bad row."""
    good = _first_good('sprint')
    no_fix = '$SPRINT,0.697632,-0.43396,0.318604,0,0.00000000,0.00000000,0,0,0,0,0,0,0,0'
    data = parse_output(make_parser('sprint'), _write(tmp_path, good, no_fix, good))
    assert stat_value(data, 'Row Validity') == [2, 0]


def test_tsg45_without_column_names(make_parser, tmp_path) -> None:
    """Without col_names, TSG45 reads the values on their own."""
    data = parse_output(make_parser('tsg45', col_names=False),
                        _write(tmp_path, '24.4972, 5.31944, 35.4860, 1533.356', '24.4971, 5.31947, 35.4862, 1533.356'))
    assert stat_value(data, 'Row Validity') == [2, 0]


@pytest.mark.parametrize('cli_args, kwargs', [
    ([], {'sbe38': False, 'col_names': False}),
    (['--sbe38', '--col_names'], {'sbe38': True, 'col_names': True}),
])
def test_tsg45_cli_options(load_dist, cli_args, kwargs) -> None:
    """--sbe38 and --col_names become the parser's options."""
    cls = load_dist('server/plugins/parsers/tsg45_parser.py.dist').SBE45TSGParser
    parser = argparse.ArgumentParser()
    cls.add_cli_arguments(parser)
    assert cls._extract_custom_cli_kwargs(parser.parse_args(cli_args)) == kwargs


@pytest.mark.parametrize('name', PARSERS)
def test_empty_file(make_parser, tmp_path, name) -> None:
    """An empty file has no output."""
    path = tmp_path / 'log.txt'
    path.write_text('')
    assert parse_output(make_parser(name), path) is None


@pytest.mark.parametrize('name', PARSERS)
def test_no_good_rows(make_parser, tmp_path, name) -> None:
    """A file with only bad rows has no output."""
    bad = _input(name).read_text().splitlines()[6].split(',', 1)[1]
    assert parse_output(make_parser(name), _write(tmp_path, bad, bad)) is None


@pytest.mark.filterwarnings('ignore:Could not infer format')
@pytest.mark.parametrize('name', PARSERS)
def test_unreadable_timestamps(make_parser, tmp_path, name) -> None:
    """A file whose timestamps aren't dates has no output."""
    good = _first_good(name)
    path = tmp_path / 'log.txt'
    path.write_text(f'2026-13-45T00:00:00.000Z,{good}\n2026-13-45T00:00:05.000Z,{good}\n')
    assert parse_output(make_parser(name), path) is None


@pytest.mark.parametrize('name', PARSERS)
def test_missing_file(make_parser, tmp_path, caplog, name) -> None:
    """A file that can't be read has no output; the error is logged."""
    assert parse_output(make_parser(name), tmp_path / 'missing.txt') is None
    assert 'Failed to read file' in caplog.text


@pytest.mark.parametrize('name', PARSERS)
def test_crop(make_parser, name) -> None:
    """start_dt and stop_dt crop the data to the window, inclusive."""
    first = pd.Timestamp(_lines(name)[0].split(',', 1)[0])
    start, stop = first + pd.Timedelta('60s'), first + pd.Timedelta('120s')
    data = parse_output(make_parser(name, start_dt=start.to_pydatetime(), stop_dt=stop.to_pydatetime()),
                        _input(name))
    bounds = [pd.Timestamp(bound) for bound in stat_value(data, 'Temporal Bounds')]
    bounds = [bound.tz_localize('UTC') if bound.tzinfo is None else bound for bound in bounds]
    assert start <= bounds[0] <= bounds[1] <= stop
    assert sum(stat_value(data, 'Row Validity')) < len(_lines(name))


@pytest.mark.parametrize('name', PARSERS)
def test_crop_to_nothing(make_parser, caplog, name) -> None:
    """A window with no data in it gives no output."""
    assert parse_output(make_parser(name, start_dt='2030-01-01T00:00:00Z'), _input(name)) is None
    assert 'empty after cropping' in caplog.text


# --- Bugs -----------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="Met doesn't check the sentence's checksum (#563)")
def test_met_checksum(make_parser, tmp_path) -> None:
    """A $WIM01 sentence whose checksum doesn't match (spliced or corrupt) is a bad row."""
    good = _first_good('met')
    spliced = good.replace(',24.41,', ',2.441,')  # the checksum no longer matches
    data = parse_output(make_parser('met'), _write(tmp_path, good, spliced, good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.xfail(strict=True, reason="Met's MAX_DELTA_T is its logging interval (#564)")
def test_met_delta_t_jitter(make_parser, tmp_path) -> None:
    """MET sentences every 10 s, a few ms late, pass the DeltaT test (the sample data's MET)."""
    good = _first_good('met')
    path = tmp_path / 'log.txt'
    path.write_text(''.join(f'2026-10-01T00:{10 * n // 60:02d}:{10 * n % 60:02d}.{15 * (n % 2):03d}Z,{good}\n'
                            for n in range(12)))
    data = parse_output(make_parser('met'), path)
    assert {test['testName']: test['results'] for test in data['qualityTests']}['DeltaT'] == 'Passed'


@pytest.mark.xfail(strict=True, reason='a position without its longitude reaches geopy (#565)')
def test_sprint_latitude_without_longitude(make_parser, tmp_path) -> None:
    """A Sprint line cut short after the latitude is a bad row, and the file is parsed."""
    good = _first_good('sprint')
    cut = ','.join(good.split(',')[:6])
    data = parse_output(make_parser('sprint'), _write(tmp_path, good, cut, good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.xfail(strict=True, reason='Paro counts lines without a depth as good rows (#566)')
def test_paro_line_without_depth(make_parser, tmp_path) -> None:
    """A Paro line without a depth isn't a good row (the CTD, O2 and compensator parsers drop them)."""
    good = _first_good('paro')
    data = parse_output(make_parser('paro'), _write(tmp_path, good, '$DPT,,0', good))
    assert stat_value(data, 'Row Validity')[0] == 2


@pytest.mark.xfail(strict=True, reason='Chlorophyll Validity is [bad, good] (#567)')
def test_fluoro_validity_order(make_parser) -> None:
    """Chlorophyll Validity is [in range, out of range], like every other Validity stat."""
    data = parse_output(make_parser('fluoro'), _input('fluoro'))
    assert stat_value(data, 'Chlorophyll Validity') == [41, 1]


@pytest.mark.xfail(strict=True, reason='PAR2 gives irradiance in a PAR unit (#568)')
def test_par2_irradiance_units(make_parser) -> None:
    """Long- and short-wave irradiance are in W/m^2."""
    data = parse_output(make_parser('par2'), _input('par2'))
    units = {stat['statName']: stat['statUnit'] for stat in data['stats']}
    units.update({f"{viz['label']} chart": viz['unit'] for viz in data['visualizerData']})
    assert {units[key] for key in ('LW Irradiance', 'SW Irradiance', 'LW Irradiance chart',
                                   'SW Irradiance chart')} == {'W/m^2'}


@pytest.mark.xfail(strict=True, reason='SSV reports SV Validity twice (#569)')
def test_ssv_one_validity_stat(make_parser) -> None:
    """SSV reports one SV Validity stat."""
    data = parse_output(make_parser('ssv'), _input('ssv'))
    assert [stat['statName'] for stat in data['stats']].count('SV Validity') == 1
