"""Tests for connection_utils' Test Setup checks of sources and destinations (#508).

``test_cst_source()``, ``test_cdt_destination()`` and
``test_cdt_rclone_destination()`` return the parts Test Setup shows. The
connection steps they call have their own tests, so here they're replaced to
drive each branch; local directories and mount points are real temporary
directories.
"""

import os
from pathlib import Path

import pytest

from server.lib import connection_utils as cu


def parts(results: list) -> list:
    """Each part as ``(partName, result)``."""
    return [(part['partName'], part['result']) for part in results]


def reasons(results: list) -> list:
    """Each part's reason, or '' for a pass."""
    return [part.get('reason', '') for part in results]


def _replace(monkeypatch, **functions):
    """Replace connection_utils functions for one test."""
    for name, function in functions.items():
        monkeypatch.setattr(cu, name, function)


def _cst(transfer_type, **overrides) -> dict:
    """A transfer config of the given type, with credentials for every type."""
    cfg = {'transferType': str(transfer_type), 'localDirIsMountPoint': '0', 'removeSourceFiles': '0',
           'smbServer': '//nas/share', 'smbDomain': 'WG', 'smbUser': 'survey', 'smbPass': 'x',
           'rsyncServer': 'host/module', 'rsyncUser': 'survey', 'rsyncPass': 'x',
           'sshServer': 'host', 'sshUser': 'survey', 'sshUseKey': '0', 'sshPass': 'x',
           'ftpServer': 'ftp.example.org', 'ftpUser': 'survey', 'ftpPass': 'x'}
    cfg.update(overrides)
    return cfg


def test_unknown_transfer_type() -> None:
    """An unknown transfer type fails before anything is checked."""
    assert parts(cu.test_cst_source(_cst(9), '/x')) == [('Transfer type', 'Fail')]
    assert parts(cu.test_cdt_destination(_cst(9, destDir='/x'))) == [('Transfer type', 'Fail')]


# --- Local collection system sources ------------------------------------------

def test_local_source(tmp_path) -> None:
    """An existing, writable directory passes."""
    assert parts(cu.test_cst_source(_cst(1, removeSourceFiles='1'), str(tmp_path))) == [
        ('Source directory', 'Pass'), ('Write test', 'Pass')]


def test_local_source_missing(tmp_path) -> None:
    """A missing directory fails every check that was asked for."""
    results = cu.test_cst_source(_cst(1, localDirIsMountPoint='1', removeSourceFiles='1'), str(tmp_path / 'no'))
    assert parts(results) == [('Source directory', 'Fail'), ('Source directory is a mount point', 'Fail'),
                              ('Write test', 'Fail')]
    assert 'Unable to find source directory' in reasons(results)[0]


def test_local_source_not_a_mount_point(tmp_path, monkeypatch) -> None:
    """A source marked as a mount point that isn't one fails."""
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: False)
    assert parts(cu.test_cst_source(_cst(1, localDirIsMountPoint='1'), str(tmp_path))) == [
        ('Source directory', 'Pass'), ('Source directory is a mount point', 'Fail')]


def test_local_source_mount_point_checks_the_top_two_components(tmp_path, monkeypatch) -> None:
    """e.g. /mnt/usb for /mnt/usb/data."""
    top_two = os.sep + os.path.join(*str(tmp_path).strip(os.sep).split(os.sep)[:2])
    real_ismount = os.path.ismount
    # Only the checked path counts as mounted: temporary_directory()'s cleanup
    # leaves its directory in place if it thinks its mntpoint is mounted
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: path == top_two or real_ismount(path))
    assert parts(cu.test_cst_source(_cst(1, localDirIsMountPoint='1'), str(tmp_path)))[-1] == (
        'Source directory is a mount point', 'Pass')


def test_local_source_not_writable(tmp_path, monkeypatch) -> None:
    """Removing source files needs write access."""
    monkeypatch.setattr(cu, 'test_write_access', lambda path: False)
    results = cu.test_cst_source(_cst(1, removeSourceFiles='1'), str(tmp_path))
    assert parts(results) == [('Source directory', 'Pass'), ('Write test', 'Fail')]
    assert 'Unable to delete source files' in reasons(results)[1]


