"""Tests that the scheduler submits transfer jobs with Gearman unique keys (#479)."""

from unittest.mock import Mock

import pytest

from server.workers import scheduler

INTERVAL = 5


class EndOfCycle(Exception):
    """Raised by the patched sleep at the end of the first cycle."""


def _ovdm():
    ovdm = Mock()
    ovdm.get_transfer_log_dir.return_value = '/tmp'
    ovdm.get_logfile_purge_timedelta.return_value = None
    ovdm.get_system_status.return_value = 'On'
    ovdm.get_active_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'longName': 'CST 1'},
        {'collectionSystemTransferID': 2, 'longName': 'CST 2'}]
    ovdm.get_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 3, 'longName': 'CDT 3'}]
    ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'longName': 'Ship-to-shore', 'enable': 1, 'pid': 0}]
    return ovdm


def _run_one_cycle(monkeypatch, locked=(), purge=None):
    """Run the scheduler until its end-of-cycle sleep; return the submit_job calls."""
    ovdm = _ovdm()
    gm_client = Mock()
    monkeypatch.setattr(scheduler, 'OpenVDM', lambda: ovdm)
    monkeypatch.setattr(scheduler, 'GearmanClient', lambda servers: gm_client)
    monkeypatch.setattr(scheduler, 'purge_old_files', purge or Mock())
    monkeypatch.setattr(scheduler, 'transfer_locked',
                        lambda kind, transfer_id: (kind, transfer_id) in locked)

    end_of_cycle = INTERVAL * 60 - 2 * 2 - 1 * 2 - 2

    def sleep(seconds):
        if seconds == end_of_cycle:
            raise EndOfCycle

    monkeypatch.setattr(scheduler.time, 'sleep', sleep)
    with pytest.raises(EndOfCycle):
        scheduler.scheduler(INTERVAL)
    return gm_client.submit_job.call_args_list


def test_each_transfer_job_has_its_own_key(monkeypatch) -> None:
    """Collection system, cruise data and ship-to-shore jobs carry the transfer's key."""
    calls = _run_one_cycle(monkeypatch)

    keys = {(call.args[0], call.kwargs['unique']) for call in calls}
    assert keys == {
        ('runCollectionSystemTransfer', 'scheduler-cst-1'),
        ('runCollectionSystemTransfer', 'scheduler-cst-2'),
        ('runCruiseDataTransfer', 'scheduler-cdt-3'),
        ('runShipToShoreTransfer', 'scheduler-cdt-4'),
    }
    assert all(call.kwargs['background'] for call in calls)


def test_keys_are_the_same_every_cycle(monkeypatch) -> None:
    """The next cycle's job for a transfer has the same key, so gearmand merges it."""
    first = [call.kwargs['unique'] for call in _run_one_cycle(monkeypatch)]
    second = [call.kwargs['unique'] for call in _run_one_cycle(monkeypatch)]
    assert first == second


def test_locked_transfers_are_still_skipped(monkeypatch) -> None:
    """A transfer a job is running isn't submitted at all (#478)."""
    calls = _run_one_cycle(monkeypatch, locked={(scheduler.CST, 2)})
    assert 'scheduler-cst-2' not in [call.kwargs['unique'] for call in calls]


def test_key_format() -> None:
    """Keys name the scheduler, the lock kind and the transfer."""
    assert scheduler.scheduler_job_key(scheduler.CST, 7) == 'scheduler-cst-7'
    assert scheduler.scheduler_job_key(scheduler.CDT, '7') == 'scheduler-cdt-7'


def test_a_failed_log_purge_doesnt_stop_scheduling(monkeypatch, caplog) -> None:
    """An error purging old transfer logs is logged, and the cycle's jobs still go out (#540)."""
    calls = _run_one_cycle(monkeypatch, purge=Mock(side_effect=OSError('No such directory')))
    assert len(calls) == 4
    assert 'Unable to purge old transfer logs: No such directory' in caplog.text

