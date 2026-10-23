"""Tests for the cruise and lowering directory workers (#511).

``cruise_directory.py`` and ``lowering_directory.py`` create and repair the
directory trees in the warehouse and set their ownership and permissions.
Directories are created for real in the ``warehouse`` fixture; ownership and
permission changes (which need root) are replaced with recorders.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import cruise_directory
from server.workers import lowering_directory

CST_SCS = {'name': 'SCS', 'destDir': 'SCS'}
CST_PUBLICDATA = {'name': 'From_PublicData', 'destDir': 'From_PublicData'}
CST_PER_LOWERING = {'name': 'Video', 'destDir': 'Video/{loweringID}'}
REQUIRED = [{'name': 'Dashboard_Data', 'destDir': 'OpenVDM/DashboardData', 'required': 1},
            {'name': 'From_PublicData', 'destDir': 'From_PublicData', 'required': 1}]
EXTRA = {'name': 'Products', 'destDir': 'Products/{cruiseID}', 'required': 0}
EXTRA_PER_LOWERING = {'name': 'Dive_Logs', 'destDir': 'Dive_Logs/{loweringID}', 'required': 0}


def _job(task, **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = cruise_directory.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: json.dumps({'parts': []}))
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def perms(monkeypatch):
    """Record ``set_owner_group_permissions()`` and ``lockdown_directory()`` calls.

    Set ``owner_fail`` or ``lockdown_fail`` to a reason to make them fail.
    """
    rec = SimpleNamespace(owner=[], lockdown=[], owner_fail=None, lockdown_fail=None)

    def owner(user, path):
        rec.owner.append((user, path))
        return {'verdict': False, 'reason': rec.owner_fail} if rec.owner_fail else {'verdict': True}

    def lockdown(base_dir, exempt_dirs=None):
        rec.lockdown.append((base_dir, exempt_dirs))
        return {'verdict': False, 'reason': rec.lockdown_fail} if rec.lockdown_fail else {'verdict': True}

    for module in (cruise_directory, lowering_directory):
        monkeypatch.setattr(module, 'set_owner_group_permissions', owner)
    monkeypatch.setattr(cruise_directory, 'lockdown_directory', lockdown)
    return rec


@pytest.fixture
def api(fake_ovdm, warehouse):
    """The fake API: one cruise-level transfer, the required and one optional extra directory."""
    fake_ovdm.get_cruise_id.return_value = warehouse.cruise_id
    fake_ovdm.get_lowering_id.return_value = None
    fake_ovdm.get_shipboard_data_warehouse_config.return_value = warehouse.config
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 7, 'name': name, 'longName': name}
    fake_ovdm.get_show_lowering_components.return_value = False
    fake_ovdm.get_required_extra_directories.return_value = [dict(d) for d in REQUIRED]
    fake_ovdm.get_active_collection_system_transfers.return_value = [dict(CST_SCS)]
    fake_ovdm.get_active_extra_directories.return_value = [dict(d) for d in REQUIRED] + [dict(EXTRA)]
    return fake_ovdm


def _worker(module, monkeypatch, fake_ovdm):
    """A worker of *module* using the fake API."""
    monkeypatch.setattr(module, 'OpenVDM', lambda: fake_ovdm)
    worker = module.OVDMGearmanWorker()
    worker.send_job_status = Mock()
    worker.send_job_data = Mock()
    return worker


# --- Cruise directory -----------------------------------------------------------

@pytest.fixture
def cruise_worker(monkeypatch, api, gearman_base, perms):
    """A cruise directory worker."""
    return _worker(cruise_directory, monkeypatch, api)


def _run_cruise(worker, task_fn, task, **payload):
    """Set the worker up for *task* as Gearman would, then run *task_fn*."""
    worker.on_job_execute(_job(task, **payload))
    return task_fn(worker, _job(task, **payload))


def test_cruise_job_setup(cruise_worker, api, warehouse) -> None:
    """The job's cruise and lowering, or the current ones; a custom task sets no task status."""
    cruise_worker.on_job_execute(_job('createCruiseDirectory', cruiseID='OTHER01', loweringID='DIVE01'))
    assert cruise_worker.cruise_id == 'OTHER01'
    assert cruise_worker.lowering_id == 'DIVE01'
    assert cruise_worker.cruise_dir == os.path.join(warehouse.config['shipboardDataWarehouseBaseDir'], 'OTHER01')
    assert cruise_worker.task['longName'] == 'Creating cruise directory'
    api.set_running_task.assert_not_called()

    cruise_worker.on_job_execute(_job('rebuildCruiseDirectory'))
    assert cruise_worker.cruise_id == warehouse.cruise_id
    assert cruise_worker.lowering_id is None
    api.set_running_task.assert_called_once_with(7, os.getpid(), 'H:test:1')


