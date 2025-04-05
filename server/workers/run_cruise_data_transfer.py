#!/usr/bin/env python3
"""
FILE:  run_cruise_data_transfer.py

DESCRIPTION:  Gearman worker that handles the transfer of all cruise data from
    the Shipboard Data Warehouse to a second location.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.9
  CREATED:  2015-01-01
 REVISION:  2022-07-24
"""

import argparse
import fnmatch
import json
import logging
import os
import sys
import shutil
import signal
import subprocess
import tempfile
import time
from os.path import dirname, realpath
from random import randint
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import is_ascii, is_rsync_patial_file
from server.lib.set_owner_group_permissions import set_owner_group_permissions
from server.lib.openvdm import OpenVDM


def build_filelist(gearman_worker, source_dir): # pylint: disable=too-many-branches
    """
    Build list of files to transfer
    """

    return_files = {'include':[], 'exclude':[], 'new':[], 'updated':[]}

    filters = build_filters(gearman_worker)

    for root, _, filenames in os.walk(source_dir): # pylint: disable=too-many-nested-blocks
        for filename in filenames:

            # do not include rsync partial files.
            if is_rsync_patial_file(filename):
                continue

            filepath = os.path.join(root, filename)

            if os.path.islink(filepath):
                logging.debug("%s is a symlink, skipping", filename)
                continue

            exclude = False
            ignore = False
            for ignore_filter in filters['ignoreFilter'].split(','):
                #logging.debug(filt)
                if fnmatch.fnmatch(filepath, ignore_filter):
                    logging.debug("%s ignored by ignore filter", filename)
                    ignore = True
                    break
            if not ignore:
                for include_filter in filters['includeFilter'].split(','):
                    if fnmatch.fnmatch(filepath, include_filter):
                        for exclude_filter in filters['excludeFilter'].split(','):
                            if fnmatch.fnmatch(filepath, exclude_filter):
                                logging.debug("%s excluded by exclude filter", filename)
                                return_files['exclude'].append(filepath)
                                exclude = True
                                break
                        if not exclude and not is_ascii(filepath):
                            logging.debug("%s is not an ascii-encoded unicode string", filename)
                            return_files['exclude'].append(filepath)
                            exclude = True
                            break

                        if exclude:
                            break

                if not exclude:
                    logging.debug("%s is a valid file for transfer", filepath)
                    return_files['include'].append(filepath)

    return_files['include'] = [filename.split(source_dir + '/',1).pop() for filename in return_files['include']]
    return_files['exclude'] = [filename.split(source_dir + '/',1).pop().replace("[", "\[").replace("]", "\]") for filename in return_files['exclude']]

    logging.debug("file list: %s", json.dumps(return_files, indent=2))

    return return_files

def build_filters(gearman_worker):
    """
    Build filters for the transfer
    """

    return {
        'includeFilter': '*',
        'excludeFilter': ','.join(build_exclude_filterlist(gearman_worker)),
        'ignoreFilter': ''
    }


