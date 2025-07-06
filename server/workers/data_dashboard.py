#!/usr/bin/env python3
"""
FILE:  data_dashboard.py

DESCRIPTION:  Gearman worker tha handles the creation and update of OVDM data
    dashboard objects.

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
import sys
import signal
import subprocess
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import build_filelist, output_json_data_to_file, set_owner_group_permissions
from server.lib.openvdm import OpenVDM

PYTHON_BINARY = os.path.join(dirname(dirname(dirname(realpath(__file__)))), 'venv/bin/python')

CUSTOM_TASKS = [
    {
        "taskID": "0",
        "name": "updateDataDashboard",
        "longName": "Updating Data Dashboard",
    }
]

# def build_filelist(source_dir):
#     """
#     return list of files in the source directory
#     """

#     source_dir = source_dir.rstrip('/') or '/'

#     logging.debug("sourceDir: %s", source_dir)

#     return_files = []
#     for root, _, filenames in os.walk(source_dir):
#         for filename in filenames:
#             return_files.append(os.path.join(root, filename))

#     return_files = [filename.replace(source_dir + '/', '', 1) for filename in return_files]
#     return return_files


class OVDMGearmanWorker(python3_gearman.GearmanWorker): # pylint: disable=too-many-instance-attributes
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.shipboard_data_warehouse_config = None
        self.cruise_id = None
        self.cruise_dir = None
        self.lowering_id = None
        self.lowering_dir = None
        self.data_dashboard_dir = None
        self.data_dashboard_manifest_file_path = None
        self.collection_system_transfer = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    @staticmethod
    def get_custom_task(current_job):
        """
        fetch task metadata
        """

        task = list(filter(lambda task: task['name'] == current_job.task, CUSTOM_TASKS))
        return task[0] if len(task) > 0 else None


    @staticmethod
    def _get_filetype(raw_path, processing_script_filename):
        cmd = [PYTHON_BINARY, processing_script_filename, '--dataType', raw_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr


    @staticmethod
    def _process_file(raw_path, processing_script_filename):
        cmd = [PYTHON_BINARY, processing_script_filename, raw_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr, cmd


    @staticmethod
    def _add_manifest_entry(entries, dd_type, json_path, raw_path, base_dir):
        rel_json = json_path.replace(base_dir + '/', '')
        rel_raw = raw_path.replace(base_dir + '/', '')
        entries.append({"type": dd_type, "dd_json": rel_json, "raw_data": rel_raw})


    @staticmethod
    def _remove_manifest_entry(entries, json_path, raw_path, base_dir):
        rel_json = json_path.replace(base_dir + '/', '')
        rel_raw = raw_path.replace(base_dir + '/', '')
        entries.append({"dd_json": rel_json, "raw_data": rel_raw})


    def _build_paths(self, filename):
        json_filename = os.path.splitext(filename)[0] + '.json'
        raw_path = os.path.join(self.cruise_dir, filename)
        json_path = os.path.join(self.data_dashboard_dir, json_filename)
        return raw_path, json_path

    def _build_processing_filename(self):
        processing_script_filename = os.path.join(self.ovdm.get_plugin_dir(), self.collection_system_transfer['name'].lower() + self.ovdm.get_plugin_suffix())
        logging.debug("Processing Script Filename: %s", processing_script_filename)

        return processing_script_filename if os.path.isfile(processing_script_filename) else None

    def _process_filelist(self, current_job, filelist, processing_script_filename, job_results, start=0, end=100):

        base_dir = self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']
        new_manifest_entries = []
        remove_manifest_entries = []
        progress_factor = end - start
        file_count = len(filelist)
        file_index = 0

        # Main Loop
        for filename in filelist:
            if self.stop:
                break

            logging.info("Processing file: %s", filename)
            raw_path, json_path = self._build_paths(filename)

            if not os.path.isfile(raw_path):
                job_results['parts'].append({"partName": "Verify data file exists", "result": "Fail", "reason": f"Unable to find data file: {filename}"})
                continue

            if os.stat(raw_path).st_size == 0:
                logging.warning("File is empty %s, skipping", filename)
                continue

            dd_type, type_err = self._get_filetype(raw_path, processing_script_filename)
            if not dd_type:
                logging.warning("File is of unknown datatype: %s", raw_path)
                self._remove_manifest_entry(remove_manifest_entries, json_path, raw_path, base_dir)
                if type_err:
                    logging.error("Err: %s", type_err)
                continue

            logging.debug("DataType found to be: %s", dd_type)
            output, error, cmd = self._process_file(raw_path, processing_script_filename)

            if not output:
                msg = f"No JSON output received from file. Parsing Command: {' '.join(cmd)}"
                logging.error(msg)
                self.ovdm.send_msg("Data Dashboard Processing failed", msg)
                self._remove_manifest_entry(remove_manifest_entries, json_path, raw_path, base_dir)
                if error:
                    logging.error("Err: %s", error)
                continue

            try:
                out_obj = json.loads(output)
            except Exception as err:
                logging.error("Error parsing JSON output from file: %s", filename)
                logging.debug(str(err))
                job_results['parts'].append({"partName": f"Parsing JSON output from file {filename}", "result": "Fail", "reason": f"Error parsing JSON output from file: {filename}"})
                continue

            if not out_obj:
                msg = f"Parser returned no output. Parsing command: {' '.join(cmd)}"
                logging.error("Datafile Parsing error: %s", msg)
                self.ovdm.send_msg("Datafile Parsing error", msg)
                continue

            if 'error' in out_obj:
                logging.error("Datafile Parsing error: %s", out_obj['error'])
                self.ovdm.send_msg("Datafile Parsing error", out_obj['error'])
                continue

            result = output_json_data_to_file(json_path, out_obj)
            if result['verdict']:
                job_results['parts'].append({"partName": f"Writing DashboardData file: {filename}", "result": "Pass"})
            else:
                msg = f"Error Writing DashboardData file: {filename}. Reason: {result['reason']}"
                logging.error("Data Dashboard Processing failed: %s", msg)
                self.ovdm.send_msg("Data Dashboard Processing failed", msg)
                job_results['parts'].append({"partName": f"Writing Dashboard file: {filename}", "result": "Fail", "reason": result['reason']})
                continue

            self._add_manifest_entry(new_manifest_entries, dd_type, json_path, raw_path, base_dir)

            self.send_job_status(current_job, int((progress_factor) * file_index / file_count) + start, 100)
            file_index += 1

        return new_manifest_entries, remove_manifest_entries


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

        self.task = (self.get_custom_task(current_job)
            if self.get_custom_task(current_job) is not None
            else self.ovdm.get_task_by_name(current_job.task)
        )

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        if int(self.task['taskID']) > 0:
            self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)
        else:
            self.ovdm.track_gearman_job(self.task['longName'], os.getpid(), current_job.handle)

        logging.info("Job: %s started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_id = payload_obj['cruiseID'] if 'cruiseID' in payload_obj else self.ovdm.get_cruise_id()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.lowering_id = payload_obj['loweringID'] if 'loweringID' in payload_obj else self.ovdm.get_lowering_id()
        self.lowering_dir = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id) if self.lowering_id else None
        self.collection_system_transfer = self.ovdm.get_collection_system_transfer(payload_obj['collectionSystemTransferID']) if 'collectionSystemTransferID' in payload_obj else None
        self.data_dashboard_dir = os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Dashboard_Data')['destDir'])
        self.data_dashboard_manifest_file_path = os.path.join(self.data_dashboard_dir, self.shipboard_data_warehouse_config['dataDashboardManifestFn'])

        if current_job.task == 'updateDataDashboard' and not self.collection_system_transfer: # doesn't exists
            return self.on_job_complete(current_job, json.dumps({
                'parts':[{
                    "partName": "Retrieve Collection System Tranfer Data",
                    "result": "Fail",
                    "reason": "Could not find configuration data for collection system transfer"
                }],
                'files': {
                    'new':[],
                    'updated':[]
                }
            }))

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job: %s (%s) failed at: %s", self.task['longName'], current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{"partName": "Worker crashed", "result": "Fail", "reason": "Unknown, contact Webb :-)"}]))
        if int(self.task['taskID']) > 0:
            self.ovdm.set_error_task(self.task['taskID'], "Worker crashed")
        else:
            self.ovdm.send_msg(self.task['longName'] + ' failed', 'Worker crashed')

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)
        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results_obj = json.loads(job_result)

        logging.debug("Preparing subsequent Gearman jobs")

        job_data = {
            'cruiseID': self.cruise_id,
            'loweringID': self.lowering_id,
            'files': results_obj['files']
        }

        if current_job.task == 'updateDataDashboard':

            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            payload_obj = json.loads(current_job.data)
            job_data['collectionSystemTransferID'] = payload_obj['collectionSystemTransferID']

            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        elif current_job.task == 'rebuildDataDashboard':

            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        if len(results_obj['parts']) > 0:
            if results_obj['parts'][-1]['result'] == "Fail": # Final Verdict
                if int(self.task['taskID']) > 0:
                    self.ovdm.set_error_task(self.task['taskID'], results_obj['parts'][-1]['reason'])
                else:
                    self.ovdm.send_msg(self.task['longName'] + ' failed', results_obj['parts'][-1]['reason'])
            else:
                if int(self.task['taskID']) > 0:
                    self.ovdm.set_idle_task(self.task['taskID'])
        else:
            if int(self.task['taskID']) > 0:
                self.ovdm.set_idle_task(self.task['taskID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s (%s) completed at: %s", self.task['longName'], current_job.handle, time.strftime("%D %T", time.gmtime()))

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
        shortcut for completing the current job as failed
        """
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def task_update_data_dashboard(worker, current_job): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    update the data dashboard
    """

    job_results = {
        'parts':[],
        'files':{
            'new':[],
            'updated':[],
            'deleted':[]
        }
    }

    payload_obj = json.loads(current_job.data)
    base_dir = worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']

    logging.info('Collection System Transfer: %s', worker.collection_system_transfer['name'])

    logging.info("Verifying plugin file exists")
    worker.send_job_status(current_job, 5, 100)

    processing_script_filename = worker._build_processing_filename()

    if processing_script_filename is None:
        reason = f"Processing script not found: {processing_script_filename}"
        logging.warning(reason)
        job_results['parts'].append({"partName": "Dashboard Processing File Located", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Dashboard Processing File Located", "result": "Pass"})

    logging.info("Build filelist for processing")
    worker.send_job_status(current_job, 10, 100)

    #build filelist
    filelist = payload_obj['files']['new'] + payload_obj['files']['updated']
    logging.debug('File List: %s', json.dumps(filelist, indent=2))

    if len(filelist) == 0:
        reason = "No new or updated files to process"
        logging.warning(reason)
        job_results['parts'].append({"partName": "Retrieve Filelist", "result": "Ignore", "reason": reason})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Retrieve Filelist", "result": "Pass"})

    logging.info("Processing files")
    worker.send_job_status(current_job, 15, 100)

    new_manifest_entries, remove_manifest_entries = worker._process_filelist(current_job, filelist, job_results, 15, 90)

    logging.info("Updating Manifest file: %s", worker.data_dashboard_manifest_file_path)
    worker.send_job_status(current_job, 9, 10)

    if len(new_manifest_entries) == 0 and len(remove_manifest_entries) == 0:
        reason = "No new, updated or obsolete entries to process"
        logging.warning(reason)
        job_results['parts'].append({"partName": "Retrieve Filelist", "result": "Ignore", "reason": reason})
        return(json.dumps(job_results))

    rows_removed = 0

    # Load existing manifest
    try:
        with open(worker.data_dashboard_manifest_file_path, 'r', encoding='utf-8') as f:
            existing_entries = json.load(f)
        job_results['parts'].append({"partName": "Reading pre-existing Dashboard manifest file", "result": "Pass"})
    except IOError:
        logging.warning("Error reading manifest file: %s", worker.data_dashboard_manifest_file_path)
        existing_entries = []
    except Exception as err:
        reason = f"Error reading dashboard manifest file: {worker.data_dashboard_manifest_file_path}"
        logging.error("%s: %s", reason, str(err))
        job_results['parts'].append({"partName": "Reading pre-existing Dashboard manifest file", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    # Remove entries
    logging.debug("Entries to remove: %s", json.dumps(remove_manifest_entries, indent=2))
    existing_entries_map = {entry['raw_data']: entry for entry in existing_entries}
    for rm in remove_manifest_entries:
        if rm['raw_data'] in existing_entries_map:
            existing_entries.remove(existing_entries_map[rm['raw_data']])
            rows_removed += 1

            dd_json_path = os.path.join(base_dir, rm['dd_json'])
            if os.path.isfile(dd_json_path):
                logging.info("Deleting orphaned dd_json file %s", dd_json_path)
                os.remove(dd_json_path)

    # Update or add entries
    logging.debug("Entries to add/update: %s", json.dumps(new_manifest_entries, indent=2))
    for entry in new_manifest_entries:
        raw_data = entry['raw_data']
        dd_json_rel = entry['dd_json'].replace(worker.cruise_id + '/', '')

        if any(e['raw_data'] == raw_data for e in existing_entries):
            job_results['files']['updated'].append(dd_json_rel)
        else:
            job_results['files']['new'].append(dd_json_rel)
            existing_entries.append(entry)

    # Logging summary
    if job_results['files']['new']:
        logging.info("%s row(s) added", len(job_results['files']['new']))
    if job_results['files']['updated']:
        logging.info("%s row(s) updated", len(job_results['files']['updated']))
    if rows_removed:
        logging.info("%s row(s) removed", rows_removed)

    # Write updated manifest
    result = output_json_data_to_file(worker.data_dashboard_manifest_file_path, existing_entries)
    if not result['verdict']:
        logging.error("Error writing manifest file: %s", worker.data_dashboard_manifest_file_path)
        job_results['parts'].append({"partName": "Writing Dashboard manifest file", "result": "Fail", "reason": result['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Writing Dashboard manifest file", "result": "Pass"})

    manifest_filename = worker.shipboard_data_warehouse_config['dataDashboardManifestFn']
    manifest_relpath = os.path.join(worker.ovdm.get_required_extra_directory_by_name('Dashboard_Data')['destDir'], manifest_filename)
    job_results['files']['updated'].append(manifest_relpath)

    # File ownership/permissions
    logging.info("Setting file ownership/permissions")
    worker.send_job_status(current_job, 9, 10)
    result = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.data_dashboard_dir)

    part_result = {"partName": "Set file/directory ownership", "result": "Pass" if result['verdict'] else "Fail"}
    if not result['verdict']:
        part_result['reason'] = result['reason']
        return json.dumps(job_results)
    job_results['parts'].append(part_result)

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_rebuild_data_dashboard(worker, current_job): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    Rebuild the existing dashboard files
    """

    job_results = {
        'parts':[],
        'files':{
            'new':[],
            'updated':[]
        }
    }

    logging.info("Rebuilding data dashboard")
    worker.send_job_status(current_job, 1, 100)

    if not os.path.exists(worker.data_dashboard_dir):
        logging.error("Data dashboard directory not found: %s", worker.data_dashboard_dir)
        job_results['parts'].append({"partName": "Verify Data Dashboard Directory exists", "result": "Fail", "reason": "Unable to locate the data dashboard directory: " + worker.data_dashboard_dir})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify Data Dashboard Directory exists", "result": "Pass"})

    collection_system_transfers = worker.ovdm.get_active_collection_system_transfers()

    collection_system_transfer_count = len(collection_system_transfers)
    collection_system_transfer_index = 0
    for collection_system_transfer in collection_system_transfers:  # pylint: disable=too-many-nested-blocks

        collection_system_transfer_index += 1

        progress_factor = int(float(collection_system_transfer_index) / float(collection_system_transfer_count) * 100)
        logging.info('Processing data from: %s', collection_system_transfer['name'])
        worker.send_job_status(current_job, 80 * progress_factor + 10, 100)

        processing_script_filename = worker._build_processing_filename()

        if processing_script_filename is None:
            reason = f"Processing script not found: {processing_script_filename}"
            logging.warning(reason)
            continue

        if collection_system_transfer['cruiseOrLowering'] == "0":
            collection_system_transfer_input_dir = os.path.join(worker.cruise_dir, collection_system_transfer['destDir'])
            filelist = build_filelist(collection_system_transfer_input_dir.get('include', []))
            filelist = [os.path.join(collection_system_transfer['destDir'], filename) for filename in filelist]

        else:
            lowerings = worker.ovdm.get_lowerings()
            lowering_base_dir = worker.shipboard_data_warehouse_config['loweringDataBaseDir']
            filelist = []

            for lowering in lowerings:
                collection_system_transfer_input_dir = os.path.join(worker.cruise_dir, lowering_base_dir, lowering, collection_system_transfer['destDir'])
                lowering_filelist = build_filelist(collection_system_transfer_input_dir).get('include', [])
                filelist.extend([os.path.join(lowering_base_dir, lowering, collection_system_transfer['destDir'], filename) for filename in lowering_filelist])

        logging.debug("FileList: %s", json.dumps(filelist, indent=2))

        start = 80 * progress_factor + 10
        end = 80 * int(float(collection_system_transfer_index + 1) / float(collection_system_transfer_count) * 100) + 10
        new_manifest_entries, _ = worker._process_filelist(current_job, filelist, job_results, start, end)

    logging.info("Updating Manifest file: %s", worker.data_dashboard_manifest_file_path)
    worker.send_job_status(current_job, 9, 10)

    output_results = output_json_data_to_file(worker.data_dashboard_manifest_file_path, new_manifest_entries)

    if not output_results['verdict']:
        logging.error("Error updating manifest file %s", worker.data_dashboard_manifest_file_path)
        job_results['parts'].append({"partName": "Updating manifest file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Updating manifest file", "result": "Pass"})

    logging.info("Setting file ownership/permissions")
    worker.send_job_status(current_job, 95, 100)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.data_dashboard_dir)

    if not output_results['verdict']:
        logging.error("Error Setting file/directory ownership/permissions")
        job_results['parts'].append({"partName": "Setting file/directory ownership", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Setting file/directory ownership", "result": "Pass"})

    worker.send_job_status(current_job, 99, 100)

    data_dashboard_dest_dir = worker.ovdm.get_required_extra_directory_by_name('Dashboard_Data')['destDir']
    job_results['files']['updated'] = [os.path.join(data_dashboard_dest_dir, filepath) for filepath in build_filelist(worker.data_dashboard_dir.get('include', []))]# might need to remove cruise_dir from begining of filepaths

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle data dashboard related tasks')
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

    logging.info("\tTask: updateDataDashboard")
    new_worker.register_task("updateDataDashboard", task_update_data_dashboard)

    logging.info("\tTask: rebuildDataDashboard")
    new_worker.register_task("rebuildDataDashboard", task_rebuild_data_dashboard)

    logging.info("Waiting for jobs...")
    new_worker.work()
