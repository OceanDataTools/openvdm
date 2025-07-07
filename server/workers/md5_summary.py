#!/usr/bin/env python3
"""
FILE:  md5_summary.py

DESCRIPTION:  Gearman worker tha handles the creation and update of an MD5
    checksum summary.

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
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import build_filelist, set_owner_group_permissions
from server.lib.openvdm import OpenVDM
from server.lib.md5_util import hash_file

TASK_NAMES = {
    'REBUILD_MD5_SUMMARY': 'rebuildMD5Summary',
    'UPDATE_MD5_SUMMARY': 'updateMD5Summary'
}

CUSTOM_TASKS = [
    {
        "taskID": "0",
        "name": TASK_NAMES['UPDATE_MD5_SUMMARY'],
        "longName": "Updating MD5 Summary",
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
        self.md5_summary_filepath = None
        self.md5_summary_md5_filepath = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    @staticmethod
    def _get_custom_task(current_job):
        """
        Fetch task metadata by name from CUSTOM_TASKS
        """

        return next((task for task in CUSTOM_TASKS if task['name'] == current_job.task), None)


    def build_md5_hashes(self, current_job, filelist):
        """
        Build the md5 hashes for the files in the filelist
        """

        filesize_limit = self.ovdm.get_md5_filesize_limit()
        filesize_limit_status = self.ovdm.get_md5_filesize_limit_status()

        hashes = []

        for idx, filename in enumerate(filelist):

            if self.stop:
                logging.debug("Stopping job")
                break

            filepath = os.path.join(self.cruise_dir, filename)

            try:
                if filesize_limit_status == 'On' and filesize_limit != '0':
                    if os.stat(filepath).st_size < int(filesize_limit) * 1000000:
                        hashes.append({'hash': hash_file(filepath), 'filename': filename})
                    else:
                        hashes.append({'hash': '********************************', 'filename': filename})

                else:
                    hashes.append({'hash': hash_file(filepath), 'filename': filename})

            except Exception as err:
                logging.error("Could not generate md5 hash for file: %s", filename)
                logging.debug(str(err))

            self.send_job_status(current_job, int(60 * idx / len(filelist)) + 20, 100) # 80-20

        return hashes


    def build_md5_summary(self, hashes):
        """
        Builds a new/updated MD5 summary file
        """

        sorted_hashes = sorted(hashes, key=lambda entry: entry['filename'])

        try:
            with open(self.md5_summary_filepath, mode='w', encoding="utf-8") as md5_summary_file:

                for filehash in sorted_hashes:
                    md5_summary_file.write(filehash['hash'] + ' ' + filehash['filename'] + '\n')

        except IOError:
            logging.error("Error updating MD5 Summary file: %s", self.md5_summary_filepath)
            return {"verdict": False, "reason": f"Error updating MD5 Summary file: {self.md5_summary_filepath}"}

        return {"verdict": True}


    def build_md5_summary_md5(self):
        """
        Build the md5 hash file for the md5 summary file
        """

        try:
            with open(self.md5_summary_md5_filepath, mode='w', encoding="utf-8") as md5_summary_md5_file:
                md5_summary_md5_file.write(hash_file(self.md5_summary_filepath))

        except IOError:
            logging.error("Error Saving MD5 Summary MD5 file: %s", self.md5_summary_md5_filepath)
            return {"verdict": False, "reason": f"Error Saving MD5 Summary MD5 file: {self.md5_summary_md5_filepath}"}

        return {"verdict": True}


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

        self.task = (self._get_custom_task(current_job)
            if self._get_custom_task(current_job) is not None
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

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.cruise_start_date = payload_obj.get('cruiseStartDate', self.ovdm.get_cruise_start_date())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        self.md5_summary_filepath = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['md5SummaryFn'])
        self.md5_summary_md5_filepath = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['md5SummaryMd5Fn'])

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
        """
        Shortcut for completing the current job as failed
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def task_update_md5_summary(worker, current_job): # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    """
    Update the existing MD5 summary files
    """

    job_results = {'parts':[]}
    payload_obj = json.loads(current_job.data)

    logging.debug("Building filelist")
    worker.send_job_status(current_job, 1, 10)

    filelist = []

    new_files = payload_obj['files'].get('new', [])
    updated_files = payload_obj['files'].get('updated', [])
    deleted_files = payload_obj['files'].get('deleted', [])

    if len(new_files) + len(updated_files) + len(deleted_files) == 0:
        return json.dumps({
            'parts': [{"partName": "Update MD5 Summary", "result": "Ignore", "reason": "Nothing to update"}]
        })

    if new_files or updated_files:
        filelist.extend(new_files)
        filelist.extend(updated_files)

    logging.debug("Building hashes")
    worker.send_job_status(current_job, 2, 10)

    new_hashes = worker.build_md5_hashes(current_job, filelist)

    job_results['parts'].append({"partName": "Calculate Hashes", "result": "Pass"})

    logging.debug("Processing existing MD5 summary file")
    worker.send_job_status(current_job, 8, 10)

    hashes = []
    try:
        with open(worker.md5_summary_filepath, 'r', encoding='utf-8') as f:
            hashes = [
                {'hash': line.split(' ', 1)[0], 'filename': line.split(' ', 1)[1].rstrip('\n')}
                for line in f if ' ' in line
            ]
    except IOError:
        msg = f"Error Reading pre-existing MD5 Summary file: {worker.md5_summary_filepath}"
        logging.error(msg)
        job_results['parts'].append({
            "partName": "Reading pre-existing MD5 Summary file",
            "result": "Fail",
            "reason": msg
        })
        return json.dumps(job_results)

    job_results['parts'].append({
        "partName": "Reading pre-existing MD5 Summary file",
        "result": "Pass"
    })

    row_added = row_updated = row_deleted = 0

    # Index existing hashes by filename
    hash_index = {entry['filename']: entry for entry in hashes}

    # Update or add new hashes
    for new in new_hashes:
        fn = new['filename']
        if fn in hash_index:
            hash_index[fn]['hash'] = new['hash']
            row_updated += 1
        else:
            entry = {'filename': fn, 'hash': new['hash']}
            hashes.append(entry)
            hash_index[fn] = entry
            row_added += 1

    # Delete obsolete entries
    if deleted_files:
        before = len(hashes)
        hashes = [e for e in hashes if e['filename'] not in deleted_files]
        row_deleted = before - len(hashes)

    # Log summary
    for label, count in (("added", row_added), ("updated", row_updated), ("deleted", row_deleted)):
        if count > 0:
            logging.debug("%s row(s) %s", count, label)

    logging.debug("Building MD5 Summary file")
    worker.send_job_status(current_job, 9, 10)

    output_results = worker.build_md5_summary(hashes)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Writing MD5 Summary file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Writing MD5 Summary file", "result": "Pass"})

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.md5_summary_filepath)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Set MD5 Summary file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set MD5 Summary file ownership/permissions", "result": "Pass"})

    logging.debug("Building MD5 Summary MD5 file")
    worker.send_job_status(current_job, 95, 100)

    output_results = worker.build_md5_summary_md5()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Writing MD5 Summary MD5 file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Writing MD5 Summary MD5 file", "result": "Pass"})

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.md5_summary_md5_filepath)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Set MD5 Summary MD5 file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set MD5 Summary MD5 file ownership/permissions", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_rebuild_md5_summary(worker, current_job): # pylint: disable=too-many-statements
    """
    Rebuild the existing MD5 summary files
    """

    job_results = {'parts':[]}

    logging.info("Rebuild MD5 Summary")
    worker.send_job_status(current_job, 1, 10)

    payload_obj = json.loads(current_job.data)
    logging.debug("Payload: %s", json.dumps(payload_obj, indent=2))

    if os.path.exists(worker.cruise_dir):
        job_results['parts'].append({"partName": "Verify Cruise Directory exists", "result": "Pass"})
    else:
        logging.error("Cruise directory not found")
        job_results['parts'].append({"partName": "Verify Cruise Directory exists", "result": "Fail", "reason": "Unable to locate the cruise directory: " + worker.cruise_dir})
        return json.dumps(job_results)

    logging.info("Building filelist")
    exclude_set = {
        worker.shipboard_data_warehouse_config['md5SummaryFn'],
        worker.shipboard_data_warehouse_config['md5SummaryMd5Fn']
    }

    exclude_transfer_logs = worker.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'] + '/'

    filelist = build_filelist(worker.cruise_dir).get('include', [])
    filtered_filelist = [
        f for f in filelist
        if f not in exclude_set and not f.startswith(exclude_transfer_logs)
    ]

    logging.debug("File list:\n%s", json.dumps(filtered_filelist, indent=2))

    job_results['parts'].append({"partName": "Retrieve Filelist", "result": "Pass"})

    worker.send_job_status(current_job, 2, 10)

    logging.info("Building hashes")
    new_hashes = worker.build_md5_hashes(current_job, filtered_filelist)
    logging.debug("Hashes: %s", json.dumps(new_hashes, indent=2))

    if worker.stop:
        job_results['parts'].append({"partName": "Calculate Hashes", "result": "Fail", "reason": "Job was stopped by user"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Calculate Hashes", "result": "Pass"})

    logging.info("Building MD5 Summary file")
    worker.send_job_status(current_job, 80, 100)

    sorted_hashes = sorted(new_hashes, key=lambda hashes: hashes['filename'])
    try:
        #logging.debug("Saving new MD5 Summary file")
        with open(worker.md5_summary_filepath, mode='w', encoding='utf-8') as md5_summary_file:

            for filehash in sorted_hashes:
                md5_summary_file.write(filehash['hash'] + ' ' + filehash['filename'] + '\n')

        job_results['parts'].append({"partName": "Writing MD5 Summary file", "result": "Pass"})

    except IOError:
        logging.error("Error saving MD5 Summary file: %s", worker.md5_summary_filepath)
        job_results['parts'].append({"partName": "Writing MD5 Summary file", "result": "Fail", "reason": "Error saving MD5 Summary file: " + worker.md5_summary_filepath})
        return json.dumps(job_results)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.md5_summary_filepath)

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Set MD5 Summary file ownership/permissions", "result": "Pass"})
    else:
        logging.error("Failed to set directory ownership")
        job_results['parts'].append({"partName": "Set MD5 Summary file ownership/permissions", "result": "Fail", "reason": output_results['reason']})

    worker.send_job_status(current_job, 95, 100)

    logging.info("Building MD5 Summary MD5 file")

    output_results = worker.build_md5_summary_md5()
    if output_results['verdict']:
        job_results['parts'].append({"partName": "Writing MD5 Summary MD5 file", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Writing MD5 Summary MD5 file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.md5_summary_md5_filepath)

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Set MD5 Summary MD5 file ownership/permissions", "result": "Pass"})
    else:
        logging.error("Failed to set directory ownership")
        job_results['parts'].append({"partName": "Set MD5 Summary MD5 file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle MD5 Summary related tasks')
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

    logging.info("\tTask: %s", TASK_NAMES['UPDATE_MD5_SUMMARY'])
    new_worker.register_task(TASK_NAMES['UPDATE_MD5_SUMMARY'], task_update_md5_summary)
    logging.info("\tTask: %s", TASK_NAMES['REBUILD_MD5_SUMMARY'])
    new_worker.register_task(TASK_NAMES['REBUILD_MD5_SUMMARY'], task_rebuild_md5_summary)

    logging.info("Waiting for jobs...")
    new_worker.work()
