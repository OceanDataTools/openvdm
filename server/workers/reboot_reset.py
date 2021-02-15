#!/usr/bin/env python3
"""

FILE:  reboot_reset.py

DESCRIPTION:  This program resets OVDM state information in the database.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.6
  CREATED:  2015-06-22
 REVISION:  2021-02-13
"""

import argparse
import logging
import sys
import time
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM

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

    openVDM = OpenVDM()

    time.sleep(5)

    logging.info("Setting all tasks to idle.")
    tasks = openVDM.get_tasks()
    for task in tasks:
        openVDM.set_idle_task(task['taskID'])

    logging.info("Setting all Collection System Transfers to idle.")
    collection_system_transfers = openVDM.get_collection_system_transfers()
    for collection_system_transfer in collection_system_transfers:
        if not collection_system_transfer['status'] == '3':
            openVDM.set_idle_collection_system_transfer(collection_system_transfer['collectionSystemTransferID'])

    logging.info("Setting all Cruise Data Transfers to idle.")
    cruise_data_transfers = openVDM.get_cruise_data_transfers()
    for cruise_data_transfer in cruise_data_transfers:
        if not cruise_data_transfer['status'] == '3':
            openVDM.set_idle_cruise_data_transfer(cruise_data_transfer['cruiseDataTransferID'])

    required_cruise_data_transfers = openVDM.get_required_cruise_data_transfers()
    for required_cruise_data_transfer in required_cruise_data_transfers:
        if not required_cruise_data_transfer['status'] == '3':
            openVDM.set_idle_cruise_data_transfer(required_cruise_data_transfer['cruiseDataTransferID'])

    logging.info("Clearing all jobs from Gearman.")
    openVDM.clear_gearman_jobs_from_db()

    logging.info("Done!")
