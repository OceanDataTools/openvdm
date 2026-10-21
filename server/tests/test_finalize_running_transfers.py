"""Tests that finalize's transfers get their final pass when one is already running (#480)."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.lib import transfer_jobs
from server.lib.transfer_jobs import IN_PROGRESS_REASON, ignored_as_in_progress, run_transfer_jobs
from server.workers import cruise, lowering

PASS = json.dumps({'parts': [{'partName': 'Transfer Files', 'result': 'Pass'}]})
IGNORED = json.dumps({'parts': [{'partName': 'Transfer in-Progress', 'result': 'Ignore',
                                 'reason': IN_PROGRESS_REASON}]})


class FakeClient:
    """A Gearman client whose jobs return scripted results, by transfer ID."""

    def __init__(self, results):
        self.results = {transfer_id: list(scripted) for transfer_id, scripted in results.items()}
        self.rounds = []

    def submit_multiple_jobs(self, jobs, background, wait_until_complete):
        assert not background and not wait_until_complete
        payloads = [json.loads(job['data']) for job in jobs]
        self.rounds.append(payloads)
        return [SimpleNamespace(result=self.results[payload['id']].pop(0)) for payload in payloads]

    def wait_until_jobs_completed(self, requests):
        return requests


@pytest.fixture
def clock(monkeypatch):
    """A fake clock that sleeping advances; returns its state."""
    state = {'now': 0.0}
    monkeypatch.setattr(transfer_jobs.time, 'monotonic', lambda: state['now'])
    monkeypatch.setattr(transfer_jobs.time, 'sleep',
                        lambda seconds: state.__setitem__('now', state['now'] + seconds))
    return state


def _locked_until(clock, free_at):
    """transfer_locked() for transfers whose job ends at the given times."""
    return lambda kind, transfer_id: clock['now'] < free_at.get(transfer_id, 0)


def _payloads(*ids):
    return {transfer_id: {'id': transfer_id, 'cruiseID': 'C1'} for transfer_id in ids}


def test_all_run_first_time(monkeypatch, clock) -> None:
    """With nothing already running, every job runs once."""
    client = FakeClient({1: [PASS], 2: [PASS]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {}))
    assert run_transfer_jobs(client, 'run', 'cst', _payloads(1, 2)) == []
    assert len(client.rounds) == 1


def test_a_running_transfer_runs_again_once_its_job_ends(monkeypatch, clock) -> None:
    """Its job is resubmitted, with finalize's payload, when the lock is free."""
    client = FakeClient({1: [PASS], 2: [IGNORED, PASS]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {2: 600}))

    assert run_transfer_jobs(client, 'run', 'cst', _payloads(1, 2)) == []
    assert client.rounds[1] == [{'id': 2, 'cruiseID': 'C1'}]
    assert clock['now'] >= 600


def test_another_run_taking_the_lock_first_is_waited_for_too(monkeypatch, clock) -> None:
    """A scheduled run that starts before the resubmitted job is waited for as well."""
    client = FakeClient({2: [IGNORED, IGNORED, PASS]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {2: 60}))

    assert run_transfer_jobs(client, 'run', 'cst', _payloads(2)) == []
    assert len(client.rounds) == 3


def test_gives_up_on_a_transfer_still_running_after_the_wait(monkeypatch, clock) -> None:
    """A transfer whose job runs past the limit is returned; the others aren't rerun."""
    client = FakeClient({1: [PASS], 2: [IGNORED]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {2: 10 ** 6}))

    assert run_transfer_jobs(client, 'run', 'cst', _payloads(1, 2), wait=3600) == [2]
    assert len(client.rounds) == 1
    assert 3600 <= clock['now'] < 3600 + 2 * transfer_jobs.POLL_INTERVAL


def test_each_runs_as_soon_as_its_own_job_ends(monkeypatch, clock) -> None:
    """Transfers are rerun in the order their jobs end, without waiting for all of them."""
    client = FakeClient({2: [IGNORED, PASS], 3: [IGNORED, PASS]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {2: 900, 3: 300}))

    assert run_transfer_jobs(client, 'run', 'cst', _payloads(2, 3)) == []
    assert [[payload['id'] for payload in round_] for round_ in client.rounds] == [[2, 3], [3], [2]]


