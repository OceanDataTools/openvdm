#!/usr/bin/env python3
"""
FILE:  run_cruise_data_transfer.py

DESCRIPTION:  Gearman worker that handles the transfer of all cruise data from
    the Shipboard Data Warehouse to a second location.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.10
  CREATED:  2015-01-01
 REVISION:  2025-04-12
"""

import argparse
import fnmatch
import json
import logging
import os
import sys
import shutil
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from os.path import dirname, realpath
from random import randint
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import is_ascii
from server.lib.set_owner_group_permissions import set_owner_group_permissions
from server.lib.openvdm import OpenVDM

@contextmanager
def temporary_directory():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)

def process_batch(filepaths, filters):
    include = []
    exclude = []

    for filepath in filepaths:
        try:
            if os.path.islink(filepath):
                continue

            if any(fnmatch.fnmatch(filepath, p) for p in filters['ignore_filters']):
                continue

            if not is_ascii(filepath):
                exclude.append(filepath)
                continue

            if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
                if not any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
                    include.append(filepath)
                else:
                    exclude.append(filepath)
            else:
                exclude.append(filepath)

        except FileNotFoundError:
            continue

    return include, exclude


def build_filelist(gearman_worker, source_dir, batch_size=1000, max_workers=8):
    return_files = {'include': [], 'exclude': [], 'new': [], 'updated': []}
    logging.info("Starting filelist build in %s", source_dir)

    filters = build_filters(gearman_worker)

    # Step 1: Gather all file paths
    filepaths = []
    for root, _, filenames in os.walk(source_dir):
        for filename in filenames:
            filepaths.append(os.path.join(root, filename))

    total_files = len(filepaths)
    logging.info("Discovered %d files", total_files)

    # Step 2: Batch file paths
    batches = [filepaths[i:i + batch_size] for i in range(0, len(filepaths), batch_size)]

    # Step 3: Process in thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_batch, batch, filters) for batch in batches]
        for future in as_completed(futures):
            include, exclude = future.result()
            return_files['include'].extend(include)
            return_files['exclude'].extend(exclude)

    logging.info("Initial filtering complete: %d included, %d excluded",
                 len(return_files['include']), len(return_files['exclude']))

    # Step 4: Format output
    return_files['include'].sort()
    return_files['exclude'].sort()

    base_len = len(source_dir.rstrip(os.sep)) + 1
    return_files['include'] = [f[base_len:] for f in return_files['include']]
    return_files['exclude'] = [f[base_len:] for f in return_files['exclude']]

    # logging.debug("Final return_files object: %s", json.dumps(return_files, indent=2))
    return return_files


