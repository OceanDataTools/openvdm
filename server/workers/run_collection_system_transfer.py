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
from server.lib.openvdm import OpenVDM

@contextmanager
def temporary_directory():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


def process_batch(file_batch, filters, data_start_time, data_end_time):
    include = []
    exclude = []

    for filepath in file_batch:
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
                exclude.append(filepath)
                continue

            if any(fnmatch.fnmatch(filepath, p) for p in filters['include_filters']):
                if not any(fnmatch.fnmatch(filepath, p) for p in filters['exclude_filters']):
                    include.append((filepath, size))
                else:
                    exclude.append(filepath)
            else:
                exclude.append(filepath)

        except FileNotFoundError:
            continue

    return include, exclude


def verify_staleness_batch(paths_sizes):
    verified = []
    for filepath, old_size in paths_sizes:
        try:
            if os.stat(filepath).st_size == old_size:
                verified.append((filepath, old_size))
        except FileNotFoundError:
            continue
    return verified


def add_rsync_arguments(gearman_worker, command, is_darwin=False):

    if gearman_worker.collection_system_transfer['bandwidthLimit'] != '0':
        command.insert(2, f'--bwlimit={gearman_worker.collection_system_transfer["bandwidthLimit"]}')

    if gearman_worker.collection_system_transfer['syncFromSource'] == '1':
        command.insert(2, '--delete')

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1':
        command.insert(2, '--remove-source-files')

    return command


def build_filelist(gearman_worker, prefix=None, batch_size=500, max_workers=16):
    source_dir = os.path.join(prefix, gearman_worker.source_dir) if prefix else gearman_worker.source_dir
    return_files = {'include': [], 'exclude': [], 'new': [], 'updated': [], 'filesize': []}

    logging.info("Starting filelist build in %s", source_dir)

    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))
    filters = build_filters(gearman_worker)

    # Step 1: Gather all file paths
    filepaths = []
    for root, _, filenames in os.walk(source_dir):
        for filename in filenames:
            filepaths.append(os.path.join(root, filename))

    total_files = len(filepaths)
    logging.info("Discovered %d files", total_files)

    # Step 2: Batch file paths
    batches = [filepaths[i:i + batch_size] for i in range(0, total_files, batch_size)]

    # Step 3: Process in thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_batch, batch, filters, data_start_time, data_end_time)
                   for batch in batches]

        for future in as_completed(futures):
            include, exclude = future.result()
            return_files['include'].extend(f for f, _ in include)
            return_files['filesize'].extend(s for _, s in include)
            return_files['exclude'].extend(exclude)

    logging.info("Initial filtering complete: %d included, %d excluded",
                 len(return_files['include']), len(return_files['exclude']))

    # Step 4: Optional staleness check
    staleness = gearman_worker.collection_system_transfer.get('staleness')
    if staleness and staleness != '0':
        wait_secs = int(staleness)
        logging.info("Waiting %ds to verify staleness...", wait_secs)
        time.sleep(wait_secs)

        paths_sizes = list(zip(return_files['include'], return_files['filesize']))
        stale_batches = [paths_sizes[i:i + batch_size] for i in range(0, len(paths_sizes), batch_size)]

        verified_paths = []
        verified_sizes = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(verify_staleness_batch, batch) for batch in stale_batches]

            for future in as_completed(futures):
                verified = future.result()
                for filepath, size in verified:
                    verified_paths.append(filepath)
                    verified_sizes.append(size)

        return_files['include'] = verified_paths
        return_files['filesize'] = verified_sizes

        logging.info("Staleness check complete: %d files remain", len(verified_paths))

    # Step 5: Format output
    del return_files['filesize']
    return_files['include'].sort()
    return_files['exclude'].sort()

    base_len = len(source_dir.rstrip(os.sep)) + 1
    return_files['include'] = [f[base_len:] for f in return_files['include']]
    return_files['exclude'] = [f[base_len:] for f in return_files['exclude']]

    # logging.debug("Final return_files object: %s", json.dumps(return_files, indent=2))
    return {'verdict': True, 'files': return_files}


def process_rsync_line(line, filters, data_start_time, data_end_time, epoch):
    """Process a single line from rsync output."""
    file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)

    if not file_or_dir.startswith('-'):
        return None

    file_mod_time = datetime.strptime(mdate + ' ' + mtime, "%Y/%m/%d %H:%M:%S")
    file_mod_time_seconds = (file_mod_time - epoch).total_seconds()

    if not (data_start_time <= file_mod_time_seconds <= data_end_time):
    # if file_mod_time_seconds < data_start_time or file_mod_time_seconds > data_end_time:
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


