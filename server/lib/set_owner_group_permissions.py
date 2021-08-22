#!/usr/bin/env python3
"""Utilities for setting file permissions/ownership.
"""
import logging
from grp import getgrnam
from os import chown, chmod, walk
from os.path import isfile, join, basename, dirname
from pwd import getpwnam

def remove_prefix(text, prefix):
    """
    Remove the specified prefix from the provided text if it exists
    """
    return text[text.startswith(prefix) and len(prefix):]

def set_owner_group_permissions(user, path):
    """
    Recursively set the ownership and permissions for the files and sub-
    directories for the given path.
    """
    reasons = []

    uid = getpwnam(user).pw_uid
    gid = getgrnam(user).gr_gid
    # Set the file permission and ownership for the current directory

    logging.debug("Setting ownership/permissions for %s", path)
    if isfile(path):
        try:
            chown(path, uid, gid)
            chmod(path, 0o644)
        except OSError:
            logging.error("Unable to set ownership/permissions for /%s", path)
            reasons.append("Unable to set ownership/permissions for /{}".format(path))

    else: #directory
        try:
            chown(path, uid, gid)
            chmod(path, 0o755)
        except OSError:
            logging.error("Unable to set ownership/permissions for /%s", path)
            reasons.append("Unable to set ownership/permissions for /{}".format(path))

        for root, dirs, files in walk(path):
            for file in files:
                fname = join(root, file)
                logging.debug("Setting ownership/permissions for %s", fname)
                try:
                    chown(fname, uid, gid)
                    chmod(fname, 0o644)
                except OSError:
                    logging.error("Unable to set ownership/permissions for %s", fname)
                    reasons.append("Unable to set ownership/permissions for {}".format(fname))

            for directory in dirs:
                dname = join(root, directory)
                logging.debug("Setting ownership/permissions for %s", dname)
                try:
                    chown(dname, uid, gid)
                    chmod(dname, 0o755)
                except OSError:
                    logging.error("Unable to set ownership/permissions for %s", dname)
                    reasons.append("Unable to set ownership/permissions for {}".format(dname))

    if len(reasons) > 0:
        return {'verdict': False, 'reason': '\n'.join(reasons)}

    return {'verdict': True}
