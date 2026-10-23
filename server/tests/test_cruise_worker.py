"""Tests for the cruise worker (#511).

``cruise.py`` sets up and finalizes cruises, exports the cruise config, writes
the cruise README and copies PublicData into the cruise. The jobs it submits
to other workers go to the ``fake_gearman`` client; the final passes of the
transfers (``run_transfer_jobs()``, tested in
``test_finalize_running_transfers.py``) and the rsync command
(``run_transfer_command()``, #510) are replaced, and ownership changes are
recorded.
"""

import json
import os
import shutil
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib.readme import GENERATED_MARKER, OPENVDM_ROOT
from server.lib.transfer_lock import CDT, CST
from server.lib.transfer_utils import TransferCommandError
from server.workers import cruise

FAIL = json.dumps({'parts': [{'partName': 'Step', 'result': 'Fail', 'reason': 'it broke'}]})
TEMPLATE = os.path.join(OPENVDM_ROOT, 'server', 'etc', 'cruise_readme.md.j2.dist')


def _cruise_config():
    """What ``getCruiseConfig`` returns, with credentials the export must drop."""
    return {
        'cruiseID': 'TEST001', 'cruiseName': 'Test cruise', 'cruisePI': '', 'cruiseStartDate': '2026/10/01 00:00',
        'cruiseEndDate': '2026/10/20 00:00', 'configCreatedOn': '2026/10/22 12:00:00', 'cruiseFinalizedOn': None,
        'warehouseConfig': {'loweringDataBaseDir': 'Vehicle', 'cruiseConfigFn': 'cruise_config.json',
                            'loweringConfigFn': 'lowering_config.json',
                            'dataDashboardManifestFn': 'manifest.json', 'md5SummaryFn': 'md5_summary.txt',
                            'md5SummaryMd5Fn': 'md5_summary.md5'},
        'collectionSystemTransfersConfig': [
            {'name': 'SCS', 'longName': 'Underway', 'description': 'Nav', 'destDir': 'SCS', 'smbPass': 'secret',
             'sourceDir': '/data'}],
        'extraDirectoriesConfig': [
            {'name': 'Dashboard_Data', 'longName': 'Dashboard', 'description': '', 'destDir': 'OpenVDM/DashboardData',
             'extraDirectoryID': '1'}],
        'cruiseDataTransfersConfig': [{'name': 'Backup', 'sshPass': 'secret'}],
        'shipToShoreTransfersConfig': [{'name': 'Shore'}],
    }


def _job(task, **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def perms(monkeypatch):
    """Record ``set_owner_group_permissions()`` calls; set ``fail`` to a path (or True) to fail them."""
    rec = SimpleNamespace(paths=[], fail=None)

    def owner(user, path):
        rec.paths.append(path)
        failed = rec.fail is True or (rec.fail and path.endswith(rec.fail))
        return {'verdict': False, 'reason': f'chown {path} failed'} if failed else {'verdict': True}

    monkeypatch.setattr(cruise, 'set_owner_group_permissions', owner)
    return rec


@pytest.fixture
def transfers(monkeypatch):
    """Replace the transfers' final passes: record them; ``missed`` scripts unrun transfers by kind."""
    rec = SimpleNamespace(calls=[], missed={}, stop_during=None)

    def run(gm_client, task, kind, payloads, should_stop=None):
        rec.calls.append((task, kind, payloads))
        if rec.stop_during == kind:
            worker.stop = True
        return rec.missed.get(kind, [])

    monkeypatch.setattr(cruise, 'run_transfer_jobs', run)
    worker = None

    def bind(w):
        nonlocal worker
        worker = w
    rec.bind = bind
    return rec


@pytest.fixture
def api(fake_ovdm, warehouse, tmp_path):
    """The fake API for the warehouse's cruise."""
    fake_ovdm.config['cruiseReadme'] = {'enable': True, 'filename': 'README.md', 'template': TEMPLATE}
    fake_ovdm.get_cruise_id.return_value = warehouse.cruise_id
    fake_ovdm.get_cruise_start_date.return_value = '2026/10/01 00:00'
    fake_ovdm.get_cruise_end_date.return_value = '2026/10/20 00:00'
    fake_ovdm.get_shipboard_data_warehouse_config.return_value = warehouse.config
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 4, 'name': name, 'longName': name}
    fake_ovdm.get_cruise_config.side_effect = _cruise_config
    fake_ovdm.get_collection_system_transfers.return_value = []
    fake_ovdm.get_extra_directories.return_value = []
    fake_ovdm.get_show_lowering_components.return_value = False
    fake_ovdm.get_transfer_log_dir.return_value = str(tmp_path / 'logs')
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'name': 'From_PublicData',
                                                                   'destDir': 'From_PublicData'}
    fake_ovdm.get_active_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 3, 'name': 'SCS'}, {'collectionSystemTransferID': 5, 'name': 'EM124'}]
    fake_ovdm.get_active_cruise_data_transfers.return_value = [{'cruiseDataTransferID': 2, 'name': 'Backup'}]
    return fake_ovdm


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = cruise.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: 'executed')
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def worker(monkeypatch, api, fake_gearman, gearman_base, perms, transfers):
    """A cruise worker using the fake API and Gearman client."""
    monkeypatch.setattr(cruise, 'OpenVDM', lambda: api)
    monkeypatch.setattr(cruise, 'LOGGING_FORMAT', '%(message)s', raising=False)
    w = cruise.OVDMGearmanWorker()
    w.send_job_status = Mock()
    w.send_job_data = Mock()
    transfers.bind(w)
    return w


