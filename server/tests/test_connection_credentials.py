"""Tests for connection_utils' logins: SMB, rsync and SSH tests, rclone configs (#508).

Passwords must reach the commands in files or on stdin, never on the command
line, where ``ps`` and a failed command's error text would show them (#424,
#426). Each test checks both.
"""

import configparser
import logging
import os
import stat
import subprocess
from pathlib import Path

import pytest

from server.lib import connection_utils as cu

SECRET = 's3cr3t,pass'


# --- Temporary secret files ---------------------------------------------------

def test_secret_files_are_private_and_deleted() -> None:
    """The SMB credentials and SSH password files are owner-only and gone afterwards."""
    with cu.smb_credentials_file({'smbUser': 'survey', 'smbPass': SECRET}) as smb_path:
        assert Path(smb_path).read_text(encoding='utf-8') == f'username=survey\npassword={SECRET}\n'
        assert stat.S_IMODE(os.stat(smb_path).st_mode) == 0o600
    with cu.ssh_password_file(SECRET) as ssh_path:
        assert Path(ssh_path).read_text(encoding='utf-8') == f'{SECRET}\n'
        assert stat.S_IMODE(os.stat(ssh_path).st_mode) == 0o600
    assert not os.path.exists(smb_path) and not os.path.exists(ssh_path)


def test_secret_file_is_deleted_when_the_block_fails() -> None:
    """The file is deleted even if the command using it fails."""
    with pytest.raises(RuntimeError):
        with cu.ssh_password_file(None) as path:
            assert Path(path).read_text(encoding='utf-8') == '\n', "None is an empty password"
            raise RuntimeError
    assert not os.path.exists(path)


def test_sshpass_command() -> None:
    """A password login is prefixed with sshpass -f; a key login is unchanged."""
    with cu.sshpass_command(['ssh', 'u@h'], {'sshUseKey': '1'}) as cmd:
        assert cmd == ['ssh', 'u@h']
    with cu.sshpass_command(['ssh', 'u@h'], {'sshUseKey': '0', 'sshPass': SECRET}) as cmd:
        assert cmd[:2] == ['sshpass', '-f'] and cmd[3:] == ['ssh', 'u@h']
        assert Path(cmd[2]).read_text(encoding='utf-8') == f'{SECRET}\n'


# --- SMB ----------------------------------------------------------------------

SMB_CFG = {'smbServer': '//nas/share', 'smbDomain': 'WORKGROUP', 'smbUser': 'survey', 'smbPass': SECRET}


def test_detect_smb_version_logs_in_with_a_credentials_file(fake_run) -> None:
    """smbclient -A reads the login from a file (#424)."""
    fake_run.on('smbclient', stdout='Disk|share|\n')

    assert cu.detect_smb_version(SMB_CFG) == ('2.1', '')

    call = fake_run.calls[0]
    credentials = call.cmd[call.cmd.index('-A') + 1]
    assert call.files[credentials] == f'username=survey\npassword={SECRET}\n'
    fake_run.assert_not_in_commands(SECRET)


def test_detect_smb_version_guest_and_windows_xp(fake_run) -> None:
    """A guest lists with -N; a Windows XP server gets SMB 1.0."""
    fake_run.on('smbclient', stdout='OS=[Windows 5.1] Server=[Windows 2000 LAN Manager]\n')
    assert cu.detect_smb_version({**SMB_CFG, 'smbUser': 'guest'}) == ('1.0', '')
    assert '-N' in fake_run.calls[0].cmd and '-A' not in fake_run.calls[0].cmd


@pytest.mark.parametrize('returncode, stderr', [
    (1, 'Connection to nas failed'),
    (0, 'session setup failed: NT_STATUS_LOGON_FAILURE'),
])
def test_detect_smb_version_failure(fake_run, returncode, stderr) -> None:
    """A failed listing, or an NT_STATUS error, returns smbclient's error."""
    fake_run.on('smbclient', returncode=returncode, stderr=stderr + '\n')
    assert cu.detect_smb_version(SMB_CFG) == (None, stderr)


def test_detect_smb_version_timeout(fake_run) -> None:
    """An unreachable server times out instead of hanging."""
    fake_run.on('smbclient', raises=subprocess.TimeoutExpired('smbclient', 10))
    version, detail = cu.detect_smb_version(SMB_CFG)
    assert version is None and 'timed out' in detail


