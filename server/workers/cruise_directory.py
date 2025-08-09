#!/usr/bin/env python3
"""
FILE:  cruise_directory.py

DESCRIPTION:  Gearman worker the handles the tasks of creating a new cruise
    data directory and updating the cruise directory structure when additional
    subdirectories must be added.

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
import sys
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import create_directories, lockdown_directory, set_owner_group_permissions
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
        "longName": "Creating cruise directory",
    },
    {
        "taskID": "0",
        "name": TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'],
        "longName": "Setting CruiseData directory permissions",
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
        self.cruise_dir = None
        self.lowering_id = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    @staticmethod
    def _get_custom_task(current_job):
        """
        Fetch task metadata
        """

        return next((task for task in CUSTOM_TASKS if task['name'] == current_job.task), None)


    def keyword_replace(self, s):
        """
        Find/replace function used to build directory names containing wildcards
        """

        if not isinstance(s, str):
            return None

        return (s.replace('{cruiseID}', self.cruise_id)
                .replace('{loweringDataBaseDir}', self.shipboard_data_warehouse_config['loweringDataBaseDir'])
                .replace('{loweringID}', self.lowering_id if self.lowering_id is not None else '{loweringID}')
                .rstrip('/')
               ) if s != '/' else s


    def build_dest_dir(self, dest_dir):
        """
        Replace any wildcards in the provided directory
        """

        return self.keyword_replace(dest_dir) if dest_dir else None


    def build_directorylist(self):
        """
        Build list of directories to created as part of creating the new cruise
        """

        return_directories = []

        # Retrieve required extra directories
        extra_directories = self.ovdm.get_required_extra_directories()

        # Filter out From_PublicData directory if the auto transfer has been disabled.
        if self.ovdm.get_transfer_public_data() is not True:
            extra_directories = [ extra_directory for extra_directory in extra_directories if extra_directory['name'] != 'From_PublicData']

        # add required extra directories to output
        return_directories.extend([ os.path.join(self.cruise_dir, self.build_dest_dir(extra_directory['destDir'])) for extra_directory in extra_directories ])

        # Add lowering base directory
        if self.ovdm.get_show_lowering_components():
            return_directories.append(os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir']))

        # Retrieve active collection system transfers
        collection_system_transfers = self.ovdm.get_active_collection_system_transfers(lowering=False)

        # Filter out collection system transfers that contain {loweringID} in the dest_dir if there is no lowering ID
        if not self.lowering_id:
            collection_system_transfers = [ collection_system_transfer for collection_system_transfer in collection_system_transfers if '{loweringID}' not in collection_system_transfer['destDir']]

        # Filter out From_PublicData directory if the auto transfer has been disabled.
        if not self.ovdm.get_transfer_public_data():
            collection_system_transfers = [ collection_system_transfer for collection_system_transfer in collection_system_transfers if collection_system_transfer['name'] != 'From_PublicData']

        # add collection system transfers to output
        return_directories.extend([ os.path.join(self.cruise_dir, self.build_dest_dir(collection_system_transfer['destDir'])) for collection_system_transfer in collection_system_transfers ])

        # Retrieve active extra directories
        extra_directories = self.ovdm.get_active_extra_directories(lowering=False)
        extra_directories = [extra_directory for extra_directory in extra_directories if extra_directory['required'] == '0']

        # Filter out extra directories that contain {loweringID} in the dest_dir if there is no lowering ID
        if not self.lowering_id:
            extra_directories = [ extra_directory for extra_directory in extra_directories if '{loweringID}' not in extra_directory['destDir']]

        # add required extra directories to output
        return_directories.extend([ os.path.join(self.cruise_dir, self.build_dest_dir(extra_directory['destDir'])) for extra_directory in extra_directories ])

        return list(set(return_directories))


    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """

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

        logging.info("Job Started: %s", current_job.handle)

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job Failed: %s", current_job.handle)

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        self.send_job_data(current_job, json.dumps(
            [{"partName": "Worker crashed", "result": "Fail", "reason": str(exc_type)}]
        ))

        if int(self.task['taskID']) > 0:
            self.ovdm.set_error_task(self.task['taskID'], f'Worker crashed: {str(exc_type)}')
        else:
            self.ovdm.send_msg(f"{self.task['longName']} failed", f'Worker crashed: {str(exc_type)}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)

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
        logging.info("Job Completed: %s", current_job.handle)

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
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def task_create_cruise_directory(worker, current_job):
    """
    Build a new cruise directory
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    logging.debug("Pre-tasks checks")

    if not os.path.exists(worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']):
        job_results['parts'].append({"partName": "Verify base directory exists", "result": "Fail", "reason": f"Failed to find base directory: {worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']}"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify base directory exists", "result": "Pass"})

    if os.path.exists(worker.cruise_dir):
        job_results['parts'].append({"partName": "Verify cruise directory does not exists", "result": "Fail", "reason": f"Cruise directory {worker.cruise_dir} already exists"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify cruise directory does not exists", "result": "Pass"})

    logging.info("Building directory list")
    worker.send_job_status(current_job, 2, 10)

    directorylist = worker.build_directorylist()
    logging.debug("Directory List: %s", json.dumps(directorylist, indent=2))

    if len(directorylist) == 0:
        job_results['parts'].append({"partName": "Build directory list", "result": "Fail", "reason": "Empty list of directories to create"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Build directory list", "result": "Pass"})

    logging.info("Creating directories")
    worker.send_job_status(current_job, 5, 10)

    output_results = create_directories(directorylist)

    if not output_results['verdict']:
        logging.error("Failed to create any/all of the cruise data directory structure")
        job_results['parts'].append({"partName": "Create directories", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create directories", "result": "Pass"})

    if worker.ovdm.show_only_current_cruise_dir() is True:
        logging.info("Resetting permissions for CruiseData directory")
        worker.send_job_status(current_job, 7, 10)

        output_results = lockdown_directory(worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], [worker.cruise_dir])

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Pass"})

    logging.info("Setting ownership/permissions for cruise directory")
    worker.send_job_status(current_job, 8, 10)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.cruise_dir)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Set cruise directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set cruise directory ownership/permissions", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_set_cruisedata_directory_permissions(worker, current_job):
    """
    Set the permissions for the CruiseData directory
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    if worker.ovdm.show_only_current_cruise_dir() is True:
        logging.info("Resetting permissions for CruiseData directory")
        worker.send_job_status(current_job, 2, 10)

        output_results = lockdown_directory(worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], [worker.cruise_dir])

        if not output_results['verdict']:
            logging.error('Could not lockdown cruise data directory')
            job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Pass"})

    logging.info("Setting ownership/permissions for cruise data directory")
    worker.send_job_status(current_job, 6, 10)

    if not os.path.isdir(worker.cruise_dir):
        reason = "Cruise directory not found"
        logging.error(reason)
        job_results['parts'].append({"partName": "Set directory permissions for current cruise", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.cruise_dir)
    job_results['parts'].append({"partName": "Set Directory permissions for current cruise", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_rebuild_cruise_directory(worker, current_job):
    """
    Fix any file permission errors and create any missing directories within
    the current cruise data directory
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    if not os.path.exists(worker.cruise_dir):
        reason = f"Unable to locate the cruise directory: {worker.cruise_dir}"
        logging.error(reason)
        job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Pass"})

    if worker.ovdm.show_only_current_cruise_dir() is True:
        logging.info("Clear CruiseData Directory Read Permissions")
        worker.send_job_status(current_job, 2, 100)

        output_results = lockdown_directory(worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], [worker.cruise_dir])

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Clear CruiseData directory read permissions", "result": "Pass"})

    logging.info("Build directory list")
    worker.send_job_status(current_job, 3, 10)

    directorylist = worker.build_directorylist()
    logging.debug("Directory List: %s", json.dumps(directorylist, indent=2))
    job_results['parts'].append({"partName": "Build directory list", "result": "Pass"})

    logging.info("Create directories")
    worker.send_job_status(current_job, 5, 10)

    output_results = create_directories(directorylist)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Create directories", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create directories", "result": "Pass"})

    logging.info("Set directory ownership/permissions")
    worker.send_job_status(current_job, 7, 10)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.cruise_dir)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Set directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})

    job_results['parts'].append({"partName": "Set directory ownership/permissions", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -----------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle cruise data directory related tasks')
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

    logging.info("\tTask: %s", TASK_NAMES['CREATE_CRUISE_DIRECTORY'])
    new_worker.register_task(TASK_NAMES['CREATE_CRUISE_DIRECTORY'], task_create_cruise_directory)

    logging.info("\tTask: %s", TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'])
    new_worker.register_task(TASK_NAMES['SET_CRUISEDATA_PERMISSIONS'], task_set_cruisedata_directory_permissions)

    logging.info("\tTask: %s", TASK_NAMES['REBUILD_CRUISE_DIRECTORY'])
    new_worker.register_task(TASK_NAMES['REBUILD_CRUISE_DIRECTORY'], task_rebuild_cruise_directory)

    logging.info("Waiting for jobs...")
    new_worker.work()
