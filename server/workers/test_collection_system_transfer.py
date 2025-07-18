#!/usr/bin/env python3
"""
FILE:  test_collection_system_transfer.py

DESCRIPTION:  Gearman worker that handles testing collection system transfer
    configurations

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
import shutil
import subprocess
import sys
import tempfile
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM


def write_test(dest_dir):
    """
    Verify the current user has write permissions to the dest_dir
    """

    if os.path.isdir(dest_dir):
        try:
            filepath = os.path.join(dest_dir, 'writeTest.txt')
            with open(filepath, mode='w', encoding='utf-8') as filehandle:
                filehandle.write("this file tests if the parent directory can be written to.  You can delete this file if desired")

            os.remove(filepath)
        except Exception as err:
            logging.warning("Unable to write to %s", dest_dir)
            logging.warning(str(err))
            return False
        return True
    return False

def build_dest_dir(gearman_worker):
    """
    Replace any wildcards in the provided directory
    """

    lowering_id = gearman_worker.lowering_id if gearman_worker.lowering_id is not None else ""
    return gearman_worker.collection_system_transfer['destDir'].replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', lowering_id).replace('{loweringDataBaseDir}', gearman_worker.shipboard_data_warehouse_config['loweringDataBaseDir']).rstrip('/')


def build_source_dir(gearman_worker):
    """
    Replace any wildcards in the provided directory
    """

    lowering_id = gearman_worker.lowering_id if gearman_worker.lowering_id is not None else ""
    return gearman_worker.collection_system_transfer['sourceDir'].replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', lowering_id).replace('{loweringDataBaseDir}', gearman_worker.shipboard_data_warehouse_config['loweringDataBaseDir']).rstrip('/')


def test_local_source_dir(gearman_worker):
    """
    Verify the source directory exists for a local directory transfer
    """

    return_val = []

    source_dir = build_source_dir(gearman_worker)
    logging.debug("Source Dir: %s", source_dir)

    if not os.path.isdir(source_dir):
        return_val.append({"partName": "Source Directory", "result": "Fail", "reason": f"Unable to find source directory: {source_dir} on the Data Warehouse"})
        if gearman_worker.collection_system_transfer['localDirIsMountPoint'] == '1':
            return_val.append({"partName": "Source Directory is a Mountpoint", "result": "Fail", "reason": f"Unable to find source directory: {source_dir} on the Data Warehouse"})
    else:
        return_val.append({"partName": "Source Directory", "result": "Pass"})

        if gearman_worker.collection_system_transfer['localDirIsMountPoint'] == '1':
            if not os.path.ismount(source_dir):
                return_val.append({"partName": "Source Directory is a Mountpoint", "result": "Fail", "reason": f"Source directory: {source_dir} is not a mountpoint on the Data Warehouse"})
            else:
                return_val.append({"partName": "Source Directory is a Mountpoint", "result": "Pass"})

    return return_val


def test_smb_source_dir(gearman_worker):
    """
    Verify the source directory exists for a samba server transfer
    """

    return_val = []

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    # Verify the server exists
    server_test_command = ['smbclient', '-L', gearman_worker.collection_system_transfer['smbServer'], '-W', gearman_worker.collection_system_transfer['smbDomain'], '-m', 'SMB2', '-g', '-N'] if gearman_worker.collection_system_transfer['smbUser'] == 'guest' else ['smbclient', '-L', gearman_worker.collection_system_transfer['smbServer'], '-W', gearman_worker.collection_system_transfer['smbDomain'], '-m', 'SMB2', '-g', '-U', gearman_worker.collection_system_transfer['smbUser'] + '%' + gearman_worker.collection_system_transfer['smbPass']]
    logging.debug('SMB Server test command: %s', ' '.join(server_test_command))

    proc = subprocess.run(server_test_command, capture_output=True, text=True, check=False)

    vers = "2.1"
    found_server = False
    for line in proc.stdout.splitlines():
        logging.debug('STDOUT Line: %s', line.rstrip('\n')) # yield line
        if line.startswith( 'Disk' ):
            found_server = True
            break

    for line in proc.stderr.splitlines():
        logging.debug('STDERR Line: %s', line.rstrip('\n')) # yield line
        if line.startswith('OS=[Windows 5.1]'):
            vers="1.0"

    if not found_server:
        logging.warning("Server Test Failed")
        return_val.extend([
            {"partName": "SMB Server", "result": "Fail", "reason": f"Could not connect to SMB Server: {gearman_worker.collection_system_transfer['smbServer']} as {gearman_worker.collection_system_transfer['smbUser']}"},
            {"partName": "SMB Share", "result": "Fail", "reason": f"Could not connect to SMB Server: {gearman_worker.collection_system_transfer['smbServer']} as {gearman_worker.collection_system_transfer['smbUser']}"},
            {"partName": "Source Directory", "result": "Fail", "reason": f"Could not connect to SMB Server: {gearman_worker.collection_system_transfer['smbServer']} as {gearman_worker.collection_system_transfer['smbUser']}"}
        ])

        return return_val

    return_val.append({"partName": "SMB Server", "result": "Pass"})

    # Create mountpoint
    mntpoint = os.path.join(tmpdir, 'mntpoint')
    os.mkdir(mntpoint, 0o755)

    rw_type = 'rw' if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1' else 'ro'
    if gearman_worker.collection_system_transfer['smbUser'] == 'guest':
        rw_type += ',guest'
    else:
        rw_type += ',username=' + gearman_worker.collection_system_transfer['smbUser']
        rw_type += ',password=' + gearman_worker.collection_system_transfer['smbPass']

    # Mount SMB Share
    mount_command = ['sudo', 'mount', '-t', 'cifs', gearman_worker.collection_system_transfer['smbServer'], mntpoint, '-o', rw_type + ',domain=' + gearman_worker.collection_system_transfer['smbDomain'] + ',vers=' + vers]

    logging.debug("Mount command: %s", ' '.join(mount_command))

    proc = subprocess.run(mount_command, capture_output=True, check=False)

    if proc.returncode != 0:
        logging.warning("Connection test failed")
        return_val.extend([
            {"partName": "SMB Share", "result": "Fail", "reason": f"Could not connect to SMB Share: {gearman_worker.collection_system_transfer['smbServer']} as {gearman_worker.collection_system_transfer['smbUser']}"},
            {"partName": "Source Directory", "result": "Fail", "reason": f"Could not connect to SMB Share: {gearman_worker.collection_system_transfer['smbServer']} as {gearman_worker.collection_system_transfer['smbUser']}"}
        ])

        # Unmount SMB Share
        if os.path.ismount(mntpoint):
            subprocess.run(['sudo', 'umount', mntpoint], check=False)

        # Cleanup
        shutil.rmtree(tmpdir)

        return return_val

    return_val.append({"partName": "SMB Share", "result": "Pass"})

    logging.debug(gearman_worker.collection_system_transfer)
    gearman_worker.collection_system_transfer['sourceDir'] = gearman_worker.collection_system_transfer['sourceDir'].rstrip('/').lstrip('/')
    source_dir = mntpoint if gearman_worker.collection_system_transfer['sourceDir'] == '' else os.path.join(mntpoint, build_source_dir(gearman_worker))

    logging.debug('Source Dir: %s', source_dir)
    if os.path.isdir(source_dir):
        return_val.append({"partName": "Source Directory", "result": "Pass"})

        if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1':
            if not write_test(source_dir):
                return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to delete data from source directory: {source_dir}"})
                return return_val

            return_val.append({"partName": "Write Test", "result": "Pass"})

    else:
        logging.warning("Source Directory Test Failed")
        return_val.append({"partName": "Source Directory", "result": "Fail", "reason": f"Unable to find source directory: {source_dir} within the SMB Share: {gearman_worker.collection_system_transfer['smbServer']}"})

    # Unmount SMB Share
    if os.path.ismount(mntpoint):
        subprocess.run(['sudo', 'umount', mntpoint], check=False)

    # Cleanup
    shutil.rmtree(tmpdir)

    return return_val


def test_rsync_source_dir(gearman_worker):
    """
    Verify the source directory exists for a rsync server transfer
    """

    return_val = []

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    rsync_password_filepath = os.path.join(tmpdir,'passwordFile')

    try:

        logging.debug("Saving rsync password file %s", rsync_password_filepath)
        with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:

            if gearman_worker.collection_system_transfer['rsyncUser'] != 'anonymous':
                rsync_password_file.write(gearman_worker.collection_system_transfer['rsyncPass'])
            else:
                rsync_password_file.write('')

    except IOError:
        logging.error("Error Saving temporary rsync password file %s", rsync_password_filepath)
        return_val.append({"partName": "Writing temporary rsync password file", "result": "Fail", "reason": f"Unable to create temporary rsync password file: {rsync_password_filepath}"})

        # Cleanup
        shutil.rmtree(tmpdir)

        return return_val

    os.chmod(rsync_password_filepath, 0o600)

    server_test_command = ['rsync', '--no-motd', '--contimeout=5', '--password-file=' + rsync_password_filepath, 'rsync://' + gearman_worker.collection_system_transfer['rsyncUser'] + '@' + gearman_worker.collection_system_transfer['rsyncServer']]

    logging.debug('Server test command: %s', ' '.join(server_test_command))

    proc = subprocess.run(server_test_command, capture_output=True, check=False)

    if proc.returncode not in [0,24]:
        logging.warning("Connection test failed")
        return_val.extend([
            {"partName": "Rsync Connection", "result": "Fail", "reason": f"Unable to connect to rsync server: {gearman_worker.collection_system_transfer['rsyncServer']} as {gearman_worker.collection_system_transfer['rsyncUser']}"},
            {"partName": "Source Directory", "result": "Fail", "reason": f"Unable to connect to rsync server: {gearman_worker.collection_system_transfer['rsyncServer']} as {gearman_worker.collection_system_transfer['rsyncUser']}"}
        ])

    else:
        return_val.append({"partName": "Rsync Connection", "result": "Pass"})

        source_dir = build_source_dir(gearman_worker)
        logging.debug('Source Dir: %s', source_dir)

        source_test_command = ['rsync', '--no-motd', '--password-file=' + rsync_password_filepath, 'rsync://' + gearman_worker.collection_system_transfer['rsyncUser'] + '@' + gearman_worker.collection_system_transfer['rsyncServer'] + source_dir]

        logging.debug('Source test command: %s', ' '.join(source_test_command))

        proc = subprocess.run(source_test_command, capture_output=True, check=False)

        if proc.returncode not in [0,24]:
            logging.warning("Source Directory Test Failed")
            return_val.append({"partName": "Source Directory", "result": "Fail", "reason": f"Unable to find source directory: {source_dir} on the Rsync Server: {gearman_worker.collection_system_transfer['rsyncServer']}"})
        else:
            return_val.append({"partName": "Source Directory", "result": "Pass"})

    # Cleanup
    shutil.rmtree(tmpdir)

    return return_val


def test_ssh_source_dir(gearman_worker):
    """
    Verify the source directory exists for a ssh server transfer
    """

    return_val = []

    server_test_command = ['ssh', gearman_worker.collection_system_transfer['sshServer'], '-l', gearman_worker.collection_system_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

    if gearman_worker.collection_system_transfer['sshUseKey'] == '1':
        server_test_command += ['-o', 'PasswordAuthentication=no']

    else:
        server_test_command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + server_test_command + ['-o', 'PubkeyAuthentication=no']

    server_test_command += ['ls']

    logging.debug('Server test command: %s', ' '.join(server_test_command))

    proc = subprocess.run(server_test_command, capture_output=True, check=False)

    if proc.returncode != 0:
        logging.warning("Connection test failed")
        return_val.extend([
            {"partName": "SSH Connection", "result": "Fail", "reason": f"Unable to connect to ssh server: {gearman_worker.collection_system_transfer['sshServer']} as {gearman_worker.collection_system_transfer['sshUser']}"},
            {"partName": "Source Directory", "result": "Fail", "reason": f"Unable to connect to ssh server: {gearman_worker.collection_system_transfer['sshServer']} as {gearman_worker.collection_system_transfer['sshUser']}"}
        ])

        return return_val

    return_val.append({"partName": "SSH Connection", "result": "Pass"})

    source_dir = build_source_dir(gearman_worker)
    logging.debug('Source Dir: %s', source_dir)

    source_test_command = ['ssh', gearman_worker.collection_system_transfer['sshServer'], '-l', gearman_worker.collection_system_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

    if gearman_worker.collection_system_transfer['sshUseKey'] == '1':
        source_test_command += ['-o', 'PasswordAuthentication=no']

    else:
        source_test_command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + source_test_command + ['-o', 'PubkeyAuthentication=no']

    source_test_command += ['ls', "\"" + source_dir + "\""]

    logging.debug('Source test command: %s', ' '.join(source_test_command))

    proc = subprocess.run(source_test_command, capture_output=True, check=False)

    if proc.returncode != 0:
        logging.warning("Source directory test failed")
        return_val.append({"partName": "Source Directory", "result": "Fail", "reason": f"Unable to find source directory: {source_dir} on the SSH Server: {gearman_worker.collection_system_transfer['sshServer']}"})
    else:
        return_val.append({"partName": "Source Directory", "result": "Pass"})

    return return_val


def test_dest_dir(gearman_worker):
    """
    Verify the destination directory exists
    """

    dest_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id, build_dest_dir(gearman_worker))

    if gearman_worker.collection_system_transfer['cruiseOrLowering'] == '1':
        if gearman_worker.lowering_id == '':
            return [{"partName": "Destination Directory", "result": "Fail", "reason": "Lowering ID is undefined" }]

        dest_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id, gearman_worker.shipboard_data_warehouse_config['loweringDataBaseDir'], gearman_worker.lowering_id, build_dest_dir(gearman_worker))

    logging.debug('Destination Directory: %s', dest_dir)

    return [{"partName": "Destination Directory", "result": "Pass"}] if os.path.isdir(dest_dir) else [{"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to find destination directory: {dest_dir} on Data Warehouse"}]


class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.lowering_id = None
        self.collection_system_transfer = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])

    def on_job_execute(self, current_job):
        """
        Function run whenever a new job arrives
        """

        logging.debug("current_job: %s", current_job)

        self.stop = False
        payload_obj = json.loads(current_job.data)

        if 'collectionSystemTransferID' in payload_obj['collectionSystemTransfer']:
            self.collection_system_transfer = self.ovdm.get_collection_system_transfer(payload_obj['collectionSystemTransfer']['collectionSystemTransferID'])

            if not self.collection_system_transfer:
                return self.on_job_complete(current_job, json.dumps({'parts':[
                    {"partName": "Located Collection System Tranfer Data", "result": "Fail", "reason": "Could not find configuration data for collection system transfer"},
                    {"partName": "Final Verdict", "result": "Fail", "reason": "Could not find configuration data for collection system transfer"}
                ]}))

            self.collection_system_transfer.update(payload_obj['collectionSystemTransfer'])

        else:
            self.collection_system_transfer = payload_obj['collectionSystemTransfer']

        self.cruise_id = payload_obj['cruiseID'] if 'cruiseID' in payload_obj else self.ovdm.get_cruise_id()
        self.lowering_id = payload_obj['loweringID'] if 'loweringID' in payload_obj else self.ovdm.get_lowering_id()

        if self.collection_system_transfer['cruiseOrLowering'] == '1' and self.lowering_id is None:
            try:
                return self.on_job_complete(current_job, json.dumps({'parts':[
                    {"partName": "Retrieve Lowering ID", "result": "Fail", "reason": "Lowering ID is not defined"},
                    {"partName": "Final Verdict", "result": "Fail", "reason": "Lowering ID is not defined"}]
                }))
            except Exception as err:
                raise err

        logging.info("Job: %s, %s transfer test started at: %s", current_job.handle, self.collection_system_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s, %s transfer test failed at: %s", current_job.handle, self.collection_system_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{"partName": "Worker crashed", "result": "Fail", "reason": "Unknown"}]))

        if 'collectionSystemTransferID' in self.collection_system_transfer:
            self.ovdm.set_error_collection_system_transfer_test(self.collection_system_transfer['collectionSystemTransferID'], 'Worker crashed')

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)
        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run whenever the current job completes
        """

        results_obj = json.loads(job_result)

        if 'collectionSystemTransferID' in self.collection_system_transfer:
            if len(results_obj['parts']) > 0:
                if results_obj['parts'][-1]['result'] == "Fail": # Final Verdict
                    self.ovdm.set_error_collection_system_transfer_test(self.collection_system_transfer['collectionSystemTransferID'], results_obj['parts'][-1]['reason'])
                else:
                    self.ovdm.clear_error_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'], self.collection_system_transfer['status'])
            else:
                self.ovdm.clear_error_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'], self.collection_system_transfer['status'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s, %s transfer test completed at: %s", current_job.handle, self.collection_system_transfer['name'], time.strftime("%D %T", time.gmtime()))

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