@pytest.mark.parametrize('remove, mode', [('1', 'rw'), ('0', 'ro')])
def test_mount_smb_share(fake_run, remove, mode) -> None:
    """Read-write only when source files are removed; the login is in credentials=."""
    assert cu.mount_smb_share({**SMB_CFG, 'removeSourceFiles': remove}, '/tmp/mnt', '2.1') == (True, '')

    call = fake_run.calls[0]
    assert call.cmd[:6] == ['mount', '-t', 'cifs', '//nas/share', '/tmp/mnt', '-o']
    options = call.cmd[6].split(',')
    assert options[:3] == [mode, 'domain=WORKGROUP', 'vers=2.1']
    credentials = options[3].removeprefix('credentials=')
    assert call.files[credentials].endswith(f'password={SECRET}\n')
    fake_run.assert_not_in_commands(SECRET)


def test_mount_smb_share_guest(fake_run) -> None:
    """A guest mount has no credentials file."""
    cu.mount_smb_share({**SMB_CFG, 'smbUser': 'guest'}, '/tmp/mnt', '1.0')
    assert fake_run.calls[0].cmd[-1] == 'rw,domain=WORKGROUP,vers=1.0,guest'


def test_mount_smb_share_failure_unmounts(fake_run) -> None:
    """A failed mount reports mount's error and unmounts any partial mount."""
    fake_run.on('mount', returncode=32, stderr='mount error(13): Permission denied\n')

    assert cu.mount_smb_share(SMB_CFG, '/tmp/mnt', '2.1') == (False, 'mount error(13): Permission denied')
    assert fake_run.commands('umount') == [['umount', '/tmp/mnt']]


def test_mount_smb_share_without_mount_command(fake_run) -> None:
    """A missing mount command is reported, not raised."""
    fake_run.on('mount', raises=FileNotFoundError('mount'))
    success, detail = cu.mount_smb_share(SMB_CFG, '/tmp/mnt', '2.1')
    assert not success and 'mount' in detail


# --- rsync --------------------------------------------------------------------

@pytest.mark.parametrize('returncode, expected', [(0, (True, '')), (24, (True, '')),
                                                  (5, (False, '@ERROR: auth failed'))])
def test_rsync_connection(fake_run, returncode, expected) -> None:
    """Exit 24 (vanished files) is still a connection; others fail with rsync's error."""
    fake_run.on('rsync', returncode=returncode, stderr='@ERROR: auth failed\n')
    assert cu.test_rsync_connection('host/module', 'survey', '/tmp/pw') == expected
    assert fake_run.calls[0].cmd == ['rsync', '--no-motd', '--contimeout=5', '--password-file=/tmp/pw',
                                     'rsync://survey@host/module']


def test_rsync_connection_without_rsync(fake_run) -> None:
    """A missing rsync fails the test; anonymous logins have no password file."""
    fake_run.on('rsync', raises=FileNotFoundError('rsync'))
    assert cu.test_rsync_connection('host', 'anonymous')[0] is False
    assert not any(arg.startswith('--password-file') for arg in fake_run.calls[0].cmd)


def test_rsync_write_access_uploads_then_deletes(fake_run, tmp_path) -> None:
    """The test file is uploaded, then deleted by syncing an empty directory (#233)."""
    assert cu.test_rsync_write_access('host/module/', 'survey', str(tmp_path), '/tmp/pw') == (True, '')

    upload, cleanup = fake_run.commands('rsync')
    assert upload[-2:] == [str(tmp_path / 'write_test' / 'write_test.txt'), 'rsync://survey@host/module/']
    assert '--remove-source-files' in upload
    assert cleanup[-2:] == [f'{tmp_path / "write_test_empty"}/', 'rsync://survey@host/module/']
    assert {'--dirs', '--delete', '--include=/write_test.txt', '--exclude=*'} <= set(cleanup)


def test_rsync_write_access_failed_upload(fake_run, tmp_path) -> None:
    """A failed upload fails the test without trying the cleanup."""
    fake_run.on('rsync', returncode=23, stderr='Permission denied\n')
    assert cu.test_rsync_write_access('host/module', 'survey', str(tmp_path)) == (False, 'Permission denied')
    assert len(fake_run.calls) == 1


def test_rsync_write_access_failed_cleanup_still_passes(fake_run, tmp_path, caplog) -> None:
    """The write worked, so a failed delete is only a warning."""
    def fail_cleanup(cmd, kwargs):
        if '--delete' in cmd:
            raise OSError('connection reset')

    fake_run.on('rsync', effect=fail_cleanup)
    with caplog.at_level(logging.WARNING):
        assert cu.test_rsync_write_access('host/module', 'survey', str(tmp_path)) == (True, '')
    assert 'Could not delete write_test.txt' in caplog.text


# --- SSH ----------------------------------------------------------------------

