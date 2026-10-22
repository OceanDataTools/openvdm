"""Tests for the collection system transfer worker's copy, job setup, outcome and task (#510).

The copy (rsync, ``run_transfer_command``) is replaced by one that copies the
listed files, except in the end-to-end tests at the end, which run real rsync
on local directories and need GNU rsync 3 (not macOS's openrsync).
"""

import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib.transfer_jobs import IN_PROGRESS_REASON
from server.lib.transfer_utils import TransferCommandError
from server.tests.cst_helpers import CST_DEFAULTS, make_worker
from server.tests.helpers import gnu_rsync
from server.workers import run_collection_system_transfer as cst_run


@pytest.fixture
def worker(monkeypatch, fake_ovdm, warehouse):
    """Return a function making a worker for a transfer with the given settings."""
    return lambda **cfg: make_worker(monkeypatch, fake_ovdm, warehouse, **cfg)


class FakeCopy:  # pylint: disable=too-few-public-methods
    """A run_transfer_command() that copies the listed files when the source is local.

    Records each command; files listed for a remote source are reported as
    new without copying. ``fail`` makes the next copy raise after copying.
    """

    def __init__(self):
        self.commands = []
        self.fail = None

    def __call__(self, worker, current_job, cmd, file_count, dest_dir):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self.commands.append(cmd)
        files_from = next(arg.split('=', 1)[1] for arg in cmd if arg.startswith('--files-from='))
        with open(files_from, encoding='utf-8') as file:
            listed = [line.rstrip('\n') for line in file if line.strip()]
        source = cmd[-2]
        new, updated = [], []
        for path in listed:
            if os.path.isdir(source):
                target = os.path.join(dest_dir, path)
                (updated if os.path.exists(target) else new).append(path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(os.path.join(source, path), target)
            else:
                new.append(path)
        if self.fail:
            raise TransferCommandError('rsync', 23, self.fail, {'new': new, 'updated': updated})
        return new, updated


@pytest.fixture
def fake_copy(monkeypatch):
    """A FakeCopy in place of run_transfer_command()."""
    copy = FakeCopy()
    monkeypatch.setattr(cst_run, 'run_transfer_command', copy)
    return copy


def _tree(root, files):
    """Create files (path: content) under root."""
    for path, content in files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)


# --- Copying from each type of source -----------------------------------------

def test_local_transfer(worker, fake_copy, tmp_path) -> None:
    """Listed files are copied, excluded ones reported; the source path ends in /."""
    _tree(tmp_path / 'src', {'a.raw': 'a', 'sub/b.raw': 'b', 'c.csv': 'c'})
    w = worker(sourceDir=str(tmp_path / 'src'), includeFilter='*.raw')
    os.makedirs(w.dest_dir)

    result = w.transfer_from_source(None)

    assert result['verdict'] and sorted(result['files']['new']) == ['a.raw', 'sub/b.raw']
    assert result['files']['exclude'] == ['c.csv'] and 'deleted' not in result['files']
    assert (tmp_path / 'src' / 'a.raw').read_text() == Path(os.path.join(w.dest_dir, 'a.raw')).read_text(encoding='utf-8')
    cmd = fake_copy.commands[0]
    assert cmd[0] == 'rsync' and cmd[-2:] == [f"{tmp_path / 'src'}/", w.dest_dir]


