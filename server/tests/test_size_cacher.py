"""Tests for the size cacher (#512 part 4).

``size_cacher.py`` loops forever: each pass measures the current cruise and
lowering directories with ``du -sb`` and stores the sizes in OpenVDM. The
tests run passes until ``time.sleep`` (patched) has been called enough times;
``du`` goes to the ``fake_run`` fixture.
"""

import pytest

from server.workers import size_cacher


class Done(Exception):
    """Raised by the patched sleep to end the loop."""


@pytest.fixture
def run(monkeypatch, fake_ovdm):
    """Return a function that runs *passes* passes of the size cacher; ``du`` goes to fake_run."""
    monkeypatch.setattr(size_cacher, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_lowering_id.return_value = 'DIVE01'
    fake_ovdm.get_show_lowering_components.return_value = True

    def run_passes(passes=1, interval=600):
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == passes:
                raise Done
        monkeypatch.setattr(size_cacher.time, 'sleep', sleep)
        with pytest.raises(Done):
            size_cacher.size_cacher(interval)
        return sleeps
    return run_passes


@pytest.fixture
def lowering_dir(warehouse):
    """The current lowering's directory."""
    path = warehouse.cruise_dir / 'Vehicle' / 'DIVE01'
    path.mkdir(parents=True)
    return path


def test_sizes(run, fake_ovdm, fake_run, warehouse, lowering_dir) -> None:
    """The cruise's and lowering's sizes are measured with du and stored; the pass then waits out
    the rest of the interval."""
    fake_run.on('du', '-sb', str(warehouse.cruise_dir), stdout=f'123456\t{warehouse.cruise_dir}\n')
    fake_run.on('du', '-sb', str(lowering_dir), stdout=f'789\t{lowering_dir}\n')
    sleeps = run()
    fake_ovdm.set_cruise_size.assert_called_once_with('123456')
    fake_ovdm.set_lowering_size.assert_called_once_with('789')
    assert fake_run.commands() == [['du', '-sb', str(warehouse.cruise_dir)], ['du', '-sb', str(lowering_dir)]]
    assert 599 < sleeps[0] <= 600


def test_no_lowering_components(run, fake_ovdm, fake_run, warehouse) -> None:
    """Without lowering components, only the cruise is measured; the lowering size is cleared."""
    fake_ovdm.get_show_lowering_components.return_value = False
    fake_run.on('du', stdout=f'5\t{warehouse.cruise_dir}\n')
    run()
    fake_ovdm.set_lowering_size.assert_called_once_with(None)
    assert len(fake_run.commands()) == 1


def test_missing_directories(run, fake_ovdm, fake_run, caplog) -> None:
    """A directory that doesn't exist (the lowering's, here) has no size, and du isn't run for it."""
    fake_run.on('du', stdout='5\t/x\n')
    run()
    fake_ovdm.set_lowering_size.assert_called_once_with(None)
    assert 'Path is not a directory or does not exist' in caplog.text


def test_du_partial_output(run, fake_ovdm, fake_run, warehouse, caplog) -> None:
    """When du fails (e.g. files vanished while it ran), its total is still used if it gave one."""
    fake_run.on('du', returncode=1, stdout=f'42\t{warehouse.cruise_dir}\n', stderr='du: cannot access x\n')
    run()
    fake_ovdm.set_cruise_size.assert_called_once_with('42')
    assert 'du failed (some files may have disappeared): du: cannot access x' in caplog.text


@pytest.mark.parametrize('stdout', ['', ' '], ids=['no-output', 'blank'])
def test_du_fails(run, fake_ovdm, fake_run, stdout) -> None:
    """When du fails without a total, there's no size."""
    fake_run.on('du', returncode=1, stdout=stdout, stderr='du: error\n')
    run()
    fake_ovdm.set_cruise_size.assert_called_once_with(None)


def test_du_cant_run(run, fake_ovdm, fake_run, caplog) -> None:
    """If du can't run, there's no size, and the loop carries on."""
    fake_run.on('du', raises=FileNotFoundError(2, 'No such file or directory'))
    run(passes=2)
    assert fake_ovdm.set_cruise_size.call_count == 2
    assert 'Exception while running du' in caplog.text


def test_api_unreachable(run, fake_ovdm, fake_run, caplog) -> None:
    """If the API can't be reached, the pass is skipped, and the next one tries again."""
    fake_ovdm.get_cruise_id.side_effect = [OSError('connection refused'), 'TEST001']
    fake_run.on('du', stdout='5\t/x\n')
    run(passes=2)
    assert 'Unable to retrieve data from OpenVDM API: connection refused' in caplog.text
    fake_ovdm.set_cruise_size.assert_called_once()


def test_slow_pass_doesnt_wait(fake_ovdm, fake_run, monkeypatch) -> None:
    """A pass that took longer than the interval starts the next one at once."""
    monkeypatch.setattr(size_cacher, 'OpenVDM', lambda: fake_ovdm)
    fake_ovdm.get_show_lowering_components.return_value = False
    fake_run.on('du', stdout='5\t/x\n')
    fake_ovdm.set_cruise_size.side_effect = [None, Done()]
    sleep = pytest.fail
    monkeypatch.setattr(size_cacher.time, 'sleep', lambda seconds: sleep(f'slept {seconds}'))
    with pytest.raises(Done):
        size_cacher.size_cacher(0)


# --- Bugs -----------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="join() of the base directory and None raises (#588)")
def test_no_current_cruise(run, fake_ovdm, fake_run) -> None:
    """Without a current cruise (a new install), the pass stores no sizes instead of crashing."""
    fake_ovdm.get_cruise_id.return_value = None
    run(passes=2)
    fake_ovdm.set_cruise_size.assert_called_with(None)


@pytest.mark.xfail(strict=True, reason="storing the sizes isn't in the try (#588)")
def test_api_fails_storing_sizes(run, fake_ovdm, fake_run) -> None:
    """If storing the sizes fails, the pass is logged and the loop carries on."""
    fake_run.on('du', stdout='5\t/x\n')
    fake_ovdm.set_cruise_size.side_effect = [OSError('connection refused'), None]
    run(passes=2)
    assert fake_ovdm.set_cruise_size.call_count == 2