def test_local_wildcard_source(tmp_path) -> None:
    """A wildcard source passes when its parent exists and a directory matches."""
    (tmp_path / 'xbt_01').mkdir()
    (tmp_path / 'xbt_file').write_text('not a directory')
    assert parts(cu.test_cst_source(_cst(1, removeSourceFiles='1'), str(tmp_path / 'xbt_*'))) == [
        ('Source directory', 'Pass'), ('Write test', 'Pass')]


@pytest.mark.parametrize('source, reason', [
    ('missing/xbt_*', 'Unable to find parent directory'),
    ('xbt_*', 'No directories matching wildcard pattern'),
])
def test_local_wildcard_source_failures(tmp_path, source, reason) -> None:
    """A missing parent, or no matching directory (files don't count)."""
    (tmp_path / 'xbt_file').write_text('files don\'t count')
    results = cu.test_cst_source(_cst(1, removeSourceFiles='1'), str(tmp_path / source))
    assert parts(results) == [('Source directory', 'Fail'), ('Write test', 'Fail')]
    assert reason in reasons(results)[0]


# --- SMB, rsync, SSH and FTP collection system sources ------------------------

def _mount_with(*dirs):
    """A mount_smb_share() that "mounts" by creating directories in the mount point."""
    def mount(cfg, mntpoint, version):
        for directory in dirs:
            os.makedirs(os.path.join(mntpoint, directory))
        return True, ''
    return mount


def test_smb_source(monkeypatch) -> None:
    """Server, share, source directory and write test all pass."""
    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''), mount_smb_share=_mount_with('data'))
    assert parts(cu.test_cst_source(_cst(3, removeSourceFiles='1'), '/data')) == [
        ('SMB server', 'Pass'), ('SMB share', 'Pass'), ('Source directory', 'Pass'), ('Write test', 'Pass')]


def test_smb_source_without_a_password(monkeypatch) -> None:
    """No password from the web app (worker token): fail before connecting."""
    monkeypatch.setattr(cu, 'detect_smb_version', lambda cfg: pytest.fail('connected'))
    results = cu.test_cst_source(_cst(3, smbPass=None), '/data')
    assert parts(results) == [('SMB server', 'Fail'), ('SMB share', 'Fail'), ('Source directory', 'Fail')]
    assert 'smbPass not available' in reasons(results)[0]


def test_smb_source_unreachable(monkeypatch) -> None:
    """An unreachable server fails with smbclient's error."""
    monkeypatch.setattr(cu, 'detect_smb_version', lambda cfg: (None, 'NT_STATUS_LOGON_FAILURE'))
    results = cu.test_cst_source(_cst(3, removeSourceFiles='1'), '/data')
    assert parts(results) == [('SMB server', 'Fail'), ('SMB share', 'Fail'), ('Source directory', 'Fail'),
                              ('Write test', 'Fail')]
    assert reasons(results)[0] == 'Could not connect to SMB server: //nas/share as survey — NT_STATUS_LOGON_FAILURE'


def test_smb_source_mount_fails(monkeypatch) -> None:
    """The server answered, but the share would not mount."""
    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''),
             mount_smb_share=lambda cfg, mnt, version: (False, 'mount error(13)'))
    assert parts(cu.test_cst_source(_cst(3), '/data')) == [
        ('SMB server', 'Pass'), ('SMB share', 'Fail'), ('Source directory', 'Fail')]


def test_smb_source_directory_missing(monkeypatch) -> None:
    """The share mounted, but the source directory is not on it."""
    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''), mount_smb_share=_mount_with('other'))
    results = cu.test_cst_source(_cst(3), '/data')
    assert parts(results)[-1] == ('Source directory', 'Fail')
    assert reasons(results)[-1] == 'Unable to find source directory: /data on SMB share'


@pytest.mark.parametrize('mounted, source, expected', [
    (['xbt_01'], '/xbt_*', [('Source directory', 'Pass'), ('Write test', 'Pass')]),
    (['other'], '/xbt_*', [('Source directory', 'Fail'), ('Write test', 'Fail')]),
    ([], '/missing/xbt_*', [('Source directory', 'Fail'), ('Write test', 'Fail')]),
])
def test_mounted_wildcard_source(tmp_path, mounted, source, expected) -> None:
    """A matching directory, no match, and a missing parent in a mount."""
    for directory in mounted:
        (tmp_path / directory).mkdir()
    results = cu._test_mounted_source(str(tmp_path), source, True, 'SMB share')  # pylint: disable=protected-access
    assert parts(results) == expected