def build_exclude_filterlist(gearman_worker):
    """
    Build exclude filter for the transfer
    """

    exclude_filterlist = []

    if gearman_worker.cruise_data_transfer['includeOVDMFiles'] == '0':
        exclude_filterlist.append(f"*{gearman_worker.shipboard_data_warehouse_config['cruiseConfigFn']}")
        exclude_filterlist.append(f"*{gearman_worker.shipboard_data_warehouse_config['md5SummaryFn']}")
        exclude_filterlist.append(f"*{gearman_worker.shipboard_data_warehouse_config['md5SummaryMd5Fn']}")

        # TODO - exclude the lowering.json files for each of the lowerings

    excluded_collection_system_ids = gearman_worker.cruise_data_transfer['excludedCollectionSystems'].split(',') if gearman_worker.cruise_data_transfer['excludedCollectionSystems'] != '' else []
    for collection_system_id in excluded_collection_system_ids:

        if collection_system_id == '0':
            continue

        collection_system_transfer = gearman_worker.ovdm.get_collection_system_transfer(collection_system_id)

        try:
            if collection_system_transfer['cruiseOrLowering'] == '0':
                exclude_filterlist.append(f"*{collection_system_transfer['destDir'].replace('{cruiseID}', gearman_worker.cruise_id)}*")
            else:
                lowerings = gearman_worker.ovdm.get_lowerings()
                for lowering in lowerings:
                    # exclude_filterlist.append("*/{cruiseID}/*/" + lowering + "/" + cruiseDataTransfer['destDir'].replace('{loweringID}', lowering) + "/*")
                    exclude_filterlist.append(f"*{lowering}/{collection_system_transfer['destDir'].replace('{cruiseID}', gearman_worker.cruise_id).replace('{loweringID}', lowering)}*")
        except Exception as err:
            logging.warning("Could not retrieve collection system transfer %s", collection_system_id)
            logging.warning(str(err))

    excluded_extra_directory_ids = gearman_worker.cruise_data_transfer['excludedExtraDirectories'].split(',') if gearman_worker.cruise_data_transfer['excludedExtraDirectories'] != '' else []
    for excluded_extra_directory_id in excluded_extra_directory_ids:

        if excluded_extra_directory_id == '0':
            continue

        extra_directory = gearman_worker.ovdm.get_extra_directory(excluded_extra_directory_id)
        exclude_filterlist.append(f"*{extra_directory['destDir'].replace('{cruiseID}', gearman_worker.cruise_id)}*")

    logging.debug("Exclude filters: %s", json.dumps(exclude_filterlist, indent=2))

    return exclude_filterlist


