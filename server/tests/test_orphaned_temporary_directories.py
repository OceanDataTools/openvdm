"""Tests for cleaning up temporary directories left by killed workers."""

import fcntl
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from server.lib import file_utils


@pytest.fixture(scope='module')
def dead_pid() -> int:
    """The PID of a process that has exited."""
    proc = subprocess.Popen([sys.executable, '-c', 'pass'])
    proc.wait()
    return proc.pid


def test_temporary_directory_names_its_process() -> None:
    """The directory name carries the PID of the process that made it."""
    with file_utils.temporary_directory() as tmpdir:
        assert os.path.basename(tmpdir).startswith(f'openvdm-{os.getpid()}-')
    assert not os.path.exists(tmpdir)


def test_only_directories_of_gone_processes_are_cleaned(tmp_path: Path, dead_pid: int) -> None:
    """A live process's directory and directories OpenVDM didn't name are left alone."""
    orphan = tmp_path / f'openvdm-{dead_pid}-abc_12'
    (orphan / 'mntpoint').mkdir(parents=True)
    (orphan / 'rsyncFileList.txt').write_text('x')
    live = tmp_path / f'openvdm-{os.getpid()}-def'
    live.mkdir()
    other = tmp_path / 'tmpxyz'
    other.mkdir()
    not_a_dir = tmp_path / f'openvdm-{dead_pid}-file'
    not_a_dir.write_text('x')

    cleaned = file_utils.cleanup_orphaned_temporary_directories(str(tmp_path))

    assert cleaned == [str(orphan)]
    assert not orphan.exists()
    assert live.exists() and other.exists() and not_a_dir.exists()


def test_mount_that_wont_unmount_is_left_in_place(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dead_pid: int) -> None:
    """Never delete through a mount: if umount fails, the directory stays (#207)."""
    orphan = tmp_path / f'openvdm-{dead_pid}-mnt'
    (orphan / 'mntpoint').mkdir(parents=True)
    (orphan / 'mntpoint' / 'share_file').write_text('on the share')
    monkeypatch.setattr(file_utils.os.path, 'ismount', lambda path: path.endswith('mntpoint'))
    run = Mock(return_value=Mock(returncode=32, stderr='target is busy'))
    monkeypatch.setattr(file_utils.subprocess, 'run', run)

    file_utils.cleanup_orphaned_temporary_directories(str(tmp_path))

    assert [call.args[0][:-1] for call in run.call_args_list] == [['umount'], ['umount', '-l']]
    assert (orphan / 'mntpoint' / 'share_file').exists()


def test_mount_is_unmounted_before_deleting(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dead_pid: int) -> None:
    """An orphan's mount is unmounted, then the directory is deleted."""
    orphan = tmp_path / f'openvdm-{dead_pid}-ok'
    (orphan / 'mntpoint').mkdir(parents=True)
    mounted = {'yes': True}
    monkeypatch.setattr(file_utils.os.path, 'ismount',
                        lambda path: path.endswith('mntpoint') and mounted['yes'])

    def umount(cmd, **_kwargs):
        mounted['yes'] = False
        return Mock(returncode=0, stderr='')
    monkeypatch.setattr(file_utils.subprocess, 'run', umount)

    file_utils.cleanup_orphaned_temporary_directories(str(tmp_path))

    assert not orphan.exists()


def test_a_directory_another_process_is_cleaning_is_skipped(tmp_path: Path, dead_pid: int) -> None:
    """A directory locked by another cleanup is left to it (#490)."""
    orphan = tmp_path / f'openvdm-{dead_pid}-abc123'
    orphan.mkdir()
    other_cleanup = os.open(orphan, os.O_RDONLY)
    try:
        fcntl.flock(other_cleanup, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert file_utils.cleanup_orphaned_temporary_directories(str(tmp_path)) == []
        assert orphan.exists()
    finally:
        os.close(other_cleanup)

    assert file_utils.cleanup_orphaned_temporary_directories(str(tmp_path)) == [str(orphan)]
    assert not orphan.exists()


def test_cleanups_running_at_once_clean_each_directory_once(tmp_path: Path, dead_pid: int) -> None:
    """reboot_reset and the workers starting together don't clean a directory twice (#490)."""
    orphans = set()
    for i in range(30):
        orphan = tmp_path / f'openvdm-{dead_pid}-dir{i:02d}'
        (orphan / 'mntpoint').mkdir(parents=True)
        (orphan / 'files.txt').write_text('x')
        orphans.add(str(orphan))

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: file_utils.cleanup_orphaned_temporary_directories(str(tmp_path)),
                                range(6)))

    cleaned = [path for result in results for path in result]
    assert sorted(cleaned) == sorted(orphans)    # each once, none missed
    assert not any(os.path.exists(path) for path in orphans)


def test_start_orphan_cleanup_runs_in_the_background(monkeypatch) -> None:
    """Workers start the cleanup in a daemon thread, so a hung umount can't block them (#490)."""
    ran = threading.Event()
    monkeypatch.setattr(file_utils, 'cleanup_orphaned_temporary_directories', lambda: ran.set())

    thread = file_utils.start_orphan_cleanup()
    thread.join(5)
    assert thread.daemon and ran.is_set()


def test_start_orphan_cleanup_logs_a_failure(monkeypatch, caplog) -> None:
    """An error in the cleanup is logged, not raised in the worker."""
    def fail():
        raise OSError('boom')

    monkeypatch.setattr(file_utils, 'cleanup_orphaned_temporary_directories', fail)
    file_utils.start_orphan_cleanup().join(5)
    assert 'Cleaning up orphaned temporary directories failed' in caplog.text
