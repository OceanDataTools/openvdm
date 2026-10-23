"""Tests for the lowering worker (#511).

``lowering.py`` sets up and finalizes lowerings, exports the lowering config
and writes the lowering README. As in ``test_cruise_worker.py``, the jobs it
submits go to the ``fake_gearman`` client, the transfers' final passes
(``run_transfer_jobs()``) are replaced, and ownership changes are recorded.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib.readme import GENERATED_MARKER, OPENVDM_ROOT
from server.lib.transfer_lock import CST
from server.workers import lowering

FAIL = json.dumps({'parts': [{'partName': 'Step', 'result': 'Fail', 'reason': 'it broke'}]})
PASS = json.dumps({'parts': [{'partName': 'Step', 'result': 'Pass'}]})
TEMPLATE = os.path.join(OPENVDM_ROOT, 'server', 'etc', 'lowering_readme.md.j2.dist')


def _lowering_config():
    """What ``getLoweringConfig`` returns, with credentials the export must drop."""
    return {
        'cruiseID': 'TEST001', 'loweringID': 'DIVE01', 'loweringStartDate': '2026/10/05 08:00',
        'loweringEndDate': '2026/10/05 16:00', 'configCreatedOn': '2026/10/22 12:00:00',
        'loweringFinalizedOn': None, 'loweringExtent': '',
        'collectionSystemTransfersConfig': [
            {'name': 'Video', 'longName': 'HD video', 'description': 'Camera', 'destDir': 'Video',
             'sshPass': 'secret', 'sourceDir': '/video'}],
    }


def _cruise_config():
    """Enough of ``getCruiseConfig`` for the lowering README."""
    return {'cruiseID': 'TEST001', 'cruiseName': 'Test cruise', 'cruiseStartDate': '2026/10/01 00:00',
            'warehouseConfig': {'loweringDataBaseDir': 'Vehicle', 'cruiseConfigFn': 'cruise_config.json',
                                'loweringConfigFn': 'lowering_config.json', 'md5SummaryFn': 'md5_summary.txt',
                                'md5SummaryMd5Fn': 'md5_summary.md5', 'dataDashboardManifestFn': 'manifest.json'}}


def _job(task, **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def perms(monkeypatch):
    """Record ``set_owner_group_permissions()`` calls; set ``fail`` to a path ending (or True) to fail them."""
    rec = SimpleNamespace(paths=[], fail=None)

    def owner(user, path):
        rec.paths.append(path)
        failed = rec.fail is True or (rec.fail and path.endswith(rec.fail))
        return {'verdict': False, 'reason': f'chown {path} failed'} if failed else {'verdict': True}

    monkeypatch.setattr(lowering, 'set_owner_group_permissions', owner)
    return rec


@pytest.fixture
def transfers(monkeypatch):
    """Replace the transfers' final passes: record them; ``missed`` scripts unrun transfers."""
    rec = SimpleNamespace(calls=[], missed=[], stop=False, worker=None)

    def run(gm_client, task, kind, payloads, should_stop=None):
        rec.calls.append((task, kind, payloads))
        if rec.stop:
            rec.worker.stop = True
        return rec.missed

    monkeypatch.setattr(lowering, 'run_transfer_jobs', run)
    return rec


@pytest.fixture
def api(fake_ovdm, warehouse, tmp_path):
    """The fake API for lowering DIVE01 of the warehouse's cruise."""
    fake_ovdm.config['loweringReadme'] = {'enable': True, 'filename': 'README.md', 'template': TEMPLATE}
    fake_ovdm.get_cruise_id.return_value = warehouse.cruise_id
    fake_ovdm.get_lowering_id.return_value = 'DIVE01'
    fake_ovdm.get_lowering_start_date.return_value = '2026/10/05 08:00'
    fake_ovdm.get_lowering_end_date.return_value = '2026/10/05 16:00'
    fake_ovdm.get_shipboard_data_warehouse_config.return_value = warehouse.config
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 6, 'name': name, 'longName': name}
    fake_ovdm.get_lowering_config.side_effect = _lowering_config
    fake_ovdm.get_cruise_config.side_effect = _cruise_config
    fake_ovdm.get_collection_system_transfers.return_value = []
    fake_ovdm.get_extra_directories.return_value = []
    fake_ovdm.get_active_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 8, 'name': 'Video'}, {'collectionSystemTransferID': 9, 'name': 'Frames'}]
    return fake_ovdm


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = lowering.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: 'executed')
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def lowering_dir(warehouse):
    """The lowering's directory, created."""
    path = warehouse.cruise_dir / 'Vehicle' / 'DIVE01'
    path.mkdir(parents=True)
    return path


