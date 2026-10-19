"""Tests that Stop leaves a signalled transfer's status to its own job."""

import errno
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import stop_job

SET_IDLE = {
    'collectionSystemTransfer': 'set_idle_collection_system_transfer',
    'cruiseDataTransfer': 'set_idle_cruise_data_transfer',
    'task': 'set_idle_task',
}


def _run(monkeypatch: pytest.MonkeyPatch, job_type: str, kill_error: OSError | None) -> Mock:
    """Run the Stop task against a job of *job_type*; return the API mock."""
    def fake_kill(_pid, _sig):
        if kill_error:
            raise kill_error
    monkeypatch.setattr(stop_job.os, 'kill', fake_kill)
    worker = SimpleNamespace(
        job_info={'type': job_type, 'id': 5, 'name': 'X', 'pid': 1234}, ovdm=Mock())
    result = json.loads(stop_job.task_stop_job(worker, Mock()))
    assert result['parts'][-1]['result'] == 'Pass'
    return worker.ovdm


@pytest.mark.parametrize('job_type', ['collectionSystemTransfer', 'cruiseDataTransfer'])
def test_signalled_transfer_keeps_its_status(monkeypatch: pytest.MonkeyPatch, job_type: str) -> None:
    """The job got the signal and sets the status when it ends."""
    ovdm = _run(monkeypatch, job_type, None)
    assert not getattr(ovdm, SET_IDLE[job_type]).called
    ovdm.send_msg.assert_called_once()


@pytest.mark.parametrize('job_type', ['collectionSystemTransfer', 'cruiseDataTransfer'])
def test_transfer_without_process_is_set_idle(monkeypatch: pytest.MonkeyPatch, job_type: str) -> None:
    """No process is left to set the status, so Stop does."""
    ovdm = _run(monkeypatch, job_type, OSError(errno.ESRCH, 'No such process'))
    getattr(ovdm, SET_IDLE[job_type]).assert_called_once_with(5)


def test_task_is_still_set_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tasks keep the old behavior."""
    ovdm = _run(monkeypatch, 'task', None)
    ovdm.set_idle_task.assert_called_once_with(5)
