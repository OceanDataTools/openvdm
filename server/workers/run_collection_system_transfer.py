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
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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


def build_filelist(gearman_worker, prefix=None): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    Build the list of files to include, exclude or ignore
    """

    source_dir = os.path.join(prefix, gearman_worker.source_dir) if prefix else gearman_worker.source_dir

    return_files = {'include':[], 'exclude':[], 'new':[], 'updated':[], 'filesize':[]}

    logging.debug("data_start_date: %s", gearman_worker.data_start_date)
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    logging.debug("Start: %s", data_start_time)

    logging.debug("data_end_date: %s", gearman_worker.data_end_date)
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))
    logging.debug("End: %s", data_end_time)

    filters = build_filters(gearman_worker)

    for root, _, filenames in os.walk(source_dir): # pylint: disable=too-many-nested-blocks
        for filename in filenames:
            filepath = os.path.join(root, filename)

            if os.path.islink(filepath):
                logging.debug("%s is a symlink, skipping", filepath)
                continue

            exclude = False
            ignore = False
            include = False

            file_mod_time = os.stat(filepath).st_mtime
            logging.debug("file_mod_time: %s", file_mod_time)

            if file_mod_time < data_start_time or file_mod_time > data_end_time:
                logging.debug("%s ignored for time reasons", filepath)
                ignore = True
                continue

            for ignore_filter in filters['ignoreFilter'].split(','):
                if fnmatch.fnmatch(filepath, ignore_filter):
                    logging.debug("%s ignored by ignore filter", filepath)
                    ignore = True
                    break

            if ignore:
                continue

            if not is_ascii(filepath):
                logging.debug("%s is not an ascii-encoded unicode string", filepath)
                return_files['exclude'].append(filepath)
                exclude = True
                continue

            for include_filter in filters['includeFilter'].split(','):
                if fnmatch.fnmatch(filepath, include_filter):
                    for exclude_filter in filters['excludeFilter'].split(','):
                        if fnmatch.fnmatch(filepath, exclude_filter):
                            logging.debug("%s excluded by exclude filter", filepath)
                            return_files['exclude'].append(filepath)
                            exclude = True
                            break

                    if exclude:
                        break

                    logging.debug("%s is a valid file for transfer", filepath)
                    include = True
                    break

            if include:
                return_files['include'].append(filepath)
                return_files['filesize'].append(os.stat(filepath).st_size)

            elif not ignore and not exclude:
                logging.debug("%s excluded because file does not match any of the filters", filepath)
                return_files['exclude'].append(filepath)

    if not gearman_worker.collection_system_transfer['staleness'] == '0':
        logging.debug("Checking for changing filesizes")
        time.sleep(int(gearman_worker.collection_system_transfer['staleness']))
        for idx, filepath in enumerate(return_files['include']):
            if not os.stat(filepath).st_size == return_files['filesize'][idx]:
                logging.debug("file %s has changed size, removing from include list", filepath)
                del return_files['include'][idx]
                del return_files['filesize'][idx]

    del return_files['filesize']

    return_files['include'].sort()
    return_files['exclude'].sort()

    return_files['include'] = [filename.replace(source_dir, '').lstrip('/') for filename in return_files['include']]
    return_files['exclude'] = [filename.replace(source_dir, '').lstrip('/') for filename in return_files['exclude']]

    logging.debug("return_files: %s", json.dumps(return_files, indent=2))
    return {'verdict': True, 'files': return_files}


def build_rsync_filelist(gearman_worker): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    Build the list of files to include, exclude or ignore, for an rsync server
    transfer
    """

    return_files = {'include':[], 'exclude':[], 'new':[], 'updated':[], 'filesize':[]}

    # staleness = int(gearman_worker.collection_system_transfer['staleness']) * 60
    # threshold_time = time.time() - staleness # 5 minutes
    epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))

    # logging.debug("Threshold: %s", threshold_time)
    logging.debug("    Start: %s", data_start_time)
    logging.debug("      End: %s", data_end_time)

    filters = build_filters(gearman_worker)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()
    rsync_password_filepath = os.path.join(tmpdir, 'passwordFile')

    try:
        with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:
            rsync_password_file.write(gearman_worker.collection_system_transfer['rsyncPass'])
        os.chmod(rsync_password_filepath, 0o600)

    except IOError:
        logging.error("Error Saving temporary rsync password file")

        # Cleanup
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': 'Error Saving temporary rsync password file: ' + rsync_password_filepath}

    command = ['rsync', '-r', '--password-file=' + rsync_password_filepath, '--no-motd', 'rsync://' + gearman_worker.collection_system_transfer['rsyncUser'] + '@' + gearman_worker.collection_system_transfer['rsyncServer'] + gearman_worker.source_dir + '/']

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1':
        command.insert(2, '--remove-source-files')

    logging.debug("Command: %s", ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    logging.debug("proc.stdout: %s", proc.stdout)

    for line in proc.stdout.splitlines(): # pylint: disable=too-many-nested-blocks
        logging.debug('line: %s', line.rstrip('\n'))
        file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)
        if file_or_dir.startswith('-'):
            exclude = False
            ignore = False
            include = False

            file_mod_time = datetime.strptime(mdate + ' ' + mtime, "%Y/%m/%d %H:%M:%S")
            file_mod_time_seconds = (file_mod_time - epoch).total_seconds()
            logging.debug("file_mod_time_seconds: %s", file_mod_time_seconds)
            if file_mod_time_seconds < data_start_time or file_mod_time_seconds > data_end_time:  # pylint: disable=chained-comparison
                logging.debug("%s ignored for time reasons", filepath)
                ignore = True
                continue

            for ignore_filter in filters['ignoreFilter'].split(','):
                if fnmatch.fnmatch(filepath, ignore_filter):
                    logging.debug("%s ignored because file matched ignore filter", filepath)
                    ignore = True
                    break

            if ignore:
                continue

            if not is_ascii(filepath):
                logging.debug("%s is not an ascii-encoded unicode string", filepath)
                return_files['exclude'].append(filepath)
                exclude = True
                continue

            for include_filter in filters['includeFilter'].split(','):
                if fnmatch.fnmatch(filepath, include_filter):
                    for exclude_filter in filters['excludeFilter'].split(','):
                        if fnmatch.fnmatch(filepath, exclude_filter):
                            logging.debug("%s excluded because file matches exclude filter", filepath)
                            return_files['exclude'].append(filepath)
                            exclude = True
                            break

                    if exclude:
                        break

                    logging.debug("%s is a valid file for transfer", filepath)
                    include = True
                    break

            if include:
                return_files['include'].append(filepath)
                return_files['filesize'].append(size)

            elif not ignore and not exclude:
                logging.debug("%s excluded because file does not match any include or ignore filters", filepath)
                return_files['exclude'].append(filepath)

    if not gearman_worker.collection_system_transfer['staleness'] == '0':
        logging.debug("Checking for changing filesizes")
        time.sleep(int(gearman_worker.collection_system_transfer['staleness']))
        proc = subprocess.run(command, capture_output=True, text=True, check=False)

        for line in proc.stdout.splitlines():
            file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)

            try:
                younger_file_idx = return_files['include'].index(filepath)
                if return_files['filesize'][younger_file_idx] != size:
                    logging.debug("file %s has changed size, removing from include list", filepath)
                    del return_files['filesize'][younger_file_idx]
                    del return_files['include'][younger_file_idx]
            except ValueError:
                pass
            except Exception as err:
                logging.error(str(err))

    del return_files['filesize']

    # Cleanup
    shutil.rmtree(tmpdir)

    if gearman_worker.source_dir != '':
        return_files['include'] = [filename.split(gearman_worker.source_dir + '/',1).pop() for filename in return_files['include']]
        return_files['exclude'] = [filename.split(gearman_worker.source_dir + '/',1).pop() for filename in return_files['exclude']]

    logging.debug('return_files: %s', json.dumps(return_files, indent=2))

    return {'verdict': True, 'files': return_files}


