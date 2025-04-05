#!/usr/bin/env python3
"""Utilities for creating/ directories and managing their permissions.
"""

import os
import re
import time
import fnmatch
import logging
from datetime import timedelta

rsync_partial_file_re = re.compile(r'(^\..+\.[\w]{6}$)')

def is_ascii(test_str):
    """Check if the characters in string s are in ASCII, U+0-U+7F."""

    return len(test_str) == len(test_str.encode())


def bad_filename(filename):
    """Verify the filename contains only valid ASCii characters"""

    try:
        str(filename)
    except Exception as err:
        logging.debug(str(err))
        return True
    return False


def bad_filenames(files):
    """
    Return a list of files that contain non-ASCii chanacters from the
    list of provided filenames
    """

    problem_files = list(filter(bad_filename, files))

    if len(problem_files) > 0:
        logging.debug("Problem Files:")
        logging.debug("\t %s", "\n\t".join(problem_files))

    return problem_files


def is_rsync_patial_file(filename):
    """
    check to see if the filename is a rsync partial file.
    """

    # file_match = False if re.match(rsync_partial_file_re, filename) is None else True
    file_match = re.match(rsync_partial_file_re, filename) is not None

    if file_match:
        logging.warning("Ignoring %s, this is an rsync partial file", filename)

    return file_match


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
            if os.path.isfile(filepath):
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
        return

    # Get the current time
    current_time = time.time()

    _purge_files(directory_path, excludes, time_delta.total_seconds(), recursive)