def _setup(worker, task='exportOVDMConfig', **payload):
    """Run the worker's job setup for *task*."""
    worker.on_job_execute(_job(task, **payload))


def _config_file(warehouse):
    return warehouse.cruise_dir / 'cruise_config.json'


# --- Job setup and completion ---------------------------------------------------

def test_job_setup(worker, api, warehouse) -> None:
    """The job's cruise and dates, or the current ones; the task is set running."""
    _setup(worker, cruiseID='OTHER01', cruiseStartDate='2026/09/01 00:00')
    assert worker.cruise_id == 'OTHER01'
    assert worker.cruise_start_date == '2026/09/01 00:00'
    assert worker.cruise_end_date == '2026/10/20 00:00'
    assert worker.cruise_dir == str(warehouse.base_dir / 'OTHER01')
    api.set_running_task.assert_called_once_with(4, os.getpid(), 'H:test:1')


def test_bad_payload(worker, api) -> None:
    """A payload that isn't JSON fails the job."""
    result = worker.on_job_execute(SimpleNamespace(data='not json', handle='H:1', task='exportOVDMConfig'))
    assert _parts(result) == [('Retrieve job data', 'Fail')]
    api.set_error_task.assert_called_once_with(4, 'Failed to parse current job payload')


def test_finalize_runs_pre_finalize_hooks(worker, api, fake_gearman) -> None:
    """Finalize first runs the preFinalizeCurrentCruise hook tasks with the cruise's details."""
    _setup(worker, 'finalizeCurrentCruise')
    assert fake_gearman.jobs == [('preFinalizeCurrentCruise', {
        'cruiseID': 'TEST001', 'cruiseStartDate': '2026/10/01 00:00', 'cruiseEndDate': '2026/10/20 00:00'})]


def test_finalize_without_pre_finalize_hooks(worker, api, fake_gearman) -> None:
    """With no pre-finalize hooks, the job goes on to the task."""
    api.config['hooks'].pop('preFinalizeCurrentCruise')
    assert worker.on_job_execute(_job('finalizeCurrentCruise')) == 'executed'
    assert fake_gearman.jobs == []


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
    assert worker.on_job_execute(_job('finalizeCurrentCruise')) == 'executed'
    assert f'Task None {logged}' in caplog.text

    caplog.clear()
    worker.on_job_execute(_job('setupNewCruise'))
    worker.on_job_complete(_job('setupNewCruise'), json.dumps({'parts': []}))
    assert f'Task None {logged}' in caplog.text


def test_hook_submission_error_is_logged(worker, fake_gearman, monkeypatch, caplog) -> None:
    """Gearman failing to run the hook jobs is logged; the job carries on."""
    monkeypatch.setattr(fake_gearman, 'submit_multiple_jobs', Mock(side_effect=OSError('no gearmand')))
    assert worker.on_job_execute(_job('finalizeCurrentCruise')) == 'executed'
    assert 'Error while submitting or running pre-finalize jobs' in caplog.text

    _setup(worker, 'setupNewCruise')
    worker.on_job_complete(_job('setupNewCruise'), json.dumps({'parts': []}))
    assert 'Error while submitting or running post-hook jobs' in caplog.text


def test_setup_runs_post_hooks(worker, api, fake_gearman) -> None:
    """After Setup New Cruise, its hook tasks run; then the task goes idle."""
    _setup(worker, 'setupNewCruise')
    result = json.dumps({'parts': [{'partName': 'Step', 'result': 'Pass'}]})
    assert worker.on_job_complete(_job('setupNewCruise'), result) == result
    assert fake_gearman.tasks() == ['postSetupNewCruise']
    api.set_idle_task.assert_called_once_with(4)


def test_setup_without_post_hooks_completes(worker, api, gearman_base, monkeypatch) -> None:
    """With no setupNewCruise hooks, the job completes instead of running again."""
    api.config['hooks'].pop('setupNewCruise')
    _setup(worker, 'setupNewCruise')
    monkeypatch.setattr(gearman_base, 'on_job_execute', Mock(side_effect=AssertionError('ran again')))
    result = json.dumps({'parts': [{'partName': 'Step', 'result': 'Pass'}]})
    assert worker.on_job_complete(_job('setupNewCruise'), result) == result
    api.set_idle_task.assert_called_once_with(4)


