#!/usr/bin/env python3
"""Gearman worker that transfers all cruise data from the Shipboard Data Warehouse to a second location.

Registers the ``runCruiseDataTransfer`` Gearman task.  Supports five
destination types (local directory, rsync server, SMB share, SSH server via
rclone, generic rclone remote) as determined by the cruise data transfer
configuration stored in the OpenVDM database.

Key responsibilities:

- Test the destination before transferring and report a human-readable error
  on failure.
- Mount SMB shares and unmount them on completion.
- Apply cruise-level exclude filters when building the rsync or rclone command.
- Report real-time transfer progress back to the Gearman job.
- Set correct file ownership and permissions after the transfer completes.
"""

import argparse
import json
import logging
import os
import sys
import signal
import subprocess
import time
import traceback
from os.path import dirname, realpath
from random import randint
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from server.lib.file_utils import is_ascii, set_owner_group_permissions, transfer_exclude_patterns, temporary_directory, write_list_file
from server.lib import transfer_utils
from server.lib.transfer_utils import TransferCommandError, error_detail
from server.lib.connection_utils import FTP_REMOTE, build_rclone_command, build_rclone_config_for_ssh, build_rclone_options, build_rsync_command, build_rsync_options, check_darwin, detect_smb_version, get_transfer_type, mount_smb_share, prepare_ftp_config, rsync_dest_path, test_cdt_destination, test_cdt_rclone_destination
from server.lib.openvdm import OpenVDM