def process_rsync_batch(batch, filters, data_start_time, data_end_time, epoch):
    """Process a batch of rsync output lines."""
    results = []
    for line in batch:
        result = process_rsync_line(line, filters, data_start_time, data_end_time, epoch)
        if result:
            results.append(result)

    return results


def build_rsync_filelist(gearman_worker, batch_size=500, max_workers=16):
    """Build the list of files to include, exclude or ignore, for an rsync server transfer."""
    return_files = {'include': [], 'exclude': [], 'new': [], 'updated': [], 'filesize': []}
    epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))

    filters = build_filters(gearman_worker)

    tmpdir = tempfile.mkdtemp()
    rsync_password_filepath = os.path.join(tmpdir, 'passwordFile')

    try:
        with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:
            rsync_password_file.write(gearman_worker.collection_system_transfer['rsyncPass'])
        os.chmod(rsync_password_filepath, 0o600)
    except IOError:
        logging.error("Error Saving temporary rsync password file")
        shutil.rmtree(tmpdir)
        return {'verdict': False, 'reason': 'Error Saving temporary rsync password file'}

    command = ['rsync', '-r', '--password-file=' + rsync_password_filepath, '--no-motd',
               f"rsync://{gearman_worker.collection_system_transfer['rsyncUser']}@"
               f"{gearman_worker.collection_system_transfer['rsyncServer']}"
               f"{gearman_worker.source_dir}/"]

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    logging.debug("Command: %s", ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    # logging.debug("proc.stdout: %s", proc.stdout)

    lines = proc.stdout.splitlines()
    total_files = len(lines)
    logging.info("Discovered %d files", total_files)

    batches = [lines[i:i + batch_size] for i in range(0, total_files, batch_size)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_rsync_batch, batch, filters, data_start_time, data_end_time, epoch)
                   for batch in batches]

        for future in as_completed(futures):
            result = future.result()
            if result:
                for category, filepath, filesize in result:
                    return_files[category].append(filepath)
                    if category == 'include':
                        return_files['filesize'].append(filesize)

    if gearman_worker.collection_system_transfer['staleness'] != '0':
        logging.debug("Checking for changing filesizes")
        time.sleep(int(gearman_worker.collection_system_transfer['staleness']))
        proc = subprocess.run(command, capture_output=True, text=True, check=False)

        for line in proc.stdout.splitlines():
            file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)

            if not file_or_dir.startswith('-'):
                continue

            try:
                younger_file_idx = return_files['include'].index(filepath)
                if return_files['filesize'][younger_file_idx] != size:
                    # logging.debug("file %s has changed size, removing from include list", filepath)
                    del return_files['filesize'][younger_file_idx]
                    del return_files['include'][younger_file_idx]
            except ValueError:
                pass
            except Exception as err:
                logging.error(str(err))

    del return_files['filesize']

    shutil.rmtree(tmpdir)

    # logging.debug('return_files: %s', json.dumps(return_files, indent=2))

    return {'verdict': True, 'files': return_files}