@pytest.fixture
def worker(monkeypatch, api, fake_gearman, gearman_base, perms, transfers):
    """A lowering worker using the fake API and Gearman client."""
    monkeypatch.setattr(lowering, 'OpenVDM', lambda: api)
    monkeypatch.setattr(lowering, 'LOGGING_FORMAT', '%(message)s', raising=False)
    w = lowering.OVDMGearmanWorker()
    w.send_job_status = Mock()
    w.send_job_data = Mock()
    transfers.worker = w
    return w


def _setup(worker, task='exportLoweringConfig', **payload):
    """Run the worker's job setup for *task*."""
    return worker.on_job_execute(_job(task, **payload))


def _config_file(lowering_dir):
    return lowering_dir / 'lowering_config.json'


# --- Job setup and completion ---------------------------------------------------

def test_job_setup(worker, api, warehouse) -> None:
    """The job's lowering and dates, or the current ones; the task is set running."""
    _setup(worker, cruiseID='OTHER01', loweringID='DIVE02', loweringStartDate='2026/10/06 08:00')
    assert (worker.cruise_id, worker.lowering_id) == ('OTHER01', 'DIVE02')
    assert worker.lowering_start_date == '2026/10/06 08:00'
    assert worker.lowering_end_date == '2026/10/05 16:00'
    assert worker.cruise_dir == str(warehouse.base_dir / 'OTHER01')
    assert worker.lowering_dir == os.path.join('Vehicle', 'DIVE02')
    api.set_running_task.assert_called_once_with(6, os.getpid(), 'H:test:1')


def test_job_needs_a_lowering(worker, api) -> None:
    """Without a lowering, the job fails."""
    api.get_lowering_id.return_value = None
    result = _setup(worker)
    assert _parts(result) == [('Verify lowering ID', 'Fail')]
    api.set_error_task.assert_called_once_with(6, 'Lowering ID is undefined')


def test_bad_payload(worker) -> None:
    """A payload that isn't JSON fails the job."""
    result = worker.on_job_execute(SimpleNamespace(data='not json', handle='H:1', task='exportLoweringConfig'))
    assert _parts(result) == [('Retrieve job data', 'Fail')]


def test_finalize_runs_pre_finalize_hooks(worker, fake_gearman) -> None:
    """Finalize first runs the preFinalizeCurrentLowering hook tasks with the lowering's details."""
    assert _setup(worker, 'finalizeCurrentLowering') == 'executed'
    assert fake_gearman.jobs == [('preFinalizeCurrentLowering', {
        'cruiseID': 'TEST001', 'loweringID': 'DIVE01', 'loweringStartDate': '2026/10/05 08:00',
        'loweringEndDate': '2026/10/05 16:00'})]


def test_finalize_without_pre_finalize_hooks(worker, api, fake_gearman) -> None:
    """With no pre-finalize hooks, the job goes on to the task."""
    api.config['hooks'].pop('preFinalizeCurrentLowering')
    assert _setup(worker, 'finalizeCurrentLowering') == 'executed'
    assert fake_gearman.jobs == []


@pytest.mark.parametrize('task', ['setupNewLowering', 'finalizeCurrentLowering'])
def test_post_hooks(worker, api, fake_gearman, task) -> None:
    """After setting up or finalizing a lowering, its hook tasks run; then the task goes idle."""
    _setup(worker, task)
    fake_gearman.jobs.clear()
    assert worker.on_job_complete(_job(task), PASS) == PASS
    assert fake_gearman.tasks() == ['postSetupNewLowering' if task == 'setupNewLowering'
                                    else 'postFinalizeCurrentLowering']
    api.set_idle_task.assert_called_once_with(6)


