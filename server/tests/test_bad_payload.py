"""A job whose payload isn't JSON fails its task instead of crashing the worker (#544).

The cruise, lowering and directory workers have their own tests of this;
these are the workers whose other tests come with #512.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import data_dashboard, md5_summary, post_hooks


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = data_dashboard.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: 'executed')
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    return base


def _worker(module, monkeypatch, fake_ovdm):
    """A worker of *module* using the fake API."""
    monkeypatch.setattr(module, 'OpenVDM', lambda: fake_ovdm)
    monkeypatch.setattr(module, 'LOGGING_FORMAT', '%(message)s', raising=False)
    worker = module.OVDMGearmanWorker()
    worker.send_job_status = Mock()
    return worker


def _bad_job(task):
    return SimpleNamespace(data='not json', handle='H:test:1', task=task)


@pytest.mark.parametrize('module, task, title', [
    (data_dashboard, 'updateDataDashboard', 'Updating data dashboard failed'),
    (md5_summary, 'updateMD5Summary', 'Updating MD5 summary failed'),
    (post_hooks, 'postCollectionSystemTransfer', None),
], ids=['data_dashboard', 'md5_summary', 'post_hooks'])
def test_custom_task(monkeypatch, fake_ovdm, fake_gearman, gearman_base, module, task, title) -> None:
    """A task without an ID posts the failure as a message; no hook tasks run."""
    worker = _worker(module, monkeypatch, fake_ovdm)
    result = worker.on_job_execute(_bad_job(task))
    assert json.loads(result)['parts'] == [{'partName': 'Retrieve job data', 'result': 'Fail',
                                            'reason': 'Failed to parse current job payload'}]
    msg_title, reason = fake_ovdm.send_msg.call_args.args
    assert msg_title == (title or f"{worker.task['longName']} failed")
    assert reason == 'Failed to parse current job payload'
    fake_ovdm.set_error_task.assert_not_called()
    assert fake_gearman.jobs == []


@pytest.mark.parametrize('module, task', [(data_dashboard, 'rebuildDataDashboard'),
                                          (md5_summary, 'rebuildMD5Summary')])
def test_api_task(monkeypatch, fake_ovdm, fake_gearman, gearman_base, module, task) -> None:
    """A task from the API gets the error status; no hook tasks run."""
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 9, 'name': name, 'longName': name}
    worker = _worker(module, monkeypatch, fake_ovdm)
    worker.on_job_execute(_bad_job(task))
    fake_ovdm.set_error_task.assert_called_once_with(9, 'Failed to parse current job payload')
    fake_ovdm.set_idle_task.assert_not_called()
    assert fake_gearman.jobs == []


def test_post_hook_unknown_task(monkeypatch, fake_ovdm, gearman_base) -> None:
    """A post-hook task OpenVDM doesn't know fails with a message, as there's no status to set."""
    fake_ovdm.get_task_by_name.return_value = None
    worker = _worker(post_hooks, monkeypatch, fake_ovdm)
    result = worker.on_job_execute(SimpleNamespace(data='{}', handle='H:test:1', task='postSomething'))
    assert json.loads(result)['parts'][-1]['reason'] == 'Task not found'
    fake_ovdm.send_msg.assert_called_once_with('postSomething failed', 'Task not found')
