"""Tests for the cruise data transfer worker (#510).

The worker counts the files to send with an rsync dry run, then copies the
cruise directory with rsync (rsync servers) or rclone (everything else). The
dry run and ``rclone mkdir`` go through ``fake_run``; the copy itself
(``run_transfer_command``) is replaced, since rclone isn't installed in CI. One
end-to-end test runs the dry run with real rsync, to check the exclude list.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib import connection_utils
from server.lib.transfer_jobs import IN_PROGRESS_REASON
from server.lib.transfer_utils import TransferCommandError
from server.tests.helpers import gnu_rsync
from server.workers import run_cruise_data_transfer as cdt_run

CDT_DEFAULTS = {
    'cruiseDataTransferID': 5, 'name': 'Backup', 'longName': 'Backup drive', 'transferType': 1,
    'destDir': '/mnt/backup', 'localDirIsMountPoint': 0, 'includeOVDMFiles': 1,
    'excludedCollectionSystems': '', 'excludedExtraDirectories': '',
    'syncToDest': 0, 'skipEmptyDirs': 1, 'skipEmptyFiles': 0, 'bandwidthLimit': 0, 'enable': 1,
    'rsyncServer': 'host/module', 'rsyncUser': 'survey', 'rsyncPass': 'rsync-pw',
    'sshServer': 'host', 'sshUser': 'survey', 'sshUseKey': 0, 'sshPass': 'ssh-pw',
    'smbServer': '//nas/share', 'smbDomain': 'WG', 'smbUser': 'survey', 'smbPass': 'smb-pw',
    'ftpServer': 'ftp.example.org', 'ftpUser': 'survey', 'ftpPass': 'ftp-pw',
}

DRY_RUN = 'Number of files: 12\nNumber of regular files transferred: 3\nTotal file size: 1,024 bytes\n'


@pytest.fixture
def worker(monkeypatch, fake_ovdm, warehouse):
    """Return a function making a worker set up as _run_job() leaves it, for the given settings."""
    monkeypatch.setattr(cdt_run, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_lowering_config_fn.return_value = 'lowering_config.json'

    def make(**cfg):
        w = cdt_run.OVDMGearmanWorker()
        w.send_job_status = Mock()
        w.cruise_data_transfer = {**CDT_DEFAULTS, **cfg}
        w.cruise_id = warehouse.cruise_id
        w.shipboard_data_warehouse_config = warehouse.config
        w.cruise_dir = str(warehouse.cruise_dir)
        return w

    return make


class Copy:  # pylint: disable=too-few-public-methods
    """A run_transfer_command() method that records its commands and returns scripted files."""

    def __init__(self):
        self.calls = []
        self.files = (['a.raw'], ['b.raw'], [])
        self.fail = None

    def __call__(self, current_job, command, file_count):
        self.calls.append((command, file_count))
        if self.fail:
            raise TransferCommandError('rclone', 1, self.fail)
        return self.files


@pytest.fixture
def copy(monkeypatch):
    """A Copy in place of every worker's run_transfer_command()."""
    fake = Copy()
    monkeypatch.setattr(cdt_run.OVDMGearmanWorker, 'run_transfer_command',
                        lambda self, job, command, count: fake(job, command, count))
    return fake


# --- Exclude list -------------------------------------------------------------

def test_exclude_list_defaults(worker) -> None:
    """With OpenVDM's files included, only the standard excludes (#259)."""
    excludes = worker().build_exclude_filterlist()
    assert excludes == cdt_run.transfer_exclude_patterns()


def test_exclude_list_without_openvdm_files(worker, warehouse) -> None:
    """The cruise config, MD5 summary and every lowering's config (any lowering ID) are left out."""
    excludes = worker(includeOVDMFiles=0).build_exclude_filterlist()
    assert excludes[:4] == ['cruise_config.json', 'md5_summary.txt', 'md5_summary.md5',
                            os.path.join('Vehicle', '*', 'lowering_config.json')]


