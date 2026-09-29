#!/usr/bin/env python3
"""Utilities for testing and connecting to remote systems.

Provides the connection checks and command builders used by the transfer
workers for the transfer types: local directory, rsync server, SMB share,
SSH server, FTP server and rclone remote. Low-level connection tests return
``(bool, str)`` tuples (success flag plus detail); the higher-level
source/destination tests return ``list[dict]`` with
``partName``/``result``/``reason`` keys.
"""

import calendar
import glob
import json
import os
import re
import sys
import uuid
import logging
import tempfile
import subprocess
import time
import configparser
from datetime import datetime
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import test_write_access, temporary_directory

# Integer fields that PHP/PDO returns as strings but Python code compares with == 1 / == 0
_TRANSFER_INT_FIELDS = frozenset([
    'transferType', 'staleness', 'removeSourceFiles', 'useStartDate',
    'skipEmptyDirs', 'skipEmptyFiles', 'syncFromSource', 'syncToDest',
    'bandwidthLimit', 'cruiseOrLowering', 'localDirIsMountPoint',
    'sshUseKey', 'ftpPort', 'includeOVDMFiles', 'status', 'enable',
    'collectionSystemTransferID', 'cruiseDataTransferID',
    'collectionSystem', 'extraDirectory',
])


def has_wildcard(s):
    """Return whether a string contains glob wildcard characters (``*``, ``?``, ``[``).

    Args:
        s: The string to check, e.g. a source directory.

    Returns:
        bool: ``True`` if *s* contains a wildcard.
    """
    return any(c in s for c in ('*', '?', '['))


def normalize_transfer_config(cfg):
    """Return a copy of a transfer configuration with its integer fields as ints.

    PHP/PDO returns every database column as a string, so fields such as
    ``transferType``, ``sshUseKey`` or ``removeSourceFiles`` arrive as ``'1'``;
    callers that compare with ``== 1`` / ``== 0`` need real ints. Values that
    can't be converted are left unchanged.

    Args:
        cfg: A collection system or cruise data transfer configuration.

    Returns:
        dict: A copy of *cfg* with the known integer fields converted.
    """
    result = dict(cfg)
    for field in _TRANSFER_INT_FIELDS:
        if field in result and isinstance(result[field], str):
            try:
                result[field] = int(result[field])
            except (ValueError, TypeError):
                pass
    return result


def get_transfer_type(transfer_type):
    """Return the name of a transfer type code.

    Args:
        transfer_type: The ``transferType`` value (``1``-``5``, as int or str).

    Returns:
        str | None: ``'local'`` (1), ``'rsync'`` (2), ``'smb'`` (3),
        ``'ssh'`` (4) or ``'ftp'`` (5), or ``None`` for any other value.
    """

    transfer_type = str(transfer_type)

    if transfer_type == "1": # Local directory
        return 'local'

    if  transfer_type == "2": # Rsync server
        return 'rsync'

    if  transfer_type == "3": # SMB server
        return 'smb'

    if  transfer_type == "4": # SSH server
        return 'ssh'

    if  transfer_type == "5": # FTP server
        return 'ftp'

    return None


def get_rclone_remote_type(remote_name, config_path=None):
        """Return the type of an rclone remote from the rclone config file.

        Args:
            remote_name: Name of the remote (the part of ``remote:path`` before ``:``).
            config_path: rclone config file. Defaults to
                ``~/.config/rclone/rclone.conf``.

        Returns:
            The remote's ``type`` (e.g. ``'local'``, ``'smb'``, ``'sftp'``,
            ``'google cloud storage'``), or ``None`` if the config file doesn't
            exist or doesn't define the remote (or its type).
        """
        # Default rclone config path
        if config_path is None:
            config_path = os.path.expanduser("~/.config/rclone/rclone.conf")

        if not os.path.isfile(config_path):
            logging.error("rclone config file %s not found", config_path)
            return None

        config = configparser.ConfigParser()
        config.read(config_path)

        if remote_name not in config:
            logging.error("rclone remote %s not found in %s", remote_name, config_path)
            return None

        return config[remote_name].get('type')


