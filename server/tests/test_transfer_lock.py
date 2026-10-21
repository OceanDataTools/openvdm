"""Tests for the per-transfer lock files that let only one job run a transfer (#478)."""

import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from server.lib import transfer_lock
from server.lib.transfer_lock import CDT, CST, acquire_transfer_lock, release_transfer_lock, transfer_locked
from server.workers import reboot_reset
from server.workers import run_collection_system_transfer as cst_run
from server.workers import run_cruise_data_transfer as cdt_run
from server.workers import run_ship_to_shore_transfer as s2s_run
from server.workers import stop_job
from server.workers import test_collection_system_transfer as cst_test

# Holds a transfer's lock in another process until killed
HOLDER = """
import sys, time
sys.path.insert(0, sys.argv[1])
from server.lib import transfer_lock
transfer_lock.LOCK_DIR = sys.argv[2]
lock = transfer_lock.acquire_transfer_lock('cst', 1)
print('locked' if lock else 'busy', flush=True)
time.sleep(60)
"""

REPO_ROOT = str(Path(__file__).resolve().parents[2])


@pytest.fixture(autouse=True)
def lock_dir(monkeypatch, tmp_path: Path) -> Path:
    """Put the lock files in a temporary directory and don't wait on retries."""
    path = tmp_path / 'locks'
    monkeypatch.setattr(transfer_lock, 'LOCK_DIR', str(path))
    monkeypatch.setattr(transfer_lock, 'ACQUIRE_RETRY_DELAY', 0)
    return path


