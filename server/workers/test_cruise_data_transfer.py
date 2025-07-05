#!/usr/bin/env python3
"""
FILE:  test_cruise_data_transfer.py

DESCRIPTION:  Gearman worker that handles testing cruise data transfer
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
import sys
import time
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM
from server.lib.connection_utils import test_cdt_destination

TASK_NAMES = {
    'TEST_CRUISE_DATA_TRANSFER': 'testCruiseDataTransfer'
}

# def write_test(dest_dir):
#     """
#     Verify the current user has write permissions to the dest_dir
#     """

#     if os.path.isdir(dest_dir):
#         try:
#             filepath = os.path.join(dest_dir, 'writeTest.txt')
#             with open(filepath, mode='w', encoding='utf-8') as filehandle:
#                 filehandle.write("this file tests if the parent directory can be written to.  You can delete this file if desired")

#             os.remove(filepath)
#         except Exception as err:
#             logging.warning("Unable to write to %s", dest_dir)
#             logging.warning(str(err))
#             return False
#         return True
#     return False


# def test_local_dest_dir(worker):
#     """
#     Verify the destination directory exists for a local directory transfer
#     """

#     return_val = []

#     dest_dir = worker.cruise_data_transfer['destDir']

#     if not os.path.isdir(dest_dir):
#         return_val.append({"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to locate destination directory: {dest_dir}"})
#         if worker.cruise_data_transfer['localDirIsMountPoint'] == '1':
#             return_val.append({"partName": "Destination Directory is a Mountpoint", "result": "Fail", "reason": f"Unable to locate destination directory: {dest_dir}"})
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to locate destination directory: {dest_dir}"})

#         return return_val

#     return_val.append({"partName": "Destination Directory", "result": "Pass"})

#     if worker.cruise_data_transfer['localDirIsMountPoint'] == '1':
#         if not os.path.ismount(dest_dir):
#             return_val.extend([
#                 {"partName": "Destination Directory is a Mountpoint", "result": "Fail", "reason": f"Destination directory: {dest_dir} is not a mountpoint"},
#                 {"partName": "Write Test", "result": "Fail", "reason": f"Destination directory: {dest_dir} is not a mountpoint"}
#             ])

#             return return_val

#         return_val.append({"partName": "Destination Directory is a Mountpoint", "result": "Pass"})

#     if not write_test(dest_dir):
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to write data to desination directory: {dest_dir}"})
#         return return_val

#     return_val.append({"partName": "Write Test", "result": "Pass"})

#     return return_val


# def test_smb_dest_dir(worker):
#     """
#     Verify the destination directory exists for a smb server transfer
#     """

#     return_val = []

#     # Verify the server exists
#     server_test_command = ['smbclient', '-L', worker.cruise_data_transfer['smbServer'], '-W', worker.cruise_data_transfer['smbDomain'], '-m', 'SMB2', '-g', '-N'] if worker.cruise_data_transfer['smbUser'] == 'guest' else ['smbclient', '-L', worker.cruise_data_transfer['smbServer'], '-W', worker.cruise_data_transfer['smbDomain'], '-m', 'SMB2', '-g', '-U', worker.cruise_data_transfer['smbUser'] + '%' + worker.cruise_data_transfer['smbPass']]
#     logging.debug("Server test command: %s", ' '.join(server_test_command))

#     proc = subprocess.run(server_test_command, capture_output=True, text=True, check=False)

#     vers = "2.1"
#     found_server = False
#     for line in proc.stdout.splitlines():
#         logging.debug("STDOUT Line: %s", line.rstrip('\n')) # yield line
#         if line.startswith( "Disk" ):
#             found_server = True
#             break

#     for line in proc.stderr.splitlines():
#         logging.debug("STDERR Line: %s", line.rstrip('\n')) # yield line
#         if line.startswith("OS=[Windows 5.1]"):
#             vers="1.0"

#     if not found_server:
#         return_val.extend([
#             {"partName": "SMB Server", "result": "Fail", "reason": f"Could not connect to SMB Server: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"},
#             {"partName": "SMB Share", "result": "Fail", "reason": f"Could not connect to SMB Server: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"},
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Could not connect to SMB Server: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Could not connect to SMB Server: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"}
#         ])

#         return return_val

#     return_val.append({"partName": "SMB Server", "result": "Pass"})

#     # Create temp directory
#     tmpdir = tempfile.mkdtemp()

#     # Create mountpoint
#     mntpoint = os.path.join(tmpdir, 'mntpoint')
#     os.mkdir(mntpoint, 0o755)

