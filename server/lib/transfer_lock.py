"""Per-transfer lock files, so only one job runs a transfer at a time.

A transfer job holds an exclusive ``flock()`` on the transfer's lock file
for as long as it runs (#478). The kernel releases the lock when the
process exits, even when it's killed, so a lock is never left behind, and
``/run`` is emptied on reboot. A transfer's ``status`` in the database is
only what the UI shows: whether a job is really running is whether its lock
is held, which the scheduler, Stop, Test Setup and ``reboot_reset`` check
with :func:`transfer_locked`.

The collection system transfer workers use :data:`CST` locks; the cruise
data and ship-to-shore transfer workers share :data:`CDT` locks, since
ship-to-shore is a cruise data transfer. All transfer workers must run on
the same host.
"""

import errno
import fcntl
import logging
import os
import time
from typing import IO, Optional

LOCK_DIR = '/run/openvdm'

CST = 'cst'
CDT = 'cdt'

# A check by transfer_locked() holds the lock for a moment; a job retries
# for this long before deciding another job holds it
ACQUIRE_ATTEMPTS = 5
ACQUIRE_RETRY_DELAY = 0.1


def _lock_path(kind: str, transfer_id) -> str:
    """Return the path of a transfer's lock file.

    Args:
        kind: :data:`CST` or :data:`CDT`.
        transfer_id: The transfer's ID.

    Returns:
        str: ``<LOCK_DIR>/<kind>-<id>.lock``.
    """
    return os.path.join(LOCK_DIR, f'{kind}-{int(transfer_id)}.lock')


def _try_lock(lock_file: IO) -> bool:
    """Try to take an exclusive lock on *lock_file* without waiting.

    Args:
        lock_file: An open lock file.

    Returns:
        bool: ``True`` if the lock was taken, ``False`` if another process holds it.
    """
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES):
            return False
        raise
    return True


def acquire_transfer_lock(kind: str, transfer_id) -> Optional[IO]:
    """Take a transfer's lock for the job that's about to run it.

    The returned file holds the lock until :func:`release_transfer_lock` or
    until the process exits. It isn't inherited by rsync, rclone or other
    child processes, so a child left running by a killed worker doesn't
    keep the transfer locked.

    Args:
        kind: :data:`CST` or :data:`CDT`.
        transfer_id: The transfer's ID.

    Returns:
        IO | None: The open lock file, or ``None`` if another job holds the lock.

    Raises:
        OSError: If the lock file can't be created or locked.
    """
    os.makedirs(LOCK_DIR, exist_ok=True)
    lock_file = open(_lock_path(kind, transfer_id), 'a', encoding='utf-8')  # pylint: disable=consider-using-with

    for attempt in range(ACQUIRE_ATTEMPTS):
        if _try_lock(lock_file):
            return lock_file
        if attempt < ACQUIRE_ATTEMPTS - 1:
            time.sleep(ACQUIRE_RETRY_DELAY)

    lock_file.close()
    return None


def release_transfer_lock(lock_file: Optional[IO]) -> None:
    """Release a lock taken by :func:`acquire_transfer_lock`.

    The lock file stays in place for the next job.

    Args:
        lock_file: The open lock file, or ``None`` (nothing to release).
    """
    if lock_file is None:
        return
    try:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
    finally:
        lock_file.close()


def transfer_locked(kind: str, transfer_id) -> bool:
    """Return whether a job is running the transfer, i.e. holds its lock.

    Args:
        kind: :data:`CST` or :data:`CDT`.
        transfer_id: The transfer's ID.

    Returns:
        bool: ``True`` if another process holds the transfer's lock. ``False``
        if it's free, if there's no lock file, or if the lock can't be checked.
    """
    try:
        with open(_lock_path(kind, transfer_id), 'r', encoding='utf-8') as lock_file:
            if not _try_lock(lock_file):
                return True
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        logging.warning("Unable to check the lock of %s transfer %s: %s", kind, transfer_id, exc)
    return False
