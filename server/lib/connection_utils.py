#!/usr/bin/env python3
"""
FILE:  connection_utils.py

DESCRIPTION:  utilities used to connect with remote systems

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2025-07-05
 REVISION:  2025-07-07
"""

import os
import sys
import logging
import subprocess
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import test_write_access, temporary_directory

def get_transfer_type(transfer_type):
    """
    Return a human-readable transfer type
    """

    if transfer_type == "1": # Local directory
        return 'local'

    if  transfer_type == "2": # Rsync server
        return 'rsync'

    if  transfer_type == "3": # SMB server
        return 'smb'

    if  transfer_type == "4": # SSH server
        return 'ssh'

    return None


def check_darwin(cfg):
    """
    Return true if server is MacOS (Darwin)
    """

    cmd = ['ssh', f"{cfg['sshUser']}@{cfg['sshServer']}", "uname -s"]
    if cfg['sshUseKey'] == '0':
        cmd = ['sshpass', '-p', cfg['sshPass']] + cmd

    logging.debug("check_darwin cmd: %s", ' '.join(cmd).replace(f'{cfg["sshPass"]}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return any(line.strip() == 'Darwin' for line in proc.stdout.splitlines())
    except subprocess.SubprocessError as exc:
        logging.error("SSH command to check for Dawin (MacOS) failed: %s", str(exc))
        return False


def detect_smb_version(cfg):
    """
    Return the SMB version used on the remote server
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
            '-U', f"{cfg['smbUser']}%{cfg['smbPass']}"
        ]

    logging.debug("detect_smb_version cmd: %s", ' '.join(cmd).replace(f'%{cfg["smbPass"]}', '%****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if proc.returncode != 0 or "NT_STATUS" in proc.stderr or "failed" in proc.stderr.lower():
            logging.error("Failed to connect to SMB server: %s", proc.stderr.strip())
            return None

        for line in proc.stdout.splitlines():
            if line.startswith('OS=[Windows 5.1]'):
                return '1.0'
        return '2.1'

    except subprocess.SubprocessError as exc:
        logging.error("SMB version detection failed: %s", str(exc))
        return None


def mount_smb_share(cfg, mntpoint, smb_version):
    """
    Mount the SMB Share to the mntpoint
    """

    # Logic handles if cfg is a cst or cdt
    read_write = 'rw' if cfg.get('removeSourceFiles', '1') == '1' else 'ro'

    opts = f"{read_write},domain={cfg['smbDomain']},vers={smb_version}"

    if cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={cfg['smbUser']},password={cfg['smbPass']}"

    cmd = ['mount', '-t', 'cifs', cfg['smbServer'], mntpoint, '-o', opts]

    logging.debug("mount_smb_share cmd: %s", ' '.join(cmd).replace(f'password={cfg["smbPass"]}', 'password=****'))
    try:
        subprocess.run(cmd, check=True)
        logging.info("Successfully mounted %s to %s", cfg['smbServer'], mntpoint)
        return True
    except subprocess.CalledProcessError as exc:
        logging.error("Failed to mount SMB share: %s.  Are you running as root?", str(exc))

        # Try to unmount in case of partial mount
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False


def build_rsync_command(flags, extra_args, source_dir, dest_dir, include_filepath):
    """
    Build the cmd array for a rsync command.  The cmd array will be passed to
    subprocess
    """

    cmd = ['rsync'] + flags
    if extra_args is not None:
        cmd += extra_args

    if include_filepath is not None:
        cmd.append(f"--files-from={include_filepath}")

    cmd += [source_dir] if dest_dir is None else [source_dir, dest_dir]
    return cmd


def test_rsync_connection(server, user, password_file=None):
    """
    Test the connection to a rsync server
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
            logging.error("rsync connection test failed: %s", proc.stderr.strip())
            return False
        return True
    except Exception as exc:
        logging.error("rsync connection test failed: %s", str(exc))
        return False


def test_rsync_write_access(server, user, tmpdir, password_file=None):
    """
    Verify the transfer has write access to the rsync server.  This is done via
    a write_test.txt file.  Currently there is no way to delete this file after
    completing the test.
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
            logging.error("rsync write test failed: %s", proc.stderr.strip())
            return False
    except Exception as exc:
        logging.error("rsync write test failed: %s", str(exc))
        return False

    # This code was an attempt to cleanup/delete the write_test.txt file
    #cmd = build_rsync_command(flags, ['-r', '--delete', '--include="write_test.txt"', '--exclude="*"'], '/dev/null/', f'rsync://{user}@{server}', None)

    #logging.debug("test_rsync_write_access cmd: %s", ' '.join(cmd))
    #try:
    #    proc = subprocess.run(cmd, capture_output=True, text=True)
    #    if proc.returncode not in [0, 24]:
    #        logging.warning("rsync failed: %s", proc.stderr.strip())
    #        return False
    #except Exception as exc:
    #    logging.error("rsync write test failed: %s", str(exc))
    #    return False

    return True


def build_ssh_command(flags, user, server, post_cmd, passwd, use_pubkey):
    """
    Build the cmd array for a ssh command.  The cmd array will be passed to
    subprocess
    """

    if (passwd is None or len(passwd) == 0) and use_pubkey is False:
        raise ValueError("Must specify either a passwd or use_pubkey")

    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes'] if use_pubkey else ['sshpass', '-p', f'{passwd}', 'ssh', '-o', 'PubkeyAuthentication=no','-o', 'StrictHostKeyChecking=no']
    cmd += flags or []
    cmd += [f'{user}@{server}', post_cmd]
    return cmd


def test_ssh_connection(server, user, passwd, use_pubkey):
    """
    Test the connection to a ssh server
    """

    cmd = build_ssh_command(None, user, server, 'ls', passwd, use_pubkey)

    logging.debug("test_ssh_connection cmd: %s", ' '.join(cmd).replace(f'{passwd}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
    except Exception as exc:
        logging.error("SSH connection test failed: %s", str(exc))
        return False
    return True


def test_ssh_remote_directory(server, user, remote_dir, passwd, use_pubkey):
    """
    Verify the presence of a directort on the ssh server
    """

    cmd = build_ssh_command(None, user, server, f'ls "{remote_dir}"', passwd, use_pubkey)

    logging.debug("test_ssh_destination cmd: %s", ' '.join(cmd).replace(f'{passwd}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
    except Exception as exc:
        logging.error("SSH destination test failed: %s", str(exc))
        return False
    return True


def test_ssh_write_access(server, user, dest_dir, passwd, use_pubkey):
    """
    Verify write access to the directory on the remote ssh server.
    """

    cmd = build_ssh_command(None, user, server, f"touch {os.path.join(dest_dir, 'writeTest.txt')}", passwd, use_pubkey)

    logging.debug("test_ssh_write_access cmd: %s", ' '.join(cmd).replace(f'{passwd}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
    except Exception as exc:
        logging.error("SSH write test failed: %s", str(exc))
        return False

    cmd = build_ssh_command(None, user, server, f"rm {os.path.join(dest_dir, 'writeTest.txt')}", passwd, use_pubkey)

    logging.debug("test_ssh_write_access cmd: %s", ' '.join(cmd).replace(f'{passwd}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
    except Exception as exc:
        logging.error("SSH write test failed: %s", str(exc))
        return False

    return True


def build_rsync_options(cfg, mode='dry-run', is_darwin=False):
    """
    Build the relevant rsync options for the given transfer
    """

    transfer_type = get_transfer_type(cfg['transferType'])

    flags = ['-trinv'] if mode == 'dry-run' else ['-triv', '--progress']

    if not is_darwin:
        flags.insert(1, '--protect-args')

    if cfg.get('skipEmptyFiles') == '1':
        flags.insert(1, '--min-size=1')

    if cfg.get('skipEmptyDirs') == '1':
        flags.insert(1, '-m')

    if mode == 'dry-run':
        flags.append('--dry-run')
        flags.append('--stats')

    else:
        if transfer_type == 'rsync':
            flags.append('--no-motd')

        if cfg.get('bandwidthLimit') not in (None, '0'):
            flags.insert(1, f"--bwlimit={cfg['bandwidthLimit']}")

        # Logic handles if cfg is a cst or cdt
        if cfg.get('removeSourceFiles', '0') == '1':
            flags.insert(2, '--remove-source-files')

        # Logic handles if cfg is a cst or cdt
        if cfg.get('syncToDest', '0') == '1':
            flags.insert(2, '--delete')

    return flags


def test_cst_source(cst_cfg, source_dir):
    """
    Test the connection to the collection system transfer
    """

    results = []

    mntpoint = None
    smb_version = None
    transfer_type = get_transfer_type(cst_cfg['transferType'])

    if not transfer_type:
        results.extend([{"partName": "Transfer type", "result": "Fail", "reason": "Unknown transfer type"}])
        return results

    with temporary_directory() as tmpdir:
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Tests for local
        if transfer_type == 'local':
            source_dir_exists = os.path.isdir(source_dir)
            if not source_dir_exists:
                reason = f"Unable to find source directory: {source_dir} on the Data Warehouse"
                results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])

                if cst_cfg['localDirIsMountPoint'] == '1':
                    results.extend([{"partName": "Source directory is a mountpoint", "result": "Fail", "reason": reason}])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Source directory", "result": "Pass"}])

            if cst_cfg['localDirIsMountPoint'] == '1':
                if not os.path.ismount(source_dir):
                    results.extend([{"partName": "Source directory is a mountpoint", "result": "Fail", "reason": f"Source directory: {source_dir} is not a mountpoint on the data warehouse"}])

                    if cst_cfg['removeSourceFiles'] == '1':
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Source directory is a mountpoint", "result": "Pass"}])

            if cst_cfg['removeSourceFiles'] == '1':
                if not test_write_access(source_dir):
                    reason = f"Unable to delete source files from: {source_dir} on SMB share"
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Write test", "result": "Pass"}])

        # Tests for smb
        if transfer_type == 'smb':

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cst_cfg)

            if not smb_version:
                reason = f"Could not connect to SMB server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                results.extend([
                    {"partName": "SMB server", "result": "Fail", "reason": reason},
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB server", "result": "Pass"}])

            mnt_success = mount_smb_share(cst_cfg, mntpoint, smb_version)
            if not mnt_success:
                reason = f"Could not connect to SMB server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                results.extend([
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB share", "result": "Pass"}])

            smb_source_dir = os.path.join(mntpoint, source_dir.lstrip('/'))
            source_dir_exists = os.path.isdir(smb_source_dir)
            if not source_dir_exists:
                reason = f"Unable to find source directory: {source_dir} on SMB share"
                results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Source directory", "result": "Pass"}])

            if cst_cfg['removeSourceFiles'] == '1':
                if not test_write_access(smb_source_dir):
                    reason = f"Unable to delete source files from: {source_dir} on SMB share"
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Write test", "result": "Pass"}])

        # Tests for rsync
        if transfer_type == 'rsync':
            if cst_cfg['rsyncUser'] != 'anonymous':
                # Build password file
                try:
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(cst_cfg['rsyncPass'])
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

            contest_success = test_rsync_connection(cst_cfg['rsyncServer'], cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Could not connect to rsync server: {cst_cfg['rsyncServer']} as {cst_cfg['rsyncUser']}"
                results.extend([
                    {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])
                return results

            results.append({"partName": "Rsync connection", "result": "Pass"})

            contest_success = test_rsync_connection(f"{cst_cfg['rsyncServer']}{source_dir}", cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Unable to find source directory: {source_dir} on the Rsync Server: {cst_cfg['rsyncServer']}"
                results.extend([
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Source directory", "result": "Pass"})

        # Tests for SSH
        if transfer_type == 'ssh':

            use_pubkey = cst_cfg['sshUseKey'] == '1'

            contest_success = test_ssh_connection(cst_cfg['sshServer'], cst_cfg['sshUser'], passwd=cst_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to connect to SSH server: {cst_cfg['sshServer']} as {cst_cfg['sshUser']}"
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SSH connection", "result": "Pass"}])

            contest_success = test_ssh_remote_directory(cst_cfg['sshServer'], cst_cfg['sshUser'], source_dir, passwd=cst_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to find destination directory: {source_dir}"
                results.extend([
                    {"partName": "Source directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Source directory", "result": "Pass"}])

        return results

def test_cdt_destination(cdt_cfg):
    """
    Test the connection to the cruise data transfer
    """

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
            dest_dir_exists = os.path.isdir(cdt_cfg['destDir'])
            if not dest_dir_exists:
                reason = f"Unable to find destination directory: {cdt_cfg['destDir']} on the Data Warehouse"
                results.extend([{"partName": "Destination directory", "result": "Fail", "reason": reason}])

                if cdt_cfg['localDirIsMountPoint'] == '1':
                    results.extend([{"partName": "Destination directory is a mountpoint", "result": "Fail", "reason": reason}])

                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Destination directory", "result": "Pass"}])

            if cdt_cfg['localDirIsMountPoint'] == '1':
                if not os.path.ismount(cdt_cfg['destDir']):
                    results.extend([{
                        "partName": "Destination directory is a mountpoint",
                        "result": "Fail",
                        "reason": f"Destination directory: {cdt_cfg['destDir']} is not a mountpoint on the Data Warehouse"
                    }])
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Destination directory is a mountpoint", "result": "Pass"}])

            if not test_write_access(cdt_cfg['destDir']):
                reason = f"Unable to delete source files from: {cdt_cfg['destDir']} on SMB share"
                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Write test", "result": "Pass"}])

        # Tests for smb
        if transfer_type == 'smb':

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cdt_cfg)

            if not smb_version:
                reason = f"Could not connect to SMB server: {cdt_cfg['smbServer']} as {cdt_cfg['smbUser']}"
                logging.error(reason)
                results.extend([
                    {"partName": "SMB server", "result": "Fail", "reason": reason},
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SMB server", "result": "Pass"}])

            mnt_success = mount_smb_share(cdt_cfg, mntpoint, smb_version)
            if not mnt_success:
                reason = f"Could not connect to SMB share: {cdt_cfg['smbServer']} as {cdt_cfg['smbUser']}"
                logging.error(reason)
                results.extend([
                    {"partName": "SMB share", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SMB share", "result": "Pass"}])

            smb_dest_dir = os.path.join(mntpoint, cdt_cfg['destDir'].lstrip('/'))
            dest_dir_exists = os.path.isdir(smb_dest_dir)
            if not dest_dir_exists:
                reason = f"Unable to find destination directory: {cdt_cfg['destDir']} on SMB share"
                logging.error(reason)
                results.extend([
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Destination directory", "result": "Pass"}])

            if not test_write_access(smb_dest_dir):
                reason = f"Write test failed to: {cdt_cfg['destDir']} on SMB share"
                logging.error(reason)
                results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Write test", "result": "Pass"}])

        # Tests for rsync
        if transfer_type == 'rsync':
            if cdt_cfg['rsyncUser'] != 'anonymous':
                # Build password file
                try:
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(cdt_cfg['rsyncPass'])
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

            contest_success = test_rsync_connection(cdt_cfg['rsyncServer'], cdt_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Could not connect to rsync server: {cdt_cfg['rsyncServer']} as {cdt_cfg['rsyncUser']}"
                results.extend([
                    {"partName": "Rsync connection", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason}
                ])
                return results

            results.append({"partName": "Rsync connection", "result": "Pass"})

            contest_success = test_rsync_connection(f"{cdt_cfg['rsyncServer']}{cdt_cfg['destDir']}", cdt_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Unable to find source directory: {cdt_cfg['destDir']} on the Rsync Server: {cdt_cfg['rsyncServer']}"
                results.extend([
                    {"partName": "Destination directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Destination directory", "result": "Pass"})

            contest_success = test_rsync_write_access(f"{cdt_cfg['rsyncServer']}{cdt_cfg['destDir']}", cdt_cfg['rsyncUser'], tmpdir, password_file)
            if not contest_success:
                reason = f"Unable to write to: {cdt_cfg['destDir']} on the Rsync Server: {cdt_cfg['rsyncServer']}"
                results.extend([
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Write test", "result": "Pass"})

        # Tests for SSH
        if transfer_type == 'ssh':

            use_pubkey = cdt_cfg['sshUseKey'] == '1'

            contest_success = test_ssh_connection(cdt_cfg['sshServer'], cdt_cfg['sshUser'], passwd=cdt_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to connect to SSH server: {cdt_cfg['sshServer']} as {cdt_cfg['sshUser']}"
                results.extend([
                    {"partName": "SSH connection", "result": "Fail", "reason": reason},
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SSH connection", "result": "Pass"}])

            contest_success = test_ssh_remote_directory(cdt_cfg['sshServer'], cdt_cfg['sshUser'], cdt_cfg['destDir'], passwd=cdt_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to find destination directory: {cdt_cfg['destDir']}"
                results.extend([
                    {"partName": "Destination directory", "result": "Fail", "reason": reason},
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Destination directory", "result": "Pass"}])


            contest_success = test_ssh_write_access(cdt_cfg['sshServer'], cdt_cfg['sshUser'], cdt_cfg['destDir'], passwd=cdt_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"No write access on ssh server: {cdt_cfg['sshServer']} as {cdt_cfg['sshUser']} at {cdt_cfg['destDir']}"
                results.extend([
                    {"partName": "Write test", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "Write test", "result": "Pass"}])

        return results
