"""Tests for the NMEA parsers in server/plugins/parsers (#513 part 1).

Each parser's output for a small input file (server/tests/data/parsers/nmea)
is compared with its saved expected output: the stats, Validity and DeltaT
included, the quality tests and the charted data. After a change to a
parser's output that's intended, ``pytest --update-expected`` saves the new
output, so the change shows in the diff.

The input files have a few good sentences every 5 s, a 30 s gap (90 s for
$WICOR) and one value out of range, and these bad rows: a wrong checksum, no
checksum, a value that isn't a number, a line without a timestamp, a sentence
cut short, a wrong unit letter (where the sentence has them) and another
sentence ($GPZDA, not a bad row; left out for GNSS, HPR, PASHR and PSXN24,
which read it, #558). The GGA and $WICOR inputs are real sentences: GGA from
openvdm_sample_data, $WICOR from the example in #408. Bugs the tests found
are strict xfails at the end.
"""

import argparse
import logging

import pandas as pd
import pytest

from server.tests.helpers import PARSER_DATA, parse_output, stat_value

# Each parser's .py.dist (server/plugins/parsers/<name>_parser.py.dist) and class
PARSERS = {
    'dbs': 'DBSParser',
    'dpt': 'DPTParser',
    'gga': 'GGAParser',
    'gnss': 'GNSSParser',
    'hdt': 'HDTParser',
    'hpr': 'HPRParser',
    'mwd': 'MWDParser',
    'mwv': 'MWVParser',
    'pashr': 'PashrParser',
    'psxn23': 'PSXN23Parser',
    'psxn24': 'PSXN24Parser',
    'vtg': 'VTGParser',
    'wicor': 'WICORParser',
    'xdr': 'XDRParser',
}

# The parsers' required options
OPTIONS = {'wicor': {'category': 'wind_speed'}}


def _nmea(body):
    """*body* as a sentence, with its checksum."""
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f'${body}*{checksum:02X}'


# A good sentence of each parser, for the bad-input tests
GOOD = {
    'dbs': _nmea('SDDBS,4921.3,f,1500.00,M,820.2,F'),
    'dpt': _nmea('SDDPT,1500.00,-5.0,12000'),
    'gga': _nmea('GPGGA,000000.987,2635.03241,N,09331.21859,W,2,09,1.1,1.89,M,,,9,0025'),
    'gnss': _nmea('PGNSS,000000.00,2635.0324,N,09331.2186,W,12.00,120.00,0.50,-0.50,0.02,0.05'),
    'hdt': _nmea('HEHDT,358.00,T'),
    'hpr': _nmea('PSAT,HPR,000000.00,120.00,0.50,-0.50,N'),
    'mwd': _nmea('WIMWD,358.0,T,346.0,M,15.0,N,7.7,M'),
    'mwv': _nmea('WIMWV,358.0,R,15.0,N,A'),
    'pashr': _nmea('PASHR,000000.000,120.00,T,-0.50,0.50,0.00,0.011,0.011,0.032,2,1'),
    'psxn23': _nmea('PSXN,23,-0.50,0.50,358.00,0.00'),
    'psxn24': _nmea('PSXN,24,0.000,0.000,0.000,0.000'),
    'vtg': _nmea('GPVTG,358.0,T,346.0,M,10.0,N,18.5,K,A'),
    'xdr': _nmea('WIXDR,P,1.01320,B,0,C,22.00,C,H,60.00,P,1,FAN,0'),
}

# The value each parser reads that's replaced by text, by field number
NUMBER_FIELD = {'dbs': 3, 'dpt': 1, 'gga': 7, 'gnss': 7, 'hdt': 1, 'hpr': 3, 'mwd': 1, 'mwv': 1,
                'pashr': 2, 'psxn23': 2, 'psxn24': 2, 'vtg': 1, 'xdr': 2}

# Each input file's good rows, and its bad rows by line number, including
# the line without a timestamp (29, #554). WICOR's input has no such line.
ROWS = {name: (42, '6, 12, 18, 29, 35') for name in PARSERS}
ROWS.update({name: (42, '6, 12, 18, 29, 35, 38') for name in ('dbs', 'dpt', 'hdt', 'mwd', 'mwv', 'vtg')})
ROWS.update({'gga': (44, '6, 12, 18, 29, 35'), 'wicor': (42, '6, 12, 18, 34')})

# A window of each input file, for the crop tests
WINDOW = {'gga': ('2012-04-28T00:01:01.109Z', '2012-04-28T00:02:01.110Z')}
DEFAULT_WINDOW = ('2026-10-01T00:01:00Z', '2026-10-01T00:02:00Z')


