"""Tests for the collection system transfer worker's paths, wildcard sources and file lists (#510)."""

import logging
import os
import time

import pytest

from server.tests.cst_helpers import make_worker
from server.workers import run_collection_system_transfer as cst_run


@pytest.fixture
def worker(monkeypatch, fake_ovdm, warehouse):
    """Return a function making a worker for a transfer with the given settings."""
    return lambda **cfg: make_worker(monkeypatch, fake_ovdm, warehouse, **cfg)


# --- Paths --------------------------------------------------------------------

def test_keyword_replace(worker) -> None:
    """{cruiseID}, {loweringID} and {loweringDataBaseDir}; a trailing / is dropped, / itself kept."""
    w = worker(lowering_id='DIVE01')
    assert w.keyword_replace('/data/{cruiseID}/{loweringDataBaseDir}/{loweringID}/') == \
        '/data/TEST001/Vehicle/DIVE01'
    assert w.keyword_replace('/') == '/'
    assert w.keyword_replace(None) is None
    assert worker().keyword_replace('/x/{loweringID}') == '/x/{loweringID}'


def test_cruise_level_paths(worker, warehouse) -> None:
    """Source, relative and absolute destination of a cruise-level transfer."""
    w = worker(sourceDir='/data/{cruiseID}/', destDir='/SCS/{cruiseID}')
    assert w.build_source_dir() == '/data/TEST001'
    assert w.build_rel_dir() == 'SCS/TEST001'
    assert w.build_dest_dir() == str(warehouse.cruise_dir / 'SCS' / 'TEST001')


def test_lowering_level_paths(worker, warehouse) -> None:
    """Lowering-level transfers go under <loweringDataBaseDir>/<loweringID>/."""
    w = worker(cruiseOrLowering=1, destDir='HD_Video', lowering_id='DIVE01')
    assert w.build_rel_dir() == os.path.join('Vehicle', 'DIVE01', 'HD_Video')
    assert worker(cruiseOrLowering=1, lowering_id=None).build_rel_dir() is None


def test_paths_without_a_transfer(worker) -> None:
    """Without a transfer there are no paths."""
    w = worker()
    w.collection_system_transfer = None
    assert w.build_rel_dir() is None and w.build_source_dir() is None


def test_build_logfile_dirpath_creates_it(worker, fake_ovdm, tmp_path) -> None:
    """The transfer log directory is created if missing."""
    fake_ovdm.get_transfer_log_dir.return_value = str(tmp_path / 'logs' / 'transfer')
    assert worker().build_logfile_dirpath() == str(tmp_path / 'logs' / 'transfer')
    assert (tmp_path / 'logs' / 'transfer').is_dir()


def test_destination_dir_check(worker, warehouse) -> None:
    """The destination must exist before a transfer."""
    w = worker()
    assert w.test_destination_dir() == [{'partName': 'Verify destination directory', 'result': 'Fail',
                                         'reason': f'Unable to find destination directory: {w.dest_dir}'}]
    os.makedirs(w.dest_dir)
    assert w.test_destination_dir() == [{'partName': 'Verify destination directory', 'result': 'Pass'}]


# --- Wildcard sources ---------------------------------------------------------

def test_enumerate_sources_without_a_wildcard(worker) -> None:
    """A plain source is one source, copied into the destination itself."""
    assert worker()._enumerate_sources('local', '/data') == [('/data', None)]  # pylint: disable=protected-access


def test_enumerate_sources_wildcard_only_in_the_last_component(worker, caplog) -> None:
    """A wildcard elsewhere in the path is used as is, with a warning."""
    with caplog.at_level(logging.WARNING):
        assert worker()._enumerate_sources('local', '/data/*/raw*') == [('/data/*/raw*', None)]  # pylint: disable=protected-access
    assert 'only supported in the last path component' in caplog.text


