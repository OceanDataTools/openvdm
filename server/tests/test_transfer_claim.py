"""Tests that only one job can run a transfer at a time."""

import json
from unittest.mock import Mock

import pytest

from server.lib import openvdm as openvdm_module
from server.lib.openvdm import OpenVDM
from server.workers import run_collection_system_transfer as cst_run
from server.workers import run_cruise_data_transfer as cdt_run
from server.workers import run_ship_to_shore_transfer as ssdw_run

WRAPPERS = [
    ('set_running_collection_system_transfer', 'get_collection_system_transfer'),
    ('set_running_cruise_data_transfer', 'get_cruise_data_transfer'),
]


@pytest.mark.parametrize('method, get_name', WRAPPERS)
@pytest.mark.parametrize('response, claimed', [
    ({'status': 'success'}, True),
    ({'status': 'error', 'message': 'transfer is already running'}, False),
])
def test_set_running_returns_claim(
        monkeypatch: pytest.MonkeyPatch, method: str, get_name: str,
        response: dict, claimed: bool) -> None:
    """The job is only tracked when it claimed the transfer."""
    monkeypatch.setattr(openvdm_module.requests, 'post',
                        Mock(return_value=Mock(text=json.dumps(response))))
    ovdm = object.__new__(OpenVDM)
    ovdm.config = {'siteRoot': 'http://openvdm/'}
    setattr(ovdm, get_name, Mock(return_value={'name': 'X'}))
    ovdm.track_gearman_job = Mock()

    assert getattr(ovdm, method)(5, 1234, 'H:host:1') is claimed
    assert ovdm.track_gearman_job.called is claimed


@pytest.mark.parametrize('module, task, attr, cfg, set_running', [
    (cst_run, 'task_run_collection_system_transfer', 'collection_system_transfer',
     {'collectionSystemTransferID': 5, 'name': 'X'}, 'set_running_collection_system_transfer'),
    (cdt_run, 'task_run_cruise_data_transfer', 'cruise_data_transfer',
     {'cruiseDataTransferID': 5, 'name': 'X'}, 'set_running_cruise_data_transfer'),
    (ssdw_run, 'task_run_ship_to_shore_transfer', 'cruise_data_transfer',
     {'cruiseDataTransferID': 5, 'name': 'X'}, 'set_running_cruise_data_transfer'),
])
def test_task_ignores_job_when_another_claimed_it(
        monkeypatch: pytest.MonkeyPatch, module, task: str, attr: str, cfg: dict,
        set_running: str) -> None:
    """A job that loses the claim is ignored before it touches the transfer."""
    monkeypatch.setattr(module.time, 'sleep', Mock())
    worker = Mock(**{f'ovdm.{set_running}.return_value': False})
    setattr(worker, attr, cfg)

    results = json.loads(getattr(module, task)(worker, Mock(handle='H:host:1')))

    assert results['parts'][-1]['result'] == 'Ignore'
    # The claim was the only API call: the job didn't go on to test or transfer
    assert [call[0] for call in worker.ovdm.method_calls] == [set_running]