def check_darwin(cfg):
    """Return whether a transfer's SSH server runs macOS (Darwin).

    Runs ``uname -s`` on the server over SSH, using ``sshpass`` when the
    transfer doesn't use a key. rsync on macOS doesn't support
    ``--protect-args``.

    Args:
        cfg: Transfer configuration with ``sshServer``, ``sshUser``,
            ``sshUseKey`` and ``sshPass``.

    Returns:
        bool: ``True`` if the server reports ``Darwin``; ``False`` otherwise,
        including when the SSH command fails.
    """

    cfg = normalize_transfer_config(cfg)
    cmd = ['ssh', f"{cfg['sshUser']}@{cfg['sshServer']}", "uname -s"]
    if cfg['sshUseKey'] == 0:
        cmd = ['sshpass', '-p', cfg.get('sshPass', '')] + cmd

    logging.debug("check_darwin cmd: %s", ' '.join(cmd).replace(f'-p {cfg.get("sshPass", "")}', '-p ****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return any(line.strip() == 'Darwin' for line in proc.stdout.splitlines())
    except subprocess.SubprocessError as exc:
        logging.error("SSH command to check for Dawin (MacOS) failed: %s", str(exc))
        return False


def detect_smb_version(cfg):
    """Detect which SMB protocol version to mount a transfer's server with.

    Lists the server's shares with ``smbclient`` (as guest if ``smbUser`` is
    ``'guest'``). Windows XP-era servers (``OS=[Windows 5.1]``) get ``'1.0'``;
    all others get ``'2.1'``.

    Args:
        cfg: Transfer configuration with ``smbServer``, ``smbDomain``,
            ``smbUser`` and ``smbPass``.

    Returns:
        tuple[str | None, str]: ``(version, "")`` on success, or ``(None,
        detail)`` with the error output if the server can't be reached or
        authentication fails.
    """

    if cfg.get('smbUser') == 'guest':
        cmd = [
            'smbclient', '-L', cfg['smbServer'],
            '-W', cfg['smbDomain'], '-m', 'SMB2', '-g', '-N'
        ]
    else:
        cmd = [
            'smbclient', '-L', cfg['smbServer'],
            '-W', cfg['smbDomain'], '-m', 'SMB2', '-g',
            '-U', f"{cfg['smbUser']}%{cfg.get('smbPass', '')}"
        ]

    logging.debug("detect_smb_version cmd: %s", ' '.join(cmd).replace(f'%{cfg.get("smbPass", "")}', '%****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if proc.returncode != 0 or "NT_STATUS" in proc.stderr or "failed" in proc.stderr.lower():
            detail = proc.stderr.strip()
            logging.error("Failed to connect to SMB server: %s", detail)
            return None, detail

        for line in proc.stdout.splitlines():
            if line.startswith('OS=[Windows 5.1]'):
                return '1.0', ""
        return '2.1', ""

    except subprocess.SubprocessError as exc:
        detail = str(exc)
        logging.error("SMB version detection failed: %s", detail)
        return None, detail


def mount_smb_share(cfg, mntpoint, smb_version):
    """Mount a transfer's SMB share (CIFS) on a local directory.

    The share is mounted read-write if the transfer removes source files
    (``removeSourceFiles``), otherwise read-only. On failure the mount point is
    unmounted again. Requires root.

    Args:
        cfg: Transfer configuration with ``smbServer`` (the share path),
            ``smbDomain``, ``smbUser`` and ``smbPass``.
        mntpoint: Existing local directory to mount the share on.
        smb_version: SMB protocol version, from :func:`detect_smb_version`.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    cfg = normalize_transfer_config(cfg)
    # Logic handles if cfg is a cst or cdt
    read_write = 'rw' if cfg.get('removeSourceFiles', 1) == 1 else 'ro'

    opts = f"{read_write},domain={cfg['smbDomain']},vers={smb_version}"

    if cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={cfg['smbUser']},password={cfg.get('smbPass', '')}"

    cmd = ['mount', '-t', 'cifs', cfg['smbServer'], mntpoint, '-o', opts]

    logging.debug("mount_smb_share cmd: %s", ' '.join(cmd).replace(f'password={cfg.get("smbPass", "")}', 'password=****'))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logging.info("Successfully mounted %s to %s", cfg['smbServer'], mntpoint)
        return True, ""
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else str(exc)
        logging.error("Failed to mount SMB share: %s.  Are you running as root?", detail)

        # Try to unmount in case of partial mount
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False, detail


def build_rsync_command(flags, extra_args, source_dir, dest_dir, include_filepath):
    """Build an rsync command line as an argument list for ``subprocess``.

    Args:
        flags: rsync options, e.g. from :func:`build_rsync_options`.
        extra_args: Additional arguments added after *flags*, or ``None``.
        source_dir: The source path.
        dest_dir: The destination path, or ``None`` to list *source_dir* only.
        include_filepath: File listing the files to transfer (passed as
            ``--files-from``), or ``None``.

    Returns:
        list[str]: The command, starting with ``rsync``.
    """

    cmd = ['rsync'] + flags
    if extra_args is not None:
        cmd += extra_args

    if include_filepath is not None:
        cmd.append(f"--files-from={include_filepath}")

    cmd += [source_dir] if dest_dir is None else [source_dir, dest_dir]
    return cmd


def test_rsync_connection(server, user, password_file=None):
    """Test that an rsync server accepts the transfer's credentials.

    Args:
        server: rsync server, as ``host`` or ``host/module``.
        user: rsync username.
        password_file: File holding the rsync password, or ``None``.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    flags = ['--no-motd', '--contimeout=5']
    extra_args = None

    if password_file is not None:
        extra_args = [f'--password-file={password_file}']

    cmd = build_rsync_command(flags, extra_args, f'rsync://{user}@{server}', None, None)

    logging.debug("test_rsync_connection cmd: %s", ' '.join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode not in [0, 24]:
            detail = proc.stderr.strip()
            logging.error("rsync connection test failed: %s", detail)
            return False, detail
        return True, ""
    except Exception as exc:
        detail = str(exc)
        logging.error("rsync connection test failed: %s", detail)
        return False, detail


def test_rsync_write_access(server, user, tmpdir, password_file=None):
    """Test that the transfer can write to an rsync server.

    Uploads a ``write_test.txt`` file. There's currently no way to delete it
    afterwards, so the file stays on the server.

    Args:
        server: rsync server, as ``host`` or ``host/module``.
        user: rsync username.
        tmpdir: Local temporary directory to create the test file in.
        password_file: File holding the rsync password, or ``None``.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    flags = ['--no-motd', '--contimeout=5']

    if password_file is not None:
        flags.extend([f'--password-file={password_file}'])

    write_test_dir = os.path.join(tmpdir, "write_test")
    os.mkdir(write_test_dir)
    write_test_file = os.path.join(write_test_dir, 'write_test.txt')

    with open(write_test_file, 'w', encoding='utf-8') as f:
        f.write("this is a write test file used by OpenVDM to determine if destination is writable")

    cmd = build_rsync_command(flags, ['--remove-source-files'], write_test_file, f'rsync://{user}@{server}', None)

    logging.debug("test_rsync_write_access cmd: %s", ' '.join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode not in [0, 24]:
            detail = proc.stderr.strip()
            logging.error("rsync write test failed: %s", detail)
            return False, detail
    except Exception as exc:
        detail = str(exc)
        logging.error("rsync write test failed: %s", detail)
        return False, detail

    return True, ""


def build_ssh_command(flags, user, server, post_cmd, passwd, use_pubkey):
    """Build an ssh command line as an argument list for ``subprocess``.

    Both forms use a 5 s connection timeout and skip host key checking. With a
    key the command runs in batch mode; with a password it's prefixed with
    ``sshpass`` and public-key authentication is disabled.

    Args:
        flags: Extra ssh options, or ``None``.
        user: SSH username.
        server: SSH server hostname or address.
        post_cmd: Command to run on the server.
        passwd: SSH password; ignored when *use_pubkey* is true.
        use_pubkey: Authenticate with the local user's SSH key instead of a
            password.

    Returns:
        list[str]: The command.

    Raises:
        ValueError: If there's no password and *use_pubkey* is false.
    """

    passwd = passwd or ''
    if (len(passwd) == 0) and use_pubkey is False:
        raise ValueError("Must specify either a passwd or use_pubkey")

    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5'] if use_pubkey else ['sshpass', '-p', f'{passwd}', 'ssh', '-o', 'PubkeyAuthentication=no','-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']
    cmd += flags or []
    cmd += [f'{user}@{server}', post_cmd]
    return cmd


def test_ssh_connection(server, user, passwd, use_pubkey):
    """Test that an SSH server accepts the transfer's credentials.

    Args:
        server: SSH server hostname or address.
        user: SSH username.
        passwd: SSH password; ignored when *use_pubkey* is true.
        use_pubkey: Authenticate with the local user's SSH key instead of a
            password.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    cmd = build_ssh_command(None, user, server, 'ls', passwd, use_pubkey)

    cmd_str = ' '.join(cmd)
    if passwd and len(passwd) > 0:
        cmd_str = cmd_str.replace(f'{passwd}', '****')

    logging.debug("test_ssh_connection cmd: %s", cmd_str)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip()
            logging.error("SSH connection test failed (exit %s): %s", proc.returncode, detail)
            return False, detail
    except Exception as exc:
        detail = str(exc)
        logging.error("SSH connection test failed: %s", detail)
        return False, detail
    return True, ""


def test_ssh_remote_directory(server, user, remote_dir, passwd, use_pubkey):
    """Test that a directory exists on an SSH server.

    Args:
        server: SSH server hostname or address.
        user: SSH username.
        remote_dir: Absolute path of the directory on the server.
        passwd: SSH password; ignored when *use_pubkey* is true.
        use_pubkey: Authenticate with the local user's SSH key instead of a
            password.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    passwd = passwd or ''
    cmd = build_ssh_command(None, user, server, f'ls "{remote_dir}"', passwd, use_pubkey)

    cmd_str = ' '.join(cmd)
    if passwd and len(passwd) > 0:
        cmd_str = cmd_str.replace(f'{passwd}', '****')

    logging.debug("test_ssh_destination cmd: %s", cmd_str)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip()
            logging.error("SSH destination test failed (exit %s): %s", proc.returncode, detail)
            return False, detail
    except Exception as exc:
        detail = str(exc)
        logging.error("SSH destination test failed: %s", detail)
        return False, detail
    return True, ""


def test_ssh_write_access(server, user, dest_dir, passwd, use_pubkey):
    """Test that the transfer can create and delete a file in a directory on an SSH server.

    Args:
        server: SSH server hostname or address.
        user: SSH username.
        dest_dir: Absolute path of the directory on the server.
        passwd: SSH password; ignored when *use_pubkey* is true.
        use_pubkey: Authenticate with the local user's SSH key instead of a
            password.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with the error output.
    """

    passwd = passwd or ''
    cmd = build_ssh_command(None, user, server, f"touch {os.path.join(dest_dir, 'writeTest.txt')}", passwd, use_pubkey)

    cmd_str = ' '.join(cmd)
    if passwd and len(passwd) > 0:
        cmd_str = cmd_str.replace(f'{passwd}', '****')

    logging.debug("test_ssh_write_access cmd: %s", cmd_str)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip()
            logging.error("SSH write test failed (exit %s): %s", proc.returncode, detail)
            return False, detail
    except Exception as exc:
        detail = str(exc)
        logging.error("SSH write test failed: %s", detail)
        return False, detail

    cmd = build_ssh_command(None, user, server, f"rm {os.path.join(dest_dir, 'writeTest.txt')}", passwd, use_pubkey)

    cmd_str = ' '.join(cmd)
    if passwd and len(passwd) > 0:
        cmd_str = cmd_str.replace(f'{passwd}', '****')

    logging.debug("test_ssh_write_access cmd: %s", cmd_str)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip()
            logging.error("SSH write test cleanup failed (exit %s): %s", proc.returncode, detail)
            return False, detail
    except Exception as exc:
        detail = str(exc)
        logging.error("SSH write test failed: %s", detail)
        return False, detail

    return True, ""


def build_rclone_config_for_ssh(cfg, rclone_config):
    """Write an rclone SFTP remote for a transfer's SSH server to a config file.

    The remote authenticates with the transfer's password (obscured with
    ``rclone obscure``) or, when ``sshUseKey`` is set, with the ``IdentityFile``
    configured for the host in ``~/.ssh/config`` (default ``~/.ssh/id_rsa``).

    Args:
        cfg: Transfer configuration with ``sshServer``, ``sshUser``,
            ``sshUseKey`` and ``sshPass``.
        rclone_config: Path of the rclone config file to write.

    Returns:
        The remote's name: the SSH server with ``.`` replaced by ``_``.

    Raises:
        subprocess.CalledProcessError: If ``rclone obscure`` fails.
    """
    cfg = normalize_transfer_config(cfg)
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    identity_file = os.path.expanduser("~/.ssh/id_rsa")
    target_host = cfg["sshServer"]
    rclone_remote = target_host.replace('.','_')

    if os.path.exists(ssh_config_path):
        with open(ssh_config_path) as f:
            found_host = False
            for line in f:
                line = line.strip()
                if line.startswith("Host "):
                    hosts = line.split()[1:]
                    found_host = target_host in hosts
                elif found_host and line.startswith("IdentityFile"):
                    identity_file = line.split(maxsplit=1)[1]
                    break

    # Build rclone config section
    out = configparser.ConfigParser()
    out[rclone_remote] = {
        "type": "sftp",
        "host": target_host,
        "user": cfg["sshUser"]
    }

    # If password provided, obscure it; otherwise use key file
    if cfg["sshUseKey"] == 0:
        try:
            result = subprocess.run(
                ["rclone", "obscure", cfg["sshPass"]],
                capture_output=True,
                text=True,
                check=True,
            )
            obscured_pass = result.stdout.strip()
            out[rclone_remote]["pass"] = obscured_pass
        except subprocess.CalledProcessError as e:
            logging.error("Failed to obscure password with rclone: %s", e)
            raise
    else:
        out[rclone_remote]["key_file"] = identity_file

    # Print for debugging
    logging.debug(f"[{rclone_remote}]")
    for k, v in out[rclone_remote].items():
        logging.debug(f"{k} = {v}")

    # Write config, overwriting existing file
    with open(rclone_config, "w") as f:
        out.write(f)

    return rclone_remote


# Keep connection tests quick when a server can't be reached; by default rclone
# retries for minutes.
RCLONE_TEST_FLAGS = ['--contimeout', '15s', '--timeout', '30s',
                     '--retries', '1', '--low-level-retries', '1']

FTP_REMOTE = 'ftp_source'

# How long mount_ftp_source() waits for the mount to appear
FTP_MOUNT_TIMEOUT = 30


def rclone_error(stderr: str) -> str:
    """Return rclone's last error line, without its timestamp/level prefix.

    Args:
        stderr: rclone's error output.

    Returns:
        The last non-empty line, or a placeholder if there is none.
    """
    lines = [line.strip() for line in (stderr or '').splitlines() if line.strip()]
    if not lines:
        return 'rclone failed with no error message'
    # Fatal errors ("Failed to ...") have a timestamp but no level
    return re.sub(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\s+(?:[A-Z]+\s*:\s*)?', '', lines[-1])


def build_rclone_config_for_ftp(cfg: dict, rclone_config: str) -> str:
    """Write an rclone FTP remote for a transfer's FTP server to a config file.

    The password is obscured with ``rclone obscure``, reading it from stdin so
    it doesn't appear in the process list. Anonymous access without a
    password uses the conventional password ``anonymous``.

    Args:
        cfg: Transfer configuration with ``ftpServer``, ``ftpPort``,
            ``ftpUser`` and ``ftpPass``.
        rclone_config: Path of the rclone config file to write.

    Returns:
        The remote's name, :data:`FTP_REMOTE`.

    Raises:
        subprocess.CalledProcessError: If ``rclone obscure`` fails.
    """
    cfg = normalize_transfer_config(cfg)

    out = configparser.ConfigParser()
    out[FTP_REMOTE] = {
        "type": "ftp",
        "host": cfg["ftpServer"],
        "port": str(cfg.get("ftpPort") or 21),
        "user": cfg.get("ftpUser") or "anonymous",
    }

    password = cfg.get("ftpPass") or ("anonymous" if out[FTP_REMOTE]["user"] == "anonymous" else "")
    if password:
        result = subprocess.run(["rclone", "obscure", "-"], input=password,
                                capture_output=True, text=True, check=True)
        out[FTP_REMOTE]["pass"] = result.stdout.strip()

    with open(rclone_config, "w", encoding="utf-8") as f:
        out.write(f)
    os.chmod(rclone_config, 0o600)

    return FTP_REMOTE


def test_ftp_connection(rclone_config: str, remote: str) -> tuple:
    """Test logging in to an FTP server by listing its root directory.

    Args:
        rclone_config: rclone config file, from :func:`build_rclone_config_for_ftp`.
        remote: Name of the FTP remote in *rclone_config*.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with rclone's error.
    """
    cmd = ['rclone', 'lsf', f'{remote}:/', '--config', rclone_config,
           '--max-depth', '1'] + RCLONE_TEST_FLAGS
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        return False, _ftp_rclone_error(exc.stderr)
    except FileNotFoundError:
        return False, 'rclone is not installed'


def _ftp_rclone_error(stderr: str) -> str:
    """Return rclone's error for an FTP remote, without the internal remote name.

    Drops the ``Failed to create file system for "ftp_source:/": `` prefix,
    which only names :data:`FTP_REMOTE`.
    """
    return re.sub(r'^Failed to create file system for "[^"]*": (NewFs: )?', '',
                  rclone_error(stderr))


def _rfc3339_to_epoch(value: str) -> float:
    """Convert an rclone ``ModTime`` (RFC 3339, up to nanoseconds) to seconds since the epoch.

    Args:
        value: e.g. ``2019-08-11T19:03:35Z`` or ``2019-08-11T19:03:35.123456789-04:00``.

    Returns:
        The time as a Unix timestamp.

    Raises:
        ValueError: If *value* isn't in that format.
    """
    match = re.match(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$', value)
    if not match:
        raise ValueError(f"Unrecognized time: {value}")
    base, fraction, zone = match.groups()
    seconds = calendar.timegm(datetime.strptime(base, '%Y-%m-%dT%H:%M:%S').timetuple())
    if fraction:
        seconds += float(f"0.{fraction}")
    if zone != 'Z':
        sign = 1 if zone[0] == '+' else -1
        seconds -= sign * (int(zone[1:3]) * 3600 + int(zone[4:6]) * 60)
    return seconds


def list_ftp_source(rclone_config: str, remote: str, source_dir: str) -> tuple:
    """List every file under an FTP source directory with one ``rclone lsjson -R``.

    Listing through the rclone mount would ``stat`` each file over FTP, and
    shows a subdirectory the server refuses to list as empty. ``lsjson``
    lists each directory once and fails on such errors, so a listing that
    can't be trusted fails the transfer instead of looking like missing files
    (#206, #208).

    Args:
        rclone_config: rclone config file, from :func:`build_rclone_config_for_ftp`.
        remote: Name of the FTP remote in *rclone_config*.
        source_dir: Directory on the FTP server to list, e.g. ``/data``.

    Returns:
        tuple[bool, list | str]: ``(True, files)`` with ``(path, size, mtime)``
        tuples (*path* relative to *source_dir*, *mtime* in seconds since the
        epoch), or ``(False, detail)`` with rclone's error.
    """
    cmd = ['rclone', 'lsjson', '-R', '--files-only', '--no-mimetype', '--config', rclone_config,
           f"{remote}:{source_dir}", '--contimeout', '15s', '--timeout', '30s']
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        return False, 'rclone is not installed'
    except subprocess.CalledProcessError as exc:
        return False, _ftp_rclone_error(exc.stderr)

    try:
        return True, [(entry['Path'], int(entry['Size']), _rfc3339_to_epoch(entry['ModTime']))
                      for entry in json.loads(proc.stdout)]
    except (ValueError, KeyError, TypeError) as exc:
        return False, f"Unreadable rclone lsjson output: {exc}"


def mount_ftp_source(cfg: dict, mntpoint: str, rclone_config: str) -> tuple:
    """Mount a transfer's FTP server on a local directory with ``rclone mount``.

    The server's root is mounted read-write if the transfer removes source
    files (``removeSourceFiles``), otherwise read-only, so ``sourceDir`` is a
    path within the mount, as for SMB shares. The files to copy are listed
    with :func:`list_ftp_source`, not through the mount, so rclone's default
    directory cache is fine. :func:`~server.lib.file_utils.temporary_directory`
    unmounts it. Requires
    FUSE (``fuse3``) and root.

    Success means *mntpoint* is actually mounted: rclone versions without
    ``--daemon-wait`` (e.g. 1.53 on Ubuntu 22.04) return before the mount is
    ready, and walking an unmounted directory would look like an empty
    source (#206).

    Args:
        cfg: Transfer configuration.
        mntpoint: Existing local directory to mount the server on.
        rclone_config: rclone config file, from :func:`build_rclone_config_for_ftp`.

    Returns:
        tuple[bool, str]: ``(True, "")`` on success, or ``(False, detail)``
        with rclone's error.
    """
    cfg = normalize_transfer_config(cfg)
    log_file = os.path.join(os.path.dirname(rclone_config), 'rclone_mount.log')

    cmd = ['rclone', 'mount', f'{FTP_REMOTE}:/', mntpoint, '--config', rclone_config,
           '--daemon', '--contimeout', '15s', '--timeout', '30s',
           '--log-level', 'ERROR', '--log-file', log_file]
    if cfg.get('removeSourceFiles', 0) != 1:
        cmd.append('--read-only')

    logging.debug("mount_ftp_source cmd: %s", ' '.join(cmd))
    # The daemonized rclone inherits stdout/stderr and keeps them open while
    # mounted, so they go to the log file: waiting on a pipe would never end.
    try:
        with open(log_file, 'a', encoding='utf-8') as log:
            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, check=True)
    except FileNotFoundError:
        return False, 'rclone is not installed'
    except subprocess.CalledProcessError:
        with open(log_file, encoding='utf-8') as f:
            detail = rclone_error(f.read())
        logging.error("Failed to mount FTP server: %s", detail)
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
        return False, detail

    deadline = time.monotonic() + FTP_MOUNT_TIMEOUT
    while not os.path.ismount(mntpoint):
        if time.monotonic() > deadline:
            with open(log_file, encoding='utf-8') as f:
                log_text = f.read()
            detail = (rclone_error(log_text) if log_text.strip()
                      else f"not mounted after {FTP_MOUNT_TIMEOUT} s")
            logging.error("FTP server mount not ready: %s", detail)
            # rclone may still be trying: stop it so it can't mount later
            subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
            subprocess.run(['pkill', '-f', f'rclone mount {FTP_REMOTE}:/ {mntpoint}'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return False, detail
        time.sleep(0.2)

    logging.info("Mounted FTP server %s on %s", cfg['ftpServer'], mntpoint)
    return True, ""


def build_rclone_options(cfg, mode='dry-run'):
    """Return the rclone subcommand and options for a cruise data transfer.

    Uses ``sync`` if the transfer mirrors deletions (``syncToDest``), otherwise
    ``copy``. Adds ``--create-empty-src-dirs`` unless ``skipEmptyDirs`` is set,
    ``--dry-run`` in dry-run mode, ``--bwlimit`` for a bandwidth limit, and the
    Google Cloud Storage options when the destination remote is a GCS bucket.

    Args:
        cfg: Cruise data transfer configuration.
        mode: ``'dry-run'`` to only list what would be transferred; any other
            value for a real transfer.

    Returns:
        tuple[str, list[str]]: ``('copy' | 'sync', flags)``.
    """

    cfg = normalize_transfer_config(cfg)
    if ':' in cfg['destDir']:
        remote_name, _ = cfg['destDir'].split(':',1)
        remote_type = get_rclone_remote_type(remote_name)
    else:
        remote_type = 'local'

    flags = ["--progress"]
    copy_sync = "sync" if cfg.get('syncToDest', 0) == 1 else "copy"

    if cfg.get('skipEmptyDirs') == 0:
        flags.append('--create-empty-src-dirs')

    if mode == 'dry-run':
        flags.append('--dry-run')

    if remote_type == 'google cloud storage':
        flags.extend(["--gcs-bucket-policy-only", "--local-no-set-modtime"])

    if cfg.get('bandwidthLimit') not in (None, 0):
        flags.extend(["--bwlimit", f"{cfg['bandwidthLimit']}k" ])

    return copy_sync, flags


def build_rsync_options(cfg, mode='dry-run', is_darwin=False):
    """Return the rsync options for a transfer.

    Dry runs use ``-trinv --dry-run --stats``; real transfers use ``-triv
    --progress`` plus ``--bwlimit``, ``--remove-source-files`` and ``--delete``
    as configured (and ``--no-motd`` for rsync servers). Both add
    ``--min-size=1`` (``skipEmptyFiles``), ``-m`` (``skipEmptyDirs``), and
    ``--protect-args`` unless the other end is macOS.

    Args:
        cfg: Collection system or cruise data transfer configuration.
        mode: ``'dry-run'`` to only list what would be transferred; any other
            value for a real transfer.
        is_darwin: The remote end runs macOS, whose rsync doesn't support
            ``--protect-args`` (see :func:`check_darwin`).

    Returns:
        list[str]: The rsync options.
    """

    cfg = normalize_transfer_config(cfg)
    transfer_type = get_transfer_type(cfg['transferType'])

    flags = ['-trinv'] if mode == 'dry-run' else ['-triv', '--progress']

    if not is_darwin:
        flags.insert(1, '--protect-args')

    if cfg.get('skipEmptyFiles', 0) == 1:
        flags.insert(1, '--min-size=1')

    if cfg.get('skipEmptyDirs', 0) == 1:
        flags.insert(1, '-m')

    if mode == 'dry-run':
        flags.append('--dry-run')
        flags.append('--stats')

    else:
        if transfer_type == 'rsync':
            flags.append('--no-motd')

        if cfg.get('bandwidthLimit') not in (None, 0):
            flags.insert(1, f"--bwlimit={cfg['bandwidthLimit']}")

        # Logic handles if cfg is a cst or cdt
        if cfg.get('removeSourceFiles', 0) == 1:
            flags.insert(2, '--remove-source-files')

        # Logic handles if cfg is a cst or cdt
        if cfg.get('syncToDest', 0) == 1:
            flags.insert(2, '--delete')

    return flags


def test_local_destination(dest_dir, is_mountpoint=0):
    """Test a local destination directory for a cruise data transfer.

    Checks that the directory exists, optionally that its top-level mount point
    (the first two path components, e.g. ``/mnt/usb``) is mounted, and that it's
    writable.

    Args:
        dest_dir: Absolute path of the destination directory.
        is_mountpoint: ``1`` if the directory must be on a mounted filesystem.

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """
    results = []

    dest_dir_exists = os.path.isdir(dest_dir)

    if not dest_dir_exists:
        reason = f"Unable to find destination directory: {dest_dir} on the data warehouse"
        results.extend([{"partName": "Destination directory", "result": "Fail", "reason": reason}])

        if is_mountpoint == 1:
            results.extend([{"partName": "Destination directory is a mount point", "result": "Fail", "reason": reason}])

        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

        return results

    results.extend([{"partName": "Destination directory", "result": "Pass"}])

    if is_mountpoint == 1:
        mnt_dir = os.sep + os.path.join(*dest_dir.strip(os.sep).split(os.sep)[:2])
        if not os.path.ismount(mnt_dir):
            reason = f"{mnt_dir} is not a mount point on the data warehouse"
            results.extend([{
                "partName": "Destination directory is a mount point",
                "result": "Fail",
                "reason": reason
            }])
            results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

            return results

        results.extend([{"partName": "Destination directory is a mount point", "result": "Pass"}])

    if not test_write_access(dest_dir):
        reason = f"Unable to write to destination directory: {dest_dir}"
        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

        return results

    results.extend([{"partName": "Write test", "result": "Pass"}])
    return results


def test_smb_destination(cdt_cfg, mntpoint, smb_version, smb_detail=""):
    """Test an SMB share destination for a cruise data transfer.

    Reports the SMB server check, mounts the share at *mntpoint*, then runs
    :func:`test_local_destination` on the destination directory within it. The
    caller is responsible for unmounting the share.

    Args:
        cdt_cfg: Cruise data transfer configuration (SMB server, share,
            credentials and ``destDir``).
        mntpoint: Local directory to mount the share on.
        smb_version: Detected SMB protocol version, or empty if detection
            failed.
        smb_detail: Error detail from SMB version detection, used as the
            failure reason.

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """
    results = []

    if not smb_version:
        reason = f"Could not connect to SMB server: {cdt_cfg['smbServer']} as {cdt_cfg['smbUser']}"
        if smb_detail:
            reason += f" — {smb_detail}"
        logging.error(reason)
        results.extend([
            {"partName": "SMB server", "result": "Fail", "reason": reason},
            {"partName": "SMB share", "result": "Fail", "reason": reason},
            {"partName": "Destination directory", "result": "Fail", "reason": reason},
            {"partName": "Write test", "result": "Fail", "reason": reason}
        ])

        return results

    results.extend([{"partName": "SMB server", "result": "Pass"}])

    mnt_success, mnt_detail = mount_smb_share(cdt_cfg, mntpoint, smb_version)
    if not mnt_success:
        reason = f"Could not connect to SMB share: {cdt_cfg['smbServer']} as {cdt_cfg['smbUser']}"
        if mnt_detail:
            reason += f" — {mnt_detail}"
        logging.error(reason)
        results.extend([
            {"partName": "SMB share", "result": "Fail", "reason": reason},
            {"partName": "Destination directory", "result": "Fail", "reason": reason},
            {"partName": "Write test", "result": "Fail", "reason": reason}
        ])

        return results

    results.extend([{"partName": "SMB share", "result": "Pass"}])

    smb_dest_dir = os.path.join(mntpoint, cdt_cfg['destDir'].lstrip('/'))
    results.extend(test_local_destination(smb_dest_dir))

    return results


def _test_mounted_source(mntpoint: str, source_dir: str, remove_source_files: bool,
                         location: str) -> list:
    """Check a source directory on a mounted SMB share or FTP server.

    Checks that the source directory exists (for a wildcard source, that its
    parent exists and at least one directory matches) and, if the transfer
    removes source files, that the directory is writable.

    Args:
        mntpoint: Where the share or server is mounted.
        source_dir: Source directory within the mount; may end in a wildcard.
        remove_source_files: Whether the transfer deletes source files.
        location: Where the source is, for failure reasons (e.g. ``'SMB share'``).

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """
    results = []

    if has_wildcard(source_dir):
        wildcard_parent = os.path.dirname(source_dir)
        wildcard_pattern = os.path.basename(source_dir)
        mnt_parent = os.path.join(mntpoint, wildcard_parent.lstrip('/'))
        if not os.path.isdir(mnt_parent):
            reason = f"Unable to find parent directory: {wildcard_parent} on {location}"
            results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])
            if remove_source_files:
                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
            return results
        matches = sorted([d for d in glob.glob(os.path.join(mnt_parent, wildcard_pattern)) if os.path.isdir(d)])
        if not matches:
            reason = f"No directories matching wildcard pattern: {source_dir} on {location}"
            results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])
            if remove_source_files:
                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
            return results
        results.extend([{"partName": "Source directory", "result": "Pass"}])
        if remove_source_files:
            if not test_write_access(matches[0]):
                reason = f"Unable to delete source files from: {matches[0]} on {location}"
                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
                return results
            results.extend([{"partName": "Write test", "result": "Pass"}])
        return results

    mnt_source_dir = os.path.join(mntpoint, source_dir.lstrip('/'))
    if not os.path.isdir(mnt_source_dir):
        reason = f"Unable to find source directory: {source_dir} on {location}"
        results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])

        if remove_source_files:
            results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

        return results

    results.extend([{"partName": "Source directory", "result": "Pass"}])

    if remove_source_files:
        if not test_write_access(mnt_source_dir):
            reason = f"Unable to delete source files from: {source_dir} on {location}"
            results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

            return results

        results.extend([{"partName": "Write test", "result": "Pass"}])

    return results


def test_cst_source(cst_cfg, source_dir):
    """Test a collection system transfer's source.

    Checks the transfer type, then, depending on it, the SMB server and share,
    rsync, SSH or FTP connection (and FTP mount), the source directory (and, if required, that it's
    a mount point), and write access when the transfer removes source files.

    Args:
        cst_cfg: Collection system transfer configuration.
        source_dir: The source directory to test (with any cruise/lowering
            substitutions already applied).

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """

    cst_cfg = normalize_transfer_config(cst_cfg)

    results = []

    mntpoint = None
    smb_version = None
    transfer_type = get_transfer_type(cst_cfg['transferType'])

    if not transfer_type:
        results.extend([{"partName": "Transfer type", "result": "Fail", "reason": "Unknown transfer type"}])
        return results

    source_has_wildcard = has_wildcard(source_dir)
    wildcard_parent = os.path.dirname(source_dir) if source_has_wildcard else None
    wildcard_pattern = os.path.basename(source_dir) if source_has_wildcard else None

    with temporary_directory() as tmpdir:
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Tests for local
        if transfer_type == 'local':
            if source_has_wildcard:
                if not os.path.isdir(wildcard_parent):
                    reason = f"Unable to find parent directory: {wildcard_parent} on the data warehouse"
                    results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])
                    if cst_cfg['localDirIsMountPoint'] == 1:
                        results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": reason}])
                    if cst_cfg['removeSourceFiles'] == 1:
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
                    return results
                matches = sorted([d for d in glob.glob(os.path.join(wildcard_parent, wildcard_pattern)) if os.path.isdir(d)])
                if not matches:
                    reason = f"No directories matching wildcard pattern: {source_dir}"
                    results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])
                    if cst_cfg['removeSourceFiles'] == 1:
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
                    return results
                results.extend([{"partName": "Source directory", "result": "Pass"}])
                if cst_cfg['localDirIsMountPoint'] == 1:
                    mnt_dir = os.sep + os.path.join(*matches[0].strip(os.sep).split(os.sep)[:2])
                    if not os.path.ismount(mnt_dir):
                        reason = f"{mnt_dir} is not a mount point on the data warehouse"
                        results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": reason}])
                        if cst_cfg['removeSourceFiles'] == 1:
                            results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
                        return results
                    results.extend([{"partName": "Source directory is a mount point", "result": "Pass"}])
                if cst_cfg['removeSourceFiles'] == 1:
                    if not test_write_access(matches[0]):
                        reason = f"Unable to delete source files from: {matches[0]} on the data warehouse"
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])
                        return results
                    results.extend([{"partName": "Write test", "result": "Pass"}])
            else:
                source_dir_exists = os.path.isdir(source_dir)
                if not source_dir_exists:
                    reason = f"Unable to find source directory: {source_dir} on the data warehouse"
                    results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])

                    if cst_cfg['localDirIsMountPoint'] == 1:
                        results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": reason}])

                    if cst_cfg['removeSourceFiles'] == 1:
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Source directory", "result": "Pass"}])

                if cst_cfg['localDirIsMountPoint'] == 1:
                    mnt_dir = os.sep + os.path.join(*source_dir.strip(os.sep).split(os.sep)[:2])
                    if not os.path.ismount(mnt_dir):
                        results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": f"{mnt_dir} is not a mount point on the data warehouse"}])

                        if cst_cfg['removeSourceFiles'] == 1:
                            results.extend([{"partName": "Write test", "result": "Fail", "reason": f"{mnt_dir} is not a mount point on the data warehouse"}])

                        return results

                    results.extend([{"partName": "Source directory is a mount point", "result": "Pass"}])

                if cst_cfg['removeSourceFiles'] == 1:
                    if not test_write_access(source_dir):
                        reason = f"Unable to delete source files from: {source_dir} on the data warehouse"
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                        return results

                    results.extend([{"partName": "Write test", "result": "Pass"}])

        # Tests for smb
        if transfer_type == 'smb':

            if cst_cfg.get('smbUser') != 'guest' and cst_cfg.get('smbPass') is None:
                reason = ("smbPass not available — worker API token may be misconfigured "
                          "or the password is not set for this transfer")
                results.extend([
                    {"partName": "SMB server", "result": "Fail", "reason": reason},
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])
                return results

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version, smb_detail = detect_smb_version(cst_cfg)

            if not smb_version:
                reason = f"Could not connect to SMB server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                if smb_detail:
                    reason += f" — {smb_detail}"
                results.extend([
                    {"partName": "SMB server", "result": "Fail", "reason": reason},
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == 1:
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB server", "result": "Pass"}])

            mnt_success, mnt_detail = mount_smb_share(cst_cfg, mntpoint, smb_version)
            if not mnt_success:
                reason = f"Could not connect to SMB server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                if mnt_detail:
                    reason += f" — {mnt_detail}"
                results.extend([
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == 1:
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB share", "result": "Pass"}])

            results.extend(_test_mounted_source(mntpoint, source_dir,
                                                cst_cfg['removeSourceFiles'] == 1, 'SMB share'))

        # Tests for FTP
        if transfer_type == 'ftp':

            if cst_cfg.get('ftpUser') != 'anonymous' and cst_cfg.get('ftpPass') is None:
                reason = ("ftpPass not available — worker API token may be misconfigured "
                          "or the password is not set for this transfer")
                results.extend([
                    {"partName": "FTP server", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])
                return results

            server = f"{cst_cfg['ftpServer']}:{cst_cfg.get('ftpPort') or 21}"
            rclone_config = os.path.join(tmpdir, 'rclone.conf')
            try:
                remote = build_rclone_config_for_ftp(cst_cfg, rclone_config)
                contest_success, contest_detail = test_ftp_connection(rclone_config, remote)
            except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
                contest_success, contest_detail = False, f"Unable to write rclone config: {exc}"

            if not contest_success:
                reason = f"Could not connect to FTP server: {server} as {cst_cfg['ftpUser']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "FTP server", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == 1:
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "FTP server", "result": "Pass"}])

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            mnt_success, mnt_detail = mount_ftp_source(cst_cfg, mntpoint, rclone_config)
            if not mnt_success:
                reason = f"Could not mount FTP server: {server}"
                if mnt_detail:
                    reason += f" — {mnt_detail}"
                results.extend([
                    {"partName": "Mount FTP server", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == 1:
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Mount FTP server", "result": "Pass"}])

            results.extend(_test_mounted_source(mntpoint, source_dir,
                                                cst_cfg['removeSourceFiles'] == 1, 'FTP server'))

        # Tests for rsync
        if transfer_type == 'rsync':
            if cst_cfg['rsyncUser'] != 'anonymous':
                rsync_pass = cst_cfg.get('rsyncPass')
                if rsync_pass is None:
                    reason = ("rsyncPass not available — worker API token may be misconfigured "
                              "or the password is not set for this transfer")
                    results.extend([
                        {"partName": "Writing temporary rsync password file", "result": "Fail", "reason": reason},
                        {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                        {"partName": "Source directory", "result": "Fail", "reason": reason}
                    ])
                    return results
                # Build password file
                try:
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(rsync_pass)
                    os.chmod(password_file, 0o600)
                except IOError:
                    reason = f"Unable to create temporary rsync password file: {password_file}"
                    results.extend([
                        {"partName": "Writing temporary rsync password file", "result": "Fail", "reason": reason},
                        {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                        {"partName": "Source directory", "result": "Fail", "reason": reason}
                    ])

                    return results
            else:
                password_file = None

            contest_success, contest_detail = test_rsync_connection(cst_cfg['rsyncServer'], cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Could not connect to rsync server: {cst_cfg['rsyncServer']} as {cst_cfg['rsyncUser']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])
                return results

            results.append({"partName": "Rsync connection", "result": "Pass"})

            check_dir = wildcard_parent if source_has_wildcard else source_dir
            contest_success, contest_detail = test_rsync_connection(f"{cst_cfg['rsyncServer']}{check_dir}", cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                if source_has_wildcard:
                    reason = f"Unable to find parent directory: {wildcard_parent} on the Rsync Server: {cst_cfg['rsyncServer']}"
                else:
                    reason = f"Unable to find source directory: {source_dir} on the Rsync Server: {cst_cfg['rsyncServer']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Source directory", "result": "Pass"})

        # Tests for SSH
        if transfer_type == 'ssh':

            use_pubkey = cst_cfg['sshUseKey'] == 1
            ssh_pass = cst_cfg.get('sshPass')
            if not use_pubkey and ssh_pass is None:
                reason = ("sshPass not available — worker API token may be misconfigured "
                          "or the password is not set for this transfer")
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])
                return results

            contest_success, contest_detail = test_ssh_connection(cst_cfg['sshServer'], cst_cfg['sshUser'], passwd=ssh_pass, use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to connect to SSH server: {cst_cfg['sshServer']} as {cst_cfg['sshUser']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SSH connection", "result": "Pass"}])

            check_dir = wildcard_parent if source_has_wildcard else source_dir
            contest_success, contest_detail = test_ssh_remote_directory(cst_cfg['sshServer'], cst_cfg['sshUser'], check_dir, passwd=ssh_pass, use_pubkey=use_pubkey)

            if not contest_success:
                if source_has_wildcard:
                    reason = f"Unable to find parent directory: {wildcard_parent}"
                else:
                    reason = f"Unable to find source directory: {source_dir}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Source directory", "result": "Pass"}])

        return results

def test_cdt_destination(cdt_cfg):
    """Test a cruise data transfer's destination.

    Checks, depending on the transfer type, the local directory (or rclone
    remote), rsync server, SMB share or SSH server, the destination directory,
    and write access.

    Args:
        cdt_cfg: Cruise data transfer configuration.

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """

    cdt_cfg = normalize_transfer_config(cdt_cfg)

    results = []

    mntpoint = None
    smb_version = None
    transfer_type = get_transfer_type(cdt_cfg['transferType'])

    if not transfer_type:
        logging.error("Unknown transfer type")
        results.extend([{"partName": "Transfer type", "result": "Fail", "reason": "Unknown transfer type"}])
        return results

    with temporary_directory() as tmpdir:
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Tests for local
        if transfer_type == 'local':
            results.extend(test_local_destination(cdt_cfg['destDir'], cdt_cfg['localDirIsMountPoint']))

            if results[-1].get('result') == 'Fail':
                return results

        # Tests for smb
        if transfer_type == 'smb':

            if cdt_cfg.get('smbUser') != 'guest' and cdt_cfg.get('smbPass') is None:
                reason = ("smbPass not available — worker API token may be misconfigured "
                          "or the password is not set for this transfer")
                results.extend([
                    {"partName": "SMB server", "result": "Fail", "reason": reason},
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])
                return results

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version, smb_detail = detect_smb_version(cdt_cfg)

            results.extend(test_smb_destination(cdt_cfg, mntpoint, smb_version, smb_detail))
            if results[-1].get('result') == 'Fail':
                return results

        # Tests for rsync
        if transfer_type == 'rsync':
            if cdt_cfg['rsyncUser'] != 'anonymous':
                rsync_pass = cdt_cfg.get('rsyncPass')
                if rsync_pass is None:
                    reason = ("rsyncPass not available — worker API token may be misconfigured "
                              "or the password is not set for this transfer")
                    results.extend([
                        {"partName": "Writing temporary rsync password file", "result": "Fail", "reason": reason},
                        {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                        {"partName": "Destination directory", "result": "Fail", "reason": reason}
                    ])
                    return results
                # Build password file
                try:
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(rsync_pass)
                    os.chmod(password_file, 0o600)
                except IOError:
                    reason = f"Unable to create temporary rsync password file: {password_file}"
                    results.extend([
                        {"partName": "Writing temporary rsync password file", "result": "Fail", "reason": reason},
                        {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                        {"partName": "Destination directory", "result": "Fail", "reason": reason}
                    ])

                    return results
            else:
                password_file = None

            contest_success, contest_detail = test_rsync_connection(cdt_cfg['rsyncServer'], cdt_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Could not connect to rsync server: {cdt_cfg['rsyncServer']} as {cdt_cfg['rsyncUser']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason}
                ])
                return results

            results.append({"partName": "Rsync connection", "result": "Pass"})

            contest_success, contest_detail = test_rsync_connection(f"{cdt_cfg['rsyncServer']}{cdt_cfg['destDir']}", cdt_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Unable to find destination directory: {cdt_cfg['destDir']} on the Rsync Server: {cdt_cfg['rsyncServer']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Destination directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Destination directory", "result": "Pass"})

            contest_success, contest_detail = test_rsync_write_access(f"{cdt_cfg['rsyncServer']}{cdt_cfg['destDir']}", cdt_cfg['rsyncUser'], tmpdir, password_file)
            if not contest_success:
                reason = f"Unable to write to: {cdt_cfg['destDir']} on the Rsync Server: {cdt_cfg['rsyncServer']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Write test", "result": "Pass"})

        # Tests for SSH
        if transfer_type == 'ssh':

            use_pubkey = cdt_cfg['sshUseKey'] == 1
            ssh_pass = cdt_cfg.get('sshPass')
            if not use_pubkey and ssh_pass is None:
                reason = ("sshPass not available — worker API token may be misconfigured "
                          "or the password is not set for this transfer")
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])
                return results

            contest_success, contest_detail = test_ssh_connection(cdt_cfg['sshServer'], cdt_cfg['sshUser'], passwd=ssh_pass, use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to connect to SSH server: {cdt_cfg['sshServer']} as {cdt_cfg['sshUser']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SSH connection", "result": "Pass"}])

            contest_success, contest_detail = test_ssh_remote_directory(cdt_cfg['sshServer'], cdt_cfg['sshUser'], cdt_cfg['destDir'], passwd=ssh_pass, use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to find destination directory: {cdt_cfg['destDir']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Destination directory", "result": "Pass"}])

            contest_success, contest_detail = test_ssh_write_access(cdt_cfg['sshServer'], cdt_cfg['sshUser'], cdt_cfg['destDir'], passwd=ssh_pass, use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"No write access on ssh server: {cdt_cfg['sshServer']} as {cdt_cfg['sshUser']} at {cdt_cfg['destDir']}"
                if contest_detail:
                    reason += f" — {contest_detail}"
                results.extend([
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Write test", "result": "Pass"}])

        return results

def test_cdt_rclone_destination(cfg):
    """Test an rclone destination for a cruise data transfer.

    ``destDir`` is either a local path or an rclone ``remote:path``. Local
    directories and SMB shares get their own tests. Any other rclone remote
    (SFTP, FTP, S3, Google Cloud Storage, Google Drive, WebDAV, ...) is tested
    with rclone itself: for bucket-based remotes (S3, GCS, B2, Azure Blob, ...)
    that the bucket exists, otherwise that the destination directory exists,
    then that a test file can be written and deleted. Failures include
    rclone's error message.

    Args:
        cfg: Cruise data transfer configuration.

    Returns:
        list[dict]: Test parts with ``partName``/``result``/``reason`` keys.
    """

    def _run_rclone(args):
        """Run ``rclone <args>``; return ``(True, stdout)`` or ``(False, error)``."""
        try:
            proc = subprocess.run(['rclone'] + args + RCLONE_TEST_FLAGS,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=True, text=True)
            return True, proc.stdout
        except subprocess.CalledProcessError as exc:
            return False, rclone_error(exc.stderr)
        except FileNotFoundError:
            return False, 'rclone is not installed'

    def _remote_features(remote_name):
        """Return ``(True, features)`` for the remote, or ``(False, error)`` if rclone can't open it."""
        success, output = _run_rclone(['backend', 'features', f'{remote_name}:'])
        if not success:
            return False, output
        try:
            return True, json.loads(output).get('Features', {})
        except ValueError:
            return True, {}

    def _verify_write_access(remote_path, gcs=False):
        """Copy a small file to ``remote_path`` and delete it; return ``(ok, error)``."""
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(b"rclone write test")
        temp_file.close()

        # Create a unique name to avoid conflicts
        remote_test_path = f"{remote_path.rstrip('/')}/.rclone-write-test-{uuid.uuid4().hex}.txt"
        cmd = ["copyto", temp_file.name, remote_test_path]

        if gcs:
            cmd += ["--gcs-bucket-policy-only", "--local-no-set-modtime"]

        try:
            success, detail = _run_rclone(cmd)
            if not success:
                return False, detail
            return _run_rclone(["deletefile", remote_test_path])
        finally:
            os.remove(temp_file.name)

    results = []
    if ':' not in cfg['destDir']:
        remote_name = None
        remote_path = cfg['destDir']
        remote_type = get_transfer_type(cfg['transferType'])
    else:
        remote_name, remote_path = cfg['destDir'].split(':', 1)
        remote_type = get_rclone_remote_type(remote_name)

        if remote_type is None:
            reason = "rclone remote does not exist or rclone config file not found"
            results.extend([
                {"partName": "Rclone remote config", "result": "Fail", "reason": reason}
            ])

            return results

        results.append({"partName": "Rclone remote config", "result": "Pass"})

    if remote_type == 'local':
        results.extend(test_local_destination(remote_path, cfg.get('localDirIsMountPoint', 0)))
        return results

    if remote_type == 'smb':
        with temporary_directory() as tmpdir:
            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version, smb_detail = detect_smb_version(cfg)

            results.extend(test_smb_destination(cfg, mntpoint, smb_version, smb_detail))
        return results

    if remote_name is None:
        return results

    # Any other rclone remote. Opening it also connects to it, so a remote
    # that can't be reached fails here rather than timing out again below.
    is_gcs = remote_type == 'google cloud storage'
    success, features = _remote_features(remote_name)
    if not success:
        # Label it as the check that would have run: bucket or directory
        if is_gcs:
            part_name = "Verify GCS bucket"
        elif remote_type in ('s3', 'b2', 'azureblob', 'swift', 'oracleobjectstorage', 'qingstor'):
            part_name = "Verify bucket"
        else:
            part_name = "Destination directory"
        reason = f"Unable to connect to rclone remote {remote_name}: {features}"
        results.extend([
            {"partName": part_name, "result": "Fail", "reason": reason},
            {"partName": "Write test", "result": "Fail", "reason": reason}
        ])
        return results

    if is_gcs or features.get('BucketBased', False):
        # Buckets have no real directories, so check the bucket itself
        part_name = "Verify GCS bucket" if is_gcs else "Verify bucket"
        bucket_name = remote_path.lstrip('/').split('/', 1)[0]
        if not bucket_name:
            reason = f"No bucket in destination {cfg['destDir']}; use {remote_name}:<bucket>/<path>"
            success = False
        else:
            success, detail = _run_rclone(['lsd', f"{remote_name}:{bucket_name}"])
            reason = f"Bucket {bucket_name} not found or not accessible: {detail}"
    else:
        part_name = "Destination directory"
        success, detail = _run_rclone(['lsf', cfg['destDir']])
        reason = f"Destination directory {cfg['destDir']} not found or not accessible: {detail}"

    if not success:
        results.extend([
            {"partName": part_name, "result": "Fail", "reason": reason},
            {"partName": "Write test", "result": "Fail", "reason": reason}
        ])
        return results

    results.append({"partName": part_name, "result": "Pass"})

    success, detail = _verify_write_access(cfg['destDir'], gcs=is_gcs)
    if not success:
        reason = f"No write access to {cfg['destDir']}: {detail}"
        results.append({"partName": "Write test", "result": "Fail", "reason": reason})
        return results

    results.append({"partName": "Write test", "result": "Pass"})

    return results

