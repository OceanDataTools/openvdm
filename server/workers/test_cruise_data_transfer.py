#!/usr/bin/env python3
"""
FILE:  test_cruise_data_transfer.py

DESCRIPTION:  Gearman worker that handles testing cruise data transfer
                configurations

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2015-01-01
 REVISION:  2025-08-08
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

from server.lib.openvdm import OpenVDM
from server.lib.connection_utils import test_cdt_destination, test_cdt_rclone_destination

TASK_NAMES = {
    'TEST_CRUISE_DATA_TRANSFER': 'testCruiseDataTransfer'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


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

        cdt_cfg = payload_obj.get('cruiseDataTransfer', {})
        cdt_id = cdt_cfg.get('cruiseDataTransferID')

        if cdt_id:
            self.cruise_data_transfer = self.ovdm.get_cruise_data_transfer(cdt_id)

            if self.cruise_data_transfer is None:
                return self._fail_job(current_job, "Locate Cruise Data Transfer Data",
                                      "Could not find cruise data transfer config to use for connection test")

            self.cruise_data_transfer.update(cdt_cfg)

        elif not cdt_cfg:
            return self._fail_job(current_job, "Locate Cruise Data Transfer Data",
                                  "Could not find cruise data transfer config to use for connection test")

        else:
            self.cruise_data_transfer = cdt_cfg

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.cruise_data_transfer['name']}: %(message)s"
        ))

        logging.info("Job Started: %s", current_job.handle)

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)


    def test_cruise_dir(self, current_job):
        """
        Verify the cruise directory exists
        """

        results = []

        cruise_dir_exists = os.path.isdir(self.cruise_dir)
        if not cruise_dir_exists:
            return self._fail_job(current_job, "Verify cruise data directory exists",
                                  f"Unable to find cruise data directory: {self.cruise_dir}")

        results.extend([{"partName": "Verify cruise data directory exists", "result": "Pass"}])

        return results


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

        cst_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        if cst_id:
            self.ovdm.set_error_cruise_data_transfer_test(cst_id, f'Worker crashed: {str(exc_type)}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)
        parts = results.get('parts', [])
        final_verdict = parts[-1] if len(parts) else None
        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job Completed: %s", current_job.handle)

        if not cdt_id:
            return super().send_job_complete(current_job, job_result)

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', "undefined")
            self.ovdm.set_error_cruise_data_transfer_test(cdt_id, reason)
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
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


    def _ignore_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as ignored
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}]
        }))


def task_test_cruise_data_transfer(worker, current_job):
    """
    Run connection tests for a cruise data transfer
    """

    cdt_cfg = worker.cruise_data_transfer

    job_results = {'parts':[]}

    if 'cruiseDataTransferID' in cdt_cfg:
        logging.debug("Setting transfer test status to 'Running'")
        worker.ovdm.set_running_cruise_data_transfer_test(cdt_cfg['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Test cruise directory")
    worker.send_job_status(current_job, 33, 100)

    job_results['parts'] = worker.test_cruise_dir(current_job)

    logging.info("Test destination")
    worker.send_job_status(current_job, 66, 100)

    if ':' in cdt_cfg['destDir']:
        job_results['parts'].extend(test_cdt_rclone_destination(cdt_cfg))
    else:
        job_results['parts'].extend(test_cdt_destination(cdt_cfg))

    for test in job_results['parts']:
        if test['result'] == "Fail":
            job_results['parts'].extend([{"partName": "Final Verdict", "result": "Fail", "reason": test['reason']}])
            return json.dumps(job_results)

    job_results['parts'].extend([{"partName": "Final Verdict", "result": "Pass"}])

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle cruise data transfer connection test related tasks')
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

    logging.info("\tTask: %s", TASK_NAMES['TEST_CRUISE_DATA_TRANSFER'])
    new_worker.register_task(TASK_NAMES['TEST_CRUISE_DATA_TRANSFER'], task_test_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