@pytest.mark.xfail(strict=True, reason="#544: the task isn't looked up before the payload")
def test_cruise_bad_payload(cruise_worker, api) -> None:
    """A payload that isn't JSON fails the job; a custom task sends a message instead of a status."""
    result = cruise_worker.on_job_execute(SimpleNamespace(data='not json', handle='H:1',
                                                          task='createCruiseDirectory'))
    assert _parts(result) == [('Retrieve job data', 'Fail')]
    api.send_msg.assert_called_once_with('Creating cruise directory failed', 'Failed to parse current job payload')


def test_keyword_replace(cruise_worker, warehouse) -> None:
    """Placeholders are replaced and trailing slashes dropped; '/' and non-strings are left alone."""
    cruise_worker.on_job_execute(_job('createCruiseDirectory'))
    assert cruise_worker.keyword_replace('{loweringDataBaseDir}/{cruiseID}/{loweringID}/') == \
        'Vehicle/TEST001/{loweringID}', 'no lowering: left as it is'
    assert cruise_worker.keyword_replace('/') == '/'
    assert cruise_worker.keyword_replace(None) is None
    assert cruise_worker.build_dest_dir('') is None
    cruise_worker.lowering_id = 'DIVE01'
    assert cruise_worker.keyword_replace('{loweringID}') == 'DIVE01'


def test_cruise_directory_list(cruise_worker, api, warehouse) -> None:
    """Required and optional extra directories and the cruise-level transfers' directories, once each."""
    cruise_worker.on_job_execute(_job('createCruiseDirectory'))
    cruise_dir = str(warehouse.cruise_dir)
    assert sorted(cruise_worker.build_directorylist()) == sorted(os.path.join(cruise_dir, d) for d in (
        'OpenVDM/DashboardData', 'From_PublicData', 'SCS', 'Products/TEST001'))
    api.get_active_collection_system_transfers.assert_called_once_with(lowering=False)
    api.get_active_extra_directories.assert_called_once_with(lowering=False)


def test_cruise_directory_list_without_publicdata(cruise_worker, api, warehouse) -> None:
    """With transferPublicData off, there's no From_PublicData directory from either list."""
    api.config['transferPublicData'] = False
    api.get_active_collection_system_transfers.return_value = [dict(CST_SCS), dict(CST_PUBLICDATA)]
    cruise_worker.on_job_execute(_job('createCruiseDirectory'))
    dirs = cruise_worker.build_directorylist()
    assert os.path.join(str(warehouse.cruise_dir), 'From_PublicData') not in dirs
    assert os.path.join(str(warehouse.cruise_dir), 'SCS') in dirs


def test_cruise_directory_list_lowerings(cruise_worker, api, warehouse) -> None:
    """The lowering base directory with lowerings shown; per-lowering directories only with a lowering."""
    api.get_show_lowering_components.return_value = True
    api.get_active_collection_system_transfers.return_value = [dict(CST_SCS), dict(CST_PER_LOWERING)]
    api.get_active_extra_directories.return_value = [dict(EXTRA_PER_LOWERING)]
    cruise_dir = str(warehouse.cruise_dir)

    cruise_worker.on_job_execute(_job('createCruiseDirectory'))
    dirs = cruise_worker.build_directorylist()
    assert os.path.join(cruise_dir, 'Vehicle') in dirs
    assert not [d for d in dirs if 'loweringID' in d]

    cruise_worker.on_job_execute(_job('createCruiseDirectory', loweringID='DIVE01'))
    dirs = cruise_worker.build_directorylist()
    assert os.path.join(cruise_dir, 'Video', 'DIVE01') in dirs
    assert os.path.join(cruise_dir, 'Dive_Logs', 'DIVE01') in dirs