def test_ssh_connection_with_password(fake_run) -> None:
    """sshpass reads the password from a file (#426)."""
    assert cu.test_ssh_connection('host', 'survey', SECRET, False) == (True, '')

    call = fake_run.calls[0]
    assert call.cmd[:2] == ['sshpass', '-f'] and call.cmd[-2:] == ['survey@host', 'ls']
    assert call.files[call.cmd[2]] == f'{SECRET}\n'
    fake_run.assert_not_in_commands(SECRET)


def test_ssh_connection_with_key(fake_run) -> None:
    """A key login runs ssh directly, in batch mode."""
    cu.test_ssh_connection('host', 'survey', None, True)
    assert fake_run.calls[0].cmd[0] == 'ssh' and 'BatchMode=yes' in fake_run.calls[0].cmd


def test_ssh_connection_failure(fake_run) -> None:
    """A failed login returns ssh's error."""
    fake_run.on('sshpass', returncode=5, stderr='Permission denied, please try again.\n')
    assert cu.test_ssh_connection('host', 'survey', SECRET, False) == (
        False, 'Permission denied, please try again.')


def test_ssh_connection_without_sshpass(fake_run) -> None:
    """A missing sshpass fails the test."""
    fake_run.on('sshpass', raises=FileNotFoundError('sshpass'))
    assert cu.test_ssh_connection('host', 'survey', SECRET, False)[0] is False


def test_ssh_test_needs_a_password_or_key() -> None:
    """Without a password or key there is no way to log in."""
    with pytest.raises(ValueError):
        cu.test_ssh_connection('host', 'survey', None, False)


def test_ssh_remote_directory(fake_run) -> None:
    """The directory is quoted, so a space in it works."""
    cu.test_ssh_remote_directory('host', 'survey', '/data/my dir', None, True)
    assert fake_run.calls[0].cmd[-1] == 'ls "/data/my dir"'


def test_ssh_write_access(fake_run) -> None:
    """Touch then remove a test file; a failed touch stops there."""
    assert cu.test_ssh_write_access('host', 'survey', '/backup', None, True) == (True, '')
    assert [cmd[-1] for cmd in fake_run.commands()] == ['touch /backup/writeTest.txt',
                                                         'rm /backup/writeTest.txt']

    fake_run.calls.clear()
    fake_run.on('ssh', returncode=1, stderr='touch: Permission denied\n')
    assert cu.test_ssh_write_access('host', 'survey', '/backup', None, True) == (
        False, 'touch: Permission denied')
    assert len(fake_run.calls) == 1


@pytest.mark.parametrize('stdout, expected', [('Darwin\n', True), ('Linux\n', False), ('', False)])
def test_check_darwin(fake_run, stdout, expected) -> None:
    """Only a server reporting Darwin is macOS; the password stays off the command line."""
    fake_run.on('sshpass', stdout=stdout)
    assert cu.check_darwin({'sshServer': 'host', 'sshUser': 'survey', 'sshUseKey': '0',
                            'sshPass': SECRET}) is expected
    fake_run.assert_not_in_commands(SECRET)


def test_check_darwin_on_ssh_failure(fake_run) -> None:
    """A failed SSH command counts as not macOS."""
    fake_run.on('ssh', raises=subprocess.TimeoutExpired('ssh', 10))
    assert cu.check_darwin({'sshServer': 'host', 'sshUser': 'survey', 'sshUseKey': '1'}) is False


# --- rclone configs -----------------------------------------------------------

def _config(path) -> configparser.ConfigParser:
    """Read an rclone config file."""
    config = configparser.ConfigParser()
    config.read(path)
    return config


def test_rclone_config_for_ssh_with_password(fake_run, tmp_path, caplog) -> None:
    """The password is obscured via stdin (#424) and masked in debug logs (#430)."""
    fake_run.on('rclone', 'obscure', stdout='OBSCURED\n')
    path = tmp_path / 'rclone.conf'
    with caplog.at_level(logging.DEBUG):
        remote = cu.build_rclone_config_for_ssh({'sshServer': 'ship.local', 'sshUser': 'survey',
                                                 'sshUseKey': '0', 'sshPass': SECRET}, str(path))

    assert remote == 'ship_local'
    assert dict(_config(path)['ship_local']) == {'type': 'sftp', 'host': 'ship.local', 'user': 'survey',
                                                 'pass': 'OBSCURED'}
    assert fake_run.calls[0].cmd == ['rclone', 'obscure', '-'] and fake_run.calls[0].kwargs['input'] == SECRET
    assert 'OBSCURED' not in caplog.text and 'pass = ****' in caplog.text


