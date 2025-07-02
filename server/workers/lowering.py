#!/usr/bin/env python3
"""
FILE:  lowering.py

DESCRIPTION:  Gearman worker the handles the tasks of initializing a new
lowering and finalizing the current lowering.

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
import signal
import sys
import subprocess
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import output_json_data_to_file, set_owner_group_permissions
from server.workers.md5_summary import TASK_NAMES as MD5_TASK_NAMES
from server.lib.openvdm import OpenVDM

TASK_NAMES = {
    'CREATE_LOWERING': 'setupNewLowering',
    'FINALIZE_LOWERING': 'finalizeCurrentLowering',
    'EXPORT_LOWERING_CONFIG': 'exportLoweringConfig'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker): # pylint: disable=too-many-instance-attributes
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.cruise_id = None
        self.lowering_id = None
        self.lowering_start_date = None
        self.shipboard_data_warehouse_config = None
        self.lowering_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_logfile_dirpath(self):
        """
        build the path to save transfer logfiles
        """

        return os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])


    def update_md5_summary(self, files):
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


    def export_lowering_config(self, finalize=False):
        """
        Export the current OpenVDM configuration to the specified filepath
        """

        lowering_config_fn = self.shipboard_data_warehouse_config['loweringConfigFn']
        lowering_config_relfilepath = os.path.join(self.lowering_dir, lowering_config_fn)
        lowering_config_filepath = os.path.join(self.cruise_dir, lowering_config_relfilepath)
        lowering_config = self.ovdm.get_lowering_config()

        if finalize:
            lowering_config['loweringFinalizedOn'] = lowering_config['configCreatedOn']
        elif os.path.isfile(lowering_config_filepath):
            logging.info("Reading existing configuration file")
            try:
                with open(lowering_config_filepath, mode='r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    lowering_config['loweringFinalizedOn'] = existing_data.get('loweringFinalizedOn')
            except OSError as err:
                logging.debug(str("Error reading config: %s", err))
                return {'verdict': False, 'reason': "Unable to read existing configuration file"}

        logging.debug(json.dumps(lowering_config))

        def scrub_transfers(transfer_list):
            for transfer in transfer_list:

                allowed_keys = ['name', 'longName', 'destDir']
                for key in list(transfer.keys()):
                    if key not in allowed_keys:
                        transfer.pop(key)

        scrub_transfers(lowering_config.get('collectionSystemTransfersConfig', []))

        results = output_json_data_to_file(lowering_config_filepath, lowering_config)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], lowering_config_filepath)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        self.update_md5_summary({'new':[], 'updated':[lowering_config_relfilepath]})

        return {'verdict': True}


    def on_job_execute(self, current_job):
        """
        Function run whenever a new job arrives
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
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())

        self.lowering_start_date = payload_obj.get('loweringStartDate', self.ovdm.get_lowering_start_date())
        self.lowering_end_date = payload_obj.get('loweringEndDate', self.ovdm.get_lowering_end_date())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.lowering_dir = os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
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
        Function run whenever the current job completes
        """

        results = json.loads(job_result)

        if current_job.task in (TASK_NAMES['CREATE_LOWERING'], TASK_NAMES['FINALIZE_LOWERING']):
            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            job_data = {
                'cruiseID': self.cruise_id,
                'loweringID': self.lowering_id,
                'loweringStartDate': self.lowering_start_date,
                'loweringEndDate': self.lowering_end_date
            }

            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        parts = results.get('parts', [])
        last_part = parts[-1] if parts else None

        if last_part and last_part.get('result') == "Fail":
            reason = last_part.get('reason', 'Unknown failure')
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
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def task_setup_new_lowering(worker, current_job):
    """
    Setup a new lowering
    """

    job_results = {'parts':[]}

    logging.info('Setting up new lowering')
    worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    logging.info("Creating lowering data directory")
    worker.send_job_status(current_job, 2, 10)

    completed_job_request = gm_client.submit_job("createLoweringDirectory", current_job.data)

    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to create lowering data directory")
        job_results['parts'].append({"partName": "Create lowering data directory structure", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create lowering data directory structure", "result": "Pass"})


    logging.info("Exporting Lowering Configuration")
    worker.send_job_status(current_job, 5, 10)

    output_results = worker.export_lowering_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    logging.info("Update Lowering Size")
    worker.send_job_status(current_job, 9, 10)

    lowering_size_proc = subprocess.run(['du','-sb', os.path.join(worker.cruise_dir, worker.lowering_dir)], capture_output=True, text=True, check=False)
    if lowering_size_proc.returncode == 0:
        logging.info("Lowering Size: %s", lowering_size_proc.stdout.split()[0])
        worker.ovdm.set_lowering_size(lowering_size_proc.stdout.split()[0])
    else:
        worker.ovdm.set_lowering_size("0")

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)

def task_finalize_current_lowering(worker, current_job):
    """
    Finalize the current lowering
    """

    job_results = {'parts':[]}

    logging.info("Finalizing current lowering")
    worker.send_job_status(current_job, 1, 10)

    full_lowering_dir = os.path.join(worker.cruise_dir, worker.lowering_dir)

    if not os.path.exists(full_lowering_dir):
        job_results['parts'].append({"partName": "Verify lowering directory exists", "result": "Fail", "reason": f"lowering directory: {full_lowering_dir} could not be found"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify lowering directory exists", "result": "Pass"})

    logging.info("Queuing Collection System Transfers")
    worker.send_job_status(current_job, 2, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    gm_data = {
        'loweringID': worker.lowering_id,
        'loweringStartDate': worker.lowering_start_date,
        'loweringEndDate': worker.lowering_end_date,
        'systemStatus': "On",
        'collectionSystemTransfer': {}
    }

    collection_system_transfer_jobs = []
    collection_system_transfers = worker.ovdm.get_active_collection_system_transfers(cruise=False)

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

    logging.info("Exporting Lowering Configuration")
    worker.send_job_status(current_job, 9, 10)

    output_results = worker.export_lowering_config(finalize=True)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_export_lowering_config(worker, current_job):
    """
    Export the lowering configuration to file
    """

    job_results = {'parts':[]}

    logging.info("Exporting Lowering Configuration")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.export_lowering_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle Lowering-Level tasks')
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

    # global new_worker
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

    logging.info("\tTask: %s", TASK_NAMES['CREATE_LOWERING'])
    new_worker.register_task(TASK_NAMES['CREATE_LOWERING'], task_setup_new_lowering)

    logging.info("\tTask: %s", TASK_NAMES['FINALIZE_LOWERING'])
    new_worker.register_task(TASK_NAMES['FINALIZE_LOWERING'], task_finalize_current_lowering)

    logging.info("\tTask: %s", TASK_NAMES['EXPORT_LOWERING_CONFIG'])
    new_worker.register_task(TASK_NAMES['EXPORT_LOWERING_CONFIG'], task_export_lowering_config)

    logging.info("Waiting for jobs...")
    new_worker.work()
