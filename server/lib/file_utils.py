#!/usr/bin/env python3
"""Utilities for local filesystem operations used across OpenVDM workers.

Provides helpers for building file lists, writing rsync include files,
managing directory ownership/permissions, purging old files, writing JSON
data files, and managing temporary directories.
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
import numpy as np
from contextlib import contextmanager
from pwd import getpwnam
from datetime import datetime, timedelta
from typing import List, Optional

default_ignore_patterns = [
    "**/@eaDir*",
    "**/.DS_Store",
    "**/._*",
    "**/Thumbs.db",
    "**/desktop.ini",
    "**/.*.??????"
]

def is_ascii(s: str) -> bool:
    """Check whether all characters in *s* are within the ASCII range (U+0–U+7F).

    Args:
        s: The string to test.

    Returns:
        ``True`` if every character in *s* is ASCII, ``False`` otherwise.
    """

    try:
        s.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False

def expand_patterns(patterns: List[str]) -> List[str]:
    """Expand recursive glob patterns to also include their top-level equivalents.

    For each pattern beginning with ``**/``, adds a version without the prefix
    so that files in the root of the search tree are also matched.

    Args:
        patterns: List of glob-style patterns, possibly containing ``**/``.

    Returns:
        Sorted list of unique patterns including both original and expanded forms.
    """
    expanded = set(patterns)
    for p in patterns:
        if p.startswith("**/"):
            expanded.add(p[3:])  # Add version without **/
    return sorted(expanded)

def is_default_ignore(filepath: str, patterns: Optional[List[str]] = None) -> bool:
    """Return ``True`` if *filepath* matches any of the provided glob-style patterns.

    Uses :func:`expand_patterns` to ensure both recursive (``**/``) and
    top-level variants are checked.  Defaults to :data:`default_ignore_patterns`
    when *patterns* is ``None``.

    Args:
        filepath: Absolute or relative path to test.
        patterns: Optional list of glob patterns.  Defaults to
            :data:`default_ignore_patterns`.

    Returns:
        ``True`` if *filepath* matches at least one pattern.
    """

    filepath = os.path.normpath(filepath)
    patterns = expand_patterns(patterns or default_ignore_patterns)

    return any(fnmatch.fnmatch(filepath, pattern) for pattern in patterns)


def build_filelist(source_dir: str) -> dict:
    """Walk *source_dir* and categorise every file as included or excluded.

    Files are excluded if they are symlinks, match
    :func:`is_default_ignore`, or contain non-ASCII characters in their path.
    All paths in the returned lists are relative to *source_dir*.

    Args:
        source_dir: Absolute path to the directory to scan.

    Returns:
        A dict with keys ``'include'``, ``'exclude'``, ``'new'``, and
        ``'updated'``.  ``'include'`` contains ASCII-clean, non-ignored
        relative paths; ``'exclude'`` contains non-ASCII paths.
        ``'new'`` and ``'updated'`` are empty lists reserved for callers.
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


def build_include_file(include_list: List[str], filepath: str) -> bool:
    """Write *include_list* to *filepath* for use as an rsync ``--files-from`` argument.

    Each entry is written on its own line, followed by a NUL byte to satisfy
    rsync's ``--from0`` option if used.

    Args:
        include_list: Relative file paths to include in the transfer.
        filepath: Destination path for the generated include file.

    Returns:
        ``True`` on success, ``False`` if the file could not be written.
    """

    try:
        with open(filepath, mode='w', encoding="utf-8") as f:
            f.write('\n'.join(include_list))
            f.write('\0')
    except IOError as exc:
        logging.error("Error writing include file: %s", str(exc))
        return False

    return True


def clear_directory(target_dir: str, delete_self: bool = False) -> dict:
    """Recursively delete all files and subdirectories inside *target_dir*.

    Args:
        target_dir: Path to the directory to clear.
        delete_self: If ``True``, also remove *target_dir* itself after
            emptying it.

    Returns:
        A dict with keys ``'verdict'`` (``bool``) and ``'reason'``
        (list of error strings).  ``'verdict'`` is ``True`` only when no
        errors occurred.
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


def delete_from_dest(dest_dir: str, include_files: List[str]) -> List[str]:
    """Delete any file in *dest_dir* that is not present in *include_files*.

    Also removes empty subdirectories left behind after deletion.

    Args:
        dest_dir: Root directory to prune.
        include_files: List of relative paths that should be *kept*.  Any file
            in *dest_dir* whose relative path is not in this list is deleted.

    Returns:
        List of relative paths that were deleted.
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