def test_create_cruise_directory(cruise_worker, api, warehouse, perms) -> None:
    """Creates the tree and sets its ownership; the job completes with the task idle."""
    warehouse.cruise_dir.rmdir()
    result = _run_cruise(cruise_worker, cruise_directory.task_create_cruise_directory,
                         'createCruiseDirectory')
    assert _parts(result) == [('Verify base directory exists', 'Pass'),
                              ('Verify cruise directory does not exists', 'Pass'),
                              ('Build directory list', 'Pass'), ('Create directories', 'Pass'),
                              ('Set cruise directory ownership/permissions', 'Pass')]
    for directory in ('SCS', 'From_PublicData', 'OpenVDM/DashboardData', 'Products/TEST001'):
        assert (warehouse.cruise_dir / directory).is_dir()
    assert perms.owner == [('survey', str(warehouse.cruise_dir))]
    assert perms.lockdown == [], 'showOnlyCurrentCruiseDir is off'

    cruise_worker.on_job_complete(_job('createCruiseDirectory'), result)
    api.set_idle_task.assert_called_once_with(0)


def test_create_cruise_directory_locks_down_others(cruise_worker, api, warehouse, perms) -> None:
    """With showOnlyCurrentCruiseDir, the other cruises' read permissions are cleared."""
    api.config['showOnlyCurrentCruiseDir'] = True
    warehouse.cruise_dir.rmdir()
    result = _run_cruise(cruise_worker, cruise_directory.task_create_cruise_directory,
                         'createCruiseDirectory')
    assert ('Clear CruiseData directory read permissions', 'Pass') in _parts(result)
    assert perms.lockdown == [(str(warehouse.base_dir), [str(warehouse.cruise_dir)])]


@pytest.mark.parametrize('setup, part', [
    (lambda w, a, p: w.base_dir.rename(w.base_dir.with_name('moved')), 'Verify base directory exists'),
    (lambda w, a, p: None, 'Verify cruise directory does not exists'),
    (lambda w, a, p: (w.cruise_dir.rmdir(), a.get_required_extra_directories.configure_mock(return_value=[]),
                      a.get_active_collection_system_transfers.configure_mock(return_value=[]),
                      a.get_active_extra_directories.configure_mock(return_value=[])),
     'Build directory list'),
    (lambda w, a, p: (w.cruise_dir.rmdir(), w.cruise_dir.write_text('a file')), 'Verify cruise directory does not exists'),
    (lambda w, a, p: (w.cruise_dir.rmdir(), a.config.update(showOnlyCurrentCruiseDir=True),
                      setattr(p, 'lockdown_fail', 'denied')),
     'Clear CruiseData directory read permissions'),
    (lambda w, a, p: (w.cruise_dir.rmdir(), setattr(p, 'owner_fail', 'denied')),
     'Set cruise directory ownership/permissions'),
], ids=['no base directory', 'cruise exists', 'nothing to create', 'cruise is a file', 'lockdown fails',
        'ownership fails'])
def test_create_cruise_directory_failures(cruise_worker, api, warehouse, perms, setup, part) -> None:
    """Each check that fails ends the job with that part failed, and a message for the custom task."""
    setup(warehouse, api, perms)
    result = _run_cruise(cruise_worker, cruise_directory.task_create_cruise_directory,
                         'createCruiseDirectory')
    assert _parts(result)[-1] == (part, 'Fail')

    cruise_worker.on_job_complete(_job('createCruiseDirectory'), result)
    api.send_msg.assert_called_once_with('Creating cruise directory failed',
                                         json.loads(result)['parts'][-1]['reason'])
    api.set_error_task.assert_not_called()