@pytest.fixture
def held_elsewhere(lock_dir: Path):
    """Hold CST 1's lock in another process; yields that process."""
    proc = subprocess.Popen([sys.executable, '-c', HOLDER, REPO_ROOT, str(lock_dir)],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'locked'
        yield proc
    finally:
        proc.kill()
        proc.wait()


def test_only_one_holder() -> None:
    """A second acquire fails while the lock is held, and works once it's released."""
    lock = acquire_transfer_lock(CST, 1)
    assert lock is not None
    assert acquire_transfer_lock(CST, 1) is None
    release_transfer_lock(lock)

    lock = acquire_transfer_lock(CST, 1)
    assert lock is not None
    release_transfer_lock(lock)


def test_kinds_and_ids_are_separate() -> None:
    """CST 1, CDT 1 and CST 2 each have their own lock."""
    locks = [acquire_transfer_lock(CST, 1), acquire_transfer_lock(CDT, 1),
             acquire_transfer_lock(CST, 2)]
    assert all(locks)
    for lock in locks:
        release_transfer_lock(lock)


def test_transfer_locked() -> None:
    """transfer_locked() is True only while a job holds the lock, and doesn't keep it."""
    assert not transfer_locked(CST, 1)     # no lock file yet

    lock = acquire_transfer_lock(CST, 1)
    assert transfer_locked(CST, 1)
    assert not transfer_locked(CDT, 1)
    release_transfer_lock(lock)

    assert not transfer_locked(CST, 1)
    lock = acquire_transfer_lock(CST, 1)   # the check left it free
    assert lock is not None
    release_transfer_lock(lock)


def test_checks_at_the_same_moment_dont_see_each_other(lock_dir) -> None:
    """A check in progress (a shared lock) isn't taken for a running job (#487)."""
    release_transfer_lock(acquire_transfer_lock(CST, 1))   # create the file
    with open(lock_dir / 'cst-1.lock', 'r', encoding='utf-8') as other_check:
        fcntl.flock(other_check, fcntl.LOCK_SH | fcntl.LOCK_NB)
        assert not transfer_locked(CST, 1)
        fcntl.flock(other_check, fcntl.LOCK_UN)


def test_released_when_the_holder_is_killed(held_elsewhere) -> None:
    """A killed job doesn't leave its transfer locked."""
    assert transfer_locked(CST, 1)
    assert acquire_transfer_lock(CST, 1) is None

    held_elsewhere.send_signal(signal.SIGKILL)
    held_elsewhere.wait()

    assert not transfer_locked(CST, 1)


def test_not_inherited_by_child_processes() -> None:
    """An rsync or rclone child doesn't keep the lock once the job releases it."""
    lock = acquire_transfer_lock(CST, 1)
    child = subprocess.Popen(['sleep', '30'])
    try:
        release_transfer_lock(lock)
        assert not transfer_locked(CST, 1)
    finally:
        child.kill()
        child.wait()


def test_release_none_is_a_no_op() -> None:
    """Releasing when no lock was taken does nothing."""
    release_transfer_lock(None)


# Transfer workers


@pytest.fixture
def root_handler():
    """The workers set the format of the root logger's first handler."""
    handler = logging.NullHandler()
    logging.getLogger().handlers.insert(0, handler)
    yield
    logging.getLogger().removeHandler(handler)


def _cst_worker():
    """A collection system transfer worker for CST 1, without __init__."""
    worker = object.__new__(cst_run.OVDMGearmanWorker)
    worker.transfer_lock = None
    worker.ovdm = Mock()
    worker.ovdm.get_collection_system_transfer.return_value = {
        'collectionSystemTransferID': 1, 'name': 'CST1', 'status': 2, 'enable': 0}
    worker._ignore_job = Mock(side_effect=lambda job, part, reason: reason)
    return worker


def _job(payload):
    return Mock(data=json.dumps(payload), handle='H:1')


CST_JOB = {'collectionSystemTransfer': {'collectionSystemTransferID': 1}, 'systemStatus': 'On'}


@pytest.mark.usefixtures('root_handler')
def test_worker_ignores_a_job_for_a_locked_transfer(held_elsewhere) -> None:
    """Another job holding the lock is running the transfer, whatever its status says."""
    worker = _cst_worker()
    assert worker.on_job_execute(_job(CST_JOB)) == "Transfer is already in-progress"


@pytest.mark.usefixtures('root_handler')
def test_worker_runs_a_transfer_shown_as_running_but_unlocked() -> None:
    """A status left at Running with no job behind it doesn't block the transfer."""
    worker = _cst_worker()
    worker.ovdm.get_collection_system_transfer.return_value['status'] = 1
    # Disabled, so the job stops at the next check, after taking the lock
    assert worker.on_job_execute(_job(CST_JOB)) == "Transfer is disabled"


@pytest.mark.usefixtures('root_handler')
def test_worker_holds_the_lock_while_the_job_runs() -> None:
    """The lock is held during the job and released when it ends."""
    worker = _cst_worker()
    seen = {}

    def run(job):
        worker.transfer_lock = acquire_transfer_lock(CST, 1)
        seen['locked'] = transfer_locked(CST, 1)
        return 'done'

    worker._run_job = run
    assert worker.on_job_execute(_job(CST_JOB)) == 'done'
    assert seen['locked']
    assert worker.transfer_lock is None
    assert not transfer_locked(CST, 1)


@pytest.mark.parametrize('module', [cst_run, cdt_run, s2s_run])
def test_worker_releases_the_lock_when_the_job_raises(module) -> None:
    """An exception in the job doesn't leave the transfer locked."""
    worker = object.__new__(module.OVDMGearmanWorker)

    def run(job):
        worker.transfer_lock = acquire_transfer_lock(CST if module is cst_run else CDT, 1)
        raise RuntimeError('boom')

    worker._run_job = run
    with pytest.raises(RuntimeError):
        worker.on_job_execute(Mock())
    assert worker.transfer_lock is None
    assert not transfer_locked(CST, 1) and not transfer_locked(CDT, 1)


@pytest.mark.usefixtures('root_handler')
def test_cruise_data_and_ship_to_shore_share_a_lock() -> None:
    """A ship-to-shore job is ignored while a cruise data job runs the same transfer."""
    lock = acquire_transfer_lock(CDT, 5)
    try:
        worker = object.__new__(s2s_run.OVDMGearmanWorker)
        worker.transfer_lock = None
        worker.ovdm = Mock()
        worker.ovdm.get_required_cruise_data_transfer_by_name.return_value = {
            'cruiseDataTransferID': 5, 'name': 'SSDW', 'status': 2, 'enable': 1}
        worker._ignore_job = Mock(side_effect=lambda job, part, reason: reason)
        assert worker.on_job_execute(_job({'bandwidthLimitStatus': True})) == \
            "Transfer is already in-progress"
    finally:
        release_transfer_lock(lock)


# Stop, Test Setup and reboot_reset


def _stop_worker(job_type='collectionSystemTransfer', job_id=1):
    worker = Mock()
    worker.job_info = {'type': job_type, 'id': job_id, 'name': 'X', 'pid': 999999}
    return worker


def test_stop_signals_a_running_transfer_and_leaves_its_status(monkeypatch) -> None:
    """The signalled job sets its own status when it ends."""
    kill = Mock()
    monkeypatch.setattr(stop_job.os, 'kill', kill)
    worker = _stop_worker()
    lock = acquire_transfer_lock(CST, 1)
    try:
        stop_job.task_stop_job(worker, Mock())
    finally:
        release_transfer_lock(lock)
    kill.assert_called_once_with(999999, signal.SIGQUIT)
    worker.ovdm.set_idle_collection_system_transfer.assert_not_called()


def test_stop_idles_a_transfer_with_no_job_without_signalling(monkeypatch) -> None:
    """With no lock held, the stored PID is stale and may be another process's."""
    kill = Mock()
    monkeypatch.setattr(stop_job.os, 'kill', kill)
    worker = _stop_worker('cruiseDataTransfer', 3)
    stop_job.task_stop_job(worker, Mock())
    kill.assert_not_called()
    worker.ovdm.set_idle_cruise_data_transfer.assert_called_once_with(3)


def test_stop_still_signals_and_idles_a_task(monkeypatch) -> None:
    """Tasks don't have locks: they're signalled and set idle as before."""
    kill = Mock()
    monkeypatch.setattr(stop_job.os, 'kill', kill)
    worker = _stop_worker('task', 4)
    stop_job.task_stop_job(worker, Mock())
    kill.assert_called_once_with(999999, signal.SIGQUIT)
    worker.ovdm.set_idle_task.assert_called_once_with(4)


def _test_setup_worker():
    worker = object.__new__(cst_test.OVDMGearmanWorker)
    worker.ovdm = Mock()
    worker.collection_system_transfer = {'collectionSystemTransferID': 1}
    return worker


@pytest.mark.parametrize('result', ['Pass', 'Fail'])
def test_test_setup_leaves_a_running_transfer_alone(monkeypatch, result) -> None:
    """A test's outcome doesn't change the status of a transfer a job is running."""
    monkeypatch.setattr(cst_test.python3_gearman.GearmanWorker, 'send_job_complete', Mock())
    worker = _test_setup_worker()
    job_result = json.dumps({'parts': [{'partName': 'Source', 'result': result, 'reason': 'r'}]})

    lock = acquire_transfer_lock(CST, 1)
    try:
        worker.on_job_complete(Mock(handle='H:1'), job_result)
    finally:
        release_transfer_lock(lock)

    worker.ovdm.set_idle_collection_system_transfer.assert_not_called()
    if result == 'Fail':
        # The message is still posted
        worker.ovdm.set_error_collection_system_transfer_test.assert_called_once_with(
            1, 'r', set_status=False)


@pytest.mark.parametrize('result', ['Pass', 'Fail'])
def test_test_setup_sets_the_status_of_an_idle_transfer(monkeypatch, result) -> None:
    """Without a running job, Test Setup sets the status as before."""
    monkeypatch.setattr(cst_test.python3_gearman.GearmanWorker, 'send_job_complete', Mock())
    worker = _test_setup_worker()
    job_result = json.dumps({'parts': [{'partName': 'Source', 'result': result, 'reason': 'r'}]})
    worker.on_job_complete(Mock(handle='H:1'), job_result)

    if result == 'Fail':
        worker.ovdm.set_error_collection_system_transfer_test.assert_called_once_with(
            1, 'r', set_status=True)
    else:
        worker.ovdm.set_idle_collection_system_transfer.assert_called_once_with(1)


def _reboot_ovdm():
    ovdm = Mock()
    ovdm.get_tasks.return_value = []
    ovdm.get_collection_system_transfers.return_value = [
        {'collectionSystemTransferID': 1, 'name': 'CST1', 'status': 1},
        {'collectionSystemTransferID': 2, 'name': 'CST2', 'status': 1}]
    ovdm.get_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 3, 'name': 'CDT3', 'status': 1}]
    ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': 4, 'name': 'SSDW', 'status': 1}]
    return ovdm


