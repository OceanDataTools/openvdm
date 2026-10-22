#!/usr/bin/env python3
"""Periodic scheduler that submits OpenVDM transfer jobs to Gearman.

Runs as a long-lived daemon (managed by Supervisor in production).  On each
cycle it submits background Gearman jobs for every active and non-running
collection system transfer and cruise data transfer, then evaluates the
ship-to-shore (SSDW) transfer — restarting it if it has been running longer
than one hour, and queuing a new run if it is enabled.  Old transfer log files
are also purged based on the configured retention period.

Usage::

    scheduler.py [--interval MINUTES] [-v ...]
"""

import sys
import time
import json
import logging
import argparse
from os.path import dirname, realpath
from python3_gearman import GearmanClient

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import purge_old_files
from server.lib.openvdm import OpenVDM
from server.lib.transfer_lock import CDT, CST, transfer_locked
from server.workers.run_collection_system_transfer import TASK_NAMES as CST_TASKS_NAMES
from server.workers.run_cruise_data_transfer import TASK_NAMES as CDT_TASKS_NAMES
from server.workers.run_ship_to_shore_transfer import TASK_NAMES as S2ST_TASKS_NAMES

# A ship-to-shore run is stopped and started again after this many seconds,
# so it picks up files written since it started (#488)
S2S_RESTART_AFTER = 60 * 60

# Seconds to wait for a ship-to-shore job stopped for its hourly restart to end
S2S_STOP_WAIT = 60


def scheduler_job_key(kind: str, transfer_id) -> str:
    """Return the Gearman unique key of the scheduler's jobs for a transfer.

    gearmand merges a job submitted with the same task and key as one that's
    still queued or running, so the queue holds at most one scheduler job per
    transfer, however long the workers are busy (#479). Only the scheduler
    uses these keys: a manual Run or a cruise/lowering finalize sends its own
    payload, which a merge would drop, so those jobs get Gearman's random keys
    and are never merged.

    Args:
        kind: ``CST`` or ``CDT``, as for the transfer's lock.
        transfer_id: The transfer's ID.

    Returns:
        str: ``scheduler-<kind>-<id>``.
    """
    return f'scheduler-{kind}-{transfer_id}'