def run_localfs_transfer_command_to_localfs(gearman_worker, gearman_job, command, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.debug("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.debug('Transfer Command: %s', ' '.join(command))

    # cruise_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)
    # dest_dir = command[-1]

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

            line = line.rstrip('\n')

            if not line:
                continue

            logging.debug("%s", line)

            if line.startswith( '>f+++++++++' ):
                filename = line.split(' ',1)[1]
                new_files.append(filename)
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1
            elif line.startswith( '>f.' ):
                filename = line.split(' ',1)[1]
                updated_files.append(filename)
                logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
                gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
                file_index += 1

    # new_files = [os.path.join(dest_dir.replace(cruise_dir, '').lstrip('/').rstrip('/'), filename) for filename in new_files]
    # updated_files = [os.path.join(dest_dir.replace(cruise_dir, '').lstrip('/').rstrip('/'), filename) for filename in updated_files]

    return new_files, updated_files


def run_localfs_transfer_command_to_remotefs(gearman_worker, gearman_job, command, file_count):
    """
    run the rsync command and return the list of new/updated files
    """

    # if there are no files to transfer, then don't
    if file_count == 0:
        logging.debug("Skipping Transfer Command: nothing to transfer")
        return [], []

    logging.debug("Transfer Command: %s", ' '.join(command))

    file_index = 0
    new_files = []
    updated_files = []

    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    while proc.returncode is None:

        proc.poll()

        if gearman_worker.stop:
            logging.debug("Stopping")
            proc.terminate()
            break

        line = proc.stdout.readline().rstrip('\n')

        if not line:
            continue

        logging.debug("%s", line)

        if line.startswith( '<f+++++++++' ):
            filename = line.split(' ',1)[1]
            new_files.append(filename)
            logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
            gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
            file_index += 1
        elif line.startswith( '<f.' ):
            filename = line.split(' ',1)[1]
            updated_files.append(filename)
            logging.info("Progress Update: %d%%", int(100 * (file_index + 1)/file_count))
            gearman_worker.send_job_status(gearman_job, int(20 + 70*float(file_index)/float(file_count)), 100)
            file_index += 1

    return new_files, updated_files


def transfer_local_dest_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Copy cruise data to a local directory
    """

    logging.debug("Transfer to Local Directory")

    cruise_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)
    dest_dir = gearman_worker.cruise_data_transfer['destDir'].rstrip('/')

    logging.debug('Destination Dir: %s', dest_dir)

    logging.debug("Building file list")
    files = build_filelist(gearman_worker, cruise_dir)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()
    rsync_exclude_list_filepath = os.path.join(tmpdir, 'rsyncExcludeList.txt')

    try:
        with open(rsync_exclude_list_filepath, mode='w', encoding="utf-8") as rsync_excludelist_file:
            rsync_excludelist_file.write('\n'.join(files['exclude']))
            rsync_excludelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file")

        # Cleanup
        logging.debug("delete tmp dir: %s", tmpdir)
        shutil.rmtree(tmpdir)
        return False

    file_count = 0
    command = ['rsync', '-trinv', '--stats', '--exclude-from=' + rsync_exclude_list_filepath, cruise_dir, dest_dir]

    if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')


    logging.debug('File count Command: %s', ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        logging.debug("%s", line)
        if line.startswith('Number of regular files transferred:'):
            file_count = int(line.split(':')[1].replace(',',''))
            logging.info("File Count: %d", file_count)
            break

    output_results = None
    if file_count == 0:
        logging.debug("Nothing to tranfser")

    else:

        command = ['rsync', '-triv', '--exclude-from=' + rsync_exclude_list_filepath, cruise_dir, dest_dir]

        if gearman_worker.cruise_data_transfer['bandwidthLimit'] != '0':
            command.insert(2, f'--bwlimit={gearman_worker.cruise_data_transfer["bandwidthLimit"]}')

        if gearman_worker.cruise_data_transfer['syncToDest'] == '1':
            command.insert(2, '--delete')

        if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
            command.insert(2, '--min-size=1')

        if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
            command.insert(2, '-m')

        files['new'], files['updated'] = run_localfs_transfer_command_to_localfs(gearman_worker, gearman_job, command, file_count)

        if gearman_worker.cruise_data_transfer['localDirIsMountPoint'] == '1':
            output_results = { 'verdict': True }
        else:
            logging.info("Setting file permissions")
            output_results = set_owner_group_permissions(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], os.path.join(dest_dir, gearman_worker.cruise_id))

    # Cleanup
    logging.debug("delete tmp dir: %s", tmpdir)
    shutil.rmtree(tmpdir)

    logging.debug("output_results: %s", output_results)

    if output_results is not None and not output_results['verdict']:
        logging.error("Error setting ownership/permissions for cruise data at destination: %s", os.path.join(dest_dir, gearman_worker.cruise_id))
        return output_results

    return { 'verdict': True, 'files': files }


def transfer_smb_dest_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Copy cruise data to a samba server
    """

    logging.debug("Transfer to SMB Source")

    cruise_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)

    logging.debug("Building file list")
    files = build_filelist(gearman_worker, cruise_dir)

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    # Create mountpoint
    mntpoint = os.path.join(tmpdir, 'mntpoint')
    os.mkdir(mntpoint, 0o755)

    # Mount SMB Share
    logging.debug("Mounting SMB Share")

    ver_test_command = ['smbclient', '-L', gearman_worker.cruise_data_transfer['smbServer'], '-W', gearman_worker.cruise_data_transfer['smbDomain'], '-m', 'SMB2', '-g', '-N'] if gearman_worker.cruise_data_transfer['smbUser'] == 'guest' else ['smbclient', '-L', gearman_worker.cruise_data_transfer['smbServer'], '-W', gearman_worker.cruise_data_transfer['smbDomain'], '-m', 'SMB2', '-g', '-U', gearman_worker.cruise_data_transfer['smbUser'] + '%' + gearman_worker.cruise_data_transfer['smbPass']]
    logging.debug("SMB version test command: %s", ' '.join(ver_test_command))

    vers="2.1"
    proc = subprocess.run(ver_test_command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('OS=[Windows 5.1]'):
            vers="1.0"
            break

    mount_command = ['sudo', 'mount', '-t', 'cifs', gearman_worker.cruise_data_transfer['smbServer'], mntpoint, '-o', 'rw' + ',guest' + ',domain=' + gearman_worker.cruise_data_transfer['smbDomain'] + ',vers=' + vers] if gearman_worker.cruise_data_transfer['smbUser'] == 'guest' else ['sudo', 'mount', '-t', 'cifs', gearman_worker.cruise_data_transfer['smbServer'], mntpoint, '-o', 'rw' + ',username=' + gearman_worker.cruise_data_transfer['smbUser'] + ',password=' + gearman_worker.cruise_data_transfer['smbPass'] + ',domain=' + gearman_worker.cruise_data_transfer['smbDomain'] + ',vers=' + vers]
    logging.debug("Mount command: %s", ' '.join(mount_command))

    subprocess.run(mount_command, capture_output=True, text=True, check=False)

    rsync_exclude_list_filepath = os.path.join(tmpdir, 'rsyncExcludeList.txt')

    try:
        with open(rsync_exclude_list_filepath, mode='w', encoding='utf-8') as rsync_excludelist_file:
            rsync_excludelist_file.write('\n'.join(files['exclude']))
            rsync_excludelist_file.write('\0')

        logging.debug('\n'.join(files['exclude']))
    except IOError:
        logging.error("Error Saving temporary rsync filelist file")

        # Cleanup
        logging.debug("delete tmp dir: %s", tmpdir)
        shutil.rmtree(tmpdir)
        return False

    file_count = 0
    command = ['rsync', '-trinv', '--stats', '--exclude-from=' + rsync_exclude_list_filepath, cruise_dir, os.path.join(mntpoint, gearman_worker.cruise_data_transfer['destDir']).rstrip('/') if gearman_worker.cruise_data_transfer['destDir'] != '/' else mntpoint]

    if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    logging.debug('File count Command: %s', ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('Number of regular files transferred:'):
            file_count = int(line.split(':')[1].replace(',',''))
            logging.info("File Count: %d", file_count)
            break

    if file_count == 0:
        logging.debug("Nothing to tranfser")

    else:

        command = ['rsync', '-triv', '--exclude-from=' + rsync_exclude_list_filepath, cruise_dir, os.path.join(mntpoint, gearman_worker.cruise_data_transfer['destDir']).rstrip('/') if gearman_worker.cruise_data_transfer['destDir'] != '/' else mntpoint]

        if gearman_worker.cruise_data_transfer['bandwidthLimit'] != '0':
            command.insert(2, f'--bwlimit={gearman_worker.cruise_data_transfer["bandwidthLimit"]}')

        if gearman_worker.cruise_data_transfer['syncToDest'] == '1':
            command.insert(2, '--delete')

        if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
            command.insert(2, '--min-size=1')

        if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
            command.insert(2, '-m')

        files['new'], files['updated'] = run_localfs_transfer_command_to_localfs(gearman_worker, gearman_job, command, file_count)

    # Cleanup
    time.sleep(2)

    logging.debug("Unmount SMB Share")
    subprocess.call(['umount', mntpoint])
    logging.debug("delete tmp dir: %s", tmpdir)
    shutil.rmtree(tmpdir)

    return { 'verdict': True, 'files': files }


def transfer_rsync_dest_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals,too-many-statements
    """
    Copy cruise data to a rsync server
    """

    logging.debug("Transfer to RSYNC Server")

    cruise_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)

    logging.debug("Building file list")
    files = build_filelist(gearman_worker, cruise_dir)

    dest_dir = gearman_worker.cruise_data_transfer['destDir'].rstrip('/')

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    rsync_password_filepath = os.path.join(tmpdir, 'passwordFile')

    try:
        with open(rsync_password_filepath, mode='w', encoding='utf-8') as rsync_password_file:
            rsync_password_file.write(gearman_worker.cruise_data_transfer['rsyncPass'])

        os.chmod(rsync_password_filepath, 0o600)

    except IOError:
        logging.error("Error Saving temporary rsync password file")
        rsync_password_file.close()

        # Cleanup
        logging.debug("delete tmp dir: %s", tmpdir)
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': 'Error Saving temporary rsync password file: ' + rsync_password_filepath}

    rsync_exclude_list_filepath = os.path.join(tmpdir, 'rsyncExcludeList.txt')

    # Create temp directory
    tmpdir = tempfile.mkdtemp()
    rsync_exclude_list_filepath = os.path.join(tmpdir, 'rsyncExcludeList.txt')

    try:
        with open(rsync_exclude_list_filepath, mode='w', encoding="utf-8") as rsync_excludelist_file:
            rsync_excludelist_file.write('\n'.join(files['exclude']))
            rsync_excludelist_file.write('\0')

    except IOError:
        logging.error("Error Saving temporary rsync filelist file")

        # Cleanup
        logging.debug("delete tmp dir: %s", tmpdir)
        shutil.rmtree(tmpdir)
        return False

    file_count = 0
    command = ['rsync', '-trinv', '--stats', '--exclude-from=' + rsync_exclude_list_filepath, '--password-file=' + rsync_password_filepath, cruise_dir, 'rsync://' + gearman_worker.cruise_data_transfer['rsyncUser'] + '@' + gearman_worker.cruise_data_transfer['rsyncServer'] + dest_dir + '/']

    if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    logging.debug('File count Command: %s', ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        if line.startswith('Number of regular files transferred:'):
            file_count = int(line.split(':')[1].replace(',',''))
            logging.info("File Count: %d", file_count)
            break

    if file_count == 0:
        logging.debug("Nothing to tranfser")

    else:

        command = ['rsync', '-triv', '--no-motd', '--exclude-from=' + rsync_exclude_list_filepath, '--password-file=' + rsync_password_filepath, cruise_dir, 'rsync://' + gearman_worker.cruise_data_transfer['rsyncUser'] + '@' + gearman_worker.cruise_data_transfer['rsyncServer'] + dest_dir + '/']

        if gearman_worker.cruise_data_transfer['bandwidthLimit'] != '0':
            command.insert(2, f'--bwlimit={gearman_worker.cruise_data_transfer["bandwidthLimit"]}')

        if gearman_worker.cruise_data_transfer['syncToDest'] == '1':
            command.insert(2, '--delete')

        if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
            command.insert(2, '--min-size=1')

        if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
            command.insert(2, '-m')

        files['new'], files['updated'] = run_localfs_transfer_command_to_remotefs(gearman_worker, gearman_job, command, file_count)


    # Cleanup
    logging.debug("delete tmp dir: %s", tmpdir)
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}


def transfer_ssh_dest_dir(gearman_worker, gearman_job): # pylint: disable=too-many-locals
    """
    Copy cruise data to a ssh server
    """

    logging.debug("Transfer to SSH Server")

    cruise_dir = os.path.join(gearman_worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], gearman_worker.cruise_id)

    logging.debug("Building file list")
    files = build_filelist(gearman_worker, cruise_dir)

    dest_dir = gearman_worker.cruise_data_transfer['destDir'].rstrip('/')

    # Create temp directory
    tmpdir = tempfile.mkdtemp()

    ssh_excludelist_filepath = os.path.join(tmpdir, 'sshExcludeList.txt')

    try:
        with open(ssh_excludelist_filepath, mode='w', encoding='utf-8') as ssh_excludelist_file:
            ssh_excludelist_file.write('\n'.join(files['exclude']))
            ssh_excludelist_file.write('\0')

    except IOError:
        logging.debug("Error Saving temporary ssh exclude filelist file")

        # Cleanup
        logging.debug("delete tmp dir: %s", tmpdir)
        shutil.rmtree(tmpdir)

        return {'verdict': False, 'reason': f'Error Saving temporary ssh exclude filelist file: {ssh_excludelist_filepath}', 'files':[]}

    file_count = 0
    command = ['rsync', '-trinv', '--stats', '--exclude-from=' + ssh_excludelist_filepath, '-e', 'ssh', cruise_dir, gearman_worker.cruise_data_transfer['sshUser'] + '@' + gearman_worker.cruise_data_transfer['sshServer'] + ':' + dest_dir]

    if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
        command.insert(2, '--min-size=1')

    if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
        command.insert(2, '-m')

    if gearman_worker.cruise_data_transfer['sshUseKey'] == '0':
        command = ['sshpass', '-p', gearman_worker.cruise_data_transfer['sshPass']] + command

    logging.debug('File count Command: %s', ' '.join(command))

    proc = subprocess.run(command, capture_output=True, text=True, check=False)

    for line in proc.stdout.splitlines():
        logging.debug("%s", line)
        if line.startswith('Number of regular files transferred:'):
            file_count = int(line.split(':')[1].replace(',',''))
            logging.info("File Count: %d", file_count)
            break

    if file_count == 0:
        logging.debug("Nothing to tranfser")

    else:

        command = ['rsync', '-triv', '--exclude-from=' + ssh_excludelist_filepath, '-e', 'ssh', cruise_dir, gearman_worker.cruise_data_transfer['sshUser'] + '@' + gearman_worker.cruise_data_transfer['sshServer'] + ':' + dest_dir]

        if gearman_worker.cruise_data_transfer['bandwidthLimit'] != '0':
            command.insert(2, f'--bwlimit={gearman_worker.cruise_data_transfer["bandwidthLimit"]}')

        if gearman_worker.cruise_data_transfer['syncToDest'] == '1':
            command.insert(2, '--delete')

        if gearman_worker.cruise_data_transfer['skipEmptyFiles'] == '1':
            command.insert(2, '--min-size=1')

        if gearman_worker.cruise_data_transfer['skipEmptyDirs'] == '1':
            command.insert(2, '-m')

        if gearman_worker.cruise_data_transfer['sshUseKey'] == '0':
            command = ['sshpass', '-p', gearman_worker.cruise_data_transfer['sshPass']] + command

        files['new'], files['updated'] = run_localfs_transfer_command_to_remotefs(gearman_worker, gearman_job, command, file_count)


    # Cleanup
    logging.debug("delete tmp dir: %s", tmpdir)
    shutil.rmtree(tmpdir)

    return {'verdict': True, 'files': files}


class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """
    Class for the current Gearman worker
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.system_status = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def on_job_execute(self, current_job):
        """
        Function run whenever a new job arrives
        """

        logging.debug("current_job: %s", current_job)

        self.stop = False
        payload_obj = json.loads(current_job.data)

        try:
            self.cruise_data_transfer = self.ovdm.get_cruise_data_transfer(payload_obj['cruiseDataTransfer']['cruiseDataTransferID'])

            logging.info("cruiseDataTransfer configuration: \n%s", json.dumps(self.cruise_data_transfer, indent=2))

            if not self.cruise_data_transfer: # doesn't exist
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Cruise Data Tranfer Data", "result": "Fail", "reason": "Could not find configuration data for cruise data transfer"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

            if self.cruise_data_transfer['status'] == "1": # running
                logging.info("Transfer job for %s skipped because a transfer for that cruise data destination is already in-progress", self.cruise_data_transfer['name'])
                return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer In-Progress", "result": "Ignore", "reason": "Transfer is already in-progress"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        except Exception as err:
            logging.debug(str(err))
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Located Cruise Data Tranfer Data", "result": "Fail", "reason": "Could not find retrieve data for cruise data transfer from OpenVDM API"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        self.system_status = payload_obj['systemStatus'] if 'systemStatus' in payload_obj else self.ovdm.get_system_status()
        self.cruise_data_transfer.update(payload_obj['cruiseDataTransfer'])

        if self.system_status == "Off" or self.cruise_data_transfer['enable'] == '0':
            logging.info("Transfer job for %s skipped because that cruise data transfer is currently disabled", self.cruise_data_transfer['name'])
            return self.on_job_complete(current_job, json.dumps({'parts':[{"partName": "Transfer Enabled", "result": "Ignore", "reason": "Transfer is disabled"}], 'files':{'new':[],'updated':[], 'exclude':[]}}))

        self.cruise_id = payload_obj['cruiseID'] if 'cruiseID' in payload_obj else self.ovdm.get_cruise_id()

        logging.info("Job: %s, %s transfer started at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run whenever the current job has an exception
        """

        logging.error("Job: %s, %s transfer failed at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

        self.send_job_data(current_job, json.dumps([{"partName": "Worker crashed", "result": "Fail", "reason": "Unknown"}]))
        self.ovdm.set_error_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'], 'Worker crashed')

        exc_type, _, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(exc_type, fname, exc_tb.tb_lineno)
        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """
        Function run whenever the current job completes
        """

        results_obj = json.loads(job_result)

        if len(results_obj['parts']) > 0:
            if results_obj['parts'][-1]['result'] == "Fail" and results_obj['parts'][-1]['partName'] != "Located Cruise Data Tranfer Data": # Final Verdict
                self.ovdm.set_error_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'], results_obj['parts'][-1]['reason'])
            elif results_obj['parts'][-1]['result'] == "Pass":
                self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])
        else:
            self.ovdm.set_idle_cruise_data_transfer(self.cruise_data_transfer['cruiseDataTransferID'])

        logging.debug("Job Results: %s", json.dumps(results_obj, indent=2))
        logging.info("Job: %s, %s transfer completed at: %s", current_job.handle, self.cruise_data_transfer['name'], time.strftime("%D %T", time.gmtime()))

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