@pytest.mark.parametrize('task', ['setupNewLowering', 'finalizeCurrentLowering'])
def test_without_post_hooks_completes(worker, api, gearman_base, monkeypatch, task) -> None:
    """With no hooks for the task, the job completes instead of running again."""
    api.config['hooks'].pop(task)
    _setup(worker, task)
    monkeypatch.setattr(gearman_base, 'on_job_execute', Mock(side_effect=AssertionError('ran again')))
    assert worker.on_job_complete(_job(task), PASS) == PASS
    api.set_idle_task.assert_called_once_with(6)


@pytest.mark.parametrize('request_state, logged', [
    ({'complete': False, 'timed_out': True}, 'timed out'),
    ({'complete': False, 'timed_out': False, 'exception': 'boom'}, 'failed: boom')])
def test_hook_jobs_that_fail_are_logged(worker, fake_gearman, monkeypatch, request_state, logged,
                                        caplog) -> None:
    """Hook jobs that time out or fail are logged, and the job carries on."""
    real = fake_gearman._request

    def request(task, raw):
        req = real(task, raw)
        req.__dict__.update(request_state)
        return req
    monkeypatch.setattr(fake_gearman, '_request', request)
    assert _setup(worker, 'finalizeCurrentLowering') == 'executed'
    assert f'Task None {logged}' in caplog.text

    caplog.clear()
    worker.on_job_complete(_job('finalizeCurrentLowering'), PASS)
    assert f'Task None {logged}' in caplog.text


def test_hook_submission_error_is_logged(worker, fake_gearman, monkeypatch, caplog) -> None:
    """Gearman failing to run the hook jobs is logged; the job carries on."""
    monkeypatch.setattr(fake_gearman, 'submit_multiple_jobs', Mock(side_effect=OSError('no gearmand')))
    assert _setup(worker, 'finalizeCurrentLowering') == 'executed'
    assert 'Error while submitting or running pre-finalize jobs' in caplog.text
    worker.on_job_complete(_job('finalizeCurrentLowering'), PASS)
    assert 'Error while submitting or running post-hook jobs' in caplog.text


def test_failed_job(worker, api) -> None:
    """A failed last part sets the task's error; a task without an ID posts a message instead."""
    _setup(worker)
    worker.on_job_complete(_job('exportLoweringConfig'), FAIL)
    api.set_error_task.assert_called_once_with(6, 'it broke')

    worker.task = {'taskID': 0, 'longName': 'Something'}
    worker.on_job_complete(_job('exportLoweringConfig'), FAIL)
    api.send_msg.assert_called_once_with('Something failed', 'it broke')


def test_crash(worker, api) -> None:
    """A crash sends a failed part and sets the task's error, with where it raised."""
    _setup(worker)
    try:
        raise ValueError('boom')
    except ValueError as exc:
        info = (type(exc), exc, exc.__traceback__)
    assert worker.on_job_exception(_job('exportLoweringConfig'), info) == 'crashed'
    reason = json.loads(worker.send_job_data.call_args.args[1])[0]['reason']
    assert reason.startswith('ValueError: boom (test_lowering_worker.py, line ')
    api.set_error_task.assert_called_once_with(6, f'Worker crashed: {reason}')

    worker.task = {'taskID': 0, 'longName': 'Something'}
    worker.on_job_exception(_job('exportLoweringConfig'), (KeyError, None, None))
    api.send_msg.assert_called_once_with('Something failed', 'Worker crashed: KeyError (unknown, line ?)')


def test_stop_and_quit(worker) -> None:
    """Stop sets the flag; quit also shuts the worker down."""
    worker.stop_task()
    assert worker.stop is True
    worker.stop = False
    worker.shutdown = Mock()
    worker.quit_worker()
    assert worker.stop is True
    worker.shutdown.assert_called_once()


def test_build_logfile_dirpath(worker, api, tmp_path) -> None:
    """The transfer log directory, created if needed."""
    api.get_transfer_log_dir.return_value = str(tmp_path / 'logs' / 'transfers')
    assert worker.build_logfile_dirpath() == str(tmp_path / 'logs' / 'transfers')
    assert (tmp_path / 'logs' / 'transfers').is_dir()


