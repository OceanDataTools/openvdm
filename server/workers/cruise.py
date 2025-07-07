#!/usr/bin/env python3
"""
FILE:  cruise.py

DESCRIPTION:  Gearman worker the handles the tasks of initializing a new cruise
    and finalizing the current cruise.  This includes initializing/finalizing
    the data dashboard, MD5summary and transfer log summary.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2015-01-01
 REVISION:  2025-07-06
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.connection_utils import build_rsync_command
from server.lib.file_utils import build_filelist, build_include_file, clear_directory, delete_from_dest, output_json_data_to_file, set_owner_group_permissions, temporary_directory
from server.workers.run_collection_system_transfer import run_transfer_command
from server.workers.cruise_directory import TASK_NAMES as CRUISE_DIR_TASK_NAMES
from server.workers.data_dashboard import TASK_NAMES as DATA_DASHBOARD_TASK_NAMES
from server.workers.md5_summary import TASK_NAMES as MD5_TASK_NAMES

from server.lib.openvdm import OpenVDM

TASK_NAMES = {
    'CREATE_CRUISE': 'setupNewCruise',
    'FINALIZE_CRUISE': 'finalizeCurrentCruise',
    'EXPORT_CRUISE_CONFIG': 'exportOVDMConfig',
    'SYNC_PUBLICDATA': 'rsyncPublicDataToCruiseData'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.cruise_id = None
        self.cruise_dir = None
        self.cruise_start_date = None
        self.shipboard_data_warehouse_config = None
        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_logfile_dirpath(self):
        """
        Build the path to save transfer logfiles
        """

        return os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])


    def update_md5_summary(self, files):
        """
        Submit list of files to be processed and added to the MD5 summary file
        """

        gm_data = {
            'cruiseID': self.cruise_id,
            'files': {
                'new': files.get('new', []),
                'updated': files.get('updated', []),
                'deleted': files.get('deleted', [])
            }
        }

        gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])
        gm_client.submit_job(MD5_TASK_NAMES['UPDATE_MD5_SUMMARY'], json.dumps(gm_data))

        logging.debug("MD5 Summary Task Complete")


    def export_cruise_config(self, finalize=False):
        """
        Export the current cruise configuration to file.
        if 'finalize' is true, mark the config as finalized.
        """

        cruise_config_fn = self.shipboard_data_warehouse_config['cruiseConfigFn']
        cruise_config_file_path = os.path.join(self.cruise_dir, cruise_config_fn)
        cruise_config = self.ovdm.get_cruise_config()

        if finalize:
            cruise_config['cruiseFinalizedOn'] = cruise_config['configCreatedOn']
        elif os.path.isfile(cruise_config_file_path):
            logging.debug("Reading existing configuration file")
            try:
                with open(cruise_config_file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    cruise_config['cruiseFinalizedOn'] = existing_data.get('cruiseFinalizedOn')
            except OSError as exc:
                logging.debug("Error reading config: %s", str(exc))
                return {'verdict': False, 'reason': "Unable to read existing configuration file"}

        def scrub_transfers(transfer_list):
            for transfer in transfer_list:

                allowed_keys = ['name', 'longName', 'destDir']
                for key in list(transfer.keys()):
                    if key not in allowed_keys:
                        transfer.pop(key)

        scrub_transfers(cruise_config.get('collectionSystemTransfersConfig', []))
        scrub_transfers(cruise_config.get('extraDirectoriesConfig', []))

        cruise_config['md5SummaryFn'] = cruise_config['warehouseConfig']['md5SummaryFn']
        cruise_config['md5SummaryMd5Fn'] = cruise_config['warehouseConfig']['md5SummaryMd5Fn']

        del cruise_config['warehouseConfig']
        del cruise_config['cruiseDataTransfersConfig']
        del cruise_config['shipToShoreTransfersConfig']

        results = output_json_data_to_file(cruise_config_file_path, cruise_config)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], cruise_config_file_path)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        self.update_md5_summary({'new':[], 'updated':[cruise_config_fn]})

        return {'verdict': True}


    def transfer_publicdata_dir(self, current_job, start_status, end_status):
        """
        Transfer the contents of the PublicData share to the cruise data directory
        """

        source_dir = self.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir']
        from_publicdata_dir = self.ovdm.get_required_extra_directory_by_name('From_PublicData')['destDir']
        dest_dir = os.path.join(self.cruise_dir, from_publicdata_dir)

        logging.debug("Verify PublicData Directory exists")
        if not os.path.exists(source_dir):
            return {'verdict': False, "reason": f"PublicData directory: {source_dir} could not be found"}

        logging.debug("Verify From_PublicData directory exists within the cruise data directory")
        if not os.path.exists(dest_dir):
            return {'verdict': False, "reason": f"From_PublicData directory: {dest_dir} could not be found"}

        logging.debug("Building file list")
        files = build_filelist(source_dir)
        logging.debug("Files: %s", json.dumps(files, indent=2))
        self.send_job_status(current_job, int((end_status - start_status) * 10/100) + start_status, 100)

        if len(files['exclude']) > 0:
            logging.warning("Found %s problem filename(s):", len(files['exclude']))
            logging.warning("\t %s", "\n\t".join(files['exclude']))

        logfile_filename = 'PublicData_Exclude.log'
        logfile_filepath = os.path.join(self.build_logfile_dirpath(), logfile_filename)
        logfile_contents = {
            'files': {
                'exclude': files['exclude']
            }
        }
        results = output_json_data_to_file(logfile_filepath, logfile_contents['files'])

        if not results['verdict']:
            return {'verdict': False, "reason": f"Error writing exclude logfile {logfile_filename}"}

        results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], logfile_filepath)

        if not results['verdict']:
            reason = f"Error setting ownership/permissions for transfer logfile: {logfile_filename}"
            logging.error(reason)
            return {'verdict': False, "reason": reason}

        with temporary_directory() as tmpdir:    # Create temp directory
            include_file = os.path.join(tmpdir, 'rsyncFileList.txt')
            if not build_include_file(files['include'], include_file):
                return {'verdict': False, 'reason': "Error Saving temporary rsync filelist file"}

            self.send_job_status(current_job, int((end_status - start_status) * 20/100) + start_status, 100)

            # Build transfer command
            rsync_flags = ['-trivm', '--progress', '--protect-args', '--min-size=1']

            cmd = build_rsync_command(rsync_flags, [], source_dir, dest_dir, include_file)

            # Transfer files
            files['new'], files['updated'] = run_transfer_command(
                self, current_job, cmd, len(files['include'])
            )

            files['new'] = [ os.path.join(from_publicdata_dir, filepath) for filepath in files['new'] ]
            files['updated'] = [ os.path.join(from_publicdata_dir, filepath) for filepath in files['updated'] ]
            self.send_job_status(current_job, int((end_status - start_status) * 70/100) + start_status, 100)

            files['deleted'] = [ os.path.join(from_publicdata_dir, filepath) for filepath in delete_from_dest(dest_dir, files['include']) ]

            results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], dest_dir)
            self.send_job_status(current_job, int((end_status - start_status) * 80/100) + start_status, 100)

            if not results['verdict']:
                return {'verdict': False, 'reason': results['reason']}

            logfile_filename = f"PublicData_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.log"
            logfile_filepath = os.path.join(self.build_logfile_dirpath(), logfile_filename)
            logfile_contents = {
                'files': {
                    'new': files['new'],
                    'updated': files['updated']
                }
            }
            results = output_json_data_to_file(logfile_filepath, logfile_contents['files'])

            if not results['verdict']:
                return {'verdict': False, "reason": f"Error writing transfer logfile {logfile_filename}"}

            results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], logfile_filepath)

            if not results['verdict']:
                reason = f"Error setting ownership/permissions for transfer logfile: {logfile_filename}"
                logging.error(reason)
                return {'verdict': False, "reason": reason}

            self.update_md5_summary(files)
            self.send_job_status(current_job, int((end_status - start_status) * 90/100) + start_status, 100)

            return {'verdict': True}


    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """

        logging.debug("current_job: %s", current_job)
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)
        except Exception:
            reason = "Failed to parse current job payload"
            logging.exception(reason)
            return self._fail_job(current_job, "Retrieve job data", reason)

        self.task = self.ovdm.get_task_by_name(current_job.task)

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)

        logging.info("Job: %s started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.cruise_start_date = payload_obj.get('cruiseStartDate', self.ovdm.get_cruise_start_date())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job: %s failed at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        self.send_job_data(current_job, json.dumps(
            [{"partName": "Worker crashed", "result": "Fail", "reason": str(exc_type)}]
        ))

        if int(self.task['taskID']) > 0:
            self.ovdm.set_error_task(self.task['taskID'], f'Worker crashed: {str(exc_type)}')
        else:
            self.ovdm.send_msg(self.task['longName'] + ' failed', f'Worker crashed: {str(exc_type)}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)

        if current_job.task in (TASK_NAMES['CREATE_CRUISE'], TASK_NAMES['FINALIZE_CRUISE']):
            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            job_data = {
                'cruiseID': self.cruise_id,
                'cruiseStartDate': self.cruise_start_date
            }

            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        parts = results.get('parts', [])
        final_verdict = parts[-1] if parts else None

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', 'Unknown failure')
            if int(self.task['taskID']) > 0:
                self.ovdm.set_error_task(self.task['taskID'], reason)
            else:
                self.ovdm.send_msg(f"{self.task['longName']} failed", reason)
        else:
            self.ovdm.set_idle_task(self.task['taskID'])

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job: %s completed at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        return super().send_job_complete(current_job, job_result)


    def stop_task(self):
        """
        Stop the current job
        """

        self.stop = True
        logging.warning("Stopping current task...")


    def quit_worker(self):
        """
        Quit the worker
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
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def task_setup_new_cruise(worker, current_job): # pylint: disable=too-many-return-statements,too-many-statements
    """
    Setup a new cruise
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    logging.info("Set ownership/permissions for the CruiseData directory")
    completed_job_request = gm_client.submit_job(CRUISE_DIR_TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'], current_job.data)
    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to lockdown the CruiseData directory")
        job_results['parts'].append({"partName": "Set ownership/permissions for CruiseData directory", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set ownership/permissions for CruiseData directory", "result": "Pass"})

    logging.info("Creating cruise data directory")
    worker.send_job_status(current_job, 2, 10)

    completed_job_request = gm_client.submit_job(CRUISE_DIR_TASK_NAMES['CREATE_CRUISE_DIRECTORY'], current_job.data)

    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to create cruise data directory")
        job_results['parts'].append({"partName": "Create cruise data directory structure", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create cruise data directory structure", "result": "Pass"})

    logging.info("Creating MD5 summary files")
    worker.send_job_status(current_job, 5, 10)

    completed_job_request = gm_client.submit_job(MD5_TASK_NAMES['REBUILD_MD5_SUMMARY'], current_job.data)

    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to create MD5 summary files")
        job_results['parts'].append({"partName": "Create MD5 summary files", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create MD5 summary files", "result": "Pass"})

    logging.info("Exporting cruise configuration")
    worker.send_job_status(current_job, 6, 10)

    output_results = worker.export_cruise_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})

    logging.info("Creating data dashboard directory structure and manifest file")
    worker.send_job_status(current_job, 7, 10)

    completed_job_request = gm_client.submit_job(DATA_DASHBOARD_TASK_NAMES['REBUILD_DATA_DASHBOARD'], current_job.data)

    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to create data dashboard directory structure and/or manifest file")
        job_results['parts'].append({"partName": "Create data dashboard directory structure and manifest file", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create data dashboard directory structure and manifest file", "result": "Pass"})

    if worker.ovdm.get_transfer_public_data():
        logging.info("Clear out PublicData directory")
        worker.send_job_status(current_job, 9, 10)

        results = clear_directory(worker.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir'])

        if not results['verdict']: # Final Verdict
            logging.error("Failed to clear out PublicData directory")
            job_results['parts'].append({"partName": "Clear out PublicData directory", "result": "Fail", "reason": results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Clear out PublicData directory", "result": "Pass"})

    logging.info("Updating cruise size")
    worker.send_job_status(current_job, 9, 10)

    cruise_size_proc = subprocess.run(['du','-sb', worker.cruise_dir], capture_output=True, text=True, check=False)
    if cruise_size_proc.returncode == 0:
        logging.info("Cruise Size: %s", cruise_size_proc.stdout.split()[0])
        worker.ovdm.set_cruise_size(cruise_size_proc.stdout.split()[0])
    else:
        worker.ovdm.set_cruise_size("0")

    worker.ovdm.set_lowering_size("0")

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_finalize_current_cruise(worker, current_job): # pylint: disable=too-many-return-statements,too-many-statements
    """
    Finalize the current cruise
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    if not os.path.exists(worker.cruise_dir):
        reason = f"Cruise directory does not exist: {worker.cruise_dir}"
        logging.error(reason)
        job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Pass"})

    logging.info("Queuing collection system transfers jobs")
    worker.send_job_status(current_job, 2, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    gm_data = {
        'cruiseID': worker.cruise_id,
        'cruiseStartDate': worker.cruise_start_date,
        'systemStatus': "On",
        'collectionSystemTransfer': {}
    }

    collection_system_transfer_jobs = []
    collection_system_transfers = worker.ovdm.get_active_collection_system_transfers(lowering=False)

    for collection_system_transfer in collection_system_transfers:
        logging.debug("Queuing runCollectionSystemTransfer job for %s", collection_system_transfer['name'])
        gm_data['collectionSystemTransfer']['collectionSystemTransferID'] = collection_system_transfer['collectionSystemTransferID']

        collection_system_transfer_jobs.append( {"task": "runCollectionSystemTransfer", "data": json.dumps(gm_data)} )

    logging.info("Submitting runCollectionSystemTransfer jobs")
    worker.send_job_status(current_job, 3, 10)

    submitted_job_request = gm_client.submit_multiple_jobs(collection_system_transfer_jobs, background=False, wait_until_complete=False)

    time.sleep(1)
    gm_client.wait_until_jobs_completed(submitted_job_request)

    job_results['parts'].append({"partName": "Run Collection System Transfers jobs", "result": "Pass"})

    if worker.ovdm.get_transfer_public_data():
        logging.debug("Transferring public data files to cruise data directory")
        worker.send_job_status(current_job, 7, 10)

        output_results = worker.transfer_publicdata_dir(current_job, 70, 90)
        logging.debug("Transfer Complete")

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Transfer PublicData files", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Transfer PublicData files", "result": "Pass"})

    logging.info("Exporting cruise configuration")
    worker.send_job_status(current_job, 9, 10)

    output_results = worker.export_cruise_config(finalize=True)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_rsync_publicdata_to_cruise_data(worker, current_job):
    """
    Sync the contents of the PublicData share to the from_PublicData extra directory
    """

    job_results = {'parts':[]}

    logging.info("Transferring files from PublicData to the cruise data directory")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.transfer_publicdata_dir(current_job, 10, 90)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Transfer files", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Transfer files", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_export_cruise_config(worker, current_job):
    """
    Export the OpenVDM configuration to file
    """

    job_results = {'parts':[]}

    logging.info("Exporting cruise configuration")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.export_cruise_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle Cruise-Level tasks')
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

    # global new_worker
    new_worker = OVDMGearmanWorker()
    new_worker.set_client_id(__file__)

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

    logging.info("\tTask: %s", TASK_NAMES.get('CREATE_CRUISE'))
    new_worker.register_task(TASK_NAMES.get('CREATE_CRUISE'), task_setup_new_cruise)

    logging.info("\tTask: %s", TASK_NAMES.get('FINALIZE_CRUISE'))
    new_worker.register_task(TASK_NAMES.get('FINALIZE_CRUISE'), task_finalize_current_cruise)

    logging.info("\tTask: %s", TASK_NAMES.get('EXPORT_CRUISE_CONFIG'))
    new_worker.register_task(TASK_NAMES.get('EXPORT_CRUISE_CONFIG'), task_export_cruise_config)

    logging.info("\tTask: %s", TASK_NAMES.get('SYNC_PUBLICDATA'))
    new_worker.register_task(TASK_NAMES.get('SYNC_PUBLICDATA'), task_rsync_publicdata_to_cruise_data)

    logging.info("Waiting for jobs...")
    new_worker.work()