@pytest.mark.skipif(os.geteuid() == 0, reason='root can write to a read-only directory')
def test_create_cruise_directories_fail(cruise_worker, warehouse) -> None:
    """Directories that can't be created fail the job and are named."""
    warehouse.cruise_dir.rmdir()
    warehouse.base_dir.chmod(0o555)
    try:
        result = _run_cruise(cruise_worker, cruise_directory.task_create_cruise_directory,
                             'createCruiseDirectory')
    finally:
        warehouse.base_dir.chmod(0o755)
    assert _parts(result)[-1] == ('Create directories', 'Fail')
    assert 'Unable to create directory: ' + str(warehouse.cruise_dir) in \
        json.loads(result)['parts'][-1]['reason']


def test_rebuild_cruise_directory(cruise_worker, api, warehouse, perms) -> None:
    """Creates the missing directories in an existing cruise; the API task goes idle."""
    (warehouse.cruise_dir / 'SCS').mkdir()
    (warehouse.cruise_dir / 'SCS' / 'keep.txt').write_text('data')
    api.config['showOnlyCurrentCruiseDir'] = True
    result = _run_cruise(cruise_worker, cruise_directory.task_rebuild_cruise_directory,
                         'rebuildCruiseDirectory')
    assert _parts(result) == [('Verify cruise directory exists', 'Pass'),
                              ('Clear CruiseData directory read permissions', 'Pass'),
                              ('Build directory list', 'Pass'), ('Create directories', 'Pass'),
                              ('Set directory ownership/permissions', 'Pass')]
    assert (warehouse.cruise_dir / 'SCS' / 'keep.txt').read_text() == 'data'
    assert (warehouse.cruise_dir / 'Products' / 'TEST001').is_dir()

    cruise_worker.on_job_complete(_job('rebuildCruiseDirectory'), result)
    api.set_idle_task.assert_called_once_with(7)


@pytest.mark.parametrize('setup, part', [
    (lambda w, a, p: w.cruise_dir.rmdir(), 'Verify cruise directory exists'),
    (lambda w, a, p: (a.config.update(showOnlyCurrentCruiseDir=True), setattr(p, 'lockdown_fail', 'denied')),
     'Clear CruiseData directory read permissions'),
    (lambda w, a, p: (w.cruise_dir / 'SCS').write_text('a file in the way'), 'Create directories'),
    (lambda w, a, p: setattr(p, 'owner_fail', 'denied'), 'Set directory ownership/permissions'),
], ids=['no cruise directory', 'lockdown fails', 'create fails', 'ownership fails'])
def test_rebuild_cruise_directory_failures(cruise_worker, api, warehouse, perms, setup, part) -> None:
    """Each failure ends the job with that part failed and sets the API task's error."""
    setup(warehouse, api, perms)
    if part == 'Create directories':
        api.get_active_collection_system_transfers.return_value = [{'name': 'SCS', 'destDir': 'SCS/raw'}]
    result = _run_cruise(cruise_worker, cruise_directory.task_rebuild_cruise_directory,
                         'rebuildCruiseDirectory')
    assert _parts(result)[-1] == (part, 'Fail')

    cruise_worker.on_job_complete(_job('rebuildCruiseDirectory'), result)
    api.set_error_task.assert_called_once_with(7, json.loads(result)['parts'][-1]['reason'])


def test_set_cruisedata_permissions(cruise_worker, api, warehouse, perms) -> None:
    """Locks down the other cruises (if set) and sets the cruise directory's ownership."""
    api.config['showOnlyCurrentCruiseDir'] = True
    result = _run_cruise(cruise_worker, cruise_directory.task_set_cruisedata_directory_permissions,
                         'setCruiseDataDirectoryPermissions')
    assert _parts(result) == [('Clear CruiseData directory read permissions', 'Pass'),
                              ('Set Directory permissions for current cruise', 'Pass')]
    assert perms.lockdown == [(str(warehouse.base_dir), [str(warehouse.cruise_dir)])]
    assert perms.owner == [('survey', str(warehouse.cruise_dir))]


