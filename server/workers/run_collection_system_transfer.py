#!/usr/bin/env python3
"""
FILE:  run_collection_system_transfer.py

DESCRIPTION:  Gearman worker that handles the transfer of data from the Collection
    System to the Shipboard Data Warehouse.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.10
  CREATED:  2015-01-01
 REVISION:  2025-04-12
"""

import argparse
import calendar
import fnmatch
import json
import logging
import os
import re
import sys
import shutil
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta
from os.path import dirname, realpath
from random import randint
import pytz
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import is_ascii
from server.lib.output_json_data_to_file import output_json_data_to_file
from server.lib.set_owner_group_permissions import set_owner_group_permissions
from server.lib.connection_utils import detect_smb_version, mount_smb_share, check_darwin, build_rsync_command, build_rsync_options, delete_from_dest
from server.lib.openvdm import OpenVDM

TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

@contextmanager
def temporary_directory():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        try:
            shutil.rmtree(tmpdir)
        except Exception as e:
            logging.warning(f"Could not delete temp dir {tmpdir}: {e}")


def process_rsync_line(line, filters, data_start_time, data_end_time, epoch):
    """Process a single line from rsync output."""

    file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)

    if not file_or_dir.startswith('-'):
        return None

    file_mod_time = datetime.strptime(mdate + ' ' + mtime, "%Y/%m/%d %H:%M:%S")
    file_mod_time_seconds = (file_mod_time - epoch).total_seconds()

    if not (data_start_time <= file_mod_time_seconds <= data_end_time):
        return None

    if any(fnmatch.fnmatch(filepath, p) for p in filters['ignore_filters']):
        return None

    if not is_ascii(filepath):
        return ('exclude', filepath, None)

    if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
        if not any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
            return ('include', filepath, size)
        else:
            return ('exclude', filepath, None)

    return ('exclude', filepath, None)


def process_batch(batch, filters, data_start_time, data_end_time):
    results = []

    for filepath in batch:
        try:
            if os.path.islink(filepath):
                continue

            stat = os.stat(filepath)
            mod_time = stat.st_mtime
            size = stat.st_size

            if not (data_start_time <= mod_time <= data_end_time):
                continue

            if any(fnmatch.fnmatch(filepath, p) for p in filters['ignore_filters']):
                continue

            if not is_ascii(filepath):
                results.append(("exclude", filepath, "0"))
                continue

            if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
                if not any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
                    results.append(("include", filepath, str(size)))
                else:
                    results.append(("exclude", filepath, "0"))
            else:
                results.append(("exclude", filepath, "0"))

        except FileNotFoundError:
            continue

    return results


def process_rsync_batch(batch, filters, data_start_time, data_end_time, epoch):
    """Process a batch of rsync output lines."""
    results = []
    for filepath in batch:
        result = process_rsync_line(filepath, filters, data_start_time, data_end_time, epoch)
        if result:
            results.append(result)
    return results


def verify_staleness_batch(paths_sizes):
    verified = []
    for filepath, old_size in paths_sizes:
        try:
            if os.stat(filepath).st_size == int(old_size):
                verified.append((filepath, old_size))
        except FileNotFoundError:
            continue
    return verified


