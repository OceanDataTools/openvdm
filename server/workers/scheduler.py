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
from datetime import datetime, timedelta, timezone
from os.path import dirname, realpath
from python3_gearman import GearmanClient

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import purge_old_files
from server.lib.openvdm import OpenVDM
from server.workers.run_collection_system_transfer import TASK_NAMES as CST_TASKS_NAMES
from server.workers.run_cruise_data_transfer import TASK_NAMES as CDT_TASKS_NAMES
from server.workers.run_ship_to_shore_transfer import TASK_NAMES as S2ST_TASKS_NAMES

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
    last_s2s_xfer = datetime.now(timezone.utc)

    if logfile_purge_timedelta:
        logging.info("Logfile purge age set to: %s", logfile_purge_timedelta)

    while True:

        # purge old transfer logs:
        logging.info("Purging old transfer logs")
        transfer_log_dir = ovdm.get_transfer_log_dir()
        purge_old_files(transfer_log_dir, excludes="*Exclude.log", timedelta_str=logfile_purge_timedelta)

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

            if collection_system_transfer['status'] == 1:
                continue

            logging.info("Submitting collection system transfer job for: %s", collection_system_transfer['longName'])

            gmData = {
                'collectionSystemTransfer': {
                    'collectionSystemTransferID': collection_system_transfer['collectionSystemTransferID']
                }
            }

            gm_client.submit_job(CST_TASKS_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'], json.dumps(gmData), background=True)
            time.sleep(2)

        # schedule cruise_data_transfers
        cruise_data_transfers = ovdm.get_cruise_data_transfers()
        for cruise_data_transfer in cruise_data_transfers:

            if cruise_data_transfer['status'] == 1:
                continue

            logging.info("Submitting cruise data transfer job for: %s", cruise_data_transfer['longName'])

            gmData = {
                'cruiseDataTransfer': {
                    'cruiseDataTransferID': cruise_data_transfer['cruiseDataTransferID']
                }
            }

            gm_client.submit_job(CDT_TASKS_NAMES['RUN_CRUISE_DATA_TRANSFER'], json.dumps(gmData), background=True)
            time.sleep(2)

        # schedule ship-to-shore transfer
        required_cruise_data_transfers = ovdm.get_required_cruise_data_transfers()
        ssdw_transfer = next((transfer for transfer in required_cruise_data_transfers if transfer["name"] == "SSDW"), None)
        if not ssdw_transfer:
            logging.error("SSDW transfer does not exists???")

        else:
            now_utc = datetime.now(timezone.utc)
            delta = now_utc - last_s2s_xfer
            if ssdw_transfer['status'] == 1 and delta > timedelta(hours=1):
                logging.info("S2S tranfer has run for an hour, time to restart")
                gmData = {'pid': ssdw_transfer['pid']}
                gm_client.submit_job("stopJob", json.dumps(gmData))

            if ssdw_transfer['enable'] == 1:
                logging.info("Submitting cruise data transfer job for: %s", ssdw_transfer['longName'])
                last_s2s_xfer = datetime.now(timezone.utc)

                gmData = {
                }

                gm_client.submit_job(S2ST_TASKS_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'], json.dumps(gmData), background=True)
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
