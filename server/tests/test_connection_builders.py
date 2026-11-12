"""Tests for connection_utils' command builders and parsers, which run nothing (#508)."""

import calendar
import os
from datetime import datetime

import pytest

from server.lib import connection_utils as cu


# --- Transfer configuration ---------------------------------------------------

@pytest.mark.parametrize('text, expected', [
    ('/data', False), ('/data/*', True), ('/data/file?.txt', True), ('/data/[ab]', True), ('', False),
])
def test_has_wildcard(text, expected) -> None:
    """*, ? and [ are wildcards."""
    assert cu.has_wildcard(text) is expected


def test_normalize_transfer_config_converts_known_int_fields() -> None:
    """PHP sends every column as a string; known integer fields become ints, others don't."""
    cfg = {'transferType': '4', 'sshUseKey': '0', 'removeSourceFiles': '1', 'sshServer': '10.0.0.1',
           'bandwidthLimit': 'not a number', 'enable': 1}
    result = cu.normalize_transfer_config(cfg)

    assert result == {'transferType': 4, 'sshUseKey': 0, 'removeSourceFiles': 1, 'sshServer': '10.0.0.1',
                      'bandwidthLimit': 'not a number', 'enable': 1}
    assert cfg['transferType'] == '4', "the original is left alone"


@pytest.mark.parametrize('code, name', [
    (1, 'local'), ('2', 'rsync'), (3, 'smb'), ('4', 'ssh'), (5, 'ftp'), (6, None), ('', None), (None, None),
])
def test_get_transfer_type(code, name) -> None:
    """Transfer type codes 1-5, as int or string; anything else is None."""
    assert cu.get_transfer_type(code) == name


def test_get_rclone_remote_type(tmp_path) -> None:
    """The remote's type from the rclone config; None without the file, remote or type."""
    config = tmp_path / 'rclone.conf'
    config.write_text('[gcs]\ntype = google cloud storage\n[notype]\nhost = x\n')

    assert cu.get_rclone_remote_type('gcs', str(config)) == 'google cloud storage'
    assert cu.get_rclone_remote_type('missing', str(config)) is None
    assert cu.get_rclone_remote_type('notype', str(config)) is None
    assert cu.get_rclone_remote_type('gcs', str(tmp_path / 'none.conf')) is None


# --- rsync and rclone commands ------------------------------------------------

def test_build_rsync_command() -> None:
    """Options, then the file lists, then source and destination."""
    assert cu.build_rsync_command(['-a'], ['--x'], '/src/', '/dest/', '/tmp/in', '/tmp/out') == [
        'rsync', '-a', '--x', '--files-from=/tmp/in', '--exclude-from=/tmp/out', '/src/', '/dest/']


def test_build_rsync_command_lists_without_destination() -> None:
    """Without a destination, rsync lists the source."""
    assert cu.build_rsync_command(['-a'], None, 'rsync://u@h', None, None) == ['rsync', '-a', 'rsync://u@h']


def test_build_rclone_command() -> None:
    """Both directories get exactly one trailing slash; options follow them."""
    assert cu.build_rclone_command('sync', ['-v'], ['--config', 'c'], '/src//', 'remote:dest',
                                   '/tmp/in', '/tmp/out') == [
        'rclone', 'sync', '/src/', 'remote:dest/', '-v', '--config', 'c',
        '--files-from', '/tmp/in', '--exclude-from', '/tmp/out']
    assert cu.build_rclone_command('copy', None, None, '/a', '/b') == ['rclone', 'copy', '/a/', '/b/']


def test_build_rclone_command_rejects_other_subcommands() -> None:
    """Only 'copy' and 'sync' are allowed."""
    with pytest.raises(ValueError):
        cu.build_rclone_command('move', None, None, '/a', '/b')


@pytest.mark.parametrize('server, dest_dir, expected', [
    ('host/module', 'backups', 'host/module/backups'),
    ('host/module/', '/backups/', 'host/module/backups'),
    ('host/module', '/', 'host/module'),
    ('host/module', '', 'host/module'),
    ('host/module', None, 'host/module'),
])
def test_rsync_dest_path(server, dest_dir, expected) -> None:
    """A destDir relative to the module is joined with one slash (#228, #247)."""
    assert cu.rsync_dest_path(server, dest_dir) == expected


