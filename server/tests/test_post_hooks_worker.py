"""Tests for the post-hooks worker (#512 part 3).

``post_hooks.py`` runs the commands ``openvdm.yaml``'s ``postHookCommands``
configures for a hook, with the job's cruise, lowering, transfer and files
filled in for their placeholders. The commands go to the ``fake_run``
fixture. A bad payload, and a task OpenVDM doesn't know, are tested in
``test_bad_payload.py``.
"""

import json
import os
import signal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import post_hooks

CSTS = {3: {'collectionSystemTransferID': 3, 'name': 'CTD'}, 5: {'collectionSystemTransferID': 5, 'name': 'SCS'}}


def _job(task='postCollectionSystemTransfer', **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


def _cmd(name, *args):
    return {'name': name, 'command': list(args)}


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run the task handler, and pass results through."""
    base = post_hooks.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute',
                        lambda self, job: self.on_job_complete(job, post_hooks.task_post_hook(self, job)))
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def api(fake_ovdm):
    """The fake API: the CTD and SCS transfers, the current lowering DIVE02, and no hook commands."""
    fake_ovdm.config['postHookCommands'] = {}
    fake_ovdm.get_lowering_id.return_value = 'DIVE02'
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: CSTS.get(int(cst_id or 0))
    fake_ovdm.get_task_by_name.return_value = None
    return fake_ovdm


@pytest.fixture
def hooks(api):
    """Set a hook's commands: ``hooks('postSetupNewCruise', [...])``, or by transfer name for a
    transfer hook: ``hooks('postCollectionSystemTransfer', CTD=[...])``."""
    def set_hook(hook, commands=None, **by_transfer):
        if by_transfer:
            api.config['postHookCommands'][hook] = [
                {'collectionSystemTransferName': name, 'commandList': cmds} for name, cmds in by_transfer.items()]
        else:
            api.config['postHookCommands'][hook] = {'commandList': commands}
    return set_hook


@pytest.fixture
def worker(monkeypatch, api, gearman_base, fake_run):
    """A post-hooks worker using the fake API; commands go to ``fake_run``."""
    monkeypatch.setattr(post_hooks, 'OpenVDM', lambda: api)
    monkeypatch.setattr(post_hooks, 'LOGGING_FORMAT', '%(message)s', raising=False)
    w = post_hooks.OVDMGearmanWorker()
    w.send_job_status = Mock()
    w.send_job_data = Mock()
    w.shutdown = Mock()
    return w


# --- Choosing and filling in the commands ------------------------------------------

def test_no_commands(worker, api, fake_run) -> None:
    """A hook without commands is ignored: nothing runs, and no status is set."""
    result = worker.on_job_execute(_job(collectionSystemTransferID=3))
    assert json.loads(result)['parts'] == [{'partName': 'Retrieve commands', 'result': 'Ignore',
                                            'reason': 'No commands found'}]
    assert fake_run.calls == []
    api.track_gearman_job.assert_not_called()
    api.set_idle_task.assert_not_called()
    api.send_msg.assert_not_called()


def test_transfer_hook(worker, api, hooks, fake_run) -> None:
    """A transfer hook runs the commands for the job's transfer, with its placeholders filled in."""
    hooks('postCollectionSystemTransfer',
          CTD=[_cmd('Plot casts', 'plot', '--cruise={cruiseID}', '--lowering={loweringID}',
                    '{collectionSystemTransferID}', '{collectionSystemTransferName}', '{newFiles}', '{updatedFiles}')],
          SCS=[_cmd('Other', 'other')])
    result = worker.on_job_execute(_job(collectionSystemTransferID=3, cruiseID='C1', loweringID='L1',
                                        files={'new': ['CTD/a.hex', 'CTD/b.hex'], 'updated': ['CTD/c.hex']}))
    assert _parts(result) == [('Get Commands', 'Pass'), ('Running commands', 'Pass')]
    assert fake_run.commands() == [['plot', '--cruise=C1', '--lowering=L1', '3', 'CTD', 'CTD/a.hex CTD/b.hex',
                                    'CTD/c.hex']]
    api.track_gearman_job.assert_called_once_with('Post collection system transfer', os.getpid(), 'H:test:1')


def test_current_cruise_and_lowering(worker, hooks, fake_run) -> None:
    """Without them in the payload, the current cruise and lowering are used; empty file lists drop
    their arguments."""
    hooks('postSetupNewLowering', [_cmd('Remote dirs', 'build', '{cruiseID}', '{loweringID}', '{newFiles}',
                                        '{updatedFiles}')])
    worker.on_job_execute(_job('postSetupNewLowering'))
    assert fake_run.commands() == [['build', 'TEST001', 'DIVE02']]


def test_other_transfers_commands_not_run(worker, hooks, fake_run) -> None:
    """A transfer with no commands of its own is ignored."""
    hooks('postDataDashboard', CTD=[_cmd('Plot casts', 'plot')])
    result = worker.on_job_execute(_job('postDataDashboard', collectionSystemTransferID=5))
    assert _parts(result) == [('Running commands', 'Ignore')]
    assert fake_run.calls == []


def test_unknown_transfer(worker, api, hooks) -> None:
    """A transfer hook for a transfer OpenVDM doesn't know fails."""
    hooks('postCollectionSystemTransfer', CTD=[_cmd('Plot casts', 'plot')])
    worker.on_job_execute(_job(collectionSystemTransferID=99))
    api.send_msg.assert_called_once_with('Post collection system transfer failed',
                                         'Could not find collection system transfer')


@pytest.mark.parametrize('hook, long_name', [
    ('postSetupNewCruise', 'Post setup new cruise'), ('preFinalizeCurrentCruise', 'Pre-finalize current cruise'),
    ('postFinalizeCurrentCruise', 'Post-finalize current cruise'),
    ('preFinalizeCurrentLowering', 'Pre-finalize current lowering'),
    ('postFinalizeCurrentLowering', 'Post-finalize current lowering')])
def test_other_hooks(worker, api, hooks, fake_run, hook, long_name) -> None:
    """The other hooks run their commandList."""
    hooks(hook, [_cmd('Export', 'export', '{cruiseID}')])
    assert _parts(worker.on_job_execute(_job(hook, cruiseID='C1')))[-1] == ('Running commands', 'Pass')
    assert fake_run.commands() == [['export', 'C1']]
    assert api.track_gearman_job.call_args.args[0] == long_name


def test_missing_placeholder_value(worker, api, hooks, fake_run) -> None:
    """A command using a placeholder from the API with no value isn't run, and the job fails saying
    which; the hook's other commands still run (#586)."""
    api.get_lowering_id.return_value = None
    hooks('postSetupNewCruise', [_cmd('Lowering dirs', 'build', '{cruiseID}', '--lowering={loweringID}'),
                                 _cmd('Cruise dirs', 'build', '{cruiseID}')])
    result = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))
    assert fake_run.commands() == [['build', 'TEST001']]
    assert result['parts'][-1] == {'partName': 'Running commands', 'result': 'Fail',
                                   'reason': 'Lowering dirs: not run, no value for {loweringID}'}
    api.send_msg.assert_called_once_with('Post setup new cruise failed',
                                         'Lowering dirs: not run, no value for {loweringID}')