@pytest.fixture
def make_parser(load_dist):
    """Return a function that makes a parser by name, with *options*."""
    def make(name, **options):
        module = load_dist(f'server/plugins/parsers/{name}_parser.py.dist')
        defaults = {} if {'fields', 'category'} & set(options) else OPTIONS.get(name, {})
        return getattr(module, PARSERS[name])(**{**defaults, **options})
    return make


def _good(name):
    """A good sentence of the parser: from GOOD, or the first in its input file ($WICOR)."""
    return GOOD.get(name) or (PARSER_DATA / 'nmea' / f'{name}.txt').read_text().split(',', 1)[1].split('\n')[0]


def _write(tmp_path, *sentences):
    """A log file of *sentences*, timestamped 5 s apart, after a comment line."""
    path = tmp_path / 'log.txt'
    path.write_text('# test log\n' + ''.join(f'2026-10-01T00:00:{5 * n:02d}.000000Z,{sentence}\n'
                                              for n, sentence in enumerate(sentences)))
    return path


# --- Output -------------------------------------------------------------------

@pytest.mark.parametrize('case, name, options', [(name, name, {}) for name in PARSERS] + [
    ('mwd_no_mag', 'mwd', {'no_mag': True}),
    ('vtg_no_mag', 'vtg', {'no_mag': True}),
    # WD7: flagged out of range on some lines
    ('wicor_wind_direction', 'wicor', {'category': 'wind_direction'}),
    # SW and LW are -99 and flagged invalid on every line
    ('wicor_radiation', 'wicor', {'category': 'radiation'}),
    # AT is -99.0 (missing) on one line; a second sensor by name; PH isn't in the file
    ('wicor_fields', 'wicor', {'fields': ['AT', 'WS_2', 'PH']}),
], ids=lambda value: value if isinstance(value, str) else '')
def test_output(make_parser, expected, monkeypatch, case, name, options) -> None:
    """Each parser's output for its input file is the expected output."""
    monkeypatch.chdir(PARSER_DATA)  # the GGA track is named after the file
    expected(f'nmea_{case}', parse_output(make_parser(name, **options), f'nmea/{name}.txt'))


@pytest.mark.parametrize('name', PARSERS)
def test_bad_rows(make_parser, caplog, name) -> None:
    """The input file's bad rows are counted and reported by line number (zero-based); another
    sentence isn't one."""
    caplog.set_level(logging.ERROR)
    path = PARSER_DATA / 'nmea' / f'{name}.txt'
    good, bad = ROWS[name]
    assert stat_value(parse_output(make_parser(name), path), 'Row Validity') == [good, len(bad.split(', '))]
    assert f'Error(s) parsing datafile {path} on row(s): {bad}' in caplog.text


# --- Bad input ----------------------------------------------------------------

