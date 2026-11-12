"""The File Naming Guide agrees with the collection system transfer's filters (#451).

``www/app/Helpers/FileNamingGuide.php`` explains a transfer's filters to the
technicians who name the files. ``server/tests/data/file_naming_guide.json``
lists, for some patterns, the example name the guide gives and whether it
says the pattern never matches; ``www/tests/Helpers/FileNamingGuideTest.php``
checks the guide gives exactly those. This checks the transfer agrees: each
example is copied, matched as ``build_filters()`` and ``classify_file()`` match
it, by the path its transfer type is matched by; and a pattern the guide says
never matches doesn't match.
"""

import json

import pytest

from server.lib.file_utils import is_default_ignore
from server.tests.helpers import ROOT
from server.workers.run_collection_system_transfer import build_filters, classify_file

CASES = json.loads((ROOT / 'server' / 'tests' / 'data' / 'file_naming_guide.json').read_text())
CONTEXT = CASES['context']
ALWAYS = (0, 10 ** 12)

# What a pattern is matched against, by transfer type: the full path on the
# OpenVDM server (local), a full path under a temporary mount point (SMB, FTP),
# or the path within the source directory (rsync, SSH)
LOCAL, RSYNC, SMB, SSH, FTP = 1, 2, 3, 4, 5
SOURCE_DIR = '/data/scs'
MOUNT_DIR = '/tmp/tmp1234abcd/mntpoint/data/scs'


def _path(example, pattern, transfer_type):
    """Where a file with the example name is, as the transfer type sees it."""
    if transfer_type == LOCAL:
        return '/' + example if pattern.startswith('/') else f'{SOURCE_DIR}/sub/{example}'
    if transfer_type in (SMB, FTP):
        return f'{MOUNT_DIR}/sub/{example}'
    return f'sub/{example}' if pattern.startswith('*') else example


def _classify(path, pattern, cruise_id=CONTEXT['cruiseID'], lowering_id=CONTEXT['loweringID']):
    filters = build_filters({'includeFilter': pattern, 'excludeFilter': '', 'ignoreFilter': ''}, cruise_id, lowering_id)
    return classify_file(path, 1, 100, filters, *ALWAYS)


@pytest.mark.parametrize('case', [case for case in CASES['patterns'] if case['example'] and not case['never_matches']],
                         ids=lambda case: f"{case['type']}:{case['pattern']}")
def test_example_is_copied(case) -> None:
    """The guide's example name is copied, at the path the transfer type matches."""
    path = _path(case['example'], case['pattern'], case['type'])
    assert _classify(path, case['pattern']) == ('include', path, '1')


@pytest.mark.parametrize('case', [case for case in CASES['patterns'] if case['never_matches']],
                         ids=lambda case: f"{case['type']}:{case['pattern']}")
def test_never_matches(case) -> None:
    """A pattern the guide says never matches for the transfer type doesn't match the named file."""
    path = _path(case['example'], case['pattern'], case['type'])
    assert _classify(path, case['pattern']) == ('exclude', path, None)


def test_lowering_id_stays_without_a_lowering() -> None:
    """Without a lowering, {loweringID} stays as written, as the guide says."""
    filters = build_filters({'includeFilter': '*{loweringID}.dat'}, 'RR2601', None)
    assert filters['include_filters'] == ['*{loweringID}.dat']


def test_case_sensitive() -> None:
    """Names are case-sensitive, as the guide says."""
    rule = CASES['rules']['case_sensitive']
    assert _classify(f"{SOURCE_DIR}/{rule['name']}", rule['pattern'])[0] == 'exclude'


def test_star_crosses_folders() -> None:
    """A * also matches across folders, as the guide says."""
    rule = CASES['rules']['star_crosses_folders']
    assert _classify(f"{SOURCE_DIR}/{rule['name']}", rule['pattern'])[0] == 'include'


@pytest.mark.parametrize('name', CASES['rules']['always_skipped'])
def test_always_skipped(name) -> None:
    """The system and temporary files the guide says are always skipped are."""
    assert is_default_ignore(f'{SOURCE_DIR}/{name}')
    assert _classify(f'{SOURCE_DIR}/{name}', '*') is None


def test_non_ascii_names_are_errors() -> None:
    """A name with a character that isn't ASCII isn't copied, and is a filename error, as the guide says."""
    assert _classify(f'{SOURCE_DIR}/temp_°C.raw', '*') == ('exclude', f'{SOURCE_DIR}/temp_°C.raw', None)
