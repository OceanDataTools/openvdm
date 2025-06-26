import os
import logging
import subprocess


def check_darwin(cst_cfg):
    # Detect if Darwin (macOS)
    is_darwin_cmd = ['ssh', f"{cst_cfg['sshUser']}@{cst_cfg['sshServer']}", "uname -s"]
    if cst_cfg['sshUseKey'] == '0':
        is_darwin_cmd = ['sshpass', '-p', cst_cfg['sshPass']] + is_darwin_cmd

    proc = subprocess.run(is_darwin_cmd, capture_output=True, text=True, check=False)
    return any(line.strip() == 'Darwin' for line in proc.stdout.splitlines())


def detect_smb_version(cst_cfg):
    if cst_cfg['smbUser'] == 'guest':
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
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('OS=[Windows 5.1]'):
            return '1.0'
    return '2.1'


def mount_smb_share(cst_cfg, mntpoint, smb_version):

    read_write = 'rw' if cst_cfg['removeSourceFiles'] == '1' else 'ro'

    opts = f"{read_write},domain={cst_cfg['smbDomain']},vers={smb_version}"

    if cst_cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={cst_cfg['smbUser']},password={cst_cfg['smbPass']}"

    mount_cmd = ['mount', '-t', 'cifs', cst_cfg['smbServer'], mntpoint, '-o', opts]
    logging.info("Mount command: %s", ' '.join(mount_cmd))

    result = subprocess.run(mount_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error("Failed to mount SMB share.")
        logging.error("STDOUT: %s", result.stdout.strip())
        logging.error("STDERR: %s", result.stderr.strip())

        # Try to unmount in case of partial mount
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    logging.info("Mounted SMB share successfully.")
    return True


def build_rsync_command(flags, extra_args, source_dir, dest_dir, include_file_path=None):
    cmd = ['rsync'] + flags
    cmd += extra_args
    if include_file_path is not None:
        cmd.append(f"--files-from={include_file_path}")
    cmd += [source_dir, dest_dir]
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
