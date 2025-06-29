#!/usr/bin/env python3
"""Utilities for processing files and filenames.
"""

import os
import re
import time
import fnmatch
import logging
import errno
import json
from pwd import getpwnam
from datetime import timedelta

rsync_partial_file_re = re.compile(r'(^\..+\.[\w]{6}$)')

def is_ascii(s):
    """Check if the characters in string s are in ASCII, U+0-U+7F."""

    try:
        s.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def is_rsync_patial_file(filename):
    """
    check to see if the filename is a rsync partial file.
    """

    # file_match = False if re.match(rsync_partial_file_re, filename) is None else True
    file_match = re.match(rsync_partial_file_re, filename) is not None

    if file_match:
        logging.warning("Ignoring %s, this is an rsync partial file", filename)

    return file_match


def delete_from_dest(dest_dir, include_files):
    deleted_files = []

    for root, _, files in os.walk(dest_dir):
        for filename in files:
            logging.warning('filename %s', filename)
            if filename in include_files:
                continue

            full_path = os.path.join(root, filename)
            logging.warning('Delete: %s', full_path)

            try:
                os.remove(full_path)
                deleted_files.append(full_path)
                logging.info("Deleted: %s", full_path)
            except FileNotFoundError:
                logging.error("File not found: %s", full_path)
            except PermissionError:
                logging.error("Insufficient permission to delete file: %s", full_path)
            except OSError as e:
                logging.error("OS error deleting file %s: %s", full_path, str(e))

    return deleted_files

    # for filename in os.listdir(dest_dir):
    #     full_path = os.path.join(dest_dir, filename)
    #     logging.warning('delete: %s', full_path)
    #     if os.path.isfile(full_path) and filename not in include_files:
    #         logging.info("Deleting: %s", filename)
    #         try:
    #             os.remove(full_path)
    #             deleted_files.append(filename)
    #         except FileNotFoundError:
    #             logging.error("File to delete not found: %s", filename)
    #         except PermissionError:
    #             logging.error("Insufficent permission to delete file: %s", filename)
    #         except OSError as e:
    #             logging.error("OS error occurred while deleting file: %s --> %s", filename, str(e))

    # return deleted_files


def purge_old_files(directory_path, excludes=None, timedelta_str=None, recursive=False):
    '''
    purge files older than the given deltatime-formatted threshold
    '''

    timedelta_str = timedelta_str or "12 hours"

    def _parse_timedelta(timedelta_str):
        '''
        parse a timedelta-style string and return a timedelta object
        '''
        time_parts = timedelta_str.split()
        time_args = {}

        i = 0
        while i < len(time_parts):
            value = int(time_parts[i])
            unit = time_parts[i + 1].lower()

            if 'day' in unit:
                time_args['days'] = value
            elif 'hour' in unit:
                time_args['hours'] = value
            elif 'minute' in unit:
                time_args['minutes'] = value
            elif 'second' in unit:
                time_args['seconds'] = value

            i += 2

        if not time_args:
            raise ValueError('Invalid timedelta string specified: %s', timedelta_str)

        return timedelta(**time_args)

    def _purge_files(directory_path, excludes, total_seconds, recursive):
        # Iterate over all files in the directory
        for filename in os.listdir(directory_path):
            filepath = os.path.join(directory_path, filename)

            # handle excludes
            skip = False
            if excludes is not None:
                for exclude in excludes.split(','):
                    if fnmatch.fnmatch(filepath, exclude):
                        logging.debug("%s excluded by exclude filter", filepath)
                        skip = True
                        break

            if skip:
                continue

            # Process files
            if os.path.os.path.isfile(filepath):
                # Check the file's last modification time
                file_mod_time = os.path.getmtime(filepath)

                # If the file is older than the specified time delta, delete it
                if current_time - file_mod_time > total_seconds:
                    try:
                        os.remove(filepath)
                        logging.info("Deleted: %s", filepath)
                    except Exception as exc:
                        logging.error("Error deleting %s: %s", filepath, exc)

            # Process directories
            if os.path.isdir(filepath):
                if not recursive:
                    continue

                _purge_files(filepath, excludes, total_seconds, recursive)

    # Parse the time delta string into a timedelta object
    try:
        # Convert the time delta string to a timedelta object
        time_delta = _parse_timedelta(timedelta_str)
    except ValueError as exc:
        logging.error("Error parsing time delta string: %s", exc)
        raise exc

    # Get the current time
    current_time = time.time()

    _purge_files(directory_path, excludes, time_delta.total_seconds(), recursive)