def detect_smb_version(gearman_worker):
    smb_cfg = gearman_worker.cruise_data_transfer
    if smb_cfg['smbUser'] == 'guest':
        cmd = [
            'smbclient', '-L', smb_cfg['smbServer'],
            '-W', smb_cfg['smbDomain'], '-m', 'SMB2', '-g', '-N'
        ]
    else:
        cmd = [
            'smbclient', '-L', smb_cfg['smbServer'],
            '-W', smb_cfg['smbDomain'], '-m', 'SMB2', '-g',
            '-U', f"{smb_cfg['smbUser']}%{smb_cfg['smbPass']}"
        ]

    logging.debug("SMB version test command: %s", ' '.join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('OS=[Windows 5.1]'):
            return '1.0'
    return '2.1'


def mount_smb_share(gearman_worker, mntpoint, smb_version):
    smb_cfg = gearman_worker.cruise_data_transfer
    opts = f"rw,domain={smb_cfg['smbDomain']},vers={smb_version}"

    if smb_cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={smb_cfg['smbUser']},password={smb_cfg['smbPass']}"

    mount_cmd = ['sudo', 'mount', '-t', 'cifs', smb_cfg['smbServer'], mntpoint, '-o', opts]
    logging.debug("Mount command: %s", ' '.join(mount_cmd))

    result = subprocess.run(mount_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error("Failed to mount SMB share.")
        logging.error("STDOUT: %s", result.stdout.strip())
        logging.error("STDERR: %s", result.stderr.strip())

        # Try to unmount in case of partial mount
        subprocess.run(['sudo', 'umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    logging.info("Mounted SMB share successfully.")
    return True


def build_filters(gearman_worker):
    """
    Build filters for the transfer
    """

    return {
        'include_filters': ['*'],
        'exclude_filters': build_exclude_filterlist(gearman_worker),
        'ignore_filters': []
    }


def build_exclude_filterlist(gearman_worker):
    """
    Build exclude filter for the transfer
    """
    exclude_filterlist = []

    cfg = gearman_worker.shipboard_data_warehouse_config
    transfer = gearman_worker.cruise_data_transfer
    lowerings = gearman_worker.ovdm.get_lowerings() or []

    # Exclude OVDM-related files if flag is set
    if transfer.get('includeOVDMFiles') == '0':
        exclude_filterlist.extend([
            f"*{cfg['cruiseConfigFn']}",
            f"*{cfg['md5SummaryFn']}",
            f"*{cfg['md5SummaryMd5Fn']}"
        ])
        # TODO: Exclude lowering.json files per lowering

    # Handle excluded collection systems
    excluded_ids = transfer.get('excludedCollectionSystems', '').split(',') if transfer.get('excludedCollectionSystems') else []

    for cs_id in filter(lambda x: x and x != '0', excluded_ids):
        try:
            cs_transfer = gearman_worker.ovdm.get_collection_system_transfer(cs_id)
            cruise_or_lowering = cs_transfer.get('cruiseOrLowering')
            dest_dir = cs_transfer.get('destDir')

            if cruise_or_lowering == '0':
                # Cruise-level exclusion
                exclude_filterlist.append(f"*{dest_dir.replace('{cruiseID}', gearman_worker.cruise_id)}*")
            else:
                # Lowering-level exclusions
                for lowering in lowerings:
                    filter_path = dest_dir.replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', lowering)
                    exclude_filterlist.append(f"*{lowering}/{filter_path}*")

        except Exception as err:
            logging.warning("Could not retrieve collection system transfer %s: %s", cs_id, err)

    # Handle excluded extra directories
    extra_dir_ids = transfer.get('excludedExtraDirectories', '').split(',') if transfer.get('excludedExtraDirectories') else []

    for extra_id in filter(lambda x: x and x != '0', extra_dir_ids):
        try:
            extra_dir = gearman_worker.ovdm.get_extra_directory(extra_id)
            exclude_filterlist.append(f"*{extra_dir['destDir'].replace('{cruiseID}', gearman_worker.cruise_id)}*")
        except Exception as err:
            logging.warning("Could not retrieve extra directory %s: %s", extra_id, err)

    logging.debug("Exclude filters: %s", json.dumps(exclude_filterlist, indent=2))
    return exclude_filterlist


def run_transfer_command(gearman_worker, gearman_job, command, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.debug("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.debug('Transfer Command: %s', ' '.join(command))

    file_index = 0
    new_files = []
    updated_files = []

    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while proc.poll() is None:

        for line in proc.stdout:

            if gearman_worker.stop:
                logging.debug("Stopping")
                proc.terminate()
                break

            if not line:
                continue

            # logging.debug("%s", line)

            if line.startswith( '>f+++++++++' ):
                filename = line.split(' ',1)[1]
                new_files.append(filename.rstrip('\n'))
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1
            elif line.startswith( '>f.' ):
                filename = line.split(' ',1)[1]
                updated_files.append(filename.rstrip('\n'))
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1

    return new_files, updated_files


def build_rsync_command(flags, extra_args, source_dir, dest_dir, exclude_file_path=None):
    cmd = ['rsync'] + flags
    if exclude_file_path:
        cmd.append(f"--exclude-from={exclude_file_path}")
    cmd += extra_args
    cmd += [source_dir, dest_dir]
    return cmd


def build_rsync_options(cfg, mode='dry-run', transfer_type=None):
    """
    Builds a list of rsync options based on config, transfer mode, and destination type.

    :param cfg: dict-like config object (e.g., gearman_worker.cruise_data_transfer)
    :param mode: 'dry-run' or 'real'
    :param transfer_type: 'local', 'smb', 'rsync', or 'ssh'
    :return: list of rsync flags
    """
    flags = ['-trinv'] if mode == 'dry-run' else ['-triv']

    if cfg.get('skipEmptyFiles') == '1':
        flags.insert(1, '--min-size=1')

    if cfg.get('skipEmptyDirs') == '1':
        flags.insert(1, '-m')

    if mode == 'dry-run':
        flags.append('--dry-run')
        flags.append('--stats')
    else:
        if cfg.get('syncToDest') == '1':
            flags.insert(1, '--delete')
        if transfer_type == 'rsync':
            flags.append('--no-motd')
        if cfg.get('bandwidthLimit') not in (None, '0'):
            flags.insert(1, f"--bwlimit={cfg['bandwidthLimit']}")

    return flags


def write_exclude_file(exclude_list, filepath):
    try:
        with open(filepath, mode='w', encoding="utf-8") as f:
            f.write('\n'.join(exclude_list))
            f.write('\0')
    except IOError as e:
        logging.error("Error writing exclude file: %s", e)
        return False

    return True


def transfer_to_destination(gearman_worker, gearman_job, transfer_type):
    """
    Unified transfer function to handle local, SMB, rsync, and SSH transfers
    """
    logging.debug("Starting unified transfer: %s", transfer_type)

    cfg = gearman_worker.cruise_data_transfer
    cruise_cfg = gearman_worker.shipboard_data_warehouse_config
    cruise_dir = os.path.join(cruise_cfg['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)

    logging.debug("Building file list")
    files = build_filelist(gearman_worker, cruise_dir)

    with temporary_directory() as tmpdir:
        exclude_file = os.path.join(tmpdir, 'rsyncExcludeList.txt')
        if not write_exclude_file(files['exclude'], exclude_file):
            return {'verdict': False, 'reason': 'Failed to write exclude file'}

        if transfer_type == 'smb':
            # Mount SMB Share
            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(gearman_worker)
            success = mount_smb_share(gearman_worker, mntpoint, smb_version)
            if not success:
                return {'verdict': False, 'reason': 'Failed to mount SMB share'}
            dest = os.path.join(mntpoint, cfg['destDir'].lstrip('/')).rstrip('/')

        elif transfer_type == 'rsync':
            # Write rsync password file
            password_file = os.path.join(tmpdir, 'rsyncPass')
            with open(password_file, 'w', encoding='utf-8') as f:
                f.write(cfg['rsyncPass'])
            os.chmod(password_file, 0o600)
            dest = f"rsync://{cfg['rsyncUser']}@{cfg['rsyncServer']}{cfg['destDir'].rstrip('/')}/"

        elif transfer_type == 'ssh':
            ssh_target = f"{cfg['sshUser']}@{cfg['sshServer']}:{cfg['destDir'].rstrip('/')}"
            dest = ssh_target

        else:  # local
            dest = cfg['destDir'].rstrip('/')

        # === DRY RUN ===
        dry_flags = build_rsync_options(cfg, mode='dry-run', transfer_type=transfer_type)

        extra_args = []
        if transfer_type == 'ssh':
            extra_args = ['-e', 'ssh']
        elif transfer_type == 'rsync':
            extra_args = [f"--password-file={password_file}"]

        dry_cmd = build_rsync_command(dry_flags, extra_args, cruise_dir, dest, exclude_file)
        if transfer_type == 'ssh' and cfg.get('sshUseKey') == '0':
            dry_cmd = ['sshpass', '-p', cfg['sshPass']] + dry_cmd

        logging.debug("Dry run command: %s", ' '.join(dry_cmd))
        proc = subprocess.run(dry_cmd, capture_output=True, text=True, check=False)

        file_count = 0
        for line in proc.stdout.splitlines():
            if line.startswith('Number of regular files transferred:'):
                file_count = int(line.split(':')[1].replace(',', ''))
                logging.info("File Count: %d", file_count)
                break

        if file_count == 0:
            logging.debug("Nothing to transfer")
        else:
            # === REAL TRANSFER ===
            real_flags = build_rsync_options(cfg, mode='real', transfer_type=transfer_type)

            real_cmd = build_rsync_command(real_flags, extra_args, cruise_dir, dest, exclude_file)
            if transfer_type == 'ssh' and cfg.get('sshUseKey') == '0':
                real_cmd = ['sshpass', '-p', cfg['sshPass']] + real_cmd

            logging.debug("Real transfer command: %s", ' '.join(real_cmd))
            files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, real_cmd, file_count)

            # === PERMISSIONS (local only) ===
            if transfer_type == 'local' and cfg.get('localDirIsMountPoint') != '1':
                logging.info("Setting file permissions")
                output = set_owner_group_permissions(
                    cruise_cfg['shipboardDataWarehouseUsername'],
                    os.path.join(dest, gearman_worker.cruise_id)
                )
                if not output['verdict']:
                    return output

        if transfer_type == 'smb':
            time.sleep(2)
            subprocess.call(['umount', mntpoint])

    return {'verdict': True, 'files': files}


class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.system_status = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def on_job_execute(self, current_job):
        """
        Function run whenever a new job arrives
        """

        logging.debug("current_job: %s", current_job)

        self.stop = False
        payload_obj = json.loads(current_job.data)

        try:
            self.cruise_data_transfer = self.ovdm.get_cruise_data_transfer(payload_obj['cruiseDataTransfer']['cruiseDataTransferID'])

            logging.info("cruiseDataTransfer configuration: \n%s", json.dumps(self.cruise_data_transfer, indent=2))

            if not self.cruise_data_transfer: # doesn't exist
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Cruise Data Tranfer Data", "result": "Fail", "reason": "Could not find configuration data for cruise data transfer"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

            if self.cruise_data_transfer['status'] == "1": # running
                logging.info("Transfer job for %s skipped because a transfer for that cruise data destination is already in-progress", self.cruise_data_transfer['name'])
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer In-Progress", "result": "Ignore", "reason": "Transfer is already in-progress"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        except Exception as err:
            logging.debug(str(err))
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Cruise Data Tranfer Data", "result": "Fail", "reason": "Could not find retrieve data for cruise data transfer from OpenVDM API"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        self.system_status = payload_obj['systemStatus'] if 'systemStatus' in payload_obj else self.ovdm.get_system_status()
        self.cruise_data_transfer.update(payload_obj['cruiseDataTransfer'])

        if self.system_status == "Off" or self.cruise_data_transfer['enable'] == '0':
            logging.info("Transfer job for %s skipped because that cruise data transfer is currently disabled", self.cruise_data_transfer['name'])
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer Enabled", "result": "Ignore", "reason": "Transfer is disabled"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        self.cruise_id = payload_obj['cruiseID'] if 'cruiseID' in payload_obj else self.ovdm.get_cruise_id()

        logging.info("Job: %s, %s transfer started at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s, %s transfer failed at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{"partName": "Worker crashed", "result": "Fail", "reason": "Unknown"}]))
        self.ovdm.set_error_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'], 'Worker crashed')

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)
        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run whenever the current job completes
        """

        results_obj = json.loads(job_result)

        if len(results_obj['parts']) > 0:
            if results_obj['parts'][-1]['result'] == "Fail" and results_obj['parts'][-1]['partName'] != "Located Cruise Data Tranfer Data": # Final Verdict
                self.ovdm.set_error_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'], results_obj['parts'][-1]['reason'])
            elif results_obj['parts'][-1]['result'] == "Pass":
                self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])
        else:
            self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s, %s transfer completed at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

        return super().send_job_complete(current_job, job_result)


    def stop_task(self):
        """
        Function to stop the current job
        """

        self.stop = True
        logging.warning("Stopping current task...")


    def quit_worker(self):
        """
        Function to quit the worker
        """

        self.stop = True
        logging.warning("Quitting worker...")
        self.shutdown()


def task_run_cruise_data_transfer(gearman_worker, current_job):
    """
    Run the cruise data transfer
    """

    time.sleep(randint(0,2))

    job_results = {
        'parts': [
            {"partName": "Transfer In-Progress", "result": "Pass"},
            {"partName": "Transfer Enabled", "result": "Pass"}
        ],
        'files':{}
    }

    logging.debug("Setting transfer status to 'Running'")
    gearman_worker.ovdm.set_running_cruise_data_transfer(gearman_worker.cruise_data_transfer['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing configuration")
    gearman_worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([gearman_worker.ovdm.get_gearman_server()])

    gm_data = {
        'cruiseDataTransfer': gearman_worker.cruise_data_transfer,
        'cruiseID': gearman_worker.cruise_id
    }

    completed_job_request = gm_client.submit_job("testCruiseDataTransfer", json.dumps(gm_data))
    results_obj = json.loads(completed_job_request.result)

    logging.debug('Connection Test Results: %s', json.dumps(results_obj, indent=2))

    if results_obj['parts'][-1]['result'] == "Pass": # Final Verdict
        logging.debug("Connection test passed")
        job_results['parts'].append({"partName": "Connection Test", "result": "Pass"})
    else:
        logging.warning("Connection test failed, quitting job")
        job_results['parts'].append({"partName": "Connection Test", "result": "Fail", "reason": results_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    gearman_worker.send_job_status(current_job, 2, 10)

    logging.info("Transferring files")
    output_results = None
    if gearman_worker.cruise_data_transfer['transferType'] == "1": # Local Directory
        output_results = transfer_to_destination(gearman_worker, current_job, 'local')
    elif  gearman_worker.cruise_data_transfer['transferType'] == "2": # Rsync Server
        output_results = transfer_to_destination(gearman_worker, current_job, 'rsync')
    elif  gearman_worker.cruise_data_transfer['transferType'] == "3": # SMB Server
        output_results = transfer_to_destination(gearman_worker, current_job, 'smb')
    elif  gearman_worker.cruise_data_transfer['transferType'] == "4": # SSH Server
        output_results = transfer_to_destination(gearman_worker, current_job, 'ssh')
    else:
        logging.error("Unknown Transfer Type")
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": "Unknown transfer type"})
        return json.dumps(job_results)

    if not output_results['verdict']:
        logging.error("Transfer of remote files failed: %s", output_results['reason'])
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    logging.debug("Transfer completed successfully")
    job_results['files'] = output_results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s file(s) intentionally skipped", len(job_results['files']['exclude']))

    gearman_worker.send_job_status(current_job, 9, 10)

    time.sleep(2)

    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle cruise data transfer related tasks')
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')

    parsed_args = parser.parse_args()

    ############################
    # Set up logging before we do any other argument parsing (so that we
    # can log problems with argument parsing).

    LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    parsed_args.verbosity = min(parsed_args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[parsed_args.verbosity])

    logging.debug("Creating Worker...")

    new_worker = OVDMGearmanWorker()
    new_worker.set_client_id(__file__)

    logging.debug("Defining Signal Handlers...")
    def sigquit_handler(_signo, _stack_frame):
        """
        Signal Handler for QUIT
        """

        logging.warning("QUIT Signal Received")
        new_worker.stop_task()

    def sigint_handler(_signo, _stack_frame):
        """
        Signal Handler for INT
        """

        logging.warning("INT Signal Received")
        new_worker.quit_worker()

    signal.signal(signal.SIGQUIT, sigquit_handler)
    signal.signal(signal.SIGINT, sigint_handler)

    logging.info("Registering worker tasks...")

    logging.info("\tTask: runCruiseDataTransfer")
    new_worker.register_task("runCruiseDataTransfer", task_run_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
