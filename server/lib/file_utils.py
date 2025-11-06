#!/usr/bin/env python3
"""
FILE:  connection_utils.py

DESCRIPTION:  utilities for dealing with local files/directories

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.12
  CREATED:  2025-07-05
 REVISION:  2025-07-07
"""

import os
import json
import time
import fnmatch
import tempfile
import shutil
import logging
import errno
import subprocess
from contextlib import contextmanager
from pwd import getpwnam
from datetime import timedelta
from typing import List, Optional

default_ignore_patterns = [
    "**/@eaDir*",
    "**/.DS_Store",
    "**/._*",
    "**/Thumbs.db",
    "**/desktop.ini",
    "**/.*.??????"
]

def is_ascii(s):
    """
    Check if the characters in string s are in ASCII, U+0-U+7F.
    """

    try:
        s.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False

def expand_patterns(patterns: List[str]) -> List[str]:
    """
    Expand recursive glob patterns (with **/) to also include
    their top-level equivalents (without the **/ prefix).
    """
    expanded = set(patterns)
    for p in patterns:
        if p.startswith("**/"):
            expanded.add(p[3:])  # Add version without **/
    return sorted(expanded)

def is_default_ignore(filepath: str, patterns: Optional[List[str]] = None) -> bool:
    """
    Returns True if the filepath matches any of the provided glob-style patterns.
    """

    filepath = os.path.normpath(filepath)
    patterns = expand_patterns(patterns or default_ignore_patterns)

    return any(fnmatch.fnmatch(filepath, pattern) for pattern in patterns)


def build_filelist(source_dir):
    """
    Builds the list of files in the source directory
    """

    return_files = { 'include':[], 'exclude':[], 'new':[], 'updated':[]}

    for root, _, files in os.walk(source_dir):

        for filename in files:
            fullpath = os.path.join(root, filename)

            if os.path.islink(fullpath):
                continue

            if is_default_ignore(fullpath):
                continue

            rel_path = os.path.relpath(fullpath, source_dir)

            if is_ascii(fullpath):
                return_files['include'].append(rel_path)
            else:
                return_files['exclude'].append(rel_path)

    return return_files


def build_include_file(include_list, filepath):
    """
    Build the rsync files-from include file
    """

    try:
        with open(filepath, mode='w', encoding="utf-8") as f:
            f.write('\n'.join(include_list))
            f.write('\0')
    except IOError as exc:
        logging.error("Error writing include file: %s", str(exc))
        return False

    return True


def clear_directory(target_dir, delete_self=False):
    """
    Deletes all empty sub-directorties within the specified target_dir
    """

    reasons = []

    if not os.path.exists(target_dir):
        reason = f"Directory not found: {target_dir}"
        logging.error(reason)
        return {'verdict': False, 'reason': [reason]}

    try:
        for entry in os.listdir(target_dir):
            path = os.path.join(target_dir, entry)

            try:
                if os.path.islink(path) or os.path.isfile(path):
                    os.remove(path)
                    logging.debug("Deleted file: %s", path)
                elif os.path.isdir(path):
                    # Recurse into subdirectory
                    result = clear_directory(path, delete_self=True)
                    if not result['verdict']:
                        reasons.extend(result['reasons'])
            except OSError as exc:
                reason = f'Failed to delete {path}: {exc}'
                logging.error(reason)
                reasons.append(reason)

        if delete_self:
            try:
                os.rmdir(target_dir)
                logging.debug("Deleted directory: %s", target_dir)
            except OSError as exc:
                reason = f"Failed to delete {target_dir}: {exc}"
                logging.error(reason)
                reasons.append(reason)
    except OSError as exc:
        reason = f"Failed to list contents of {target_dir}: {exc}"
        logging.error(reason)
        reasons.append(reason)

    return {
        'verdict': len(reasons) == 0,
        'reason': reasons
    }


def delete_from_dest(dest_dir, include_files):
    """
    Delete the files in the included_files list from the dest_dir
    """

    deleted_files = []

    for root, _, files in os.walk(dest_dir):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, dest_dir)

            if rel_path not in include_files:
                try:
                    os.remove(full_path)
                    deleted_files.append(rel_path)
                    logging.debug("Deleted file: %s", rel_path)
                except FileNotFoundError:
                    logging.warning("File to be deleted not found: %s", full_path)
                except PermissionError:
                    logging.error("File not deleted due to permission errors: %s", full_path)
                except OSError as exc:
                    logging.error("File not deleted due to OS error: %s, %s", full_path, str(exc))

    for root, dirs, _ in os.walk(dest_dir, topdown=False):
        for d in dirs:
            dir_path = os.path.join(root, d)
            try:
                if not os.listdir(dir_path):  # is empty
                    os.rmdir(dir_path)
                    logging.debug("Deleted directory: %s", dir_path)
            except OSError as exc:
                logging.error("Directory not deleted due to OS error: %s, %s", dir_path, str(exc))

    return deleted_files


