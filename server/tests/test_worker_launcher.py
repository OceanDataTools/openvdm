"""Tests for the worker launcher, which reports failed workers in an OpenVDM message (#503)."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from server.lib import openvdm, worker_launcher


@pytest.fixture(autouse=True)
def report_dir(monkeypatch, tmp_path):
    """Record reported failures in a temporary directory; returns it."""
    directory = tmp_path / 'run'
    monkeypatch.setattr(worker_launcher, 'REPORT_DIR', str(directory))
    return directory


@pytest.fixture
def ovdm(monkeypatch):
    """A fake OpenVDM whose messages are recorded; returns it."""
    instance = Mock()
    monkeypatch.setattr(openvdm, 'OpenVDM', lambda: instance)
    return instance


@pytest.fixture(autouse=True)
def keep_argv_and_path(monkeypatch):
    """main() changes sys.argv and sys.path, as running the worker directly would."""
    monkeypatch.setattr(sys, 'argv', list(sys.argv))
    monkeypatch.setattr(sys, 'path', list(sys.path))


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / f'{name}.py'
    path.write_text(body, encoding='utf-8')
    return str(path)


def test_missing_package_is_reported(tmp_path, ovdm, capsys) -> None:
    """A worker that fails on import is reported, with the fix, and exits with 1."""
    script = _script(tmp_path, 'cruise', 'import jinja2_not_installed\n')

    assert worker_launcher.main([script]) == 1

    title, body = ovdm.send_msg.call_args.args
    assert title == 'Worker cruise stopped'
    assert "No module named 'jinja2_not_installed'" in body and 'requirements.txt' in body
    assert 'Traceback' in capsys.readouterr().err


def test_other_failures_point_to_the_log(tmp_path, ovdm) -> None:
    """Other exceptions name the worker's log."""
    script = _script(tmp_path, 'md5_summary', 'raise RuntimeError("bad setting")\n')

    assert worker_launcher.main([script]) == 1
    assert '/var/log/openvdm/md5_summary.log' in ovdm.send_msg.call_args.args[1]
    assert 'RuntimeError: bad setting' in ovdm.send_msg.call_args.args[1]


def test_normal_end_is_not_reported(tmp_path, ovdm) -> None:
    """A worker that ends normally (e.g. stopped by Supervisor) exits with 0."""
    script = _script(tmp_path, 'stop_job', 'x = 1\n')
    assert worker_launcher.main([script]) == 0
    ovdm.send_msg.assert_not_called()


def test_runs_as_main_with_its_own_arguments(tmp_path, ovdm) -> None:
    """The worker sees __name__ == '__main__', its own path and its arguments."""
    out = tmp_path / 'out.txt'
    script = _script(tmp_path, 'worker', (
        'import sys\n'
        f'open({str(out)!r}, "w").write(" ".join([__name__, __file__] + sys.argv[1:]))\n'))

    assert worker_launcher.main([script, '-v', '-v']) == 0
    assert out.read_text() == f'__main__ {script} -v -v'


def test_sys_exit_keeps_its_status(tmp_path, ovdm) -> None:
    """A worker's own sys.exit() (e.g. argparse's usage error) isn't reported."""
    script = _script(tmp_path, 'worker', 'import sys\nsys.exit(2)\n')
    with pytest.raises(SystemExit) as exc:
        worker_launcher.main([script])
    assert exc.value.code == 2
    ovdm.send_msg.assert_not_called()


def test_usage_without_a_script(capsys) -> None:
    """No worker script is a usage error."""
    assert worker_launcher.main([]) == 2
    assert 'usage' in capsys.readouterr().err


def test_same_failure_is_reported_once_an_hour(report_dir) -> None:
    """Supervisor's restarts don't repeat the message; a new failure or an hour later does."""
    first = worker_launcher._first_report  # pylint: disable=protected-access
    assert first('cruise', 'ModuleNotFoundError: x', now=1000)
    record = report_dir / 'worker-cruise.failed'
    os.utime(record, (1000, 1000))

    assert not first('cruise', 'ModuleNotFoundError: x', now=1000 + 60)
    assert first('lowering', 'ModuleNotFoundError: x', now=1000 + 60)
    assert first('cruise', 'RuntimeError: y', now=1000 + 60)
    os.utime(record, (1000, 1000))
    assert first('cruise', 'RuntimeError: y', now=1000 + worker_launcher.REPEAT_AFTER + 1)


def test_restarted_worker_does_not_post_again(tmp_path, ovdm) -> None:
    """Each of Supervisor's restarts fails the same way; only the first is posted."""
    script = _script(tmp_path, 'cruise', 'import jinja2_not_installed\n')
    for _ in range(4):
        assert worker_launcher.main([script]) == 1
    assert ovdm.send_msg.call_count == 1


def test_unreported_when_openvdm_is_unavailable(tmp_path, monkeypatch, caplog) -> None:
    """Without openvdm.yaml there's nowhere to post: it's logged, and the exit status is the same."""
    def no_config():
        raise FileNotFoundError('OpenVDM configuration file not found: openvdm.yaml')

    monkeypatch.setattr(openvdm, 'OpenVDM', no_config)
    script = _script(tmp_path, 'cruise', 'raise RuntimeError("x")\n')

    assert worker_launcher.main([script]) == 1
    assert 'Unable to post an OpenVDM message' in caplog.text


def test_unwritable_record_still_reports(monkeypatch, ovdm, tmp_path) -> None:
    """If the record can't be written, the failure is reported every time rather than never."""
    blocker = tmp_path / 'file'
    blocker.write_text('')
    monkeypatch.setattr(worker_launcher, 'REPORT_DIR', str(blocker / 'run'))
    script = _script(tmp_path, 'cruise', 'raise RuntimeError("x")\n')

    worker_launcher.main([script])
    worker_launcher.main([script])
    assert ovdm.send_msg.call_count == 2
