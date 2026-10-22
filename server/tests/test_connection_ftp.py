"""Tests for connection_utils' FTP helpers: listing, write test, mount, setup (#508)."""

import json
import os
import subprocess

import pytest

from server.lib import connection_utils as cu

CONFIG = '/tmp/rclone.conf'


def test_ftp_connection_lists_the_given_directory(fake_run) -> None:
    """The directory the transfer uses, not /, which some accounts can't list (#209)."""
    assert cu.test_ftp_connection(CONFIG, 'ftp_source', '/data') == (True, '')
    cmd = fake_run.calls[0].cmd
    assert cmd[:3] == ['rclone', 'lsf', 'ftp_source:/data'] and cmd[3:5] == ['--config', CONFIG]
    assert set(cu.RCLONE_TEST_FLAGS) <= set(cmd)


def test_ftp_connection_failure(fake_run) -> None:
    """A failed login returns rclone's error without the remote name."""
    fake_run.on('rclone', returncode=1, stderr=(
        '2026/10/22 10:00:00 Failed to create file system for "ftp_source:/data": NewFs: 530 Login incorrect.'))
    assert cu.test_ftp_connection(CONFIG, 'ftp_source', '/data') == (False, '530 Login incorrect.')


def test_ftp_connection_without_rclone(fake_run) -> None:
    """A missing rclone is reported."""
    fake_run.on('rclone', raises=FileNotFoundError('rclone'))
    assert cu.test_ftp_connection(CONFIG, 'ftp_source') == (False, 'rclone is not installed')


def test_list_ftp_source(fake_run) -> None:
    """One lsjson -R: paths relative to the source, sizes and epoch times (#208); excludes (#265)."""
    fake_run.on('rclone', 'lsjson', stdout=json.dumps([
        {'Path': 'a.txt', 'Size': 10, 'ModTime': '2019-08-11T19:03:35Z'},
        {'Path': 'sub/b.raw', 'Size': '2048', 'ModTime': '2019-08-11T19:03:36.5Z'},
    ]))

    success, files = cu.list_ftp_source(CONFIG, 'ftp_source', '/data', ['*.tmp', 'old/**'])

    assert success
    assert [(path, size) for path, size, _ in files] == [('a.txt', 10), ('sub/b.raw', 2048)]
    assert files[1][2] - files[0][2] == pytest.approx(1.5)
    cmd = fake_run.calls[0].cmd
    assert 'ftp_source:/data' in cmd and {'-R', '--files-only'} <= set(cmd)
    assert cmd[-2:] == ['--exclude=*.tmp', '--exclude=old/**']


def test_list_ftp_source_refused_directory_fails(fake_run) -> None:
    """A directory the server won't list fails the listing instead of looking empty (#208)."""
    fake_run.on('rclone', 'lsjson', returncode=3, stderr='2026/10/22 10:00:00 ERROR : sub: error listing: 550 Permission denied\n')
    assert cu.list_ftp_source(CONFIG, 'ftp_source', '/data') == (False, 'sub: error listing: 550 Permission denied')


@pytest.mark.parametrize('stdout', ['not json', json.dumps([{'Path': 'a'}]),
                                    json.dumps([{'Path': 'a', 'Size': 1, 'ModTime': 'yesterday'}])])
def test_list_ftp_source_unreadable_output(fake_run, stdout) -> None:
    """Output that is not JSON, or lacks a field, fails the listing."""
    fake_run.on('rclone', 'lsjson', stdout=stdout)
    success, detail = cu.list_ftp_source(CONFIG, 'ftp_source', '/data')
    assert not success and detail.startswith('Unreadable rclone lsjson output')


def test_list_ftp_source_without_rclone(fake_run) -> None:
    """A missing rclone is reported."""
    fake_run.on('rclone', raises=FileNotFoundError('rclone'))
    assert cu.list_ftp_source(CONFIG, 'ftp_source', '/') == (False, 'rclone is not installed')


