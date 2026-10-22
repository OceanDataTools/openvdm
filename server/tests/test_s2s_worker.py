"""Tests for the ship-to-shore transfer worker (#510).

The ship-to-shore transfer sends the files the enabled ship-to-shore
transfers select, highest priority first, with rsync over SSH or rclone to a
``remote:path``. The copy (``run_transfer_command``) is replaced.
"""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib.transfer_jobs import IN_PROGRESS_REASON
from server.lib.transfer_utils import TransferCommandError
from server.workers import run_ship_to_shore_transfer as s2s_run

SSDW = {
    'cruiseDataTransferID': 4, 'name': 'SSDW', 'longName': 'Shoreside Data Warehouse', 'transferType': 4,
    'destDir': '/ssdw', 'enable': 1, 'bandwidthLimit': 128, 'syncToDest': 0, 'skipEmptyDirs': 1,
    'skipEmptyFiles': 0, 'sshServer': 'shore.example.org', 'sshUser': 'survey', 'sshUseKey': 0,
    'sshPass': 'ssh-pw',
}


def _s2s(priority, include, collection_system=0, extra_directory=0, enable=1) -> dict:
    """A ship-to-shore transfer, as the API returns it (strings)."""
    return {'priority': str(priority), 'includeFilter': include, 'collectionSystem': str(collection_system),
            'extraDirectory': str(extra_directory), 'enable': str(enable)}


