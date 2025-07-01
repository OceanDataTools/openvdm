#!/usr/bin/env python3
"""Wrapper for hashlib_md5 to comply with new security best practices.
"""

import hashlib

BUF_SIZE = 65536  # read files in 64kb chunks

def hashlib_md5():
    """
    Function that returns a newer md5 hashlib but will revert to older
    version if needed.
    """

    try:
        return hashlib.md5(usedforsecurity=False)
    except TypeError:
        # usedforsecurity is not supported
        return hashlib.md5()

def hash_file(filepath):
    """
    Build the md5 hash for the given file
    """
    try:
        with open(filepath, mode='rb') as f:
            file_hash = hashlib_md5()
            while chunk := f.read(BUF_SIZE):
                file_hash.update(chunk)
        return file_hash.hexdigest()  # to get a printable str instead of bytes
    except Exception as err:
        raise err
