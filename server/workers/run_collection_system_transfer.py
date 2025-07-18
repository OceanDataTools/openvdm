#!/usr/bin/env python3
"""
FILE:  run_collection_system_transfer.py

DESCRIPTION:  Gearman worker that handles the transfer of data from the Collection
    System to the Shipboard Data Warehouse.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2015-01-01
 REVISION:  2025-07-06
"""

import argparse
import calendar
import fnmatch
import json
import logging
import os
import re
import sys
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from os.path import dirname, realpath
from random import randint
import pytz
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import build_include_file, is_ascii, is_rsync_patial_file, delete_from_dest, output_json_data_to_file, set_owner_group_permissions, temporary_directory
from server.lib.connection_utils import build_rsync_command, build_rsync_options, check_darwin, detect_smb_version, get_transfer_type, mount_smb_share, test_cst_source
from server.lib.openvdm import OpenVDM

TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

TASK_NAMES = {
    'RUN_COLLECTION_SYSTEM_TRANSFER': 'runCollectionSystemTransfer'
}

def process_batch(batch, filters, data_start_time, data_end_time):
    """
    Process a batch of file paths
    """

    def _process_filepath(filepath, filters, data_start_time, data_end_time):
        """
        Process a file path to determine if it should be included or excluded from
        the data transfer
        """

        try:
            if os.path.islink(filepath):
                return None

            stat = os.stat(filepath)
            mod_time = stat.st_mtime
            size = stat.st_size

            if not (data_start_time <= mod_time <= data_end_time):
                return None

            if not is_ascii(filepath):
                return ("exclude", filepath, None)

            if is_rsync_patial_file(filepath):
                return None

            if any(fnmatch.fnmatch(filepath, p) for p in filters['ignore_filters']):
                return None

            if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
                if any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
                    return ("exclude", filepath, None)

                return ("include", filepath, str(size))

            return ("exclude", filepath, None)

        except FileNotFoundError:
            return None


    results = []

    for filepath in batch:
        result = _process_filepath(filepath, filters, data_start_time, data_end_time)
        if result:
            results.append(result)
    return results


def process_rsync_batch(batch, filters, data_start_time, data_end_time, epoch):
    """
    Process a batch of rsync output lines.
    """

    def _process_rsync_line(line, filters, data_start_time, data_end_time, epoch):
        """
        Process a single line of rsync output.
        """

        parts = line.strip().split(None, 4)
        if len(parts) < 5:
            logging.warning("Skipping malformed rsync line: %s", line)
            return None

        file_or_dir, size, mdate, mtime, filepath = parts

        if not file_or_dir.startswith('-'):
            return None

        try:
            file_mod_time = datetime.strptime(f"{mdate} {mtime}", "%Y/%m/%d %H:%M:%S")
        except ValueError as exc:
            logging.warning("Could not parse date/time from line: %s (%s)", line, str(exc))
            return None

        file_mod_time_seconds = (file_mod_time - epoch).total_seconds()
        if not (data_start_time <= file_mod_time_seconds <= data_end_time):
            return None

        if not is_ascii(filepath):
            return ('exclude', filepath, None)

        if is_rsync_patial_file(filepath):
            return None

        if any(fnmatch.fnmatch(filepath, p) for p in filters['ignore_filters']):
            return None

        if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
            if any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
                return ('exclude', filepath, None)

            return ('include', filepath, size)

        return ('exclude', filepath, None)


    results = []
    for filepath in batch:
        result = _process_rsync_line(filepath, filters, data_start_time, data_end_time, epoch)
        if result:
            results.append(result)
    return results