def test_mounted_source_not_writable(tmp_path, monkeypatch) -> None:
    """Removing source files needs write access, with or without a wildcard."""
    monkeypatch.setattr(cu, 'test_write_access', lambda path: False)
    (tmp_path / 'xbt_01').mkdir()
    for source in ('/', '/xbt_*'):
        results = cu._test_mounted_source(str(tmp_path), source, True, 'FTP server')  # pylint: disable=protected-access
        assert parts(results) == [('Source directory', 'Pass'), ('Write test', 'Fail')]


def test_rsync_source(monkeypatch, fake_run) -> None:
    """The password goes in a private file; the server, then the source directory, is listed."""
    seen = []

    def connection(server, user, password_file):
        seen.append((server, Path(password_file).read_text(encoding='utf-8'),
                     oct(os.stat(password_file).st_mode & 0o777)))
        return True, ''

    monkeypatch.setattr(cu, 'test_rsync_connection', connection)
    assert parts(cu.test_cst_source(_cst(2, rsyncPass='p@ss'), '/data/xbt*')) == [
        ('Rsync connection', 'Pass'), ('Source directory', 'Pass')]
    assert seen == [('host/module', 'p@ss', '0o600'), ('host/module/data', 'p@ss', '0o600')]


def test_rsync_source_anonymous(monkeypatch) -> None:
    """Anonymous rsync logins have no password file."""
    passwords = []
    monkeypatch.setattr(cu, 'test_rsync_connection', lambda s, u, p: passwords.append(p) or (True, ''))
    cu.test_cst_source(_cst(2, rsyncUser='anonymous', rsyncPass=None), '/data')
    assert passwords == [None, None]


def test_rsync_source_without_a_password() -> None:
    """No password from the web app (worker token): fail before connecting."""
    results = cu.test_cst_source(_cst(2, rsyncPass=None), '/data')
    assert parts(results) == [('Writing temporary rsync password file', 'Fail'), ('Rsync connection', 'Fail'),
                              ('Source directory', 'Fail')]


@pytest.mark.parametrize('answers, source, expected, reason', [
    ([(False, 'auth failed')], '/data',
     [('Rsync connection', 'Fail'), ('Source directory', 'Fail')],
     'Could not connect to rsync server: host/module as survey — auth failed'),
    ([(True, ''), (False, 'No such file')], '/data',
     [('Rsync connection', 'Pass'), ('Source directory', 'Fail')],
     'Unable to find source directory: /data on the Rsync Server: host/module — No such file'),
    ([(True, ''), (False, '')], '/data/x*',
     [('Rsync connection', 'Pass'), ('Source directory', 'Fail')],
     'Unable to find parent directory: /data on the Rsync Server: host/module'),
])
def test_rsync_source_failures(monkeypatch, answers, source, expected, reason) -> None:
    """A failed login, a missing source directory, and a missing wildcard parent."""
    replies = iter(answers)
    monkeypatch.setattr(cu, 'test_rsync_connection', lambda *args: next(replies))
    results = cu.test_cst_source(_cst(2), source)
    assert parts(results) == expected and reasons(results)[-1] == reason


def test_ssh_source(monkeypatch) -> None:
    """A wildcard source checks its parent directory."""
    checked = []
    _replace(monkeypatch, test_ssh_connection=lambda *a, **k: (True, ''),
             test_ssh_remote_directory=lambda s, u, d, **k: checked.append((d, k)) or (True, ''))
    assert parts(cu.test_cst_source(_cst(4, sshUseKey='1', sshPass=None), '/data/x*')) == [
        ('SSH connection', 'Pass'), ('Source directory', 'Pass')]
    assert checked == [('/data', {'passwd': None, 'use_pubkey': True})]


def test_ssh_source_failures(monkeypatch) -> None:
    """No password, a failed login, and a missing source directory."""
    assert parts(cu.test_cst_source(_cst(4, sshPass=None), '/data')) == [
        ('SSH connection', 'Fail'), ('Source directory', 'Fail')]

    monkeypatch.setattr(cu, 'test_ssh_connection', lambda *a, **k: (False, 'Permission denied'))
    results = cu.test_cst_source(_cst(4), '/data')
    assert parts(results) == [('SSH connection', 'Fail'), ('Source directory', 'Fail')]
    assert reasons(results)[0] == 'Unable to connect to SSH server: host as survey — Permission denied'

    _replace(monkeypatch, test_ssh_connection=lambda *a, **k: (True, ''),
             test_ssh_remote_directory=lambda *a, **k: (False, 'No such file'))
    results = cu.test_cst_source(_cst(4), '/data')
    assert parts(results) == [('SSH connection', 'Pass'), ('Source directory', 'Fail')]
    assert reasons(results)[-1] == 'Unable to find source directory: /data — No such file'