def test_enumerate_local_wildcard(worker, tmp_path) -> None:
    """Matching directories, sorted, each copied into a directory of its own name; files don't count."""
    for name in ('run02', 'run01'):
        (tmp_path / name).mkdir()
    (tmp_path / 'run03.txt').write_text('a file')
    assert worker()._enumerate_sources('local', f'{tmp_path}/run*') == [  # pylint: disable=protected-access
        (f'{tmp_path}/run01', 'run01'), (f'{tmp_path}/run02', 'run02')]
    assert worker()._enumerate_sources('local', f'{tmp_path}/none*') == []  # pylint: disable=protected-access


def test_enumerate_mounted_wildcard(worker, tmp_path) -> None:
    """On a mount, the server path's parent is found through mount_path() (#209)."""
    (tmp_path / 'xbt01').mkdir()
    pairs = worker()._enumerate_sources('ftp', '/data/xbt*', prefix=str(tmp_path), mount_base='/data')  # pylint: disable=protected-access
    assert pairs == [('/data/xbt01', 'xbt01')]


LISTING = ('drwxr-xr-x          4,096 2026/10/22 10:00:00 .\n'
           'drwxr-xr-x          4,096 2026/10/22 10:00:00 run02\n'
           'drwxr-xr-x          4,096 2026/10/22 10:00:00 run01\n'
           'drwxr-xr-x          4,096 2026/10/22 10:00:00 other\n'
           '-rw-r--r--             10 2026/10/22 10:00:00 run03\n'
           'short line\n')


def test_enumerate_rsync_wildcard(worker, fake_run) -> None:
    """An rsync server is listed to find the matching directories."""
    fake_run.on('rsync', stdout=LISTING)
    pairs = worker(transferType=2)._enumerate_sources('rsync', '/data/run*', password_file='/tmp/pw')  # pylint: disable=protected-access
    assert pairs == [('/data/run01', 'run01'), ('/data/run02', 'run02')]
    assert fake_run.calls[0].cmd == ['rsync', '--no-motd', '--password-file=/tmp/pw',
                                     'rsync://survey@host/module/data/']


def test_enumerate_ssh_wildcard(worker, fake_run) -> None:
    """Listed over SSH with sshpass; macOS servers get no --protect-args."""
    fake_run.on('sshpass', stdout=LISTING)
    w = worker(transferType=4)
    assert w._enumerate_sources('ssh', '/data/run0[12]') == [('/data/run01', 'run01'), ('/data/run02', 'run02')]  # pylint: disable=protected-access
    cmd = fake_run.calls[0].cmd
    assert cmd[:2] == ['sshpass', '-f'] and cmd[3:] == ['rsync', '--protect-args', '-e', 'ssh', 'survey@host:/data/']
    fake_run.assert_not_in_commands('ssh-pw')

    w._enumerate_sources('ssh', '/data/run*', is_darwin=True)  # pylint: disable=protected-access
    assert '--protect-args' not in fake_run.calls[1].cmd


@pytest.mark.parametrize('transfer_type, prefix', [('rsync', 'rsync'), ('ssh', 'sshpass')])
def test_enumerate_remote_wildcard_failures(worker, fake_run, transfer_type, prefix) -> None:
    """A failed listing, or nothing matching, finds no sources."""
    w = worker(transferType=2 if transfer_type == 'rsync' else 4)
    fake_run.on(prefix, returncode=5, stderr='auth failed')
    assert w._enumerate_sources(transfer_type, '/data/run*') == []  # pylint: disable=protected-access
    fake_run.on(prefix, stdout='drwxr-xr-x 4,096 2026/10/22 10:00:00 other\n')
    assert w._enumerate_sources(transfer_type, '/data/run*') == []  # pylint: disable=protected-access


def test_enumerate_unknown_type(worker) -> None:
    """An unknown transfer type is left as given."""
    assert worker()._enumerate_sources('other', '/data/x*') == [('/data/x*', None)]  # pylint: disable=protected-access


# --- File lists: local and SMB ------------------------------------------------

def _tree(root, files):
    """Create files (path: content) under root."""
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)


