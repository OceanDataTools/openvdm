#!/usr/bin/env python3
"""
FILE:  connection_utils.py

DESCRIPTION:  utilities used to connect with remote systems

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2025-07-05
 REVISION:  2025-08-08
"""

import os
import sys
import uuid
import logging
import tempfile
import subprocess
import configparser
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


def get_rclone_remote_type(remote_name, config_path=None):
        # Default rclone config path
        if config_path is None:
            config_path = os.path.expanduser("~/.config/rclone/rclone.conf")

        if not os.path.isfile(config_path):
            logging.error("rclone config file %s not found.  assuming local", config_path)
            return "local"

        config = configparser.ConfigParser()
        config.read(config_path)

        remote_section = config[remote_name] if remote_name in config else {}
        return remote_section.get('type', 'local')


def check_darwin(cfg):
    """
    Return true if server is MacOS (Darwin)
    """

    cmd = ['ssh', f"{cfg['sshUser']}@{cfg['sshServer']}", "uname -s"]
    if cfg['sshUseKey'] == '0':
        cmd = ['sshpass', '-p', cfg['sshPass']] + cmd

    logging.debug("check_darwin cmd: %s", ' '.join(cmd).replace(f'-p {cfg["sshPass"]}', '-p ****'))
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

    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5'] if use_pubkey else ['sshpass', '-p', f'{passwd}', 'ssh', '-o', 'PubkeyAuthentication=no','-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5']
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


def build_rclone_config_for_ssh(cfg, rclone_config):
    ssh_config = os.path.join(os.path.expanduser("~"), ".ssh", "config")
    identityFile = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")

    target_host = cfg['sshServer']
    found_host = False

    if os.path.exists(ssh_config):
        with open(ssh_config) as f:
            for line in f:
                line = line.strip()
                print(line)
                if line.startswith("Host "):
                    print("found host")
                    hosts = line.split()[1:]
                    found_host = target_host in hosts
                elif found_host and line.startswith('IdentityFile'):
                    print("found identityFile")
                    identityFile = line.split()[1]
                    print(identityFile)
                    break

    out = configparser.ConfigParser()
    section_name = f"{target_host}"
    out.add_section(target_host)
    out.set(section_name, "type", "sftp")
    out.set(section_name, "host", target_host)
    out.set(section_name, "user", cfg["sshUser"])
    out.set(section_name, "key_file", identityFile)
    
    print(f"[{section_name}]")
    for key, value in out[section_name].items():
        print(f"{key} = {value}")

    with open(rclone_config, "w") as f:
        out.write(f)


def build_rclone_options(cfg, mode='dry-run'):
    """
    Build the relevant rsync options for the given transfer
    """

    if ':' in cfg['destDir']:
        remote_name, _ = cfg['destDir'].split(':',1)
        remote_type = get_rclone_remote_type(remote_name)
    else:
        remote_type = 'local'

    flags = ["--progress"]
    copy_sync = "sync" if cfg.get('syncToDest', '0') == '1' else "copy"

    #if cfg.get('skipEmptyFiles') == '1':
    #    flags.extend(['--min-size', '1B'])

    if cfg.get('skipEmptyDirs') == '0':
        flags.append('--create-empty-src-dirs')

    if mode == 'dry-run':
        flags.append('--dry-run')

    if remote_type == 'google cloud storage':
        flags.extend(["--gcs-bucket-policy-only", "--local-no-set-modtime"])

    if cfg.get('bandwidthLimit') not in (None, '0'):
        flags.extend(["--bwlimit", f"{cfg['bandwidthLimit']}k" ])

    return copy_sync, flags


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


def test_local_destination(dest_dir, is_mountpoint='0'):
    results = []

    dest_dir_exists = os.path.isdir(dest_dir)

    if not dest_dir_exists:
        reason = f"Unable to find destination directory: {dest_dir} on the data warehouse"
        results.extend([{"partName": "Destination directory", "result": "Fail", "reason": reason}])

        if is_mountpoint == '1':
            results.extend([{"partName": "Destination directory is a mount point", "result": "Fail", "reason": reason}])

        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

        return results

    results.extend([{"partName": "Destination directory", "result": "Pass"}])

    if is_mountpoint == '1':
        mnt_dir = os.sep + os.path.join(*dest_dir.strip(os.sep).split(os.sep)[:2])
        if not os.path.ismount(mnt_dir):
            results.extend([{
                "partName": "Destination directory is a mount point",
                "result": "Fail",
                "reason": f"{mnt_dir} is not a mount point on the data warehouse"
            }])
            results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

            return results

        results.extend([{"partName": "Destination directory is a mount point", "result": "Pass"}])

    if not test_write_access(dest_dir):
        reason = f"Unable to delete source files from: {dest_dir} on SMB share"
        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

        return results

    results.extend([{"partName": "Write test", "result": "Pass"}])
    return results