def test_exclude_list_excluded_directories(worker, fake_ovdm) -> None:
    """Excluded collection systems and extra directories, cruise- or lowering-level."""
    systems = {'1': {'cruiseOrLowering': 0, 'destDir': 'SCS/{cruiseID}'},
               '2': {'cruiseOrLowering': 1, 'destDir': 'Video/{loweringID}'}}
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: systems[cst_id]
    fake_ovdm.get_extra_directory.side_effect = lambda ed_id: {'cruiseOrLowering': 0, 'destDir': 'Products'}

    excludes = worker(excludedCollectionSystems='1,2,0,', excludedExtraDirectories='7').build_exclude_filterlist()

    assert excludes[:3] == ['SCS/TEST001/**', os.path.join('Vehicle', '*', 'Video/*') + '/**', 'Products/**']


def test_exclude_list_lowering_extra_directory(worker, fake_ovdm) -> None:
    """A lowering-level extra directory is left out of every lowering."""
    fake_ovdm.get_extra_directory.return_value = {'cruiseOrLowering': 1, 'destDir': 'Notes'}
    assert worker(excludedExtraDirectories='3').build_exclude_filterlist()[0] == \
        os.path.join('Vehicle', '*', 'Notes') + '/**'


def test_exclude_list_api_failures_are_warnings(worker, fake_ovdm, caplog) -> None:
    """A collection system or extra directory the API can't return is skipped with a warning."""
    fake_ovdm.get_collection_system_transfer.side_effect = RuntimeError('API down')
    fake_ovdm.get_extra_directory.side_effect = RuntimeError('API down')
    excludes = worker(excludedCollectionSystems='1', excludedExtraDirectories='2').build_exclude_filterlist()
    assert excludes == cdt_run.transfer_exclude_patterns()
    assert 'Could not retrieve collection system transfer 1' in caplog.text
    assert 'Could not retrieve extra directory 2' in caplog.text


def test_exclude_list_non_ascii_files(worker, warehouse) -> None:
    """Files with non-ASCII names are left out, by their path in the cruise directory."""
    (warehouse.cruise_dir / 'SCS').mkdir()
    (warehouse.cruise_dir / 'SCS' / 'café.txt').write_text('x')
    (warehouse.cruise_dir / 'SCS' / 'plain.txt').write_text('x')
    assert os.path.join('SCS', 'café.txt') in worker().build_exclude_filterlist()


# --- Destination test, mkdir and progress -------------------------------------

def test_destination_test_routes_rclone_remotes(worker, monkeypatch) -> None:
    """A ':' in destDir means an rclone remote."""
    monkeypatch.setattr(cdt_run, 'test_cdt_rclone_destination', lambda cfg: ['rclone'])
    monkeypatch.setattr(cdt_run, 'test_cdt_destination', lambda cfg: ['plain'])
    assert worker(destDir='gcs:bucket').test_destination() == ['rclone']
    assert worker(destDir='/mnt/backup').test_destination() == ['plain']


def test_make_cruise_dir(worker, fake_run, caplog) -> None:
    """rclone mkdir <dest>/<cruiseID>; a failure is only logged."""
    w = worker()
    w.make_cruise_dir('remote:backup/', ['--config', '/tmp/c'])
    assert fake_run.calls[0].cmd == ['rclone', 'mkdir', 'remote:backup/TEST001', '--config', '/tmp/c']

    fake_run.on('rclone', 'mkdir', returncode=1, stderr='permission denied')
    w.make_cruise_dir('remote:backup')
    assert 'Error creating cruise directory: permission denied' in caplog.text


def test_run_transfer_command_reports_progress(worker, monkeypatch) -> None:
    """Progress maps the copy's 0-100% to the job's 5-95%."""
    def fake(cmd, count, progress, should_stop):
        progress(50)
        return {'new': ['a'], 'updated': [], 'deleted': ['b'], 'stopped': False}

    monkeypatch.setattr(cdt_run.transfer_utils, 'run_transfer_command', fake)
    w = worker()
    assert w.run_transfer_command(object(), ['rclone'], 1) == (['a'], [], ['b'])
    w.send_job_status.assert_called_once()
    assert w.send_job_status.call_args.args[1:] == (50, 100)