def _cst(**overrides) -> dict:
    """A collection system transfer config with every option off."""
    cfg = {'transferType': '1', 'skipEmptyFiles': '0', 'skipEmptyDirs': '0', 'bandwidthLimit': '0',
           'removeSourceFiles': '0', 'syncToDest': '0'}
    cfg.update(overrides)
    return cfg


def test_build_rsync_options_dry_run() -> None:
    """A dry run lists itemized changes and stats."""
    assert cu.build_rsync_options(_cst()) == ['-trinv', '--protect-args', '--dry-run', '--stats']


def test_build_rsync_options_real_transfer() -> None:
    """A real transfer shows progress instead."""
    assert cu.build_rsync_options(_cst(), mode='real') == ['-triv', '--protect-args', '--progress']


def test_build_rsync_options_all_settings() -> None:
    """Each setting adds its option; rsync servers get --no-motd."""
    cfg = _cst(transferType='2', skipEmptyFiles='1', skipEmptyDirs='1', bandwidthLimit='500',
               removeSourceFiles='1', syncToDest='1')
    flags = cu.build_rsync_options(cfg, mode='real')
    assert flags[0] == '-triv'
    assert set(flags[1:]) == {'--bwlimit=500', '--delete', '--remove-source-files', '-m', '--min-size=1',
                              '--protect-args', '--progress', '--no-motd'}


def test_build_rsync_options_darwin_has_no_protect_args() -> None:
    """macOS's rsync doesn't support --protect-args."""
    assert '--protect-args' not in cu.build_rsync_options(_cst(), is_darwin=True)


def test_build_rsync_options_dry_run_ignores_transfer_settings() -> None:
    """A dry run never deletes or removes anything."""
    flags = cu.build_rsync_options(_cst(removeSourceFiles='1', syncToDest='1', bandwidthLimit='5'))
    assert not {'--delete', '--remove-source-files', '--bwlimit=5'} & set(flags)


def _cdt(**overrides) -> dict:
    """A cruise data transfer config to a local directory."""
    cfg = {'destDir': '/backup', 'syncToDest': '0', 'skipEmptyDirs': '1', 'bandwidthLimit': '0'}
    cfg.update(overrides)
    return cfg


def test_build_rclone_options_defaults() -> None:
    """A plain copy, as a dry run."""
    assert cu.build_rclone_options(_cdt()) == ('copy', ['--progress', '--dry-run'])


def test_build_rclone_options_real_sync() -> None:
    """syncToDest syncs, empty dirs are created unless skipped, -v logs files (#230)."""
    copy_sync, flags = cu.build_rclone_options(_cdt(syncToDest='1', skipEmptyDirs='0', bandwidthLimit='200'),
                                               mode='real')
    assert copy_sync == 'sync'
    assert flags == ['--progress', '--create-empty-src-dirs', '-v', '--bwlimit', '200k']


def test_build_rclone_options_gcs_remote(monkeypatch) -> None:
    """A Google Cloud Storage remote gets its bucket options."""
    monkeypatch.setattr(cu, 'get_rclone_remote_type', lambda name: 'google cloud storage')
    _, flags = cu.build_rclone_options(_cdt(destDir='gcs:bucket/cruise'))
    assert ['--gcs-bucket-policy-only', '--local-no-set-modtime'] == flags[-2:]


# --- ssh ----------------------------------------------------------------------

def test_build_ssh_command_with_key() -> None:
    """A key login runs in batch mode."""
    assert cu.build_ssh_command(None, 'survey', 'host', 'ls', None, True) == [
        'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
        'survey@host', 'ls']