def build_ssh_filelist(gearman_worker, batch_size=500, max_workers=16):
    return_files = {'include': [], 'exclude': [], 'new': [], 'updated': [], 'filesize': []}

    epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))
    filters = build_filters(gearman_worker)

    # Detect if Darwin (macOS)
    is_darwin_cmd = ['ssh', f"{gearman_worker.collection_system_transfer['sshUser']}@{gearman_worker.collection_system_transfer['sshServer']}", "uname -s"]
    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        is_darwin_cmd = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + is_darwin_cmd

    proc = subprocess.run(is_darwin_cmd, capture_output=True, text=True, check=False)
    is_darwin = any(line.strip() == 'Darwin' for line in proc.stdout.splitlines())

    # Build rsync command
    command = ['rsync', '-r', '-e', 'ssh',
               f"{gearman_worker.collection_system_transfer['sshUser']}@{gearman_worker.collection_system_transfer['sshServer']}:{gearman_worker.source_dir}/"]

    if not is_darwin:
        command.insert(2, '--protect-args')

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

    logging.debug("Command: %s", ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    lines = proc.stdout.splitlines()

    batches = [lines[i:i + batch_size] for i in range(0, len(lines), batch_size)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
    if gearman_worker.collection_system_transfer['staleness'] != '0':
        time.sleep(int(gearman_worker.collection_system_transfer['staleness']))
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        for line in proc.stdout.splitlines():
            try:
                file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)
                idx = return_files['include'].index(filepath)
                if return_files['filesize'][idx] != size:
                    del return_files['filesize'][idx]
                    del return_files['include'][idx]
            except (ValueError, Exception) as err:
                logging.warning("Error verifying staleness: %s", err)

    del return_files['filesize']

    # return_files['include'] = [f.split(gearman_worker.source_dir + '/', 1).pop()
    #                            for f in return_files['include']]
    # return_files['exclude'] = [f.split(gearman_worker.source_dir + '/', 1).pop()
    #                            for f in return_files['exclude']]

    # logging.debug('return_files: %s', json.dumps(return_files, indent=2))
    return {'verdict': True, 'files': return_files}


def build_filters(gearman_worker):
    """
    Replace wildcard string in filters
    """

    filters = {
        'includeFilter': gearman_worker.collection_system_transfer['includeFilter']
            .replace('{cruiseID}', gearman_worker.cruise_id)
            .replace('{loweringID}', gearman_worker.lowering_id)
            .replace('{YYYY}', '20[0-9][0-9]')
            .replace('{YY}', '[0-9][0-9]')
            .replace('{mm}', '[0-1][0-9]')
            .replace('{DD}', '[0-3][0-9]')
            .replace('{HH}', '[0-2][0-9]')
            .replace('{MM}', '[0-5][0-9]'),
        'excludeFilter': gearman_worker.collection_system_transfer['excludeFilter']
            .replace('{cruiseID}', gearman_worker.cruise_id)
            .replace('{loweringID}', gearman_worker.lowering_id)
            .replace('{YYYY}', '20[0-9][0-9]')
            .replace('{YY}', '[0-9][0-9]')
            .replace('{mm}', '[0-1][0-9]')
            .replace('{DD}', '[0-3][0-9]')
            .replace('{HH}', '[0-2][0-9]')
            .replace('{MM}', '[0-5][0-9]'),
        'ignoreFilter': gearman_worker.collection_system_transfer['ignoreFilter']
            .replace('{cruiseID}', gearman_worker.cruise_id)
            .replace('{loweringID}', gearman_worker.lowering_id)
            .replace('{YYYY}', '20[0-9][0-9]')
            .replace('{YY}', '[0-9][0-9]')
            .replace('{mm}', '[0-1][0-9]')
            .replace('{DD}', '[0-3][0-9]')
            .replace('{HH}', '[0-2][0-9]')
            .replace('{MM}', '[0-5][0-9]')
    }
    # logging.debug(json.dumps(filters, indent=2))

    return {
        'include_filters': filters['includeFilter'].split(',') if filters['includeFilter'] else [],
        'exclude_filters': filters['excludeFilter'].split(',') if filters['excludeFilter'] else [],
        'ignore_filters': filters['ignoreFilter'].split(',') if filters['ignoreFilter'] else []
    }


def build_dest_dir(gearman_worker):
    """
    Replace wildcard string in destDir
    """

    return gearman_worker.collection_system_transfer['destDir'].replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', gearman_worker.lowering_id).replace('{loweringDataBaseDir}', gearman_worker.shipboard_data_warehouse_config['loweringDataBaseDir']).rstrip('/')


def build_source_dir(gearman_worker):
    """
    Replace wildcard string in sourceDir
    """

    return gearman_worker.collection_system_transfer['sourceDir'].replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', gearman_worker.lowering_id).replace('{loweringDataBaseDir}', gearman_worker.shipboard_data_warehouse_config['loweringDataBaseDir']).rstrip('/')


def build_logfile_dirpath(gearman_worker):
    """
    build the path to save transfer logfiles
    """

    return os.path.join(gearman_worker.cruise_dir, gearman_worker.ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])