# --- Copying to each type of destination --------------------------------------

def _dry_run(fake_run, output=DRY_RUN, returncode=0, stderr=''):
    """Script the rsync dry run's output and exit code."""
    fake_run.on('rsync', stdout=output, returncode=returncode, stderr=stderr)


def _real_command(copy):
    """The copy command the worker ran."""
    return copy.calls[0][0]


def test_local_destination(worker, fake_run, copy, monkeypatch, warehouse) -> None:
    """Local directories are copied with rclone, at the local limits (#465), then owned by the warehouse user."""
    _dry_run(fake_run)
    perms = Mock(return_value={'verdict': True})
    monkeypatch.setattr(cdt_run, 'set_owner_group_permissions', perms)

    result = worker().transfer_to_destination(None)

    assert result == {'verdict': True, 'files': {'new': ['a.raw'], 'updated': ['b.raw'], 'deleted': [],
                                                 'exclude': []}}
    dry = fake_run.commands('rsync')[0]
    assert '--dry-run' in dry and dry[-2:] == [str(warehouse.cruise_dir), '/mnt/backup/TEST001/']
    assert any(arg.startswith('--exclude-from=') for arg in dry)
    cmd, count = copy.calls[0]
    assert count == 3 and cmd[:4] == ['rclone', 'copy', f'{warehouse.cruise_dir}/', '/mnt/backup/TEST001/']
    assert cmd[cmd.index('--transfers') + 1] == '1' and '--exclude-from' in cmd
    assert fake_run.commands('rclone', 'mkdir') == [['rclone', 'mkdir', '/mnt/backup/TEST001']]
    perms.assert_called_once_with('survey', '/mnt/backup/TEST001')


def test_local_mount_point_destination_keeps_ownership(worker, fake_run, copy, monkeypatch) -> None:
    """A destination on its own drive isn't chowned."""
    _dry_run(fake_run)
    perms = Mock()
    monkeypatch.setattr(cdt_run, 'set_owner_group_permissions', perms)
    worker(localDirIsMountPoint=1).transfer_to_destination(None)
    perms.assert_not_called()


def test_local_destination_ownership_failure(worker, fake_run, copy, monkeypatch) -> None:
    """An ownership failure fails the transfer with its reason."""
    _dry_run(fake_run)
    monkeypatch.setattr(cdt_run, 'set_owner_group_permissions',
                        lambda user, path: {'verdict': False, 'reason': 'chown failed'})
    assert worker().transfer_to_destination(None) == {'verdict': False, 'reason': 'chown failed'}


def test_rclone_remote_destination(worker, fake_run, copy, monkeypatch, tmp_path) -> None:
    """A remote:path destination: the dry run writes locally (#249), the copy gets the remote limits."""
    _dry_run(fake_run)
    monkeypatch.setattr(connection_utils, 'get_rclone_remote_type', lambda name: 's3')
    w = worker(destDir='s3remote:bucket')
    w.ovdm.config['rcloneConcurrency'] = {'remote': {'transfers': 8}}

    w.transfer_to_destination(None)

    assert fake_run.commands('rsync')[0][-1].endswith('/TEST001/')
    assert not fake_run.commands('rsync')[0][-1].startswith('s3remote:')
    cmd = _real_command(copy)
    assert cmd[3] == 's3remote:bucket/TEST001/' and cmd[cmd.index('--transfers') + 1] == '8'


def test_nothing_to_transfer(worker, fake_run, copy) -> None:
    """A dry run counting no files copies nothing."""
    _dry_run(fake_run, output='Number of regular files transferred: 0\n')
    assert worker().transfer_to_destination(None)['files']['new'] == []
    assert copy.calls == []