def purge_old_files(directory_path, excludes=None, timedelta_str=None, recursive=False):
    """
    purge files older than the given deltatime-formatted threshold
    """

    timedelta_str = timedelta_str or "12 hours"

    def _parse_timedelta(timedelta_str):
        """
        parse a timedelta-style string and return a timedelta object
        """

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
        """
        Remove files older than total_seconds from the directory path with the
        exception of files listed in the excludes list.
        """

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
                        logging.debug("Purged file: %s", filepath)
                    except FileNotFoundError:
                        logging.warning("File to be purged not found: %s", filepath)
                    except PermissionError:
                        logging.error("File not purged due to permission errors: %s", filepath)
                    except OSError as exc:
                        logging.error("File not purged due to OS error: %s, %s", filepath, str(exc))

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
        logging.error("Error parsing time delta string: %s", str(exc))
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
            reason = f'Unable to create parent directory(ies) for data file: {file_path}'
            logging.error(reason)
            return {'verdict': False, 'reason': reason}
    except Exception as exc:
        raise exc

    with open(file_path, mode='w', encoding="utf-8") as json_file:
        logging.debug("Saving JSON file: %s", file_path)
        try:
            json.dump(contents, json_file, indent=4)

        except IOError:
            reason = f'Unable to create data file: {file_path}'
            logging.error(reason)
            return {'verdict': False, 'reason': reason}

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
            reason = f"Unable to set ownership/permissions for /{path}"
            logging.debug(reason)
            reasons.append(reason)

    else: #directory
        try:
            os.chown(path, uid, gid)
            os.chmod(path, 0o755)
        except OSError:
            reason = "Unable to set ownership/permissions for /%s", path
            logging.debug(reason)
            reasons.append(reason)

        for root, dirs, files in os.walk(path):
            for file in files:
                fname = os.path.join(root, file)
                logging.debug("Setting ownership/permissions for %s", fname)
                try:
                    os.chown(fname, uid, gid)
                    os.chmod(fname, 0o644)
                except OSError:
                    reason = f"Unable to set ownership/permissions for {fname}"
                    logging.debug(reason)
                    reasons.append(reason)

            for directory in dirs:
                dname = os.path.join(root, directory)
                logging.debug("Setting ownership/permissions for %s", dname)
                try:
                    os.chown(dname, uid, gid)
                    os.chmod(dname, 0o755)
                except OSError:
                    reason = f"Unable to set ownership/permissions for {dname}"
                    logging.debug(reason)
                    reasons.append(reason)

    if len(reasons) > 0:
        reason = f"Unable to set ownership/permissions for {len(reasons)} file(s)"
        logging.error(reason)
        return {'verdict': False, 'reason': reason}

    return {'verdict': True}


@contextmanager
def temporary_directory(preserve_on_error=False):
    """
    Helper function to handle the creation/deletion of a tmp directory
    """

    tmpdir = tempfile.mkdtemp()
    mntpoint_path = os.path.join(tmpdir, 'mntpoint')

    def _cleanup_temp_dir(tmpdir, mntpoint_path):
        """Helper to unmount and delete a temporary directory safely."""
        if os.path.ismount(mntpoint_path):
            try:
                subprocess.run(['umount', mntpoint_path], check=True)
                logging.info("Unmounted %s before cleanup.", mntpoint_path)
            except subprocess.CalledProcessError as exc:
                logging.warning("Failed to unmount %s: %s", mntpoint_path, str(exc))

        try:
            shutil.rmtree(tmpdir)
            logging.debug("Deleted temporary directory: %s", tmpdir)
        except Exception as exc:
            logging.error("Could not delete temp dir %s: %s", tmpdir, str(exc))

    try:
        yield tmpdir
    except Exception as exc:
        if preserve_on_error:
            logging.warning("Exception occurred. Preserving temp dir: %s", tmpdir)
            logging.debug("Preserved due to exception:\n%s", str(exc))
        else:
            _cleanup_temp_dir(tmpdir, mntpoint_path)
        raise  # Re-raise the original exception
    else:
        _cleanup_temp_dir(tmpdir, mntpoint_path)


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
                reason = f"Unable to create directory: {directory}"
                logging.error(reason)
                reasons.append(reason)

    if len(reasons) > 0:
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    return {'verdict': True}


def lockdown_directory(base_dir, exempt_dirs=[]):
    """
    Lockdown permissions on the base directory, skip the exempt directories if
    present
    """

    reasons = []

    if not isinstance(exempt_dirs, list):
        logging.error("Except directories not provided as a list")
        raise ValueError("Except directories not provided as a list")

    exempt_dirs = [ os.path.join(base_dir, exempt_dir) for exempt_dir in exempt_dirs ]

    try:
        dir_contents = [os.path.join(base_dir, f) for f in os.listdir(base_dir)]
    except OSError as exc:
        reason = f"Failed to list contents of directory {base_dir}"
        logging.error("%s: %s", reason, str(exc))
        reasons.append(reason)
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    for file in filter(os.path.isfile, dir_contents):
        try:
            os.chmod(file, 0o600)
        except (OSError, PermissionError) as exc:
            reason = f"Unable to set permissions for file {file}"
            logging.warning("%s: %s", reason, str(exc))
            reasons.append(reason)

    for directory in filter(os.path.isdir, dir_contents):
        if os.path.abspath(directory) in exempt_dirs:
            continue
        try:
            os.chmod(directory, 0o700)
        except (OSError, PermissionError) as exc:
            reason = f"Unable to set permissions for directory {directory}"
            logging.warning("%s: %s", reason, str(exc))
            reasons.append(reason)

    if len(reasons) > 0:
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    return {'verdict': True}


def test_write_access(dest_dir):
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
    except (OSError, PermissionError) as exc:
        logging.exception("Write test failed for %s: %s", dest_dir, str(exc))
        return False
