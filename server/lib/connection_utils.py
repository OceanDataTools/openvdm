import os
import logging
import subprocess


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

    logging.info("SMB version test command: %s", ' '.join(cmd))
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
    logging.info("Mount command: %s", ' '.join(cmd).replace(f'password={cst_cfg['smbPass']}', 'password=****'))

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

    cmd = ['ssh']
    if passwd is None or len(passwd) == 0:
        cmd = ['sshpass', '-p', f'{passwd}', 'ssh', '-o', 'PubkeyAuthentication=no']

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


def build_rsync_options(cfg, mode='dry-run', is_darwin=False, transfer_type=None):
    """
    Builds a list of rsync options based on config, transfer mode, and destination type.

    :param cfg: dict-like config object (e.g., gearman_worker.collection_system_transfer)
    :param mode: 'dry-run' or 'real'
    :param transfer_type: 'local', 'smb', 'rsync', or 'ssh'
    :return: list of rsync flags
    """
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

        if cfg['removeSourceFiles'] == '1':
            flags.insert(2, '--remove-source-files')

    return flags