@pytest.mark.parametrize('setup, part', [
    (lambda w, a, p: (a.config.update(showOnlyCurrentCruiseDir=True), setattr(p, 'lockdown_fail', 'denied')),
     'Clear CruiseData directory read permissions'),
    (lambda w, a, p: w.cruise_dir.rmdir(), 'Set directory permissions for current cruise'),
], ids=['lockdown fails', 'no cruise directory'])
def test_set_cruisedata_permissions_failures(cruise_worker, api, warehouse, perms, setup, part) -> None:
    """A failed lockdown, or no cruise directory, fails the job."""
    setup(warehouse, api, perms)
    result = _run_cruise(cruise_worker, cruise_directory.task_set_cruisedata_directory_permissions,
                         'setCruiseDataDirectoryPermissions')
    assert _parts(result)[-1] == (part, 'Fail')


@pytest.mark.xfail(strict=True, reason='#545: the ownership result is ignored')
def test_set_cruisedata_permissions_ownership_fails(cruise_worker, warehouse, perms) -> None:
    """Ownership that can't be set fails the job, as in the create and rebuild tasks."""
    perms.owner_fail = 'chown failed'
    result = _run_cruise(cruise_worker, cruise_directory.task_set_cruisedata_directory_permissions,
                         'setCruiseDataDirectoryPermissions')
    assert json.loads(result)['parts'][-1] == {'partName': 'Set directory permissions for current cruise',
                                               'result': 'Fail', 'reason': 'chown failed'}


# --- Shared job handling (the lowering worker's is the same code) ---------------

@pytest.mark.parametrize('module, task', [(cruise_directory, 'createCruiseDirectory'),
                                          (lowering_directory, 'createLoweringDirectory')])
def test_crash_custom_task(monkeypatch, api, gearman_base, module, task) -> None:
    """A crash in a custom task sends a failed part and an OpenVDM message, with where it raised."""
    worker = _worker(module, monkeypatch, api)
    worker.on_job_execute(_job(task, loweringID='DIVE01'))
    try:
        raise ValueError('boom')
    except ValueError as exc:
        info = (type(exc), exc, exc.__traceback__)
    assert worker.on_job_exception(_job(task), info) == 'crashed'
    part = json.loads(worker.send_job_data.call_args.args[1])[0]
    assert part['partName'] == 'Worker crashed'
    assert part['reason'].startswith('ValueError: boom (test_directory_workers.py, line ')
    api.send_msg.assert_called_once()
    api.set_error_task.assert_not_called()


@pytest.mark.parametrize('module, task', [(cruise_directory, 'rebuildCruiseDirectory'),
                                          (lowering_directory, 'rebuildLoweringDirectory')])
def test_crash_api_task(monkeypatch, api, gearman_base, module, task) -> None:
    """A crash in an API task sets its error; one without a message or traceback still says what."""
    worker = _worker(module, monkeypatch, api)
    worker.on_job_execute(_job(task, loweringID='DIVE01'))
    worker.on_job_exception(_job(task), (KeyError, None, None))
    api.set_error_task.assert_called_once_with(7, 'Worker crashed: KeyError (unknown, line ?)')


@pytest.mark.parametrize('module', [cruise_directory, lowering_directory])
def test_stop_and_quit(monkeypatch, api, gearman_base, module) -> None:
    """Stop sets the flag; quit also shuts the worker down."""
    worker = _worker(module, monkeypatch, api)
    worker.stop_task()
    assert worker.stop is True
    worker.stop = False
    worker.shutdown = Mock()
    worker.quit_worker()
    assert worker.stop is True
    worker.shutdown.assert_called_once()


# --- Lowering directory ---------------------------------------------------------

@pytest.fixture
def lowering_worker(monkeypatch, api, gearman_base, perms, warehouse):
    """A lowering directory worker, with DIVE01 the current lowering and its base directory created."""
    api.get_lowering_id.return_value = 'DIVE01'
    api.get_active_collection_system_transfers.side_effect = lambda cruise=True, lowering=True: (
        [{'name': 'ROV_Video', 'destDir': 'Video'}] if not cruise else [dict(CST_SCS), dict(CST_PER_LOWERING)])
    api.get_active_extra_directories.side_effect = lambda cruise=True, lowering=True: (
        [{'name': 'Frames', 'destDir': 'Frames/{loweringID}', 'required': 0}] if not cruise
        else [dict(EXTRA), dict(EXTRA_PER_LOWERING)])
    (warehouse.cruise_dir / 'Vehicle').mkdir()
    return _worker(lowering_directory, monkeypatch, api)


