"""Tests for the Stop worker (#512 part 4).

``stop_job.py`` finds the transfer or task with the job's PID, sends it
SIGQUIT and sets it idle. ``os.kill`` is replaced; how Stop uses the transfer
locks (#478) is tested in ``test_transfer_lock.py``.
"""

import errno
import json
import signal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import stop_job


def _job(**payload):
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task='stopJob')


def _parts(result):
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run the task handler, and pass results through."""
    base = stop_job.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute',
                        lambda self, job: self.on_job_complete(job, stop_job.task_stop_job(self, job)))
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def api(fake_ovdm):
    """The fake API: idle jobs have PID 0; CST 3 (PID 1001), CDT 2 (1002), the SSDW (1003) and task
    Rebuild MD5 (1004) are running."""
    fake_ovdm.get_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'Idle CST', 'pid': 0},
        {'collectionSystemTransferID': 3, 'name': 'SCS', 'pid': 1001}]
    fake_ovdm.get_cruise_data_transfers.return_value = [{'cruiseDataTransferID': 2, 'name': 'Backup', 'pid': 1002}]
    fake_ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'pid': 1003}]
    fake_ovdm.get_tasks.return_value = [{'taskID': 7, 'name': 'rebuildMD5Summary', 'pid': 1004}]
    return fake_ovdm


@pytest.fixture
def kill(monkeypatch):
    """Record os.kill() calls; set ``kill.side_effect`` to make it fail."""
    mock = Mock()
    monkeypatch.setattr(stop_job.os, 'kill', mock)
    return mock


@pytest.fixture
def locked(monkeypatch):
    """The (kind, ID)s of the transfers whose lock is held, i.e. which a job is running."""
    held = set()
    monkeypatch.setattr(stop_job, 'transfer_locked', lambda kind, transfer_id: (kind, transfer_id) in held)
    return held


@pytest.fixture
def worker(monkeypatch, api, gearman_base, kill, locked):
    """A Stop worker using the fake API."""
    monkeypatch.setattr(stop_job, 'OpenVDM', lambda: api)
    w = stop_job.OVDMGearmanWorker()
    w.send_job_data = Mock()
    w.shutdown = Mock()
    return w


@pytest.mark.parametrize('pid, info', [
    (1001, {'type': 'collectionSystemTransfer', 'id': 3, 'name': 'SCS', 'pid': 1001}),
    (1002, {'type': 'cruiseDataTransfer', 'id': 2, 'name': 'Backup', 'pid': 1002}),
    (1003, {'type': 'cruiseDataTransfer', 'id': 4, 'name': 'SSDW', 'pid': 1003}),
    (1004, {'type': 'task', 'id': 7, 'name': 'rebuildMD5Summary', 'pid': 1004}),
    (4242, {'type': 'unknown'}),
])
def test_job_info(worker, pid, info) -> None:
    """The job is found by its PID among the transfers (required ones included), then the tasks."""
    worker.on_job_execute(_job(pid=pid))
    assert worker.job_info == info


def test_stop_task(worker, api, kill) -> None:
    """A task is signalled, set idle, and its Manual Stop message posted."""
    result = worker.on_job_execute(_job(pid=1004))
    assert _parts(result) == [('Retrieve Job Info', 'Pass'), ('Verify OpenVDM Job', 'Pass'), ('Stopped Job', 'Pass')]
    kill.assert_called_once_with(1004, signal.SIGQUIT)
    api.set_idle_task.assert_called_once_with(7)
    api.send_msg.assert_called_once_with('Manual Stop of task', 'rebuildMD5Summary')


def test_stop_running_cruise_data_transfer(worker, api, kill, locked) -> None:
    """A running cruise data transfer is signalled; it sets its own status when it ends."""
    locked.add((stop_job.CDT, 2))
    worker.on_job_execute(_job(pid=1002))
    kill.assert_called_once_with(1002, signal.SIGQUIT)
    api.set_idle_cruise_data_transfer.assert_not_called()
    api.send_msg.assert_called_once_with('Manual Stop of transfer', 'Backup')


def test_stop_unknown_job(worker, api, kill) -> None:
    """A PID OpenVDM doesn't know fails, and nothing is signalled."""
    result = json.loads(worker.on_job_execute(_job(pid=4242)))
    assert result['parts'] == [{'partName': 'Verify OpenVDM Job', 'result': 'Fail',
                                'reason': 'Unknown job type: unknown'}]
    kill.assert_not_called()
    api.send_msg.assert_not_called()


def test_process_already_gone(worker, api, kill, caplog) -> None:
    """A task whose process has already ended is still set idle."""
    kill.side_effect = ProcessLookupError(errno.ESRCH, 'No such process')
    result = worker.on_job_execute(_job(pid=1004))
    assert _parts(result)[-1] == ('Stopped Job', 'Pass')
    assert 'Process does not exist: PID 1004' in caplog.text
    api.set_idle_task.assert_called_once_with(7)


def test_bad_payload(worker, kill) -> None:
    """A payload that isn't JSON fails the job; nothing is signalled."""
    result = worker.on_job_execute(SimpleNamespace(data='not json', handle='H:1', task='stopJob'))
    assert _parts(result) == [('Retrieve current job data', 'Fail')]
    kill.assert_not_called()


def test_job_exception(worker) -> None:
    """A crash is reported with where it happened."""
    try:
        raise KeyError('pid')
    except KeyError as err:
        info = (type(err), err, err.__traceback__)
    assert worker.on_job_exception(_job(), info) == 'crashed'
    sent = json.loads(worker.send_job_data.call_args.args[1])
    assert sent[0]['reason'].startswith("KeyError: 'pid' (test_stop_job.py, line ")


def test_stop_and_quit(worker) -> None:
    """Stop stops the current task; quit also shuts the worker down."""
    worker.stop_task()
    assert worker.stop
    worker.quit_worker()
    worker.shutdown.assert_called_once()


@pytest.mark.parametrize('pid', [0, '0', '', None, ' 0 '])
def test_stop_with_no_running_job(worker, api, kill, pid) -> None:
    """Stop for a transfer that has just ended (its PID is now 0), or without a PID, changes nothing:
    it doesn't set another, idle transfer idle or post a message about it (#590)."""
    result = json.loads(worker.on_job_execute(_job(pid=pid) if pid is not None else _job()))
    assert result['parts'] == [{'partName': 'Verify OpenVDM Job', 'result': 'Ignore',
                                'reason': 'No job is running: it may have just finished'}]
    api.get_collection_system_transfers.assert_not_called()
    api.set_idle_collection_system_transfer.assert_not_called()
    api.send_msg.assert_not_called()
    kill.assert_not_called()


def test_kill_fails(worker, api, kill) -> None:
    """A process that can't be signalled (e.g. not permitted) fails the job, and the job isn't
    shown as stopped: not set idle, no "Manual Stop" message (#589)."""
    kill.side_effect = PermissionError(errno.EPERM, 'Operation not permitted')
    result = json.loads(worker.on_job_execute(_job(pid=1004)))
    assert [part['result'] for part in result['parts'] if part['partName'] == 'Stopped Job'] == ['Fail']
    assert 'Operation not permitted' in result['parts'][-1]['reason']
    api.set_idle_task.assert_not_called()
    api.send_msg.assert_not_called()
