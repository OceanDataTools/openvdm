"""Tests for cleaning up temporary directories left by killed workers."""

import os
import subprocess
import sys
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