def test_reboot_reset_leaves_running_transfers_and_the_job_list(monkeypatch) -> None:
    """A transfer whose lock is held keeps its status, and the job list is kept."""
    ovdm = _reboot_ovdm()
    monkeypatch.setattr(reboot_reset, 'OpenVDM', lambda: ovdm)
    locks = [acquire_transfer_lock(CST, 1), acquire_transfer_lock(CDT, 4)]
    try:
        reboot_reset.reboot_reset()
    finally:
        for lock in locks:
            release_transfer_lock(lock)

    ovdm.set_idle_collection_system_transfer.assert_called_once_with(2)
    ovdm.set_idle_cruise_data_transfer.assert_called_once_with(3)
    ovdm.clear_gearman_jobs_from_db.assert_not_called()


def test_reboot_reset_resets_everything_at_start_up(monkeypatch) -> None:
    """At start-up no lock is held: every transfer is reset and the job list cleared."""
    ovdm = _reboot_ovdm()
    monkeypatch.setattr(reboot_reset, 'OpenVDM', lambda: ovdm)
    reboot_reset.reboot_reset()

    assert ovdm.set_idle_collection_system_transfer.call_count == 2
    assert ovdm.set_idle_cruise_data_transfer.call_count == 2
    ovdm.clear_gearman_jobs_from_db.assert_called_once_with()


def test_lock_files_stay_in_place(lock_dir: Path) -> None:
    """Releasing doesn't delete the file, so two jobs can't lock different files."""
    release_transfer_lock(acquire_transfer_lock(CST, 1))
    assert os.path.exists(lock_dir / 'cst-1.lock')