#     # Mount SMB Share
#     mount_command = ['mount', '-t', 'cifs', worker.cruise_data_transfer['smbServer'], mntpoint, '-o', 'rw'+',guest'+',domain='+worker.cruise_data_transfer['smbDomain']+',vers='+vers] if worker.cruise_data_transfer['smbUser'] == 'guest' else ['mount', '-t', 'cifs', worker.cruise_data_transfer['smbServer'], mntpoint, '-o', 'rw'+',username='+worker.cruise_data_transfer['smbUser']+',password='+worker.cruise_data_transfer['smbPass']+',domain='+worker.cruise_data_transfer['smbDomain']+',vers='+vers]

#     logging.debug("Mount command: %s", ' '.join(mount_command))

#     proc = subprocess.run(mount_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.extend([
#             {"partName": "SMB Share", "result": "Fail", "reason": f"Could not connect to SMB Share: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"},
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Could not connect to SMB Share: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Could not connect to SMB Share: {worker.cruise_data_transfer['smbServer']} as {worker.cruise_data_transfer['smbUser']}"}
#         ])

#         # Cleanup
#         shutil.rmtree(tmpdir)

#         return return_val

#     return_val.append({"partName": "SMB Share", "result": "Pass"})

#     dest_dir = os.path.join(mntpoint, worker.cruise_data_transfer['destDir'])
#     if not os.path.isdir(dest_dir):
#         return_val.append({"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to find destination directory: {worker.cruise_data_transfer['destDir']} within the SMB Share: {worker.cruise_data_transfer['smbServer']}"})
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to find destination directory: {worker.cruise_data_transfer['destDir']} within the SMB Share: {worker.cruise_data_transfer['smbServer']}"})

#     else:
#         return_val.append({"partName": "Destination Directory", "result": "Pass"})

#         if not write_test(dest_dir):
#             return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to write to destination directory: {dest_dir} within the SMB Share: {worker.cruise_data_transfer['smbServer']}"})
#         else:
#             return_val.append({"partName": "Write Test", "result": "Pass"})


#     # Unmount SMB Share
#     if os.path.ismount(mntpoint):
#         subprocess.call(['sudo', 'umount', mntpoint])

#     # Cleanup
#     shutil.rmtree(tmpdir)

#     return return_val


# def test_rsync_dest_dir(worker):
#     """
#     Verify the destination directory exists for a rsync server transfer
#     """

#     return_val = []

#     # Create temp directory
#     tmpdir = tempfile.mkdtemp()

#     rsync_password_filepath = os.path.join(tmpdir,'passwordFile')

#     try:
#         with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:

#             if worker.cruise_data_transfer['rsyncUser'] != 'anonymous':
#                 rsync_password_file.write(worker.cruise_data_transfer['rsyncPass'])
#             else:
#                 rsync_password_file.write('')

#     except IOError:
#         logging.error("Error Saving temporary rsync password file %s", rsync_password_filepath)
#         return_val.append({"partName": "Writing temporary rsync password file", "result": "Fail", "reason": f"Unable to create temporary rsync password file: {rsync_password_filepath}"})

#         # Cleanup
#         shutil.rmtree(tmpdir)

#         return return_val

#     os.chmod(rsync_password_filepath, 0o600)

#     server_test_command = ['rsync', '--no-motd', '--password-file=' + rsync_password_filepath, 'rsync://' + worker.cruise_data_transfer['rsyncUser'] + '@' + worker.cruise_data_transfer['rsyncServer']]

#     logging.debug("Server test command: %s", ' '.join(server_test_command))