def test_failed_job_sets_task_error(worker, api) -> None:
    """A job whose last part failed sets the task's error with its reason."""
    _setup(worker)
    worker.on_job_complete(_job('exportOVDMConfig'), FAIL)
    api.set_error_task.assert_called_once_with(4, 'it broke')


def test_failed_job_with_a_custom_task_sends_a_message(worker, api) -> None:
    """A task without an ID has no status, so a failure is posted as a message."""
    _setup(worker)
    worker.task = {'taskID': 0, 'longName': 'Something'}
    worker.on_job_complete(_job('exportOVDMConfig'), FAIL)
    api.send_msg.assert_called_once_with('Something failed', 'it broke')


def test_crash(worker, api) -> None:
    """A crash sends a failed part and sets the task's error, with where it raised."""
    _setup(worker)
    try:
        raise ValueError('boom')
    except ValueError as exc:
        info = (type(exc), exc, exc.__traceback__)
    assert worker.on_job_exception(_job('exportOVDMConfig'), info) == 'crashed'
    reason = json.loads(worker.send_job_data.call_args.args[1])[0]['reason']
    assert reason.startswith('ValueError: boom (test_cruise_worker.py, line ')
    api.set_error_task.assert_called_once_with(4, f'Worker crashed: {reason}')

    worker.task = {'taskID': 0, 'longName': 'Something'}
    worker.on_job_exception(_job('exportOVDMConfig'), (KeyError, None, None))
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


# --- Export cruise config -------------------------------------------------------

def test_export_cruise_config(worker, api, warehouse, perms) -> None:
    """Credentials and transfer settings dropped, file names, paths and the vessel added, empty values left out."""
    api.config['vessel'] = {'name': 'R/V Example', 'contact': {'email': 'ops@example.org', 'phone': ''}}
    _setup(worker)
    assert worker.export_cruise_config() == {'verdict': True}
    config = json.loads(_config_file(warehouse).read_text())

    assert config['collectionSystemTransfersConfig'] == [
        {'name': 'SCS', 'longName': 'Underway', 'description': 'Nav', 'destDir': 'SCS'}]
    assert config['extraDirectoriesConfig'] == [
        {'name': 'Dashboard_Data', 'longName': 'Dashboard', 'description': '', 'destDir': 'OpenVDM/DashboardData'}]
    for key in ('warehouseConfig', 'cruiseDataTransfersConfig', 'shipToShoreTransfersConfig', 'cruiseConfigFn',
                'loweringConfigFn', 'dataDashboardManifestFn', 'cruisePI', 'cruiseFinalizedOn',
                'loweringConfigPath'):
        assert key not in config, key
    assert config['md5SummaryFn'] == 'md5_summary.txt'
    assert config['dataDashboardManifestPath'] == 'OpenVDM/DashboardData/manifest.json'
    assert config['vessel'] == {'name': 'R/V Example', 'contact': {'email': 'ops@example.org'}}
    assert perms.paths == [str(_config_file(warehouse))]
    api.update_md5_summary.assert_called_once_with(updated=['cruise_config.json'], cruise_id='TEST001',
                                                   background=False)


def test_export_cruise_config_lowering_path(worker, api, warehouse) -> None:
    """The lowering config's path is given once the cruise has a lowering base directory; no vessel, no key."""
    api.config.pop('vessel', None)
    (warehouse.cruise_dir / 'Vehicle').mkdir()
    _setup(worker)
    worker.export_cruise_config()
    config = json.loads(_config_file(warehouse).read_text())
    assert config['loweringConfigPath'] == 'Vehicle/<loweringID>/lowering_config.json'
    assert 'vessel' not in config


def test_export_cruise_config_finalized_date(worker, warehouse) -> None:
    """Finalizing sets cruiseFinalizedOn; a later export keeps it."""
    _setup(worker)
    worker.export_cruise_config(finalize=True)
    assert json.loads(_config_file(warehouse).read_text())['cruiseFinalizedOn'] == '2026/10/22 12:00:00'
    worker.export_cruise_config()
    assert json.loads(_config_file(warehouse).read_text())['cruiseFinalizedOn'] == '2026/10/22 12:00:00'


@pytest.mark.skipif(os.geteuid() == 0, reason='root can read any file')
def test_export_cruise_config_unreadable(worker, warehouse) -> None:
    """An existing config file that can't be read fails the export."""
    _config_file(warehouse).write_text('{}')
    _config_file(warehouse).chmod(0)
    _setup(worker)
    assert worker.export_cruise_config()['reason'].startswith(
        'Unable to read the existing configuration file cruise_config.json: [Errno 13] Permission denied')