def _ftp(monkeypatch, connection=(True, ''), mounted=(), mount_ok=True, config=(True, 'rclone.conf')):
    """Replace the FTP steps; the "mount" creates directories in <tmpdir>/mntpoint."""
    def mount(cfg, tmpdir, rclone_config, mount_base):
        if not mount_ok:
            return False, 'fusermount: not found'
        mntpoint = os.path.join(tmpdir, 'mntpoint')
        for directory in mounted:
            os.makedirs(os.path.join(mntpoint, directory))
        os.makedirs(mntpoint, exist_ok=True)
        return True, mntpoint

    listed = []
    _replace(monkeypatch, prepare_ftp_config=lambda cfg, tmpdir: config,
             test_ftp_connection=lambda cfg, remote, path: listed.append(path) or connection,
             prepare_ftp_mount=mount)
    return listed


def test_ftp_source(monkeypatch) -> None:
    """The mount base is listed and mounted (#209); the source is checked in the mount."""
    listed = _ftp(monkeypatch, mounted=['xbt_01'])
    assert parts(cu.test_cst_source(_cst(5, removeSourceFiles='1'), '/data/xbt_*')) == [
        ('FTP server', 'Pass'), ('Mount FTP server', 'Pass'), ('Source directory', 'Pass'), ('Write test', 'Pass')]
    assert listed == ['/data']


def test_ftp_source_config_fails(monkeypatch) -> None:
    """A setup failure (e.g. no password) fails before connecting."""
    _ftp(monkeypatch, config=(False, cu.FTP_PASS_MISSING))
    results = cu.test_cst_source(_cst(5), '/data')
    assert parts(results) == [('FTP server', 'Fail'), ('Source directory', 'Fail')]
    assert reasons(results) == [cu.FTP_PASS_MISSING] * 2


@pytest.mark.parametrize('source, reason', [
    ('/data/xbt', 'Unable to find source directory: /data/xbt on FTP server'),
    ('/data/xbt/', 'Unable to find source directory: /data/xbt/ on FTP server'),
    ('/data/xbt*', 'Unable to find parent directory: /data on FTP server'),
])
def test_ftp_source_directory_not_found(monkeypatch, source, reason) -> None:
    """Logged in but can't list it: the server passes, the source fails (#242)."""
    _ftp(monkeypatch, connection=(False, '501 No such directory.'))
    results = cu.test_cst_source(_cst(5, removeSourceFiles='1'), source)
    assert parts(results) == [('FTP server', 'Pass'), ('Source directory', 'Fail'), ('Write test', 'Fail')]
    assert reasons(results)[1] == reason


def test_ftp_source_login_fails(monkeypatch) -> None:
    """A failed login fails the server and source with rclone's error."""
    _ftp(monkeypatch, connection=(False, '530 Login incorrect.'))
    results = cu.test_cst_source(_cst(5), '/data')
    assert parts(results) == [('FTP server', 'Fail'), ('Source directory', 'Fail')]
    assert reasons(results)[0] == 'Could not connect to FTP server: ftp.example.org:21 as survey — 530 Login incorrect.'


def test_ftp_source_mount_fails(monkeypatch) -> None:
    """Logged in, but the mount failed."""
    _ftp(monkeypatch, mount_ok=False)
    results = cu.test_cst_source(_cst(5, removeSourceFiles='1'), '/data')
    assert parts(results) == [('FTP server', 'Pass'), ('Mount FTP server', 'Fail'), ('Source directory', 'Fail'),
                              ('Write test', 'Fail')]
    assert reasons(results)[1].endswith('— fusermount: not found')


# --- Cruise data transfer destinations ----------------------------------------

def test_local_destination_ends_on_failure(tmp_path) -> None:
    """A missing local destination fails, and an existing one passes, with nothing else checked."""
    assert parts(cu.test_cdt_destination(_cst(1, destDir=str(tmp_path / 'missing')))) == [
        ('Destination directory', 'Fail'), ('Write test', 'Fail')]
    assert parts(cu.test_cdt_destination(_cst(1, destDir=str(tmp_path)))) == [
        ('Destination directory', 'Pass'), ('Write test', 'Pass')]