def test_local_file_list(worker, tmp_path) -> None:
    """Filters with {cruiseID} and date placeholders; ignored folders aren't walked (#265)."""
    _tree(tmp_path, {'TEST001_20261022.raw': 'a', 'sub/TEST001_20261022.raw': 'b', 'notes.txt': 'c',
                     'TEST001_bad.raw': 'd', 'scratch.tmp': 'e', '.DS_Store': 'f', '@eaDir/thumb.jpg': 'g'})
    w = worker(sourceDir=str(tmp_path), includeFilter='*{cruiseID}_{YYYY}{mm}{DD}.raw,*.txt',
               excludeFilter='*notes*', ignoreFilter='*.tmp')

    result = w.build_cst_filelist()

    assert result['verdict']
    assert sorted(result['files']['include']) == ['TEST001_20261022.raw', 'sub/TEST001_20261022.raw']
    assert sorted(result['files']['exclude']) == ['TEST001_bad.raw', 'notes.txt']
    assert result['files']['new'] == [] and result['files']['updated'] == []


def test_local_file_list_lowering_placeholder(worker, tmp_path) -> None:
    """Filters can use {loweringID}."""
    _tree(tmp_path, {'DIVE01.raw': 'a', 'DIVE02.raw': 'b'})
    w = worker(sourceDir=str(tmp_path), includeFilter='*{loweringID}.raw', lowering_id='DIVE01')
    assert w.build_cst_filelist()['files']['include'] == ['DIVE01.raw']


def test_local_file_list_date_window(worker, tmp_path) -> None:
    """Files modified before the data window are left out."""
    _tree(tmp_path, {'old.raw': 'a', 'new.raw': 'b'})
    os.utime(tmp_path / 'old.raw', (946684800, 946684800))        # 2000-01-01
    w = worker(sourceDir=str(tmp_path))
    w.data_start_date = '2020/01/01 00:00'
    assert w.build_cst_filelist()['files']['include'] == ['new.raw']


def test_local_file_list_missing_source(worker, tmp_path) -> None:
    """A missing source fails rather than looking empty, which Sync would act on (#206)."""
    result = worker(sourceDir=str(tmp_path / 'missing')).build_cst_filelist()
    assert result == {'verdict': False, 'reason': f'Source directory {tmp_path / "missing"} not found'}


def test_local_file_list_unreadable_subdirectory(worker, tmp_path, monkeypatch, caplog) -> None:
    """Locally an unreadable folder is a warning; on an SMB share it fails the listing."""
    _tree(tmp_path, {'a.raw': 'a'})
    real_walk = os.walk

    def walk(top, onerror=None):
        onerror(PermissionError(13, 'Permission denied', str(tmp_path / 'private')))
        yield from real_walk(top)

    monkeypatch.setattr(cst_run.os, 'walk', walk)
    with caplog.at_level(logging.WARNING):
        assert worker(sourceDir=str(tmp_path)).build_cst_filelist()['files']['include'] == ['a.raw']
    assert 'Skipping unreadable source path' in caplog.text

    smb = worker(transferType=3, sourceDir='/')
    result = smb.build_cst_filelist(prefix=str(tmp_path))
    assert not result['verdict'] and result['reason'].startswith('Error listing source directory /: ')


def test_local_file_list_stopped_while_walking(worker, tmp_path) -> None:
    """Stop during the walk returns no files, so nothing is copied or deleted (#473)."""
    _tree(tmp_path, {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path))
    w.stop = True
    assert w.build_cst_filelist() == {'verdict': True, 'stopped': True,
                                      'files': {'include': [], 'exclude': [], 'new': [], 'updated': []}}


def test_smb_file_list_in_the_mount(worker, tmp_path) -> None:
    """An SMB source is listed in the mount; paths are relative to the source."""
    _tree(tmp_path, {'share_dir/a.raw': 'a'})
    result = worker(transferType=3, sourceDir='/share_dir').build_cst_filelist(prefix=str(tmp_path))
    assert result['files']['include'] == ['a.raw']