@pytest.mark.parametrize('text', ['{truncated', '[]'])
def test_export_cruise_config_not_json(worker, warehouse, text) -> None:
    """An existing config file that isn't a JSON object fails the export, keeping its finalized date (#548)."""
    _config_file(warehouse).write_text(text)
    _setup(worker)
    result = worker.export_cruise_config()
    assert result['verdict'] is False
    assert result['reason'].startswith('Unable to read the existing configuration file cruise_config.json: ')
    assert _config_file(warehouse).read_text() == text


def test_export_cruise_config_write_fails(worker, monkeypatch) -> None:
    """A config file that can't be written fails the export with the reason."""
    monkeypatch.setattr(cruise, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'full'})
    _setup(worker)
    assert worker.export_cruise_config() == {'verdict': False, 'reason': 'full'}


def test_export_cruise_config_ownership_fails(worker, api, warehouse, perms) -> None:
    """Ownership that can't be set fails the export; no MD5 update."""
    perms.fail = True
    _setup(worker)
    assert worker.export_cruise_config()['verdict'] is False
    api.update_md5_summary.assert_not_called()


# --- Cruise README --------------------------------------------------------------

def test_build_cruise_readme(worker, api, warehouse, perms) -> None:
    """Writes the README with the finalized date from the config file, and queues its MD5 update."""
    _setup(worker)
    worker.export_cruise_config(finalize=True)
    api.update_md5_summary.reset_mock()
    assert worker.build_cruise_readme() == {'verdict': True}
    text = (warehouse.cruise_dir / 'README.md').read_text()
    assert GENERATED_MARKER in text.splitlines()[0]
    assert 'TEST001' in text
    assert str(warehouse.cruise_dir / 'README.md') in perms.paths
    api.update_md5_summary.assert_called_once_with(updated=['README.md'], cruise_id='TEST001', background=False)


def test_build_cruise_readme_without_config_file(worker, warehouse, caplog) -> None:
    """Without a config file yet, the README is written without a finalized date."""
    _setup(worker)
    assert worker.build_cruise_readme() == {'verdict': True}
    assert 'Unable to read the finalized date' in caplog.text


def test_build_cruise_readme_turned_off(worker, api, warehouse) -> None:
    """Turned off in openvdm.yaml: skipped, nothing written."""
    api.config['cruiseReadme']['enable'] = False
    _setup(worker)
    assert worker.build_cruise_readme() == {'verdict': True, 'skipped': True}
    assert not (warehouse.cruise_dir / 'README.md').exists()


@pytest.mark.parametrize('block, reason', [
    ({'template': '/nowhere/readme.md.j2'}, 'README template not found: /nowhere/readme.md.j2'),
    ({'template': TEMPLATE, 'filename': '{loweringID}.md'}, "filename can't use {loweringID}"),
], ids=['no template', 'bad filename'])
def test_build_cruise_readme_bad_settings(worker, api, block, reason) -> None:
    """Settings that can't be used fail with the reason."""
    api.config['cruiseReadme'] = block
    _setup(worker)
    result = worker.build_cruise_readme()
    assert result['verdict'] is False
    assert reason in result['reason']


def test_build_cruise_readme_api_error(worker, api) -> None:
    """An API call that fails fails the README."""
    _setup(worker)
    api.get_collection_system_transfers.side_effect = OSError('API down')
    assert worker.build_cruise_readme() == {
        'verdict': False, 'reason': 'Unable to get the cruise configuration from OpenVDM: API down'}


def test_build_cruise_readme_template_error(worker, api, tmp_path) -> None:
    """A template with a syntax error fails the README, naming the line."""
    template = tmp_path / 'broken.md.j2'
    template.write_text('line one\n{% if %}\n')
    api.config['cruiseReadme'] = {'template': str(template)}
    _setup(worker)
    reason = worker.build_cruise_readme()['reason']
    assert reason.startswith(f'Unable to build the README from {template}, line 2: ')


def test_build_cruise_readme_not_ours(worker, warehouse) -> None:
    """A README OpenVDM didn't write is left alone, and the README fails."""
    (warehouse.cruise_dir / 'README.md').write_text('My own notes\n')
    _setup(worker)
    result = worker.build_cruise_readme()
    assert result['verdict'] is False
    assert "wasn't written by OpenVDM" in result['reason']
    assert (warehouse.cruise_dir / 'README.md').read_text() == 'My own notes\n'


def test_build_cruise_readme_ownership_fails(worker, api, perms) -> None:
    """Ownership that can't be set fails the README; no MD5 update."""
    perms.fail = 'README.md'
    _setup(worker)
    assert worker.build_cruise_readme()['verdict'] is False
    api.update_md5_summary.assert_not_called()


# --- PublicData -----------------------------------------------------------------