def test_dry_run_failure(worker, fake_run, copy) -> None:
    """A failed dry run fails the transfer instead of looking like nothing to send (#230)."""
    _dry_run(fake_run, returncode=23, stderr='rsync: [sender] opendir "/x" failed: Permission denied (13)\n')
    result = worker().transfer_to_destination(None)
    assert result['reason'].startswith('Dry run failed: rsync exited with code 23: rsync: [sender] opendir')
    assert copy.calls == []


def test_dry_run_vanished_files_are_fine(worker, fake_run, copy, monkeypatch) -> None:
    """Exit 24 (files vanished during the dry run) still counts."""
    _dry_run(fake_run, returncode=24)
    monkeypatch.setattr(cdt_run, 'set_owner_group_permissions', Mock(return_value={'verdict': True}))
    assert worker().transfer_to_destination(None)['verdict'] is True


def test_failed_copy(worker, fake_run, copy) -> None:
    """A failed copy fails the transfer (#230)."""
    _dry_run(fake_run)
    copy.fail = 'Failed to copy: 1 errors'
    assert worker().transfer_to_destination(None)['reason'].startswith('Transfer failed: ')


def test_exclude_file_cant_be_written(worker, monkeypatch) -> None:
    """An exclude list that cannot be written fails the transfer."""
    monkeypatch.setattr(cdt_run, 'write_list_file', lambda items, path: False)
    assert worker().transfer_to_destination(None) == {'verdict': False, 'reason': 'Failed to write exclude file'}


def test_unknown_transfer_type(worker) -> None:
    """An unknown transfer type fails before anything else."""
    assert worker(transferType=9).transfer_to_destination(None) == {'verdict': False,
                                                                    'reason': 'Unknown Transfer Type'}


def test_smb_destination(worker, fake_run, copy, monkeypatch) -> None:
    """The share is mounted and copied to with rclone, at the local limits."""
    monkeypatch.setattr(cdt_run, 'detect_smb_version', lambda cfg: ('2.1', ''))
    monkeypatch.setattr(cdt_run, 'mount_smb_share', lambda cfg, mntpoint, version: (True, ''))
    _dry_run(fake_run)

    worker(transferType=3, destDir='/backups/').transfer_to_destination(None)

    cmd = _real_command(copy)
    assert cmd[3].endswith('/mntpoint/backups/TEST001/') and cmd[cmd.index('--transfers') + 1] == '1'


def test_smb_mount_fails(worker, monkeypatch) -> None:
    """A share that won't mount fails with mount's error."""
    monkeypatch.setattr(cdt_run, 'detect_smb_version', lambda cfg: (None, 'NT_STATUS_HOST_UNREACHABLE'))
    monkeypatch.setattr(cdt_run, 'mount_smb_share', lambda *args: (False, 'mount error(112)'))
    assert worker(transferType=3).transfer_to_destination(None) == {
        'verdict': False, 'reason': 'Failed to mount SMB share — mount error(112)'}


def test_rsync_destination(worker, fake_run, copy) -> None:
    """The password is in a private file; the dry run doesn't get it, which rsync rejects locally (#249)."""
    _dry_run(fake_run)

    worker(transferType=2, destDir='/backups').transfer_to_destination(None)

    dry = fake_run.commands('rsync')[0]
    assert not any(arg.startswith('--password-file') for arg in dry)
    cmd = _real_command(copy)
    password_arg = next(arg for arg in cmd if arg.startswith('--password-file='))
    assert Path(password_arg.split('=', 1)[1]).parent.name.startswith('openvdm-')
    assert cmd[0] == 'rsync' and cmd[-1] == 'rsync://survey@host/module/backups/'
    assert '--dry-run' not in cmd


def test_ssh_destination(worker, fake_run, copy, monkeypatch) -> None:
    """SSH destinations are copied with rclone through an SFTP remote; macOS changes the dry run."""
    monkeypatch.setattr(cdt_run, 'check_darwin', lambda cfg: True)
    monkeypatch.setattr(cdt_run, 'build_rclone_config_for_ssh', lambda cfg, path: 'host')
    _dry_run(fake_run)

    worker(transferType=4, destDir='/data/backups').transfer_to_destination(None)

    assert '--protect-args' not in fake_run.commands('rsync')[0]
    cmd = _real_command(copy)
    assert cmd[3] == 'host:/data/backups/TEST001/' and '--config' in cmd