def build_ssh_filelist(gearman_worker): # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    """
    Build the list of files to include, exclude or ignore for a ssh server
    transfer
    """

    return_files = {'include':[], 'exclude':[], 'new':[], 'updated':[], 'filesize':[]}

    epoch = datetime.strptime('1970/01/01 00:00:00', "%Y/%m/%d %H:%M:%S")
    data_start_time = calendar.timegm(time.strptime(gearman_worker.data_start_date, "%Y/%m/%d %H:%M"))
    data_end_time = calendar.timegm(time.strptime(gearman_worker.data_end_date, "%Y/%m/%d %H:%M:%S"))

    logging.debug("    Start: %s", data_start_time)
    logging.debug("      End: %s", data_end_time)

    filters = build_filters(gearman_worker)

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

    command = ['rsync', '-r', '-e', 'ssh', gearman_worker.collection_system_transfer['sshUser'] + '@' + gearman_worker.collection_system_transfer['sshServer'] + ':' + gearman_worker.source_dir + '/']

    if not is_darwin:
        command.insert(2, '--protect-args')

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1':
        command.insert(2, '--remove-source-files')

    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

    logging.debug("Command: %s", ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines(): # pylint: disable=too-many-nested-blocks
        logging.debug('line: %s', line.rstrip('\n'))
        file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)
        if file_or_dir.startswith('-'):
            exclude = False
            ignore = False
            include = False

            file_mod_time = datetime.strptime(mdate + ' ' + mtime, "%Y/%m/%d %H:%M:%S")
            file_mod_time_seconds = (file_mod_time - epoch).total_seconds()
            logging.debug("file_mod_time_seconds: %s", file_mod_time_seconds)
            if file_mod_time_seconds < data_start_time or file_mod_time_seconds >data_end_time: # pylint: disable=chained-comparison
                logging.debug("%s ignored for time reasons", filepath)
                ignore = True
                continue

            for ignore_filter in filters['ignoreFilter'].split(','):
                if fnmatch.fnmatch(filepath, ignore_filter):
                    logging.debug("%s ignored because file matched ignore filter", filepath)
                    ignore = True
                    break

            if ignore:
                continue

            if not is_ascii(filepath):
                logging.debug("%s is not an ascii-encoded unicode string", filepath)
                return_files['exclude'].append(filepath)
                exclude = True
                continue

            for include_filter in filters['includeFilter'].split(','):
                if fnmatch.fnmatch(filepath, include_filter):
                    for exclude_filter in filters['excludeFilter'].split(','):
                        if fnmatch.fnmatch(filepath, exclude_filter):
                            logging.debug("%s excluded because file matches exclude filter", filepath)
                            return_files['exclude'].append(filepath)
                            exclude = True
                            break

                    if exclude:
                        break

                    logging.debug("%s is a valid file for transfer", filepath)
                    include = True
                    break

            if include:
                return_files['include'].append(filepath)
                return_files['filesize'].append(size)

            elif not ignore and not exclude:
                logging.debug("%s excluded because file does not match any include or ignore filters", filepath)
                return_files['exclude'].append(filepath)

    if not gearman_worker.collection_system_transfer['staleness'] == '0':
        logging.debug("Checking for changing filesizes")
        time.sleep(int(gearman_worker.collection_system_transfer['staleness']))
        proc = subprocess.run(command, capture_output=True, text=True, check=False)

        for line in proc.stdout.splitlines():
            file_or_dir, size, mdate, mtime, filepath = line.split(None, 4)

            try:
                younger_file_idx = return_files['include'].index(filepath)
                if return_files['filesize'][younger_file_idx] != size:
                    logging.debug("file %s has changed size, removing from include list", filepath)
                    del return_files['filesize'][younger_file_idx]
                    del return_files['include'][younger_file_idx]
            except ValueError:
                pass
            except Exception as err:
                logging.error(str(err))

    del return_files['filesize']

    return_files['include'] = [filename.split(gearman_worker.source_dir + '/',1).pop() for filename in return_files['include']]
    return_files['exclude'] = [filename.split(gearman_worker.source_dir + '/',1).pop() for filename in return_files['exclude']]

    logging.debug('return_files: %s', json.dumps(return_files, indent=2))

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
    logging.debug(json.dumps(filters, indent=2))

    return filters


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

    file_index = 0
    new_files = []
    updated_files = []

    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while proc.poll() is None:

        for line in proc.stdout:
            if gearman_worker.stop:
                logging.debug("Stopping")
                proc.terminate()
                break

            if not line:
                continue

            logging.debug("%s", line)

            if line.startswith( '>f+++++++++' ):
                filename = line.split(' ',1)[1]
                new_files.append(filename.rstrip('\n'))
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1
            elif line.startswith( '>f.' ):
                filename = line.split(' ',1)[1]
                updated_files.append(filename.rstrip('\n'))
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1

    return new_files, updated_files


def delete_from_dest(gearman_worker, gearman_job, include_files):
    deleted_files = []

    for filename in os.listdir(gearman_worker.dest_dir):
        full_path = os.path.join(gearman_worker.dest_dir, filename)
        if os.path.isfile(full_path) and filename not in include_files:
            print(f"🗑 Deleting: {filename}")
            os.remove(full_path)
            deleted_files.append(filename)

    return deleted_files

def transfer_local_source_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Preform a collection system transfer from a local directory
    """

    logging.debug("Transfer from Local Directory")

    logging.debug("Source Dir: %s", gearman_worker.source_dir)
    logging.debug("Destination Dir: %s", gearman_worker.dest_dir)

    logging.debug("Build file list")
    output_results = build_filelist(gearman_worker)
    if not output_results['verdict']:
        return { 'verdict': False, 'reason': "Error building filelist", 'files':[] }
    files = output_results['files']

    logging.debug("Files: %s", json.dumps(files['include'], indent=2))

    # Create temp directory
    tmpdir = tempfile.mkdtemp()
    rsync_filelist_filepath = os.path.join(tmpdir, 'rsyncFileList.txt')

    logging.debug("Mod file list")
    local_transfer_filelist = files['include']
    local_transfer_filelist = [filename.replace(gearman_worker.source_dir, '', 1) for filename in local_transfer_filelist]

    logging.debug("Start")
    try:
        with open(rsync_filelist_filepath, mode='w', encoding='utf-8') as rsync_filelist_file:
            for file in local_transfer_filelist:
                try:
                    rsync_filelist_file.write(str(file) + '\n')
                except Exception as err:
                    logging.warning("File not ascii: %s", file)
                    logging.debug(str(err))
            rsync_filelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file %s", rsync_filelist_filepath)

        # Cleanup
        shutil.rmtree(tmpdir)
        return {'verdict': False, 'reason': 'Error Saving temporary rsync filelist file: ' + rsync_filelist_filepath, 'files': []}

    logging.debug("Done")

    command = ['rsync', '-tri', '--files-from=' + rsync_filelist_filepath, gearman_worker.source_dir + '/', gearman_worker.dest_dir]

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

    logging.debug("File List: %s", json.dumps(files['include'], indent=2))

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

    command = ['rsync', '-tri', '--files-from=' + rsync_filelist_filepath,  os.path.join(mntpoint, gearman_worker.source_dir, ''), os.path.join(gearman_worker.dest_dir, '')]

    if gearman_worker.collection_system_transfer['bandwidthLimit'] != '0':
        command.insert(2, f'--bwlimit={gearman_worker.collection_system_transfer["bandwidthLimit"]}')

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.collection_system_transfer['removeSourceFiles'] == '1':
        command.insert(2, '--remove-source-files')

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    if gearman_worker.collection_system_transfer['syncFromSource'] == '1':
        files['deleted'] = delete_from_dest(gearman_worker, gearman_job, files['include'])

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

    logging.debug("Build file list")
    output_results = build_rsync_filelist(gearman_worker)

    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason'], 'files':[]}

    files = output_results['files']

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

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

    if gearman_worker.collection_system_transfer['bandwidthLimit'] != '0':
        command.insert(2, f'--bwlimit={gearman_worker.collection_system_transfer["bandwidthLimit"]}')

    if gearman_worker.collection_system_transfer['syncFromSource'] == '1':
        command.insert(2, '--delete')

    if gearman_worker.collection_system_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.collection_system_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

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

    logging.debug("Build file list")
    output_results = build_ssh_filelist(gearman_worker)
    if not output_results['verdict']:
        return {'verdict': False, 'reason': output_results['reason'], 'files':[]}

    files = output_results['files']

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

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

    if gearman_worker.collection_system_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.collection_system_transfer['sshPass']] + command

    files['new'], files['updated'] = run_transfer_command(gearman_worker, gearman_job, command, len(files['include']))

    # Cleanup
    shutil.rmtree(tmpdir)

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
            logging.debug(str(err))
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

        if results_obj['files']['new'] or results_obj['files']['updated'] or results_obj['files']['deleted']:

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

            if 'deleted' in results_obj['files']:
                # job_data['files']['deleted'] = [
                #     os.path.join(self.collection_system_transfer['destDir'], filepath).lstrip('/')
                #     for filepath in results_obj['files']['deleted']
                # ]

                job_data['files']['deleted'] = [
                    os.path.normpath(os.path.join(self.collection_system_transfer['destDir'], filepath))
                    for filepath in results_obj['files']['deleted']
                ]

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
        output_results = transfer_local_source_dir(gearman_worker, current_job)
    elif  gearman_worker.collection_system_transfer['transferType'] == "2": # Rsync Server
        output_results = transfer_rsync_source_dir(gearman_worker, current_job)
    elif  gearman_worker.collection_system_transfer['transferType'] == "3": # SMB Server
        output_results = transfer_smb_source_dir(gearman_worker, current_job)
    elif  gearman_worker.collection_system_transfer['transferType'] == "4": # SSH Server
        output_results = transfer_ssh_source_dir(gearman_worker, current_job)
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

    if 'delete' in job_results['files'] and len(job_results['files']['deleted']) > 0:
        logging.warning("%s file(s) deleted", len(job_results['files']['deleted']))

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