def test_local_destination_not_writable(tmp_path, monkeypatch) -> None:
    """A destination that cannot be written to fails the write test."""
    monkeypatch.setattr(cu, 'test_write_access', lambda path: False)
    assert parts(cu.test_local_destination(str(tmp_path))) == [('Destination directory', 'Pass'),
                                                               ('Write test', 'Fail')]


def test_smb_destination(monkeypatch) -> None:
    """The destination directory is checked inside the mounted share."""
    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''), mount_smb_share=_mount_with('backup'))
    assert parts(cu.test_cdt_destination(_cst(3, destDir='/backup'))) == [
        ('SMB server', 'Pass'), ('SMB share', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Pass')]


def test_smb_destination_failures(monkeypatch) -> None:
    """No password, an unreachable server, and a share that would not mount."""
    results = cu.test_cdt_destination(_cst(3, destDir='/b', smbPass=None))
    assert parts(results) == [('SMB server', 'Fail'), ('SMB share', 'Fail'), ('Destination directory', 'Fail'),
                              ('Write test', 'Fail')]

    monkeypatch.setattr(cu, 'detect_smb_version', lambda cfg: (None, 'NT_STATUS_HOST_UNREACHABLE'))
    results = cu.test_cdt_destination(_cst(3, destDir='/b'))
    assert parts(results)[0] == ('SMB server', 'Fail') and 'NT_STATUS_HOST_UNREACHABLE' in reasons(results)[0]

    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''),
             mount_smb_share=lambda *args: (False, 'mount error(2)'))
    results = cu.test_cdt_destination(_cst(3, destDir='/b'))
    assert parts(results) == [('SMB server', 'Pass'), ('SMB share', 'Fail'), ('Destination directory', 'Fail'),
                              ('Write test', 'Fail')]
    assert reasons(results)[1].endswith('— mount error(2)')