def build_filelist(gearman_worker, transfer_type='local', prefix=None, rsync_password_filepath=None, is_darwin=False, batch_size=500, max_workers=16):
    source_dir = os.path.join(prefix, gearman_worker.source_dir.lstrip('/')) if prefix else gearman_worker.source_dir
    return_files = {'include': [], 'exclude': [], 'new': [], 'updated': [], 'filesize': []}
    filters = build_filters(gearman_worker)
    epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))

    # Get file list based on transfer_type
    if transfer_type in ['local', 'smb']:
        filepaths = []
        for root, _, filenames in os.walk(source_dir):
            for filename in filenames:
                filepaths.append(os.path.join(root, filename))
    else:
        command = ['rsync', '-r']
        if transfer_type == 'rsync':
            command += ['--password-file=' + rsync_password_filepath, '--no-motd',
                        f"rsync://{gearman_worker.collection_system_transfer['rsyncUser']}@"
                        f"{gearman_worker.collection_system_transfer['rsyncServer']}"
                        f"{gearman_worker.source_dir}/"]
        elif transfer_type == 'ssh':
            command += ['-e', 'ssh',
                        f"{gearman_worker.collection_system_transfer['sshUser']}@"
                        f"{gearman_worker.collection_system_transfer['sshServer']}:{gearman_worker.source_dir}/"]
            if not is_darwin:
                command.insert(2, '--protect-args')
            if gearman_worker.collection_system_transfer.get('sshUseKey') == '0':
                command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

        if gearman_worker.collection_system_transfer.get('skipEmptyFiles') == '1':
            command.insert(2, '--min-size=1')
        if gearman_worker.collection_system_transfer.get('skipEmptyDirs') == '1':
            command.insert(2, '-m')

        logging.info("File list Command: %s", ' '.join(command))
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        filepaths = proc.stdout.splitlines()
        filepaths = [filepath for filepath in filepaths if filepath.startswith('-')]

    total_files = len(filepaths)
    logging.info("Discovered %d files", total_files)

    # Batch and process
    batches = [filepaths[i:i + batch_size] for i in range(0, total_files, batch_size)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        if transfer_type in ['local', 'smb']:
            futures = [executor.submit(process_batch, batch, filters, data_start_time, data_end_time)
                       for batch in batches]
        else:
            futures = [executor.submit(process_rsync_batch, batch, filters, data_start_time, data_end_time, epoch)
                       for batch in batches]

        for future in as_completed(futures):
            result = future.result()
            if result:
                for item in result:
                    if item[0] == 'include':
                        return_files['include'].append(item[1])
                        return_files['filesize'].append(item[2])
                    elif item[0] == 'exclude':
                        return_files['exclude'].append(item[1])

    # Optional staleness check
    staleness = gearman_worker.collection_system_transfer.get('staleness')
    if staleness and staleness != '0':
        logging.info("Checking staleness (wait %ss)...", staleness)
        time.sleep(int(staleness))

        if transfer_type in ['local', 'smb']:
            paths_sizes = list(zip(return_files['include'], return_files['filesize']))
            stale_batches = [paths_sizes[i:i + batch_size] for i in range(0, len(paths_sizes), batch_size)]
            verified_paths = []
            verified_sizes = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(verify_staleness_batch, batch) for batch in stale_batches]
                for future in as_completed(futures):
                    for filepath, size in future.result():
                        verified_paths.append(filepath)
                        verified_sizes.append(size)
            return_files['include'] = verified_paths
            return_files['filesize'] = verified_sizes
        else:
            proc = subprocess.run(command, capture_output=True, text=True, check=False)
            for line in proc.stdout.splitlines():
                try:
                    file_or_dir, size, *_ , filepath = line.split(None, 4)
                    if not file_or_dir.startswith('-'):
                        continue
                    idx = return_files['include'].index(filepath)
                    if return_files['filesize'][idx] != size:
                        del return_files['filesize'][idx]
                        del return_files['include'][idx]
                except Exception as err:
                    logging.warning("Staleness check error: %s", err)

    # Format final output
    del return_files['filesize']
    if transfer_type in ['local', 'smb']:
        base_len = len(source_dir.rstrip(os.sep)) + 1
        return_files['include'] = [f[base_len:] for f in return_files['include']]
        return_files['exclude'] = [f[base_len:] for f in return_files['exclude']]

    return {'verdict': True, 'files': return_files}


def build_filters(gearman_worker):
    """
    Replace wildcard string in filters
    """

    def expand_placeholders(template: str, context: dict) -> str:
        for key, value in context.items():
            template = template.replace(key, value)
        return template

    context = {
        '{cruiseID}': gearman_worker.cruise_id,
        '{loweringID}': gearman_worker.lowering_id,
        '{YYYY}': '20[0-9][0-9]',
        '{YY}': '[0-9][0-9]',
        '{mm}': '[0-1][0-9]',
        '{DD}': '[0-3][0-9]',
        '{HH}': '[0-2][0-9]',
        '{MM}': '[0-5][0-9]',
        '{SS}': '[0-5][0-9]',
    }

    filters = {}
    for key in ['includeFilter', 'excludeFilter', 'ignoreFilter']:
        raw = gearman_worker.collection_system_transfer.get(key, '')
        expanded = expand_placeholders(raw, context)
        filters[key.replace('Filter', '_filters')] = expanded.split(',') if expanded else []

    return filters


def build_include_file(include_list, filepath):
    try:
        with open(filepath, mode='w', encoding="utf-8") as f:
            f.write('\n'.join(include_list))
            f.write('\0')
    except IOError as e:
        logging.error("Error writing include file: %s", e)
        return False

    return True