def test_ssh_destination_without_a_key(worker, monkeypatch) -> None:
    """A key login with no key fails with what's missing."""
    monkeypatch.setattr(cdt_run, 'check_darwin', lambda cfg: False)

    def no_key(cfg, path):
        raise FileNotFoundError('No SSH key for host')

    monkeypatch.setattr(cdt_run, 'build_rclone_config_for_ssh', no_key)
    assert worker(transferType=4, sshUseKey=1).transfer_to_destination(None) == {
        'verdict': False, 'reason': 'No SSH key for host'}


def test_ftp_destination(worker, fake_run, copy, monkeypatch) -> None:
    """FTP destinations (#199): rclone to <destDir>/<cruiseID> on the server."""
    monkeypatch.setattr(cdt_run, 'prepare_ftp_config', lambda cfg, tmpdir: (True, f'{tmpdir}/rclone.conf'))
    _dry_run(fake_run)

    worker(transferType=5, destDir='/incoming').transfer_to_destination(None)

    cmd = _real_command(copy)
    assert cmd[3] == 'ftp_source:/incoming/TEST001/' and cmd[cmd.index('--config') + 1].endswith('rclone.conf')
    assert fake_run.commands('rclone', 'mkdir')[0][2] == 'ftp_source:/incoming/TEST001'


def test_ftp_destination_setup_fails(worker, monkeypatch) -> None:
    """An FTP setup failure fails the transfer with its reason."""
    monkeypatch.setattr(cdt_run, 'prepare_ftp_config', lambda cfg, tmpdir: (False, 'rclone is not installed'))
    assert worker(transferType=5).transfer_to_destination(None) == {'verdict': False,
                                                                    'reason': 'rclone is not installed'}


@pytest.mark.skipif(not gnu_rsync(), reason='needs GNU rsync 3 (macOS has openrsync)')
def test_real_dry_run_counts_only_what_isnt_excluded(worker, fake_ovdm, warehouse, copy, tmp_path,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                                                     monkeypatch) -> None:
    """With real rsync, excluded collection systems and OpenVDM's files aren't counted."""
    for path in ('SCS/a.raw', 'SCS/b.raw', 'Video/c.mp4', 'cruise_config.json', 'md5_summary.txt',
                 'Vehicle/DIVE01/lowering_config.json', 'Vehicle/DIVE01/notes.txt', 'SCS/.DS_Store'):
        (warehouse.cruise_dir / path).parent.mkdir(parents=True, exist_ok=True)
        (warehouse.cruise_dir / path).write_text('x')
    fake_ovdm.get_collection_system_transfer.return_value = {'cruiseOrLowering': 0, 'destDir': 'Video'}
    monkeypatch.setattr(cdt_run, 'set_owner_group_permissions', Mock(return_value={'verdict': True}))
    # Only the dry run is real: rclone (mkdir and the copy) isn't installed in CI
    monkeypatch.setattr(cdt_run.OVDMGearmanWorker, 'make_cruise_dir', lambda self, dest, args=None: None)
    (tmp_path / 'backup').mkdir()

    worker(destDir=str(tmp_path / 'backup'), includeOVDMFiles=0,
           excludedCollectionSystems='1').transfer_to_destination(None)

    assert copy.calls[0][1] == 3        # SCS/a.raw, SCS/b.raw, Vehicle/DIVE01/notes.txt


# --- Job setup and outcome ----------------------------------------------------

def _job(**payload):
    """A Gearman job with the given payload."""
    payload.setdefault('cruiseDataTransfer', {'cruiseDataTransferID': 5})
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task='runCruiseDataTransfer')


