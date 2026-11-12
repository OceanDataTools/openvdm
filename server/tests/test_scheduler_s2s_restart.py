"""Tests for the scheduler's hourly ship-to-shore restart (#488)."""

from unittest.mock import Mock

import pytest

from server.workers import scheduler

INTERVAL = 5    # minutes, the default transfer interval
SSDW_ID = 4


class EndOfRun(Exception):
    """Raised by the patched sleep after the last cycle."""


class FakeShipToShore:
    """A ship-to-shore job that holds its lock until stopped, or for *duration* seconds."""

    def __init__(self, clock, duration=None, running_at_start=False):
        self.clock = clock
        self.duration = duration
        self.ends_at = float('inf') if running_at_start else None
        self.events = []

    def locked(self, kind, transfer_id):
        """transfer_locked() for SSDW."""
        return (kind, transfer_id) == (scheduler.CDT, SSDW_ID) and self.ends_at is not None \
            and self.clock['now'] < self.ends_at

    def submit_job(self, task, data, **kwargs):
        """Record runs and stops; a run takes the lock, a stop ends it."""
        if task == 'runShipToShoreTransfer':
            self.events.append(('run', self.clock['now']))
            self.ends_at = self.clock['now'] + (self.duration or float('inf'))
        elif task == 'stopJob':
            self.events.append(('stop', self.clock['now']))
            self.ends_at = self.clock['now'] + 3     # the stopped job ends a few seconds later


def _run(monkeypatch, s2s, cycles, enable=1):
    """Run the scheduler for *cycles* passes against a fake clock."""
    ovdm = Mock()
    ovdm.get_transfer_log_dir.return_value = '/tmp'
    ovdm.get_logfile_purge_timedelta.return_value = None
    ovdm.get_system_status.return_value = 'On'
    ovdm.get_active_collection_system_transfers.return_value = []
    ovdm.get_cruise_data_transfers.return_value = []
    ovdm.get_required_cruise_data_transfers.return_value = [
        {'cruiseDataTransferID': SSDW_ID, 'name': 'SSDW', 'longName': 'Ship-to-shore',
         'enable': enable, 'pid': 1234}]
    monkeypatch.setattr(scheduler, 'OpenVDM', lambda: ovdm)
    monkeypatch.setattr(scheduler, 'GearmanClient', lambda servers: s2s)
    monkeypatch.setattr(scheduler, 'purge_old_files', Mock())
    monkeypatch.setattr(scheduler, 'transfer_locked', s2s.locked)
    monkeypatch.setattr(scheduler.time, 'monotonic', lambda: s2s.clock['now'])
    # The scheduler waits for the start of a minute by gmtime(): from the same
    # clock, or each cycle would be longer by a real-time-dependent amount
    real_gmtime = scheduler.time.gmtime
    monkeypatch.setattr(scheduler.time, 'gmtime', lambda *args: real_gmtime(s2s.clock['now']))

    end_of_cycle = INTERVAL * 60 - 2
    passes = {'done': 0}

    def sleep(seconds):
        s2s.clock['now'] += seconds
        if seconds == end_of_cycle:
            passes['done'] += 1
            if passes['done'] == cycles:
                raise EndOfRun

    monkeypatch.setattr(scheduler.time, 'sleep', sleep)
    with pytest.raises(EndOfRun):
        scheduler.scheduler(INTERVAL)
    return s2s.events


@pytest.fixture
def clock():
    """The fake clock's state."""
    return {'now': 0.0}


def test_a_long_run_is_restarted_after_an_hour(monkeypatch, clock) -> None:
    """A run still going after an hour is stopped and a new one started in the same pass."""
    events = _run(monkeypatch, FakeShipToShore(clock), cycles=30)

    kinds = [kind for kind, _ in events]
    assert kinds == ['run', 'stop', 'run', 'stop', 'run']
    (_, first), (_, stop), (_, second) = events[:3]
    assert 3600 < stop - first <= 3600 + INTERVAL * 60
    assert second - stop < 60


def test_nothing_is_submitted_while_a_run_is_going(monkeypatch, clock) -> None:
    """Passes during a run don't submit another job, which would only merge into it."""
    events = _run(monkeypatch, FakeShipToShore(clock), cycles=10)
    assert events == [('run', events[0][1])]


def test_short_runs_are_started_every_pass_and_never_stopped(monkeypatch, clock) -> None:
    """Runs that end within an interval get a new run each pass and no restarts."""
    events = _run(monkeypatch, FakeShipToShore(clock, duration=120), cycles=20)
    kinds = [kind for kind, _ in events]
    assert 'stop' not in kinds and kinds.count('run') == 20


def test_a_run_started_elsewhere_is_timed_from_when_it_is_first_seen(monkeypatch, clock) -> None:
    """A manual run, or one going when the scheduler starts, is restarted an hour after it's first seen."""
    events = _run(monkeypatch, FakeShipToShore(clock, running_at_start=True), cycles=16)
    assert [kind for kind, _ in events] == ['stop', 'run']
    assert events[0][1] > 3600


def test_disabled_transfer_is_not_started_after_a_stop(monkeypatch, clock) -> None:
    """With SSDW disabled, a run still going gets its restart's stop but no new run."""
    events = _run(monkeypatch, FakeShipToShore(clock, running_at_start=True), cycles=16, enable=0)
    assert [kind for kind, _ in events] == ['stop']