def run_transfer_command(worker, current_job, cmd, file_count):
    """
    Run the rsync command and return the list of new and updated files
    """

    if file_count == 0:
        logging.info("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.debug('Transfer Command: %s', ' '.join(cmd))

    new_files = []
    updated_files = []
    last_percent_reported = -1

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while proc.poll() is None:

        for line in proc.stdout:

            if worker.stop:
                logging.info("Stopping")
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
                        if current_job:
                            worker.send_job_status(current_job, int(50 * percent / 100) + 20, 100) # 70 - 20
                        last_percent_reported = percent

    return new_files, updated_files


class OVDMGearmanWorker(python3_gearman.GearmanWorker):  # pylint: disable=too-many-instance-attributes
    """
    Gearman worker for OpenVDM-based collection system transfers.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.lowering_id = None
        self.collection_system_transfer = None
        self.shipboard_data_warehouse_config = None

        self.cruise_dir = None
        self.source_dir = None
        self.dest_dir = None

        self.data_start_date = None
        self.data_end_date = None
        self.transfer_start_date = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def keyword_replace(self, s):
        """
        Simple keyword replace function
        """

        if not isinstance(s, str):
            return None

        return (s.replace('{cruiseID}', self.cruise_id)
                .replace('{loweringDataBaseDir}', self.shipboard_data_warehouse_config['loweringDataBaseDir'])
                .replace('{loweringID}', self.lowering_id if self.lowering_id is not None else '{loweringID}')
                .rstrip('/')
               ) if s != '/' else s


    def build_rel_dir(self):
        """
        Replace wildcard string in destDir
        """

        if not self.collection_system_transfer:
            return None

        dest_dir = self.keyword_replace(self.collection_system_transfer['destDir']).lstrip('/')

        if self.collection_system_transfer.get('cruiseOrLowering') == '1':
            if self.lowering_id is None:
                return None

            return os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id, dest_dir)

        return dest_dir


    def build_source_dir(self):
        """
        Replace wildcard string in sourceDir
        """

        return self.keyword_replace(self.collection_system_transfer['sourceDir']) if self.collection_system_transfer else None


    def build_dest_dir(self):
        """
        Replace wildcard string in destDir AND add full cruise path
        """

        return os.path.join(self.cruise_dir, self.build_rel_dir())


    def build_logfile_dirpath(self):
        """
        Build the path to save transfer logfiles
        """

        return os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])


    def build_cst_filelist(self, prefix=None, rsync_password_filepath=None, is_darwin=False, batch_size=500, max_workers=16):
        """
        Build the list of files to include, exclude, ignore for the given transfer.
        """

        def _build_filters(cst_cfg, cruise_id, lowering_id):
            """
            Build a dict of filters with their wildcards replaced with the appropriate
            values
            """

            def _expand_placeholders(template: str, context: dict) -> str:
                for key, value in context.items():
                    template = template.replace(key, value)
                return template

            context = {
                '{cruiseID}': cruise_id,
                '{loweringID}': lowering_id or '{loweringID}',
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
                raw = cst_cfg.get(key, '')
                expanded = _expand_placeholders(raw, context)
                filters[key.replace('Filter', '_filters')] = expanded.split(',') if expanded else []

            return filters


        def _verify_staleness_batch(paths_sizes):
            """
            Verify a file hasn't changed size
            """

            verified = []
            for filepath, old_size in paths_sizes:
                try:
                    if os.stat(filepath).st_size == int(old_size):
                        verified.append((filepath, old_size))
                except FileNotFoundError:
                    continue
            return verified


        source_dir = os.path.join(prefix, self.source_dir.lstrip('/')) if prefix else self.source_dir
        cst_cfg = self.collection_system_transfer
        transfer_type = get_transfer_type(cst_cfg['transferType'])
        filters = _build_filters(cst_cfg, self.cruise_id, self.lowering_id)

        epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
        data_start_time = calendar.timegm(time.strptime(self.data_start_date, "%Y/%m/%d %H:%M"))
        data_end_time = calendar.timegm(time.strptime(self.data_end_date, "%Y/%m/%d %H:%M:%S"))

        return_files = {'include': [], 'exclude': [], 'new': [], 'updated': [], 'filesize': []}

        # Get file list based on transfer_type
        if transfer_type in ['local', 'smb']:
            filepaths = []
            for root, _, filenames in os.walk(source_dir):
                for filename in filenames:
                    filepaths.append(os.path.join(root, filename))
        else:
            command = ['rsync', '-r']
            if transfer_type == 'rsync':
                command += [f'--password-file={rsync_password_filepath}', '--no-motd',
                            f"rsync://{cst_cfg['rsyncUser']}@"
                            f"{cst_cfg['rsyncServer']}"
                            f"{self.source_dir}/"]
            elif transfer_type == 'ssh':
                command += ['-e', 'ssh',
                            f"{cst_cfg['sshUser']}@"
                            f"{cst_cfg['sshServer']}:{self.source_dir}/"]
                if not is_darwin:
                    command.insert(2, '--protect-args')
                if cst_cfg.get('sshUseKey') == '0':
                    command = ['sshpass', '-p', cst_cfg['sshPass']] + command

            if cst_cfg.get('skipEmptyFiles') == '1':
                command.insert(2, '--min-size=1')
            if cst_cfg.get('skipEmptyDirs') == '1':
                command.insert(2, '-m')

            logging.debug("File list Command: %s", ' '.join(command))
            proc = subprocess.run(command, capture_output=True, text=True, check=False)
            filepaths = proc.stdout.splitlines()
            filepaths = [filepath for filepath in filepaths if filepath.startswith('-')]

        total_files = len(filepaths)
        logging.debug("Discovered %d files", total_files)

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
        staleness = cst_cfg.get('staleness')
        if staleness and staleness != '0':
            logging.debug("Checking staleness (wait %ss)...", staleness)
            time.sleep(int(staleness))

            if transfer_type in ['local', 'smb']:
                paths_sizes = list(zip(return_files['include'], return_files['filesize']))
                stale_batches = [paths_sizes[i:i + batch_size] for i in range(0, len(paths_sizes), batch_size)]
                verified_paths = []
                verified_sizes = []
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(_verify_staleness_batch, batch) for batch in stale_batches]
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
                    except Exception as exc:
                        logging.warning("Staleness check error: %s", str(exc))

        # Format final output
        del return_files['filesize']
        if transfer_type in ['local', 'smb']:
            base_len = len(source_dir.rstrip(os.sep)) + 1
            return_files['include'] = [f[base_len:] for f in return_files['include']]
            return_files['exclude'] = [f[base_len:] for f in return_files['exclude']]

        return {'verdict': True, 'files': return_files}


    def test_destination_dir(self):
        """
        Verify the destination directory exists
        """

        results = []

        dest_dir_exists = os.path.isdir(self.dest_dir)
        if not dest_dir_exists:
            reason = f"Unable to find destination directory: {self.dest_dir}"
            results.extend([{"partName": "Verify destination directory", "result": "Fail", "reason": reason}])

            return results

        results.extend([{"partName": "Verify destination directory", "result": "Pass"}])

        return results


    def transfer_from_source(self, current_job):
        """
        Perform the collection system transfer.
        """

        cst_cfg = self.collection_system_transfer
        transfer_type = get_transfer_type(cst_cfg['transferType'])

        if not transfer_type:
            reason = 'Unknown transfer type'
            logging.error(reason)
            return {'verdict': False, 'reason': reason}

        source_dir = self.source_dir
        dest_dir = self.dest_dir

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
                smb_version = detect_smb_version(cst_cfg)
                success = mount_smb_share(cst_cfg, mntpoint, smb_version)
                if not success:
                    return {'verdict': False, 'reason': 'Failed to mount SMB share'}
                prefix = mntpoint

            # Adjustments for RSYNC
            if transfer_type == 'rsync':
                # Build password file
                try:
                    with open(password_file, 'w', encoding='utf-8') as f:
                        f.write(cst_cfg['rsyncPass'])
                    os.chmod(password_file, 0o600)
                except IOError:
                    return {'verdict': False, 'reason': 'Error writing rsync password file', 'files': []}
            else:
                password_file = None

            # Adjustments for SSH
            if transfer_type == 'ssh':
                is_darwin = check_darwin(cst_cfg)

            # Build filelist (from local, SMB mount, etc.)
            filelist_result = self.build_cst_filelist(prefix=prefix, rsync_password_filepath=password_file, is_darwin=is_darwin)

            if not filelist_result['verdict']:
                return {'verdict': False, 'reason': filelist_result.get('reason', 'Unknown'), 'files': []}

            files = filelist_result['files']

            # Write file list
            if not build_include_file(files['include'], include_file):
                return {'verdict': False, 'reason': 'Error writing file list', 'files': []}

            # Build rsync command
            if transfer_type == 'local':
                source_path = source_dir if source_dir == '/' else source_dir.rstrip('/')
            elif transfer_type == 'rsync':
                source_path = f"rsync://{cst_cfg['rsyncUser']}@" \
                              f"{cst_cfg['rsyncServer']}" \
                              f"{source_dir}"
            elif transfer_type == 'ssh':
                user = cst_cfg['sshUser']
                host = cst_cfg['sshServer']
                source_path = f"{user}@{host}:{source_dir}"
            elif transfer_type == 'smb':
                source_path = os.path.join(mntpoint, source_dir.lstrip('/').rstrip('/'))

            source_path += '/'

            extra_args = []
            if transfer_type == 'ssh':
                extra_args = ['-e', 'ssh']
            elif transfer_type == 'rsync':
                extra_args = [f"--password-file={password_file}"]

            # Build command
            rsync_flags = build_rsync_options(cst_cfg, mode='real', is_darwin=is_darwin)
            cmd = build_rsync_command(rsync_flags, extra_args, source_path, dest_dir, include_file)
            if transfer_type == 'ssh' and cst_cfg.get('sshUseKey') == '0':
                cmd = ['sshpass', '-p', cst_cfg['sshPass']] + cmd

            # Transfer files
            files['new'], files['updated'] = run_transfer_command(
                self, current_job, cmd, len(files['include'])
            )

            # Delete files if sync'ing with source
            if cst_cfg['syncFromSource'] == '1':
                files['deleted'] = delete_from_dest(dest_dir, files['include'])

        return {'verdict': True, 'files': files}


    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)

            cst_cfg = payload_obj.get('collectionSystemTransfer', {})
            cst_id = cst_cfg.get('collectionSystemTransferID')

            self.collection_system_transfer = self.ovdm.get_collection_system_transfer(cst_id)

            if self.collection_system_transfer is None:
                self.collection_system_transfer = {
                    'name': "UNKNOWN"
                }

                return self._fail_job(current_job, "Retrieve collection system transfer",
                                      "Could not retrieve collection system transfer for transferring files")

        except Exception:
            reason = "Failed to parse current job payload"
            logging.exception(reason)
            return self._fail_job(current_job, "Retrieve collection system transfer data", reason)

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.collection_system_transfer['name']}: %(message)s"
        ))

        # verify the transfer is NOT already in-progress
        if self.collection_system_transfer['status'] == "1":
            logging.info("Transfer already in-progress")
            return self._ignore_job(current_job, "Transfer in-Progress", "Transfer is already in-progress")

        start_time = time.gmtime()
        self.transfer_start_date = time.strftime("%Y%m%dT%H%M%SZ", start_time)

        logging.info("Job Started: %s", current_job.handle)

        system_status = payload_obj.get('systemStatus', self.ovdm.get_system_status())
        self.collection_system_transfer.update(payload_obj['collectionSystemTransfer'])

        if system_status == "Off" or self.collection_system_transfer['enable'] == '0':
            logging.info("Transfer disabled for %s", self.collection_system_transfer['name'])
            return self._ignore_job(current_job, "Transfer Enabled", "Transfer is disabled")

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())

        # Check for empty lowering ID passed via payload
        if self.lowering_id is not None and len(self.lowering_id) == 0:
            self.lowering_id = None

        # fail if lowering ID is required but not found
        if (self.collection_system_transfer.get('cruiseOrLowering') == '1'  or '{loweringID}' in self.collection_system_transfer.get('destDir')) and self.lowering_id is None:
            return self._fail_job(current_job, "Verify lowering ID",
                                    "Lowering ID is undefined")

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.dest_dir = self.build_dest_dir()
        self.source_dir = self.build_source_dir()

        ### Set temporal bounds for transfer
        self.data_start_date = "1970/01/01 00:00"
        self.data_end_date = "9999/12/31 23:59:59"

        # if requested, set to specified bounds for the corresponding cruise/lowering
        if self.collection_system_transfer['useStartDate'] == '1':
            if self.collection_system_transfer['cruiseOrLowering'] == "0":
                logging.debug("Using cruise Time bounds")
                self.data_start_date = self.ovdm.get_cruise_start_date() or "1970/01/01 00:00"
                cruise_end = self.ovdm.get_cruise_end_date()
                self.data_end_date = f"{cruise_end}:59" if cruise_end else "9999/12/31 23:59:59"
            else:
                logging.debug("Using lowering Time bounds")
                self.data_start_date = self.ovdm.get_lowering_start_date() or "1970/01/01 00:00"
                lowering_end = self.ovdm.get_lowering_end_date()
                self.data_end_date = f"{lowering_end}:59" if lowering_end else "9999/12/31 23:59:59"

            if self.collection_system_transfer['staleness'] != "0":
                staleness_dt = (datetime.utcnow() - timedelta(seconds=int(self.collection_system_transfer['staleness']))).replace(tzinfo=pytz.UTC)
                data_end_dt = datetime.strptime(f"{self.data_end_date}+0000", "%Y/%m/%d %H:%M:%S%z")
                if staleness_dt < data_end_dt:
                    self.data_end_date = staleness_dt.strftime("%Y/%m/%d %H:%M:%S")

        # Todo - there's a chance the dates are not set and stay set to None... which errors here.
        logging.debug("Start date/time filter: %s", self.data_start_date)
        logging.debug("End date/time filter: %s", self.data_end_date)

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

        cst_id = self.collection_system_transfer.get('collectionSystemTransferID')

        if cst_id:
            self.ovdm.set_error_collection_system_transfer(cst_id, f'Worker crashed: {str(exc_type)}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)
        parts = results.get('parts', [])
        final_verdict = parts[-1] if parts else None
        cst_id = self.collection_system_transfer.get('collectionSystemTransferID')

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job Completed: %s", current_job.handle)

        if not cst_id:
            return super().send_job_complete(current_job, job_result)

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', "undefined")
            self.ovdm.set_error_collection_system_transfer(cst_id, reason)
            return super().send_job_complete(current_job, job_result)

        # If not a failure, prepare potential follow-up jobs
        new_files = results.get('files', {}).get('new', [])
        updated_files = results.get('files', {}).get('updated', [])
        deleted_files = results.get('files', {}).get('deleted', [])

        if new_files or updated_files or deleted_files:
            logging.info("Preparing subsequent Gearman jobs")
            rel_dir = self.build_rel_dir()
            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            job_data = {
                'cruiseID': self.cruise_id,
                'collectionSystemTransferID': cst_id,
                'files': {
                    'new': [os.path.join(rel_dir, f) for f in new_files],
                    'updated': [os.path.join(rel_dir, f) for f in updated_files],
                    'deleted': [os.path.normpath(os.path.join(rel_dir, f)) for f in deleted_files],
                }
            }

            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        # Always set idle at the end if not failed
        self.ovdm.set_idle_collection_system_transfer(cst_id)

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
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


    def _ignore_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as ignored
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_run_collection_system_transfer(worker, current_job): # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements
    """
    Run the collection system transfer
    """

    time.sleep(randint(0,2))

    cst_cfg = worker.collection_system_transfer

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
    worker.ovdm.set_running_collection_system_transfer(cst_cfg['collectionSystemTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing source")
    worker.send_job_status(current_job, 1, 10)

    results = test_cst_source(cst_cfg, worker.source_dir)

    if results[-1]['result'] == "Fail": # Final Verdict
        logging.warning("Source test failed, quitting job")
        job_results['parts'].append({"partName": "Source Test", "result": "Fail", "reason": results[-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Source Test", "result": "Pass"})

    logging.info("Testing destination")
    worker.send_job_status(current_job, 15, 100)

    results = worker.test_destination_dir()

    if results[-1]['result'] == "Fail": # Final Verdict
        logging.warning("Destination test failed, quitting job")
        job_results['parts'].append({"partName": "Destination Test", "result": "Fail", "reason": results[-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Destination Test", "result": "Pass"})

    logging.info("Transferring files")
    worker.send_job_status(current_job, 2, 10)

    results = worker.transfer_from_source(current_job)

    if not results['verdict']:
        logging.error("Transfer of remote files failed: %s", results['reason'])
        job_results['parts'].append({"partName": "Transfer Files", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    job_results['files'] = results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s misnamed file(s) encountered", len(job_results['files']['exclude']))
    if job_results['files'].get('deleted') and len(job_results['files']['deleted']) > 0:
        logging.debug("%s file(s) deleted", len(job_results['files']['deleted']))

    if job_results['files']['new'] or job_results['files']['updated']:
        if worker.shipboard_data_warehouse_config['localDirIsMountPoint'] == '0':
            logging.info("Setting file permissions")
            worker.send_job_status(current_job, 9, 10)

            results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.dest_dir)

            if not results['verdict']:
                logging.error("Error setting destination directory file/directory ownership/permissions: %s", worker.dest_dir)
                job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Fail", "reason": results['reason']})

            job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Pass"})

        logging.info("Writing transfer logfile")
        worker.send_job_status(current_job, 93, 10)

        logfile_filename = f"{cst_cfg['name']}_{worker.transfer_start_date}.log"
        logfile_contents = {
            'files': {
                'new': job_results['files']['new'],
                'updated': job_results['files']['updated']
            }
        }

        results = output_json_data_to_file(os.path.join(worker.build_logfile_dirpath(), logfile_filename), logfile_contents['files'])

        if not results['verdict']:
            logging.error("Error writing transfer logfile: %s", logfile_filename)
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Fail", "reason": results['reason']})
            return json.dumps(job_results)

        results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(worker.build_logfile_dirpath(), logfile_filename))

        if not results['verdict']:
            job_results['parts'].append({"partName": "Set OpenVDM config file ownership/permissions", "result": "Fail", "reason": results['reason']})
            return json.dumps(job_results)

        job_results['parts'].append({"partName": "Write transfer logfile", "result": "Pass"})

    logging.info("Writing exclude logfile")
    worker.send_job_status(current_job, 95, 100)

    logfile_filename = f"{cst_cfg['name']}_Exclude.log"
    logfile_contents = {
        'files': {
            'exclude': job_results['files']['exclude']
        }
    }
    results = output_json_data_to_file(os.path.join(worker.build_logfile_dirpath(), logfile_filename), logfile_contents['files'])

    if not results['verdict']:
        logging.error("Error writing transfer logfile: %s", results['reason'])
        job_results['parts'].append({"partName": "Write exclude logfile", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(worker.build_logfile_dirpath(), logfile_filename))

    if not results['verdict']:
        logging.error("Error setting ownership/permissions for transfer logfile: %s", logfile_filename)
        job_results['parts'].append({"partName": "Set transfer logfile ownership/permissions", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Write exclude logfile", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
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

    logging.info("\tTask: %s", TASK_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'], task_run_collection_system_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