@pytest.fixture
def worker(monkeypatch, fake_ovdm, warehouse):
    """Return a function making a worker set up as _run_job() leaves it."""
    monkeypatch.setattr(s2s_run, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_required_ship_to_shore_transfers.return_value = []
    fake_ovdm.get_ship_to_shore_transfers.return_value = []

    def make(lowerings=(), **cfg):
        w = s2s_run.OVDMGearmanWorker()
        w.send_job_status = Mock()
        w.cruise_data_transfer = {**SSDW, **cfg}
        w.cruise_id = warehouse.cruise_id
        w.lowerings = list(lowerings)
        w.shipboard_data_warehouse_config = warehouse.config
        w.cruise_dir = str(warehouse.cruise_dir)
        w.transfer_start_date = '20261022T100000Z'
        return w

    return make


def _tree(root, paths):
    """Create files under root."""
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text('x')


# --- Selecting the files ------------------------------------------------------

def test_process_batch(tmp_path) -> None:
    """The first priority whose pattern matches; non-ASCII names excluded; others dropped."""
    _tree(tmp_path, ['a.json', 'b.raw', 'café.json', '.DS_Store'])
    os.symlink(tmp_path / 'a.json', tmp_path / 'link.json')
    filters = {'1': [f'{tmp_path}/*.json'], '2': [f'{tmp_path}/*']}
    batch = [str(tmp_path / name) for name in ('a.json', 'b.raw', 'café.json', '.DS_Store', 'link.json')]

    assert s2s_run.process_batch(batch, filters) == [
        ('include', str(tmp_path / 'a.json'), '1'), ('include', str(tmp_path / 'b.raw'), '2'),
        ('exclude', str(tmp_path / 'café.json'))]


def test_process_batch_skips_vanished_files(monkeypatch) -> None:
    """A file that disappears while it's checked is skipped."""
    def vanished(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(s2s_run.os.path, 'islink', vanished)
    assert s2s_run.process_batch(['/gone.txt'], {'1': ['*']}) == []


def test_file_list_by_priority(worker, fake_ovdm, warehouse) -> None:
    """Files are sent highest priority (1) first; disabled transfers and unmatched files aren't sent."""
    _tree(warehouse.cruise_dir, ['TEST001_summary.txt', 'track.kml', 'big.raw', 'notes.txt'])
    fake_ovdm.get_required_ship_to_shore_transfers.return_value = [_s2s(1, '{cruiseID}_summary.txt')]
    fake_ovdm.get_ship_to_shore_transfers.return_value = [_s2s(3, '*.kml'), _s2s(2, 'big.raw', enable=0)]

    files = worker().build_filelist()['files']

    assert files == {'include': ['TEST001_summary.txt', 'track.kml'], 'new': [], 'updated': [], 'exclude': []}


def test_file_list_from_collection_systems_and_extra_directories(worker, fake_ovdm, warehouse) -> None:
    """Patterns are relative to the source's directory; lowering-level ones to each lowering's."""
    _tree(warehouse.cruise_dir, ['SCS/nav.csv', 'SCS/raw.dat', 'Vehicle/DIVE01/Video/clip.jpg',
                                 'Vehicle/DIVE02/Video/clip.jpg', 'Products/map.png', 'other.csv'])
    sources = {'1': {'cruiseOrLowering': '0', 'destDir': 'SCS'}, '2': {'cruiseOrLowering': '1', 'destDir': 'Video'}}
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: sources[str(cst_id)]
    fake_ovdm.get_extra_directory.return_value = {'cruiseOrLowering': '0', 'destDir': 'Products'}
    fake_ovdm.get_ship_to_shore_transfers.return_value = [
        _s2s(1, '*.csv', collection_system=1), _s2s(2, '*.jpg', collection_system=2),
        _s2s(3, '*.png', extra_directory=7)]

    files = worker(lowerings=['DIVE01', 'DIVE02']).build_filelist()['files']

    assert files['include'][0] == 'SCS/nav.csv'
    assert sorted(files['include'][1:3]) == ['Vehicle/DIVE01/Video/clip.jpg', 'Vehicle/DIVE02/Video/clip.jpg']
    assert files['include'][3:] == ['Products/map.png']


def test_file_list_lowering_extra_directory(worker, fake_ovdm, warehouse) -> None:
    """A lowering-level extra directory's patterns cover every lowering."""
    _tree(warehouse.cruise_dir, ['Vehicle/DIVE01/Notes/log.txt'])
    fake_ovdm.get_extra_directory.return_value = {'cruiseOrLowering': 1, 'destDir': 'Notes'}
    fake_ovdm.get_ship_to_shore_transfers.return_value = [_s2s(1, '*.txt', extra_directory=3)]
    assert worker(lowerings=['DIVE01']).build_filelist()['files']['include'] == ['Vehicle/DIVE01/Notes/log.txt']


def test_file_list_non_ascii_excluded(worker, fake_ovdm, warehouse) -> None:
    """Non-ASCII names are excluded and listed in the exclude log."""
    _tree(warehouse.cruise_dir, ['café.txt'])
    fake_ovdm.get_ship_to_shore_transfers.return_value = [_s2s(1, '*')]
    assert worker().build_filelist()['files']['exclude'] == ['café.txt']


# --- Copying ------------------------------------------------------------------

class Copy:  # pylint: disable=too-few-public-methods
    """A run_transfer_command() method that records its commands and the file list."""

    def __init__(self):
        self.calls = []
        self.fail = None

    def __call__(self, current_job, command, file_count):
        files_from = next((arg.split('=', 1)[1] for arg in command if arg.startswith('--files-from=')), None)
        if files_from is None and '--files-from' in command:
            files_from = command[command.index('--files-from') + 1]
        with open(files_from, encoding='utf-8') as file:
            listed = file.read().splitlines()
        self.calls.append(SimpleNamespace(command=command, count=file_count, listed=listed))
        if self.fail:
            raise TransferCommandError('rsync', 12, self.fail)
        return ['TEST001/a.txt'], [], []


@pytest.fixture
def copy(monkeypatch):
    """A Copy in place of every worker's run_transfer_command()."""
    fake = Copy()
    monkeypatch.setattr(s2s_run.OVDMGearmanWorker, 'run_transfer_command',
                        lambda self, job, command, count: fake(job, command, count))
    return fake


def test_rsync_over_ssh(worker, fake_ovdm, warehouse, copy, monkeypatch) -> None:
    """Files go under <cruiseID>/ on the server, from the warehouse; the password stays in a file (#426)."""
    _tree(warehouse.cruise_dir, ['a.txt', 'b.txt'])
    fake_ovdm.get_ship_to_shore_transfers.return_value = [_s2s(1, '*.txt')]
    monkeypatch.setattr(s2s_run, 'check_darwin', lambda cfg: False)

    result = worker().transfer_to_destination(None)

    assert result['verdict'] and result['files']['new'] == ['TEST001/a.txt']
    call = copy.calls[0]
    assert call.count == 2 and sorted(call.listed) == ['TEST001/a.txt', 'TEST001/b.txt']
    assert call.command[:2] == ['sshpass', '-f'] and 'ssh-pw' not in call.command
    assert call.command[-2:] == [f"{warehouse.base_dir}/", 'survey@shore.example.org:/ssdw/']
    assert '--bwlimit=128' in call.command and '--protect-args' in call.command


def test_rclone_remote(worker, fake_ovdm, warehouse, copy, monkeypatch) -> None:
    """A remote:path destination is copied with rclone at the remote limits (#465), without sshpass."""
    _tree(warehouse.cruise_dir, ['a.txt'])
    fake_ovdm.get_ship_to_shore_transfers.return_value = [_s2s(1, '*.txt')]
    fake_ovdm.config['rcloneConcurrency'] = {'remote': {'transfers': 2}}
    monkeypatch.setattr('server.lib.connection_utils.get_rclone_remote_type', lambda name: 's3')

    worker(destDir='shore:bucket/ssdw').transfer_to_destination(None)

    command = copy.calls[0].command
    assert command[:4] == ['rclone', 'copy', f'{warehouse.base_dir}/', 'shore:bucket/ssdw/']
    assert command[command.index('--transfers') + 1] == '2' and '--bwlimit' in command


def test_failed_copy(worker, copy, monkeypatch) -> None:
    """A failed copy fails the transfer (#230)."""
    monkeypatch.setattr(s2s_run, 'check_darwin', lambda cfg: True)
    copy.fail = 'connection unexpectedly closed'
    assert worker().transfer_to_destination(None)['reason'].startswith('Transfer failed: ')


def test_include_file_cant_be_written(worker, monkeypatch) -> None:
    """A file list that cannot be written fails the transfer."""
    monkeypatch.setattr(s2s_run, 'write_list_file', lambda files, path: False)
    assert worker().transfer_to_destination(None) == {'verdict': False, 'reason': 'Failed to write include file'}


def test_file_list_failure(worker, monkeypatch) -> None:
    """A file list that fails ends the transfer with its reason."""
    monkeypatch.setattr(s2s_run.OVDMGearmanWorker, 'build_filelist', lambda self: {'verdict': False, 'reason': 'x'})
    assert worker().transfer_to_destination(None) == {'verdict': False, 'reason': 'x'}


def test_destination_test_routes_rclone_remotes(worker, monkeypatch) -> None:
    """A ':' in destDir means an rclone remote."""
    monkeypatch.setattr(s2s_run, 'test_cdt_rclone_destination', lambda cfg: ['rclone'])
    monkeypatch.setattr(s2s_run, 'test_cdt_destination', lambda cfg: ['ssh'])
    assert worker(destDir='shore:x').test_destination() == ['rclone']
    assert worker().test_destination() == ['ssh']


def test_run_transfer_command_reports_progress(worker, monkeypatch) -> None:
    """Progress maps the copy's 0-100% to the job's 5-95%."""
    def fake(cmd, count, progress, should_stop):
        progress(100)
        return {'new': ['a'], 'updated': ['b'], 'deleted': [], 'stopped': False}

    monkeypatch.setattr(s2s_run.transfer_utils, 'run_transfer_command', fake)
    w = worker()
    assert w.run_transfer_command(object(), ['rsync'], 1) == (['a'], ['b'], [])
    assert w.send_job_status.call_args.args[1:] == (95, 100)


def test_build_logfile_dirpath(worker, fake_ovdm, tmp_path) -> None:
    """The transfer log directory is created if missing."""
    fake_ovdm.get_transfer_log_dir.return_value = str(tmp_path / 'logs')
    assert worker().build_logfile_dirpath() == str(tmp_path / 'logs') and (tmp_path / 'logs').is_dir()


# --- Job setup and outcome ----------------------------------------------------

def _job(**payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task='runShipToShoreTransfer')


@pytest.fixture
def job_worker(worker, fake_ovdm, monkeypatch):
    """A worker whose job runs up to the task."""
    w = worker()
    fake_ovdm.get_required_cruise_data_transfer_by_name.return_value = dict(SSDW)
    fake_ovdm.get_ship_to_shore_bw_limit_status.return_value = True
    fake_ovdm.get_system_status.return_value = 'On'
    fake_ovdm.get_lowerings.return_value = ['DIVE01']
    monkeypatch.setattr(s2s_run, 'acquire_transfer_lock', lambda kind, transfer_id: 'lock')
    monkeypatch.setattr(s2s_run, 'release_transfer_lock', Mock())
    monkeypatch.setattr(s2s_run.python3_gearman.GearmanWorker, 'on_job_execute',
                        lambda self, job: json.dumps({'ran': True}))
    monkeypatch.setattr(s2s_run.python3_gearman.GearmanWorker, 'send_job_complete',
                        lambda self, job, result: result)
    return w


def test_job_runs(job_worker, warehouse) -> None:
    """The SSDW transfer and the cruise's lowerings are loaded; the lock is released after."""
    assert json.loads(job_worker.on_job_execute(_job(cruiseID='OTHER01'))) == {'ran': True}
    assert job_worker.cruise_dir == str(warehouse.base_dir / 'OTHER01') and job_worker.lowerings == ['DIVE01']
    assert job_worker.cruise_data_transfer['bandwidthLimit'] == 128
    s2s_run.release_transfer_lock.assert_called_once_with('lock')


@pytest.mark.parametrize('payload, setting, limit', [
    ({}, False, 0), ({'bandwidthLimitStatus': False}, True, 0), ({'bandwidthLimitStatus': True}, False, 128)])
def test_bandwidth_limit_status(job_worker, fake_ovdm, payload, setting, limit) -> None:
    """With the bandwidth limit off (in the payload, else the setting), no limit is applied."""
    fake_ovdm.get_ship_to_shore_bw_limit_status.return_value = setting
    job_worker.on_job_execute(_job(**payload))
    assert job_worker.cruise_data_transfer['bandwidthLimit'] == limit


def test_job_already_running_is_ignored(job_worker, monkeypatch, fake_ovdm) -> None:
    """The ship-to-shore transfer shares the cruise data transfer lock (#478)."""
    kinds = []
    monkeypatch.setattr(s2s_run, 'acquire_transfer_lock', lambda kind, transfer_id: kinds.append(kind))
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == IN_PROGRESS_REASON
    assert kinds == ['cdt']
    fake_ovdm.set_idle_cruise_data_transfer.assert_not_called()


def test_job_that_cant_lock(job_worker, monkeypatch) -> None:
    """A lock that cannot be taken fails the job."""
    def no_lock(kind, transfer_id):
        raise OSError('Permission denied')

    monkeypatch.setattr(s2s_run, 'acquire_transfer_lock', no_lock)
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == \
        'Unable to lock the transfer: Permission denied'


@pytest.mark.parametrize('status, enable', [('Off', 1), ('On', 0)])
def test_disabled_job_is_ignored(job_worker, fake_ovdm, status, enable) -> None:
    """System Status Off, or the transfer disabled."""
    fake_ovdm.get_system_status.return_value = status
    fake_ovdm.get_required_cruise_data_transfer_by_name.return_value = {**SSDW, 'enable': enable}
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == 'Transfer is disabled'


def test_job_without_the_ssdw_transfer(job_worker, fake_ovdm) -> None:
    """Without the required SSDW transfer the job fails."""
    fake_ovdm.get_required_cruise_data_transfer_by_name.return_value = None
    assert json.loads(job_worker.on_job_execute(_job()))['parts'][-1]['reason'] == \
        'Could not find configuration data for cruise data transfer'


def test_job_with_unparseable_payload(job_worker) -> None:
    """A payload that is not JSON fails the job."""
    job = SimpleNamespace(data='not json', handle='H:1', task='runShipToShoreTransfer')
    assert json.loads(job_worker.on_job_execute(job))['parts'][-1]['reason'] == \
        'Could not retrieve data for cruise data transfer from OpenVDM API'


@pytest.mark.parametrize('result, idle, error', [('Pass', True, None), ('Fail', False, 'boom'), ('Ignore', False, None)])
def test_job_outcome(job_worker, fake_ovdm, result, idle, error) -> None:
    """Pass sets idle, Fail sets the error with its reason, Ignore leaves the status alone."""
    job_worker.on_job_complete(_job(), json.dumps({'parts': [{'partName': 'x', 'result': result, 'reason': 'boom'}]}))
    assert fake_ovdm.set_idle_cruise_data_transfer.called is idle
    if error:
        fake_ovdm.set_error_cruise_data_transfer.assert_called_once_with(4, error)


def test_crashed_job_reports_where(job_worker, fake_ovdm, monkeypatch) -> None:
    """A crash sets the error with the exception and the line that raised it."""
    monkeypatch.setattr(s2s_run.python3_gearman.GearmanWorker, 'on_job_exception', lambda self, job, info: None)
    job_worker.send_job_data = Mock()
    try:
        raise OSError('No route to host')
    except OSError:
        job_worker.on_job_exception(_job(), sys.exc_info())
    assert fake_ovdm.set_error_cruise_data_transfer.call_args.args[1].startswith(
        'Worker crashed: OSError: No route to host (test_s2s_worker.py, line ')
    job_worker.on_job_exception(_job(), (None, None, None))
    assert fake_ovdm.set_error_cruise_data_transfer.call_args.args[1].endswith('(unknown, line ?)')


def test_quit_marks_the_transfer_idle(job_worker, fake_ovdm, monkeypatch) -> None:
    """Quitting sets the transfer idle and asks the job to stop."""
    monkeypatch.setattr(s2s_run.python3_gearman.GearmanWorker, 'shutdown', lambda self: 'shut down')
    job_worker.stop_task()
    assert job_worker.stop
    job_worker.quit_worker()
    fake_ovdm.set_idle_cruise_data_transfer.assert_called_once_with(4)


# --- The task -----------------------------------------------------------------

@pytest.fixture
def task_worker(worker, fake_ovdm, tmp_path, monkeypatch):
    """A worker whose destination test passes, with logs in tmp_path/logs."""
    monkeypatch.setattr(s2s_run.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(s2s_run, 'set_owner_group_permissions', Mock(return_value={'verdict': True}))
    fake_ovdm.get_transfer_log_dir.return_value = str(tmp_path / 'logs')
    w = worker()
    monkeypatch.setattr(w, 'test_destination', lambda: [{'partName': 'Write test', 'result': 'Pass'}])
    return w


def _parts(result):
    """Each part of a task result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


def test_task_writes_the_logs_without_the_cruise_prefix(task_worker, monkeypatch, tmp_path, fake_ovdm) -> None:
    """The transfer log lists paths in the cruise, without the copy's <cruiseID>/ prefix."""
    files = {'new': ['TEST001/a.txt'], 'updated': ['TEST001/b.txt'], 'exclude': ['c.txt'], 'deleted': ['TEST001/d']}
    monkeypatch.setattr(task_worker, 'transfer_to_destination', lambda job: {'verdict': True, 'files': files})

    result = s2s_run.task_run_ship_to_shore_transfer(task_worker, _job())

    assert _parts(result) == [('Transfer In-Progress', 'Pass'), ('Transfer Enabled', 'Pass'),
                              ('Destination test', 'Pass'), ('Transfer files', 'Pass'),
                              ('Write transfer logfile', 'Pass'), ('Write exclude logfile', 'Pass')]
    assert json.loads((tmp_path / 'logs' / 'TEST001_SSDW_20261022T100000Z.log').read_text()) == {
        'new': ['a.txt'], 'updated': ['b.txt']}
    assert json.loads((tmp_path / 'logs' / 'TEST001_SSDW_Exclude.log').read_text()) == {'exclude': ['c.txt']}
    fake_ovdm.set_running_cruise_data_transfer.assert_called_once()


def test_task_with_nothing_sent(task_worker, monkeypatch, tmp_path) -> None:
    """Without new or updated files, only the exclude log is written."""
    monkeypatch.setattr(task_worker, 'transfer_to_destination', lambda job: {
        'verdict': True, 'files': {'new': [], 'updated': [], 'exclude': []}})
    assert _parts(s2s_run.task_run_ship_to_shore_transfer(task_worker, _job()))[-1] == ('Write exclude logfile',
                                                                                      'Pass')
    assert not list((tmp_path / 'logs').glob('*Z.log'))


def test_task_destination_test_fails(task_worker, monkeypatch) -> None:
    """A failed destination test ends the task with the test's reason."""
    monkeypatch.setattr(task_worker, 'test_destination', lambda: [
        {'partName': 'SSH connection', 'result': 'Fail', 'reason': 'Permission denied'}])
    result = json.loads(s2s_run.task_run_ship_to_shore_transfer(task_worker, _job()))
    assert result['parts'][-1] == {'partName': 'Connection test', 'result': 'Fail', 'reason': 'Permission denied'}


def test_task_transfer_fails(task_worker, monkeypatch) -> None:
    """A failed transfer ends the task."""
    monkeypatch.setattr(task_worker, 'transfer_to_destination', lambda job: {'verdict': False, 'reason': 'x'})
    assert _parts(s2s_run.task_run_ship_to_shore_transfer(task_worker, _job()))[-1] == ('Transfer files', 'Fail')


@pytest.mark.parametrize('failing, part', [
    ('write1', 'Write transfer logfile'), ('perms1', 'Set OpenVDM config file ownership/permissions'),
    ('write2', 'Write exclude logfile'), ('perms2', 'Set transfer logfile ownership/permissions')])
def test_task_log_failures(task_worker, monkeypatch, failing, part) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Each log write, and setting each log's ownership."""
    monkeypatch.setattr(task_worker, 'transfer_to_destination', lambda job: {
        'verdict': True, 'files': {'new': ['TEST001/a'], 'updated': [], 'exclude': []}})
    counts = {'write': 0, 'perms': 0}

    def step(kind):
        def run(*args):
            counts[kind] += 1
            return {'verdict': f'{kind}{counts[kind]}' != failing, 'reason': 'failed'}
        return run

    monkeypatch.setattr(s2s_run, 'output_json_data_to_file', step('write'))
    monkeypatch.setattr(s2s_run, 'set_owner_group_permissions', step('perms'))
    assert _parts(s2s_run.task_run_ship_to_shore_transfer(task_worker, _job()))[-1] == (part, 'Fail')