def test_rclone_config_for_ssh_with_key(monkeypatch, tmp_path) -> None:
    """A key login uses the key ssh would use for the host."""
    monkeypatch.setattr(cu, 'ssh_identity_file', lambda host, user: '/home/u/.ssh/id_ed25519')
    path = tmp_path / 'rclone.conf'
    cu.build_rclone_config_for_ssh({'sshServer': 'h', 'sshUser': 'u', 'sshUseKey': '1'}, str(path))
    assert _config(path)['h']['key_file'] == '/home/u/.ssh/id_ed25519'


def test_rclone_config_for_ssh_without_a_key(monkeypatch, tmp_path) -> None:
    """A key login with no key fails with what's missing."""
    monkeypatch.setattr(cu, 'ssh_identity_file', lambda host, user: None)
    with pytest.raises(FileNotFoundError):
        cu.build_rclone_config_for_ssh({'sshServer': 'h', 'sshUser': 'u', 'sshUseKey': '1'},
                                       str(tmp_path / 'rclone.conf'))


def test_rclone_config_for_ssh_obscure_failure(fake_run, tmp_path) -> None:
    """A failed rclone obscure is raised to the caller."""
    fake_run.on('rclone', 'obscure', returncode=1)
    with pytest.raises(subprocess.CalledProcessError):
        cu.build_rclone_config_for_ssh({'sshServer': 'h', 'sshUser': 'u', 'sshUseKey': '0', 'sshPass': 'x'},
                                       str(tmp_path / 'rclone.conf'))


@pytest.mark.parametrize('cfg, section', [
    ({'ftpServer': 'ftp.example.org:2121', 'ftpUser': 'survey', 'ftpPass': SECRET},
     {'type': 'ftp', 'host': 'ftp.example.org', 'port': '2121', 'user': 'survey', 'pass': 'OBSCURED'}),
    ({'ftpServer': '[fe80::1]', 'ftpUser': 'anonymous', 'ftpPass': ''},
     {'type': 'ftp', 'host': '[fe80::1]', 'port': '21', 'user': 'anonymous', 'pass': 'OBSCURED'}),
    ({'ftpServer': 'h', 'ftpUser': 'survey', 'ftpPass': ''},
     {'type': 'ftp', 'host': 'h', 'port': '21', 'user': 'survey'}),
])
def test_rclone_config_for_ftp(fake_run, tmp_path, cfg, section) -> None:
    """Port and IPv6 brackets; anonymous gets the password 'anonymous'; the file is private."""
    fake_run.on('rclone', 'obscure', stdout='OBSCURED\n')
    path = tmp_path / 'rclone.conf'

    assert cu.build_rclone_config_for_ftp(cfg, str(path)) == cu.FTP_REMOTE
    assert dict(_config(path)[cu.FTP_REMOTE]) == section
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    if 'pass' in section:
        assert fake_run.calls[0].kwargs['input'] == (cfg['ftpPass'] or 'anonymous')
    fake_run.assert_not_in_commands(SECRET)


def test_rclone_config_for_ftp_bad_port(tmp_path) -> None:
    """An invalid port in the FTP Server field is raised to the caller."""
    with pytest.raises(ValueError):
        cu.build_rclone_config_for_ftp({'ftpServer': 'h:99999', 'ftpUser': 'a'}, str(tmp_path / 'c'))


def test_rsync_write_access_upload_error(fake_run, tmp_path) -> None:
    """An upload that raises fails the test."""
    fake_run.on('rsync', raises=OSError('rsync: not found'))
    assert cu.test_rsync_write_access('host/m', 'survey', str(tmp_path)) == (False, 'rsync: not found')


def test_rsync_write_access_cleanup_exit_status(fake_run, tmp_path, caplog) -> None:
    """A cleanup that exits non-zero is also only a warning."""
    fake_run.on('rsync', '--no-motd', '--contimeout=5', '--dirs', returncode=23, stderr='denied')
    with caplog.at_level(logging.WARNING):
        assert cu.test_rsync_write_access('host/m', 'survey', str(tmp_path)) == (True, '')
    assert 'Could not delete write_test.txt' in caplog.text and 'denied' in caplog.text


def test_get_rclone_remote_type_default_config(tmp_path, monkeypatch) -> None:
    """Without a path, rclone's own config file in the home directory."""
    monkeypatch.setenv('HOME', str(tmp_path))
    config = tmp_path / '.config' / 'rclone' / 'rclone.conf'
    config.parent.mkdir(parents=True)
    config.write_text('[s3remote]\ntype = s3\n')
    assert cu.get_rclone_remote_type('s3remote') == 's3'