def test_local_staleness_drops_growing_files(worker, tmp_path, monkeypatch) -> None:
    """A file whose size changes during the staleness wait isn't transferred yet."""
    _tree(tmp_path, {'done.raw': 'aaaa', 'growing.raw': 'bb', 'deleted.raw': 'c'})
    waits = []

    def wait(seconds):
        waits.append(seconds)
        (tmp_path / 'growing.raw').write_text('bbbbbb')
        os.remove(tmp_path / 'deleted.raw')

    monkeypatch.setattr(cst_run.time, 'sleep', wait)
    result = worker(sourceDir=str(tmp_path), staleness=5).build_cst_filelist()
    assert waits == [5] and result['files']['include'] == ['done.raw']


def test_local_staleness_stopped(worker, tmp_path, monkeypatch) -> None:
    """Stop during the staleness check returns no files (#473)."""
    _tree(tmp_path, {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path), staleness=5)
    monkeypatch.setattr(cst_run.time, 'sleep', lambda seconds: setattr(w, 'stop', True))
    assert w.build_cst_filelist()['stopped'] is True


# --- File lists: rsync and SSH ------------------------------------------------

RSYNC_LISTING = ('drwxr-xr-x          4,096 2026/10/22 10:00:00 .\n'
                 '-rw-r--r--             10 2026/10/22 10:00:00 a.raw\n'
                 '-rw-r--r--             20 2026/10/22 10:00:00 sub/b.raw\n'
                 '-rw-r--r--              5 2026/10/22 10:00:00 c.csv\n')


def test_rsync_file_list(worker, fake_run) -> None:
    """The listing command carries the options, ignored-folder excludes and password file."""
    fake_run.on('rsync', stdout=RSYNC_LISTING)
    w = worker(transferType=2, includeFilter='*.raw', skipEmptyFiles=1, skipEmptyDirs=1)

    result = w.build_cst_filelist(rsync_password_filepath='/tmp/pw')

    assert sorted(result['files']['include']) == ['a.raw', 'sub/b.raw'] and result['files']['exclude'] == ['c.csv']
    cmd = fake_run.calls[0].cmd
    assert cmd[:4] == ['rsync', '-r', '--min-size=1', '-m']
    assert any(arg.startswith('--exclude=') for arg in cmd)
    assert cmd[-3:] == ['--password-file=/tmp/pw', '--no-motd', 'rsync://survey@host/module/data/']


def test_ssh_file_list(worker, fake_run) -> None:
    """The SSH password goes to sshpass in a file (#426); macOS gets no --protect-args."""
    fake_run.on('sshpass', stdout=RSYNC_LISTING)
    w = worker(transferType=4)
    assert len(w.build_cst_filelist()['files']['include']) == 3
    cmd = fake_run.calls[0].cmd
    assert cmd[:2] == ['sshpass', '-f'] and '--protect-args' in cmd and cmd[-3:] == ['-e', 'ssh', 'survey@host:/data/']
    fake_run.assert_not_in_commands('ssh-pw')

    w.build_cst_filelist(is_darwin=True)
    assert '--protect-args' not in fake_run.calls[1].cmd


@pytest.mark.parametrize('sync, returncode, stderr, ok', [
    (0, 23, 'rsync: opendir "/data/private" failed: Permission denied (13)\n', True),
    (1, 23, 'rsync: opendir "/data/private" failed: Permission denied (13)\n', False),
    (0, 10, 'rsync: failed to connect to host: Connection refused (111)\n', False),
])
def test_rsync_file_list_errors(worker, fake_run, sync, returncode, stderr, ok) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """A partial listing is used only without Sync from source (#238, #264)."""
    fake_run.on('rsync', returncode=returncode, stdout=RSYNC_LISTING, stderr=stderr)
    result = worker(transferType=2, syncFromSource=sync).build_cst_filelist(rsync_password_filepath='/p')
    assert result['verdict'] is ok
    if not ok:
        assert result['reason'].startswith(f'Error listing source directory /data: rsync exited with code {returncode}')