def test_ftp_write_access(fake_run) -> None:
    """Upload then delete a uniquely named file; the local temporary file is removed."""
    assert cu.test_ftp_write_access(CONFIG, 'ftp_source', '/backup/') == (True, '')

    upload, delete = fake_run.commands()
    assert upload[:2] == ['rclone', 'copyto'] and delete[:2] == ['rclone', 'deletefile']
    remote_file = upload[3]
    assert remote_file.startswith('ftp_source:/backup/.openvdm-write-test-') and delete[2] == remote_file
    assert not os.path.exists(upload[2])


def test_ftp_write_access_failure(fake_run) -> None:
    """A failed upload fails the test without trying the delete."""
    fake_run.on('rclone', 'copyto', returncode=1, stderr='553 Could not create file.')
    assert cu.test_ftp_write_access(CONFIG, 'ftp_source', '/backup') == (False, '553 Could not create file.')
    assert len(fake_run.calls) == 1


# --- rclone mount -------------------------------------------------------------

FTP_CFG = {'ftpServer': 'ftp.example.org', 'ftpUser': 'survey', 'ftpPass': 'x', 'removeSourceFiles': '0'}


@pytest.fixture
def mount_env(tmp_path, monkeypatch):
    """A temporary directory for the config and mount point; a fast clock for the wait."""
    clock = {'now': 0.0}
    monkeypatch.setattr(cu.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(cu.time, 'sleep', lambda seconds: clock.__setitem__('now', clock['now'] + seconds))
    mntpoint = tmp_path / 'mntpoint'
    mntpoint.mkdir()
    return tmp_path, str(mntpoint), str(tmp_path / 'rclone.conf')


@pytest.mark.parametrize('remove, read_only', [('0', True), ('1', False)])
def test_mount_ftp_source(fake_run, mount_env, monkeypatch, remove, read_only) -> None:
    """Mounts the base directory, read-only unless source files are removed."""
    _, mntpoint, config = mount_env
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: path == mntpoint)

    assert cu.mount_ftp_source({**FTP_CFG, 'removeSourceFiles': remove}, mntpoint, config, '/data') == (True, '')

    call = fake_run.calls[0]
    assert call.cmd[:4] == ['rclone', 'mount', 'ftp_source:/data', mntpoint] and '--daemon' in call.cmd
    assert ('--read-only' in call.cmd) is read_only
    # The daemon keeps its output open: it goes to the log file, not a pipe
    assert call.kwargs['stdout'] is call.kwargs['stderr'] and call.kwargs['stdout'] is not subprocess.PIPE


def test_mount_ftp_source_waits_for_the_mount(fake_run, mount_env, monkeypatch) -> None:
    """Older rclone returns before the mount is ready; success waits for it (#206)."""
    _, mntpoint, config = mount_env
    checks = iter([False, False, True])
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: next(checks))
    assert cu.mount_ftp_source(FTP_CFG, mntpoint, config) == (True, '')


def test_mount_ftp_source_failure_reports_the_log(fake_run, mount_env) -> None:
    """A failed mount reports rclone's log and unmounts."""
    def write_log(cmd, kwargs):
        kwargs['stdout'].write('2026/10/22 10:00:00 Fatal error: fusermount: not found\n')

    _, mntpoint, config = mount_env
    fake_run.on('rclone', 'mount', returncode=1, effect=write_log)

    assert cu.mount_ftp_source(FTP_CFG, mntpoint, config) == (False, 'Fatal error: fusermount: not found')
    assert fake_run.commands('umount') == [['umount', mntpoint]]


def test_mount_ftp_source_timeout_stops_rclone(fake_run, mount_env, monkeypatch) -> None:
    """A mount that never appears is unmounted and its rclone killed, so it can't mount later."""
    _, mntpoint, config = mount_env
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: False)

    success, detail = cu.mount_ftp_source(FTP_CFG, mntpoint, config, '/data/x*')

    assert not success and detail == f'not mounted after {cu.FTP_MOUNT_TIMEOUT} s'
    assert fake_run.commands('umount') == [['umount', mntpoint]]
    (pkill,) = fake_run.commands('pkill')
    assert pkill[:2] == ['pkill', '-f'] and pkill[2] == cu.ere_escape(
        f'rclone mount ftp_source:/data/x* {mntpoint}')