def output_json_data_to_file(file_path, contents):
    """
    Write contents to the specified file_path.  Assumes contents is a json
    string-able object
    """

    try:
        os.makedirs(os.path.dirname(file_path))
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            logging.error("Unable to create parent directory for data file")
            return {'verdict': False, 'reason': f'Unable to create parent directory(ies) for data file: {file_path}'}
    except Exception as err:
        raise err

    with open(file_path, mode='w', encoding="utf-8") as json_file:
        logging.debug("Saving JSON file: %s", file_path)
        try:
            json.dump(contents, json_file, indent=4)

        except IOError:
            logging.error("Error Saving JSON file: %s", file_path)
            return {'verdict': False, 'reason': f'Unable to create data file: {file_path}'}

    return {'verdict': True}


def set_owner_group_permissions(user, path):
    """
    Recursively set the ownership and permissions for the files and sub-
    directories for the given path.
    """

    reasons = []

    uid = getpwnam(user).pw_uid
    gid = getpwnam(user).pw_gid
    # Set the file permission and ownership for the current directory

    logging.debug("Setting ownership/permissions for %s", path)
    if os.path.isfile(path):
        try:
            os.chown(path, uid, gid)
            os.chmod(path, 0o644)
        except OSError:
            logging.debug("Unable to set ownership/permissions for /%s", path)
            reasons.append(f"Unable to set ownership/permissions for /{path}")

    else: #directory
        try:
            os.chown(path, uid, gid)
            os.chmod(path, 0o755)
        except OSError:
            logging.debug("Unable to set ownership/permissions for /%s", path)
            reasons.append(f"Unable to set ownership/permissions for /{path}")

        for root, dirs, files in os.walk(path):
            for file in files:
                fname = os.path.join(root, file)
                logging.debug("Setting ownership/permissions for %s", fname)
                try:
                    os.chown(fname, uid, gid)
                    os.chmod(fname, 0o644)
                except OSError:
                    logging.debug("Unable to set ownership/permissions for %s", fname)
                    reasons.append(f"Unable to set ownership/permissions for {fname}")

            for directory in dirs:
                dname = os.path.join(root, directory)
                logging.debug("Setting ownership/permissions for %s", dname)
                try:
                    os.chown(dname, uid, gid)
                    os.chmod(dname, 0o755)
                except OSError:
                    logging.debug("Unable to set ownership/permissions for %s", dname)
                    reasons.append(f"Unable to set ownership/permissions for {dname}")

    if len(reasons) > 0:
        logging.error("Unable to set ownership/permissions for %s file", len(reasons))
        return {'verdict': False, 'reason': f"Unable to set ownership/permissions for {len(reasons)} file"}

    return {'verdict': True}


def create_directories(directorylist):
    """
    Create the directories in the provide directory list
    """

    reasons = []
    for directory in directorylist:
        try:
            os.makedirs(directory)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                logging.error("Unable to create directory: %s", directory)
                reasons.append("Unable to create directory: %s", directory)

    if len(reasons) > 0:
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    return {'verdict': True}


def lockdown_directory(base_dir, exempt_dir):
    """
    Lockdown permissions on the base directory, skip the exempt directory if present
    """

    dir_contents = [ os.path.join(base_dir,f) for f in os.listdir(base_dir)]
    files = filter(os.path.isfile, dir_contents)
    for file in files:
        os.chmod(file, 0o600)

    directories = filter(os.path.isdir, dir_contents)
    for directory in directories:
        if not directory == exempt_dir:
            os.chmod(directory, 0o700)


def verfy_write_access(dest_dir):
    """
    Verify the current user has write permissions to the dest_dir
    """

    try:
        test_file = os.path.join(dest_dir, 'writeTest.txt')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("This file tests if the directory can be written to.")
        os.remove(test_file)
        logging.info("Write test passed for %s", dest_dir)
        return True
    except Exception:
        logging.exception("Write test failed for %s", dest_dir)
        return False
