"""Tests that reboot_reset leaves records whose worker is still running alone."""

from unittest.mock import Mock

import pytest

from server.workers import reboot_reset as rr

LIVE_PID = 4242


@pytest.fixture
def ovdm(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """An OpenVDM API mock with one live and one stale record of each kind."""
    api = Mock()
    api.get_tasks.return_value = [
        {'taskID': 1, 'name': 'live task', 'pid': LIVE_PID},
        {'taskID': 2, 'name': 'stale task', 'pid': 0}]
    api.get_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'live cst', 'status': 1, 'pid': LIVE_PID},
        {'collectionSystemTransferID': 2, 'name': 'stale cst', 'status': 1, 'pid': 99},
        {'collectionSystemTransferID': 3, 'name': 'failed cst', 'status': 3, 'pid': 0}]
    api.get_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 1, 'name': 'live cdt', 'status': 5, 'pid': LIVE_PID},
        {'cruiseDataTransferID': 2, 'name': 'stale cdt', 'status': 1, 'pid': 99}]
    api.get_required_cruise_data_transfers.return_value = []
    monkeypatch.setattr(rr, 'OpenVDM', lambda: api)
    monkeypatch.setattr(rr, '_worker_alive', lambda row: row.get('pid') == LIVE_PID)
    return api


def test_live_records_are_left_alone(ovdm: Mock) -> None:
    """Only records without a running worker are reset; the job list is kept."""
    rr.reboot_reset()

    ovdm.set_idle_task.assert_called_once_with(2)
    ovdm.set_idle_collection_system_transfer.assert_called_once_with(2)
    ovdm.set_idle_cruise_data_transfer.assert_called_once_with(2)
    ovdm.clear_gearman_jobs_from_db.assert_not_called()


def test_everything_is_reset_when_nothing_runs(monkeypatch: pytest.MonkeyPatch, ovdm: Mock) -> None:
    """At start-up no worker holds anything: reset all but errors, clear the job list."""
    monkeypatch.setattr(rr, '_worker_alive', lambda row: False)

    rr.reboot_reset()

    assert ovdm.set_idle_task.call_count == 2
    assert [c.args[0] for c in ovdm.set_idle_collection_system_transfer.call_args_list] == [1, 2]
    assert [c.args[0] for c in ovdm.set_idle_cruise_data_transfer.call_args_list] == [1, 2]
    ovdm.clear_gearman_jobs_from_db.assert_called_once()


@pytest.mark.parametrize('pid', [0, None, '', 'x', 2 ** 22 + 1])
def test_worker_alive_without_a_worker(pid) -> None:
    """No PID, a bad one or a missing process isn't a live worker."""
    assert rr._worker_alive({'pid': pid}) is False
