#!/usr/bin/env python3
"""
FILE:  scheduler.py

DESCRIPTION:  This program handles the scheduling of the transfer-related Gearman
    tasks.

USAGE: scheduler.py [--interval <interval>] <siteRoot>

ARGUMENTS: --interval <interval> The interval in minutes between transfer job
            submissions.  If this argument is not provided the default inteval
            is 5 minutes

            <siteRoot> The base URL to the OpenVDM installation on the Shipboard
             Data Warehouse.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.10
  CREATED:  2015-01-01
 REVISION:  2025-04-12
"""

import os
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
from server.workers.run_collection_system_transfer import TASK_NAMES as CST_TASKS_NAMES
from server.workers.run_cruise_data_transfer import TASK_NAMES as CDT_TASKS_NAMES
from server.workers.run_ship_to_shore_transfer import TASK_NAMES as S2ST_TASKS_NAMES

def scheduler(ovdm, interval=None):

    ovdm = OpenVDM()
    interval = interval or ovdm.get_transfer_interval()

    gm_client = GearmanClient([ovdm.get_gearman_server()])
    time.sleep(10)

    cruise_basedir = ovdm.get_cruisedata_path()
    logfile_purge_timedelta = ovdm.get_logfile_purge_timedelta()

    if logfile_purge_timedelta:
        logging.info("Logfile purge age set to: %s", logfile_purge_timedelta)

    while True:

        # purge old transfer logs:
        logging.info("Purging old transfer logs")
        cruiseID = ovdm.get_cruise_id()
        transfer_log_dir = os.path.join(cruise_basedir, cruiseID, ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])
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
        collection_system_transfers = ovdm.get_active_collection_system_transfers()
        for collection_system_transfer in collection_system_transfers:
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
        for required_cruise_data_transfer in required_cruise_data_transfers:
            if required_cruise_data_transfer['name'] == 'SSDW':
                logging.info("Submitting cruise data transfer job for: %s", required_cruise_data_transfer['longName'])

                gmData = {
                }

                gm_client.submit_job(S2ST_TASKS_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'], json.dumps(gmData), background=True)
                time.sleep(2)
                break

        delay = parsed_args.interval * 60 - len(collection_system_transfers) * 2 - len(cruise_data_transfers) * 2 - 2
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
