#!/usr/bin/env python3
"""
FILE:  stop_job.py

DESCRIPTION:  Gearman worker that handles the manual termination of other OVDM
    data transfers and OVDM tasks.

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

from server.lib.openvdm import OpenVDM

class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.job_pid = ''
        self.job_info = {}
        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def _get_job_info(self):
        """
        Fetch job metadata
        """

        collection_system_transfers = self.ovdm.get_collection_system_transfers()
        for collection_system_transfer in collection_system_transfers:
            if collection_system_transfer['pid'] == self.job_pid:
                return {'type': 'collectionSystemTransfer', 'id': collection_system_transfer['collectionSystemTransferID'], 'name': collection_system_transfer['name'], 'pid': collection_system_transfer['pid']}

        cruise_data_transfers = self.ovdm.get_cruise_data_transfers()
        for cruise_data_transfer in cruise_data_transfers:
            if cruise_data_transfer['pid'] != "0":
                return {'type': 'cruiseDataTransfer', 'id': cruise_data_transfer['cruiseDataTransferID'], 'name': cruise_data_transfer['name'], 'pid': cruise_data_transfer['pid']}

        cruise_data_transfers = self.ovdm.get_required_cruise_data_transfers()
        for cruise_data_transfer in cruise_data_transfers:
            if cruise_data_transfer['pid'] != "0":
                return {'type': 'cruiseDataTransfer', 'id': cruise_data_transfer['cruiseDataTransferID'], 'name': cruise_data_transfer['name'], 'pid': cruise_data_transfer['pid']}

        tasks = self.ovdm.get_tasks()
        for task in tasks:
            if task['pid'] != "0":
                return {'type': 'task', 'id': task['taskID'], 'name': task['name'], 'pid': task['pid']}

        return {'type':'unknown'}


    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """

        logging.debug("Received job: %s", current_job)

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)

        except Exception:
            reason = "Failed to parse current job payload"
            logging.exception(reason)
            return self._fail_job(current_job, "Retrieve current job data", reason)

        self.job_pid = payload_obj.get('pid')
        self.job_info = self._get_job_info()

        logging.info("Job: %s, Killing PID: %s failed at: %s", current_job.handle, self.job_pid, time.strftime("%D %T", time.gmtime()))

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job: %s, failed at: %s", current_job.handle,
              time.strftime("%D %T", time.gmtime()))

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        self.send_job_data(current_job, json.dumps(
            [{"partName": "Worker crashed", "result": "Fail", "reason": str(exc_type)}]
        ))

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results_obj = json.loads(job_result)

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s, Killing PID %s completed at: %s", current_job.handle,
                     self.job_pid, time.strftime("%D %T", time.gmtime()))

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


    def _fail_job(self, current_job, part_name, reason):
        """
        shortcut for completing the current job as failed
        """
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_stop_job(worker, current_job):
    """
    Stop the specified OpenVDM task/transfer/process
    """
    job_info = worker.job_info
    job_type = job_info.get('type')
    job_id = job_info.get('id')
    job_name = job_info.get('name')
    job_pid = job_info.get('pid')

    job_results = {'parts': [{"partName": "Retrieve Job Info", "result": "Pass"}]}

    if job_type == "unknown":
        logging.error("Unknown job type: %s", job_type)
        return worker._fail_job(current_job, "Valid OpenVDM Job", f"Unknown job type: {job_type}")

    job_results['parts'].append({"partName": "Valid OpenVDM Job", "result": "Pass"})
    logging.debug("Quitting job: %s", job_pid)

    try:
        os.kill(int(job_pid), signal.SIGQUIT)
    except OSError as err:
        if err.errno == 3:
            logging.warning("Process does not exist: PID %s", job_pid)
        else:
            logging.error("Error killing PID %s: %s", job_pid, err)
            job_results['parts'].append({
                "partName": "Stopped Job",
                "result": "Fail",
                "reason": f"Error killing PID: {job_pid} --> {err}"
            })

    finally:
        actions = {
            'collectionSystemTransfer': worker.ovdm.set_idle_collection_system_transfer,
            'cruiseDataTransfer': worker.ovdm.set_idle_cruise_data_transfer,
            'task': worker.ovdm.set_idle_task
        }

        if job_type in actions:
            actions[job_type](job_id)
            worker.ovdm.send_msg("Manual Stop of transfer" if 'Transfer' in job_type else "Manual Stop of task", job_name)

        job_results['parts'].append({"partName": "Stopped Job", "result": "Pass"})

    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle dynamic stopping of other tasks')
    parser.add_argument('-d', '--debug', action='store_true', help=' display debug messages')
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

    logging.info("\tTask: stopJob")
    new_worker.register_task("stopJob", task_stop_job)

    logging.info("Waiting for jobs...")
    new_worker.work()