# --- Export lowering config -----------------------------------------------------

def test_export_lowering_config(worker, api, lowering_dir, perms) -> None:
    """Credentials and transfer settings dropped, an unset extent left out; MD5 update queued."""
    _setup(worker)
    assert worker.export_lowering_config() == {'verdict': True}
    config = json.loads(_config_file(lowering_dir).read_text())
    assert config['collectionSystemTransfersConfig'] == [
        {'name': 'Video', 'longName': 'HD video', 'description': 'Camera', 'destDir': 'Video'}]
    assert 'loweringExtent' not in config
    assert config['loweringFinalizedOn'] is None
    assert perms.paths == [str(_config_file(lowering_dir))]
    api.update_md5_summary.assert_called_once_with(updated=['Vehicle/DIVE01/lowering_config.json'],
                                                   cruise_id='TEST001', background=False)


def test_export_lowering_config_extent(worker, api, lowering_dir) -> None:
    """A set extent is kept (#399)."""
    extent = '{"westernmost": -121, "easternmost": -120, "southernmost": 44, "northernmost": 45}'
    api.get_lowering_config.side_effect = lambda: {**_lowering_config(), 'loweringExtent': extent}
    _setup(worker)
    worker.export_lowering_config()
    assert json.loads(_config_file(lowering_dir).read_text())['loweringExtent'] == extent


def test_export_lowering_config_finalized_date(worker, lowering_dir) -> None:
    """Finalizing sets loweringFinalizedOn; a later export keeps it."""
    _setup(worker)
    worker.export_lowering_config(finalize=True)
    assert json.loads(_config_file(lowering_dir).read_text())['loweringFinalizedOn'] == '2026/10/22 12:00:00'
    worker.export_lowering_config()
    assert json.loads(_config_file(lowering_dir).read_text())['loweringFinalizedOn'] == '2026/10/22 12:00:00'


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read any file')
def test_export_lowering_config_unreadable(worker, lowering_dir) -> None:
    """An existing config file that can't be read fails the export."""
    _config_file(lowering_dir).write_text('{}')
    _config_file(lowering_dir).chmod(0)
    _setup(worker)
    assert worker.export_lowering_config()['reason'].startswith(
        'Unable to read the existing configuration file lowering_config.json: [Errno 13] Permission denied')


@pytest.mark.parametrize('text', ['{truncated', '[]'])
def test_export_lowering_config_not_json(worker, lowering_dir, text) -> None:
    """An existing config file that isn't a JSON object fails the export, keeping its finalized date (#548)."""
    _config_file(lowering_dir).write_text(text)
    _setup(worker)
    result = worker.export_lowering_config()
    assert result['verdict'] is False
    assert result['reason'].startswith('Unable to read the existing configuration file lowering_config.json: ')
    assert _config_file(lowering_dir).read_text() == text


def test_export_lowering_config_write_fails(worker, monkeypatch, lowering_dir) -> None:
    """A config file that can't be written fails the export with the reason."""
    monkeypatch.setattr(lowering, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'full'})
    _setup(worker)
    assert worker.export_lowering_config() == {'verdict': False, 'reason': 'full'}


def test_export_lowering_config_ownership_fails(worker, api, lowering_dir, perms) -> None:
    """Ownership that can't be set fails the export; no MD5 update."""
    perms.fail = True
    _setup(worker)
    assert worker.export_lowering_config()['verdict'] is False
    api.update_md5_summary.assert_not_called()


# --- Lowering README ------------------------------------------------------------

def test_build_lowering_readme(worker, api, lowering_dir, perms) -> None:
    """Written in the lowering directory from its config file; MD5 update queued."""
    _setup(worker)
    worker.export_lowering_config(finalize=True)
    api.update_md5_summary.reset_mock()
    assert worker.build_lowering_readme() == {'verdict': True}
    text = (lowering_dir / 'README.md').read_text()
    assert GENERATED_MARKER in text.splitlines()[0]
    assert 'DIVE01' in text
    assert str(lowering_dir / 'README.md') in perms.paths
    api.update_md5_summary.assert_called_once_with(updated=['Vehicle/DIVE01/README.md'], cruise_id='TEST001',
                                                   background=False)