def test_smb_destination(cdt_cfg, mntpoint, smb_version):
    results = []

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
    results.extend(test_local_destination(smb_dest_dir))

    return results



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
                reason = f"Unable to find source directory: {source_dir} on the data warehouse"
                results.extend([{"partName": "Source directory", "result": "Fail", "reason": reason}])

                if cst_cfg['localDirIsMountPoint'] == '1':
                    results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": reason}])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Source directory", "result": "Pass"}])

            if cst_cfg['localDirIsMountPoint'] == '1':
                mnt_dir = os.sep + os.path.join(*source_dir.strip(os.sep).split(os.sep)[:2])
                if not os.path.ismount(mnt_dir):
                    results.extend([{"partName": "Source directory is a mount point", "result": "Fail", "reason": f"{mnt_dir} is not a mount point on the data warehouse"}])

                    if cst_cfg['removeSourceFiles'] == '1':
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Source directory is a mount point", "result": "Pass"}])

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
            results.extend(test_local_destination(cdt_cfg['destDir'], cdt_cfg['localDirIsMountPoint']))

            if results[-1].get('result') == 'Fail':
                return results

        # Tests for smb
        if transfer_type == 'smb':

            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cdt_cfg)

            results.extend(test_smb_destination(cdt_cfg, mntpoint, smb_version))
            if results[-1].get('result') == 'Fail':
                return results

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

def test_cdt_rclone_destination(cfg):

    def _gcs_bucket_exists(remote_path):
        try:
            subprocess.run(
                ["rclone", "lsd", remote_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError:
            # Optional: inspect e.stderr for specific errors like "bucket does not exist"
            return False

    def _verify_write_access(remote_path, bucket=False):
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.write(b"rclone write test")
        temp_file.close()

        # Create a unique name to avoid conflicts
        remote_test_path = f"{remote_path.rstrip('/')}/.rclone-write-test-{uuid.uuid4().hex}.txt"
        cmd = ["rclone", "copyto", temp_file.name, remote_test_path]

        if bucket:
            cmd += ["--gcs-bucket-policy-only", "--local-no-set-modtime"]

        try:
            # Attempt to copy the file to the bucket
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )

            # Attempt to delete the test file from the bucket
            subprocess.run(
                ["rclone", "deletefile", remote_test_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )

            return True
        except subprocess.CalledProcessError:
            #logging.exception(str(e))
            return False
        finally:
            os.remove(temp_file.name)

    def _verify_sftp_destination(remote_path):
        try:
            subprocess.run(
                ["rclone", "lsf", remote_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError:
            # Optional: inspect e.stderr for specific errors like "bucket does not exist"
            return False

    results = []
    if ':' not in cfg['destDir']:
        remote_name = None
        remote_path = cfg['destDir']
        remote_type = get_transfer_type(cfg)
    else:
        remote_name, remote_path = cfg['destDir'].split(':')
        remote_type = get_rclone_remote_type(remote_name)

        if remote_type is None:
            reason = "rclone remote does not exist or rclone config file not found"
            results.extend([
                {"partName": "Rclone remote config", "result": "Fail", "reason": reason}
            ])

            return results

        results.append({"partName": "Rclone remote config", "result": "Pass"})

    if remote_type == 'local':
        results.extend(test_local_destination(remote_path))

    if remote_type == 'smb':
        with temporary_directory() as tmpdir:
            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cfg)

            results.extend(test_smb_destination(cfg, mntpoint, smb_version))

    if remote_type == 'google cloud storage':
        if '/' not in remote_path:
            remote_path += '/'
        bucket_name, dest_dir = remote_path.split('/',1)
        if not _gcs_bucket_exists(f"{remote_name}:{bucket_name}"):
            reason = f"GCS bucket {bucket_name} does not exist"
            results.extend([
                {"partName": "Verify GCS bucket", "result": "Fail", "reason": reason},
                {"partName": "Write test", "result": "Fail", "reason": reason}
            ])

            return results

        results.append({"partName": "Verify GCS bucket", "result": "Pass"})

        if not _verify_write_access(f"{remote_name}:{remote_path}", True):
            reason = f"No write access to {remote_name}:{remote_path}"
            results.append({"partName": "Write test", "result": "Fail", "reason": reason})

            return results

        results.append({"partName": "Write test", "result": "Pass"})

    if remote_type == 'sftp':
        _, dest_dir = remote_path.split('/',1)
        if not _verify_sftp_destination(cfg['destDir']):
            reason = f"Destination directory {dest_dir} does not exist"
            results.extend([
                {"partName": "Destination directory", "result": "Fail", "reason": reason},
                {"partName": "Write test", "result": "Fail", "reason": reason}
            ])

            return results

        results.append({"partName": "Destination directory", "result": "Pass"})

        if not _verify_write_access(cfg['destDir']):
            reason = f"No write access to {cfg['destDir']}"
            results.append({"partName": "Write test", "result": "Fail", "reason": reason})

            return results

        results.append({"partName": "Write test", "result": "Pass"})

    return results

