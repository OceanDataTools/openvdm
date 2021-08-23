#!/usr/bin/env python3
"""Utilities for determining invalid filenames.
"""
import re
import logging

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
    
    file_match = False if re.match(rsync_partial_file_re, filename) is None else True

    if file_match:
        logging.warning("Ignoring %s, this is an rsync partial file", filename)

    return file_match

