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
  VERSION:  2.11
  CREATED:  2017-09-30
 REVISION:  2025-07-06
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

def size_cacher(interval):
    """
    Calculate the sizes of the cruise and lowering directories at the defined
    interval
    """

    def loop_delay(start_dt, interval_s):
        elapsed = (datetime.datetime.utcnow() - start_dt).total_seconds()
        delay = interval_s - elapsed
        logging.debug("Elapsed Time: %.2f seconds", elapsed)

        if delay > 0:
            logging.info("Sleeping for %.2f seconds", delay)
            time.sleep(delay)

    def get_dir_size(path):
        if isdir(path):
            logging.debug("Calculating size for: %s", path)
            proc = subprocess.run(['du', '-sb', path], capture_output=True, text=True)
            if proc.returncode == 0:
                return proc.stdout.split()[0]
        return None

    ovdm = OpenVDM()

    while True:
        start = datetime.datetime.utcnow()

        try:
            warehouse_config = ovdm.get_shipboard_data_warehouse_config()
            cruise_id = ovdm.get_cruise_id()
            lowering_id = ovdm.get_lowering_id() if ovdm.get_show_lowering_components() else None
        except Exception as e:
            logging.error("Unable to retrieve data from OpenVDM API: %s", e)

            loop_delay(start, interval)
            continue

        cruise_dir = join(warehouse_config['shipboardDataWarehouseBaseDir'], cruise_id)
        lowering_dir = join(cruise_dir, warehouse_config['loweringDataBaseDir'], lowering_id) if lowering_id else None

        logging.debug("Cruise Directory: %s", cruise_dir)
        logging.debug("Lowering Directory: %s", lowering_dir)

        cruise_size = get_dir_size(cruise_dir)
        lowering_size = get_dir_size(lowering_dir) if lowering_dir else None

        ovdm.set_cruise_size(cruise_size)
        ovdm.set_lowering_size(lowering_size)

        if cruise_size:
            logging.info("Cruise Size: %s", cruise_size)
        if lowering_size:
            logging.info("Lowering Size: %s", lowering_size)

        loop_delay(start, interval)


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

    size_cacher(parsed_args.interval)