def _run_lowering(worker, task_fn, task, **payload):
    """Set the worker up for *task* as Gearman would, then run *task_fn*."""
    worker.on_job_execute(_job(task, **payload))
    return task_fn(worker, _job(task, **payload))


def test_lowering_job_setup(lowering_worker, warehouse) -> None:
    """The lowering's directories, from the job or the current lowering."""
    lowering_worker.on_job_execute(_job('createLoweringDirectory', loweringID='DIVE02'))
    assert lowering_worker.lowering_dir == os.path.join('Vehicle', 'DIVE02')
    assert lowering_worker.lowering_base_dir == str(warehouse.cruise_dir / 'Vehicle')
    assert lowering_worker.lowering_full_dir == str(warehouse.cruise_dir / 'Vehicle' / 'DIVE02')
    lowering_worker.on_job_execute(_job('createLoweringDirectory'))
    assert lowering_worker.lowering_id == 'DIVE01'


@pytest.mark.parametrize('data', [
    pytest.param('not json', marks=pytest.mark.xfail(strict=True, reason="#544: the task isn't looked up before the payload")),
    json.dumps({'loweringID': ''})])
def test_lowering_job_needs_a_payload_and_lowering(lowering_worker, api, data) -> None:
    """A bad payload, or no lowering, fails the job."""
    api.get_lowering_id.return_value = None
    result = lowering_worker.on_job_execute(SimpleNamespace(data=data, handle='H:1',
                                                            task='createLoweringDirectory'))
    assert _parts(result)[0][1] == 'Fail'
    api.send_msg.assert_called_once()


def test_lowering_directory_list(lowering_worker, warehouse) -> None:
    """The lowering directory, its transfers' and extra directories, and per-lowering ones elsewhere."""
    lowering_worker.on_job_execute(_job('createLoweringDirectory'))
    cruise_dir = str(warehouse.cruise_dir)
    lowering_dir = os.path.join(cruise_dir, 'Vehicle', 'DIVE01')
    assert sorted(lowering_worker.build_directorylist()) == sorted([
        lowering_dir, os.path.join(lowering_dir, 'Video'), os.path.join(lowering_dir, 'Frames', 'DIVE01'),
        os.path.join(cruise_dir, 'Video', 'DIVE01'), os.path.join(cruise_dir, 'Dive_Logs', 'DIVE01')])
    assert lowering_worker.keyword_replace(None) is None
    assert lowering_worker.keyword_replace('/') == '/'
    assert lowering_worker.build_dest_dir(None) is None


def test_create_lowering_directory(lowering_worker, api, warehouse, perms) -> None:
    """Creates the lowering's tree and sets its ownership."""
    result = _run_lowering(lowering_worker, lowering_directory.task_create_lowering_directory,
                           'createLoweringDirectory')
    assert _parts(result) == [('Verify cruise directory exists', 'Pass'),
                              ('Verify lowering base directory exists', 'Pass'),
                              ('Verify lowering directory does not exists', 'Pass'),
                              ('Build Directory List', 'Pass'), ('Create Directories', 'Pass'),
                              ('Set lowering directory ownership/permissions', 'Pass')]
    lowering_dir = warehouse.cruise_dir / 'Vehicle' / 'DIVE01'
    assert (lowering_dir / 'Video').is_dir()
    assert (warehouse.cruise_dir / 'Dive_Logs' / 'DIVE01').is_dir()
    assert perms.owner == [('survey', str(lowering_dir))]

    lowering_worker.on_job_complete(_job('createLoweringDirectory'), result)
    api.set_idle_task.assert_called_once_with(0)


@pytest.mark.parametrize('setup, part', [
    (lambda w, p: w.cruise_dir.joinpath('Vehicle').rmdir() or w.cruise_dir.rmdir(),
     'Verify cruise directory exists'),
    (lambda w, p: w.cruise_dir.joinpath('Vehicle').rmdir(), 'Verify lowering base directory exists'),
    (lambda w, p: w.cruise_dir.joinpath('Vehicle', 'DIVE01').mkdir(), 'Verify lowering directory does not exists'),
    (lambda w, p: w.cruise_dir.joinpath('Video').write_text('a file in the way'), 'Create Directories'),
    (lambda w, p: setattr(p, 'owner_fail', 'denied'), 'Set lowering directory ownership/permissions'),
], ids=['no cruise directory', 'no lowering base directory', 'lowering exists', 'create fails',
        'ownership fails'])