def test_transfer_placeholders_outside_transfer_hook(worker, hooks, fake_run) -> None:
    """The transfer placeholders have no value outside a transfer hook (#586)."""
    hooks('postFinalizeCurrentCruise', [_cmd('Export', 'export', '{collectionSystemTransferName}',
                                             '{collectionSystemTransferID}')])
    result = json.loads(worker.on_job_execute(_job('postFinalizeCurrentCruise')))
    assert fake_run.calls == []
    assert result['parts'][-1]['reason'] == \
        'Export: not run, no value for {collectionSystemTransferID}, {collectionSystemTransferName}'


def test_missing_value_not_used(worker, api, hooks, fake_run) -> None:
    """A placeholder without a value that a command doesn't use doesn't stop it."""
    api.get_lowering_id.return_value = None
    hooks('postSetupNewCruise', [_cmd('Cruise dirs', 'build', '{cruiseID}')])
    assert _parts(worker.on_job_execute(_job('postSetupNewCruise')))[-1] == ('Running commands', 'Pass')


@pytest.mark.parametrize('files', [{}, None, {'new': None}], ids=['empty', 'null', 'null-list'])
def test_no_files(worker, hooks, fake_run, files) -> None:
    """Without files, {newFiles} and {updatedFiles} are empty, and their arguments dropped."""
    hooks('postCollectionSystemTransfer', CTD=[_cmd('Plot casts', 'plot', '{newFiles}', '{updatedFiles}')])
    worker.on_job_execute(_job(collectionSystemTransferID=3, files=files))
    assert fake_run.commands() == [['plot']]


# --- Running the commands ---------------------------------------------------------

def test_commands_run_in_order(worker, hooks, fake_run) -> None:
    """Every command runs, in order, even after one fails; the failures are all reported."""
    hooks('postSetupNewCruise', [_cmd('First', 'one'), _cmd('Second', 'two'), _cmd('Third', 'three')])
    fake_run.on('one', returncode=1, stderr='first failed\n')
    fake_run.on('three', returncode=2, stdout='third said no\n')
    result = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))
    assert fake_run.commands() == [['one'], ['two'], ['three']]
    assert result['parts'][-1] == {'partName': 'Running commands', 'result': 'Fail',
                                   'reason': 'First (exit 1):\nfirst failed\n\nThird (exit 2):\nthird said no'}


def test_command_failure_message(worker, api, hooks, fake_run) -> None:
    """A failed command posts an OpenVDM message naming it, with its exit status and output."""
    hooks('postSetupNewCruise', [_cmd('Remote dirs', 'build', '-s')])
    fake_run.on('build', returncode=1)
    worker.on_job_execute(_job('postSetupNewCruise'))
    api.send_msg.assert_called_once_with('Post setup new cruise failed', 'Remote dirs (exit 1)')


