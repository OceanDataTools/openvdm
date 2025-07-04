#!/usr/bin/env python3
"""
FILE:  lowering_directory.py

DESCRIPTION:  Gearman worker the handles the tasks of creating a new lowering
data directory and updating the lowering directory structure when additional
subdirectories must be added.

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
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import create_directories, set_owner_group_permissions
from server.lib.openvdm import OpenVDM

TASK_NAMES = {
    'CREATE_CRUISE_DIRECTORY': 'createCruiseDirectory',
    'REBUILD_CRUISE_DIRECTORY': 'rebuildCruiseDirectory',
    'SET_CRUISEDATA_PERMISSIONS': 'setCruiseDataDirectoryPermissions'
}

CUSTOM_TASKS = [
    {
        "taskID": "0",
        "name": TASK_NAMES['CREATE_CRUISE_DIRECTORY'],
        "longName": "Creating Lowering Directory",
    },
    {
        "taskID": "0",
        "name": TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'],
        "longName": "Setting Lowering Data Directory Permissions",
    }

]

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
        self.cruise_dir = None
        self.lowering_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    @staticmethod
    def _get_custom_task(current_job):
        """
        Fetch task metadata
        """

        return next((task for task in CUSTOM_TASKS if task['name'] == current_job.task), None)


    def keyword_replace(self, s):
        if not isinstance(s, str):
            return None

        return (s.replace('{cruiseID}', self.cruise_id)
                .replace('{loweringDataBaseDir}', self.shipboard_data_warehouse_config['loweringDataBaseDir'])
                .replace('{loweringID}', self.lowering_id)
                .rstrip('/')
               ) if s != '/' else s


    def build_dest_dir(self, dest_dir):
        """
        Replace any wildcards in the provided directory
        """

        return self.keyword_replace(dest_dir) if dest_dir else None


    def build_directorylist(self):
        """
        build the list of directories to be created as part of creating the new
        cruise
        """

        lowering_full_dir = os.path.join(self.cruise_dir, self.lowering_dir)

        return_directories = [ lowering_full_dir ]

        # Retrieve active collection system transfers for lowering-related transfers
        collection_system_transfers = self.ovdm.get_active_collection_system_transfers(cruise=False)
        return_directories.extend([ os.path.join(lowering_full_dir, self.build_dest_dir(collection_system_transfer['destDir'])) for collection_system_transfer in collection_system_transfers ])

        # Retrieve active collection system transfers for lowering-related extra directories
        extra_directories = self.ovdm.get_active_extra_directories(cruise=False)
        return_directories.extend([ os.path.join(lowering_full_dir, self.build_dest_dir(extra_directory['destDir'])) for extra_directory in extra_directories ])

        # Special case where an collection system needs to be created outside of the lowering directory
        collection_system_transfers = self.ovdm.get_active_collection_system_transfers(lowering=False)
        return_directories.extend([ os.path.join(self.cruise_dir, self.build_dest_dir(collection_system_transfer['destDir'])) for collection_system_transfer in collection_system_transfers if '{loweringID}' in collection_system_transfer['destDir']])

        # Special case where an extra directory needs to be created outside of the lowering directory
        extra_directories = self.ovdm.get_active_extra_directories(lowering=False)
        return_directories.extend([ os.path.join(self.cruise_dir, self.build_dest_dir(extra_directory['destDir'])) for extra_directory in extra_directories  if '{loweringID}' in extra_directory['destDir']])

        return list(set(return_directories))


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

        self.task = self._get_custom_task(current_job) or self.ovdm.get_task_by_name(current_job.task)

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        if int(self.task['taskID']) > 0:
            self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)

        logging.info("Job: %s started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())

        if not self.lowering_id:
            return self._fail_job(current_job, "Lowering ID not found", reason)

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.lowering_dir = os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id)
        self.lowering_base_dir = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir'])
        self.lowering_full_dir = os.path.join(self.cruise_dir, self.lowering_dir)

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


def task_create_lowering_directory(worker, current_job):
    """
    Setup the lowering directory for the specified lowering ID
    """

    job_results = {'parts':[]}

    payload_obj = json.loads(current_job.data)
    logging.debug("Payload: %s", json.dumps(payload_obj, indent=2))

    logging.debug("Pre-tasks checks")
    worker.send_job_status(current_job, 1, 10)

    if not os.path.exists(worker.cruise_dir):
        job_results['parts'].append({"partName": "Verify Cruise Directory exists", "result": "Fail", "reason": f"Cruise directory {worker.cruise_dir} does not exists"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify Cruise Directory exists", "result": "Pass"})

    if not os.path.exists(worker.lowering_base_dir):
        job_results['parts'].append({"partName": "Verify Lowering Base Directory exists", "result": "Fail", "reason": f"Lowering base directory {worker.lowering_base_dir} does not exists"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify Lowering Base Directory exists", "result": "Pass"})

    if os.path.exists(worker.lowering_full_dir):
        job_results['parts'].append({"partName": "Verify Lowering Directory does not exists", "result": "Fail", "reason": f"Lowering directory {worker.lowering_full_dir} already exists"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify Lowering Directory does not exists", "result": "Pass"})

    logging.debug("Build directory list")
    worker.send_job_status(current_job, 2, 10)

    directorylist = worker.build_directorylist()
    logging.debug("Directory List: %s", json.dumps(directorylist, indent=2))

    job_results['parts'].append({"partName": "Build Directory List", "result": "Pass"})

    logging.debug("Create lowering directories")
    worker.send_job_status(current_job, 5, 10)

    output_results = create_directories(directorylist)

    if not output_results['verdict']:
        logging.error("Failed to create any/all of the lowering data directory structure")
        job_results['parts'].append({"partName": "Create Directories", "result": "Fail", "reason": output_results['reason']})

    job_results['parts'].append({"partName": "Create Directories", "result": "Pass"})

    logging.debug("Set lowering directory ownership/permissions")
    worker.send_job_status(current_job, 8, 10)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.lowering_full_dir)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Set cruise directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set cruise directory ownership/permissions", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_set_lowering_data_directory_permissions(worker, current_job):
    """
    Set the permissions for the specified lowering ID
    """

    job_results = {'parts':[]}

    payload_obj = json.loads(current_job.data)
    logging.debug("Payload: %s", json.dumps(payload_obj, indent=2))

    worker.send_job_status(current_job, 1, 10)

    if os.path.isdir(worker.lowering_base_dir):
        logging.info("Set ownership and read/write permissions for lowering base directory within current cruise data directory")
        worker.send_job_status(current_job, 5, 10)

        set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.lowering_base_dir)
        job_results['parts'].append({"partName": "Set Directory Permissions for lowering data directories", "result": "Pass"})

    job_results['parts'].append({"partName": "Set Directory Permissions for lowering data directories", "result": "Pass"})
    worker.send_job_status(current_job, 10, 10)

    return json.dumps(job_results)


def task_rebuild_lowering_directory(worker, current_job):
    """
    Verify and create if necessary all the lowering sub-directories
    """

    job_results = {'parts':[]}

    payload_obj = json.loads(current_job.data)
    logging.debug("Payload: %s", json.dumps(payload_obj, indent=2))

    logging.info("Pre-task checks")
    worker.send_job_status(current_job, 1, 10)

    if not os.path.exists(worker.lowering_full_dir):
        job_results['parts'].append({"partName": "Verify Lowering Directory exists", "result": "Fail", "reason": "Unable to find lowering directory: " + worker.lowering_dir})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify Lowering Directory exists", "result": "Pass"})

    logging.info("Build directory list")
    worker.send_job_status(current_job, 2, 10)

    directorylist = worker.build_directorylist()
    logging.debug("Directory List: %s", json.dumps(directorylist, indent=2))
    job_results['parts'].append({"partName": "Build Directory List", "result": "Pass"})

    if len(directorylist) > 0:
        logging.info("Create directories")
        worker.send_job_status(current_job, 5, 10)

        output_results = create_directories(directorylist)

        if output_results['verdict']:
            job_results['parts'].append({"partName": "Create Directories", "result": "Pass"})
        else:
            logging.error("Unable to create any/all of the lowering data directory structure")
            job_results['parts'].append({"partName": "Create Directories", "result": "Fail", "reason": output_results['reason']})

    logging.info("Set directory ownership/permissions")
    worker.send_job_status(current_job, 7, 10)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.lowering_full_dir)

    if not output_results['verdict']:
        logging.error("Failed to set directory ownership")
        job_results['parts'].append({"partName": "Set Directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})

    job_results['parts'].append({"partName": "Set Directory ownership/permissions", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle Lowering data directory related tasks')
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

    logging.info("\tTask: %s", TASK_NAMES['CREATE_CRUISE_DIRECTORY'])
    new_worker.register_task(TASK_NAMES['CREATE_CRUISE_DIRECTORY'], task_create_lowering_directory)

    logging.info("\tTask: %s", TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'])
    new_worker.register_task(TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'], task_set_lowering_data_directory_permissions)

    logging.info("\tTask: %s", TASK_NAMES['REBUILD_CRUISE_DIRECTORY'])
    new_worker.register_task(TASK_NAMES['REBUILD_CRUISE_DIRECTORY'], task_rebuild_lowering_directory)

    logging.info("Waiting for jobs...")
    new_worker.work()