def run_transfer_command(gearman_worker, gearman_job, command, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.info("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.info('Transfer Command: %s', ' '.join(command))

    new_files = []
    updated_files = []
    last_percent_reported = -1

    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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
                        gearman_worker.send_job_status(gearman_job, int(20 + 70 * percent / 100), 100)
                        last_percent_reported = percent

    return new_files, updated_files


def transfer_from_source(gearman_worker, gearman_job, transfer_type):
    """
    Perform a collection system transfer from the configured source type.
    """

    cfg = gearman_worker.collection_system_transfer
    source_dir = gearman_worker.source_dir
    dest_dir = gearman_worker.dest_dir

    prefix = None
    mntpoint = None
    is_darwin = False

    with temporary_directory() as tmpdir:
        include_file = os.path.join(tmpdir, 'rsyncFileList.txt')
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Adjustments for SMB
        if transfer_type == 'smb':
            # Mount SMB Share
            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cfg)
            success = mount_smb_share(cfg, mntpoint, smb_version)
            if not success:
                return {'verdict': False, 'reason': 'Failed to mount SMB share'}
            prefix = mntpoint

        # Adjustments for RSYNC
        if transfer_type == 'rsync':
            # Build password file
            try:
                with open(password_file, 'w', encoding='utf-8') as f:
                    f.write(gearman_worker.collection_system_transfer['rsyncPass'])
                os.chmod(password_file, 0o600)
            except IOError:
                return {'verdict': False, 'reason': 'Error writing rsync password file', 'files': []}
        else:
            password_file = None

        if transfer_type == 'ssh':
            is_darwin = check_darwin(cfg)

        # Build filelist (from local, SMB mount, etc.)
        filelist_result = build_filelist(gearman_worker, transfer_type=transfer_type, prefix=prefix, rsync_password_filepath=password_file, is_darwin=is_darwin)

        if not filelist_result['verdict']:
            if mntpoint:
                subprocess.call(['umount', mntpoint])
            return {'verdict': False, 'reason': filelist_result.get('reason', 'Unknown'), 'files': []}

        files = filelist_result['files']

        # Write file list
        if not build_include_file(files['include'], include_file):
            if mntpoint:
                subprocess.call(['umount', mntpoint])
            return {'verdict': False, 'reason': 'Error writing file list', 'files': []}

        # Build rsync command
        if transfer_type == 'local':
            source_path = source_dir if source_dir == '/' else source_dir.rstrip('/')
        elif transfer_type == 'rsync':
            source_path = f"rsync://{gearman_worker.collection_system_transfer['rsyncUser']}@" \
                          f"{gearman_worker.collection_system_transfer['rsyncServer']}" \
                          f"{source_dir}"
        elif transfer_type == 'ssh':
            user = gearman_worker.collection_system_transfer['sshUser']
            host = gearman_worker.collection_system_transfer['sshServer']
            source_path = f"{user}@{host}:{source_dir}"
        elif transfer_type == 'smb':
            source_path = os.path.join(mntpoint, source_dir.lstrip('/').rstrip('/'))

        source_path = source_path + '/'

        extra_args = []
        if transfer_type == 'ssh':
            extra_args = ['-e', 'ssh']
        elif transfer_type == 'rsync':
            extra_args = [f"--password-file={password_file}"]

        # Base command
        rsync_flags = build_rsync_options(cfg, mode='real', is_darwin=is_darwin, transfer_type=transfer_type)

        rsync_cmd = build_rsync_command(rsync_flags, extra_args, source_path, dest_dir, include_file)
        if transfer_type == 'ssh' and cfg.get('sshUseKey') == '0':
            rsync_cmd = ['sshpass', '-p', cfg['sshPass']] + rsync_cmd

        # Transfer files
        files['new'], files['updated'] = run_transfer_command(
            gearman_worker, gearman_job, rsync_cmd, len(files['include'])
        )

        # Delete files if sync'ing with source
        if cfg['syncFromSource'] == '1':
            files['deleted'] = delete_from_dest(dest_dir, files['include'])

        # Cleanup
        if mntpoint:
            time.sleep(2)
            subprocess.call(['umount', mntpoint])

    return {'verdict': True, 'files': files}



class OVDMGearmanWorker(python3_gearman.GearmanWorker):  # pylint: disable=too-many-instance-attributes
    """
    Gearman worker for OpenVDM-based collection system transfers.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.system_status = None
        self.collection_system_transfer = None
        self.shipboard_data_warehouse_config = None

        self.cruise_dir = None
        self.source_dir = None
        self.dest_dir = None
        self.lowering_id = None
        self.data_start_date = None
        self.data_end_date = None
        self.transfer_start_date = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])

    def keyword_replace(self, s):
        return (
            s.replace('{cruiseID}', self.cruise_id)
             .replace('{loweringID}', self.lowering_id)
             .replace('{loweringDataBaseDir}', self.shipboard_data_warehouse_config['loweringDataBaseDir'])
             .rstrip('/')
        )

    def build_dest_dir(self):
        """
        Replace wildcard string in destDir
        """

        return self.keyword_replace(self.collection_system_transfer['destDir']) if self.collection_system_transfer else ""


    def build_source_dir(self):
        """
        Replace wildcard string in sourceDir
        """

        return self.keyword_replace(self.collection_system_transfer['sourceDir']) if self.collection_system_transfer else ""


    def build_logfile_dirpath(self):
        """
        build the path to save transfer logfiles
        """

        return os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])


    def on_job_execute(self, current_job):
        logging.debug("Received job: %s", current_job)
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)

            cst_id = payload_obj['collectionSystemTransfer']['collectionSystemTransferID']
            self.collection_system_transfer = self.ovdm.get_collection_system_transfer(cst_id)

            if self.collection_system_transfer is None:
                self.collection_system_transfer = {
                    'name': "Unknown Transfer"
                }

                return self._fail_job(current_job, "Located Collection System Transfer Data",
                                      "Could not find configuration data for collection system transfer")

            if self.collection_system_transfer['status'] == "1":
                logging.info("Transfer already in-progress for %s", self.collection_system_transfer['name'])
                return self._ignore_job(current_job, "Transfer In-Progress", "Transfer is already in-progress")

        except Exception:
            logging.exception("Failed to retrieve collection system transfer config")
            return self._fail_job(current_job, "Located Collection System Transfer Data",
                                  "Could not retrieve data for collection system transfer from OpenVDM API")

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.collection_system_transfer['name']}: %(message)s"
        ))

        logging.info("Job: %s, transfer started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.system_status = payload_obj['systemStatus'] if 'systemStatus' in payload_obj else self.ovdm.get_system_status()
        self.collection_system_transfer.update(payload_obj['collectionSystemTransfer'])

        if self.system_status == "Off" or self.collection_system_transfer['enable'] == '0':
            logging.info("Transfer disabled for %s", self.collection_system_transfer['name'])
            return self._ignore_job(current_job, "Transfer Enabled", "Transfer is disabled")

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id()) or ""
        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        if len(self.lowering_id) == 0:
            # exit with error if trying to run a lowering collection system transfer
            if self.collection_system_transfer['cruiseOrLowering'] == "1" or '{loweringID}' in self.collection_system_transfer['destDir']:
                return self._fail_job(current_job, "Validate Lowering ID",
                                      "Lowering ID is not defined")

        if self.collection_system_transfer['cruiseOrLowering'] == "1":
            self.dest_dir = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id, self.build_dest_dir())
        else:
            self.dest_dir = os.path.join(self.cruise_dir, self.build_dest_dir())

        self.source_dir = self.build_source_dir()

        self.transfer_start_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

        ### Set temporal bounds for transfer
        # if temporal bands are not used then set to absolute min/max
        if self.collection_system_transfer['useStartDate'] == '0':
            self.data_start_date = "1970/01/01 00:00"
            self.data_end_date = "9999/12/31 23:59:59"

        # if temporal bands are used then set to specified bounds for the corresponding cruise/lowering
        else:
            if self.collection_system_transfer['cruiseOrLowering'] == "0":
                logging.debug("Using cruise Time bounds")
                self.data_start_date = self.ovdm.get_cruise_start_date() or "1970/01/01 00:00"
                cruise_end = self.ovdm.get_cruise_end_date()
                self.data_end_date = cruise_end + ":59" if cruise_end else "9999/12/31 23:59:59"
            else:
                logging.debug("Using lowering Time bounds")
                self.data_start_date = self.ovdm.get_lowering_start_date() or "1970/01/01 00:00"
                lowering_end = self.ovdm.get_lowering_end_date()
                self.data_end_date = lowering_end + ":59" if lowering_end else "9999/12/31 23:59:59"

            if self.collection_system_transfer['staleness'] != "0":
                staleness_dt = (datetime.utcnow() - timedelta(seconds=int(self.collection_system_transfer['staleness']))).replace(tzinfo=pytz.UTC)
                data_end_dt = datetime.strptime(self.data_end_date + "+0000", "%Y/%m/%d %H:%M:%S" + '%z')
                if staleness_dt < data_end_dt:
                    self.data_end_date = staleness_dt.strftime("%Y/%m/%d %H:%M:%S")

        # Todo - there's a chance the dates are not set and stay set to None... which errors here.
        logging.debug("Start date/time filter: %s", self.data_start_date)
        logging.debug("End date/time filter: %s", self.data_end_date)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s, %s transfer failed at: %s", current_job.handle,
                      self.collection_system_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{
            "partName": "Worker crashed", "result": "Fail", "reason": "Unknown"
        }]))
        self.ovdm.set_error_collection_system_transfer(
            self.collection_system_transfer['collectionSystemTransferID'], 'Worker crashed'
        )

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run whenever the current job completes
        """

        results_obj = json.loads(job_result)

        final_part = results_obj['parts'][-1] if results_obj['parts'] else None

        if final_part:
            if final_part['result'] == "Fail" and final_part['partName'] != "Located Collection System Transfer Data":
                self.ovdm.set_error_collection_system_transfer(
                    self.collection_system_transfer['collectionSystemTransferID'], final_part['reason']
                )
            elif final_part['result'] == "Pass":

                if results_obj['files']['new'] or results_obj['files']['updated'] or ('deleted' in results_obj['files'] and results_obj['files']['deleted']):

                    logging.info("Preparing subsequent Gearman jobs")
                    gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

                    job_data = {
                        'cruiseID': self.cruise_id,
                        'collectionSystemTransferID': self.collection_system_transfer['collectionSystemTransferID'] if self.collection_system_transfer else '-1',
                        'files': {
                            'new': [ os.path.join(self.collection_system_transfer['destDir'], filepath).lstrip('/') for filepath in results_obj['files']['new']],
                            'updated': [ os.path.join(self.collection_system_transfer['destDir'], filepath).lstrip('/') for filepath in results_obj['files']['updated']]
                        }
                    }

                    if 'deleted' in results_obj['files']:
                        job_data['files']['deleted'] = [
                            os.path.normpath(os.path.join(self.collection_system_transfer['destDir'], filepath))
                            for filepath in results_obj['files']['deleted']
                        ]

                    for task in self.ovdm.get_tasks_for_hook('runCollectionSystemTransfer'):
                        logging.info("Adding post task: %s", task)
                        gm_client.submit_job(task, json.dumps(job_data), background=True)

                self.ovdm.set_idle_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'])
        else:
            self.ovdm.set_idle_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s transfer completed at: %s", current_job.handle,
                     time.strftime("%D %T", time.gmtime()))

        return super().send_job_complete(current_job, job_result)

    def stop_task(self):
        self.stop = True
        logging.warning("Stopping current task...")


    def quit_worker(self):
        self.stop = True
        logging.warning("Quitting worker...")
        self.shutdown()

    # --- Helper Methods ---
    def _fail_job(self, current_job, part_name, reason):
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))

    def _ignore_job(self, current_job, part_name, reason):
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_run_collection_system_transfer(gearman_worker, current_job): # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements
    """
    Run the collection system transfer
    """

    time.sleep(randint(0,2))

    job_results = {
        'parts': [
            {"partName": "Transfer In-Progress", "result": "Pass"},
            {"partName": "Transfer Enabled", "result": "Pass"}
        ],
        'files': {
            'new': [],
            'updated':[],
            'exclude':[]
        }
    }

    logging.debug("Setting transfer status to 'Running'")
    gearman_worker.ovdm.set_running_collection_system_transfer(gearman_worker.collection_system_transfer['collectionSystemTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing connection")
    gearman_worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([gearman_worker.ovdm.get_gearman_server()])

    gm_data = {
        'collectionSystemTransfer': gearman_worker.collection_system_transfer,
        'cruiseID': gearman_worker.cruise_id
    }

    completed_job_request = gm_client.submit_job("testCollectionSystemTransfer", json.dumps(gm_data))
    results_obj = json.loads(completed_job_request.result)

    logging.debug('Connection Test Results: %s', json.dumps(results_obj, indent=2))

    if results_obj['parts'][-1]['result'] == "Pass": # Final Verdict
        logging.debug("Connection test passed")
        job_results['parts'].append({"partName": "Connection Test", "result": "Pass"})
    else:
        logging.warning("Connection test failed, quitting job")
        job_results['parts'].append({"partName": "Connection Test", "result": "Fail", "reason": results_obj['parts'][-1]['reason']})
        return json.dumps(job_results)

    gearman_worker.send_job_status(current_job, 2, 10)

    # if gearman_worker.collection_system_transfer['cruiseOrLowering'] == "1" and gearman_worker.lowering_id is None:
    #     logging.info("Verifying lowering_id is set")
    #     job_results['parts'].append({'partName': 'Destination Directory Test', "result": "Fail", 'reason': 'Lowering ID is not defined'})
    #     return json.dumps(job_results)

    logging.info("Transferring files")
    output_results = None
    if gearman_worker.collection_system_transfer['transferType'] == "1": # Local Directory
        output_results = transfer_from_source(gearman_worker, current_job, 'local')
    elif  gearman_worker.collection_system_transfer['transferType'] == "2": # Rsync Server
        output_results = transfer_from_source(gearman_worker, current_job, 'rsync')
    elif  gearman_worker.collection_system_transfer['transferType'] == "3": # SMB Server
        output_results = transfer_from_source(gearman_worker, current_job, 'smb')
    elif  gearman_worker.collection_system_transfer['transferType'] == "4": # SSH Server
        output_results = transfer_from_source(gearman_worker, current_job, 'ssh')
    else:
        logging.error("Unknown Transfer Type")
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": "Unknown transfer type"})
        return json.dumps(job_results)

    if not output_results['verdict']:
        logging.error("Transfer of remote files failed: %s", output_results['reason'])
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    logging.info("Transfer completed successfully")
    job_results['files'] = output_results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s misnamed file(s) encountered", len(job_results['files']['exclude']))
    if 'deleted' in job_results['files'] and len(job_results['files']['deleted']) > 0:
        logging.debug("%s file(s) deleted", len(job_results['files']['deleted']))

    gearman_worker.send_job_status(current_job, 9, 10)

    if job_results['files']['new'] or job_results['files']['updated']:

        logging.info("Setting file permissions")
        output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], gearman_worker.dest_dir)

        if not output_results['verdict']:
            logging.error("Error setting destination directory file/directory ownership/permissions: %s", gearman_worker.dest_dir)
            job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})

        job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Pass"})

        logfile_filename = gearman_worker.collection_system_transfer['name'] + '_' + gearman_worker.transfer_start_date + '.log'
        logfile_contents = {
            'files': {
                'new': job_results['files']['new'],
                'updated': job_results['files']['updated']
            }
        }

        output_results = output_json_data_to_file(os.path.join(gearman_worker.build_logfile_dirpath(), logfile_filename), logfile_contents['files'])

        if output_results['verdict']:
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Pass"})
        else:
            logging.error("Error writing transfer logfile: %s", logfile_filename)
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(gearman_worker.build_logfile_dirpath(), logfile_filename))

        if not output_results['verdict']:
            job_results['parts'].append({"partName": "Set OpenVDM config file ownership/permissions", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

    logfile_filename = gearman_worker.collection_system_transfer['name'] + '_Exclude.log'
    logfile_contents = {
        'files': {
            'exclude': job_results['files']['exclude']
        }
    }
    logfile_contents['files']['exclude'] = job_results['files']['exclude']

    output_results = output_json_data_to_file(os.path.join(gearman_worker.build_logfile_dirpath(), logfile_filename), logfile_contents['files'])

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Write exclude logfile", "result": "Pass"})
    else:
        logging.error("Error writing transfer logfile: %s", output_results['reason'])
        job_results['parts'].append({"partName": "Write exclude logfile", "result": "Fail", "reason": output_results['reason']})
        return job_results

    output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(gearman_worker.build_logfile_dirpath(), logfile_filename))

    if not output_results['verdict']:
        logging.error("Error setting ownership/permissions for transfer logfile: %s", logfile_filename)
        job_results['parts'].append({"partName": "Set transfer logfile ownership/permissions", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    gearman_worker.send_job_status(current_job, 10, 10)

    time.sleep(2)

    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle collection system transfer related tasks')
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

        LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("QUIT Signal Received")
        new_worker.stop_task()

    def sigint_handler(_signo, _stack_frame):
        """
        Signal Handler for INT
        """

        LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("INT Signal Received")
        new_worker.quit_worker()

    signal.signal(signal.SIGQUIT, sigquit_handler)
    signal.signal(signal.SIGINT, sigint_handler)

    logging.info("Registering worker tasks...")

    logging.info("\tTask: runCollectionSystemTransfer")
    new_worker.register_task("runCollectionSystemTransfer", task_run_collection_system_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