def test_build_lowering_readme_turned_off(worker, api, lowering_dir) -> None:
    """Turned off in openvdm.yaml: skipped, nothing written."""
    api.config['loweringReadme']['enable'] = False
    _setup(worker)
    assert worker.build_lowering_readme() == {'verdict': True, 'skipped': True}
    assert not (lowering_dir / 'README.md').exists()


@pytest.mark.parametrize('block, reason', [
    ({'template': '/nowhere/readme.md.j2'}, 'README template not found: /nowhere/readme.md.j2'),
    ({'template': TEMPLATE, 'filename': 'notes/README.md'}, 'must be a file name, not a path'),
], ids=['no template', 'bad filename'])
def test_build_lowering_readme_bad_settings(worker, api, block, reason) -> None:
    """Settings that can't be used fail with the reason."""
    api.config['loweringReadme'] = block
    _setup(worker)
    result = worker.build_lowering_readme()
    assert result['verdict'] is False
    assert reason in result['reason']


def test_build_lowering_readme_bad_filled_in_name(worker, api) -> None:
    """A name that isn't a file name once the lowering ID is filled in fails the README."""
    api.config['loweringReadme']['filename'] = '{loweringID}'
    _setup(worker, loweringID='..')
    assert worker.build_lowering_readme() == {
        'verdict': False, 'reason': "The README's filename must be a file name, not a path: .."}


def test_build_lowering_readme_without_config_file(worker, lowering_dir) -> None:
    """Without the lowering's config file, the README fails: its details come from there."""
    _setup(worker)
    assert worker.build_lowering_readme()['reason'].startswith('Unable to read the lowering config file: ')


def test_build_lowering_readme_api_error(worker, api, lowering_dir) -> None:
    """An API call that fails fails the README."""
    _setup(worker)
    worker.export_lowering_config()
    api.get_cruise_config.side_effect = OSError('API down')
    assert worker.build_lowering_readme() == {
        'verdict': False, 'reason': 'Unable to get the configuration from OpenVDM: API down'}


def test_build_lowering_readme_template_error(worker, api, lowering_dir, tmp_path) -> None:
    """A template with a syntax error fails the README, naming the line."""
    template = tmp_path / 'broken.md.j2'
    template.write_text('line one\n{% if %}\n')
    api.config['loweringReadme'] = {'template': str(template)}
    _setup(worker)
    worker.export_lowering_config()
    assert worker.build_lowering_readme()['reason'].startswith(
        f'Unable to build the README from {template}, line 2: ')


def test_build_lowering_readme_not_ours(worker, lowering_dir) -> None:
    """A README OpenVDM didn't write is left alone, and the README fails."""
    (lowering_dir / 'README.md').write_text('Dive notes\n')
    _setup(worker)
    worker.export_lowering_config()
    assert "wasn't written by OpenVDM" in worker.build_lowering_readme()['reason']
    assert (lowering_dir / 'README.md').read_text() == 'Dive notes\n'


def test_build_lowering_readme_ownership_fails(worker, api, lowering_dir, perms) -> None:
    """Ownership that can't be set fails the README; no MD5 update."""
    _setup(worker)
    worker.export_lowering_config()
    api.update_md5_summary.reset_mock()
    perms.fail = 'README.md'
    assert worker.build_lowering_readme()['verdict'] is False
    api.update_md5_summary.assert_not_called()


# --- Export and Rebuild README tasks --------------------------------------------

def test_export_task(worker, lowering_dir) -> None:
    """Exports the config and writes the README."""
    _setup(worker)
    result = lowering.task_export_lowering_config(worker, _job('exportLoweringConfig'))
    assert _parts(result) == [('Export lowering config data to file', 'Pass'), ('Write lowering README', 'Pass')]
    assert (lowering_dir / 'README.md').is_file()