def test_rsync_staleness_keeps_files_listed_again_unchanged(worker, fake_run, monkeypatch) -> None:
    """Changed or missing on the re-listing: not transferred yet (#284)."""
    relisting = ('-rw-r--r--  10 2026/10/22 10:00:00 a.raw\n'
                 '-rw-r--r--  25 2026/10/22 10:00:00 sub/b.raw\n')
    monkeypatch.setattr(cst_run.time, 'sleep', lambda seconds: fake_run.on('rsync', stdout=relisting))
    fake_run.on('rsync', stdout=RSYNC_LISTING)
    result = worker(transferType=2, staleness=10).build_cst_filelist(rsync_password_filepath='/p')
    assert result['files']['include'] == ['a.raw']
    assert fake_run.calls[0].cmd == fake_run.calls[1].cmd


def test_rsync_staleness_relisting_fails(worker, fake_run, monkeypatch) -> None:
    """A failed re-listing fails instead of silently skipping the check (#238)."""
    monkeypatch.setattr(cst_run.time, 'sleep',
                        lambda seconds: fake_run.on('rsync', returncode=10, stderr='Connection refused'))
    fake_run.on('rsync', stdout=RSYNC_LISTING)
    result = worker(transferType=2, staleness=10).build_cst_filelist(rsync_password_filepath='/p')
    assert result['reason'].startswith('Error re-listing source directory /data: rsync exited with code 10')


# --- File lists: FTP ----------------------------------------------------------

def test_ftp_file_list(worker, monkeypatch) -> None:
    """FTP sources are listed with rclone lsjson, not through the mount (#208)."""
    calls = []
    monkeypatch.setattr(cst_run, 'list_ftp_source', lambda config, remote, path, excludes: calls.append(
        (config, remote, path)) or (True, [('a.raw', 10, time.time()), ('sub/b.csv', 3, time.time())]))

    result = worker(transferType=5, includeFilter='*.raw').build_cst_filelist(prefix='/mnt', rclone_config='cfg')

    assert result['files'] == {'include': ['a.raw'], 'exclude': ['sub/b.csv'], 'new': [], 'updated': []}
    assert calls == [('cfg', 'ftp_source', '/data')]


def test_ftp_file_list_failure(worker, monkeypatch) -> None:
    """A failed rclone listing fails the file list."""
    monkeypatch.setattr(cst_run, 'list_ftp_source', lambda *args: (False, '550 Permission denied'))
    assert worker(transferType=5).build_cst_filelist(prefix='/mnt', rclone_config='cfg') == {
        'verdict': False, 'reason': 'Error listing source directory /data: 550 Permission denied'}


def test_ftp_staleness(worker, monkeypatch) -> None:
    """The re-listing drops files whose size changed; a failed re-listing fails."""
    now = time.time()
    listings = iter([(True, [('a.raw', 10, now), ('b.raw', 5, now)]), (True, [('a.raw', 10, now), ('b.raw', 9, now)])])
    monkeypatch.setattr(cst_run, 'list_ftp_source', lambda *args: next(listings))
    monkeypatch.setattr(cst_run.time, 'sleep', lambda seconds: None)
    w = worker(transferType=5, staleness=5)
    assert w.build_cst_filelist(prefix='/mnt', rclone_config='c')['files']['include'] == ['a.raw']

    listings = iter([(True, [('a.raw', 10, now)]), (False, 'timeout')])
    assert w.build_cst_filelist(prefix='/mnt', rclone_config='c') == {
        'verdict': False, 'reason': 'Error re-listing source directory /data: timeout'}


def test_local_file_list_stopped_while_classifying(worker, tmp_path, monkeypatch) -> None:
    """Stop during classification also returns no files (#473)."""
    _tree(tmp_path, {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path))

    def classify(batch, *args):
        w.stop = True
        return [('include', batch[0], '1')]

    monkeypatch.setattr(cst_run, 'process_batch', classify)
    assert w.build_cst_filelist()['stopped'] is True
