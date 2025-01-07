#!/usr/bin/env python3
"""Wrapper for hashlib_md5 to comply with new security best practices.
"""

import hashlib

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