@pytest.fixture
def publicdata(warehouse, monkeypatch):
    """PublicData with two files, a From_PublicData directory with a stale file, and a fake rsync.

    ``rsync.new``/``rsync.updated`` script the copied files; ``rsync.raises`` an error.
    """
    (warehouse.publicdata_dir / 'notes.txt').write_text('notes')
    (warehouse.publicdata_dir / 'photos').mkdir()
    (warehouse.publicdata_dir / 'photos' / 'a.jpg').write_text('jpg')
    dest = warehouse.cruise_dir / 'From_PublicData'
    dest.mkdir()
    (dest / 'removed.txt').write_text('gone from PublicData')
    rsync = SimpleNamespace(new=['notes.txt', 'photos/a.jpg'], updated=[], raises=None, cmds=[])

    def run(worker, current_job, cmd, count, dest_dir):
        rsync.cmds.append(cmd)
        if rsync.raises:
            raise rsync.raises
        for path in rsync.new + rsync.updated:
            os.makedirs(os.path.dirname(os.path.join(dest_dir, path)), exist_ok=True)
            with open(os.path.join(dest_dir, path), 'w', encoding='utf-8') as copy:
                copy.write('copied')
        return list(rsync.new), list(rsync.updated)

    monkeypatch.setattr(cruise, 'run_transfer_command', run)
    return rsync


def test_transfer_publicdata(worker, api, warehouse, publicdata, perms, tmp_path) -> None:
    """Copies PublicData, removes files no longer there, logs the copy and updates the MD5 summary."""
    _setup(worker, 'rsyncPublicDataToCruiseData')
    assert worker.transfer_publicdata_dir(_job('rsyncPublicDataToCruiseData'), 10, 90) == {'verdict': True}

    cmd = publicdata.cmds[0]
    assert cmd[0] == 'rsync'
    assert cmd[-2:] == [str(warehouse.publicdata_dir), str(warehouse.cruise_dir / 'From_PublicData')]
    assert not (warehouse.cruise_dir / 'From_PublicData' / 'removed.txt').exists()
    api.update_md5_summary.assert_called_once_with(
        new=['From_PublicData/notes.txt', 'From_PublicData/photos/a.jpg'], updated=[],
        deleted=['From_PublicData/removed.txt'], cruise_id='TEST001', background=False)

    logs = sorted(os.listdir(tmp_path / 'logs'))
    assert logs[0] == 'PublicData_Exclude.log'
    assert logs[1].startswith('TEST001_PublicData_')
    assert json.loads((tmp_path / 'logs' / logs[1]).read_text())['new'] == [
        'From_PublicData/notes.txt', 'From_PublicData/photos/a.jpg']
    assert str(warehouse.cruise_dir / 'From_PublicData') in perms.paths


def test_transfer_publicdata_excluded_names(worker, publicdata, warehouse, tmp_path, caplog) -> None:
    """Files with names rsync can't be given are left out, logged and listed in the exclude log."""
    (warehouse.publicdata_dir / 'caf\u00e9.txt').write_text('menu')
    _setup(worker, 'rsyncPublicDataToCruiseData')
    assert worker.transfer_publicdata_dir(_job('rsyncPublicDataToCruiseData'), 10, 90) == {'verdict': True}
    assert 'Found 1 problem filename(s)' in caplog.text
    assert json.loads((tmp_path / 'logs' / 'PublicData_Exclude.log').read_text())['exclude'] == [
        'caf\u00e9.txt']


def test_transfer_publicdata_nothing_new(worker, api, publicdata, tmp_path) -> None:
    """With nothing copied, there's no transfer log; the MD5 summary still gets the deletions."""
    publicdata.new = []
    _setup(worker, 'rsyncPublicDataToCruiseData')
    assert worker.transfer_publicdata_dir(_job('rsyncPublicDataToCruiseData'), 10, 90) == {'verdict': True}
    assert os.listdir(tmp_path / 'logs') == ['PublicData_Exclude.log']
    assert api.update_md5_summary.call_args.kwargs['deleted'] == ['From_PublicData/removed.txt']


@pytest.mark.parametrize('setup, reason', [
    (lambda w, p, perms, mp: shutil.rmtree(w.publicdata_dir), 'PublicData directory: '),
    (lambda w, p, perms, mp: shutil.rmtree(w.cruise_dir / 'From_PublicData'),
     'From_PublicData directory: '),
    (lambda w, p, perms, mp: mp.setattr(cruise, 'output_json_data_to_file',
                                        lambda path, data: {'verdict': False, 'reason': 'full'}),
     'Error writing exclude logfile PublicData_Exclude.log'),
    (lambda w, p, perms, mp: setattr(perms, 'fail', 'PublicData_Exclude.log'),
     'Error setting ownership/permissions for transfer logfile: PublicData_Exclude.log'),
    (lambda w, p, perms, mp: mp.setattr(cruise, 'write_list_file', lambda entries, path: False),
     'Error Saving temporary rsync filelist file'),
    (lambda w, p, perms, mp: setattr(p, 'raises', TransferCommandError('rsync', 12, '')),
     'PublicData transfer failed: rsync exited with code 12'),
    (lambda w, p, perms, mp: setattr(perms, 'fail', 'From_PublicData'), 'chown '),
    (lambda w, p, perms, mp: mp.setattr(cruise, 'output_json_data_to_file',
                lambda path, data: {'verdict': 'Exclude' in path, 'reason': 'full'}),
     'Error writing transfer logfile TEST001_PublicData_'),
], ids=['no PublicData', 'no From_PublicData', 'exclude log write', 'exclude log ownership', 'file list',
        'rsync fails', 'destination ownership', 'transfer log write'])