#     proc = subprocess.run(server_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.extend([
#             {"partName": "Rsync Connection", "result": "Fail", "reason": f"Unable to connect to rsync server: {worker.cruise_data_transfer['rsyncServer']} as {worker.cruise_data_transfer['rsyncUser']}"},
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to connect to rsync server: {worker.cruise_data_transfer['rsyncServer']} as {worker.cruise_data_transfer['rsyncUser']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Unable to connect to rsync server: {worker.cruise_data_transfer['rsyncServer']} as {worker.cruise_data_transfer['rsyncUser']}"}
#         ])

#         # Cleanup
#         shutil.rmtree(tmpdir)

#         return return_val

#     return_val.append({"partName": "Rsync Connection", "result": "Pass"})

#     dest_dir = worker.cruise_data_transfer['destDir']

#     dest_test_command = ['rsync', '--contimeout=5', '--no-motd', '--password-file=' + rsync_password_filepath, 'rsync://' + worker.cruise_data_transfer['rsyncUser'] + '@' + worker.cruise_data_transfer['rsyncServer'] + dest_dir]

#     logging.debug("Destination test command: %s", ' '.join(dest_test_command))

#     proc = subprocess.run(dest_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.extend([
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to find destination directory: {dest_dir} on the Rsync Server: {worker.cruise_data_transfer['rsyncServer']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Unable to find destination directory: {dest_dir} on the Rsync Server: {worker.cruise_data_transfer['rsyncServer']}"}
#         ])

#         # Cleanup
#         shutil.rmtree(tmpdir)

#         return return_val

#     return_val.append({"partName": "Destination Directory", "result": "Pass"})

#     write_test_file = os.path.join(tmpdir, 'writeTest.txt')
#     with open(write_test_file, mode='a', encoding='utf-8') as write_test_file_handle:
#         write_test_file_handle.write("This file proves this directory can be written to by OpenVDM")

#     write_test_command = ['rsync', '-vi', '--no-motd', '--password-file=' + rsync_password_filepath, write_test_file, 'rsync://' + worker.cruise_data_transfer['rsyncUser'] + '@' + worker.cruise_data_transfer['rsyncServer'] + dest_dir]

#     logging.debug("Server Test Command: %s", ' '.join(write_test_command))

#     proc = subprocess.run(write_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to write to destination directory: {dest_dir} on the Rsync Server: {worker.cruise_data_transfer['rsyncServer']}"})

#     else:

#         os.remove(write_test_file)
#         write_cleanup_command = ['rsync', '-vir', '--no-motd', '--password-file=' + rsync_password_filepath, '--delete', '--include=writeTest.txt', '--exclude=*', tmpdir + '/', 'rsync://' + worker.cruise_data_transfer['rsyncUser'] + '@' + worker.cruise_data_transfer['rsyncServer'] + dest_dir]

#         logging.debug("Write test cleanup command: %s", ' '.join(write_cleanup_command))

#         proc = subprocess.run(write_cleanup_command, capture_output=True, text=True, check=False)

#         logging.debug(proc.stderr)

#         if proc.returncode != 0:
#             return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to write to destination directory: {dest_dir} on the Rsync Server: {worker.cruise_data_transfer['rsyncServer']}"})

#         else:
#             return_val.append({"partName": "Write Test", "result": "Pass"})

#     # Cleanup
#     shutil.rmtree(tmpdir)

#     return return_val


# def test_ssh_dest_dir(worker):
#     """
#     Verify the destination directory exists for a ssh server transfer
#     """

#     return_val = []

#     server_test_command = ['ssh', worker.cruise_data_transfer['sshServer'], '-l', worker.cruise_data_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

#     if worker.cruise_data_transfer['sshUseKey'] == '1':
#         server_test_command += ['-o', 'PasswordAuthentication=no']

#     else:
#         server_test_command = ['sshpass', '-p', worker.cruise_data_transfer['sshPass']] + server_test_command + ['-o', 'PubkeyAuthentication=no']

#     server_test_command += ['ls']

#     logging.debug("Connection test command: %s", ' '.join(server_test_command))

#     proc = subprocess.run(server_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.extend([
#             {"partName": "SSH Connection", "result": "Fail", "reason": f"Unable to connect to ssh server: {worker.cruise_data_transfer['sshServer']} as {worker.cruise_data_transfer['sshUser']}"},
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to connect to ssh server: {worker.cruise_data_transfer['sshServer']} as {worker.cruise_data_transfer['sshUser']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Unable to connect to ssh server: {worker.cruise_data_transfer['sshServer']} as {worker.cruise_data_transfer['sshUser']}"}
#         ])
#         return return_val

#     return_val.append({"partName": "SSH Connection", "result": "Pass"})

#     dest_dir = worker.cruise_data_transfer['destDir']

#     dest_test_command = ['ssh', worker.cruise_data_transfer['sshServer'], '-l', worker.cruise_data_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

#     if worker.cruise_data_transfer['sshUseKey'] == '1':
#         dest_test_command += ['-o', 'PasswordAuthentication=no']

#     else:
#         dest_test_command = ['sshpass', '-p', worker.cruise_data_transfer['sshPass']] + dest_test_command + ['-o', 'PubkeyAuthentication=no']

#     dest_test_command += ['ls', "\"" + dest_dir + "\""]

#     logging.debug("Destination test command: %s", dest_test_command)

#     proc = subprocess.run(dest_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.extend([
#             {"partName": "Destination Directory", "result": "Fail", "reason": f"Unable to find destination directory: {dest_dir} on the SSH Server: {worker.cruise_data_transfer['sshServer']}"},
#             {"partName": "Write Test", "result": "Fail", "reason": f"Unable to find destination directory: {dest_dir} on the SSH Server: {worker.cruise_data_transfer['sshServer']}"}
#         ])

#         return return_val

#     return_val.append({"partName": "Destination Directory", "result": "Pass"})

#     write_test_command = ['ssh', worker.cruise_data_transfer['sshServer'], '-l', worker.cruise_data_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

#     if worker.cruise_data_transfer['sshUseKey'] == '1':
#         write_test_command += ['-o', 'PasswordAuthentication=no']

#     else:
#         write_test_command = ['sshpass', '-p', worker.cruise_data_transfer['sshPass']] + write_test_command + ['-o', 'PubkeyAuthentication=no']

#     write_test_command += ['touch ' + os.path.join(dest_dir, 'writeTest.txt')]

#     logging.debug("Write test command: %s", write_test_command)

#     proc = subprocess.run(write_test_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to write to destination directory: {dest_dir} on the SSH Server: {worker.cruise_data_transfer['sshServer']}"})

#         return return_val

#     write_cleanup_command = ['ssh', worker.cruise_data_transfer['sshServer'], '-l', worker.cruise_data_transfer['sshUser'], '-o', 'StrictHostKeyChecking=no']

#     if worker.cruise_data_transfer['sshUseKey'] == '1':
#         write_cleanup_command += ['-o', 'PasswordAuthentication=no']

#     else:
#         write_cleanup_command = ['sshpass', '-p', worker.cruise_data_transfer['sshPass']] + write_cleanup_command + ['-o', 'PubkeyAuthentication=no']

#     write_cleanup_command += ['rm ' + os.path.join(dest_dir, 'writeTest.txt')]


#     logging.debug("Write test cleanup command: %s", ' '.join(write_cleanup_command))

#     proc = subprocess.run(write_cleanup_command, capture_output=True, check=False)

#     if proc.returncode != 0:
#         return_val.append({"partName": "Write Test", "result": "Fail", "reason": f"Unable to cleanup test file from destination directory: {dest_dir} on the SSH Server: {worker.cruise_data_transfer['sshServer']}"})

#         return return_val

#     return_val.append({"partName": "Write Test", "result": "Pass"})

#     return return_val


# def test_source_dir(worker):
#     """
#     Verify the cruise directory exists
#     """

#     cruise_dir = os.path.join(worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], worker.cruise_id)

#     return [{"partName": "Source Directory", "result": "Pass"}] if os.path.isdir(cruise_dir) else [{"partName": "Source Directory", "result": "Fail", "reason": f"Unable to find cruise directory: {cruise_dir} on the Data Warehouse"}]


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
            f"%(asctime)-15s %(levelname)s - {self.collection_system_transfer['name']}: %(message)s"
        ))

        logging.info("Job: %s, transfer test started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

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
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s, transfer test failed at: %s", current_job.handle,
                      time.strftime("%D %T", time.gmtime()))

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
        Function run whenever the current job completes
        """

        results = json.loads(job_result)
        job_parts = results.get('parts', [])
        final_verdict = job_parts[-1] if len(job_parts) else None
        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job: %s transfer completed at: %s", current_job.handle,
                     time.strftime("%D %T", time.gmtime()))

        if not cdt_id:
            return super().send_job_complete(current_job, job_result)

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', "undefined")
            self.ovdm.set_error_cruise_data_transfer_test(cdt_id, reason)
            return super().send_job_complete(current_job, job_result)

        # Always set idle at the end if not failed
        self.ovdm.clear_error_cruise_data_transfer(cdt_id)

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


    def _ignore_job(self, current_job, part_name, reason):
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
    worker.send_job_status(current_job, 1, 4)

    job_results['parts'] = worker.test_cruise_dir(current_job)

    logging.info("Test destination")
    worker.send_job_status(current_job, 2, 4)

    job_results['parts'].extend(test_cdt_destination(cdt_cfg))
    worker.send_job_status(current_job, 3, 4)

    for test in job_results['parts']:
        if test['result'] == "Fail":
            job_results['parts'].extend([{"partName": "Final Verdict", "result": "Fail", "reason": test['reason']}])
            return json.dumps(job_results)

    job_results['parts'].extend([{"partName": "Final Verdict", "result": "Pass"}])

    worker.send_job_status(current_job, 3, 4)

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

    logging.info("\tTask: %s", TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'], task_test_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
