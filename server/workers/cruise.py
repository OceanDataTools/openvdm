#!/usr/bin/env python3
"""
FILE:  cruise.py

DESCRIPTION:  Gearman worker the handles the tasks of initializing a new cruise
    and finalizing the current cruise.  This includes initializing/finalizing
    the data dashboard, MD5summary and transfer log summary.

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
import signal
import subprocess
import sys
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.connection_utils import build_rsync_command
from server.lib.file_utils import build_filelist, build_include_file, clear_directory, output_json_data_to_file, set_owner_group_permissions, temporary_directory
from server.lib.openvdm import OpenVDM

TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

def export_cruise_config(gearman_worker, cruise_config_file_path, finalize=False):
    """
    Export the current cruise configuration to the specified file.
    If 'finalize' is True, mark the config as finalized.
    """
    cruise_config = gearman_worker.ovdm.get_cruise_config()

    if finalize:
        cruise_config['cruiseFinalizedOn'] = cruise_config['configCreatedOn']
    elif os.path.isfile(cruise_config_file_path):
        logging.info("Reading existing configuration file")
        try:
            with open(cruise_config_file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                cruise_config['cruiseFinalizedOn'] = existing_data.get('cruiseFinalizedOn')
        except OSError as err:
            logging.debug("Error reading config: %s", err)
            return {'verdict': False, 'reason': "Unable to read existing configuration file"}

    def scrub_transfer(transfer_list, lowering_data_base_dir):
        for transfer in transfer_list:
            if transfer['cruiseOrLowering'] == '1':
                transfer['destDir'] = os.path.join(lowering_data_base_dir, "{loweringID}", transfer['destDir'])

            allowed_keys = ['name', 'longName', 'destDir']
            for key in list(transfer.keys()):
                if key not in allowed_keys:
                    transfer.pop(key)

    # scrub_passwords(cruise_config.get('collectionSystemTransfersConfig', []))
    scrub_transfer(cruise_config.get('collectionSystemTransfersConfig', []), cruise_config.get('loweringDataBaseDir'))
    scrub_transfer(cruise_config.get('extraDirectoriesConfig', []), cruise_config.get('loweringDataBaseDir'))

    cruise_config['md5SummaryFn'] = cruise_config['warehouseConfig']['md5SummaryFn']
    cruise_config['md5SummaryMd5Fn'] = cruise_config['warehouseConfig']['md5SummaryMd5Fn']

    del cruise_config['warehouseConfig']
    del cruise_config['cruiseDataTransfersConfig']
    del cruise_config['shipToShoreTransfersConfig']

    output_results = output_json_data_to_file(cruise_config_file_path, cruise_config)
    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason']}

    output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], cruise_config_file_path)
    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason']}

    gearman_worker.update_md5_summary(output_results.get('files', {'new':[], 'updated':[]}))

    return {'verdict': True}


def run_transfer_command(gearman_worker, gearman_job, cmd, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.info("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.info('Transfer Command: %s', ' '.join(cmd))

    new_files = []
    updated_files = []
    last_percent_reported = -1

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while proc.poll() is None:

        for line in proc.stdout:

            if gearman_worker.stop:
                logging.debug("Stopping")
                proc.terminate()
                break

            line = line.strip()

            if not line:
                continue

            if line.startswith( '>f+++++++++' ):
                filename = line.split(' ',1)[1]
                new_files.append(filename.rstrip('\n'))
            elif line.startswith( '>f.' ):
                filename = line.split(' ',1)[1]
                updated_files.append(filename.rstrip('\n'))

            # Extract progress from `to-chk=` lines
            match = TO_CHK_RE.search(line)
            if match:
                remaining = int(match.group(1))
                total = int(match.group(2))
                if total > 0:
                    percent = int(100 * (total - remaining) / total)

                    if percent != last_percent_reported:
                        logging.info("Progress Update: %d%%", percent)
                        if gearman_job:
                            gearman_worker.send_job_status(gearman_job, int(20 + 70 * percent / 100), 100)
                        last_percent_reported = percent

    return new_files, updated_files


def transfer_publicdata_dir(gearman_worker, gearman_job, start_status, end_status, remove_source_files=False):
    """
    Transfer the contents of the PublicData share to the Cruise Data Directory
    """

    job_results = {'parts':[]}

    source_dir = gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir']
    dest_dir = os.path.join(gearman_worker.cruise_dir, gearman_worker.ovdm.get_required_extra_directory_by_name('From_PublicData')['destDir'])

    logging.debug("Verify PublicData Directory exists")
    if not os.path.exists(source_dir):
        job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Fail", "reason": "PublicData directory: " + source_dir + " could not be found"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Pass"})

    logging.debug("Verify From_PublicData directory exists within the cruise data directory")
    if not os.path.exists(dest_dir):
        job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Fail", "reason": "From_PublicData directory: " + dest_dir + " could not be found"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Pass"})

    logging.debug("Building file list")
    files = build_filelist(source_dir)
    logging.debug("Files: %s", json.dumps(files, indent=2))
    gearman_worker.send_job_status(gearman_job, int((end_status - start_status) * 10/100) + start_status, 100)

    if len(files['exclude']) > 0:
        logging.warning("Found %s problem filename(s):", len(files['exclude']))
        logging.warning("\t %s", "\n\t".join(files['exclude']))
        return {'verdict': False, 'reason': f"Symbolic links or Non-ASCii filenames in {source_dir}: {', '.join(files['exclude'])}"}

    with temporary_directory() as tmpdir:    # Create temp directory
        include_file = os.path.join(tmpdir, 'rsyncFileList.txt')
        if not build_include_file(files['include'], include_file):
            return {'verdict': False, 'reason': "Error Saving temporary rsync filelist file"}

        gearman_worker.send_job_status(gearman_job, int((end_status - start_status) * 20/100) + start_status, 100)

        # Build transfer command
        rsync_flags = ['-trivm', '--progress', '--protect-args', '--min-size=1']

        if remove_source_files:
            rsync_flags.append('--remove-source-files')
        else:
            rsync_flags.append('--delete')

        cmd = build_rsync_command(rsync_flags, [], source_dir, dest_dir, include_file)

        # Transfer files
        files['new'], files['updated'] = run_transfer_command(
            gearman_worker, gearman_worker, cmd, len(files['include'])
        )
        gearman_worker.send_job_status(gearman_job, int((end_status - start_status) * 70/100) + start_status, 100)

        output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], dest_dir)
        gearman_worker.send_job_status(gearman_job, int((end_status - start_status) * 80/100) + start_status, 100)

        if not output_results['verdict']:
            return {'verdict': False, 'reason': output_results['reason']}

        gearman_worker.update_md5_summary(files)
        gearman_worker.send_job_status(gearman_job, int((end_status - start_status) * 90/100) + start_status, 100)

        return {'verdict': True}


class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.cruise_id = None
        self.cruise_start_date = None
        self.shipboard_data_warehouse_config = None
        self.cruise_dir = None
        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def update_md5_summary(self, files):
        gm_data = {
            'cruiseID': self.cruise_id,
            'files': files
        }

        gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])
        gm_client.submit_job("updateMD5Summary", json.dumps(gm_data))

        logging.debug("MD5 Summary Task Complete")


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
            return self._fail_job(current_job, "Retrieve Collection System Transfer Data", reason)

        self.task = self.ovdm.get_task_by_name(current_job.task)
        logging.debug("task: %s", self.task)

        if int(self.task['taskID']) > 0:
            self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)

        logging.info("Job: %s (%s) started at: %s", self.task['longName'], current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.cruise_start_date = payload_obj.get('cruiseStartDate',self.ovdm.get_cruise_start_date())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s (%s) failed at: %s", self.task['longName'], current_job.handle, time.strftime("%D %T", time.gmtime()))

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

        job_data = {
            'cruiseID': self.cruise_id,
            'cruiseStartDate': self.cruise_start_date
        }

        if current_job.task == "setupNewCruise":

            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            for task in self.ovdm.get_tasks_for_hook('setupNewCruise'):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        elif current_job.task == "finalizeCurrentCruise":

            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            for task in self.ovdm.get_tasks_for_hook('finalizeCurrentCruise'):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        if len(results['parts']) > 0:
            if results['parts'][-1]['result'] == "Fail": # Final Verdict
                if int(self.task['taskID']) > 0:
                    self.ovdm.set_error_task(self.task['taskID'], results['parts'][-1]['reason'])
                else:
                    self.ovdm.send_msg(self.task['longName'] + ' failed', results['parts'][-1]['reason'])
            else:
                self.ovdm.set_idle_task(self.task['taskID'])
        else:
            self.ovdm.set_idle_task(self.task['taskID'])

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job: %s (%s) completed at: %s", self.task['longName'], current_job.handle,
                     time.strftime("%D %T", time.gmtime()))

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


def task_setup_new_cruise(gearman_worker, gearman_job): # pylint: disable=too-many-return-statements,too-many-statements
    """
    Setup a new cruise
    """

    job_results = {'parts':[]}

    cruise_config_file_path = os.path.join(gearman_worker.cruise_dir, gearman_worker.shipboard_data_warehouse_config['cruiseConfigFn'])

    gearman_worker.send_job_status(gearman_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([gearman_worker.ovdm.get_gearman_server()])

    logging.info("Set ownership/permissions for the CruiseData directory")
    completed_job_request = gm_client.submit_job("setCruiseDataDirectoryPermissions", gearman_job.data)

    result_obj = json.loads(completed_job_request.result)

    if result_obj['parts'][-1]['result'] != "Pass": # Final Verdict
        logging.error("Failed to lockdown the CruiseData directory")
        job_results['parts'].append({"partName": "Set ownership/permissions for CruiseData directory", "result": "Fail", "reason": result_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Set ownership/permissions for CruiseData directory", "result": "Pass"})

    logging.info("Creating cruise data directory")
    completed_job_request = gm_client.submit_job("createCruiseDirectory", gearman_job.data)

    result_obj = json.loads(completed_job_request.result)

    if result_obj['parts'][-1]['result'] != "Pass": # Final Verdict
        logging.error("Failed to create cruise data directory")
        job_results['parts'].append({"partName": "Create cruise data directory structure", "result": "Fail", "reason": result_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create cruise data directory structure", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 5, 10)

    #build OpenVDM Config file
    logging.info("Exporting Cruise Configuration")
    output_results = export_cruise_config(gearman_worker, cruise_config_file_path)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 7, 10)

    logging.info("Creating MD5 summary files")
    completed_job_request = gm_client.submit_job("rebuildMD5Summary", gearman_job.data)

    result_obj = json.loads(completed_job_request.result)

    if result_obj['parts'][-1]['result'] != "Pass": # Final Verdict
        logging.error("Failed to create MD5 summary files")
        job_results['parts'].append({"partName": "Create MD5 summary files", "result": "Fail", "reason": result_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create MD5 summary files", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 8, 10)

    logging.info("Creating data dashboard directory structure and manifest file")
    completed_job_request = gm_client.submit_job("rebuildDataDashboard", gearman_job.data)

    result_obj = json.loads(completed_job_request.result)

    if result_obj['parts'][-1]['result'] != "Pass": # Final Verdict
        logging.error("Failed to create data dashboard directory structure and/or manifest file")
        job_results['parts'].append({"partName": "Create data dashboard directory structure and manifest file", "result": "Fail", "reason": result_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create data dashboard directory structure and manifest file", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 9, 10)

    logging.info("Updating Cruise Size")
    cruise_size_proc = subprocess.run(['du','-sb', gearman_worker.cruise_dir], capture_output=True, text=True, check=False)
    if cruise_size_proc.returncode == 0:
        logging.info("Cruise Size: %s", cruise_size_proc.stdout.split()[0])
        gearman_worker.ovdm.set_cruise_size(cruise_size_proc.stdout.split()[0])
    else:
        gearman_worker.ovdm.set_cruise_size("0")

    gearman_worker.ovdm.set_lowering_size("0")

    gearman_worker.send_job_status(gearman_job, 10, 10)

    return json.dumps(job_results)


def task_finalize_current_cruise(gearman_worker, gearman_job): # pylint: disable=too-many-return-statements,too-many-statements
    """
    Finalize the current cruise
    """

    job_results = {'parts':[]}

    gearman_worker.send_job_status(gearman_job, 1, 10)

    # publicdata_dir = gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir']

    cruise_config_file_path = os.path.join(gearman_worker.cruise_dir, gearman_worker.shipboard_data_warehouse_config['cruiseConfigFn'])

    if not os.path.exists(gearman_worker.cruise_dir):
        job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Fail", "reason": "Cruise directory: " + gearman_worker.cruise_dir + " could not be found"})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 2, 10)
    logging.info("Queuing Collection System Transfers")

    gm_client = python3_gearman.GearmanClient([gearman_worker.ovdm.get_gearman_server()])

    gm_data = {
        'cruiseID': gearman_worker.cruise_id,
        'cruiseStartDate': gearman_worker.cruise_start_date,
        'systemStatus': "On",
        'collectionSystemTransfer': {}
    }

    collection_system_transfer_jobs = []

    collection_system_transfers = gearman_worker.ovdm.get_active_collection_system_transfers(lowering=False)

    for collection_system_transfer in collection_system_transfers:

        logging.debug("Queuing runCollectionSystemTransfer job for %s", collection_system_transfer['name'])
        gm_data['collectionSystemTransfer']['collectionSystemTransferID'] = collection_system_transfer['collectionSystemTransferID']

        collection_system_transfer_jobs.append( {"task": "runCollectionSystemTransfer", "data": json.dumps(gm_data)} )

    gearman_worker.send_job_status(gearman_job, 3, 10)

    logging.info("Submitting runCollectionSystemTransfer jobs")
    submitted_job_request = gm_client.submit_multiple_jobs(collection_system_transfer_jobs, background=False, wait_until_complete=False)

    gearman_worker.send_job_status(gearman_job, 4, 10)

    time.sleep(1)

    if gearman_worker.ovdm.get_transfer_public_data():

        # logging.info("Transferring files from PublicData to the cruise data directory")
        # from_publicdata_dir = os.path.join(gearman_worker.cruise_dir, gearman_worker.ovdm.get_required_extra_directory_by_name('From_PublicData')['destDir'])

        # logging.debug("Verify From_PublicData directory exists within the cruise data directory")
        # if not os.path.exists(from_publicdata_dir):
        #     job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Fail", "reason": "From_PublicData directory: " + from_publicdata_dir + " could not be found"})
        #     return json.dumps(job_results)

        # job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Pass"})

        # logging.debug("Verify PublicData Directory exists")
        # if not os.path.exists(publicdata_dir):
        #     job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Fail", "reason": "PublicData directory: " + publicdata_dir + " could not be found"})
        #     return json.dumps(job_results)

        # job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Pass"})

        logging.debug("Transferring public data files to cruise data directory")
        output_results = transfer_publicdata_dir(gearman_worker, gearman_job, 40, 80, True)
        logging.debug("Transfer Complete")

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Transfer PublicData files", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Transfer PublicData files", "result": "Pass"})
        gearman_worker.send_job_status(gearman_job, 8, 10)

        logging.info("Clearing files from PublicData")
        publicdata_dir = gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir']
        output_results = clear_directory(publicdata_dir)
        logging.debug("Clearing Complete")

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Clear out PublicData files", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        gearman_worker.send_job_status(gearman_job, 9, 10)

        # if len(files['new']) > 0 or len(files['updated']) > 0:

        #     output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], from_publicdata_dir)

        #     if not output_results['verdict']:
        #         job_results['parts'].append({"partName": "Set file/directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        #         return json.dumps(job_results)

        #     job_results['parts'].append({"partName": "Set file/directory ownership/permissions", "result": "Pass"})

    gm_client.wait_until_jobs_completed(submitted_job_request)
    logging.info("Completed runCollectionSystemTransfers jobs")
    job_results['parts'].append({"partName": "Run Collection System Transfers jobs", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 95, 100)

    #build OpenVDM Config file
    logging.info("Exporting OpenVDM Configuration")
    output_results = export_cruise_config(gearman_worker, cruise_config_file_path, finalize=True)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})

    # output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], cruise_config_file_path)

    # if not output_results['verdict']:
    #     job_results['parts'].append({"partName": "Set OpenVDM config file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
    #     return json.dumps(job_results)

    # job_results['parts'].append({"partName": "Set OpenVDM config file ownership/permissions", "result": "Pass"})

    # logging.info("Initiating MD5 Summary Task")

    # gm_data = {
    #     'cruiseID': gearman_worker.cruise_id,
    #     'files': files
    # }

    # gm_data['files']['updated'].append(gearman_worker.shipboard_data_warehouse_config['cruiseConfigFn'])

    # gm_client.submit_job("updateMD5Summary", json.dumps(gm_data))

    # logging.debug("MD5 Summary Task Complete")

    gearman_worker.send_job_status(gearman_job, 10, 10)
    return json.dumps(job_results)

def task_rsync_publicdata_to_cruise_data(gearman_worker, gearman_job):
    """
    Sync the contents of the PublicData share to the from_PublicData Extra Directory
    """

    job_results = {'parts':[]}

    publicdata_dir = gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehousePublicDataDir']
    from_publicdata_dir = os.path.join(gearman_worker.cruise_dir, gearman_worker.ovdm.get_required_extra_directory_by_name('From_PublicData')['destDir'])

    gearman_worker.send_job_status(gearman_job, 1, 10)

    if os.path.exists(from_publicdata_dir):
        job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Verify From_PublicData directory exists", "result": "Fail", "reason": "Unable to locate the From_PublicData directory: " + from_publicdata_dir})
        return json.dumps(job_results)

    if os.path.exists(publicdata_dir):
        job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Verify PublicData directory exists", "result": "Fail", "reason": "Unable to locate the PublicData directory: " + publicdata_dir})
        return json.dumps(job_results)

    gearman_worker.send_job_status(gearman_job, 5, 10)

    logging.info("Transferring files from PublicData to the cruise data directory")
    output_results = transfer_publicdata_dir(gearman_worker, gearman_job, 50, 100)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Transfer files", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Transfer files", "result": "Pass"})

    gearman_worker.send_job_status(gearman_job, 10, 10)
    return json.dumps(job_results)


def task_export_cruise_config(gearman_worker, gearman_job):
    """
    Export the OpenVDM configuration to file
    """

    job_results = {'parts':[]}

    cruise_config_file_path = os.path.join(gearman_worker.cruise_dir, gearman_worker.shipboard_data_warehouse_config['cruiseConfigFn'])

    gearman_worker.send_job_status(gearman_job, 1, 10)

    logging.info("Verifying cruise directory exists")
    if os.path.exists(gearman_worker.cruise_dir):
        job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Verify cruise directory exists", "result": "Fail", "reason": "Unable to locate the cruise directory: " + gearman_worker.cruise_dir})
        return json.dumps(job_results)

    gearman_worker.send_job_status(gearman_job, 3, 10)

    #build Cruise Config file
    logging.info("Exporting Cruise Configuration")
    output_results = export_cruise_config(gearman_worker, cruise_config_file_path)

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Export cruise config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    gearman_worker.send_job_status(gearman_job, 6, 10)

    logging.info("Setting file ownership/permissions")
    output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], cruise_config_file_path)

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Set file ownership/permissions", "result": "Pass"})
    else:
        job_results['parts'].append({"partName": "Set file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    gearman_worker.send_job_status(gearman_job, 10, 10)
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

    logging.debug("Creating Worker...")

    # global new_worker
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

    logging.info("\tTask: setupNewCruise")
    new_worker.register_task("setupNewCruise", task_setup_new_cruise)

    logging.info("\tTask: finalizeCurrentCruise")
    new_worker.register_task("finalizeCurrentCruise", task_finalize_current_cruise)

    logging.info("\tTask: exportOVDMConfig")
    new_worker.register_task("exportOVDMConfig", task_export_cruise_config)

    logging.info("\tTask: rsyncPublicDataToCruiseData")
    new_worker.register_task("rsyncPublicDataToCruiseData", task_rsync_publicdata_to_cruise_data)

    logging.info("Waiting for jobs...")
    new_worker.work()