def test_transfer_publicdata_failures(worker, api, warehouse, publicdata, perms, monkeypatch, setup,
                                      reason) -> None:
    """Each failure stops the copy with its reason; the MD5 summary isn't updated."""
    setup(warehouse, publicdata, perms, monkeypatch)
    _setup(worker, 'rsyncPublicDataToCruiseData')
    result = worker.transfer_publicdata_dir(_job('rsyncPublicDataToCruiseData'), 10, 90)
    assert result['verdict'] is False
    assert reason in result['reason']
    api.update_md5_summary.assert_not_called()


def test_transfer_publicdata_log_ownership_fails(worker, api, publicdata, perms) -> None:
    """The transfer log's ownership failing stops the copy before the MD5 update."""
    perms.fail = 'Z.log'
    _setup(worker, 'rsyncPublicDataToCruiseData')
    result = worker.transfer_publicdata_dir(_job('rsyncPublicDataToCruiseData'), 10, 90)
    assert result['reason'].startswith('Error setting ownership/permissions for transfer logfile: TEST001_PublicData_')
    api.update_md5_summary.assert_not_called()


def test_rsync_publicdata_task(worker, publicdata) -> None:
    """The task passes or fails with the copy."""
    _setup(worker, 'rsyncPublicDataToCruiseData')
    job = _job('rsyncPublicDataToCruiseData')
    assert _parts(cruise.task_rsync_publicdata_to_cruise_data(worker, job)) == [('Transfer files', 'Pass')]
    publicdata.raises = TransferCommandError('rsync', 12, '')
    assert _parts(cruise.task_rsync_publicdata_to_cruise_data(worker, job)) == [('Transfer files', 'Fail')]


# --- Export and Rebuild README tasks --------------------------------------------

def test_export_task(worker, api, warehouse) -> None:
    """Exports the config and writes the README."""
    _setup(worker)
    result = cruise.task_export_cruise_config(worker, _job('exportOVDMConfig'))
    assert _parts(result) == [('Export cruise config data to file', 'Pass'), ('Write cruise README', 'Pass')]
    assert (warehouse.cruise_dir / 'README.md').is_file()