def test_rsync_destination(monkeypatch) -> None:
    """The destDir is joined to the module (#228) for the directory and write checks."""
    servers = []
    _replace(monkeypatch, test_rsync_connection=lambda s, u, p: servers.append(s) or (True, ''),
             test_rsync_write_access=lambda s, u, tmpdir, p: servers.append(('write', s)) or (True, ''))
    assert parts(cu.test_cdt_destination(_cst(2, destDir='/backups/'))) == [
        ('Rsync connection', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Pass')]
    assert servers == ['host/module', 'host/module/backups', ('write', 'host/module/backups')]


@pytest.mark.parametrize('connection, write, expected', [
    ([(False, 'x')], (True, ''), [('Rsync connection', 'Fail'), ('Destination directory', 'Fail')]),
    ([(True, ''), (False, 'x')], (True, ''), [('Rsync connection', 'Pass'), ('Destination directory', 'Fail')]),
    ([(True, ''), (True, '')], (False, 'x'),
     [('Rsync connection', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Fail')]),
])
def test_rsync_destination_failures(monkeypatch, connection, write, expected) -> None:
    """A failed login, a missing destination directory, and no write access."""
    replies = iter(connection)
    _replace(monkeypatch, test_rsync_connection=lambda *args: next(replies),
             test_rsync_write_access=lambda *args: write)
    assert parts(cu.test_cdt_destination(_cst(2, destDir='backups'))) == expected


def test_rsync_destination_without_a_password() -> None:
    """No password from the web app (worker token): fail before connecting."""
    assert parts(cu.test_cdt_destination(_cst(2, destDir='b', rsyncPass=None)))[0] == (
        'Writing temporary rsync password file', 'Fail')


@pytest.mark.parametrize('connection, directory, write, expected', [
    ((True, ''), (True, ''), (True, ''),
     [('SSH connection', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Pass')]),
    ((False, 'x'), (True, ''), (True, ''),
     [('SSH connection', 'Fail'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]),
    ((True, ''), (False, 'x'), (True, ''),
     [('SSH connection', 'Pass'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]),
    ((True, ''), (True, ''), (False, 'x'),
     [('SSH connection', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Fail')]),
])
def test_ssh_destination(monkeypatch, connection, directory, write, expected) -> None:
    """Each failure fails the checks after it."""
    _replace(monkeypatch, test_ssh_connection=lambda *a, **k: connection,
             test_ssh_remote_directory=lambda *a, **k: directory, test_ssh_write_access=lambda *a, **k: write)
    assert parts(cu.test_cdt_destination(_cst(4, destDir='/backup'))) == expected


def test_ssh_destination_without_a_password() -> None:
    """No password from the web app (worker token): fail before connecting."""
    assert parts(cu.test_cdt_destination(_cst(4, destDir='/b', sshPass=None))) == [
        ('SSH connection', 'Fail'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]


@pytest.mark.parametrize('config, connection, write, expected', [
    ((True, 'c'), (True, ''), (True, ''),
     [('FTP server', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Pass')]),
    ((False, 'bad port'), (True, ''), (True, ''),
     [('FTP server', 'Fail'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]),
    ((True, 'c'), (False, "directory not found"), (True, ''),
     [('FTP server', 'Pass'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]),
    ((True, 'c'), (False, '530 Login incorrect.'), (True, ''),
     [('FTP server', 'Fail'), ('Destination directory', 'Fail'), ('Write test', 'Fail')]),
    ((True, 'c'), (True, ''), (False, '553 denied'),
     [('FTP server', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Fail')]),
])
def test_ftp_destination(monkeypatch, config, connection, write, expected) -> None:
    """FTP destinations (#199): the login, the directory, then a write test."""
    _replace(monkeypatch, prepare_ftp_config=lambda cfg, tmpdir: config,
             test_ftp_connection=lambda *args: connection, test_ftp_write_access=lambda *args: write)
    assert parts(cu.test_cdt_destination(_cst(5, destDir='/backup'))) == expected


# --- rclone destinations ------------------------------------------------------

def test_rclone_destination_without_the_remote(monkeypatch) -> None:
    """A remote missing from the rclone config fails first."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: None)
    assert parts(cu.test_cdt_rclone_destination(_cst(1, destDir='nope:backup'))) == [
        ('Rclone remote config', 'Fail')]


def test_rclone_destination_local_remote(monkeypatch, tmp_path) -> None:
    """A local remote's path is tested as a local directory."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: 'local')
    assert parts(cu.test_cdt_rclone_destination(_cst(1, destDir=f'disk:{tmp_path}'))) == [
        ('Rclone remote config', 'Pass'), ('Destination directory', 'Pass'), ('Write test', 'Pass')]


def test_rclone_destination_plain_local_path(tmp_path) -> None:
    """A path without a ":" is tested as a local directory."""
    assert parts(cu.test_cdt_rclone_destination(_cst(1, destDir=str(tmp_path)))) == [
        ('Destination directory', 'Pass'), ('Write test', 'Pass')]


def test_rclone_destination_smb_remote(monkeypatch) -> None:
    """An SMB remote is tested by mounting the share."""
    _replace(monkeypatch, get_rclone_remote_type=lambda name: 'smb',
             detect_smb_version=lambda cfg: (None, 'unreachable'))
    assert parts(cu.test_cdt_rclone_destination(_cst(1, destDir='nas:backup')))[:2] == [
        ('Rclone remote config', 'Pass'), ('SMB server', 'Fail')]


def _rclone(fake_run, features='{"Features": {}}', listing=0, copy=0, delete=0):
    """Script the rclone commands the remote checks run; 0 passes, 1 fails."""
    fake_run.on('rclone', 'backend', stdout=features)
    fake_run.on('rclone', 'lsd', returncode=listing, stderr='2026/10/22 10:00:00 ERROR : bucket missing')
    fake_run.on('rclone', 'lsf', returncode=listing, stderr='2026/10/22 10:00:00 ERROR : directory not found')
    fake_run.on('rclone', 'copyto', returncode=copy, stderr='2026/10/22 10:00:00 ERROR : 403 Forbidden')
    fake_run.on('rclone', 'deletefile', returncode=delete, stderr='2026/10/22 10:00:00 ERROR : 403 Forbidden')


@pytest.mark.parametrize('remote_type, features, first_part', [
    ('sftp', '{"Features": {}}', 'Destination directory'),
    ('s3', '{"Features": {"BucketBased": true}}', 'Verify bucket'),
    ('google cloud storage', '{"Features": {"BucketBased": true}}', 'Verify GCS bucket'),
    ('webdav', 'not json', 'Destination directory'),
])
def test_rclone_remote_destination(monkeypatch, fake_run, remote_type, features, first_part) -> None:
    """Buckets are checked as buckets, other remotes as directories, then a write test; GCS gets its options."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: remote_type)
    _rclone(fake_run, features=features)

    assert parts(cu.test_cdt_rclone_destination(_cst(1, destDir='remote:bucket/cruise'))) == [
        ('Rclone remote config', 'Pass'), (first_part, 'Pass'), ('Write test', 'Pass')]

    if first_part == 'Destination directory':
        assert fake_run.commands('rclone', 'lsf')[0][2] == 'remote:bucket/cruise'
    else:
        assert fake_run.commands('rclone', 'lsd')[0][2] == 'remote:bucket'
    copy = fake_run.commands('rclone', 'copyto')[0]
    assert ('--gcs-bucket-policy-only' in copy) is (remote_type == 'google cloud storage')
    assert copy[3].startswith('remote:bucket/cruise/.rclone-write-test-')


@pytest.mark.parametrize('remote_type, part', [('sftp', 'Destination directory'), ('s3', 'Verify bucket'),
                                               ('google cloud storage', 'Verify GCS bucket')])
def test_rclone_remote_unreachable(monkeypatch, fake_run, remote_type, part) -> None:
    """A remote rclone can't open fails as the check that would have run."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: remote_type)
    fake_run.on('rclone', 'backend', returncode=1, stderr='2026/10/22 10:00:00 Failed to create file system: dial tcp')
    results = cu.test_cdt_rclone_destination(_cst(1, destDir='remote:b'))
    assert parts(results)[1:] == [(part, 'Fail'), ('Write test', 'Fail')]
    assert reasons(results)[1] == 'Unable to connect to rclone remote remote: Failed to create file system: dial tcp'


@pytest.mark.parametrize('dest_dir, listing, copy, delete, expected', [
    ('remote:', 0, 0, 0, [('Verify bucket', 'Fail'), ('Write test', 'Fail')]),
    ('remote:b', 1, 0, 0, [('Verify bucket', 'Fail'), ('Write test', 'Fail')]),
    ('remote:b', 0, 1, 0, [('Verify bucket', 'Pass'), ('Write test', 'Fail')]),
    ('remote:b', 0, 0, 1, [('Verify bucket', 'Pass'), ('Write test', 'Fail')]),
])
def test_rclone_bucket_failures(monkeypatch, fake_run, dest_dir, listing, copy, delete, expected) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """No bucket in the path, a missing bucket, and a failed upload or delete."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: 's3')
    _rclone(fake_run, features='{"Features": {"BucketBased": true}}', listing=listing, copy=copy, delete=delete)
    results = cu.test_cdt_rclone_destination(_cst(1, destDir=dest_dir))
    assert parts(results)[1:] == expected
    if dest_dir == 'remote:':
        assert reasons(results)[1].startswith('No bucket in destination remote:')


def test_rclone_destination_without_rclone(monkeypatch, fake_run) -> None:
    """A missing rclone is reported."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: 'sftp')
    fake_run.on('rclone', raises=FileNotFoundError('rclone'))
    assert reasons(cu.test_cdt_rclone_destination(_cst(1, destDir='r:x')))[1].endswith('rclone is not installed')


# --- Remaining branches -------------------------------------------------------

def test_local_wildcard_source_on_a_mount_point(tmp_path, monkeypatch) -> None:
    """A wildcard source marked as a mount point checks its first match's top two components."""
    (tmp_path / 'xbt_01').mkdir()
    real_ismount = os.path.ismount
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: False if str(tmp_path).startswith(path)
                        else real_ismount(path))
    cfg = _cst(1, localDirIsMountPoint='1', removeSourceFiles='1')
    assert parts(cu.test_cst_source(cfg, str(tmp_path / 'xbt_*'))) == [
        ('Source directory', 'Pass'), ('Source directory is a mount point', 'Fail'), ('Write test', 'Fail')]

    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: str(tmp_path).startswith(path) or real_ismount(path))
    monkeypatch.setattr(cu, 'test_write_access', lambda path: False)
    assert parts(cu.test_cst_source(cfg, str(tmp_path / 'xbt_*'))) == [
        ('Source directory', 'Pass'), ('Source directory is a mount point', 'Pass'), ('Write test', 'Fail')]


def test_local_wildcard_source_missing_parent_on_a_mount_point(tmp_path) -> None:
    """A missing parent also fails the mount point and write checks."""
    cfg = _cst(1, localDirIsMountPoint='1', removeSourceFiles='1')
    assert parts(cu.test_cst_source(cfg, str(tmp_path / 'missing' / 'x*'))) == [
        ('Source directory', 'Fail'), ('Source directory is a mount point', 'Fail'), ('Write test', 'Fail')]


def test_local_source_not_a_mount_point_with_write_test(tmp_path, monkeypatch) -> None:
    """A source that is not mounted also fails the write test."""
    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: False)
    assert parts(cu.test_cst_source(_cst(1, localDirIsMountPoint='1', removeSourceFiles='1'), str(tmp_path))) == [
        ('Source directory', 'Pass'), ('Source directory is a mount point', 'Fail'), ('Write test', 'Fail')]


def test_failures_add_a_failed_write_test_when_removing_source_files(monkeypatch) -> None:
    """SMB mount and FTP login failures also fail the write test the transfer would need."""
    _replace(monkeypatch, detect_smb_version=lambda cfg: ('2.1', ''),
             mount_smb_share=lambda *args: (False, ''))
    assert parts(cu.test_cst_source(_cst(3, removeSourceFiles='1'), '/d'))[-1] == ('Write test', 'Fail')

    _ftp(monkeypatch, connection=(False, '530 Login incorrect.'))
    assert parts(cu.test_cst_source(_cst(5, removeSourceFiles='1'), '/d'))[-1] == ('Write test', 'Fail')


def test_mounted_source_missing_with_write_test(tmp_path) -> None:
    """A missing source in a mount also fails the write test."""
    results = cu._test_mounted_source(str(tmp_path), '/missing', True, 'SMB share')  # pylint: disable=protected-access
    assert parts(results) == [('Source directory', 'Fail'), ('Write test', 'Fail')]


@pytest.mark.parametrize('test', [cu.test_cst_source, cu.test_cdt_destination])
def test_rsync_password_file_cant_be_written(monkeypatch, test) -> None:
    """A password file that cannot be written fails before connecting."""
    def no_chmod(path, mode):
        raise PermissionError(path)

    monkeypatch.setattr(cu.os, 'chmod', no_chmod)
    args = (_cst(2), '/data') if test is cu.test_cst_source else (_cst(2, destDir='b'),)
    results = test(*args)
    assert parts(results)[0] == ('Writing temporary rsync password file', 'Fail')
    assert reasons(results)[0].startswith('Unable to create temporary rsync password file')


def test_rsync_destination_anonymous(monkeypatch) -> None:
    """Anonymous rsync logins have no password file."""
    passwords = []
    _replace(monkeypatch, test_rsync_connection=lambda s, u, p: passwords.append(p) or (True, ''),
             test_rsync_write_access=lambda s, u, tmpdir, p: passwords.append(p) or (True, ''))
    cu.test_cdt_destination(_cst(2, destDir='b', rsyncUser='anonymous', rsyncPass=None))
    assert passwords == [None, None, None]


def test_ssh_wildcard_parent_missing(monkeypatch) -> None:
    """A wildcard source's missing parent is named in the reason."""
    _replace(monkeypatch, test_ssh_connection=lambda *a, **k: (True, ''),
             test_ssh_remote_directory=lambda *a, **k: (False, ''))
    assert reasons(cu.test_cst_source(_cst(4), '/data/x*'))[-1] == 'Unable to find parent directory: /data'


def test_rclone_destination_plain_path_of_another_type() -> None:
    """Without a ':' and not local or SMB, there's nothing for rclone to test."""
    assert cu.test_cdt_rclone_destination(_cst(4, destDir='/backup')) == []


def test_local_destination_mount_point(tmp_path, monkeypatch) -> None:
    """A destination marked as a mount point: missing, not mounted, mounted."""
    missing = cu.test_local_destination(str(tmp_path / 'missing'), 1)
    assert parts(missing) == [('Destination directory', 'Fail'), ('Destination directory is a mount point', 'Fail'),
                              ('Write test', 'Fail')]

    monkeypatch.setattr(cu.os.path, 'ismount', lambda path: False)
    assert parts(cu.test_local_destination(str(tmp_path), 1)) == [
        ('Destination directory', 'Pass'), ('Destination directory is a mount point', 'Fail'), ('Write test', 'Fail')]


def test_on_root_filesystem(tmp_path) -> None:
    """The real check compares devices with /."""
    assert cu._on_root_filesystem(os.sep) is True  # pylint: disable=protected-access
    assert isinstance(cu._on_root_filesystem(str(tmp_path)), bool)  # pylint: disable=protected-access
