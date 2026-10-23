"""Tests for the scheduler's cycle and the reboot reset (#512 part 4).

What ``test_scheduler_job_keys.py`` (#479) and ``test_scheduler_s2s_restart.py``
(#488) don't cover: System Status Off, locked and disabled transfers, a
missing SSDW transfer, the interval from the API; and ``reboot_reset.py``'s
tasks, locked transfers and transfers in error (``test_transfer_lock.py``
covers its locks, #478).
"""

from unittest.mock import Mock

import pytest

from server.workers import reboot_reset, scheduler

INTERVAL = 5


class EndOfCycle(Exception):
    """Raised by the patched sleep to end the scheduler's loop."""


def _ovdm(**overrides):
    ovdm = Mock()
    ovdm.get_transfer_log_dir.return_value = '/tmp'
    ovdm.get_logfile_purge_timedelta.return_value = '30 days'
    ovdm.get_system_status.return_value = 'On'
    ovdm.get_transfer_interval.return_value = INTERVAL
    ovdm.get_active_collection_system_transfers.return_value = [{'collectionSystemTransferID': 1, 'longName': 'CST 1'}]
    ovdm.get_cruise_data_transfers.return_value = [{'cruiseDataTransferID': 3, 'longName': 'CDT 3'}]
    ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'longName': 'Ship-to-shore', 'enable': 1, 'pid': 0}]
    for name, value in overrides.items():
        getattr(ovdm, name).return_value = value
    return ovdm


def _cycle(monkeypatch, ovdm, interval=INTERVAL, locked=(), end=None, seconds=(0,)):  # pylint: disable=too-many-arguments
    """Run the scheduler until the sleep *end* (default: the end-of-cycle wait); return the jobs and
    sleeps. *seconds* are the clock's seconds past the minute, in turn."""
    gm_client = Mock()
    monkeypatch.setattr(scheduler, 'OpenVDM', lambda: ovdm)
    monkeypatch.setattr(scheduler, 'GearmanClient', lambda servers: gm_client)
    monkeypatch.setattr(scheduler, 'purge_old_files', Mock())
    monkeypatch.setattr(scheduler, 'transfer_locked', lambda kind, transfer_id: (kind, transfer_id) in locked)
    clock = iter(seconds)
    monkeypatch.setattr(scheduler.time, 'gmtime', lambda: Mock(tm_sec=next(clock, 0)))
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if (end or (lambda s: s > 60))(seconds):
            raise EndOfCycle
    monkeypatch.setattr(scheduler.time, 'sleep', sleep)
    with pytest.raises(EndOfCycle):
        scheduler.scheduler(interval)
    return [call.args[0] for call in gm_client.submit_job.call_args_list], sleeps


def test_cycle(monkeypatch, caplog) -> None:
    """A cycle submits each transfer's job, then waits out the interval less the time spent."""
    caplog.set_level('INFO')
    tasks, sleeps = _cycle(monkeypatch, _ovdm())
    assert tasks == ['runCollectionSystemTransfer', 'runCruiseDataTransfer', 'runShipToShoreTransfer']
    assert sleeps[-1] == INTERVAL * 60 - 2 - 2 - 2
    assert 'Logfile purge age set to: 30 days' in caplog.text


def test_interval_from_api(monkeypatch) -> None:
    """Without an interval, the API's transfer interval is used."""
    _, sleeps = _cycle(monkeypatch, _ovdm(get_transfer_interval=10), interval=None)
    assert sleeps[-1] == 10 * 60 - 6


def test_system_status_off(monkeypatch) -> None:
    """With System Status Off, no jobs are submitted."""
    ovdm = _ovdm(get_system_status='Off')
    tasks, _ = _cycle(monkeypatch, ovdm, end=lambda seconds: seconds == INTERVAL)
    assert tasks == []
    ovdm.get_active_collection_system_transfers.assert_not_called()


def test_locked_cruise_data_transfer(monkeypatch) -> None:
    """A cruise data transfer a job is running isn't submitted again (#478)."""
    tasks, _ = _cycle(monkeypatch, _ovdm(), locked={(scheduler.CDT, 3)})
    assert 'runCruiseDataTransfer' not in tasks


def test_disabled_ship_to_shore(monkeypatch) -> None:
    """A disabled ship-to-shore transfer isn't submitted."""
    tasks, _ = _cycle(monkeypatch, _ovdm(get_required_cruise_data_transfers=[
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'longName': 'Ship-to-shore', 'enable': 0, 'pid': 0}]))
    assert 'runShipToShoreTransfer' not in tasks


def test_no_ship_to_shore_transfer(monkeypatch, caplog) -> None:
    """Without the SSDW transfer, that's logged; the others are still submitted."""
    tasks, _ = _cycle(monkeypatch, _ovdm(get_required_cruise_data_transfers=[]))
    assert tasks == ['runCollectionSystemTransfer', 'runCruiseDataTransfer']
    assert 'SSDW transfer does not exists' in caplog.text


def test_waits_for_the_minute(monkeypatch) -> None:
    """A cycle starts at the top of a minute: 42 s past it, it waits 18 s."""
    _, sleeps = _cycle(monkeypatch, _ovdm(), seconds=(42, 0))
    assert sleeps[:2] == [10, 18]     # the start-up wait, then to the minute


# --- Reboot reset -----------------------------------------------------------------

@pytest.fixture
def reset(monkeypatch, fake_ovdm):
    """Return a function that runs the reboot reset with *locked* transfers held."""
    fake_ovdm.get_tasks.return_value = [{'taskID': 1}, {'taskID': 2}]
    fake_ovdm.get_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'SCS', 'status': 1},
        {'collectionSystemTransferID': 2, 'name': 'CTD', 'status': 3}]
    fake_ovdm.get_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 3, 'name': 'Backup', 'status': 1},
        {'cruiseDataTransferID': 5, 'name': 'USB', 'status': 3}]
    fake_ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'status': 1}]
    monkeypatch.setattr(reboot_reset, 'OpenVDM', lambda: fake_ovdm)

    def run(locked=()):
        monkeypatch.setattr(reboot_reset, 'transfer_locked', lambda kind, transfer_id: (kind, transfer_id) in locked)
        reboot_reset.reboot_reset()
    return run


def test_reboot_reset(reset, fake_ovdm) -> None:
    """Every task and every transfer not in error is set idle, and the Gearman jobs are cleared."""
    reset()
    assert [call.args for call in fake_ovdm.set_idle_task.call_args_list] == [(1,), (2,)]
    fake_ovdm.set_idle_collection_system_transfer.assert_called_once_with(1)
    assert [call.args for call in fake_ovdm.set_idle_cruise_data_transfer.call_args_list] == [(3,), (4,)]
    fake_ovdm.clear_gearman_jobs_from_db.assert_called_once()


def test_reboot_reset_running_transfers(reset, fake_ovdm, caplog) -> None:
    """Transfers a job is still running are left alone, and so are the Gearman jobs (#478)."""
    reset(locked={(reboot_reset.CDT, 3), (reboot_reset.CDT, 4)})
    fake_ovdm.set_idle_cruise_data_transfer.assert_not_called()
    fake_ovdm.clear_gearman_jobs_from_db.assert_not_called()
    assert 'Left alone, still running: Backup, SSDW' in caplog.text