def test_failed_jobs_are_not_retried(monkeypatch, clock) -> None:
    """Only jobs ignored as in progress are run again, not failed ones."""
    failed = json.dumps({'parts': [{'partName': 'Transfer Files', 'result': 'Fail', 'reason': 'x'}]})
    client = FakeClient({1: [failed], 2: [None]})
    monkeypatch.setattr(transfer_jobs, 'transfer_locked', _locked_until(clock, {}))
    assert run_transfer_jobs(client, 'run', 'cst', _payloads(1, 2)) == []
    assert len(client.rounds) == 1


@pytest.mark.parametrize('result, expected', [
    (IGNORED, True),
    (PASS, False),
    (json.dumps({'parts': [{'result': 'Ignore', 'reason': 'Transfer is disabled'}]}), False),
    (json.dumps({'parts': []}), False),
    (None, False),
    ('not json', False),
])
def test_ignored_as_in_progress(result, expected) -> None:
    """Only the in-progress Ignore counts, not a disabled transfer or a failure."""
    assert ignored_as_in_progress(result) is expected


def test_lowering_finalize_warns_and_completes(monkeypatch, tmp_path) -> None:
    """A transfer that never got its final pass is reported, and finalize still exports."""
    (tmp_path / 'L1').mkdir()
    worker = Mock(cruise_dir=str(tmp_path), lowering_dir='L1', lowering_id='L1')
    worker.ovdm.get_active_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'SCS'},
        {'collectionSystemTransferID': 2, 'name': 'Sonar'}]
    worker.export_lowering_config.return_value = {'verdict': True}
    run = Mock(return_value=[2])
    monkeypatch.setattr(lowering, 'run_transfer_jobs', run)
    monkeypatch.setattr(lowering.python3_gearman, 'GearmanClient', Mock())

    results = json.loads(lowering.task_finalize_current_lowering(worker, Mock()))

    payloads = run.call_args.args[3]
    assert payloads[2]['collectionSystemTransfer'] == {'collectionSystemTransferID': 2}
    assert payloads[1]['loweringID'] == 'L1'

    parts = {part['partName']: part for part in results['parts']}
    assert parts['Final pass of collection system transfers']['result'] == 'Fail'
    assert 'Sonar' in parts['Final pass of collection system transfers']['reason']
    assert 'SCS' not in parts['Final pass of collection system transfers']['reason']
    assert results['parts'][-1] == {'partName': 'Export lowering config data to file', 'result': 'Pass'}
    title, body = worker.ovdm.send_msg.call_args.args
    assert 'still running' in title and 'Sonar' in body


def test_cruise_finalize_runs_both_kinds_and_completes(monkeypatch, tmp_path) -> None:
    """Collection system and cruise data transfers each get the wait; finalize still completes."""
    worker = Mock(cruise_dir=str(tmp_path), cruise_id='C1')
    worker.ovdm.get_active_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'SCS'}]
    worker.ovdm.get_active_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 5, 'name': 'Backup'}]
    worker.ovdm.get_transfer_public_data.return_value = False
    worker.ovdm.get_tasks_for_hook.return_value = []
    worker.export_cruise_config.return_value = {'verdict': True}
    run = Mock(side_effect=[[], [5]])
    monkeypatch.setattr(cruise, 'run_transfer_jobs', run)
    monkeypatch.setattr(cruise.python3_gearman, 'GearmanClient', Mock())

    results = json.loads(cruise.task_finalize_current_cruise(worker, Mock()))

    (cst_call, cdt_call) = run.call_args_list
    assert cst_call.args[2] == 'cst' and cst_call.args[3][1]['cruiseID'] == 'C1'
    assert cdt_call.args[2] == 'cdt' and cdt_call.args[3][5]['cruiseDataTransfer'] == {'cruiseDataTransferID': 5}

    names = [part['partName'] for part in results['parts']]
    assert 'Final pass of collection system transfers' not in names
    # The warning comes before the last part, which decides that finalize passed
    assert results['parts'][-2]['partName'] == 'Final pass of cruise data transfers'
    assert results['parts'][-1] == {'partName': 'Run cruise data transfers jobs', 'result': 'Pass'}
    worker.ovdm.send_msg.assert_called_once()
