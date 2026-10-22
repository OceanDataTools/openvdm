"""Tests for the Test Setup workers of collection system and cruise data transfers (#510).

These OpenVDM workers (``test_collection_system_transfer.py`` and
``test_cruise_data_transfer.py``) run the connection checks behind the Test
Setup button. The checks themselves (``test_cst_source()`` and the
destination tests) have their own tests (#508), so they're replaced here.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import test_collection_system_transfer as cst_test
from server.workers import test_cruise_data_transfer as cdt_test

CST = {'collectionSystemTransferID': '3', 'name': 'SCS', 'transferType': '1', 'sourceDir': '/data/{cruiseID}/',
       'destDir': 'SCS', 'cruiseOrLowering': '0', 'enable': '1', 'removeSourceFiles': '0'}
CDT = {'cruiseDataTransferID': '5', 'name': 'Backup', 'transferType': '4', 'destDir': '/backup', 'enable': '1'}

PASS = [{'partName': 'Source directory', 'result': 'Pass'}]


def _job(task, **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run the task by returning a marker, and pass results through."""
    base = cst_test.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: json.dumps({'ran': True}))
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def locked(monkeypatch):
    """Which transfers a job is running (holds the lock for); none by default."""
    held = set()
    monkeypatch.setattr(cst_test, 'transfer_locked', lambda kind, transfer_id: (kind, int(transfer_id)) in held)
    monkeypatch.setattr(cdt_test, 'transfer_locked', lambda kind, transfer_id: (kind, int(transfer_id)) in held)
    return held


# --- Collection system transfers ----------------------------------------------

