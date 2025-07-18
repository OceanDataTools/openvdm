#!/usr/bin/env python3
"""
FILE:  size_cacher.py

DESCRIPTION:  This program handles calculating the cruise and lowering
                directory sizes.

USAGE: size_cacher.py [--interval <interval>]

ARGUMENTS: --interval <interval> The minimum interval in second between directory
    size calculations.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.10
  CREATED:  2017-09-30
 REVISION:  2025-04-12
"""

import argparse
import datetime
import logging
import subprocess
import sys
import time
from os.path import dirname, realpath, join, isdir

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='OpenVDM Directory Size Cacher')
    parser.add_argument('--interval', default=10, metavar='interval', type=int, help='Maximum update rate in seconds')
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

    ovdm = OpenVDM()

    while True:

        start_t = datetime.datetime.utcnow()

        warehouse_config = ovdm.get_shipboard_data_warehouse_config()
        cruise_dir = join(warehouse_config['shipboardDataWarehouseBaseDir'], ovdm.get_cruise_id())

        lowering_id = ovdm.get_lowering_id() if ovdm.get_show_lowering_components() else None
        lowering_dir = join(cruise_dir, warehouse_config['loweringDataBaseDir'], lowering_id) if lowering_id else None

        logging.debug("Cruise Directory: %s", cruise_dir)
        logging.debug("Lowering Directory: %s", lowering_dir)

        if isdir(cruise_dir):
            logging.debug("Calculating Cruise Size...")
            cruise_size_proc = subprocess.run(['du','-sb', cruise_dir], capture_output=True, text=True, check=False)
            if cruise_size_proc.returncode == 0:
                logging.info("Cruise Size: %s", cruise_size_proc.stdout.split()[0])
                ovdm.set_cruise_size(cruise_size_proc.stdout.split()[0])

            if lowering_dir and isdir(lowering_dir):
                logging.debug("Calculating Lowering Size...")
                loweringSizeProc = subprocess.run(['du','-sb', lowering_dir], capture_output=True, text=True, check=False)
                if loweringSizeProc.returncode == 0:
                    logging.info("Lowering Size: %s", loweringSizeProc.stdout.split()[0])
                    ovdm.set_lowering_size(loweringSizeProc.stdout.split()[0])

        else:
            ovdm.set_cruise_size()
            ovdm.set_lowering_size()

        end_t = datetime.datetime.utcnow()

        elapse_t = end_t - start_t
        logging.debug("Total Seconds: %s", elapse_t.total_seconds())

        if (elapse_t.total_seconds()) >= parsed_args.interval:
            continue

        logging.info("Calculating size again in %s seconds", parsed_args.interval - elapse_t.total_seconds())
        time.sleep(parsed_args.interval - elapse_t.total_seconds())