def task_run_cruise_data_transfer(gearman_worker, current_job):
    """
    Run the cruise data transfer
    """

    time.sleep(randint(0,2))

    job_results = {
        'parts': [
            {"partName": "Transfer In-Progress", "result": "Pass"},
            {"partName": "Transfer Enabled", "result": "Pass"}
        ],
        'files':{}
    }

    logging.debug("Setting transfer status to 'Running'")
    gearman_worker.ovdm.set_running_cruise_data_transfer(gearman_worker.cruise_data_transfer['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing configuration")
    gearman_worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([gearman_worker.ovdm.get_gearman_server()])

    gm_data = {
        'cruiseDataTransfer': gearman_worker.cruise_data_transfer,
        'cruiseID': gearman_worker.cruise_id
    }

    completed_job_request = gm_client.submit_job("testCruiseDataTransfer", json.dumps(gm_data))
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

    logging.info("Transferring files")
    output_results = None
    if gearman_worker.cruise_data_transfer['transferType'] == "1": # Local Directory
        output_results = transfer_local_dest_dir(gearman_worker, current_job)
    elif  gearman_worker.cruise_data_transfer['transferType'] == "2": # Rsync Server
        output_results = transfer_rsync_dest_dir(gearman_worker, current_job)
    elif  gearman_worker.cruise_data_transfer['transferType'] == "3": # SMB Server
        output_results = transfer_smb_dest_dir(gearman_worker, current_job)
    elif  gearman_worker.cruise_data_transfer['transferType'] == "4": # SSH Server
        output_results = transfer_ssh_dest_dir(gearman_worker, current_job)
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
        logging.debug("%s file(s) intentionally skipped", len(job_results['files']['exclude']))

    gearman_worker.send_job_status(current_job, 9, 10)

    time.sleep(2)

    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle cruise data transfer related tasks')
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

    logging.info("\tTask: runCruiseDataTransfer")
    new_worker.register_task("runCruiseDataTransfer", task_run_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
