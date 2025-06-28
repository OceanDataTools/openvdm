import os
import sys
import shutil
import logging
import tempfile
import subprocess
from os.path import dirname, realpath
from contextlib import contextmanager

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

def get_transfer_type(transfer_type):

    if transfer_type == "1": # Local Directory
        return 'local'

    if  transfer_type == "2": # Rsync Server
        return 'rsync'

    if  transfer_type == "3": # SMB Server
        return 'smb'

    if  transfer_type == "4": # SSH Server
        return 'ssh'

    return None


def check_darwin(cst_cfg):
    # Detect if Darwin (MacOS)
    cmd = ['ssh', f"{cst_cfg['sshUser']}@{cst_cfg['sshServer']}", "uname -s"]
    if cst_cfg['sshUseKey'] == '0':
        cmd = ['sshpass', '-p', cst_cfg['sshPass']] + cmd

    logging.debug("check_darwin cmd: %s", ' '.join(cmd).replace(f'{cst_cfg["sshPass"]}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return any(line.strip() == 'Darwin' for line in proc.stdout.splitlines())
    except subprocess.SubprocessError as e:
        logging.error("SSH command to check for Dawin (MacOS) failed: %s", str(e))
        return False


def detect_smb_version(cst_cfg):
    if cst_cfg.get('smbUser') == 'guest':
        cmd = [
            'smbclient', '-L', cst_cfg['smbServer'],
            '-W', cst_cfg['smbDomain'], '-m', 'SMB2', '-g', '-N'
        ]
    else:
        cmd = [
            'smbclient', '-L', cst_cfg['smbServer'],
            '-W', cst_cfg['smbDomain'], '-m', 'SMB2', '-g',
            '-U', f"{cst_cfg['smbUser']}%{cst_cfg['smbPass']}"
        ]

    logging.debug("detect_smb_version cmd: %s", ' '.join(cmd).replace(f'password={cst_cfg["smbPass"]}', 'password=****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if proc.returncode != 0 or "NT_STATUS" in proc.stderr or "failed" in proc.stderr.lower():
            logging.error("Failed to connect to SMB server: %s", proc.stderr.strip())
            return None

        for line in proc.stdout.splitlines():
            if line.startswith('OS=[Windows 5.1]'):
                return '1.0'
        return '2.1'

    except subprocess.SubprocessError as e:
        logging.error("SMB version detection failed: %s", str(e))
        return None


def mount_smb_share(cst_cfg, mntpoint, smb_version):

    read_write = 'rw' if cst_cfg['removeSourceFiles'] == '1' else 'ro'

    opts = f"{read_write},domain={cst_cfg['smbDomain']},vers={smb_version}"

    if cst_cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={cst_cfg['smbUser']},password={cst_cfg['smbPass']}"

    cmd = ['mount', '-t', 'cifs', cst_cfg['smbServer'], mntpoint, '-o', opts]

    logging.debug("mount_smb_share cmd: %s", ' '.join(cmd).replace(f'password={cst_cfg["smbPass"]}', 'password=****'))
    try:
        subprocess.run(cmd, check=True)
        logging.info("Successfully mounted %s to %s", cst_cfg['smbServer'], mntpoint)
        return True
    except subprocess.CalledProcessError as e:
        logging.error("Failed to mount SMB share: %s", str(e))

        # Try to unmount in case of partial mount
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False


def test_rsync_connection(server, user, password_file=None):
    flags = ['--no-motd', '--contimeout=5']
    extra_args = None

    if password_file is not None:
        extra_args = [f'--password-file={password_file}']

    cmd = build_rsync_command(flags, extra_args, f'rsync://{user}@{server}', None, None)

    logging.debug("test_rsync_connection cmd: %s", ' '.join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode not in [0, 24]:
            logging.warning("rsync failed: %s", proc.stderr.strip())
            return False
        return True
    except Exception as e:
        logging.error("rsync connection test failed: %s", str(e))
        return False


def build_rsync_command(flags, extra_args, source_dir, dest_dir, include_filepath):
    cmd = ['rsync'] + flags
    if extra_args is not None:
        cmd += extra_args

    if include_filepath is not None:
        cmd.append(f"--files-from={include_filepath}")

    cmd += [source_dir] if dest_dir is None else [source_dir, dest_dir]
    return cmd


def test_ssh_connection(server, user, passwd, use_pubkey):
    cmd = build_ssh_command(['-o', 'StrictHostKeyChecking=no'], user, server, 'ls', passwd, use_pubkey)

    logging.debug("test_ssh_connection cmd: %s", ' '.join(cmd).replace(f'{passwd}', '****'))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False
        return True
    except Exception as e:
        logging.error("SSH connection test failed: %s", str(e))
        return False


def build_ssh_command(flags, user, server, post_cmd, passwd, use_pubkey):

    if (passwd is None or len(passwd) == 0) and use_pubkey is False:
        raise ValueError("Must specify either a passwd or use_pubkey")

    cmd = ['ssh'] if use_pubkey else ['sshpass', '-p', f'{passwd}', 'ssh', '-o', 'PubkeyAuthentication=no']
    cmd += flags or []
    cmd += [f'{user}@{server}', post_cmd]
    return cmd


def delete_from_dest(dest_dir, include_files):
    deleted_files = []

    for filename in os.listdir(dest_dir):
        full_path = os.path.join(dest_dir, filename)
        if os.path.isfile(full_path) and filename not in include_files:
            logging.info("Deleting: %s", filename)
            try:
                os.remove(full_path)
                deleted_files.append(filename)
            except FileNotFoundError:
                logging.error("File to delete not found: %s", filename)
            except PermissionError:
                logging.error("Insufficent permission to delete file: %s", filename)
            except OSError as e:
                logging.error("OS error occurred while deleting file: %s --> %s", filename, str(e))

    return deleted_files


def build_rsync_options(cst_cfg, mode='dry-run', is_darwin=False):
    """
    Builds a list of rsync options based on config, transfer mode, and destination type.

    :param cst_cfg: dict-like config object (e.g., gearman_worker.collection_system_transfer)
    :param mode: 'dry-run' or 'real'
    :param transfer_type: 'local', 'smb', 'rsync', or 'ssh'
    :return: list of rsync flags
    """

    transfer_type = get_transfer_type(cst_cfg['transferType'])

    flags = ['-trinv'] if mode == 'dry-run' else ['-triv', '--progress']

    if not is_darwin:
        flags.insert(1, '--protect-args')

    if cst_cfg.get('skipEmptyFiles') == '1':
        flags.insert(1, '--min-size=1')

    if cst_cfg.get('skipEmptyDirs') == '1':
        flags.insert(1, '-m')

    if mode == 'dry-run':
        flags.append('--dry-run')
        flags.append('--stats')

    else:
        if transfer_type == 'rsync':
            flags.append('--no-motd')

        if cst_cfg.get('bandwidthLimit') not in (None, '0'):
            flags.insert(1, f"--bwlimit={cst_cfg['bandwidthLimit']}")

        if cst_cfg['removeSourceFiles'] == '1':
            flags.insert(2, '--remove-source-files')

    return flags


def test_cst_source(cst_cfg, source_dir):

    @contextmanager
    def temporary_directory():
        tmpdir = tempfile.mkdtemp()
        try:
            yield tmpdir
        finally:
            mntpoint_path = os.path.join(tmpdir, 'mntpoint')

            if os.path.ismount(mntpoint_path):
                try:
                    subprocess.run(['umount', mntpoint_path], check=True)
                    logging.info(f"Unmounted {mntpoint_path} before cleanup.")
                except subprocess.CalledProcessError as e:
                    logging.warning(f"Failed to unmount {mntpoint_path}: {e}")

            try:
                shutil.rmtree(tmpdir)
            except Exception as e:
                logging.warning(f"Could not delete temp dir {tmpdir}: {e}")


    results = []

    mntpoint = None
    smb_version = None
    transfer_type = get_transfer_type(cst_cfg['transferType'])

    if not transfer_type:
        logging.error("Unknown Transfer Type")
        results.extend([{"partName": "Collection transfer type", "result": "Fail", "reason": "Unknown transfer type"}])
        return results

    with temporary_directory() as tmpdir:
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Tests for local
        if transfer_type == 'local':
            source_dir_exists = os.path.isdir(source_dir)
            if not source_dir_exists:
                reason = f"Unable to find source directory: {source_dir} on the Data Warehouse"
                results.extend([{"partName": "Source Directory", "result": "Fail", "reason": reason}])

                if cst_cfg['localDirIsMountPoint'] == '1':
                    results.extend([{"partName": "Source Directory is a Mountpoint", "result": "Fail", "reason": reason}])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Source Directory", "result": "Pass"}])

            if cst_cfg['localDirIsMountPoint'] == '1':
                if not os.path.ismount(source_dir):
                    results.extend([{"partName": "Source Directory is a Mountpoint", "result": "Fail", "reason": f"Source directory: {source_dir} is not a mountpoint on the Data Warehouse"}])

                    if cst_cfg['removeSourceFiles'] == '1':
                        results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                    return results

                results.extend([{"partName": "Source Directory is a Mountpoint", "result": "Pass"}])

            if cst_cfg['removeSourceFiles'] == '1':
                if not verfy_write_access(source_dir):
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
                logging.error("unable to connect to SMB server")
                reason = f"Could not connect to SMB Server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                results.extend([
                    {"partName": "SMB Server", "result": "Fail", "reason": reason},
                    {"partName": "SMB Share", "result": "Fail", "reason": reason},
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB Server", "result": "Pass"}])

            mnt_success = mount_smb_share(cst_cfg, mntpoint, smb_version)
            if not mnt_success:
                reason = f"Could not connect to SMB Server: {cst_cfg['smbServer']} as {cst_cfg['smbUser']}"
                results.extend([
                    {"partName": "SMB Share", "result": "Fail", "reason": reason},
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "SMB Share", "result": "Pass"}])

            smb_source_dir = os.path.join(mntpoint, source_dir.lstrip('/'))
            source_dir_exists = os.path.isdir(smb_source_dir)
            if not source_dir_exists:
                reason = f"Unable to find source directory: {source_dir} on SMB share"
                results.extend([{"partName": "Source Directory", "result": "Fail", "reason": reason}])

                if cst_cfg['removeSourceFiles'] == '1':
                    results.extend([{"partName": "Write test", "result": "Fail", "reason": reason}])

                return results

            results.extend([{"partName": "Source Directory", "result": "Pass"}])

            if cst_cfg['removeSourceFiles'] == '1':
                if not verfy_write_access(smb_source_dir):
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
                        {"partName": "Rsync Connection", "result": "Fail", "reason": reason},
                        {"partName": "Source Directory", "result": "Fail", "reason": reason}
                    ])
            else:
                password_file = None

            contest_success = test_rsync_connection(cst_cfg['rsyncServer'], cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Could not connect to Rsync Server: {cst_cfg['rsyncServer']} as {cst_cfg['rsyncUser']}"
                results.extend([
                    {"partName": "Rsync Connection", "result": "Fail", "reason": reason},
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])
                return results

            results.append({"partName": "Rsync Connection", "result": "Pass"})

            contest_success = test_rsync_connection(cst_cfg['rsyncServer'] + source_dir, cst_cfg['rsyncUser'], password_file)
            if not contest_success:
                reason = f"Unable to find source directory: {source_dir} on the Rsync Server: {cst_cfg['rsyncServer']}"
                results.extend([
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Source Directory", "result": "Pass"})

        # Tests for SSH
        if transfer_type == 'ssh':

            use_pubkey = cst_cfg['sshUseKey'] == '1'

            contest_success = test_ssh_connection(cst_cfg['sshServer'], cst_cfg['sshUser'], passwd=cst_cfg['sshPass'], use_pubkey=use_pubkey)

            if not contest_success:
                reason = f"Unable to connect to ssh server: {cst_cfg['sshServer']} as {cst_cfg['sshUser']}"
                results.extend([
                    {"partName": "SSH Connection", "result": "Fail", "reason": reason},
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.extend([{"partName": "SSH Connection", "result": "Pass"}])

            cmd = build_ssh_command(['-o', 'StrictHostKeyChecking=no'], cst_cfg['sshUser'], cst_cfg['sshServer'], f'ls "{source_dir}"', cst_cfg['sshPass'], use_pubkey)
            proc = subprocess.run(cmd, capture_output=True, check=False)
            if proc.returncode != 0:
                reason = f"Unable to find source directory: {source_dir} on the SSH Server: {cst_cfg['rsyncServer']}"
                results.extend([
                    {"partName": "Source Directory", "result": "Fail", "reason": reason}
                ])

                return results

            results.append({"partName": "Source Directory", "result": "Pass"})

        return results


def verfy_write_access(dest_dir):
    """
    Verify the current user has write permissions to the dest_dir
    """

    try:
        test_file = os.path.join(dest_dir, 'writeTest.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("This file tests if the directory can be written to.")
        os.remove(test_file)
        logging.info("Write test passed for %s", dest_dir)
        return True
    except Exception:
        logging.exception("Write test failed for %s", dest_dir)
        return False

