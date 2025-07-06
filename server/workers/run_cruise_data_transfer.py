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
import json
import logging
import os
import re
import sys
import signal
import subprocess
import time
from os.path import dirname, realpath
from random import randint
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import set_owner_group_permissions, temporary_directory
from server.lib.connection_utils import build_rsync_options, check_darwin, detect_smb_version, get_transfer_type, mount_smb_share, test_cdt_destination
from server.lib.openvdm import OpenVDM

TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

TASK_NAMES = {
    'RUN_CRUISE_DATA_TRANSFER': 'runCruiseDataTransfer'
}


class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Gearman worker for OpenVDM-based cruise data transfers.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.system_status = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        self.cruise_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_exclude_filterlist(self):
        """
        Build exclude filter for the transfer
        """
        exclude_filterlist = []

        wh_cfg = self.shipboard_data_warehouse_config
        cdt_cfg = self.cruise_data_transfer
        lowerings = self.ovdm.get_lowerings() or []

        # Exclude OVDM-related files if flag is set
        if cdt_cfg.get('includeOVDMFiles') == '0':
            exclude_filterlist.extend([
                f"/{wh_cfg['cruiseConfigFn']}",
                f"/{wh_cfg['md5SummaryFn']}",
                f"/{wh_cfg['md5SummaryMd5Fn']}"
            ])

            for lowering in lowerings:
                logging.debug(json.dumps(lowering, indent=2))
                exclude_filterlist.append(f"/{os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], lowering, self.ovdm.get_lowering_config_fn())}")

        # Handle excluded collection systems
        ex_cst_ids = cdt_cfg.get('excludedCollectionSystems', '').split(',') if cdt_cfg.get('excludedCollectionSystems') else []

        for cst_id in filter(lambda x: x and x != '0', ex_cst_ids):
            try:
                cst_cfg = self.ovdm.get_collection_system_transfer(cst_id)
                cruise_or_lowering = cst_cfg.get('cruiseOrLowering')
                dest_dir = cst_cfg.get('destDir')

                if cruise_or_lowering == '0':
                    # Cruise-level exclusion
                    exclude_filterlist.append(f"/{dest_dir.replace('{cruiseID}', self.cruise_id)}/*")
                else:
                    # Lowering-level exclusions
                    for lowering in lowerings:
                        filter_path = dest_dir.replace('{cruiseID}', self.cruise_id).replace('{loweringID}', lowering)
                        exclude_filterlist.append(f"/{os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], lowering, filter_path)}/*")

            except Exception as err:
                logging.warning("Could not retrieve collection system transfer %s: %s", cst_id, err)

        # Handle excluded extra directories
        ex_ed_ids = cdt_cfg.get('excludedExtraDirectories', '').split(',') if cdt_cfg.get('excludedExtraDirectories') else []

        for ed_id in filter(lambda x: x and x != '0', ex_ed_ids):
            try:
                ed_cfg = self.ovdm.get_extra_directory(ed_id)
                cruise_or_lowering = ed_cfg.get('cruiseOrLowering')
                dest_dir = ed_cfg.get('destDir')

                if cruise_or_lowering == '0':
                    # Cruise-level exclusion
                    exclude_filterlist.append(f"/{dest_dir.replace('{cruiseID}', self.cruise_id)}/*")
                else:
                    # Lowering-level exclusions
                    for lowering in lowerings:
                        filter_path = dest_dir.replace('{cruiseID}', self.cruise_id).replace('{loweringID}', lowering)
                        exclude_filterlist.append(f"/{os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], lowering, filter_path)}/*")

            except Exception as err:
                logging.warning("Could not retrieve extra directory %s: %s", ed_id, err)

        exclude_filterlist = [ self.cruise_id + path_filter for path_filter in exclude_filterlist ]

        logging.debug("Exclude filters: %s", json.dumps(exclude_filterlist, indent=2))
        return exclude_filterlist


    def run_transfer_command(self, current_job, command, file_count):
        """
        run the rsync command and return the list of new/updated files
        """

        # if there are no files to transfer, then don't
        if file_count == 0:
            logging.debug("Skipping Transfer Command: nothing to transfer")
            return [], []

        logging.debug('Transfer Command: %s', ' '.join(command))

        # file_index = 0
        new_files = []
        updated_files = []
        last_percent_reported = -1

        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while proc.poll() is None:

            for line in proc.stdout:

                if self.stop:
                    logging.debug("Stopping")
                    proc.terminate()
                    break

                line = line.strip()

                if not line:
                    continue

                if line.startswith(('>f+', '<f+')):
                    new_files.append(line.split(' ', 1)[1].rstrip('\n'))
                elif line.startswith(('>f.', '<f.')):
                    updated_files.append(line.split(' ', 1)[1].rstrip('\n'))

                # Extract progress from `to-chk=` lines
                match = TO_CHK_RE.search(line)
                if match:
                    remaining = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        percent = int(100 * (total - remaining) / total)

                        if percent != last_percent_reported:
                            logging.info("Progress Update: %d%%", percent)
                            self.send_job_status(current_job, int(75 * percent/100) + 20, 100)
                            last_percent_reported = percent

        return new_files, updated_files


    def transfer_to_destination(self, current_job):
        """
        Unified transfer function to handle local, SMB, rsync, and SSH transfers
        """

        cdt_cfg = self.cruise_data_transfer
        transfer_type = get_transfer_type(cdt_cfg['transferType'])

        if not transfer_type:
            logging.error("Unknown Transfer Type")
            return {'verdict': False, 'reason': 'Unknown Transfer Type'}

        files = { 'new':[], 'updated':[], 'exclude': [] }
        is_darwin = False

        def _build_rsync_command(flags, extra_args, source_dir, dest_dir, exclude_file_path=None):
            cmd = ['rsync'] + flags
            if extra_args is not None:
                cmd += extra_args

            if exclude_file_path is not None:
                cmd.append(f"--exclude-from={exclude_file_path}")

            cmd += [source_dir, dest_dir.rstrip('/')+'/']
            return cmd

        def _build_exclude_file(exclude_list, filepath):
            try:
                with open(filepath, mode='w', encoding="utf-8") as f:
                    f.write('\n'.join(exclude_list))
                    f.write('\0')
            except IOError as e:
                logging.error("Error writing exclude file: %s", e)
                return False

            return True

        with temporary_directory() as tmpdir:
            exclude_file = os.path.join(tmpdir, 'rsyncExcludeList.txt')
            exclude_list = self.build_exclude_filterlist()
            if not _build_exclude_file(exclude_list, exclude_file):
                return {'verdict': False, 'reason': 'Failed to write exclude file'}

            if transfer_type == 'smb':
                # Mount SMB Share
                mntpoint = os.path.join(tmpdir, 'mntpoint')
                os.mkdir(mntpoint, 0o755)
                smb_version = detect_smb_version(cdt_cfg)
                success = mount_smb_share(cdt_cfg, mntpoint, smb_version)
                if not success:
                    return {'verdict': False, 'reason': 'Failed to mount SMB share'}
                dest_dir = os.path.join(mntpoint, cdt_cfg['destDir'].lstrip('/'))

            elif transfer_type == 'rsync':
                # Write rsync password file
                password_file = os.path.join(tmpdir, 'rsyncPass')
                with open(password_file, 'w', encoding='utf-8') as f:
                    f.write(cdt_cfg['rsyncPass'])
                os.chmod(password_file, 0o600)
                dest_dir = f"rsync://{cdt_cfg['rsyncUser']}@{cdt_cfg['rsyncServer']}{cdt_cfg['destDir']}/"

            elif transfer_type == 'ssh':

                is_darwin = check_darwin(cdt_cfg)
                dest_dir = f"{cdt_cfg['sshUser']}@{cdt_cfg['sshServer']}:{cdt_cfg['destDir']}"

            else:  # local
                dest_dir = cdt_cfg['destDir']

            # === DRY RUN ===
            dry_flags = build_rsync_options(cdt_cfg, mode='dry-run', is_darwin=is_darwin)

            extra_args = []
            if transfer_type == 'ssh':
                extra_args = ['-e', 'ssh']
            elif transfer_type == 'rsync':
                extra_args = [f"--password-file={password_file}"]

            dry_cmd = _build_rsync_command(dry_flags, extra_args, self.cruise_dir, dest_dir, exclude_file)
            if transfer_type == 'ssh' and cdt_cfg.get('sshUseKey') == '0':
                dry_cmd = ['sshpass', '-p', cdt_cfg['sshPass']] + dry_cmd

            logging.debug("Dry run command: %s", ' '.join(dry_cmd).replace(f'-p {cdt_cfg["sshPass"]}', '-p ****'))
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
                real_flags = build_rsync_options(cdt_cfg, mode='real', is_darwin=is_darwin)

                real_cmd = _build_rsync_command(real_flags, extra_args, self.cruise_dir, dest_dir, exclude_file)
                if transfer_type == 'ssh' and cdt_cfg.get('sshUseKey') == '0':
                    real_cmd = ['sshpass', '-p', cdt_cfg['sshPass']] + real_cmd

                files['new'], files['updated'] = self.run_transfer_command(current_job, real_cmd, file_count)

                # === PERMISSIONS (local only) ===
                if transfer_type == 'local' and cdt_cfg.get('localDirIsMountPoint') == '0':
                    logging.info("Setting file permissions")
                    output = set_owner_group_permissions(
                        self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'],
                        os.path.join(dest_dir, self.cruise_id)
                    )
                    if not output['verdict']:
                        return output

        return {'verdict': True, 'files': files}


    def on_job_execute(self, current_job):
        logging.debug("Received job: %s", current_job)
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("Payload: %s", current_job.data)

            cdt_id = payload_obj['cruiseDataTransfer']['cruiseDataTransferID']
            self.cruise_data_transfer = self.ovdm.get_cruise_data_transfer(cdt_id)

            if not self.cruise_data_transfer:
                self.cruise_data_transfer = {
                    'name': "Unknown Transfer"
                }

                return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                      "Could not find configuration data for cruise data transfer")

            if self.cruise_data_transfer['status'] == "1":
                logging.info("Transfer already in-progress for %s", self.cruise_data_transfer['name'])
                return self._ignore_job(current_job, "Transfer In-Progress", "Transfer is already in-progress")

        except Exception:
            logging.exception("Failed to retrieve cruise data transfer config")
            return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                  "Could not retrieve data for cruise data transfer from OpenVDM API")

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.cruise_data_transfer['name']}: %(message)s"
        ))

        logging.info("Job: %s, transfer started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.system_status = payload_obj.get('systemStatus', self.ovdm.get_system_status())
        self.cruise_data_transfer.update(payload_obj['cruiseDataTransfer'])

        if self.system_status == "Off" or self.cruise_data_transfer['enable'] == '0':
            logging.info("Transfer disabled for %s", self.cruise_data_transfer['name'])
            return self._ignore_job(current_job, "Transfer Enabled", "Transfer is disabled")

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)

    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job: %s, transfer failed at: %s", current_job.handle,
                      time.strftime("%D %T", time.gmtime()))

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        self.send_job_data(current_job, json.dumps(
            [{"partName": "Worker crashed", "result": "Fail", "reason": str(exc_type)}]
        ))

        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        if cdt_id:
            self.ovdm.set_error_cruise_data_transfer(cdt_id, f'Worker crashed: {str(exc_type)}')

        return super().on_job_exception(current_job, exc_info)

    def on_job_complete(self, current_job, job_result):
        results_obj = json.loads(job_result)

        final_part = results_obj['parts'][-1] if results_obj['parts'] else None

        if final_part:
            if final_part['result'] == "Fail" and final_part['partName'] != "Located Cruise Data Transfer Data":
                self.ovdm.set_error_cruise_data_transfer(
                    self.cruise_data_transfer['cruiseDataTransferID'], final_part['reason']
                )
            elif final_part['result'] == "Pass":
                self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])
        else:
            self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s transfer completed at: %s", current_job.handle,
                     time.strftime("%D %T", time.gmtime()))

        return super().send_job_complete(current_job, job_result)

    def stop_task(self):
        self.stop = True
        logging.warning("Stopping current task...")

    def quit_worker(self):
        self.stop = True
        logging.warning("Quitting worker...")
        self.shutdown()

    # --- Helper Methods ---

    def _fail_job(self, current_job, part_name, reason):
        """
        shortcut for completing the current job as failed
        """
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))

    def _ignore_job(self, current_job, part_name, reason):
        """
        shortcut for completing the current job as ignored
        """
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_run_cruise_data_transfer(worker, current_job):
    """
    Run the cruise data transfer
    """

    time.sleep(randint(0,2))

    cdt_cfg = worker.cruise_data_transfer

    job_results = {
        'parts': [
            {"partName": "Transfer In-Progress", "result": "Pass"},
            {"partName": "Transfer Enabled", "result": "Pass"}
        ],
        'files':{}
    }

    logging.debug("Setting transfer status to 'Running'")
    worker.ovdm.set_running_cruise_data_transfer(worker.cruise_data_transfer['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing destination")
    worker.send_job_status(current_job, 1, 10)
    results = test_cdt_destination(cdt_cfg)

    if results[-1]['result'] == "Fail": # Final Verdict
        logging.warning("Connection test failed, quitting job")
        job_results['parts'].append({"partName": "Connection Test", "result": "Fail", "reason": results[-1]['reason']})
        return json.dumps(job_results)

    logging.debug("Destination test passed")
    job_results['parts'].append({"partName": "Destination Test", "result": "Pass"})

    logging.info("Transferring files")
    worker.send_job_status(current_job, 2, 10)
    results = worker.transfer_to_destination(current_job)

    if not results['verdict']:
        logging.error("Transfer of remote files failed: %s", results['reason'])
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    logging.debug("Transfer completed successfully")
    job_results['files'] = results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s file(s) intentionally skipped", len(job_results['files']['exclude']))

    worker.send_job_status(current_job, 10, 10)

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

        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("QUIT Signal Received")
        new_worker.stop_task()

    def sigint_handler(_signo, _stack_frame):
        """
        Signal Handler for INT
        """

        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("INT Signal Received")
        new_worker.quit_worker()

    signal.signal(signal.SIGQUIT, sigquit_handler)
    signal.signal(signal.SIGINT, sigint_handler)

    logging.info("Registering worker tasks...")

    logging.info("\tTask: %s", TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'], task_run_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
