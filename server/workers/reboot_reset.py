#!/usr/bin/env python3
"""Reset OpenVDM state in the database after an unscheduled system reboot.

Sets all Gearman tasks, collection system transfers, and cruise data transfers
back to idle, then clears any stale Gearman job records from the database.
Intended to be run automatically by Supervisor/systemd on startup, or manually
after an ungraceful shutdown. Anything whose worker process is still running
is left alone, so running it while jobs are in progress doesn't free their
transfers for a second copy (#472).
"""

import argparse
import logging
import sys
import time
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM


def _worker_alive(row: dict) -> bool:
    """Return whether *row*'s stored PID is a running OpenVDM worker.

    Args:
        row: A task or transfer record with a ``pid``.

    Returns:
        bool: ``True`` if ``/proc/<pid>`` is an OpenVDM worker process.
    """

    try:
        pid = int(row.get('pid') or 0)
        if pid <= 0:
            return False
        with open(f'/proc/{pid}/cmdline', 'rb') as cmdline:
            return b'server/workers/' in cmdline.read()
    except (OSError, ValueError):
        return False


def reboot_reset():
    """Reset all OpenVDM tasks and transfers to idle and clear stale Gearman jobs.

    Connects to the OpenVDM API, marks every task and every collection
    system and cruise data transfer that isn't in error as idle, then removes
    any lingering Gearman job entries from the database. Records whose worker
    is still running are skipped, and the job list is kept if there are any.
    """

    openVDM = OpenVDM()
    alive = []

    logging.info("Setting all tasks to idle.")
    tasks = openVDM.get_tasks()
    for task in tasks:
        if _worker_alive(task):
            alive.append(task['name'])
            continue
        openVDM.set_idle_task(task['taskID'])

    logging.info("Setting all Collection System Transfers to idle.")
    collection_system_transfers = openVDM.get_collection_system_transfers()
    for collection_system_transfer in collection_system_transfers:
        if _worker_alive(collection_system_transfer):
            alive.append(collection_system_transfer['name'])
            continue
        if not collection_system_transfer['status'] == 3:
            openVDM.set_idle_collection_system_transfer(collection_system_transfer['collectionSystemTransferID'])

    logging.info("Setting all Cruise Data Transfers to idle.")
    cruise_data_transfers = openVDM.get_cruise_data_transfers()
    for cruise_data_transfer in cruise_data_transfers:
        if _worker_alive(cruise_data_transfer):
            alive.append(cruise_data_transfer['name'])
            continue
        if not cruise_data_transfer['status'] == 3:
            openVDM.set_idle_cruise_data_transfer(cruise_data_transfer['cruiseDataTransferID'])

    required_cruise_data_transfers = openVDM.get_required_cruise_data_transfers()
    for required_cruise_data_transfer in required_cruise_data_transfers:
        if _worker_alive(required_cruise_data_transfer):
            alive.append(required_cruise_data_transfer['name'])
            continue
        if not required_cruise_data_transfer['status'] == 3:
            openVDM.set_idle_cruise_data_transfer(required_cruise_data_transfer['cruiseDataTransferID'])

    if alive:
        # The job list drops finished jobs by itself; keep the running ones
        logging.warning("Left alone, worker still running: %s", ', '.join(alive))
    else:
        logging.info("Clearing all jobs from Gearman.")
        openVDM.clear_gearman_jobs_from_db()

    logging.info("Done!")


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle resetting OpenVDM database after an unscheduled system reboot')
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

    # Wait a period of time to allow processes to settle out
    time.sleep(5)

    reboot_reset()