def test_mount_ftp_source_without_rclone(fake_run, mount_env) -> None:
    """A missing rclone is reported."""
    _, mntpoint, config = mount_env
    fake_run.on('rclone', raises=FileNotFoundError('rclone'))
    assert cu.mount_ftp_source(FTP_CFG, mntpoint, config) == (False, 'rclone is not installed')


# --- Setup steps shared by Test Setup and the transfer (#214) ------------------

def test_prepare_ftp_config(fake_run, tmp_path) -> None:
    """The rclone config is written to the temporary directory."""
    fake_run.on('rclone', 'obscure', stdout='OBSCURED\n')
    assert cu.prepare_ftp_config(FTP_CFG, str(tmp_path)) == (True, str(tmp_path / 'rclone.conf'))
    assert (tmp_path / 'rclone.conf').is_file()


@pytest.mark.parametrize('cfg, expected', [
    ({'ftpServer': 'h', 'ftpUser': 'survey', 'ftpPass': None}, cu.FTP_PASS_MISSING),
    ({'ftpServer': 'h:0', 'ftpUser': 'survey', 'ftpPass': 'x'}, 'Invalid FTP port in h:0: must be a number '
                                                                'from 1 to 65535'),
])
def test_prepare_ftp_config_failures(fake_run, tmp_path, cfg, expected) -> None:
    """No password from the web app (worker token), or a bad port."""
    assert cu.prepare_ftp_config(cfg, str(tmp_path)) == (False, expected)


def test_prepare_ftp_config_anonymous_needs_no_password(fake_run, tmp_path) -> None:
    """Anonymous logins need no password from the web app."""
    assert cu.prepare_ftp_config({'ftpServer': 'h', 'ftpUser': 'anonymous', 'ftpPass': None},
                                 str(tmp_path))[0] is True


@pytest.mark.parametrize('raises, expected', [
    (FileNotFoundError('rclone'), 'rclone is not installed'),
    (subprocess.CalledProcessError(1, 'rclone'), 'Unable to write rclone config: '),
])
def test_prepare_ftp_config_rclone_problems(fake_run, tmp_path, raises, expected) -> None:
    """A missing rclone, or a failed rclone obscure, is reported."""
    fake_run.on('rclone', raises=raises)
    success, detail = cu.prepare_ftp_config(FTP_CFG, str(tmp_path))
    assert not success and detail.startswith(expected)


def test_prepare_ftp_mount(monkeypatch, tmp_path) -> None:
    """Mounts at <tmpdir>/mntpoint, which temporary_directory() unmounts."""
    calls = []
    monkeypatch.setattr(cu, 'mount_ftp_source', lambda *args: calls.append(args) or (True, ''))
    assert cu.prepare_ftp_mount(FTP_CFG, str(tmp_path), 'cfg', '/data') == (True, str(tmp_path / 'mntpoint'))
    assert (tmp_path / 'mntpoint').is_dir() and calls[0][1:] == (str(tmp_path / 'mntpoint'), 'cfg', '/data')

    monkeypatch.setattr(cu, 'mount_ftp_source', lambda *args: (False, 'no fuse'))
    assert cu.prepare_ftp_mount(FTP_CFG, str(tmp_path), 'cfg', '/data') == (False, 'no fuse')


def test_ftp_write_access_without_rclone(fake_run) -> None:
    """A missing rclone is reported."""
    fake_run.on('rclone', raises=FileNotFoundError('rclone'))
    assert cu.test_ftp_write_access(CONFIG, 'ftp_source', '/b') == (False, 'rclone is not installed')
