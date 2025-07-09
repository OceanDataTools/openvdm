#!/usr/bin/env python3
"""
FILE:  run_ship_to_shore_transfer.py

DESCRIPTION:  Gearman worker that handles the transfer of data from the
    Shipboard Data Warehouse to a Shoreside Data Warehouse.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2017-09-30
 REVISION:  2025-07-06
"""

import argparse
import fnmatch
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
from server.lib.file_utils import output_json_data_to_file, set_owner_group_permissions, temporary_directory
from server.lib.connection_utils import build_rsync_options, check_darwin, test_cdt_destination
from server.lib.openvdm import OpenVDM

TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

TASK_NAMES = {
    'RUN_SHIP_TO_SHORE_TRANSFER': 'runShipToShoreTransfer'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.lowerings = None
        self.system_status = None
        self.transfer_start_date = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        self.cruise_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_filelist(self, is_darwin, batch_size=500, max_workers=16):
        """
        Build the list of files for the ship-to-shore transfer
        """

        def _build_filters(transfer):
            """
            Replace any wildcards in the provided filters
            """

            def _expand_placeholders(template: str, context: dict) -> str:
                for key, value in context.items():
                    template = template.replace(key, value)
                return template


            context = {
                '{cruiseID}': self.cruise_id
                #'{loweringID}': self.lowering_id or '{loweringID}'
            }

            raw = transfer.get('includeFilter', '')
            expanded = _expand_placeholders(raw, context)

            return expanded.split(',')

        transfers = (
            self.ovdm.get_ship_to_shore_transfers()
            + self.ovdm.get_required_ship_to_shore_transfers()
        )

        logging.debug('shipToShoreTransfers: %s', json.dumps(transfers, indent=2))

        proc_filters = []

        for priority in map(str, range(1, 6)):
            for t in transfers:
                if t['priority'] != priority or t['enable'] != '1':
                    continue

                raw_filters = _build_filters(t)
                logging.debug("Raw Filters: %s", json.dumps(raw_filters, indent=2))

                base_path = f"*/{self.cruise_id}"

                if t['collectionSystem'] != "0":
                    cs = self.ovdm.get_collection_system_transfer(t['collectionSystem'])
                    if cs['cruiseOrLowering'] == '1':
                        base_path = f"{base_path}/{self.shipboard_data_warehouse_config['loweringDataBaseDir']}/{{loweringID}}"
                    path_prefix = f"{base_path}/{cs['destDir']}"
                elif t['extraDirectory'] != "0":
                    ed = self.ovdm.get_extra_directory(t['extraDirectory'])
                    if ed['cruiseOrLowering'] == '1':
                        base_path = f"{base_path}/{self.shipboard_data_warehouse_config['loweringDataBaseDir']}/{{loweringID}}"
                    path_prefix = f"{base_path}/{ed['destDir']}"
                else:
                    path_prefix = base_path

                expanded_filters = []
                for flt in raw_filters:
                    if "{loweringID}" in flt:
                        expanded_filters.extend(
                            flt.replace("{loweringID}", lid) for lid in self.lowerings
                        )
                    else:
                        expanded_filters.append(flt)

                logging.debug("Expanded Filters: %s", json.dumps(expanded_filters, indent=2))

                proc_filters.extend(f"{path_prefix}/{f}" for f in expanded_filters)

        logging.debug("Processed Filters: %s", json.dumps(proc_filters, indent=2))

        return_files = {'include': [], 'new': [], 'updated': [], 'exclude': []}
        for root, _, files in os.walk(self.cruise_dir):
            for f in files:
                full_path = os.path.join(root, f)
                if any(fnmatch.fnmatch(full_path, flt) for flt in proc_filters):
                    return_files['include'].append(full_path)

        return_files['include'] = [
            f.replace(f'{self.cruise_dir}/', '', 1) for f in return_files['include']
        ]

        logging.debug("Returned Files: %s", json.dumps(return_files, indent=2))

        return {'verdict': True, 'files': return_files}


        # logging.debug("Building filters")
        # raw_filters = {'includeFilter':[]}
        # ship_to_shore_transfers = self.ovdm.get_ship_to_shore_transfers() + self.ovdm.get_required_ship_to_shore_transfers()

        # logging.debug('shipToShoreTransfers: %s', json.dumps(ship_to_shore_transfers, indent=2))

        # for priority in range(1, 6):
        #     for ship_to_shore_transfer in ship_to_shore_transfers:
        #         if ship_to_shore_transfer['priority'] == str(priority) and ship_to_shore_transfer['enable'] == '1':
        #             if not ship_to_shore_transfer['collectionSystem'] == "0":
        #                 collection_system = self.ovdm.get_collection_system_transfer(ship_to_shore_transfer['collectionSystem'])
        #                 raw_filters['includeFilter'] += [f"*/{self.cruise_id}/{collection_system['destDir']}/{ship_to_shore_filter}" for ship_to_shore_filter in ship_to_shore_transfer['includeFilter'].split(',')]
        #             elif not ship_to_shore_transfer['extraDirectory'] == "0":
        #                 extra_directory = self.ovdm.get_extra_directory(ship_to_shore_transfer['extraDirectory'])
        #                 raw_filters['includeFilter'] += [f"*/{self.cruise_id}/{extra_directory['destDir']}/{ship_to_shore_filter}" for ship_to_shore_filter in ship_to_shore_transfer['includeFilter'].split(',')]
        #             else:
        #                 raw_filters['includeFilter'] += [f"*/{self.cruise_id}/{ship_to_shore_filter}" for ship_to_shore_filter in ship_to_shore_transfer['includeFilter'].split(',')]

        # logging.debug("Raw Filters: %s", json.dumps(raw_filters, indent=2))

        # proc_filters = build_filters(self, raw_filters)
        # logging.debug("Processed Filters: %s", json.dumps(raw_filters, indent=2))

        # cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        # return_files = {'include':[], 'new':[], 'updated':[], 'exclude':[]}
        # for root, _, filenames in os.walk(cruise_dir):
        #     for filename in filenames:
        #         for include_filter in proc_filters['includeFilter']:
        #             if fnmatch.fnmatch(os.path.join(root, filename), include_filter):
        #                 return_files['include'].append(os.path.join(root, filename))

        # return_files['include'] = [filename.replace(f'{cruise_dir}/', '', 1) for filename in return_files['include']]

        # logging.debug("Returned Files: %s", json.dumps(return_files, indent=2))

        # return { 'verdict': True, 'files': return_files }


    def build_logfile_dirpath(self):
        """
        Build the path for saving the transfer logfile
        """

        cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return os.path.join(cruise_dir, self.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])


    def run_transfer_command(self, current_job, command, file_count):
        """
        Run the rsync command and return the list of new/updated files
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
        Transfer the files to a destination on a ssh server
        """

        cdt_cfg = self.cruise_data_transfer
        is_darwin = False

        def _build_rsync_command(flags, extra_args, source_dir, dest_dir, include_file_path=None):
            cmd = ['rsync'] + flags
            if extra_args is not None:
                cmd += extra_args

            if include_file_path is not None:
                cmd.append(f"--files-from={include_file_path}")

            cmd += [source_dir, dest_dir.rstrip('/')+'/']
            return cmd

        def _build_include_file(include_list, filepath):
            try:
                with open(filepath, mode='w', encoding="utf-8") as f:
                    logging.debug('\n'.join(include_list))
                    logging.debug('\0')
                    f.write('\n'.join(include_list))
                    f.write('\0')
            except IOError as exc:
                logging.error("Error writing include file: %s", str(exc))
                return False

            return True

        with temporary_directory() as tmpdir:
            is_darwin = check_darwin(cdt_cfg)
            dest_dir = f"{cdt_cfg['sshUser']}@{cdt_cfg['sshServer']}:{cdt_cfg['destDir']}"

            include_file = os.path.join(tmpdir, 'rsyncFileList.txt')

            # Build filelist (from local, SMB mount, etc.)
            results = self.build_filelist(is_darwin)

            if not results['verdict']:
                return {'verdict': False, 'reason': results.get('reason', 'Unknown')}

            files = results['files']
            logging.debug("files: %s", json.dumps(files, indent=2))

            if not _build_include_file(files['include'], include_file):
                return {'verdict': False, 'reason': 'Failed to write include file'}

            real_flags = build_rsync_options(cdt_cfg, mode='real', is_darwin=is_darwin)
            extra_args = ['-e', 'ssh']

            cmd = _build_rsync_command(real_flags, extra_args, self.cruise_dir, dest_dir, include_file)
            if cdt_cfg.get('sshUseKey') == '0':
                cmd = ['sshpass', '-p', cdt_cfg['sshPass']] + cmd

            logging.debug('Transfer Command: %s', ' '.join(cmd))
            files['new'], files['updated'] = self.run_transfer_command(current_job, cmd, len(files['include']))
            return {'verdict': True, 'files': files}

    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """

        logging.debug("current_job: %s", current_job)
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("Payload: %s", current_job.data)

            self.cruise_data_transfer = self.ovdm.get_required_cruise_data_transfer_by_name("SSDW")

            if not self.cruise_data_transfer:
                self.cruise_data_transfer = {
                    'name': "UNKNOWN"
                }

                return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                      "Could not find configuration data for cruise data transfer")

            self.cruise_data_transfer.update(payload_obj.get('cruiseDataTransfer', {}))

            logging.debug('bandwidthLimitStatus: %s', payload_obj.get('bandwidthLimitStatus', self.ovdm.get_ship_to_shore_bw_limit_status()))
            if not payload_obj.get('bandwidthLimitStatus', self.ovdm.get_ship_to_shore_bw_limit_status()):
                self.cruise_data_transfer['bandwidthLimit'] = '0'

        except Exception:
            logging.exception("Failed to retrieve cruise data transfer config")
            return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                  "Could not retrieve data for cruise data transfer from OpenVDM API")

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.cruise_data_transfer['name']}: %(message)s"
        ))

        # verify the transfer is NOT already in-progress
        if self.cruise_data_transfer['status'] == "1":
            logging.info("Transfer already in-progress for %s", self.cruise_data_transfer['name'])
            return self._ignore_job(current_job, "Transfer In-Progress", "Transfer is already in-progress")

        start_time = time.gmtime()
        self.transfer_start_date = time.strftime("%Y%m%dT%H%M%SZ", start_time)

        logging.info("Job: %s, transfer started at: %s", current_job.handle, time.strftime("%D %T", start_time))

        self.system_status = payload_obj.get('systemStatus', self.ovdm.get_system_status())

        if self.system_status == "Off" or self.cruise_data_transfer['enable'] == '0':
            logging.info("Transfer disabled for %s", self.cruise_data_transfer['name'])
            return self._ignore_job(current_job, "Transfer Enabled", "Transfer is disabled")

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowerings = self.ovdm.get_lowerings()
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
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)
        parts = results.get('parts', [])
        final_verdict = parts[-1] if parts else None
        logging.debug(self.cruise_data_transfer)

        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job: %s transfer completed at: %s", current_job.handle,
                     time.strftime("%D %T", time.gmtime()))

        if not cdt_id:
            return super().send_job_complete(current_job, job_result)

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', "undefined")
            self.ovdm.set_error_cruise_data_transfer(cdt_id, reason)
            return super().send_job_complete(current_job, job_result)

        # Always set idle at the end if not failed
        self.ovdm.set_idle_cruise_data_transfer(cdt_id)

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


    # --- Helper Methods ---
    def _fail_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as failed
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


    def _ignore_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as ignored
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_run_ship_to_shore_transfer(worker, current_job): # pylint: disable=too-many-statements
    """
    Perform the ship-to-shore transfer
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
    worker.ovdm.set_running_cruise_data_transfer(cdt_cfg['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing configuration")
    worker.send_job_status(current_job, 1, 10)

    results = test_cdt_destination(cdt_cfg)

    if results[-1]['result'] == "Fail": # Final Verdict
        logging.warning("Connection test failed, quitting job")
        job_results['parts'].append({"partName": "Connection Test", "result": "Fail", "reason": results[-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Destination Test", "result": "Pass"})

    logging.info("Transferring files")
    worker.send_job_status(current_job, 2, 10)

    results = worker.transfer_to_destination(current_job)

    if not results['verdict']:
        logging.error("Transfer of remote files failed: %s", results['reason'])
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    job_results['files'] = results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s file(s) intentionally skipped", len(job_results['files']['exclude']))
    if job_results['files'].get('deleted') and len(job_results['files']['deleted']) > 0:
        logging.debug("%s file(s) deleted", len(job_results['files']['deleted']))

    if job_results['files']['new'] or job_results['files']['updated']:
        logging.info("Writing transfer logfile")
        worker.send_job_status(current_job, 9, 10)

        logfile_filename = f"{cdt_cfg['name']}_{worker.transfer_start_date}.log"
        logfile_contents = {
            'files': {
                'new': job_results['files']['new'],
                'updated': job_results['files']['updated']
            }
        }

        results = output_json_data_to_file(os.path.join(worker.build_logfile_dirpath(), logfile_filename), logfile_contents['files'])

        if not results['verdict']:
            logging.error("Error writing transfer logfile: %s", logfile_filename)
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Fail", "reason": results['reason']})
            return json.dumps(job_results)

        results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(worker.build_logfile_dirpath(), logfile_filename))

        if not results['verdict']:
            job_results['parts'].append({"partName": "Set OpenVDM config file ownership/permissions", "result": "Fail", "reason": results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Write transfer logfile", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle ship-to-shore transfer related tasks')
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

    new_worker = OVDMGearmanWorker()
    new_worker.set_client_id(__file__)

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

    logging.info("\tTask: %s", TASK_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'], task_run_ship_to_shore_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