def test_export_task_failures(worker, api, warehouse, monkeypatch) -> None:
    """A failed export ends the task; a failed README is its last part, so fails it, without a message."""
    (warehouse.cruise_dir / 'README.md').write_text('mine\n')
    _setup(worker)
    result = cruise.task_export_cruise_config(worker, _job('exportOVDMConfig'))
    assert _parts(result)[-1] == ('Write cruise README', 'Fail')
    api.send_msg.assert_not_called()

    monkeypatch.setattr(cruise, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    result = cruise.task_export_cruise_config(worker, _job('exportOVDMConfig'))
    assert _parts(result) == [('Export cruise config data to file', 'Fail')]


def test_export_task_readme_off(worker, api) -> None:
    """With the README turned off, there's no README part."""
    api.config['cruiseReadme']['enable'] = False
    _setup(worker)
    assert _parts(cruise.task_export_cruise_config(worker, _job('exportOVDMConfig'))) == [
        ('Export cruise config data to file', 'Pass')]


@pytest.mark.parametrize('setup, expected', [
    (lambda w, a: None, 'Pass'),
    (lambda w, a: a.config['cruiseReadme'].update(enable=False), 'Fail'),
    (lambda w, a: (w.cruise_dir / 'README.md').write_text('mine\n'), 'Fail'),
], ids=['written', 'turned off', 'not ours'])
def test_rebuild_readme_task(worker, api, warehouse, setup, expected) -> None:
    """Passes when written; fails when turned off (nothing was rebuilt) or when it can't be written."""
    setup(warehouse, api)
    _setup(worker, 'rebuildCruiseReadme')
    result = json.loads(cruise.task_rebuild_cruise_readme(worker, _job('rebuildCruiseReadme')))
    assert result['parts'][-1]['result'] == expected
    if api.config['cruiseReadme'].get('enable') is False:
        assert result['parts'][-1]['reason'] == 'The cruise README is turned off (cruiseReadme in openvdm.yaml)'


# --- Setup New Cruise -----------------------------------------------------------

@pytest.fixture
def du(fake_run):
    """``du -sb`` reports the cruise's size."""
    fake_run.on('du', stdout='12345\t/cruise\n')
    return fake_run


def test_setup_new_cruise(worker, api, warehouse, fake_gearman, du) -> None:
    """Creates the directories, MD5 summary, config, README and dashboard, clears PublicData, sets sizes."""
    (warehouse.publicdata_dir / 'last_cruise.txt').write_text('old')
    _setup(worker, 'setupNewCruise')
    result = cruise.task_setup_new_cruise(worker, _job('setupNewCruise', cruiseID='TEST001'))

    assert _parts(result) == [
        ('Create cruise data directory structure', 'Pass'), ('Create MD5 summary files', 'Pass'),
        ('Export cruise config data to file', 'Pass'), ('Write cruise README', 'Pass'),
        ('Create data dashboard directory structure and manifest file', 'Pass'),
        ('Clear out PublicData directory', 'Pass')]
    assert fake_gearman.tasks() == ['createCruiseDirectory', 'rebuildMD5Summary', 'rebuildDataDashboard']
    assert fake_gearman.jobs[0][1] == {'cruiseID': 'TEST001'}, "the job's own payload"
    assert os.listdir(warehouse.publicdata_dir) == []
    assert du.calls[0].cmd == ['du', '-sb', str(warehouse.cruise_dir)]
    api.set_cruise_size.assert_called_once_with('12345')
    api.set_lowering_size.assert_called_once_with('0')


def test_setup_new_cruise_without_publicdata(worker, api, warehouse, fake_run) -> None:
    """With transferPublicData off, PublicData is left alone; a failed du records a size of 0."""
    api.config['transferPublicData'] = False
    fake_run.on('du', returncode=1)
    (warehouse.publicdata_dir / 'keep.txt').write_text('keep')
    _setup(worker, 'setupNewCruise')
    result = cruise.task_setup_new_cruise(worker, _job('setupNewCruise'))
    assert ('Clear out PublicData directory', 'Pass') not in _parts(result)
    assert (warehouse.publicdata_dir / 'keep.txt').exists()
    api.set_cruise_size.assert_called_once_with('0')


@pytest.mark.parametrize('task, part', [
    ('createCruiseDirectory', 'Create cruise data directory structure'),
    ('rebuildMD5Summary', 'Create MD5 summary files'),
    ('rebuildDataDashboard', 'Create data dashboard directory structure and manifest file'),
])
def test_setup_new_cruise_job_fails(worker, fake_gearman, du, task, part) -> None:
    """A step run by another worker that fails ends the setup with its reason."""
    fake_gearman.results[task] = FAIL
    _setup(worker, 'setupNewCruise')
    result = json.loads(cruise.task_setup_new_cruise(worker, _job('setupNewCruise')))
    assert result['parts'][-1] == {'partName': part, 'result': 'Fail', 'reason': 'it broke'}


def test_setup_new_cruise_export_fails(worker, monkeypatch, du) -> None:
    """A failed config export ends the setup."""
    monkeypatch.setattr(cruise, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    _setup(worker, 'setupNewCruise')
    assert _parts(cruise.task_setup_new_cruise(worker, _job('setupNewCruise')))[-1] == \
        ('Export cruise config data to file', 'Fail')


def test_setup_new_cruise_readme_fails(worker, api, warehouse, du) -> None:
    """A README that can't be written is reported, with a message, and the setup carries on."""
    (warehouse.cruise_dir / 'README.md').write_text('mine\n')
    _setup(worker, 'setupNewCruise')
    parts = _parts(cruise.task_setup_new_cruise(worker, _job('setupNewCruise')))
    assert ('Write cruise README', 'Fail') in parts
    assert parts[-1] == ('Clear out PublicData directory', 'Pass')
    assert api.send_msg.call_args.args[0] == 'Cruise README not written'


def test_setup_new_cruise_clear_publicdata_fails(worker, warehouse, du) -> None:
    """PublicData that can't be cleared fails the setup."""
    warehouse.publicdata_dir.rmdir()
    _setup(worker, 'setupNewCruise')
    assert _parts(cruise.task_setup_new_cruise(worker, _job('setupNewCruise')))[-1] == \
        ('Clear out PublicData directory', 'Fail')


# --- Finalize Current Cruise ----------------------------------------------------

def test_finalize(worker, api, warehouse, fake_gearman, transfers, publicdata) -> None:
    """Final transfer passes, PublicData, the finalized config and README, post-finalize hooks, then CDTs."""
    _setup(worker, 'finalizeCurrentCruise')
    fake_gearman.jobs.clear()
    result = cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise'))

    assert _parts(result) == [
        ('Verify cruise directory exists', 'Pass'), ('Run collection system transfers jobs', 'Pass'),
        ('Transfer PublicData files', 'Pass'), ('Export cruise config data to file', 'Pass'),
        ('Write cruise README', 'Pass'), ('Run post-finalize tasks', 'Pass'),
        ('Run cruise data transfers jobs', 'Pass')]

    (cst_task, cst_kind, cst_jobs), (cdt_task, cdt_kind, cdt_jobs) = transfers.calls
    assert (cst_task, cst_kind, cdt_task, cdt_kind) == (
        'runCollectionSystemTransfer', CST, 'runCruiseDataTransfer', CDT)
    assert cst_jobs[3] == {'cruiseID': 'TEST001', 'cruiseStartDate': '2026/10/01 00:00', 'systemStatus': 'On',
                           'collectionSystemTransfer': {'collectionSystemTransferID': 3}}
    assert list(cst_jobs) == [3, 5]
    assert cdt_jobs[2]['cruiseDataTransfer'] == {'cruiseDataTransferID': 2}
    assert json.loads(_config_file(warehouse).read_text())['cruiseFinalizedOn'] == '2026/10/22 12:00:00'
    assert fake_gearman.jobs == [('postFinalizeCurrentCruise', {
        'cruiseID': 'TEST001', 'cruiseStartDate': '2026/10/01 00:00', 'cruiseEndDate': '2026/10/20 00:00'})]


def test_finalize_without_publicdata_or_hooks(worker, api, fake_gearman, transfers) -> None:
    """With transferPublicData off and no post-finalize hooks, those steps run nothing."""
    api.config['transferPublicData'] = False
    api.config['hooks'].pop('finalizeCurrentCruise')
    _setup(worker, 'finalizeCurrentCruise')
    fake_gearman.jobs.clear()
    parts = _parts(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))
    assert ('Transfer PublicData files', 'Pass') not in parts
    assert fake_gearman.jobs == []
    assert parts[-1] == ('Run cruise data transfers jobs', 'Pass')


def test_finalize_no_cruise_directory(worker, warehouse, transfers) -> None:
    """Without the cruise directory, nothing runs."""
    warehouse.cruise_dir.rmdir()
    _setup(worker, 'finalizeCurrentCruise')
    assert _parts(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise'))) == [
        ('Verify cruise directory exists', 'Fail')]
    assert transfers.calls == []


@pytest.mark.parametrize('kind, part', [(CST, 'Run collection system transfers jobs'),
                                        (CDT, 'Run cruise data transfers jobs')])
def test_finalize_stopped(worker, transfers, publicdata, kind, part) -> None:
    """Stopped during a final pass: ends there, ignored rather than failed (#487)."""
    transfers.stop_during = kind
    _setup(worker, 'finalizeCurrentCruise')
    result = json.loads(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))
    assert result['parts'][-1] == {'partName': part, 'result': 'Ignore', 'reason': 'Stopped'}
    assert len(transfers.calls) == (1 if kind == CST else 2)


