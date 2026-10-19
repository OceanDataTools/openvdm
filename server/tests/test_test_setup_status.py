"""Tests that Test Setup leaves a running transfer's status alone."""

import json
from unittest.mock import Mock

import pytest
import python3_gearman

from server.lib import openvdm as openvdm_module
from server.lib.openvdm import OpenVDM
from server.workers import test_collection_system_transfer as cst_test
from server.workers import test_cruise_data_transfer as cdt_test

WORKERS = [
    (cst_test, 'collection_system_transfer', 'collectionSystemTransferID',
     'get_collection_system_transfer', 'set_idle_collection_system_transfer'),
    (cdt_test, 'cruise_data_transfer', 'cruiseDataTransferID',
     'get_cruise_data_transfer', 'set_idle_cruise_data_transfer'),
]


@pytest.mark.parametrize('module, attr, id_key, get_name, set_idle_name', WORKERS)
@pytest.mark.parametrize('status, sets_idle', [(1, False), (5, False), (2, True), (3, True)])
def test_passed_test_sets_idle_unless_running(
        monkeypatch: pytest.MonkeyPatch, module, attr: str, id_key: str, get_name: str,
        set_idle_name: str, status: int, sets_idle: bool) -> None:
    """A passed test clears the transfer's status, but not while the transfer is running."""
    monkeypatch.setattr(python3_gearman.GearmanWorker, 'send_job_complete', Mock())
    worker = object.__new__(module.OVDMGearmanWorker)
    setattr(worker, attr, {id_key: 5})
    worker.ovdm = Mock(**{f'{get_name}.return_value': {id_key: 5, 'status': status}})

    worker.on_job_complete(Mock(), json.dumps({'parts': [{'result': 'Pass'}]}))

    assert getattr(worker.ovdm, set_idle_name).called == sets_idle


@pytest.mark.parametrize('method, get_name, api', [
    ('set_error_collection_system_transfer_test', 'get_collection_system_transfer',
     'setErrorCollectionSystemTransfer'),
    ('set_error_cruise_data_transfer_test', 'get_cruise_data_transfer',
     'setErrorCruiseDataTransfer'),
])
@pytest.mark.parametrize('status, sets_error', [(1, False), (5, False), (2, True)])
def test_failed_test_sets_error_unless_running(
        monkeypatch: pytest.MonkeyPatch, method: str, get_name: str, api: str,
        status: int, sets_error: bool) -> None:
    """A failed test posts its message, but only sets the error status if the transfer isn't running."""
    get = Mock()
    monkeypatch.setattr(openvdm_module.requests, 'get', get)
    ovdm = object.__new__(OpenVDM)
    ovdm.config = {'siteRoot': 'http://openvdm/'}
    setattr(ovdm, get_name, Mock(return_value={'name': 'X', 'status': status}))
    ovdm.send_msg = Mock()

    getattr(ovdm, method)(5, 'reason')

    assert any(api in str(call) for call in get.call_args_list) == sets_error
    ovdm.send_msg.assert_called_once_with('X Connection test failed', 'reason')