def purge_old_files(directory_path: str, excludes: Optional[str] = None,
                    timedelta_str: Optional[str] = None, recursive: bool = False) -> None:
    """Delete files in *directory_path* that are older than *timedelta_str*.

    Args:
        directory_path: Directory to scan for old files.
        excludes: Comma-separated list of glob patterns for files to skip.
        timedelta_str: Human-readable age threshold such as ``"12 hours"`` or
            ``"3 days"``.  Defaults to ``"12 hours"``.
        recursive: If ``True``, also purge files in subdirectories.

    Raises:
        ValueError: If *timedelta_str* cannot be parsed.
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


def output_json_data_to_file(file_path: str, contents) -> dict:
    """Serialise *contents* as JSON and write it to *file_path*.

    Parent directories are created automatically.  Uses :class:`NpEncoder` to
    handle NumPy types and :class:`~datetime.datetime` objects.

    Args:
        file_path: Destination file path.
        contents: Any JSON-serialisable object (including NumPy arrays and
            ``datetime`` instances).

    Returns:
        A dict with key ``'verdict'`` (``bool``) and, on failure, a ``'reason'``
        string.
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
            json.dump(contents, json_file, cls=NpEncoder)

        except IOError:
            reason = f'Unable to create data file: {file_path}'
            logging.error(reason)
            return {'verdict': False, 'reason': reason}

    return {'verdict': True}


def set_owner_group_permissions(user: str, path: str) -> dict:
    """Recursively set ownership and permissions on *path* for *user*.

    Files are set to ``0o644``; directories to ``0o755``.  Ownership (uid/gid)
    is looked up from the system password database.

    Args:
        user: System username whose uid/gid will own the files.
        path: File or directory path to update.

    Returns:
        A dict with key ``'verdict'`` (``bool``) and, on failure, a ``'reason'``
        string describing the first set of errors encountered.
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
def temporary_directory(preserve_on_error: bool = False):
    """Context manager that creates a temporary directory and cleans it up on exit.

    If a ``mntpoint`` subdirectory exists and is mounted at cleanup time, it is
    unmounted before the tree is removed.

    Args:
        preserve_on_error: If ``True``, skip cleanup when an exception is raised
            (useful for post-mortem debugging).

    Yields:
        Path to the freshly created temporary directory.

    Raises:
        Exception: Re-raises any exception that occurs inside the ``with`` block.
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


def create_directories(directorylist: List[str]) -> dict:
    """Create all directories listed in *directorylist*.

    Uses :func:`os.makedirs` so intermediate parents are created as needed.
    Existing directories are silently skipped.

    Args:
        directorylist: Absolute paths of directories to create.

    Returns:
        A dict with key ``'verdict'`` (``bool``) and, on failure, a ``'reason'``
        string containing newline-separated error messages.
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


def lockdown_directory(base_dir: str, exempt_dirs: Optional[List[str]] = None) -> dict:
    """Restrict permissions on the immediate contents of *base_dir*.

    Files are set to ``0o600``; subdirectories to ``0o700``.  Directories
    listed in *exempt_dirs* (relative to *base_dir*) are skipped.

    Args:
        base_dir: Directory whose contents will be locked down.
        exempt_dirs: List of subdirectory names (relative to *base_dir*) to
            leave untouched.  Defaults to an empty list.

    Returns:
        A dict with key ``'verdict'`` (``bool``) and, on failure, a ``'reason'``
        string containing newline-separated error messages.

    Raises:
        ValueError: If *exempt_dirs* is not a list.
    """

    reasons = []

    if exempt_dirs is None:
        exempt_dirs = []

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


def test_write_access(dest_dir: str) -> bool:
    """Verify that the current process has write permission to *dest_dir*.

    Creates and immediately deletes a temporary file inside the directory.

    Args:
        dest_dir: Directory path to test.

    Returns:
        ``True`` if a test file was successfully written and removed,
        ``False`` otherwise.
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

class NpEncoder(json.JSONEncoder):
    """JSON encoder that handles NumPy scalars, arrays, and :class:`~datetime.datetime` objects.

    Pass as the ``cls`` argument to :func:`json.dumps` or :func:`json.dump`
    wherever OpenVDM data (which may contain NumPy values) is serialised.
    """

    def default(self, o): # pylint: disable=arguments-differ
        """Serialise *o* to a JSON-compatible Python type.

        Args:
            o: Object to serialise.

        Returns:
            A JSON-native type (``int``, ``float``, ``list``, or ``str``).
        """

        if isinstance(o, np.integer):
            return int(o)

        if isinstance(o, np.floating):
            return float(o)

        if isinstance(o, np.ndarray):
            return o.tolist()

        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        return super().default(o)