def test_build_ssh_command_with_password_file() -> None:
    """A password login reads the password from a file (sshpass -f), never the command line."""
    cmd = cu.build_ssh_command(['-p', '2222'], 'survey', 'host', 'ls', '/tmp/pw', False)
    assert cmd[:3] == ['sshpass', '-f', '/tmp/pw']
    assert 'PubkeyAuthentication=no' in cmd and cmd[-4:] == ['-p', '2222', 'survey@host', 'ls']


def test_build_ssh_command_needs_a_password_file_or_key() -> None:
    """Without a password file or key there is no way to log in."""
    with pytest.raises(ValueError):
        cu.build_ssh_command(None, 'survey', 'host', 'ls', None, False)


@pytest.mark.parametrize('patterns, host, expected', [
    (['*'], 'ship.local', True),
    (['ship.*'], 'ship.local', True),
    (['Ship.*'], 'ship.local', False),
    (['*', '!ship.local'], 'ship.local', False),
    (['!other', 'ship?local'], 'ship.local', True),
    ([], 'ship.local', False),
])
def test_ssh_host_matches(patterns, host, expected) -> None:
    """ssh_config Host patterns: wildcards, case-sensitive, negation wins (#340)."""
    assert cu._ssh_host_matches(patterns, host) is expected  # pylint: disable=protected-access


@pytest.fixture
def ssh_dir(tmp_path, monkeypatch):
    """A home directory with an empty .ssh directory."""
    monkeypatch.setenv('HOME', str(tmp_path))
    directory = tmp_path / '.ssh'
    directory.mkdir()
    return directory


def test_ssh_identity_file_default_keys(ssh_dir) -> None:
    """Without a config, the first default key that exists, in ssh's order."""
    assert cu.ssh_identity_file('host') is None
    (ssh_dir / 'id_ed25519').write_text('key')
    assert cu.ssh_identity_file('host') == str(ssh_dir / 'id_ed25519')
    (ssh_dir / 'id_rsa').write_text('key')
    assert cu.ssh_identity_file('host') == str(ssh_dir / 'id_rsa')


def test_ssh_identity_file_from_config(ssh_dir, tmp_path) -> None:
    """Matching Host and Match blocks, keyword=value, ~ and %h/%r tokens; others skipped."""
    for name in ('ship.local_survey', 'match_key', 'other'):
        (ssh_dir / name).write_text('key')
    (ssh_dir / 'config').write_text(
        '# comment\n'
        'Host other.host\n    IdentityFile ~/.ssh/other\n'
        'Match user survey\n    IdentityFile ~/.ssh/other\n'
        'HOST ship.*\n    identityfile=~/.ssh/%h_%r\n'
        'Match host ship.local,!x\n    IdentityFile .ssh/match_key\n')

    assert cu.ssh_identity_file('ship.local', 'survey') == str(ssh_dir / 'ship.local_survey')
    os.remove(ssh_dir / 'ship.local_survey')
    assert cu.ssh_identity_file('ship.local', 'survey') == str(tmp_path / '.ssh' / 'match_key')


# --- rclone output ------------------------------------------------------------

@pytest.mark.parametrize('stderr, expected', [
    ('2026/10/22 10:00:00 ERROR : x: directory not found\n', 'x: directory not found'),
    ('2026/10/22 10:00:00 Failed to create file system: bad\n', 'Failed to create file system: bad'),
    ('first\n\n  last line  \n', 'last line'),
    ('', 'rclone failed with no error message'),
    (None, 'rclone failed with no error message'),
])
def test_rclone_error(stderr, expected) -> None:
    """The last line, without rclone's timestamp and level."""
    assert cu.rclone_error(stderr) == expected


def test_ftp_rclone_error_drops_the_remote_name() -> None:
    """The internal ftp_source remote name is left out of the message."""
    stderr = '2026/10/22 10:00:00 Failed to create file system for "ftp_source:/": NewFs: 530 Login incorrect.'
    assert cu._ftp_rclone_error(stderr) == '530 Login incorrect.'  # pylint: disable=protected-access