def test_finalize_missed_transfers(worker, api, transfers, publicdata) -> None:
    """Transfers still running after the wait are reported by name, and finalize carries on (#480)."""
    transfers.missed = {CST: [5], CDT: [2]}
    _setup(worker, 'finalizeCurrentCruise')
    parts = json.loads(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))['parts']
    assert parts[-1]['result'] == 'Pass'
    titles = [call.args[0] for call in api.send_msg.call_args_list]
    assert titles == ['Finalizing TEST001: collection system transfers still running',
                      'Finalizing TEST001: cruise data transfers still running']
    assert 'EM124' in api.send_msg.call_args_list[0].args[1]
    assert 'Backup' in api.send_msg.call_args_list[1].args[1]


def test_finalize_publicdata_fails(worker, publicdata, transfers) -> None:
    """A failed PublicData copy ends finalize before the config export and CDTs."""
    publicdata.raises = TransferCommandError('rsync', 23, '')
    _setup(worker, 'finalizeCurrentCruise')
    assert _parts(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))[-1] == \
        ('Transfer PublicData files', 'Fail')
    assert len(transfers.calls) == 1


def test_finalize_export_fails(worker, api, monkeypatch, transfers) -> None:
    """A failed config export ends finalize before the CDTs."""
    api.config['transferPublicData'] = False
    monkeypatch.setattr(cruise, 'output_json_data_to_file', lambda path, data: {'verdict': False, 'reason': 'x'})
    _setup(worker, 'finalizeCurrentCruise')
    assert _parts(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))[-1] == \
        ('Export cruise config data to file', 'Fail')
    assert len(transfers.calls) == 1


def test_finalize_readme_fails(worker, api, warehouse, transfers) -> None:
    """A README that can't be written is reported with a message; finalize carries on to the CDTs."""
    api.config['transferPublicData'] = False
    (warehouse.cruise_dir / 'README.md').write_text('mine\n')
    _setup(worker, 'finalizeCurrentCruise')
    parts = _parts(cruise.task_finalize_current_cruise(worker, _job('finalizeCurrentCruise')))
    assert ('Write cruise README', 'Fail') in parts
    assert parts[-1] == ('Run cruise data transfers jobs', 'Pass')
    assert api.send_msg.call_args.args[0] == 'Cruise README not written'