def test_create_lowering_directory_failures(lowering_worker, warehouse, perms, setup, part) -> None:
    """Each failed check ends the job with that part failed."""
    setup(warehouse, perms)
    result = _run_lowering(lowering_worker, lowering_directory.task_create_lowering_directory,
                           'createLoweringDirectory')
    assert _parts(result)[-1] == (part, 'Fail')


def test_rebuild_lowering_directory(lowering_worker, api, warehouse, perms) -> None:
    """Creates the lowering's missing directories and fixes ownership; the API task goes idle."""
    (warehouse.cruise_dir / 'Vehicle' / 'DIVE01').mkdir()
    result = _run_lowering(lowering_worker, lowering_directory.task_rebuild_lowering_directory,
                           'rebuildLoweringDirectory')
    assert _parts(result) == [('Verify lowering directory exists', 'Pass'), ('Build Directory List', 'Pass'),
                              ('Create Directories', 'Pass'), ('Set Directory ownership/permissions', 'Pass')]
    assert (warehouse.cruise_dir / 'Vehicle' / 'DIVE01' / 'Frames' / 'DIVE01').is_dir()

    lowering_worker.on_job_complete(_job('rebuildLoweringDirectory'), result)
    api.set_idle_task.assert_called_once_with(7)


@pytest.mark.parametrize('setup, part', [
    (lambda w, p: None, 'Verify lowering directory exists'),
    (lambda w, p: (w.cruise_dir.joinpath('Vehicle', 'DIVE01').mkdir(),
                   w.cruise_dir.joinpath('Video').write_text('a file in the way')), 'Create Directories'),
    (lambda w, p: (w.cruise_dir.joinpath('Vehicle', 'DIVE01').mkdir(), setattr(p, 'owner_fail', 'denied')),
     'Set Directory ownership/permissions'),
], ids=['no lowering directory', 'create fails', 'ownership fails'])
def test_rebuild_lowering_directory_failures(lowering_worker, api, warehouse, perms, setup, part) -> None:
    """Each failure ends the job with that part failed and sets the API task's error."""
    setup(warehouse, perms)
    result = _run_lowering(lowering_worker, lowering_directory.task_rebuild_lowering_directory,
                           'rebuildLoweringDirectory')
    assert _parts(result)[-1] == (part, 'Fail')

    lowering_worker.on_job_complete(_job('rebuildLoweringDirectory'), result)
    api.set_error_task.assert_called_once_with(7, json.loads(result)['parts'][-1]['reason'])


def test_set_loweringdata_permissions(lowering_worker, warehouse, perms) -> None:
    """Sets the lowering base directory's ownership."""
    result = _run_lowering(lowering_worker, lowering_directory.task_set_loweringdata_directory_permissions,
                           'setLoweringDataDirectoryPermissions')
    assert _parts(result) == [('Set lowering base directory ownership/permissions', 'Pass')]
    assert perms.owner == [('survey', str(warehouse.cruise_dir / 'Vehicle'))]


@pytest.mark.parametrize('setup, part', [
    (lambda w, p: w.cruise_dir.joinpath('Vehicle').rmdir(), 'Verify lowering base directory exists'),
    (lambda w, p: setattr(p, 'owner_fail', 'denied'), 'Set lowering base directory ownership/permissions'),
], ids=['no lowering base directory', 'ownership fails'])
def test_set_loweringdata_permissions_failures(lowering_worker, warehouse, perms, setup, part) -> None:
    """No lowering base directory, or ownership that can't be set, fails the job."""
    setup(warehouse, perms)
    result = _run_lowering(lowering_worker, lowering_directory.task_set_loweringdata_directory_permissions,
                           'setLoweringDataDirectoryPermissions')
    assert _parts(result)[-1] == (part, 'Fail')