@pytest.fixture
def job_worker(worker, fake_ovdm, monkeypatch):
    """A worker whose job runs up to the task."""
    w = worker()
    fake_ovdm.get_cruise_data_transfer.return_value = dict(CDT_DEFAULTS)
    fake_ovdm.get_system_status.return_value = 'On'
    monkeypatch.setattr(cdt_run, 'acquire_transfer_lock', lambda kind, transfer_id: 'lock')
    monkeypatch.setattr(cdt_run, 'release_transfer_lock', Mock())
    monkeypatch.setattr(cdt_run.python3_gearman.GearmanWorker, 'on_job_execute',
                        lambda self, job: json.dumps({'ran': True}))
    monkeypatch.setattr(cdt_run.python3_gearman.GearmanWorker, 'send_job_complete',
                        lambda self, job, result: result)
    return w


def test_job_runs_with_the_payloads_cruise(job_worker, warehouse) -> None:
    """The payload's cruise sets the cruise directory; the lock is released after."""
    assert json.loads(job_worker.on_job_execute(_job(cruiseID='OTHER01'))) == {'ran': True}
    assert job_worker.cruise_dir == str(warehouse.base_dir / 'OTHER01')
    cdt_run.release_transfer_lock.assert_called_once_with('lock')


def test_job_already_running_is_ignored(job_worker, monkeypatch, fake_ovdm) -> None:
    """Another job holds the lock (#478); the status is left alone."""
    monkeypatch.setattr(cdt_run, 'acquire_transfer_lock', lambda kind, transfer_id: None)
    result = json.loads(job_worker.on_job_execute(_job()))
    assert result['parts'] == [{'partName': 'Transfer In-Progress', 'result': 'Ignore',
                                'reason': IN_PROGRESS_REASON}]
    fake_ovdm.set_idle_cruise_data_transfer.assert_not_called()


def test_job_that_cant_lock(job_worker, monkeypatch, fake_ovdm) -> None:
    """A lock that can't be taken fails the job and sets the error."""
    def no_lock(kind, transfer_id):
        raise OSError('No space left on device')

    monkeypatch.setattr(cdt_run, 'acquire_transfer_lock', no_lock)
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == \
        'Unable to lock the transfer: No space left on device'
    fake_ovdm.set_error_cruise_data_transfer.assert_called_once()


@pytest.mark.parametrize('status, enable', [('Off', 1), ('On', 0)])
def test_disabled_job_is_ignored(job_worker, fake_ovdm, status, enable) -> None:
    """System Status Off, or the transfer disabled."""
    fake_ovdm.get_system_status.return_value = status
    fake_ovdm.get_cruise_data_transfer.return_value = {**CDT_DEFAULTS, 'enable': enable}
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == 'Transfer is disabled'


@pytest.mark.parametrize('data, config, reason', [
    ('not json', CDT_DEFAULTS, 'Could not retrieve data for cruise data transfer from OpenVDM API'),
    (json.dumps({'cruiseDataTransfer': {'cruiseDataTransferID': 5}}), None,
     'Could not find configuration data for cruise data transfer'),
])
def test_job_setup_failures(job_worker, fake_ovdm, data, config, reason) -> None:
    """A payload that isn't JSON, or a transfer the API doesn't return."""
    fake_ovdm.get_cruise_data_transfer.return_value = config
    job = SimpleNamespace(data=data, handle='H:1', task='runCruiseDataTransfer')
    assert json.loads(job_worker.on_job_execute(job))['parts'][-1]['reason'] == reason


@pytest.mark.parametrize('result, idle, error', [
    ('Pass', True, None), ('Fail', False, 'boom'), ('Ignore', False, None)])
def test_job_outcome(job_worker, fake_ovdm, result, idle, error) -> None:
    """Pass sets idle, Fail sets the error with its reason, Ignore leaves the status alone."""
    job_worker.on_job_complete(_job(), json.dumps({'parts': [{'partName': 'x', 'result': result,
                                                              'reason': 'boom'}]}))
    assert fake_ovdm.set_idle_cruise_data_transfer.called is idle
    if error:
        fake_ovdm.set_error_cruise_data_transfer.assert_called_once_with(5, error)
    else:
        fake_ovdm.set_error_cruise_data_transfer.assert_not_called()


