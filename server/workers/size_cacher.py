#!/usr/bin/env python3
"""Continuously cache the on-disk sizes of the cruise and lowering directories.

Runs as a long-lived daemon process (managed by Supervisor in production).
At each interval it calls ``du -sb`` on the current cruise and, if active, the
current lowering directory, then pushes the byte totals to the OpenVDM API so
the web UI can display them without a blocking ``du`` call on every page load.

Usage::

    size_cacher.py [--interval SECONDS] [-v ...]
"""

import argparse
from datetime import datetime, timezone
import logging
import subprocess
import sys
import time
from os.path import dirname, realpath, join, isdir

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM

def size_cacher(interval: int) -> None:
    """Poll cruise and lowering directory sizes and push them to the OpenVDM API.

    Runs an infinite loop.  On each iteration the current cruise and (when
    lowering components are enabled) lowering directory sizes are measured with
    ``du -sb``, then written back to OpenVDM via
    :py:meth:`~server.lib.openvdm.OpenVDM.set_cruise_size` and
    :py:meth:`~server.lib.openvdm.OpenVDM.set_lowering_size`.  The loop then
    sleeps until ``interval`` seconds have elapsed since the start of the
    previous iteration.

    Args:
        interval: Minimum number of seconds between consecutive size
            calculations.
    """

    ovdm = OpenVDM()

    def loop_delay(start_dt, interval_s):
        elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds()
        delay = interval_s - elapsed
        logging.debug("Elapsed Time: %.2f seconds", elapsed)

        if delay > 0:
            logging.info("Sleeping for %.2f seconds", delay)
            time.sleep(delay)


    def get_dir_size(path):
        if not isdir(path):
            logging.warning("Path is not a directory or does not exist: %s", path)
            return None

        logging.debug("Calculating size for: %s", path)

        try:
            proc = subprocess.run(
                ['du', '-sb', path],
                capture_output=True,
                text=True
            )

            if proc.returncode == 0:
                return proc.stdout.split()[0]
            else:
                logging.warning("du failed (some files may have disappeared): %s", proc.stderr.strip())
                # attempt to parse partial output anyway
                if proc.stdout:
                    try:
                        return proc.stdout.split()[0]
                    except Exception:
                        pass
                return None

        except Exception as e:
            logging.exception("Exception while running du on %s: %s", path, e)
            return None


    while True:
        start = datetime.now(timezone.utc)

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