def test_export_task_failures(worker, api, lowering_dir, monkeypatch) -> None:
    """A failed README is the task's last part, so fails it; a failed export ends it."""
    (lowering_dir / 'README.md').write_text('mine\n')
    _setup(worker)
    assert _parts(lowering.task_export_lowering_config(worker, _job('exportLoweringConfig')))[-1] == \
        ('Write lowering README', 'Fail')
    api.send_msg.assert_not_called()

    monkeypatch.setattr(lowering, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    assert _parts(lowering.task_export_lowering_config(worker, _job('exportLoweringConfig'))) == [
        ('Export lowering config data to file', 'Fail')]


def test_export_task_readme_off(worker, api, lowering_dir) -> None:
    """With the README turned off, there's no README part."""
    api.config['loweringReadme']['enable'] = False
    _setup(worker)
    assert _parts(lowering.task_export_lowering_config(worker, _job('exportLoweringConfig'))) == [
        ('Export lowering config data to file', 'Pass')]


@pytest.mark.parametrize('setup, expected', [
    (lambda d, a: None, 'Pass'),
    (lambda d, a: a.config['loweringReadme'].update(enable=False), 'Fail'),
    (lambda d, a: (d / 'README.md').write_text('mine\n'), 'Fail'),
], ids=['written', 'turned off', 'not ours'])
def test_rebuild_readme_task(worker, api, lowering_dir, setup, expected) -> None:
    """Passes when written; fails when turned off (nothing was rebuilt) or when it can't be written."""
    setup(lowering_dir, api)
    _setup(worker, 'rebuildLoweringReadme')
    worker.export_lowering_config()
    part = json.loads(lowering.task_rebuild_lowering_readme(worker, _job('rebuildLoweringReadme')))['parts'][-1]
    assert part['result'] == expected
    if api.config['loweringReadme'].get('enable') is False:
        assert part['reason'] == 'The lowering README is turned off (loweringReadme in openvdm.yaml)'


# --- Setup New Lowering ---------------------------------------------------------

def test_setup_new_lowering(worker, api, warehouse, fake_gearman, fake_run) -> None:
    """Creates the lowering directory (another worker), exports the config, writes the README, sets its size."""
    fake_run.on('du', stdout='678\t/lowering\n')

    def create_directory(data):
        (warehouse.cruise_dir / 'Vehicle' / 'DIVE01').mkdir(parents=True)
        return PASS
    fake_gearman.results['createLoweringDirectory'] = create_directory
    _setup(worker, 'setupNewLowering')
    result = lowering.task_setup_new_lowering(worker, _job('setupNewLowering', loweringID='DIVE01'))

    assert _parts(result) == [('Create lowering data directory structure', 'Pass'),
                              ('Export lowering config data to file', 'Pass'), ('Write lowering README', 'Pass')]
    assert fake_gearman.jobs == [('createLoweringDirectory', {'loweringID': 'DIVE01'})]
    assert fake_run.calls[0].cmd == ['du', '-sb', str(warehouse.cruise_dir / 'Vehicle' / 'DIVE01')]
    api.set_lowering_size.assert_called_once_with('678')


def test_setup_new_lowering_du_fails(worker, api, lowering_dir, fake_run) -> None:
    """A failed du records a size of 0."""
    fake_run.on('du', returncode=1)
    _setup(worker, 'setupNewLowering')
    lowering.task_setup_new_lowering(worker, _job('setupNewLowering'))
    api.set_lowering_size.assert_called_once_with('0')


def test_setup_new_lowering_directory_fails(worker, api, fake_gearman) -> None:
    """A lowering directory that can't be created ends the setup with its reason."""
    fake_gearman.results['createLoweringDirectory'] = FAIL
    _setup(worker, 'setupNewLowering')
    result = json.loads(lowering.task_setup_new_lowering(worker, _job('setupNewLowering')))
    assert result['parts'] == [{'partName': 'Create lowering data directory structure', 'result': 'Fail',
                                'reason': 'it broke'}]
    api.set_lowering_size.assert_not_called()


def test_setup_new_lowering_export_fails(worker, lowering_dir, monkeypatch, fake_run) -> None:
    """A failed config export ends the setup."""
    monkeypatch.setattr(lowering, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    _setup(worker, 'setupNewLowering')
    assert _parts(lowering.task_setup_new_lowering(worker, _job('setupNewLowering')))[-1] == \
        ('Export lowering config data to file', 'Fail')


def test_setup_new_lowering_readme_fails(worker, api, lowering_dir, fake_run) -> None:
    """A README that can't be written is the last part, so the setup fails with its reason; the size is still set."""
    fake_run.on('du', stdout='1\t/x\n')
    (lowering_dir / 'README.md').write_text('mine\n')
    _setup(worker, 'setupNewLowering')
    assert _parts(lowering.task_setup_new_lowering(worker, _job('setupNewLowering')))[-1] == \
        ('Write lowering README', 'Fail')
    api.set_lowering_size.assert_called_once_with('1')


# --- Finalize Current Lowering --------------------------------------------------

def test_finalize(worker, api, lowering_dir, transfers) -> None:
    """The lowering's transfers' final pass, then the finalized config and README."""
    _setup(worker, 'finalizeCurrentLowering')
    result = lowering.task_finalize_current_lowering(worker, _job('finalizeCurrentLowering'))

    assert _parts(result) == [('Verify lowering directory exists', 'Pass'),
                              ('Run collection system transfers jobs', 'Pass'),
                              ('Export lowering config data to file', 'Pass'), ('Write lowering README', 'Pass')]
    [(task, kind, jobs)] = transfers.calls
    assert (task, kind, list(jobs)) == ('runCollectionSystemTransfer', CST, [8, 9])
    assert jobs[8] == {'loweringID': 'DIVE01', 'loweringStartDate': '2026/10/05 08:00',
                       'loweringEndDate': '2026/10/05 16:00', 'systemStatus': 'On',
                       'collectionSystemTransfer': {'collectionSystemTransferID': 8}}
    api.get_active_collection_system_transfers.assert_called_once_with(cruise=False)
    assert json.loads(_config_file(lowering_dir).read_text())['loweringFinalizedOn'] == '2026/10/22 12:00:00'


def test_finalize_no_lowering_directory(worker, transfers) -> None:
    """Without the lowering directory, nothing runs."""
    _setup(worker, 'finalizeCurrentLowering')
    result = json.loads(lowering.task_finalize_current_lowering(worker, _job('finalizeCurrentLowering')))
    assert result['parts'] == [{'partName': 'Verify lowering directory exists', 'result': 'Fail',
                                'reason': 'Lowering directory does not exist: Vehicle/DIVE01'}]
    assert transfers.calls == []


def test_finalize_stopped(worker, lowering_dir, transfers) -> None:
    """Stopped during the final pass: ends there, ignored rather than failed (#487)."""
    transfers.stop = True
    _setup(worker, 'finalizeCurrentLowering')
    result = json.loads(lowering.task_finalize_current_lowering(worker, _job('finalizeCurrentLowering')))
    assert result['parts'][-1] == {'partName': 'Run collection system transfers jobs', 'result': 'Ignore',
                                   'reason': 'Stopped'}
    assert not _config_file(lowering_dir).exists()


def test_finalize_missed_transfers(worker, api, lowering_dir, transfers) -> None:
    """Transfers still running after the wait are reported by name, and finalize carries on (#480)."""
    transfers.missed = [9]
    _setup(worker, 'finalizeCurrentLowering')
    parts = _parts(lowering.task_finalize_current_lowering(worker, _job('finalizeCurrentLowering')))
    assert parts[-1] == ('Write lowering README', 'Pass')
    title, body = api.send_msg.call_args.args
    assert title == 'Finalizing DIVE01: collection system transfers still running'
    assert 'Frames' in body and 'Video' not in body


def test_finalize_export_fails(worker, lowering_dir, monkeypatch, transfers) -> None:
    """A failed config export ends finalize."""
    monkeypatch.setattr(lowering, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    _setup(worker, 'finalizeCurrentLowering')
    assert _parts(lowering.task_finalize_current_lowering(worker, _job('finalizeCurrentLowering')))[-1] == \
        ('Export lowering config data to file', 'Fail')