def _bad_sentences(name):
    """Corrupt copies of the parser's good sentence, by name."""
    good = GOOD[name]
    fields = good[1:].split('*')[0].split(',')
    fields[NUMBER_FIELD[name]] = 'x' + fields[NUMBER_FIELD[name]]
    return {
        'bad checksum': good[:-2] + ('00' if good[-2:] != '00' else '11'),
        'cut short': good[:len(good) // 2],
        'not a number': _nmea(','.join(fields)),
    }


@pytest.mark.parametrize('name, case', [(name, case) for name in GOOD for case in _bad_sentences(name)])
def test_bad_sentence(make_parser, tmp_path, name, case) -> None:
    """A corrupt sentence is a bad row; the good ones around it are read."""
    good = GOOD[name]
    data = parse_output(make_parser(name), _write(tmp_path, good, _bad_sentences(name)[case], good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('name', GOOD)
def test_missing_checksum_is_a_bad_row(make_parser, tmp_path, name) -> None:
    """A sentence without a checksum has been cut short: by default it's a bad row (#416, #418)."""
    good = GOOD[name]
    data = parse_output(make_parser(name), _write(tmp_path, good, good.split('*')[0], good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('name', [name for name in GOOD if name not in ('gga', 'mwv', 'psxn23')])
def test_require_checksum_false(make_parser, tmp_path, name) -> None:
    """With require_checksum=False, a sentence without a checksum is read (#418)."""
    good = GOOD[name]
    data = parse_output(make_parser(name, require_checksum=False), _write(tmp_path, good, good.split('*')[0], good))
    assert stat_value(data, 'Row Validity') == [3, 0]


@pytest.mark.parametrize('name', [name for name in GOOD if name != 'gga'])
def test_require_checksum_false_still_checks_it(make_parser, tmp_path, name) -> None:
    """With require_checksum=False, a checksum that doesn't match is still a bad row."""
    good = GOOD[name]
    data = parse_output(make_parser(name, require_checksum=False),
                  _write(tmp_path, good, good[:-2] + ('00' if good[-2:] != '00' else '11'), good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('name, sentence', [
    ('dbs', _nmea('SDDBS,4921.3,f,1500.00,F,820.2,F')),
    ('dpt', _nmea('SDDPT,1500.00,-5.0,12000,1')),
    ('hdt', _nmea('HEHDT,120.00,M')),
    ('mwd', _nmea('WIMWD,10.0,T,358.0,M,15.0,K,7.7,M')),
    ('mwv', _nmea('WIMWV,30.0,X,15.0,N,A')),
    ('mwv', _nmea('WIMWV,30.0,R,15.0,X,A')),
    ('psxn23', _nmea('PSXN,23,-0.50,0.50,358.00')),
    ('psxn24', _nmea('PSXN,24,0.000,0.000,0.000')),
    ('vtg', _nmea('GPVTG,10.0,T,358.0,M,10.0,N,18.5,M,A')),
    ('vtg', _nmea('GPVTG,10.0,T,358.0,M,10.0,N')),
    ('gga', _nmea('GPGGA,000000.987,2635.03241,N,09331.21859,W,2,09,1.1,1.89,M,,,9')),
    ('gga', _nmea('GPGGA,000000.987,26.3503241,N,09331.21859,W,2,09,1.1,1.89,M,,,9,0025')),
    ('gga', _nmea('GPGGA,000000.987,2635.03241,N,09331.21859,W,2,09,1.1,1.89,F,,,9,0025')),
    ('gga', _nmea('GPGGA,000000.987,9935.03241,N,09331.21859,W,2,09,1.1,1.89,M,,,9,0025')),
], ids=lambda value: value if not value.startswith('$') else None)
def test_malformed_sentence(make_parser, tmp_path, name, sentence) -> None:
    """A sentence with the wrong number of fields, units or position format is a bad row."""
    good = GOOD[name]
    data = parse_output(make_parser(name), _write(tmp_path, good, sentence, good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('sentence', [
    _nmea('SDDPT,1500.00,-5.0'),
    _nmea('GPVTG,10.0,T,358.0,M,10.0,N,18.5,K'),
], ids=['dpt-3-fields', 'vtg-9-fields'])
def test_older_sentence_versions(make_parser, tmp_path, sentence) -> None:
    """DPT without the maximum range and VTG without the mode (before NMEA 2.3) are read."""
    name = sentence[3:6].lower()
    data = parse_output(make_parser(name), _write(tmp_path, GOOD[name], sentence))
    assert stat_value(data, 'Row Validity') == [2, 0]


@pytest.mark.parametrize('name', PARSERS)
def test_empty_file(make_parser, tmp_path, name) -> None:
    """An empty file has no output."""
    path = tmp_path / 'log.txt'
    path.write_text('')
    assert parse_output(make_parser(name), path) is None


@pytest.mark.parametrize('name', PARSERS)
def test_no_good_rows(make_parser, tmp_path, name) -> None:
    """A file with only bad rows has no output."""
    assert parse_output(make_parser(name), _write(tmp_path, '$GARBAGE*00', 'no timestamp here')) is None


@pytest.mark.filterwarnings('ignore:Could not infer format')
@pytest.mark.parametrize('name', PARSERS)
def test_unreadable_timestamps(make_parser, tmp_path, name) -> None:
    """A file whose timestamps aren't dates has no output."""
    good = _good(name)
    path = tmp_path / 'log.txt'
    path.write_text(f'2026-13-45T00:00:00.000Z,{good}\n2026-13-45T00:00:05.000Z,{good}\n')
    assert parse_output(make_parser(name), path) is None


@pytest.mark.parametrize('name', PARSERS)
def test_missing_file(make_parser, tmp_path, caplog, name) -> None:
    """A file that can't be read has no output; the error is logged."""
    assert parse_output(make_parser(name), tmp_path / 'missing.txt') is None
    assert 'Failed to read file' in caplog.text


@pytest.mark.parametrize('name', PARSERS)
def test_crop(make_parser, monkeypatch, name) -> None:
    """start_dt and stop_dt crop the data to the window, inclusive."""
    monkeypatch.chdir(PARSER_DATA)
    start, stop = WINDOW.get(name, DEFAULT_WINDOW)
    data = parse_output(make_parser(name, start_dt=start, stop_dt=stop), f'nmea/{name}.txt')
    assert [pd.Timestamp(bound) for bound in stat_value(data, 'Temporal Bounds')] == [pd.Timestamp(start),
                                                                                 pd.Timestamp(stop)]


@pytest.mark.parametrize('name', PARSERS)
def test_crop_to_nothing(make_parser, monkeypatch, caplog, name) -> None:
    """A window with no data in it gives no output."""
    monkeypatch.chdir(PARSER_DATA)
    parser = make_parser(name, start_dt='2030-01-01T00:00:00Z')
    assert parse_output(parser, f'nmea/{name}.txt') is None
    assert 'empty after cropping' in caplog.text


# --- $WICOR options -------------------------------------------------------------

@pytest.mark.parametrize('options, message', [
    ({}, 'Give either fields or a category'),
    ({'fields': ['AT'], 'category': 'air'}, 'Give either fields or a category'),
    ({'category': 'weather'}, 'Unknown $WICOR category: weather'),
    ({'fields': ['AT', 'XX', 'YY_2']}, 'Unknown $WICOR field(s): XX, YY_2'),
])
def test_wicor_bad_options(load_dist, options, message) -> None:
    """The parser needs exactly one of fields and category, and only ones it knows (#408)."""
    module = load_dist('server/plugins/parsers/wicor_parser.py.dist')
    with pytest.raises(ValueError, match=message.replace('$', r'\$').replace('(', r'\(').replace(')', r'\)')):
        module.WICORParser(**options)


def test_wicor_category_not_in_file(make_parser, caplog) -> None:
    """A category with none of its fields in the file gives no output."""
    assert parse_output(make_parser('wicor', category='optics_chem'), PARSER_DATA / 'nmea' / 'wicor.txt') is None
    assert 'No optics_chem fields in file' in caplog.text


def test_wicor_field_not_in_file(make_parser, caplog) -> None:
    """A field that's never in the file is left out, with a warning."""
    data = parse_output(make_parser('wicor', fields=['AT', 'PH']), PARSER_DATA / 'nmea' / 'wicor.txt')
    assert 'Field(s) not in' in caplog.text and ': PH' in caplog.text
    assert [viz['label'] for viz in data['visualizerData']] == ['Air Temperature']


def test_wicor_checksum_required(make_parser, tmp_path) -> None:
    """$WICOR sentences always need their checksum."""
    good = _good('wicor')
    data = parse_output(make_parser('wicor'), _write(tmp_path, good, good.split('*')[0], good))
    assert stat_value(data, 'Row Validity') == [2, 1]


@pytest.mark.parametrize('cli_args, kwargs', [
    (['--category', 'air'], {'fields': None, 'category': 'air', 'max_delta_t': 60}),
    (['--fields', 'AT,WS_2', '--max-delta-t', '5'],
     {'fields': ['AT', 'WS_2'], 'category': None, 'max_delta_t': 5}),
])
def test_wicor_cli_options(load_dist, cli_args, kwargs) -> None:
    """The command line's --category, --fields and --max-delta-t become the parser's options."""
    module = load_dist('server/plugins/parsers/wicor_parser.py.dist')
    parser = argparse.ArgumentParser()
    module.WICORParser.add_cli_arguments(parser)
    assert module.WICORParser._extract_custom_cli_kwargs(parser.parse_args(cli_args)) == kwargs


@pytest.mark.parametrize('name', [name for name in GOOD if name != 'gga'])
@pytest.mark.parametrize('cli_args, required', [([], True), (['--allow-missing-checksum'], False)])
def test_allow_missing_checksum_cli_option(load_dist, name, cli_args, required) -> None:
    """--allow-missing-checksum sets require_checksum=False (#418)."""
    cls = getattr(load_dist(f'server/plugins/parsers/{name}_parser.py.dist'), PARSERS[name])
    parser = argparse.ArgumentParser()
    cls.add_cli_arguments(parser)
    assert cls._extract_custom_cli_kwargs(parser.parse_args(cli_args))['require_checksum'] is required


@pytest.mark.parametrize('name', ['mwd', 'vtg'])
def test_no_mag_cli_option(load_dist, name) -> None:
    """--noMag sets no_mag."""
    cls = getattr(load_dist(f'server/plugins/parsers/{name}_parser.py.dist'), PARSERS[name])
    parser = argparse.ArgumentParser()
    cls.add_cli_arguments(parser)
    assert cls._extract_custom_cli_kwargs(parser.parse_args(['--noMag']))['no_mag'] is True
    assert cls._extract_custom_cli_kwargs(parser.parse_args([]))['no_mag'] is False


def test_xdr_reads_one_layout(make_parser, tmp_path) -> None:
    """XDR reads its instrument's field layout only: a sentence with an ID after each sensor isn't read (#561)."""
    standard = _nmea('WIXDR,P,1.01320,B,0,C,22.00,C,1,H,60.00,P,2')
    assert parse_output(make_parser('xdr'), _write(tmp_path, standard, standard)) is None


# --- Bugs -----------------------------------------------------------------------

@pytest.mark.parametrize('name', PARSERS)
def test_line_without_timestamp_is_a_bad_row(make_parser, tmp_path, name) -> None:
    """A line without a timestamp is a bad row (#554)."""
    good = _good(name)
    path = _write(tmp_path, good, good)
    path.write_text(path.read_text() + good + '\n')
    assert stat_value(parse_output(make_parser(name), path), 'Row Validity') == [2, 1]


def test_gga_reads_the_first_line(make_parser, tmp_path) -> None:
    """GGA reads a log file's first line: OpenRVDAS logs have no header (#555)."""
    path = tmp_path / 'log.txt'
    path.write_text(''.join(f'2026-10-01T00:00:0{n}.000000Z,{GOOD["gga"]}\n' for n in range(3)))
    assert stat_value(parse_output(make_parser('gga'), path), 'Row Validity') == [3, 0]


def test_mwd_speed_in_m_s(make_parser, tmp_path) -> None:
    """MWD's second speed is in m/s (unit M), not mph (#556)."""
    data = parse_output(make_parser('mwd'), _write(tmp_path, GOOD['mwd'], GOOD['mwd']))
    units = {stat['statUnit'] for stat in data['stats']} | {viz['unit'] for viz in data['visualizerData']}
    assert 'mph' not in units and 'm/s' in units


@pytest.mark.parametrize('name', ['mwv', 'psxn23'])
def test_require_checksum_false_last_field(make_parser, tmp_path, name) -> None:
    """With require_checksum=False, MWV and PSXN23 read a sentence without a checksum (#418, #557)."""
    good = GOOD[name]
    data = parse_output(make_parser(name, require_checksum=False), _write(tmp_path, good, good.split('*')[0], good))
    assert stat_value(data, 'Row Validity') == [3, 0]


@pytest.mark.parametrize('name, other', [
    pytest.param('gnss', _nmea('GPZDA,000250.00,01,10,2026,00,00'),
                 marks=pytest.mark.xfail(strict=True, reason="GNSS's sentence isn't known yet (#633)")),
    ('hpr', _nmea('GPZDA,000250.00,01,10,2026,00,00')),
    ('pashr', _nmea('GPZDA,000250.00,01,10,2026,00,00')),
    ('psxn24', _nmea('PSXN,23,-0.50,0.50,358.00,0.00')),
])
def test_other_sentences_are_skipped(make_parser, tmp_path, name, other) -> None:
    """Another sentence in the file is neither read nor a bad row (#558)."""
    good = GOOD[name]
    assert stat_value(parse_output(make_parser(name), _write(tmp_path, good, other, good)), 'Row Validity') == [2, 0]


def test_hpr_heading_types(make_parser, tmp_path) -> None:
    """HPR reads Hemisphere's $PSAT,HPR with a GPS (N) or gyro (G) heading; another type letter
    is a bad row (#558)."""
    lines = [_nmea(f'PSAT,HPR,000000.00,120.00,0.50,-0.50,{kind}') for kind in ('N', 'G', 'X')]
    assert stat_value(parse_output(make_parser('hpr'), _write(tmp_path, *lines)), 'Row Validity') == [2, 1]


def test_psxn24_heave_velocity_unit(make_parser, tmp_path) -> None:
    """PSXN24's heave velocity is charted in m/s (#559)."""
    data = parse_output(make_parser('psxn24'), _write(tmp_path, GOOD['psxn24'], GOOD['psxn24']))
    assert {viz['label']: viz['unit'] for viz in data['visualizerData']}['Heave Velocity'] == 'm/s'


def test_angle_rounded_to_360(make_parser, tmp_path) -> None:
    """A mean heading that rounds to 360 is charted as 0 (#560)."""
    good = _nmea('HEHDT,359.9996,T')
    data = parse_output(make_parser('hdt'), _write(tmp_path, good, good))
    assert data['visualizerData'][0]['data'][0][1] == 0.0
