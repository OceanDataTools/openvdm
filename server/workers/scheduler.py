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
  VERSION:  2.9
  CREATED:  2015-01-01
 REVISION:  2022-07-24
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
from server.lib.openvdm import OpenVDM, DEFAULT_CONFIG_FILE
from server.lib.read_config import read_config

if __name__ == "__main__":

    ovdm = OpenVDM()

    parser = argparse.ArgumentParser(description='OpenVDM Data Transfer Scheduler')
    parser.add_argument('-i', '--interval', default=ovdm.get_transfer_interval(), metavar='interval', type=int, help='interval in minutes')
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

    logging.debug("Creating Geaman Client...")
    gm_client = GearmanClient([ovdm.get_gearman_server()])

    time.sleep(10)

    cruise_basedir = ovdm.get_cruisedata_path()
    openvdm_config = read_config(DEFAULT_CONFIG_FILE)
    logfile_purge_timedelta = openvdm_config['logfilePurgeTimedelta'] or None

    if logfile_purge_timedelta:
        logging.info("Logfile purge age set to: %s", logfile_purge_timedelta)

    while True:

        CURRENT_SEC = 0
        while True:
            t = time.gmtime()
            if CURRENT_SEC < t.tm_sec:
                CURRENT_SEC = t.tm_sec
                time.sleep(60-t.tm_sec)
            else:
                break

        # schedule collection_system_transfers
        collection_system_transfers = ovdm.get_active_collection_system_transfers()
        for collection_system_transfer in collection_system_transfers:
            logging.info("Submitting collection system transfer job for: %s", collection_system_transfer['longName'])

            gmData = {
                'collectionSystemTransfer': {
                    'collectionSystemTransferID': collection_system_transfer['collectionSystemTransferID']
                }
            }

            completed_job_request = gm_client.submit_job("runCollectionSystemTransfer", json.dumps(gmData), background=True)

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

            completed_job_request = gm_client.submit_job("runCruiseDataTransfer", json.dumps(gmData), background=True)

            time.sleep(2)

        # schedule ship-to-shore transfer
        required_cruise_data_transfers = ovdm.get_required_cruise_data_transfers()
        for required_cruise_data_transfer in required_cruise_data_transfers:
            if required_cruise_data_transfer['name'] == 'SSDW':
                logging.info("Submitting cruise data transfer job for: %s", required_cruise_data_transfer['longName'])

                gmData = {
                }

                completed_job_request = gm_client.submit_job("runShipToShoreTransfer", json.dumps(gmData), background=True)

            time.sleep(2)

        # purge old transfer logs:
        logging.info("Purging old transfer logs")
        cruiseID = ovdm.get_cruise_id()
        transfer_log_dir = os.path.join(cruise_basedir, cruiseID, ovdm.get_required_extra_directory_by_name('Transfer_Logs')['destDir'])
        purge_old_files(transfer_log_dir, excludes="*Exclude.log", timedelta_str=logfile_purge_timedelta)

        delay = parsed_args.interval * 60 - len(collection_system_transfers) * 2 - len(cruise_data_transfers) * 2 - 2
        logging.info("Waiting %s seconds until next round of tasks are queued", delay)
        time.sleep(delay)