def run_transfer_command(gearman_worker, gearman_job, command, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.debug("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.debug('Transfer Command: %s', ' '.join(command))

    TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

    # file_index = 0
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

            logging.debug("%s", line)

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


def transfer_local_source_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Preform a collection system transfer from a local directory
    """

    logging.debug("Transfer from Local Directory")
    logging.debug("Source Dir: %s", gearman_worker.source_dir)
    logging.debug("Destination Dir: %s", gearman_worker.dest_dir)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    logging.debug("Build file list")
    output_results = build_filelist(gearman_worker)
    if not output_results['verdict']:
        return { 'verdict': False, 'reason': "Error building filelist", 'files':[] }
    files = output_results['files']
    # logging.debug("Files: %s", json.dumps(files['include'], indent=2))

    rsync_filelist_filepath = os.path.join(tmpdir, 'rsyncFileList.txt')

    logging.debug("Mod file list")
    local_transfer_filelist = files['include']
    local_transfer_filelist = [filename.replace(gearman_worker.source_dir, '', 1) for filename in local_transfer_filelist]

    try:
        with open(rsync_filelist_filepath, mode='w', encoding='utf-8') as rsync_filelist_file:
            rsync_filelist_file.write('\n'.join(local_transfer_filelist))
            rsync_filelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file %s", rsync_filelist_filepath)

        # Cleanup
        shutil.rmtree(tmpdir)
        return {'verdict': False, 'reason': 'Error Saving temporary rsync filelist file: ' + rsync_filelist_filepath, 'files': []}

    command = ['rsync', '-tri', '--files-from=' + rsync_filelist_filepath, gearman_worker.source_dir + '/', gearman_worker.dest_dir]

    command = add_rsync_arguments(gearman_worker, command)

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    # Cleanup
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}


def transfer_smb_source_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Preform a collection system transfer from a samba server
    """

    logging.debug("Transfer from SMB Source")

    gearman_worker.source_dir = gearman_worker.source_dir.strip().rstrip('/').lstrip('/')

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    # Create mountpoint
    mntpoint = os.path.join(tmpdir, 'mntpoint')
    os.mkdir(mntpoint, 0o755)

    logging.debug("Source Dir: %s", gearman_worker.source_dir)
    logging.debug("Destination Dir: %s", gearman_worker.dest_dir)

    # Mount SMB Share
    logging.debug("Mounting SMB Share")

    ver_test_command = ['smbclient', '-L', gearman_worker.collection_system_transfer['smbServer'], '-W', gearman_worker.collection_system_transfer['smbDomain'], '-m', 'SMB2', '-g', '-N'] if gearman_worker.collection_system_transfer['smbUser'] == 'guest' else ['smbclient', '-L', gearman_worker.collection_system_transfer['smbServer'], '-W', gearman_worker.collection_system_transfer['smbDomain'], '-m', 'SMB2', '-g', '-U', gearman_worker.collection_system_transfer['smbUser'] + '%' + gearman_worker.collection_system_transfer['smbPass']]
    logging.debug("SMB version test command: %s", ' '.join(ver_test_command))

    vers="2.1"
    proc = subprocess.run(ver_test_command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('OS=[Windows 5.1]'):
            vers="1.0"
            break

    rw_type = 'rw' if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1' else 'ro'
    if gearman_worker.collection_system_transfer['smbUser'] == 'guest':
        rw_type += ',guest'
    else:
        rw_type += f",username={gearman_worker.collection_system_transfer['smbUser']}"
        rw_type += f",password={gearman_worker.collection_system_transfer['smbPass']}"

    mount_command = ['sudo', 'mount', '-t', 'cifs', gearman_worker.collection_system_transfer['smbServer'], mntpoint, '-o', f"{rw_type},domain={gearman_worker.collection_system_transfer['smbDomain']},vers={vers}"]

    logging.debug("Mount command: %s", ' '.join(mount_command))

    proc = subprocess.call(mount_command)

    logging.debug("Build file list")
    output_results = build_filelist(gearman_worker, prefix=mntpoint)
    if not output_results['verdict']:
        return { 'verdict': False, 'reason': "Error building filelist", 'files':[] }
    files = output_results['files']

    # logging.debug("File List: %s", json.dumps(files['include'], indent=2))

    rsync_filelist_filepath = os.path.join(tmpdir, 'rsyncFileList.txt')

    try:
        with open(rsync_filelist_filepath, mode='w', encoding='utf-8') as rsync_filelist_file:
            rsync_filelist_file.write('\n'.join(files['include']))
            rsync_filelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file")

        # Cleanup
        time.sleep(2)
        subprocess.call(['umount', mntpoint])
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': f'Error Saving temporary rsync filelist file: {rsync_filelist_filepath}', 'files': []}

    command = ['rsync', '-tri', '--files-from=' + rsync_filelist_filepath, os.path.join(mntpoint, gearman_worker.source_dir), gearman_worker.dest_dir]

    command = add_rsync_arguments(gearman_worker, command)

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    # Cleanup
    time.sleep(2)
    logging.debug('Unmounting SMB Share')
    subprocess.call(['umount', mntpoint])
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}

def transfer_rsync_source_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Preform a collection system transfer from a rsync server
    """

    logging.debug("Transfer from RSYNC Server")
    logging.debug("Source Dir: %s", gearman_worker.source_dir)
    logging.debug("Destination Dir: %s", gearman_worker.dest_dir)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    logging.debug("Build file list")
    output_results = build_rsync_filelist(gearman_worker)
    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason'], 'files':[]}
    files = output_results['files']

    rsync_password_filepath = os.path.join(tmpdir, 'passwordFile')

    try:
        with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:
            rsync_password_file.write(gearman_worker.collection_system_transfer['rsyncPass'])

        os.chmod(rsync_password_filepath, 0o600)

    except IOError:
        logging.error("Error Saving temporary rsync password file")
        rsync_password_file.close()

        # Cleanup
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': f'Error Saving temporary rsync password file: {rsync_password_filepath}'}

    rsync_filelist_filepath = os.path.join(tmpdir, 'rsyncFileList.txt')

    try:
        with open(rsync_filelist_filepath, mode='w', encoding='utf-8') as rsync_filelist_file:
            rsync_filelist_file.write('\n'.join(files['include']))
            rsync_filelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file")

        # Cleanup
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': f'Error Saving temporary rsync filelist file: {rsync_filelist_filepath}', 'files':[]}

    command = ['rsync', '-tri', '--no-motd', '--files-from=' + rsync_filelist_filepath, '--password-file=' + rsync_password_filepath, 'rsync://' + gearman_worker.collection_system_transfer['rsyncUser'] + '@' + gearman_worker.collection_system_transfer['rsyncServer'] + gearman_worker.source_dir, gearman_worker.dest_dir]

    command = add_rsync_arguments(gearman_worker, command)

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    # Cleanup
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}


def transfer_ssh_source_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals
    """
    Preform a collection system transfer from a ssh server
    """

    logging.debug("Transfer from SSH Server")
    logging.debug("Source Dir: %s", gearman_worker.source_dir)
    logging.debug("Destination Dir: %s", gearman_worker.dest_dir)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    logging.debug("Build file list")
    output_results = build_ssh_filelist(gearman_worker)
    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason'], 'files':[]}
    files = output_results['files']

    ssh_filelist_filepath = os.path.join(tmpdir, 'sshFileList.txt')

    try:
        with open(ssh_filelist_filepath, mode='w', encoding='utf-8') as ssh_filelist_file:
            ssh_filelist_file.write('\n'.join(files['include']))
            ssh_filelist_file.write('\0')

    except IOError:
        logging.debug("Error Saving temporary ssh filelist file")

        # Cleanup
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': f'Error Saving temporary rsync filelist file: {ssh_filelist_filepath}', 'files':[]}

    is_darwin = False
    command = ['ssh',  gearman_worker.collection_system_transfer['sshUser'] + '@' + gearman_worker.collection_system_transfer['sshServer'], "uname -s"]

    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

    logging.debug("Command: %s", ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines(): # pylint: disable=too-many-nested-blocks
        is_darwin = line.rstrip('\n') == 'Darwin'
        if is_darwin:
            break

    command = ['rsync', '-tri', '--files-from=' + ssh_filelist_filepath, '-e', 'ssh', gearman_worker.collection_system_transfer['sshUser'] + '@' + gearman_worker.collection_system_transfer['sshServer'] + ':' + gearman_worker.source_dir, gearman_worker.dest_dir]

    if not is_darwin:
        command.insert(2, '--protect-args')

    command = add_rsync_arguments(gearman_worker, command)

    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    # Cleanup
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}

def detect_smb_version(cst_cfg):
    if cst_cfg['smbUser'] == 'guest':
        cmd = [
            'smbclient', '-L', cst_cfg['smbServer'],
            '-W', cst_cfg['smbDomain'], '-m', 'SMB2', '-g', '-N'
        ]
    else:
        cmd = [
            'smbclient', '-L', cst_cfg['smbServer'],
            '-W', cst_cfg['smbDomain'], '-m', 'SMB2', '-g',
            '-U', f"{cst_cfg['smbUser']}%{cst_cfg['smbPass']}"
        ]

    logging.debug("SMB version test command: %s", ' '.join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('OS=[Windows 5.1]'):
            return '1.0'
    return '2.1'


def mount_smb_share(cst_cfg, mntpoint, smb_version):

    read_write = 'rw' if cst_cfg['removeSourceFiles'] == '1' else 'ro'

    opts = f"{read_write},domain={cst_cfg['smbDomain']},vers={smb_version}"

    if cst_cfg['smbUser'] == 'guest':
        opts += ",guest"
    else:
        opts += f",username={cst_cfg['smbUser']},password={cst_cfg['smbPass']}"

    mount_cmd = ['mount', '-t', 'cifs', cst_cfg['smbServer'], mntpoint, '-o', opts]
    logging.debug("Mount command: %s", ' '.join(mount_cmd))

    result = subprocess.run(mount_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logging.error("Failed to mount SMB share.")
        logging.error("STDOUT: %s", result.stdout.strip())
        logging.error("STDERR: %s", result.stderr.strip())

        # Try to unmount in case of partial mount
        subprocess.run(['umount', mntpoint], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    logging.info("Mounted SMB share successfully.")
    return True


def write_include_file(include_list, filepath):
    try:
        with open(filepath, mode='w', encoding="utf-8") as f:
            f.write('\n'.join(include_list))
            f.write('\0')
    except IOError as e:
        logging.error("Error writing include file: %s", e)
        return False

    return True


def build_rsync_command(flags, extra_args, source_dir, dest_dir, include_file_path=None):
    logging.warning(include_file_path)
    cmd = ['rsync'] + flags
    cmd += extra_args
    if include_file_path is not None:
        cmd.append(f"--file-from={include_file_path}")
    cmd += [source_dir, dest_dir]
    return cmd


def build_rsync_options(cfg, mode='dry-run', is_darwin=False, transfer_type=None):
    """
    Builds a list of rsync options based on config, transfer mode, and destination type.

    :param cfg: dict-like config object (e.g., gearman_worker.cruise_data_transfer)
    :param mode: 'dry-run' or 'real'
    :param transfer_type: 'local', 'smb', 'rsync', or 'ssh'
    :return: list of rsync flags
    """
    flags = ['-trinv'] if mode == 'dry-run' else ['-triv', '--progress']

    if not is_darwin:
        flags.insert(1, '--protect-args')

    if cfg.get('skipEmptyFiles') == '1':
        flags.insert(1, '--min-size=1')

    if cfg.get('skipEmptyDirs') == '1':
        flags.insert(1, '-m')

    if mode == 'dry-run':
        flags.append('--dry-run')
        flags.append('--stats')

    else:
        if cfg.get('syncToDest') == '1':
            flags.insert(1, '--delete')

        if transfer_type == 'rsync':
            flags.append('--no-motd')

        if cfg.get('bandwidthLimit') not in (None, '0'):
            flags.insert(1, f"--bwlimit={cfg['bandwidthLimit']}")

        if cfg['removeSourceFiles'] == '1':
            flags.insert(2, '--remove-source-files')

        if cfg['syncFromSource'] == '1':
            flags.insert(2, '--delete')

    return flags


def transfer_from_source(gearman_worker, gearman_job, transfer_type):
    """
    Perform a collection system transfer from the configured source type.
    """
    logging.debug("Starting unified transfer: %s", transfer_type)

    cfg = gearman_worker.collection_system_transfer
    source_dir = gearman_worker.source_dir
    dest_dir = gearman_worker.dest_dir

    prefix = None
    mntpoint = None

    with temporary_directory() as tmpdir:
        include_file = os.path.join(tmpdir, 'rsyncFileList.txt')
        password_file = os.path.join(tmpdir, 'passwordFile')

        # Adjustments for SMB
        if transfer_type == 'smb':
            # Mount SMB Share
            mntpoint = os.path.join(tmpdir, 'mntpoint')
            os.mkdir(mntpoint, 0o755)
            smb_version = detect_smb_version(cfg)
            success = mount_smb_share(gearman_worker, mntpoint, smb_version)
            if not success:
                return {'verdict': False, 'reason': 'Failed to mount SMB share'}
            prefix = mntpoint

        # Build filelist (from local, SMB mount, etc.)
        filelist_result = build_filelist(gearman_worker, prefix=prefix) if transfer_type in ['local', 'smb'] else (
            build_rsync_filelist(gearman_worker) if transfer_type == 'rsync' else build_ssh_filelist(gearman_worker)
        )
        if not filelist_result['verdict']:
            if mntpoint:
                subprocess.call(['umount', mntpoint])
            return {'verdict': False, 'reason': filelist_result.get('reason', 'Unknown'), 'files': []}

        files = filelist_result['files']

        # Write file list
        if not write_include_file(files['include'], include_file):
            if mntpoint:
                subprocess.call(['umount', mntpoint])
            return {'verdict': False, 'reason': 'Error writing file list', 'files': []}

        # Build rsync command
        if transfer_type == 'local':
            source_path = os.path.join(prefix if prefix else '', source_dir.lstrip('/')).rstrip('/')
        elif transfer_type == 'rsync':
            try:
                with open(password_file, 'w', encoding='utf-8') as f:
                    f.write(gearman_worker.collection_system_transfer['rsyncPass'])
                os.chmod(password_file, 0o600)
            except IOError:
                return {'verdict': False, 'reason': 'Error writing rsync password file', 'files': []}

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
        rsync_flags = build_rsync_options(cfg, mode='real', is_darwin=False, transfer_type=transfer_type)

        rsync_cmd = build_rsync_command(rsync_flags, extra_args, source_dir, dest_dir, include_file)
        if transfer_type == 'ssh' and cfg.get('sshUseKey') == '0':
            rsync_cmd = ['sshpass', '-p', cfg['sshPass']] + rsync_cmd

        # Transfer files
        # files['new'], files['updated'] = run_transfer_command(
        #     gearman_worker, gearman_job, rsync_cmd, len(files['include'])
        # )

        # Cleanup
        if mntpoint:
            time.sleep(2)
            subprocess.call(['umount', mntpoint])

    return {'verdict': True, 'files': files}



class OVDMGearmanWorker(python3_gearman.GearmanWorker):  # pylint: disable=too-many-instance-attributes
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.transfer_start_date = None
        self.cruise_id = None
        self.cruise_dir = None
        self.source_dir = None
        self.dest_dir = None
        self.lowering_id = None
        self.data_start_date = None
        self.data_end_date = None
        self.system_status = None
        self.collection_system_transfer = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])

    def on_job_execute(self, current_job):
        """
        Function run whenever a new job arrives
        """

        LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.debug("current_job: %s", current_job)

        payload_obj = json.loads(current_job.data)
        logging.debug("payload: %s", current_job.data)

        try:
            self.collection_system_transfer = self.ovdm.get_collection_system_transfer(payload_obj['collectionSystemTransfer']['collectionSystemTransferID'])

            if not self.collection_system_transfer: # doesn't exists
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Collection System Tranfer Data", "result": "Fail", "reason": "Could not find configuration data for collection system transfer"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

            if self.collection_system_transfer['status'] == "1": #running
                logging.info("Transfer job skipped because a transfer for that collection system is already in-progress")
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer In-Progress", "result": "Ignore", "reason": "Transfer is already in-progress"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        except Exception as err:
            logging.error(str(err))
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Collection System Tranfer Data", "result": "Fail", "reason": "Could not find retrieve data for collection system transfer from OpenVDM API"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        LOGGING_FORMAT = f'%(asctime)-15s %(levelname)s - {self.collection_system_transfer["name"]}: %(message)s'
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        self.system_status = payload_obj['systemStatus'] if 'systemStatus' in payload_obj else self.ovdm.get_system_status()
        self.collection_system_transfer.update(payload_obj['collectionSystemTransfer'])

        if self.system_status == "Off" or self.collection_system_transfer['enable'] == '0':
            logging.info("Transfer job for %s skipped because that collection system transfer is currently disabled", self.collection_system_transfer['name'])
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer Enabled", "result": "Ignore", "reason": "Transfer is disabled"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        self.cruise_id = payload_obj['cruiseID'] if 'cruiseID' in payload_obj else self.ovdm.get_cruise_id()
        self.lowering_id = payload_obj['loweringID'] if 'loweringID' in payload_obj else self.ovdm.get_lowering_id()

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        if not self.lowering_id:
            # exit with error if trying to run a lowering collection system transfer
            if self.collection_system_transfer['cruiseOrLowering'] == "1":
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Validate Lowering ID", "result": "Fail", "reason": "Lowering ID is not defined"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

            # exit with error if trying to run a cruise collection system transfer that has a loweringID in the destination path
            if '{loweringID}' in self.collection_system_transfer['destDir']:
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Validate Lowering ID", "result": "Fail", "reason": "Lowering ID is not defined"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

            self.lowering_id = ""

        if self.collection_system_transfer['cruiseOrLowering'] == "1":
            self.dest_dir = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id, build_dest_dir(self))
        else:
            self.dest_dir = os.path.join(self.cruise_dir, build_dest_dir(self))

        self.source_dir = build_source_dir(self)

        logging.info("Job: %s, transfer started at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

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
                self.data_end_date = self.ovdm.get_cruise_end_date() + ":59" if self.ovdm.get_cruise_end_date() else "9999/12/31 23:59:59"
                # self.data_start_date = payload_obj['cruiseStartDate'] if 'cruiseStartDate' in payload_obj and payload_obj['cruiseStartDate'] != '' else "1970/01/01 00:00"
                # self.data_end_date = payload_obj['cruiseEndDate'] if 'cruiseEndDate' in payload_obj and payload_obj['cruiseEndDate'] != '' else "9999/12/31 23:59"
            else:
                logging.debug("Using lowering Time bounds")
                self.data_start_date = self.ovdm.get_lowering_start_date() or "1970/01/01 00:00"
                self.data_end_date = self.ovdm.get_lowering_end_date() + ":59" if self.ovdm.get_lowering_end_date() else "9999/12/31 23:59:59"
                # self.data_start_date = payload_obj['loweringStartDate'] if 'loweringStartDate' in payload_obj and payload_obj['loweringStartDate'] != '' else "1970/01/01 00:00"
                # self.data_end_date = payload_obj['loweringEndDate'] if 'loweringEndDate' in payload_obj and payload_obj['loweringEndDate'] != '' else "9999/12/31 23:59"

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

        logging.error("Job: %s, transfer failed at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{"partName": "Worker crashed", "result": "Fail", "reason": "Unknown"}]))
        self.ovdm.set_error_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'], 'Worker crashed')

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run whenever the current job completes
        """

        results_obj = json.loads(job_result)

        if results_obj['files']['new'] or results_obj['files']['updated']:

            logging.debug("Preparing subsequent Gearman jobs")
            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            job_data = {
                'cruiseID': self.cruise_id,
                'collectionSystemTransferID': self.collection_system_transfer['collectionSystemTransferID'] if self.collection_system_transfer else '-1',
                'files': {
                    'new': [ os.path.join(self.collection_system_transfer['destDir'], filepath).lstrip('/') for filepath in results_obj['files']['new']],
                    'updated': [ os.path.join(self.collection_system_transfer['destDir'], filepath).lstrip('/') for filepath in results_obj['files']['updated']]
                }
            }

            for task in self.ovdm.get_tasks_for_hook('runCollectionSystemTransfer'):
                logging.info("Adding post task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        if self.collection_system_transfer:
            if len(results_obj['parts']) > 0:
                if results_obj['parts'][-1]['result'] == "Fail" and results_obj['parts'][-1]['partName'] != "Located Collection System Tranfer Data": # Final Verdict
                    self.ovdm.set_error_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'], results_obj['parts'][-1]['reason'])
                elif results_obj['parts'][-1]['result'] == "Pass":
                    self.ovdm.set_idle_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'])
            else:
                self.ovdm.set_idle_collection_system_transfer(self.collection_system_transfer['collectionSystemTransferID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s, transfer completed at: %s", current_job.handle, time.strftime("%D %T", time.gmtime()))

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

    logging.debug("Transfer completed successfully")
    job_results['files'] = output_results['files']
    job_results['parts'].append({"partName": "Transfer Files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.warning("%s misnamed file(s) encountered", len(job_results['files']['exclude']))

    gearman_worker.send_job_status(current_job, 9, 10)

    if job_results['files']['new'] or job_results['files']['updated']:

        logging.info("Setting file permissions")
        output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], gearman_worker.dest_dir)

        if not output_results['verdict']:
            logging.error("Error setting destination directory file/directory ownership/permissions: %s", gearman_worker.dest_dir)
            job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Fail", "reason": output_results['reason']})

        job_results['parts'].append({"partName": "Setting file/directory ownership/permissions", "result": "Pass"})

        logging.debug("Building logfiles")

        logfile_filename = gearman_worker.collection_system_transfer['name'] + '_' + gearman_worker.transfer_start_date + '.log'

        logfile_contents = {
            'files': {
                'new': job_results['files']['new'],
                'updated': job_results['files']['updated']
            }
        }

        output_results = output_json_data_to_file(os.path.join(build_logfile_dirpath(gearman_worker), logfile_filename), logfile_contents['files'])

        if output_results['verdict']:
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Pass"})
        else:
            logging.error("Error writing transfer logfile: %s", logfile_filename)
            job_results['parts'].append({"partName": "Write transfer logfile", "result": "Fail", "reason": output_results['reason']})
            return json.dumps(job_results)

        output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(build_logfile_dirpath(gearman_worker), logfile_filename))

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

    output_results = output_json_data_to_file(os.path.join(build_logfile_dirpath(gearman_worker), logfile_filename), logfile_contents['files'])

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Write exclude logfile", "result": "Pass"})
    else:
        logging.error("Error writing transfer logfile: %s", output_results['reason'])
        job_results['parts'].append({"partName": "Write exclude logfile", "result": "Fail", "reason": output_results['reason']})
        return job_results

    output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(build_logfile_dirpath(gearman_worker), logfile_filename))

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

    logging.debug("Creating Worker...")

    new_worker = OVDMGearmanWorker()
    new_worker.set_client_id(__file__)

    logging.debug("Defining Signal Handlers...")
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