def test_crashed_job_reports_where(job_worker, fake_ovdm, monkeypatch) -> None:
    """A crash sets the error with the exception and the line that raised it."""
    monkeypatch.setattr(cdt_run.python3_gearman.GearmanWorker, 'on_job_exception', lambda self, job, info: None)
    job_worker.send_job_data = Mock()
    job_worker.cruise_data_transfer = dict(CDT_DEFAULTS)
    try:
        raise ValueError('bad destDir')
    except ValueError:
        job_worker.on_job_exception(_job(), sys.exc_info())
    assert fake_ovdm.set_error_cruise_data_transfer.call_args.args[1].startswith(
        'Worker crashed: ValueError: bad destDir (test_cdt_worker.py, line ')

    job_worker.on_job_exception(_job(), (None, None, None))
    assert fake_ovdm.set_error_cruise_data_transfer.call_args.args[1] == \
        'Worker crashed: UnknownError (unknown, line ?)'


def test_stop_and_quit(job_worker, monkeypatch) -> None:
    """Stop sets the flag; quit also shuts the worker down."""
    job_worker.stop_task()
    assert job_worker.stop
    monkeypatch.setattr(job_worker, 'shutdown', Mock())
    job_worker.quit_worker()
    assert job_worker.shutdown.called


# --- The task -----------------------------------------------------------------

@pytest.fixture
def task_worker(worker, monkeypatch):
    """A worker for the task, which waits a random 0-2 s first."""
    monkeypatch.setattr(cdt_run.time, 'sleep', lambda seconds: None)
    return worker()


def _parts(result):
    """Each part of a task result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


def test_task(task_worker, monkeypatch, fake_ovdm) -> None:
    """The destination is tested, then the cruise directory copied; the files are returned."""
    monkeypatch.setattr(task_worker, 'test_destination', lambda: [{'partName': 'Write test', 'result': 'Pass'}])
    files = {'new': ['a'], 'updated': ['b'], 'deleted': [], 'exclude': ['c']}
    monkeypatch.setattr(task_worker, 'transfer_to_destination', lambda job: {'verdict': True, 'files': files})

    result = cdt_run.task_run_cruise_data_transfer(task_worker, _job())

    assert _parts(result) == [('Transfer in-Progress', 'Pass'), ('Transfer enabled', 'Pass'),
                              ('Connection test', 'Pass'), ('Transfer files', 'Pass')]
    assert json.loads(result)['files'] == files
    fake_ovdm.set_running_cruise_data_transfer.assert_called_once()


def test_task_connection_test_fails(task_worker, monkeypatch) -> None:
    """A failed destination test ends the task with the test's reason."""
    monkeypatch.setattr(task_worker, 'test_destination', lambda: [
        {'partName': 'Destination directory', 'result': 'Fail', 'reason': 'not mounted'}])
    result = json.loads(cdt_run.task_run_cruise_data_transfer(task_worker, _job()))
    assert result['parts'][-1] == {'partName': 'Connection test', 'result': 'Fail', 'reason': 'not mounted'}


def test_task_transfer_fails(task_worker, monkeypatch) -> None:
    """A failed transfer ends the task with the transfer's reason."""
    monkeypatch.setattr(task_worker, 'test_destination', lambda: [{'partName': 'x', 'result': 'Pass'}])
    monkeypatch.setattr(task_worker, 'transfer_to_destination',
                        lambda job: {'verdict': False, 'reason': 'Transfer failed: disk full'})
    result = json.loads(cdt_run.task_run_cruise_data_transfer(task_worker, _job()))
    assert result['parts'][-1] == {'partName': 'Transfer files', 'result': 'Fail',
                                   'reason': 'Transfer failed: disk full'}