def test_local_transfer_syncs_deletions(worker, fake_copy, tmp_path) -> None:
    """With Sync from source, destination files no longer in the source are deleted."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path / 'src'), syncFromSource=1)
    _tree(tmp_path, {os.path.relpath(w.dest_dir, tmp_path) + '/old.raw': 'gone from the source'})

    result = w.transfer_from_source(None)

    assert result['files']['deleted'] == ['old.raw'] and not os.path.exists(os.path.join(w.dest_dir, 'old.raw'))


def test_wildcard_source_copies_each_match_into_its_own_directory(worker, fake_copy, tmp_path) -> None:
    """Each match goes into a directory of its name; deletions are per match."""
    _tree(tmp_path / 'src', {'run01/a.raw': '1', 'run02/a.raw': '2', 'other/a.raw': 'x'})
    w = worker(sourceDir=f"{tmp_path / 'src'}/run*", syncFromSource=1)
    os.makedirs(w.dest_dir)

    result = w.transfer_from_source(None)

    assert sorted(result['files']['new']) == ['run01/a.raw', 'run02/a.raw'] and result['files']['deleted'] == []
    assert Path(os.path.join(w.dest_dir, 'run02', 'a.raw')).read_text(encoding='utf-8') == '2'
    assert [cmd[-1] for cmd in fake_copy.commands] == [os.path.join(w.dest_dir, 'run01'),
                                                       os.path.join(w.dest_dir, 'run02')]


def test_wildcard_source_without_matches(worker, fake_copy, tmp_path) -> None:
    """A wildcard matching nothing fails the transfer."""
    result = worker(sourceDir=f'{tmp_path}/run*').transfer_from_source(None)
    assert result == {'verdict': False, 'reason': f'No source directories found matching: {tmp_path}/run*',
                      'files': []}


def test_unknown_transfer_type(worker) -> None:
    """An unknown transfer type fails before anything is mounted."""
    assert worker(transferType=9).transfer_from_source(None) == {'verdict': False, 'reason': 'Unknown transfer type'}


def test_listing_failure_copies_nothing(worker, fake_copy, tmp_path) -> None:
    """Every source is listed before anything is copied; a failed listing fails the transfer (#206)."""
    result = worker(sourceDir=str(tmp_path / 'missing')).transfer_from_source(None)
    assert not result['verdict'] and result['reason'].startswith('Unable to list source files: Source directory')
    assert fake_copy.commands == []


def test_stopped_while_listing(worker, fake_copy, tmp_path) -> None:
    """Stopped while listing: nothing copied or deleted (#473)."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path / 'src'), syncFromSource=1)
    w.stop = True
    result = w.transfer_from_source(None)
    assert result == {'verdict': True, 'stopped': True, 'files': {'new': [], 'updated': [], 'exclude': [],
                                                                  'deleted': []}}
    assert fake_copy.commands == []


def test_failed_copy_returns_what_was_copied(worker, fake_copy, tmp_path) -> None:
    """A failed copy fails the transfer, but returns the files copied, for the hooks (#230, #239)."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    w = worker(sourceDir=str(tmp_path / 'src'))
    os.makedirs(w.dest_dir)
    fake_copy.fail = 'rsync error: some files could not be transferred (code 23)'

    result = w.transfer_from_source(None)

    assert result['verdict'] is False and result['reason'].startswith('Transfer failed: ')
    assert result['files']['new'] == ['a.raw']


def test_file_list_that_cant_be_written(worker, fake_copy, tmp_path, monkeypatch) -> None:
    """A source whose list can't be written fails the transfer instead of being skipped (#238)."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    monkeypatch.setattr(cst_run, 'write_list_file', lambda files, path: False)
    result = worker(sourceDir=str(tmp_path / 'src')).transfer_from_source(None)
    assert result['reason'] == f"Unable to write the file list for {tmp_path / 'src'}"


def test_smb_transfer(worker, fake_copy, monkeypatch) -> None:
    """The share is mounted and copied from its mount point."""
    def mount(cfg, mntpoint, version):
        _tree(Path(mntpoint), {'data/a.raw': 'a'})
        return True, ''

    monkeypatch.setattr(cst_run, 'detect_smb_version', lambda cfg: ('2.1', ''))
    monkeypatch.setattr(cst_run, 'mount_smb_share', mount)
    w = worker(transferType=3)
    os.makedirs(w.dest_dir)

    result = w.transfer_from_source(None)

    assert result['files']['new'] == ['a.raw']
    assert fake_copy.commands[0][-2].endswith('/mntpoint/data/')


def test_smb_mount_fails(worker, monkeypatch) -> None:
    """A share that won't mount fails with mount's error."""
    monkeypatch.setattr(cst_run, 'detect_smb_version', lambda cfg: ('2.1', ''))
    monkeypatch.setattr(cst_run, 'mount_smb_share', lambda *args: (False, 'mount error(13)'))
    assert worker(transferType=3).transfer_from_source(None) == {
        'verdict': False, 'reason': 'Failed to mount SMB share — mount error(13)'}


def test_ftp_transfer(worker, fake_copy, monkeypatch) -> None:
    """The source directory is mounted (#209) and listed with rclone (#208)."""
    def mount(cfg, tmpdir, config, mount_base):
        mntpoint = os.path.join(tmpdir, 'mntpoint')
        _tree(Path(mntpoint), {'a.raw': 'a'})
        return True, mntpoint

    monkeypatch.setattr(cst_run, 'prepare_ftp_config', lambda cfg, tmpdir: (True, 'rclone.conf'))
    monkeypatch.setattr(cst_run, 'prepare_ftp_mount', mount)
    monkeypatch.setattr(cst_run, 'list_ftp_source', lambda *args: (True, [('a.raw', 1, 1.7e9)]))
    w = worker(transferType=5)
    os.makedirs(w.dest_dir)

    assert w.transfer_from_source(None)['files']['new'] == ['a.raw']
    assert fake_copy.commands[0][-2].endswith('/mntpoint/')


@pytest.mark.parametrize('config, mount, reason', [
    ((False, 'ftpPass not available'), None, 'ftpPass not available'),
    ((True, 'cfg'), (False, 'fusermount: not found'), 'Failed to mount FTP server — fusermount: not found'),
])
def test_ftp_setup_failures(worker, monkeypatch, config, mount, reason) -> None:
    """No password, or a mount that fails."""
    monkeypatch.setattr(cst_run, 'prepare_ftp_config', lambda cfg, tmpdir: config)
    monkeypatch.setattr(cst_run, 'prepare_ftp_mount', lambda *args: mount)
    assert worker(transferType=5).transfer_from_source(None)['reason'] == reason


def test_rsync_transfer(worker, fake_copy, fake_run) -> None:
    """The password goes in a private file, given to rsync with --password-file."""
    fake_run.on('rsync', stdout='-rw-r--r--  10 2026/10/22 10:00:00 a.raw\n')
    w = worker(transferType=2)
    os.makedirs(w.dest_dir)

    assert w.transfer_from_source(None)['files']['new'] == ['a.raw']

    cmd = fake_copy.commands[0]
    password_arg = next(arg for arg in cmd if arg.startswith('--password-file='))
    assert fake_run.calls[0].files[password_arg.split('=', 1)[1]] == 'rsync-pw'
    assert cmd[-2] == 'rsync://survey@host/module/data/'
    fake_run.assert_not_in_commands('rsync-pw')


def test_rsync_transfer_without_a_password(worker) -> None:
    """No password from the web app (worker token) fails the transfer."""
    assert worker(transferType=2, rsyncPass=None).transfer_from_source(None)['reason'].startswith(
        'rsyncPass not available')


def test_rsync_password_file_cant_be_written(worker, monkeypatch) -> None:
    """A password file that cannot be written fails the transfer."""
    monkeypatch.setattr(cst_run.os, 'chmod', Mock(side_effect=PermissionError('denied')))
    assert worker(transferType=2).transfer_from_source(None)['reason'] == 'Error writing rsync password file'


def test_ssh_transfer(worker, fake_copy, fake_run, monkeypatch) -> None:
    """Copied with rsync -e ssh through sshpass; macOS servers are detected first."""
    monkeypatch.setattr(cst_run, 'check_darwin', lambda cfg: False)
    fake_run.on('sshpass', stdout='-rw-r--r--  10 2026/10/22 10:00:00 a.raw\n')
    w = worker(transferType=4)
    os.makedirs(w.dest_dir)

    assert w.transfer_from_source(None)['files']['new'] == ['a.raw']
    cmd = fake_copy.commands[0]
    assert cmd[:2] == ['sshpass', '-f'] and ['-e', 'ssh'] == cmd[cmd.index('-e'):cmd.index('-e') + 2]
    assert cmd[-2] == 'survey@host:/data/'


# --- Job setup ----------------------------------------------------------------

def _job(**payload):
    """A Gearman job with the given payload."""
    payload.setdefault('collectionSystemTransfer', {'collectionSystemTransferID': 3})
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task='runCollectionSystemTransfer')


@pytest.fixture
def job_worker(monkeypatch, fake_ovdm, warehouse):
    """A worker whose job runs up to the task: what _run_job() set up is recorded."""
    w = make_worker(monkeypatch, fake_ovdm, warehouse)
    fake_ovdm.get_collection_system_transfer.return_value = dict(CST_DEFAULTS)
    fake_ovdm.get_system_status.return_value = 'On'
    fake_ovdm.get_lowering_id.return_value = None
    monkeypatch.setattr(cst_run, 'acquire_transfer_lock', lambda kind, transfer_id: 'lock')
    monkeypatch.setattr(cst_run, 'release_transfer_lock', Mock())
    monkeypatch.setattr(cst_run.python3_gearman.GearmanWorker, 'on_job_execute',
                        lambda self, job: json.dumps({'ran': True}))
    monkeypatch.setattr(cst_run.python3_gearman.GearmanWorker, 'send_job_complete',
                        lambda self, job, result: result)
    return w


def _result(text):
    """A job's JSON result."""
    return json.loads(text)


def test_job_runs_with_the_payloads_settings(job_worker, fake_ovdm, warehouse) -> None:
    """The payload's cruise and settings override the current ones; the lock is released after."""
    result = job_worker.on_job_execute(_job(cruiseID='OTHER01', collectionSystemTransfer={
        'collectionSystemTransferID': 3, 'sourceDir': '/data/{cruiseID}'}))

    assert _result(result) == {'ran': True}
    assert job_worker.cruise_id == 'OTHER01' and job_worker.source_dir == '/data/OTHER01'
    assert job_worker.dest_dir == str(warehouse.base_dir / 'OTHER01' / 'SCS')
    cst_run.release_transfer_lock.assert_called_once_with('lock')
    assert job_worker.transfer_lock is None


def test_job_for_a_transfer_already_running_is_ignored(job_worker, monkeypatch, fake_ovdm) -> None:
    """Another job holds the lock (#478): ignored, and the status is left alone."""
    monkeypatch.setattr(cst_run, 'acquire_transfer_lock', lambda kind, transfer_id: None)
    result = _result(job_worker.on_job_execute(_job()))
    assert result['parts'] == [{'partName': 'Transfer in-Progress', 'result': 'Ignore', 'reason': IN_PROGRESS_REASON}]
    fake_ovdm.set_idle_collection_system_transfer.assert_not_called()
    fake_ovdm.set_error_collection_system_transfer.assert_not_called()


def test_job_that_cant_lock(job_worker, monkeypatch, fake_ovdm) -> None:
    """A lock that cannot be taken fails the job and sets the error."""
    def no_lock(kind, transfer_id):
        raise OSError('Read-only file system')

    monkeypatch.setattr(cst_run, 'acquire_transfer_lock', no_lock)
    result = _result(job_worker.on_job_execute(_job()))
    assert result['parts'][-1]['reason'] == 'Unable to lock the transfer: Read-only file system'
    fake_ovdm.set_error_collection_system_transfer.assert_called_once()


@pytest.mark.parametrize('status, enable', [('Off', 1), ('On', 0)])
def test_disabled_job_is_ignored(job_worker, fake_ovdm, status, enable) -> None:
    """System Status Off, or the transfer disabled: ignored."""
    fake_ovdm.get_system_status.return_value = status
    fake_ovdm.get_collection_system_transfer.return_value = {**CST_DEFAULTS, 'enable': enable}
    assert _result(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == 'Transfer is disabled'


def test_job_with_unparseable_payload(job_worker) -> None:
    """A payload that is not JSON fails the job."""
    job = SimpleNamespace(data='not json', handle='H:1', task='runCollectionSystemTransfer')
    assert _result(job_worker.on_job_execute(job))['parts'][-1]['reason'] == 'Failed to parse current job payload'


def test_job_for_an_unknown_transfer(job_worker, fake_ovdm) -> None:
    """A transfer the API does not return fails the job."""
    fake_ovdm.get_collection_system_transfer.return_value = None
    assert _result(job_worker.on_job_execute(_job()))['parts'][-1]['partName'] == 'Retrieve collection system transfer'


@pytest.mark.parametrize('settings', [{'cruiseOrLowering': 1}, {'destDir': 'Video/{loweringID}'}])
def test_lowering_transfer_needs_a_lowering(job_worker, fake_ovdm, settings) -> None:
    """Lowering-level transfers, or {loweringID} in destDir, need a lowering."""
    fake_ovdm.get_collection_system_transfer.return_value = {**CST_DEFAULTS, **settings}
    assert _result(job_worker.on_job_execute(_job(loweringID='')))['parts'][-1]['reason'] == 'Lowering ID is undefined'


def test_cruise_time_bounds(job_worker, fake_ovdm) -> None:
    """useStartDate limits the data to the cruise's dates, to the end of its last minute."""
    fake_ovdm.get_collection_system_transfer.return_value = {**CST_DEFAULTS, 'useStartDate': 1}
    fake_ovdm.get_cruise_start_date.return_value = '2026/10/01 00:00'
    fake_ovdm.get_cruise_end_date.return_value = '2026/10/20 12:00'
    job_worker.on_job_execute(_job())
    assert (job_worker.data_start_date, job_worker.data_end_date) == ('2026/10/01 00:00', '2026/10/20 12:00:59')


def test_lowering_time_bounds_without_an_end(job_worker, fake_ovdm) -> None:
    """A lowering still going has no end to its window."""
    fake_ovdm.get_collection_system_transfer.return_value = {**CST_DEFAULTS, 'useStartDate': 1,
                                                             'cruiseOrLowering': 1}
    fake_ovdm.get_lowering_start_date.return_value = '2026/10/22 09:00'
    fake_ovdm.get_lowering_end_date.return_value = ''
    job_worker.on_job_execute(_job(loweringID='DIVE01'))
    assert (job_worker.data_start_date, job_worker.data_end_date) == ('2026/10/22 09:00', '9999/12/31 23:59:59')


def test_staleness_ends_the_window_before_now(job_worker, fake_ovdm) -> None:
    """With staleness, files newer than now minus the staleness aren't transferred yet."""
    fake_ovdm.get_collection_system_transfer.return_value = {**CST_DEFAULTS, 'useStartDate': 1, 'staleness': 300}
    fake_ovdm.get_cruise_start_date.return_value = None
    fake_ovdm.get_cruise_end_date.return_value = None
    job_worker.on_job_execute(_job())
    assert job_worker.data_start_date == '1970/01/01 00:00'
    assert job_worker.data_end_date < '9999' and job_worker.data_end_date.startswith('20')


# --- Job outcome --------------------------------------------------------------

def _done(parts, files=None):
    """A job result with the given parts and files."""
    return json.dumps({'parts': parts, 'files': files or {'new': [], 'updated': [], 'exclude': []}})


def test_passed_job_sets_idle_and_runs_the_hooks(job_worker, fake_ovdm, fake_gearman) -> None:
    """New, updated and deleted files go to the hook tasks with paths in the cruise directory."""
    fake_ovdm.config['hooks']['runCollectionSystemTransfer'] = ['updateDataDashboard', 'updateMD5Summary']
    job_worker.on_job_complete(_job(), _done([{'partName': 'Transfer Files', 'result': 'Pass'}],
                                             {'new': ['a.raw'], 'updated': ['b.raw'], 'deleted': ['sub/../c.raw']}))

    fake_ovdm.set_idle_collection_system_transfer.assert_called_once_with(3)
    assert fake_gearman.tasks() == ['updateDataDashboard', 'updateMD5Summary']
    assert fake_gearman.jobs[0][1] == {'cruiseID': 'TEST001', 'collectionSystemTransferID': 3, 'files': {
        'new': ['SCS/a.raw'], 'updated': ['SCS/b.raw'], 'deleted': ['SCS/c.raw']}}


def test_passed_job_without_files_runs_no_hooks(job_worker, fake_ovdm, fake_gearman) -> None:
    """No new, updated or deleted files: no hooks."""
    fake_ovdm.config['hooks']['runCollectionSystemTransfer'] = ['updateDataDashboard']
    job_worker.on_job_complete(_job(), _done([{'partName': 'Transfer Files', 'result': 'Pass'}]))
    assert fake_gearman.jobs == [] and fake_ovdm.set_idle_collection_system_transfer.called


def test_failed_job_sets_error_and_still_hooks_what_was_copied(job_worker, fake_ovdm, fake_gearman) -> None:
    """A failed transfer's copied files still reach the hooks (#239); the status is error, not idle."""
    fake_ovdm.config['hooks']['runCollectionSystemTransfer'] = ['updateDataDashboard']
    job_worker.on_job_complete(_job(), _done([{'partName': 'Transfer Files', 'result': 'Fail', 'reason': 'boom'}],
                                             {'new': ['a.raw'], 'updated': [], 'exclude': []}))
    fake_ovdm.set_error_collection_system_transfer.assert_called_once_with(3, 'boom')
    fake_ovdm.set_idle_collection_system_transfer.assert_not_called()
    assert fake_gearman.tasks() == ['updateDataDashboard']


def test_ignored_job_leaves_the_status_alone(job_worker, fake_ovdm) -> None:
    """An ignored job doesn't change the transfer's status."""
    job_worker.on_job_complete(_job(), _done([{'partName': 'x', 'result': 'Ignore', 'reason': 'disabled'}]))
    fake_ovdm.set_idle_collection_system_transfer.assert_not_called()
    fake_ovdm.set_error_collection_system_transfer.assert_not_called()


def test_crashed_job_reports_where(job_worker, fake_ovdm, monkeypatch) -> None:
    """A crash sets the error with the exception and the line that raised it."""
    monkeypatch.setattr(cst_run.python3_gearman.GearmanWorker, 'on_job_exception', lambda self, job, info: 'crashed')
    job_worker.send_job_data = Mock()
    try:
        raise KeyError('destDir')
    except KeyError:
        assert job_worker.on_job_exception(_job(), sys.exc_info()) == 'crashed'

    reason = fake_ovdm.set_error_collection_system_transfer.call_args.args[1]
    assert reason.startswith("Worker crashed: KeyError: 'destDir' (test_cst_transfer.py, line ")
    assert json.loads(job_worker.send_job_data.call_args.args[1])[0]['partName'] == 'Worker crashed'


def test_crash_without_a_traceback(job_worker, fake_ovdm, monkeypatch) -> None:
    """A crash without exception details still sets an error."""
    monkeypatch.setattr(cst_run.python3_gearman.GearmanWorker, 'on_job_exception', lambda self, job, info: None)
    job_worker.send_job_data = Mock()
    job_worker.on_job_exception(_job(), (None, None, None))
    assert fake_ovdm.set_error_collection_system_transfer.call_args.args[1] == \
        'Worker crashed: UnknownError (unknown, line ?)'


def test_stop_and_quit(job_worker, monkeypatch) -> None:
    """Stop sets the flag; quit also shuts the worker down."""
    job_worker.stop_task()
    assert job_worker.stop is True
    job_worker.stop = False
    monkeypatch.setattr(job_worker, 'shutdown', Mock())
    job_worker.quit_worker()
    assert job_worker.stop is True and job_worker.shutdown.called


# --- The task -----------------------------------------------------------------

@pytest.fixture
def task_worker(worker, fake_ovdm, tmp_path, monkeypatch):
    """A worker for a local source in tmp_path/src, with log files in tmp_path/logs."""
    monkeypatch.setattr(cst_run.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(cst_run, 'set_owner_group_permissions', Mock(return_value={'verdict': True}))
    fake_ovdm.get_transfer_log_dir.return_value = str(tmp_path / 'logs')
    (tmp_path / 'src').mkdir()
    w = worker(sourceDir=str(tmp_path / 'src'), includeFilter='*.raw')
    os.makedirs(w.dest_dir)
    return w


def _parts(result):
    """Each part of a task result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


def test_task_transfers_and_writes_the_logs(task_worker, fake_copy, fake_ovdm, tmp_path) -> None:
    """A successful transfer writes the transfer log (new, updated) and the exclude log."""
    _tree(tmp_path / 'src', {'a.raw': 'a', 'b.csv': 'b'})

    result = cst_run.task_run_collection_system_transfer(task_worker, _job())

    assert _parts(result) == [('Transfer In-Progress', 'Pass'), ('Transfer Enabled', 'Pass'), ('Source Test', 'Pass'),
                              ('Destination Test', 'Pass'), ('Transfer Files', 'Pass'),
                              ('Setting file/directory ownership/permissions', 'Pass'),
                              ('Write transfer logfile', 'Pass'), ('Write exclude logfile', 'Pass')]
    fake_ovdm.set_running_collection_system_transfer.assert_called_once()
    log = json.loads((tmp_path / 'logs' / 'TEST001_SCS_20261022T100000Z.log').read_text())
    assert log == {'new': ['a.raw'], 'updated': []}
    assert json.loads((tmp_path / 'logs' / 'TEST001_SCS_Exclude.log').read_text()) == {'exclude': ['b.csv']}


def test_task_with_nothing_new_writes_only_the_exclude_log(task_worker, fake_copy, tmp_path) -> None:
    """Without new or updated files, only the exclude log is written."""
    result = cst_run.task_run_collection_system_transfer(task_worker, _job())
    assert _parts(result)[-1] == ('Write exclude logfile', 'Pass')
    assert ('Write transfer logfile', 'Pass') not in _parts(result)
    assert not list((tmp_path / 'logs').glob('*Z.log'))


def test_task_source_test_fails(task_worker, monkeypatch) -> None:
    """A failed source test ends the task with the test's reason."""
    monkeypatch.setattr(cst_run, 'test_cst_source', lambda cfg, source: [
        {'partName': 'Source directory', 'result': 'Fail', 'reason': 'Unable to find source directory'}])
    result = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))
    assert result['parts'][-1] == {'partName': 'Source Test', 'result': 'Fail',
                                   'reason': 'Unable to find source directory'}


def test_task_destination_missing(task_worker) -> None:
    """A missing destination ends the task."""
    os.rmdir(task_worker.dest_dir)
    assert _parts(cst_run.task_run_collection_system_transfer(task_worker, _job()))[-1] == ('Destination Test', 'Fail')


def test_task_failed_transfer_sets_ownership_of_what_was_copied(task_worker, fake_copy, tmp_path) -> None:
    """Copied files still get their ownership set and are returned for the hooks (#239)."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    fake_copy.fail = 'code 23'

    result = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))

    assert result['parts'][-1]['partName'] == 'Transfer Files' and result['parts'][-1]['result'] == 'Fail'
    assert result['files']['new'] == ['a.raw']
    cst_run.set_owner_group_permissions.assert_called_once_with('survey', task_worker.dest_dir)


def test_task_stopped_keeps_the_last_logs(task_worker, tmp_path, monkeypatch) -> None:
    """Stopped while listing: Transfer Files passes and the logs of the last full run stay (#473)."""
    monkeypatch.setattr(task_worker, 'transfer_from_source', lambda job: {'verdict': True, 'stopped': True,
                                                                          'files': {}})
    assert _parts(cst_run.task_run_collection_system_transfer(task_worker, _job()))[-1] == ('Transfer Files', 'Pass')
    assert not (tmp_path / 'logs').exists()


@pytest.mark.parametrize('failing_call, part', [
    (1, 'Setting file/directory ownership/permissions'),
    (2, 'Set OpenVDM config file ownership/permissions'),
    (3, 'Set transfer logfile ownership/permissions'),
])
def test_task_ownership_failures(task_worker, fake_copy, tmp_path, monkeypatch, failing_call, part) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Ownership of the files, the transfer log, or the exclude log."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    calls = []

    def perms(user, path):
        calls.append(path)
        return {'verdict': len(calls) != failing_call, 'reason': 'chown failed'}

    monkeypatch.setattr(cst_run, 'set_owner_group_permissions', perms)
    assert _parts(cst_run.task_run_collection_system_transfer(task_worker, _job()))[-1] == (part, 'Fail')


@pytest.mark.parametrize('failing_call, part', [(1, 'Write transfer logfile'), (2, 'Write exclude logfile')])
def test_task_log_write_failures(task_worker, fake_copy, tmp_path, monkeypatch, failing_call, part) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """The transfer log, or the exclude log, that cannot be written."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    calls = []
    monkeypatch.setattr(cst_run, 'output_json_data_to_file', lambda path, data: calls.append(path) or {
        'verdict': len(calls) != failing_call, 'reason': 'disk full'})
    assert _parts(cst_run.task_run_collection_system_transfer(task_worker, _job()))[-1] == (part, 'Fail')


# --- End to end, with real rsync ----------------------------------------------

needs_gnu_rsync = pytest.mark.skipif(not gnu_rsync(), reason='needs GNU rsync 3 (macOS has openrsync)')


@needs_gnu_rsync
def test_real_local_transfer(task_worker, fake_ovdm, tmp_path) -> None:
    """A real rsync copies new and then updated files, and reports which were which."""
    _tree(tmp_path / 'src', {'a.raw': 'one', 'sub/b.raw': 'two', 'skip.csv': 'x'})

    first = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))
    assert first['parts'][-1]['result'] == 'Pass'
    assert sorted(first['files']['new']) == ['a.raw', 'sub/b.raw'] and first['files']['exclude'] == ['skip.csv']
    assert Path(os.path.join(task_worker.dest_dir, 'sub', 'b.raw')).read_text(encoding='utf-8') == 'two'

    (tmp_path / 'src' / 'a.raw').write_text('one, longer now')
    second = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))
    assert second['files']['new'] == [] and second['files']['updated'] == ['a.raw']


@needs_gnu_rsync
def test_real_sync_from_source_deletes(worker, fake_ovdm, tmp_path, monkeypatch) -> None:
    """With Sync from source, a file deleted from the source is deleted from the destination."""
    monkeypatch.setattr(cst_run.time, 'sleep', lambda seconds: None)
    _tree(tmp_path / 'src', {'a.raw': 'a', 'b.raw': 'b'})
    w = worker(sourceDir=str(tmp_path / 'src'), syncFromSource=1)
    os.makedirs(w.dest_dir)
    w.transfer_from_source(None)

    os.remove(tmp_path / 'src' / 'b.raw')
    result = w.transfer_from_source(None)
    assert result['files']['deleted'] == ['b.raw'] and os.listdir(w.dest_dir) == ['a.raw']


def test_task_failed_transfer_ownership_failure_is_logged(task_worker, fake_copy, tmp_path, monkeypatch, caplog) -> None:
    """After a failed copy, an ownership failure is logged; the transfer's failure is what's reported."""
    _tree(tmp_path / 'src', {'a.raw': 'a'})
    fake_copy.fail = 'code 23'
    monkeypatch.setattr(cst_run, 'set_owner_group_permissions', Mock(return_value={'verdict': False, 'reason': 'x'}))
    result = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))
    assert result['parts'][-1]['partName'] == 'Transfer Files'
    assert 'Error setting destination directory file/directory ownership' in caplog.text


def test_task_reports_updated_and_deleted_files(task_worker, monkeypatch) -> None:
    """Updated and deleted files are returned with the result."""
    files = {'new': [], 'updated': ['a.raw'], 'exclude': [], 'deleted': ['b.raw']}
    monkeypatch.setattr(task_worker, 'transfer_from_source', lambda job: {'verdict': True, 'files': files})
    result = json.loads(cst_run.task_run_collection_system_transfer(task_worker, _job()))
    assert result['files'] == files and result['parts'][-1] == {'partName': 'Write exclude logfile',
                                                                'result': 'Pass'}