def scheduler(interval: int = None) -> None:
    """Submit Gearman transfer jobs on a recurring interval.

    Runs an infinite loop.  Each iteration:

    1. Purges transfer log files older than the configured retention period.
    2. Waits until the next full minute boundary.
    3. Skips the rest of the cycle if the system status is ``'Off'``.
    4. Submits a background ``runCollectionSystemTransfer`` job for each
       active, non-running collection system transfer.
    5. Submits a background ``runCruiseDataTransfer`` job for each
       non-running cruise data transfer.
    6. Manages the ship-to-shore (SSDW) transfer: stops it if it has been
       running for more than one hour, and starts a new run if enabled.

    A transfer is running while a job holds its lock (#478), whatever its
    status says. Jobs are submitted with :func:`scheduler_job_key`, so a
    transfer's job still waiting in the queue isn't queued again (#479).
    7. Sleeps until the next interval boundary.

    Args:
        interval: Scheduling interval in minutes.  When ``None`` the value is
            retrieved from the OpenVDM API (``getTransferInterval``).
    """

    ovdm = OpenVDM()
    interval = interval or ovdm.get_transfer_interval()

    gm_client = GearmanClient([ovdm.get_gearman_server()])
    time.sleep(10)

    logfile_purge_timedelta = ovdm.get_logfile_purge_timedelta()
    # When the current ship-to-shore run started, for its hourly restart
    s2s_started = None

    if logfile_purge_timedelta:
        logging.info("Logfile purge age set to: %s", logfile_purge_timedelta)

    while True:

        # purge old transfer logs; a problem there mustn't stop the
        # scheduling of transfers (#540)
        logging.info("Purging old transfer logs")
        try:
            transfer_log_dir = ovdm.get_transfer_log_dir()
            purge_old_files(transfer_log_dir, excludes="*Exclude.log", timedelta_str=logfile_purge_timedelta)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Unable to purge old transfer logs: %s", exc)

        # Run on the minute
        CURRENT_SEC = 0
        while True:
            t = time.gmtime()
            if CURRENT_SEC < t.tm_sec:
                CURRENT_SEC = t.tm_sec
                time.sleep(60-t.tm_sec)
            else:
                break

        if ovdm.get_system_status() == 'Off':
            logging.debug("System current set to Off")
            time.sleep(interval)
            continue

        # schedule collection_system_transfers
        collection_system_transfers = ovdm.get_active_collection_system_transfers('longName')
        for collection_system_transfer in collection_system_transfers:

            # A job holding the transfer's lock is running it (#478)
            if transfer_locked(CST, collection_system_transfer['collectionSystemTransferID']):
                continue

            logging.info("Submitting collection system transfer job for: %s", collection_system_transfer['longName'])

            gmData = {
                'collectionSystemTransfer': {
                    'collectionSystemTransferID': collection_system_transfer['collectionSystemTransferID']
                }
            }

            gm_client.submit_job(CST_TASKS_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'], json.dumps(gmData),
                                 unique=scheduler_job_key(CST, collection_system_transfer['collectionSystemTransferID']),
                                 background=True)
            time.sleep(2)

        # schedule cruise_data_transfers
        cruise_data_transfers = ovdm.get_cruise_data_transfers()
        for cruise_data_transfer in cruise_data_transfers:

            if transfer_locked(CDT, cruise_data_transfer['cruiseDataTransferID']):
                continue

            logging.info("Submitting cruise data transfer job for: %s", cruise_data_transfer['longName'])

            gmData = {
                'cruiseDataTransfer': {
                    'cruiseDataTransferID': cruise_data_transfer['cruiseDataTransferID']
                }
            }

            gm_client.submit_job(CDT_TASKS_NAMES['RUN_CRUISE_DATA_TRANSFER'], json.dumps(gmData),
                                 unique=scheduler_job_key(CDT, cruise_data_transfer['cruiseDataTransferID']),
                                 background=True)
            time.sleep(2)

        # schedule ship-to-shore transfer
        required_cruise_data_transfers = ovdm.get_required_cruise_data_transfers()
        ssdw_transfer = next((transfer for transfer in required_cruise_data_transfers if transfer["name"] == "SSDW"), None)
        if not ssdw_transfer:
            logging.error("SSDW transfer does not exists???")

        else:
            ssdw_id = ssdw_transfer['cruiseDataTransferID']
            running = transfer_locked(CDT, ssdw_id)
            if not running:
                s2s_started = None
            elif s2s_started is None:
                # A run the scheduler didn't start (a manual Run, or one going
                # when the scheduler started): time it from now
                s2s_started = time.monotonic()

            if running and time.monotonic() - s2s_started > S2S_RESTART_AFTER:
                logging.info("S2S tranfer has run for an hour, time to restart")
                gmData = {'pid': ssdw_transfer['pid']}
                gm_client.submit_job("stopJob", json.dumps(gmData))

                # The stopped job holds the lock until it ends; a new run
                # submitted before then would be ignored
                for _ in range(S2S_STOP_WAIT):
                    running = transfer_locked(CDT, ssdw_id)
                    if not running:
                        break
                    time.sleep(1)

            # While a run is going, a submission would only merge into it
            # (#479), so the next one starts once it has ended or been
            # restarted (#488)
            if ssdw_transfer['enable'] == 1 and not running:
                logging.info("Submitting cruise data transfer job for: %s", ssdw_transfer['longName'])
                s2s_started = time.monotonic()

                gmData = {
                }

                gm_client.submit_job(S2ST_TASKS_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'], json.dumps(gmData),
                                     unique=scheduler_job_key(CDT, ssdw_id),
                                     background=True)
                time.sleep(2)

        delay = interval * 60 - len(collection_system_transfers) * 2 - len(cruise_data_transfers) * 2 - 2
        logging.info("Waiting %s seconds until next round of tasks are queued", delay)
        time.sleep(delay)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='OpenVDM Data Transfer Scheduler')
    parser.add_argument('-i', '--interval', metavar='interval', type=int, help='interval in minutes')
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

    scheduler(parsed_args.interval)