def test_rfc3339_to_epoch() -> None:
    """rclone ModTimes, with nanoseconds and time zones."""
    utc = calendar.timegm(datetime(2019, 8, 11, 19, 3, 35).timetuple())
    to_epoch = cu._rfc3339_to_epoch  # pylint: disable=protected-access
    assert to_epoch('2019-08-11T19:03:35Z') == utc
    assert to_epoch('2019-08-11T19:03:35.123456789Z') == pytest.approx(utc + 0.123456789)
    assert to_epoch('2019-08-11T15:03:35-04:00') == utc
    assert to_epoch('2019-08-11T21:33:35+02:30') == utc
    with pytest.raises(ValueError):
        to_epoch('2019-08-11 19:03:35')


# --- FTP server field and paths -----------------------------------------------

@pytest.mark.parametrize('value, expected', [
    ('ftp.example.org', ('ftp.example.org', 21)),
    (' ftp.example.org:2121 ', ('ftp.example.org', 2121)),
    ('10.0.0.5:21', ('10.0.0.5', 21)),
    ('[fe80::1]:990', ('fe80::1', 990)),
    ('[fe80::1]', ('fe80::1', 21)),
    ('fe80::1', ('fe80::1', 21)),
    ('host:', ('host', 21)),
])
def test_split_ftp_server(value, expected) -> None:
    """host, host:port, [ipv6]:port or a bare IPv6 address; port 21 by default (#224)."""
    assert cu.split_ftp_server(value) == expected


@pytest.mark.parametrize('value', ['host:0', 'host:65536', 'host:ftp', '[fe80::1', '[fe80::1]x'])
def test_split_ftp_server_rejects_bad_ports(value) -> None:
    """Ports outside 1-65535, non-numeric ports and unmatched brackets."""
    with pytest.raises(ValueError):
        cu.split_ftp_server(value)


@pytest.mark.parametrize('value, expected', [
    ('ftp.example.org', 'ftp.example.org:21'), ('[fe80::1]:990', '[fe80::1]:990'), ('host:bad', 'host:bad'),
])
def test_ftp_server_label(value, expected) -> None:
    """host:port for messages; unparseable values are shown as given."""
    assert cu.ftp_server_label(value) == expected


def test_ere_escape() -> None:
    """POSIX ERE specials are escaped; -, # and ~ aren't (#242)."""
    assert cu.ere_escape('rclone mount ftp_source:/data/*.txt /tmp/a-b') == \
        r'rclone mount ftp_source:/data/\*\.txt /tmp/a-b'
    assert cu.ere_escape(r'a(b)[c]{d}|e^f$g+h?i\j') == r'a\(b\)\[c\]\{d\}\|e\^f\$g\+h\?i\\j'


@pytest.mark.parametrize('source_dir, expected', [
    ('/data/xbt', '/data/xbt'),
    ('/data/xbt/', '/data/xbt'),
    ('/data/xbt*', '/data'),
    ('/data/*/raw', '/data/*/raw'),
    ('data', '/data'),
    ('/', '/'),
    ('/*', '/'),
])
def test_ftp_mount_base(source_dir, expected) -> None:
    """The source directory, or a wildcard source's parent, never the server root (#209)."""
    assert cu.ftp_mount_base(source_dir) == expected


@pytest.mark.parametrize('path, mount_base, expected', [
    ('/data/xbt', None, '/mnt/data/xbt'),
    ('/data/xbt', '/', '/mnt/data/xbt'),
    ('/data/xbt', '/data/xbt', '/mnt'),
    ('/data/xbt/raw', '/data/xbt', '/mnt/raw'),
    ('/data/xbt/', '/data', '/mnt/xbt'),
])
def test_mount_path(path, mount_base, expected) -> None:
    """Where a server path is in a mount of mount_base (#209)."""
    assert cu.mount_path('/mnt', path, mount_base) == expected


def test_ssh_identity_file_match_all(ssh_dir) -> None:
    """A Match all block applies to every host."""
    (ssh_dir / 'all_key').write_text('key')
    (ssh_dir / 'config').write_text('Host nope\nMatch all\n    IdentityFile "~/.ssh/all_key"\n')
    assert cu.ssh_identity_file('anything') == str(ssh_dir / 'all_key')