def test_command_killed(worker, hooks, fake_run) -> None:
    """A command killed by a signal says so."""
    hooks('postSetupNewCruise', [_cmd('Remote dirs', 'build')])
    fake_run.on('build', returncode=-signal.SIGKILL)
    result = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))
    assert result['parts'][-1]['reason'] == f'Remote dirs (killed by signal {int(signal.SIGKILL)})'


def test_command_cant_start(worker, hooks, fake_run) -> None:
    """A command that can't start (e.g. not installed) fails, saying which program."""
    hooks('postSetupNewCruise', [_cmd('Remote dirs', '/opt/missing')])
    fake_run.on('/opt/missing', raises=FileNotFoundError(2, 'No such file or directory'))
    result = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))
    assert result['parts'][-1]['reason'] == \
        "Remote dirs: couldn't run /opt/missing: [Errno 2] No such file or directory"


def test_empty_command(worker, hooks, fake_run, monkeypatch) -> None:
    """A command left empty after its placeholders are filled in fails as an empty command."""
    hooks('postSetupNewCruise', [_cmd('Files only', '{newFiles}')])
    monkeypatch.setattr(post_hooks.subprocess, 'run', Mock(side_effect=IndexError('list index out of range')))
    result = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))
    assert result['parts'][-1]['reason'] == "Files only: couldn't run an empty command: list index out of range"


def test_long_output_cut(worker, hooks, fake_run) -> None:
    """Only the end of a failed command's output goes in the reason: its last 20 lines, at most
    2000 characters, with a note."""
    hooks('postSetupNewCruise', [_cmd('Noisy', 'noisy')])
    fake_run.on('noisy', returncode=1, stderr=''.join(f'line {n}\n' for n in range(50)))
    reason = json.loads(worker.on_job_execute(_job('postSetupNewCruise')))['parts'][-1]['reason']
    assert reason == 'Noisy (exit 1):\n[earlier output cut]\n' + '\n'.join(f'line {n}' for n in range(30, 50))
    assert post_hooks.OVDMGearmanWorker._output_tail('x' * 3000) == '[earlier output cut]\n' + 'x' * 2000


def test_progress(worker, hooks) -> None:
    """Progress is reported for each command."""
    hooks('postSetupNewCruise', [_cmd('First', 'one'), _cmd('Second', 'two')])
    worker.on_job_execute(_job('postSetupNewCruise'))
    assert [call.args[1:] for call in worker.send_job_status.call_args_list] == [
        (1, 10), (2, 10), (60, 100), (100, 100), (10, 10)]


# --- Completion ---------------------------------------------------------------------

def test_passed_hook(worker, api, hooks) -> None:
    """A passed hook sets its (ID 0) task idle; nothing is posted."""
    hooks('postSetupNewCruise', [_cmd('First', 'one')])
    worker.on_job_execute(_job('postSetupNewCruise'))
    api.set_idle_task.assert_called_once_with(0)
    api.send_msg.assert_not_called()


def test_hook_with_task_id(worker, api, hooks, fake_run) -> None:
    """A hook task with an ID in OpenVDM gets its error status set instead of a message."""
    worker.task = {'taskID': 12, 'name': 'postSetupNewCruise', 'longName': 'Post setup'}
    worker.on_job_complete(_job('postSetupNewCruise'),
                           json.dumps({'parts': [{'partName': 'x', 'result': 'Fail', 'reason': 'broke'}]}))
    api.set_error_task.assert_called_once_with(12, 'broke')


def test_no_parts(worker, api) -> None:
    """A result without parts sets no status."""
    worker.task = post_hooks.CUSTOM_TASKS[0]
    assert worker.on_job_complete(_job(), json.dumps({'parts': []})) == json.dumps({'parts': []})
    api.set_idle_task.assert_not_called()


@pytest.mark.parametrize('task_id, call', [(0, 'send_msg'), (12, 'set_error_task')])
def test_job_exception(worker, api, task_id, call) -> None:
    """A crash is reported with where it happened."""
    worker.task = {'taskID': task_id, 'name': 'postSetupNewCruise', 'longName': 'Post setup new cruise'}
    try:
        raise KeyError('commandList')
    except KeyError as err:
        info = (type(err), err, err.__traceback__)
    assert worker.on_job_exception(_job('postSetupNewCruise'), info) == 'crashed'
    assert getattr(api, call).call_args.args[-1].startswith(
        "Worker crashed: KeyError: 'commandList' (test_post_hooks_worker.py, line ")


def test_stop_and_quit(worker) -> None:
    """Stop stops the current task; quit also shuts the worker down."""
    worker.stop_task()
    assert worker.stop
    worker.quit_worker()
    worker.shutdown.assert_called_once()


def test_build_commands_none(worker) -> None:
    """No command list builds no commands."""
    assert worker._build_commands(None) is None