@pytest.fixture
def cst_worker(monkeypatch, fake_ovdm, gearman_base, locked):
    """A collection system Test Setup worker with the CST above in the API."""
    monkeypatch.setattr(cst_test, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: dict(CST)
    fake_ovdm.get_lowering_id.return_value = None
    worker = cst_test.OVDMGearmanWorker()
    worker.send_job_status = Mock()
    worker.send_job_data = Mock()
    return worker


def test_cst_job_setup(cst_worker, warehouse) -> None:
    """The saved transfer, with the form's unsaved settings on top, and its paths."""
    result = cst_worker.on_job_execute(_job('testCollectionSystemTransfer', collectionSystemTransfer={
        'collectionSystemTransferID': 3, 'destDir': 'SCS/{cruiseID}'}))

    assert json.loads(result) == {'ran': True}
    assert cst_worker.collection_system_transfer['transferType'] == 1, 'normalized'
    assert cst_worker.source_dir == '/data/TEST001'
    assert cst_worker.dest_dir == str(warehouse.cruise_dir / 'SCS' / 'TEST001')


def test_cst_job_for_an_unsaved_transfer(cst_worker, fake_ovdm) -> None:
    """Test Setup on the add form: no ID, so the form's settings are used as they are."""
    cst_worker.on_job_execute(_job('testCollectionSystemTransfer', collectionSystemTransfer={
        'name': 'New', 'sourceDir': '/new', 'destDir': 'New', 'cruiseOrLowering': '0'}))
    fake_ovdm.get_collection_system_transfer.assert_not_called()
    assert cst_worker.source_dir == '/new'


def test_cst_lowering_paths(cst_worker, fake_ovdm, warehouse) -> None:
    """A lowering-level transfer goes under <loweringDataBaseDir>/<loweringID>; placeholders are replaced."""
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: {
        **CST, 'cruiseOrLowering': '1', 'sourceDir': '/video/{loweringDataBaseDir}/{loweringID}', 'destDir': '/'}
    cst_worker.on_job_execute(_job('testCollectionSystemTransfer', loweringID='DIVE01',
                                   collectionSystemTransfer={'collectionSystemTransferID': 3}))
    assert cst_worker.source_dir == '/video/Vehicle/DIVE01'
    assert cst_worker.dest_dir == str(warehouse.cruise_dir / 'Vehicle' / 'DIVE01') + '/'
    assert cst_worker.keyword_replace(None) is None


def test_cst_lowering_transfer_needs_a_lowering(cst_worker, fake_ovdm) -> None:
    """A lowering-level transfer without a lowering fails the test."""
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: {**CST, 'cruiseOrLowering': '1'}
    result = cst_worker.on_job_execute(_job('testCollectionSystemTransfer', loweringID='',
                                            collectionSystemTransfer={'collectionSystemTransferID': 3}))
    assert json.loads(result)['parts'][-1]['reason'] == 'Lowering ID is undefined'
    fake_ovdm.set_error_collection_system_transfer_test.assert_called_once_with(3, 'Lowering ID is undefined',
                                                                                 set_status=True)


def test_cst_unknown_transfer(cst_worker, fake_ovdm) -> None:
    """A transfer ID the API doesn't know (e.g. deleted) fails the test instead of crashing (#528)."""
    fake_ovdm.get_collection_system_transfer.side_effect = lambda cst_id: None
    result = cst_worker.on_job_execute(_job('testCollectionSystemTransfer',
                                            collectionSystemTransfer={'collectionSystemTransferID': 9}))
    assert json.loads(result)['parts'][-1]['partName'] == 'Locate collection system transfer Data'


@pytest.mark.parametrize('data', ['not json', json.dumps({})])
def test_cst_bad_payload_on_a_fresh_worker(cst_worker, data) -> None:
    """A payload that isn't JSON, or has no transfer, fails the test instead of crashing (#528)."""
    job = SimpleNamespace(data=data, handle='H:1', task='testCollectionSystemTransfer')
    assert json.loads(cst_worker.on_job_execute(job))['parts'][-1]['result'] == 'Fail'


def test_cst_bad_payload_after_a_job(cst_worker, fake_ovdm) -> None:
    """After a job, a bad payload fails without changing the previous job's transfer (#528)."""
    cst_worker.collection_system_transfer = dict(CST)
    job = SimpleNamespace(data='not json', handle='H:1', task='testCollectionSystemTransfer')
    assert json.loads(cst_worker.on_job_execute(job))['parts'][-1]['reason'] == 'Failed to parse current job payload'
    fake_ovdm.set_error_collection_system_transfer_test.assert_not_called()


def test_cst_destination_check(cst_worker, warehouse) -> None:
    """The destination must exist in the cruise directory."""
    cst_worker.dest_dir = str(warehouse.cruise_dir / 'SCS')
    assert cst_worker.test_destination_dir()[0]['result'] == 'Fail'
    (warehouse.cruise_dir / 'SCS').mkdir()
    assert cst_worker.test_destination_dir() == [{'partName': 'Destination directory', 'result': 'Pass'}]


def _ready(cst_worker, warehouse, **cfg):
    """Set the worker up for the task, as on_job_execute() does."""
    cst_worker.collection_system_transfer = cst_test.normalize_transfer_config({**CST, **cfg})
    cst_worker.source_dir = '/data'
    cst_worker.dest_dir = str(warehouse.cruise_dir / 'SCS')


def test_cst_task(cst_worker, warehouse, fake_ovdm, monkeypatch) -> None:
    """The source and destination checks, then a Final Verdict."""
    monkeypatch.setattr(cst_test, 'test_cst_source', lambda cfg, source: list(PASS))
    _ready(cst_worker, warehouse)
    (warehouse.cruise_dir / 'SCS').mkdir()

    result = cst_test.task_test_collection_system_transfer(cst_worker, _job('testCollectionSystemTransfer'))

    assert _parts(result) == [('Source directory', 'Pass'), ('Destination directory', 'Pass'), ('Final Verdict', 'Pass')]
    fake_ovdm.set_running_collection_system_transfer_test.assert_called_once()


def test_cst_task_failure_is_the_verdict(cst_worker, warehouse, monkeypatch) -> None:
    """The first failure's reason becomes the Final Verdict's."""
    monkeypatch.setattr(cst_test, 'test_cst_source', lambda cfg, source: [
        {'partName': 'Source directory', 'result': 'Fail', 'reason': 'Unable to find source directory: /data'}])
    _ready(cst_worker, warehouse)
    result = json.loads(cst_test.task_test_collection_system_transfer(cst_worker, _job('t')))
    assert result['parts'][-1] == {'partName': 'Final Verdict', 'result': 'Fail',
                                   'reason': 'Unable to find source directory: /data'}


def test_cst_task_disabled_transfer_skips_the_destination(cst_worker, warehouse, monkeypatch) -> None:
    """A disabled transfer's destination may not exist yet, so it isn't checked."""
    monkeypatch.setattr(cst_test, 'test_cst_source', lambda cfg, source: list(PASS))
    _ready(cst_worker, warehouse, enable='0')
    assert _parts(cst_test.task_test_collection_system_transfer(cst_worker, _job('t'))) == [
        ('Source directory', 'Pass'), ('Final Verdict', 'Pass')]


def test_cst_task_for_an_unsaved_transfer(cst_worker, warehouse, fake_ovdm, monkeypatch) -> None:
    """Without an ID, there's no status to set."""
    monkeypatch.setattr(cst_test, 'test_cst_source', lambda cfg, source: list(PASS))
    _ready(cst_worker, warehouse, enable='0')
    del cst_worker.collection_system_transfer['collectionSystemTransferID']
    cst_test.task_test_collection_system_transfer(cst_worker, _job('t'))
    fake_ovdm.set_running_collection_system_transfer_test.assert_not_called()


@pytest.mark.parametrize('verdict, running', [('Pass', False), ('Pass', True), ('Fail', False), ('Fail', True)])
def test_cst_outcome(cst_worker, fake_ovdm, locked, verdict, running) -> None:
    """Pass sets idle and Fail the test error, but not for a transfer a job is running (#478)."""
    cst_worker.collection_system_transfer = dict(CST)
    if running:
        locked.add(('cst', 3))
    cst_worker.on_job_complete(_job('t'), json.dumps({'parts': [{'partName': 'Final Verdict', 'result': verdict,
                                                                'reason': 'x'}]}))
    if verdict == 'Pass':
        assert fake_ovdm.set_idle_collection_system_transfer.called is not running
    else:
        fake_ovdm.set_error_collection_system_transfer_test.assert_called_once_with('3', 'x', set_status=not running)


def test_cst_outcome_for_an_unsaved_transfer(cst_worker, fake_ovdm) -> None:
    """Without an ID there is no status to set."""
    cst_worker.collection_system_transfer = {'name': 'New'}
    cst_worker.on_job_complete(_job('t'), json.dumps({'parts': []}))
    fake_ovdm.set_idle_collection_system_transfer.assert_not_called()


def test_cst_crash(cst_worker, fake_ovdm, locked) -> None:
    """A crash sets the test error; a running transfer's status is left alone (#478)."""
    cst_worker.collection_system_transfer = dict(CST)
    locked.add(('cst', 3))
    try:
        raise KeyError('sourceDir')
    except KeyError:
        assert cst_worker.on_job_exception(_job('t'), sys.exc_info()) == 'crashed'
    args = fake_ovdm.set_error_collection_system_transfer_test.call_args
    assert args.args[1].startswith("Worker crashed: KeyError: 'sourceDir' (test_test_setup_workers.py, line ")
    assert args.kwargs == {'set_status': False}

    cst_worker.on_job_exception(_job('t'), (None, None, None))
    assert fake_ovdm.set_error_collection_system_transfer_test.call_args.args[1].endswith('(unknown, line ?)')


def test_cst_stop_and_quit(cst_worker, monkeypatch) -> None:
    """Stop sets the flag; quit also shuts the worker down."""
    cst_worker.stop_task()
    assert cst_worker.stop
    monkeypatch.setattr(cst_worker, 'shutdown', Mock())
    cst_worker.quit_worker()
    assert cst_worker.shutdown.called


def test_cst_ignore_job(cst_worker, fake_ovdm) -> None:
    """An ignored test is completed like a passed one."""
    cst_worker.collection_system_transfer = dict(CST)
    assert _parts(cst_worker._ignore_job(_job('t'), 'Part', 'reason')) == [('Part', 'Ignore')]  # pylint: disable=protected-access


# --- Cruise data transfers ----------------------------------------------------

@pytest.fixture
def cdt_worker(monkeypatch, fake_ovdm, gearman_base, locked):
    """A cruise data Test Setup worker with the CDT above in the API."""
    monkeypatch.setattr(cdt_test, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_cruise_data_transfer.side_effect = lambda cdt_id: dict(CDT)
    worker = cdt_test.OVDMGearmanWorker()
    worker.send_job_status = Mock()
    worker.send_job_data = Mock()
    return worker


def test_cdt_job_setup(cdt_worker, warehouse) -> None:
    """The saved transfer, with the form's settings on top; the payload's cruise."""
    cdt_worker.on_job_execute(_job('testCruiseDataTransfer', cruiseID='OTHER01',
                                   cruiseDataTransfer={'cruiseDataTransferID': 5, 'destDir': '/other'}))
    assert cdt_worker.cruise_data_transfer['destDir'] == '/other' and cdt_worker.cruise_data_transfer['transferType'] == 4
    assert cdt_worker.cruise_dir == str(warehouse.base_dir / 'OTHER01')


def test_cdt_job_for_an_unsaved_transfer(cdt_worker, fake_ovdm) -> None:
    """Test Setup on the add form: the form's settings are used as they are."""
    cdt_worker.on_job_execute(_job('testCruiseDataTransfer', cruiseDataTransfer={'name': 'New', 'destDir': '/n'}))
    fake_ovdm.get_cruise_data_transfer.assert_not_called()
    assert cdt_worker.cruise_data_transfer['destDir'] == '/n'


def test_cdt_unknown_transfer(cdt_worker, fake_ovdm) -> None:
    """A transfer ID the API doesn't know (e.g. deleted) fails the test instead of crashing (#528)."""
    fake_ovdm.get_cruise_data_transfer.side_effect = lambda cdt_id: None
    result = cdt_worker.on_job_execute(_job('testCruiseDataTransfer', cruiseDataTransfer={'cruiseDataTransferID': 9}))
    assert json.loads(result)['parts'][-1]['partName'] == 'Locate Cruise Data Transfer Data'


@pytest.mark.parametrize('data', ['not json', json.dumps({})])
def test_cdt_bad_payload_on_a_fresh_worker(cdt_worker, data) -> None:
    """A payload that isn't JSON, or has no transfer, fails the test instead of crashing (#528)."""
    job = SimpleNamespace(data=data, handle='H:1', task='testCruiseDataTransfer')
    assert json.loads(cdt_worker.on_job_execute(job))['parts'][-1]['result'] == 'Fail'


def test_cdt_bad_payload_after_a_job(cdt_worker, fake_ovdm) -> None:
    """After a job, a bad payload fails without changing the previous job's transfer (#528)."""
    for data in ('not json', json.dumps({})):
        cdt_worker.cruise_data_transfer = dict(CDT)
        job = SimpleNamespace(data=data, handle='H:1', task='testCruiseDataTransfer')
        assert json.loads(cdt_worker.on_job_execute(job))['parts'][-1]['result'] == 'Fail'
    fake_ovdm.set_error_cruise_data_transfer_test.assert_not_called()


def _cdt_ready(cdt_worker, warehouse, **cfg):
    """Set the worker up for the task, as on_job_execute() does."""
    cdt_worker.cruise_data_transfer = cdt_test.normalize_transfer_config({**CDT, **cfg})
    cdt_worker.cruise_dir = str(warehouse.cruise_dir)


@pytest.mark.parametrize('cfg, check', [
    ({'transferType': '4', 'destDir': '/backup'}, 'destination'),
    ({'transferType': '1', 'destDir': '/mnt/backup'}, 'rclone'),
    ({'transferType': '3', 'destDir': 'backups'}, 'rclone'),
    ({'transferType': '1', 'destDir': 'gcs:bucket'}, 'rclone'),
])
def test_cdt_task_routes_to_the_right_check(cdt_worker, warehouse, monkeypatch, cfg, check) -> None:
    """Local, SMB and remote:path destinations use the rclone check; others the plain one."""
    calls = []
    monkeypatch.setattr(cdt_test, 'test_cdt_rclone_destination', lambda c: calls.append('rclone') or list(PASS))
    monkeypatch.setattr(cdt_test, 'test_cdt_destination', lambda c: calls.append('destination') or list(PASS))
    _cdt_ready(cdt_worker, warehouse, **cfg)

    result = cdt_test.task_test_cruise_data_transfer(cdt_worker, _job('t'))

    assert calls == [check]
    assert _parts(result) == [('Verify cruise data directory exists', 'Pass'), ('Source directory', 'Pass'),
                              ('Final Verdict', 'Pass')]


def test_cdt_task_failure_is_the_verdict(cdt_worker, warehouse, fake_ovdm, monkeypatch) -> None:
    """The first failure's reason becomes the Final Verdict's."""
    monkeypatch.setattr(cdt_test, 'test_cdt_destination', lambda c: [
        {'partName': 'SSH connection', 'result': 'Fail', 'reason': 'Permission denied'}])
    _cdt_ready(cdt_worker, warehouse)
    result = json.loads(cdt_test.task_test_cruise_data_transfer(cdt_worker, _job('t')))
    assert result['parts'][-1] == {'partName': 'Final Verdict', 'result': 'Fail', 'reason': 'Permission denied'}
    fake_ovdm.set_running_cruise_data_transfer_test.assert_called_once()


def test_cdt_task_without_a_cruise_directory(cdt_worker, warehouse, monkeypatch) -> None:
    """A missing cruise directory fails the test, in the Final Verdict, instead of crashing (#529)."""
    monkeypatch.setattr(cdt_test, 'test_cdt_destination', lambda c: list(PASS))
    _cdt_ready(cdt_worker, warehouse)
    cdt_worker.cruise_dir = str(warehouse.base_dir / 'missing')
    result = json.loads(cdt_test.task_test_cruise_data_transfer(cdt_worker, _job('t')))
    assert [part['result'] for part in result['parts']] == ['Fail', 'Pass', 'Fail']
    assert result['parts'][-1] == {'partName': 'Final Verdict', 'result': 'Fail',
                                   'reason': f"Unable to find cruise data directory: {warehouse.base_dir / 'missing'}"}


def test_cdt_cruise_dir_check(cdt_worker, warehouse, fake_ovdm) -> None:
    """The check returns its part; it doesn't complete the job itself (#529)."""
    _cdt_ready(cdt_worker, warehouse)
    assert cdt_worker.test_cruise_dir() == [{'partName': 'Verify cruise data directory exists', 'result': 'Pass'}]
    cdt_worker.cruise_dir = str(warehouse.base_dir / 'missing')
    assert cdt_worker.test_cruise_dir()[0]['result'] == 'Fail'
    fake_ovdm.set_error_cruise_data_transfer_test.assert_not_called()


@pytest.mark.parametrize('verdict, running', [('Pass', False), ('Pass', True), ('Fail', False), ('Fail', True)])
def test_cdt_outcome(cdt_worker, fake_ovdm, locked, verdict, running) -> None:
    """Pass sets idle and Fail the test error, but not for a transfer a job is running (#478)."""
    cdt_worker.cruise_data_transfer = dict(CDT)
    if running:
        locked.add(('cdt', 5))
    cdt_worker.on_job_complete(_job('t'), json.dumps({'parts': [{'partName': 'Final Verdict', 'result': verdict,
                                                                'reason': 'x'}]}))
    if verdict == 'Pass':
        assert fake_ovdm.set_idle_cruise_data_transfer.called is not running
    else:
        fake_ovdm.set_error_cruise_data_transfer_test.assert_called_once_with('5', 'x', set_status=not running)


def test_cdt_outcome_for_an_unsaved_transfer(cdt_worker, fake_ovdm) -> None:
    """Without an ID there is no status to set."""
    cdt_worker.cruise_data_transfer = {'name': 'New'}
    cdt_worker.on_job_complete(_job('t'), json.dumps({'parts': []}))
    fake_ovdm.set_idle_cruise_data_transfer.assert_not_called()


def test_cdt_crash(cdt_worker, fake_ovdm) -> None:
    """A crash sets the test error with the exception and where it was raised."""
    cdt_worker.cruise_data_transfer = dict(CDT)
    try:
        raise RuntimeError('boom')
    except RuntimeError:
        cdt_worker.on_job_exception(_job('t'), sys.exc_info())
    assert fake_ovdm.set_error_cruise_data_transfer_test.call_args.args[1].startswith('Worker crashed: RuntimeError: boom')
    assert fake_ovdm.set_error_cruise_data_transfer_test.call_args.kwargs == {'set_status': True}
    cdt_worker.on_job_exception(_job('t'), (None, None, None))
    assert fake_ovdm.set_error_cruise_data_transfer_test.call_args.args[1].endswith('(unknown, line ?)')


def test_cdt_stop_quit_and_ignore(cdt_worker, monkeypatch) -> None:
    """Stop sets the flag, quit shuts down, and an ignored test completes."""
    cdt_worker.stop_task()
    assert cdt_worker.stop
    monkeypatch.setattr(cdt_worker, 'shutdown', Mock())
    cdt_worker.quit_worker()
    assert cdt_worker.shutdown.called
    cdt_worker.cruise_data_transfer = dict(CDT)
    assert _parts(cdt_worker._ignore_job(_job('t'), 'Part', 'reason')) == [('Part', 'Ignore')]  # pylint: disable=protected-access


def test_cst_dest_dir_without_a_transfer_or_lowering(cst_worker, warehouse) -> None:
    """No destination without a transfer, or for a lowering-level one without a lowering."""
    assert cst_worker.build_dest_dir() is None
    cst_worker.collection_system_transfer = {**CST, 'cruiseOrLowering': 1}
    cst_worker.shipboard_data_warehouse_config = warehouse.config
    cst_worker.cruise_id = 'TEST001'
    assert cst_worker.build_dest_dir() is None