def task_test_collection_system_transfer(gearman_worker, current_job):
    """
    Run connection tests for a collection system transfer
    """

    job_results = {'parts':[]}

    if 'collectionSystemTransferID' in gearman_worker.collection_system_transfer:
        gearman_worker.ovdm.set_running_collection_system_transfer_test(gearman_worker.collection_system_transfer['collectionSystemTransferID'], os.getpid(), current_job.handle)

    gearman_worker.send_job_status(current_job, 1, 4)

    logging.info("Testing Source Directory")
    if gearman_worker.collection_system_transfer['transferType'] == "1": # Local Directory
        job_results['parts'] = test_local_source_dir(gearman_worker)
    elif  gearman_worker.collection_system_transfer['transferType'] == "2": # Rsync Server
        job_results['parts'] += test_rsync_source_dir(gearman_worker)
    elif  gearman_worker.collection_system_transfer['transferType'] == "3": # SMB Share
        job_results['parts'] += test_smb_source_dir(gearman_worker)
    elif  gearman_worker.collection_system_transfer['transferType'] == "4": # SSH Server
        job_results['parts'] += test_ssh_source_dir(gearman_worker)

    gearman_worker.send_job_status(current_job, 2, 4)

    if gearman_worker.collection_system_transfer['enable'] == '1':
        logging.info("Testing Destination Directory")
        job_results['parts'] += test_dest_dir(gearman_worker)
        gearman_worker.send_job_status(current_job, 3, 4)

    verdict = True
    for test in job_results['parts']:
        if test['result'] == "Fail":
            verdict = False
            job_results['parts'].append({"partName": "Final Verdict", "result": "Fail", "reason": test['reason']})
            break

    if verdict:
        job_results['parts'].append({"partName": "Final Verdict", "result": "Pass"})

    gearman_worker.send_job_status(current_job, 4, 4)

    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle collection system transfer connection test related tasks')
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

    logging.info("\tTask: testCollectionSystemTransfer")
    new_worker.register_task("testCollectionSystemTransfer", task_test_collection_system_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