# Gearman task names this worker registers.
TASK_NAMES = {
    'RUN_CRUISE_DATA_TRANSFER': 'runCruiseDataTransfer'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker):
    """Gearman worker for cruise data transfers to a secondary destination.

    Attributes:
        stop: Flag set to ``True`` to halt after the current job.
        ovdm: OpenVDM API client.
        cruise_id: Current cruise identifier.
        system_status: Cached system status string (``'On'`` or ``'Off'``).
        cruise_data_transfer: Configuration dict for the active transfer.
        shipboard_data_warehouse_config: Warehouse configuration snapshot.
        cruise_dir: Absolute path to the cruise data directory.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.cruise_id = None
        self.system_status = None
        self.cruise_data_transfer = None
        self.shipboard_data_warehouse_config = None

        self.cruise_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_exclude_filterlist(self):
        """Return the rsync/rclone exclude patterns for the cruise data transfer.

        Excludes the collection systems and extra directories the transfer is
        set to skip, and lowering config files where configured, plus files
        with non-ASCII names.

        Returns:
            list[str]: Exclude patterns, relative to the cruise directory.
        """

        #exclude non-ascii filenames
        def _find_non_ascii_files(source_dir):
            non_ascii_files = []
            for root, dirs, files in os.walk(source_dir):
                for name in files:
                    if not is_ascii(name):
                        full_path = os.path.join(root, name)
                        non_ascii_files.append(os.path.relpath(full_path, source_dir))
            return non_ascii_files

        exclude_filterlist = []

        wh_cfg = self.shipboard_data_warehouse_config
        cdt_cfg = self.cruise_data_transfer

        # Exclude OVDM-related files if flag is set
        if cdt_cfg.get('includeOVDMFiles') == 0:
            exclude_filterlist.extend([
                f"{wh_cfg['cruiseConfigFn']}",
                f"{wh_cfg['md5SummaryFn']}",
                f"{wh_cfg['md5SummaryMd5Fn']}"
            ])

            # Wildcard the lowering-ID segment so lowerings created after this
            # exclude list is generated are still covered for the lifetime of
            # long-running (e.g. rclone) transfers.
            exclude_filterlist.append(f"{os.path.join(wh_cfg['loweringDataBaseDir'], '*', self.ovdm.get_lowering_config_fn())}")

        # Handle excluded collection systems
        ex_cst_ids = cdt_cfg.get('excludedCollectionSystems', '').split(',') if cdt_cfg.get('excludedCollectionSystems') else []

        for cst_id in filter(lambda x: x and x != 0, ex_cst_ids):
            try:
                cst_cfg = self.ovdm.get_collection_system_transfer(cst_id)
                cruise_or_lowering = cst_cfg.get('cruiseOrLowering')
                dest_dir = cst_cfg.get('destDir')

                if cruise_or_lowering == 0:
                    # Cruise-level exclusion
                    exclude_filterlist.append(f"{dest_dir.replace('{cruiseID}', self.cruise_id)}/**")
                else:
                    # Lowering-level exclusion. Wildcard the lowering-ID
                    # segment rather than enumerating currently known
                    # lowerings, so lowerings created after this exclude list
                    # is generated are still covered for the lifetime of
                    # long-running (e.g. rclone) transfers.
                    filter_path = dest_dir.replace('{cruiseID}', self.cruise_id).replace('{loweringID}', '*')
                    exclude_filterlist.append(f"{os.path.join(wh_cfg['loweringDataBaseDir'], '*', filter_path)}/**")

            except Exception as exc:
                logging.warning("Could not retrieve collection system transfer %s: %s", cst_id, str(exc))

        # Handle excluded extra directories
        ex_ed_ids = cdt_cfg.get('excludedExtraDirectories', '').split(',') if cdt_cfg.get('excludedExtraDirectories') else []

        for ed_id in filter(lambda x: x and x != 0, ex_ed_ids):
            try:
                ed_cfg = self.ovdm.get_extra_directory(ed_id)
                cruise_or_lowering = ed_cfg.get('cruiseOrLowering')
                dest_dir = ed_cfg.get('destDir')

                if cruise_or_lowering == 0:
                    # Cruise-level exclusion
                    exclude_filterlist.append(f"{dest_dir.replace('{cruiseID}', self.cruise_id)}/**")
                else:
                    # Lowering-level exclusion. Wildcard the lowering-ID
                    # segment rather than enumerating currently known
                    # lowerings, so lowerings created after this exclude list
                    # is generated are still covered for the lifetime of
                    # long-running (e.g. rclone) transfers.
                    filter_path = dest_dir.replace('{cruiseID}', self.cruise_id).replace('{loweringID}', '*')
                    exclude_filterlist.append(f"{os.path.join(wh_cfg['loweringDataBaseDir'], '*', filter_path)}/**")

            except Exception as exc:
                logging.warning("Could not retrieve extra directory %s: %s", ed_id, str(exc))

        exclude_filterlist.extend(_find_non_ascii_files(self.cruise_dir))
        #exclude_filterlist = [ '{self.cruise_id}/{path_filter}' for path_filter in exclude_filterlist ]
        # rsync partial files, Synology files, .DS_Store, etc, in a form rclone
        # also matches at the top level and in directories (#259)
        exclude_filterlist.extend(transfer_exclude_patterns())

        return exclude_filterlist


    def test_destination(self):
        """Run the connection tests for the transfer's destination.

        Uses ``test_cdt_rclone_destination()`` for rclone destinations (a
        ``remote:path`` ``destDir``) and ``test_cdt_destination()`` otherwise.

        Returns:
            list[dict]: Test parts with ``partName``/``result``/``reason``
            keys.
        """
        if ':' in self.cruise_data_transfer['destDir']:
            return test_cdt_rclone_destination(self.cruise_data_transfer)

        return test_cdt_destination(self.cruise_data_transfer)


    def make_cruise_dir(self, dest_dir, extra_args=None):
        """Create the cruise directory on an rclone destination (``rclone mkdir``).

        Failures are logged, not raised.

        Args:
            dest_dir: rclone destination (``remote:path``).
            extra_args: Extra rclone arguments (e.g. ``['--config', path]``),
                or ``None``.
        """

        # Build rclone command
        command = ['rclone', 'mkdir', f'{dest_dir.rstrip("/")}/{self.cruise_id}']
        if extra_args:
            command.extend(extra_args)

        logging.debug('mkdir Command: %s', ' '.join(command))
        try:

            # Run the command
            subprocess.run(command, check=True, capture_output=True, text=True)

            logging.debug("Remote cruise directory created successfully.")

        except subprocess.CalledProcessError as e:
            logging.error("Error creating cruise directory: %s", e.stderr)


    def run_transfer_command(self, current_job, command, file_count):
        """Run an rsync or rclone transfer command and collect the files it transferred.

        Uses :func:`server.lib.transfer_utils.run_transfer_command`, reporting
        progress to the Gearman job and honouring ``self.stop``.

        Args:
            current_job: The Gearman job, for progress updates.
            command: The rsync or rclone command as an argument list.
            file_count: Number of files expected; with ``0`` the command isn't
                run.

        Returns:
            tuple[list, list, list]: ``(new_files, updated_files, deleted_files)``.

        Raises:
            TransferCommandError: If the command exits with an error (#230).
        """

        def _progress(percent):
            self.send_job_status(current_job, int(90 * percent/100) + 5, 100)  # 95 - 5

        result = transfer_utils.run_transfer_command(command, file_count, _progress, lambda: self.stop)
        return result['new'], result['updated'], result['deleted']


    def transfer_to_destination(self, current_job):
        """Copy the cruise directory to the transfer's destination.

        Handles local directories, SMB shares, rsync servers, SSH servers, FTP
        servers and rclone remotes, applying the transfer's exclude filters.

        Args:
            current_job: The Gearman job, for progress updates.

        Returns:
            dict: ``{'verdict': True, 'files': ...}`` with the transferred
            files, or ``{'verdict': False, 'reason': ...}``.
        """

        cdt_cfg = self.cruise_data_transfer
        transfer_type = get_transfer_type(cdt_cfg['transferType'])

        if not transfer_type:
            logging.error("Unknown Transfer Type")
            return {'verdict': False, 'reason': 'Unknown Transfer Type'}

        files = { 'new':[], 'updated':[], 'deleted':[], 'exclude': [] }
        is_darwin = False
        rclone_args = None  # e.g. the --config for an SSH or FTP destination's rclone remote


        with temporary_directory() as tmpdir:
            exclude_file = os.path.join(tmpdir, 'rsyncExcludeList.txt')

            exclude_list = self.build_exclude_filterlist()
            logging.debug("Exclude filters: %s", json.dumps(exclude_list, indent=2))

            if not write_list_file(exclude_list, exclude_file):
                return {'verdict': False, 'reason': 'Failed to write exclude file'}

            if transfer_type == 'smb':
                # Mount SMB Share
                mntpoint = os.path.join(tmpdir, 'mntpoint')
                os.mkdir(mntpoint, 0o755)
                smb_version, smb_detail = detect_smb_version(cdt_cfg)
                success, mount_detail = mount_smb_share(cdt_cfg, mntpoint, smb_version)
                if not success:
                    reason = 'Failed to mount SMB share'
                    if mount_detail:
                        reason += f' — {mount_detail}'
                    return {'verdict': False, 'reason': reason}
                dest_dir = os.path.join(mntpoint, cdt_cfg['destDir'].lstrip('/'))

            elif transfer_type == 'rsync':
                # Write rsync password file
                password_file = os.path.join(tmpdir, 'rsyncPass')
                with open(password_file, 'w', encoding='utf-8') as f:
                    f.write(cdt_cfg['rsyncPass'])
                os.chmod(password_file, 0o600)
                dest_dir = f"rsync://{cdt_cfg['rsyncUser']}@{rsync_dest_path(cdt_cfg['rsyncServer'], cdt_cfg['destDir'])}/"

            elif transfer_type == 'ssh':
                is_darwin = check_darwin(cdt_cfg)
                rclone_config = os.path.join(tmpdir, 'rclone_config')
                rclone_remote = build_rclone_config_for_ssh(cdt_cfg, rclone_config)
                rclone_args = ['--config', rclone_config]
                dest_dir = f"{rclone_remote}:{cdt_cfg['destDir']}"

            elif transfer_type == 'ftp':
                # destDir is an absolute path on the FTP server (#199)
                success, rclone_config = prepare_ftp_config(cdt_cfg, tmpdir)
                if not success:
                    return {'verdict': False, 'reason': rclone_config}
                rclone_args = ['--config', rclone_config]
                dest_dir = f"{FTP_REMOTE}:{cdt_cfg['destDir']}"

            else:  # local
                dest_dir = cdt_cfg['destDir']

            # === DRY RUN ===
            dry_flags = build_rsync_options(cdt_cfg, mode='dry-run', is_darwin=is_darwin)

            # The dry run only counts the files to send, and always writes
            # locally: to the temporary directory for a remote destination
            # (':' in dest_dir), so without remote-only arguments such as
            # --password-file (rsync rejects it without an rsync daemon, #249)
            dr_dest_dir = f'{tmpdir}/{self.cruise_id}' if ':' in dest_dir else f'{dest_dir.rstrip("/")}/{self.cruise_id}'
            dry_cmd = build_rsync_command(dry_flags, None, self.cruise_dir, dr_dest_dir.rstrip('/') + '/',
                                          None, exclude_file)

            logging.debug("Dry run command: %s", transfer_utils.redact_command(dry_cmd))
            proc = subprocess.run(dry_cmd, capture_output=True, text=True, check=False)
            if proc.returncode not in transfer_utils.RSYNC_OK_CODES:
                # Otherwise it looks like "nothing to transfer" (#230)
                detail = error_detail('rsync', (proc.stdout + proc.stderr).splitlines())
                reason = f"Dry run failed: rsync exited with code {proc.returncode}"
                if detail:
                    reason += f": {detail}"
                logging.error(reason)
                return {'verdict': False, 'reason': reason}

            file_count = 0
            for line in proc.stdout.splitlines():
                if line.startswith('Number of regular files transferred:'):
                    file_count = int(line.split(':')[1].replace(',', ''))
                    logging.info("File Count: %d", file_count)
                    break

            if file_count == 0:
                logging.debug("Nothing to transfer")
                return {'verdict': True, 'files': files}

            try:
                # === USING RSYNC ===
                if transfer_type == 'rsync':
                    real_flags = build_rsync_options(cdt_cfg, mode='real', is_darwin=is_darwin)
                    real_cmd = build_rsync_command(real_flags, [f"--password-file={password_file}"],
                                                   self.cruise_dir, dest_dir.rstrip('/') + '/',
                                                   None, exclude_file)

                    files['new'], files['updated'], files['deleted'] = self.run_transfer_command(current_job, real_cmd, file_count)

                # === USING RCLONE === (local directories and SMB mounts, and
                # rclone remotes for SSH and FTP destinations)
                else:
                    self.make_cruise_dir(dest_dir, rclone_args)

                    copy_sync, flags = build_rclone_options(cdt_cfg, mode='real')
                    cmd = build_rclone_command(copy_sync, flags, rclone_args, self.cruise_dir,
                                               os.path.join(dest_dir, self.cruise_id),
                                               exclude_filepath=exclude_file)

                    logging.debug("Transfer command: %s", transfer_utils.redact_command(cmd))

                    files['new'], files['updated'], files['deleted'] = self.run_transfer_command(current_job, cmd, file_count)
            except TransferCommandError as exc:
                # Don't report a failed transfer as successful (#230)
                return {'verdict': False, 'reason': f"Transfer failed: {exc}"}

            # === PERMISSIONS (local only) ===
            if transfer_type == 'local' and ':' not in dest_dir and cdt_cfg.get('localDirIsMountPoint') == 0:
                logging.info("Setting file permissions")
                output = set_owner_group_permissions(
                    self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'],
                    os.path.join(dest_dir, self.cruise_id)
                )
                if not output['verdict']:
                    return output

        return {'verdict': True, 'files': files}


    def on_job_execute(self, current_job):
        """Set up and run a job for this worker's task.

        Reads the job's JSON payload (``cruiseDataTransfer``, ``cruiseID``,
        ``systemStatus``; any it omits default to the current cruise/lowering
        settings), loads what the task needs from the OpenVDM API, then runs
        the task handler.

        Args:
            current_job: The Gearman job.

        Returns:
            str: The job result: the task handler's JSON result, or an early
            failure result (e.g. if the payload can't be parsed).
        """
        self.stop = False

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("Payload: %s", current_job.data)

            cdt_id = payload_obj['cruiseDataTransfer']['cruiseDataTransferID']
            self.cruise_data_transfer = self.ovdm.get_cruise_data_transfer(cdt_id)

            if not self.cruise_data_transfer:
                self.cruise_data_transfer = {
                    'name': "UNKNOWN"
                }

                return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                      "Could not find configuration data for cruise data transfer")

        except Exception:
            logging.exception("Failed to retrieve cruise data transfer config")
            return self._fail_job(current_job, "Located Cruise Data Transfer Data",
                                  "Could not retrieve data for cruise data transfer from OpenVDM API")

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.cruise_data_transfer['name']}: %(message)s"
        ))

        # verify the transfer is NOT already in-progress
        if self.cruise_data_transfer['status'] == 1:
            logging.info("Transfer already in-progress for %s", self.cruise_data_transfer['name'])
            return self._ignore_job(current_job, "Transfer In-Progress", "Transfer is already in-progress")

        logging.info("Job Started: %s", current_job.handle)

        self.system_status = payload_obj.get('systemStatus', self.ovdm.get_system_status())
        self.cruise_data_transfer.update(payload_obj['cruiseDataTransfer'])

        if self.system_status == "Off" or self.cruise_data_transfer['enable'] == 0:
            logging.info("Transfer disabled for %s", self.cruise_data_transfer['name'])
            return self._ignore_job(current_job, "Transfer Enabled", "Transfer is disabled")

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """Handle an exception raised while running the job.

        Sets the cruise data transfer's status to error and sends it back to
        Gearman as a failed job part.

        Args:
            current_job: The Gearman job.
            exc_info: ``(type, value, traceback)`` of the exception.

        Returns:
            The base ``GearmanWorker`` exception result.
        """

        logging.error("Job Failed: %s", current_job.handle)

        exc_type, exc_value, exc_tb = exc_info
        # Report the frame that raised, not the outermost one (python3_gearman's worker.py)
        frame = traceback.extract_tb(exc_tb)[-1] if exc_tb else None
        fname = os.path.split(frame.filename)[1] if frame else "unknown"
        lineno = frame.lineno if frame else "?"
        logging.error("%s in %s line %s", exc_type, fname, lineno)

        exc_name = exc_type.__name__ if exc_type else "UnknownError"
        exc_msg = str(exc_value) if exc_value else ""
        location = f"{fname}, line {lineno}"
        reason = f"{exc_name}: {exc_msg} ({location})" if exc_msg else f"{exc_name} ({location})"

        self.send_job_data(current_job, json.dumps(
            [{"partName": "Worker crashed", "result": "Fail", "reason": reason}]
        ))

        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        if cdt_id:
            self.ovdm.set_error_cruise_data_transfer(cdt_id, f'Worker crashed: {reason}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """Record the job's outcome, then report completion to Gearman.

        The outcome is the last entry in the result's ``parts``: ``Fail`` sets
        the cruise data transfer's status to error, with that part's reason;
        ``Ignore`` leaves the status unchanged; anything else sets it to idle.

        Args:
            current_job: The Gearman job.
            job_result: The task handler's JSON result.

        Returns:
            The base ``GearmanWorker`` completion result.
        """

        results = json.loads(job_result)
        parts = results.get('parts', [])
        final_part = parts[-1] if parts else {}
        final_verdict = final_part.get("result", None)
        cdt_id = self.cruise_data_transfer.get('cruiseDataTransferID')

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job Completed: %s ", current_job.handle)

        if not cdt_id or not final_verdict or final_verdict == "Ignore":
            return super().send_job_complete(current_job, job_result)

        if final_verdict == "Fail":
            reason = final_part.get('reason', "undefined")
            self.ovdm.set_error_cruise_data_transfer(cdt_id, reason)
            return super().send_job_complete(current_job, job_result)

        # Always set idle at the end if not failed
        self.ovdm.set_idle_cruise_data_transfer(cdt_id)

        return super().send_job_complete(current_job, job_result)


    def stop_task(self):
        """
        Function to stop the current job
        """

        self.stop = True
        logging.warning("Stopping current task...")


    def quit_worker(self):
        """
        Function to quit the worker
        """

        self.stop = True
        logging.warning("Quitting worker...")
        self.shutdown()


    # --- Helper Methods ---
    def _fail_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as failed
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


    def _ignore_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as ignored
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}],
            'files': {'new': [], 'updated': [], 'exclude': []}
        }))


def task_run_cruise_data_transfer(worker, current_job):
    """Gearman task: run a cruise data transfer.

    Checks the transfer isn't already running and is enabled, tests the
    destination, then copies the cruise directory to it.

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        current_job: The Gearman job.

    Returns:
        str: JSON job results: ``parts`` (each with ``partName``, ``result``
        and, on failure, ``reason``) and ``files`` (the transferred files).
    """

    time.sleep(randint(0,2))

    cdt_cfg = worker.cruise_data_transfer

    job_results = {
        'parts': [
            {"partName": "Transfer in-Progress", "result": "Pass"},
            {"partName": "Transfer enabled", "result": "Pass"}
        ],
        'files':{}
    }

    logging.debug("Setting transfer status to 'Running'")
    worker.ovdm.set_running_cruise_data_transfer(cdt_cfg['cruiseDataTransferID'], os.getpid(), current_job.handle)

    logging.info("Testing destination")
    worker.send_job_status(current_job, 1, 100)

    results = worker.test_destination()

    if results[-1]['result'] == "Fail": # Final Verdict
        logging.warning("Connection test failed, quitting job")
        job_results['parts'].append({"partName": "Connection test", "result": "Fail", "reason": results[-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Connection test", "result": "Pass"})

    logging.info("Transferring files")
    worker.send_job_status(current_job, 2, 100)

    results = worker.transfer_to_destination(current_job)

    if not results['verdict']:
        logging.error("Transfer of remote files failed: %s", results['reason'])
        job_results['parts'].append({"partName": "Transfer files", "result": "Fail", "reason": results['reason']})
        return json.dumps(job_results)

    job_results['files'] = results['files']
    job_results['parts'].append({"partName": "Transfer files", "result": "Pass"})

    if len(job_results['files']['new']) > 0:
        logging.debug("%s file(s) added", len(job_results['files']['new']))
    if len(job_results['files']['updated']) > 0:
        logging.debug("%s file(s) updated", len(job_results['files']['updated']))
    if len(job_results['files']['exclude']) > 0:
        logging.debug("%s file(s) intentionally skipped", len(job_results['files']['exclude']))

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle cruise data transfer related tasks')
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
        """Handle SIGQUIT: stop the current task; the worker keeps running.

        Args:
            _signo: Signal number (unused).
            _stack_frame: Current stack frame (unused).
        """

        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("QUIT Signal Received")
        new_worker.stop_task()

    def sigint_handler(_signo, _stack_frame):
        """Handle SIGINT: stop the current task and shut down the worker.

        Args:
            _signo: Signal number (unused).
            _stack_frame: Current stack frame (unused).
        """

        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        logging.warning("INT Signal Received")
        new_worker.quit_worker()

    signal.signal(signal.SIGQUIT, sigquit_handler)
    signal.signal(signal.SIGINT, sigint_handler)

    logging.info("Registering worker tasks...")

    logging.info("\tTask: %s", TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'])
    new_worker.register_task(TASK_NAMES['RUN_CRUISE_DATA_TRANSFER'], task_run_cruise_data_transfer)

    logging.info("Waiting for jobs...")
    new_worker.work()
