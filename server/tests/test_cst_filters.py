"""Tests for the collection system transfer's file classification and rsync handling (#510)."""

import logging
import os
import subprocess
from datetime import datetime

import pytest

from server.lib.transfer_utils import TransferCommandError
from server.workers import run_collection_system_transfer as cst_run

FILTERS = {'include_filters': ['*.raw', '*.txt'], 'exclude_filters': ['*bad*'], 'ignore_filters': ['*.tmp']}
ALWAYS = (0, 10 ** 12)


@pytest.mark.parametrize('path, expected', [
    ('/data/a.raw', ('include', '/data/a.raw', '10')),
    ('/data/bad.raw', ('exclude', '/data/bad.raw', None)),
    ('/data/a.csv', ('exclude', '/data/a.csv', None)),
    ('/data/a.tmp', None),
    ('/data/.DS_Store', None),
    ('/data/café.raw', ('exclude', '/data/café.raw', None)),
])
def test_classify_file(path, expected) -> None:
    """Included unless excluded; unmatched and non-ASCII names are excluded; ignored ones dropped."""
    assert cst_run.classify_file(path, 10, 100, FILTERS, *ALWAYS) == expected


@pytest.mark.parametrize('mod_time, expected', [(99, None), (100, 'include'), (200, 'include'), (201, None)])
def test_classify_file_date_window(mod_time, expected) -> None:
    """Only files modified within the window (inclusive) are considered."""
    result = cst_run.classify_file('/d/a.raw', 1, mod_time, FILTERS, 100, 200)
    assert (result[0] if result else None) == expected


def test_process_batch_stats_files(tmp_path) -> None:
    """Sizes and times come from the files; symlinks and vanished files are skipped."""
    (tmp_path / 'a.raw').write_text('12345')
    (tmp_path / 'b.csv').write_text('x')
    os.symlink(tmp_path / 'a.raw', tmp_path / 'link.raw')
    batch = [str(tmp_path / name) for name in ('a.raw', 'b.csv', 'link.raw', 'gone.raw')]

    assert cst_run.process_batch(batch, FILTERS, *ALWAYS) == [
        ('include', str(tmp_path / 'a.raw'), '5'), ('exclude', str(tmp_path / 'b.csv'), None)]


def test_process_batch_stops(tmp_path) -> None:
    """Stop ends the batch before the next file (#473)."""
    (tmp_path / 'a.raw').write_text('x')
    assert cst_run.process_batch([str(tmp_path / 'a.raw')], FILTERS, *ALWAYS, should_stop=lambda: True) == []


def test_process_listed_batch() -> None:
    """Listed files (e.g. from rclone lsjson) use the listing's size and time."""
    batch = [('/d/a.raw', 7, 150), ('/d/old.raw', 7, 50), ('/d/a.csv', 1, 150)]
    assert cst_run.process_listed_batch(batch, FILTERS, 100, 200) == [
        ('include', '/d/a.raw', '7'), ('exclude', '/d/a.csv', None)]


EPOCH = datetime(1970, 1, 1)


def test_process_rsync_batch(caplog) -> None:
    """rsync listing lines: files only, default-ignored and malformed ones skipped."""
    lines = [
        '-rw-r--r--          1,024 2026/10/22 10:00:00 sub/a.raw',
        '-rw-r--r--             10 2026/10/22 10:00:00 name with spaces.txt',
        'drwxr-xr-x          4,096 2026/10/22 10:00:00 sub',
        '-rw-r--r--             10 2026/10/22 10:00:00 sub/.DS_Store',
        '-rw-r--r--             10 2026/10/22 10:00:00 bad.raw',
        '-rw-r--r--             10 2026/10/22 10:00:00 a.tmp',
        '-rw-r--r--             10 2026/10/22 10:00:00 a.csv',
        '-rw-r--r--             10 not-a-date 10:00:00 b.raw',
        'garbage',
    ]
    with caplog.at_level(logging.WARNING):
        results = cst_run.process_rsync_batch(lines, FILTERS, *ALWAYS, EPOCH)
    assert results == [('include', 'sub/a.raw', '1,024'), ('include', 'name with spaces.txt', '10'),
                       ('exclude', 'bad.raw', None), ('exclude', 'a.csv', None)]
    assert 'Could not parse date/time' in caplog.text and 'Skipping malformed rsync line' in caplog.text


def test_process_rsync_batch_date_window() -> None:
    """rsync listing times are compared with the window, inclusive."""
    line = '-rw-r--r--  10 1970/01/01 00:01:40 a.raw'      # 100 s after the epoch
    assert cst_run.process_rsync_batch([line], FILTERS, 100, 100, EPOCH) == [('include', 'a.raw', '10')]
    assert cst_run.process_rsync_batch([line], FILTERS, 101, 200, EPOCH) == []


def test_process_rsync_batch_non_ascii_name() -> None:
    """Non-ASCII names in an rsync listing are excluded."""
    line = '-rw-r--r--  10 2026/10/22 10:00:00 café.raw'
    assert cst_run.process_rsync_batch([line], FILTERS, *ALWAYS, EPOCH) == [('exclude', 'café.raw', None)]


def test_add_files_prefixes_wildcard_matches() -> None:
    """A wildcard match's files go under its directory name."""
    all_files = {'new': ['x'], 'updated': [], 'exclude': []}
    cst_run._add_files(all_files, 'run01', {'new': ['a'], 'updated': ['b'], 'exclude': ['c']})  # pylint: disable=protected-access
    cst_run._add_files(all_files, None, {'new': ['d'], 'updated': [], 'exclude': []})  # pylint: disable=protected-access
    assert all_files == {'new': ['x', 'run01/a', 'd'], 'updated': ['run01/b'], 'exclude': ['run01/c']}


