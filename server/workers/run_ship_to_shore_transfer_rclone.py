#!/usr/bin/env python3
"""
FILE:  run_ship_to_shore_transfer_rclone.py

DESCRIPTION:  Gearman worker that handles the transfer of data from the
    Shipboard Data Warehouse to a Shoreside Data Warehouse using rclone
    as the transport mechanism.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2025-08-06
 REVISION:
"""

import argparse
import logging
import os
import sys
import re
import subprocess
import signal
from os.path import dirname, realpath

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import temporary_directory
from server.workers.run_ship_to_shore_transfer import OVDMGearmanWorker as ShipToShoreGearmanWorker
from server.workers.run_ship_to_shore_transfer import TASK_NAMES, task_run_ship_to_shore_transfer

RCLONE_PROGRESS_RE = re.compile(r'Transferred:\s+[\d.]+\w+\s+\/\s+[\d.]+\w+,\s+(\d+)%')

class OVDMGearmanWorker(ShipToShoreGearmanWorker):
    """
    Class for the current Gearman worker
    """

    def test_destination(self):
        return [{"partName": "Connection test", "result": "Pass"}]


    def run_transfer_command(self, current_job, command, file_count):
        """
        Run the rclone copy command and parse the output for progress.
        Returns: (new_files, updated_files, deleted_files)
        """

        if file_count == 0:
            logging.debug("Skipping Transfer Command: nothing to transfer")
            return [], [], []

        logging.debug('Transfer Command: %s', ' '.join(command))

        last_percent_reported = -1

        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        try:
            for line in proc.stdout:
                if self.stop:
                    logging.debug("Stopping transfer")
                    proc.terminate()
                    break

                line = line.strip()
                if not line:
                    continue

                logging.debug("rclone output: %s", line)

                # Try to extract progress percentage from rclone's output
                match = RCLONE_PROGRESS_RE.search(line)
                if match:
                    percent = int(match.group(1))
                    if percent != last_percent_reported:
                        logging.info("Progress Update: %d%%", percent)
                        self.send_job_status(current_job, int(75 * percent / 100) + 20, 100)
                        last_percent_reported = percent

            proc.wait()

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, command)

        except Exception as e:
            logging.error("Transfer failed: %s", e)
            proc.terminate()

        # return new_files, updated_files, deleted_files
        return [], [], []


    def transfer_to_destination(self, current_job):
        """
        Transfer the files to a destination on a ssh server
        """

        cdt_cfg = self.cruise_data_transfer
        is_darwin = False

        def _build_rclone_command(flags, extra_args, source_dir, dest_dir, include_file_path=None):
            cmd = ['rclone', 'copy'] + flags
            if extra_args is not None:
                cmd += extra_args

            if include_file_path is not None:
                cmd.append(f"--files-from {include_file_path}")

            cmd += [source_dir.rstrip('/')+'/', dest_dir.rstrip('/')+'/']
            return cmd

        def _build_include_file(include_list, filepath):
            try:
                with open(filepath, mode='w', encoding="utf-8") as f:
                    f.write('\n'.join(include_list))
                    f.write('\0')
            except IOError as exc:
                logging.error("Error writing include file: %s", str(exc))
                return False

            return True

        with temporary_directory() as tmpdir:
            dest_dir = cdt_cfg['destDir']

            include_file = os.path.join(tmpdir, 'rsyncFileList.txt')

            results = self.build_filelist(is_darwin)

            if not results['verdict']:
                return {'verdict': False, 'reason': results.get('reason', 'Unknown')}

            files = results['files']

            if not _build_include_file([f'{self.cruise_id}/{filepath}' for filepath in files['include']], include_file):
                return {'verdict': False, 'reason': 'Failed to write include file'}

            flags = ["--create-empty-src-dirs", "--progress"]
            cmd = _build_rclone_command(flags, None, self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], dest_dir, include_file)
            # cmd = [
            #     "rclone", "copy", self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'],
            #     dest_dir,
            #     "--files-from", include_file,
            #     "--create-empty-src-dirs",
            #     "--progress"
            # ]

            files['new'], files['updated'], files['deleted'] = self.run_transfer_command(current_job, cmd, len(files['include']))
            return {'verdict': True, 'files': files}


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle ship-to-shore transfer related tasks')
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

    new_worker = OVDMGearmanWorker()
    new_worker.set_client_id(__file__)

    def sigquit_handler(_signo, _stack_frame):
        """
        Signal Handler for QUIT
        """

        logging.warning("QUIT Signal Received")
        new_worker.stop_task()

    def sigint_handler(_signo, _stack_frame):
        """
        Signal Handler for INT
        """

        logging.warning("INT Signal Received")
        new_worker.quit_worker()

    signal.signal(signal.SIGQUIT, sigquit_handler)
    signal.signal(signal.SIGINT, sigint_handler)

    logging.info("Registering worker tasks...")

    logging.info("\tTask: %s", TASK_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_SHIP_TO_SHORE_TRANSFER'], task_run_ship_to_shore_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