def _proc(returncode, stderr='', stdout=''):
    """A finished rsync process with the given exit code and output."""
    return subprocess.CompletedProcess(['rsync'], returncode, stdout, stderr)


def test_rsync_listing_error_prefers_the_senders_error() -> None:
    """The sender's error is the cause; the receiver's broken pipe after it isn't (#284)."""
    proc = _proc(12, stderr='rsync: [sender] write error: Broken pipe\nrsync: [receiver] read error\n'
                            'rsync error: error in rsync protocol data stream (code 12)\n')
    reason = cst_run._rsync_listing_error('Error listing source directory /d', proc)  # pylint: disable=protected-access
    assert reason == ('Error listing source directory /d: rsync exited with code 12: '
                      'rsync: [sender] write error: Broken pipe')


def test_rsync_listing_error_without_detail() -> None:
    """Without an error line, the reason is just the exit code."""
    assert cst_run._rsync_listing_error('Listing', _proc(5)) == 'Listing: rsync exited with code 5'  # pylint: disable=protected-access


SUBDIR_ERRORS = ('rsync: [sender] opendir "/data/private" failed: Permission denied (13)\n'
                 'rsync: opendir "/data/locked" (in module) failed: Permission denied (13)\n'
                 'rsync error: some files/attrs were not transferred (code 23)\n')


def test_rsync_listing_failure_ok_codes() -> None:
    """Exit 0 and 24 (vanished files) are usable listings."""
    failure = cst_run._rsync_listing_failure  # pylint: disable=protected-access
    assert failure('L', _proc(0), True) is None and failure('L', _proc(24), True) is None


def test_rsync_listing_failure_skips_unreadable_subdirectories(caplog) -> None:
    """Without Sync from source, unreadable directories inside the source are warnings (#264)."""
    with caplog.at_level(logging.WARNING):
        assert cst_run._rsync_listing_failure('L', _proc(23, SUBDIR_ERRORS), False) is None  # pylint: disable=protected-access
    assert caplog.text.count('Skipping unreadable source path') == 2


def test_rsync_listing_failure_many_unreadable_subdirectories(caplog) -> None:
    """Only the first 10 unreadable directories are logged one by one."""
    errors = ''.join(f'rsync: opendir "/data/d{i}" failed: Permission denied (13)\n' for i in range(12))
    with caplog.at_level(logging.WARNING):
        assert cst_run._rsync_listing_failure('L', _proc(23, errors), False) is None  # pylint: disable=protected-access
    assert '... and 2 more unreadable source paths' in caplog.text


@pytest.mark.parametrize('stderr, sync', [
    (SUBDIR_ERRORS, True),
    ('rsync: change_dir "/data" failed: No such file or directory (2)\n', False),
    ('rsync: [sender] opendir "/data/." failed: Permission denied (13)\n', False),
    ('', False),
])
def test_rsync_listing_failure_fails(stderr, sync) -> None:
    """A partial listing fails with Sync from source (#238), as does an unreadable source (#284)."""
    reason = cst_run._rsync_listing_failure('Error listing', _proc(23, stderr), sync)  # pylint: disable=protected-access
    assert reason.startswith('Error listing: rsync exited with code 23')


class _Worker:  # pylint: disable=too-few-public-methods
    """Just what run_transfer_command() uses."""

    def __init__(self):
        self.stop = False
        self.status = []

    def send_job_status(self, job, numerator, denominator):
        """Record a progress update."""
        self.status.append((numerator, denominator))


def test_run_transfer_command_reports_progress(monkeypatch, tmp_path) -> None:
    """Progress maps rsync's 0-100% to the job's 5-95%."""
    def fake(cmd, count, progress, should_stop):
        progress(0)
        progress(100)
        return {'new': ['a'], 'updated': ['b'], 'deleted': [], 'stopped': False}

    monkeypatch.setattr(cst_run.transfer_utils, 'run_transfer_command', fake)
    worker = _Worker()
    assert cst_run.run_transfer_command(worker, object(), ['rsync'], 2, str(tmp_path)) == (['a'], ['b'])
    assert worker.status == [(5, 100), (95, 100)]


def test_run_transfer_command_stopped_keeps_copied_files(monkeypatch, tmp_path) -> None:
    """After Stop, a file rsync listed but hadn't copied isn't reported (#262)."""
    (tmp_path / 'copied').write_text('x')
    monkeypatch.setattr(cst_run.transfer_utils, 'run_transfer_command',
                        lambda *args: {'new': ['copied', 'partial'], 'updated': ['gone'], 'deleted': [],
                                       'stopped': True})
    assert cst_run.run_transfer_command(_Worker(), None, ['rsync'], 3, str(tmp_path)) == (['copied'], [])


def test_run_transfer_command_failure_keeps_copied_files(monkeypatch, tmp_path) -> None:
    """A failed transfer raises with only the files really copied (#239, #262)."""
    (tmp_path / 'copied').write_text('x')

    def fail(*args):
        raise TransferCommandError('rsync', 23, 'failed', {'new': ['copied', 'partial'], 'updated': ['gone']})

    monkeypatch.setattr(cst_run.transfer_utils, 'run_transfer_command', fail)
    with pytest.raises(TransferCommandError) as exc:
        cst_run.run_transfer_command(_Worker(), None, ['rsync'], 2, str(tmp_path))
    assert exc.value.files == {'new': ['copied'], 'updated': []}
