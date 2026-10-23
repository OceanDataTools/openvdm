#!/usr/bin/env python3
"""Gearman worker that initializes and finalizes OpenVDM lowerings.

Registers four Gearman tasks:

- ``setupNewLowering`` — create the lowering directory tree, initialize the
  MD5 summary for the lowering, set directory permissions, and export the
  lowering configuration and README.
- ``finalizeCurrentLowering`` — run pre-finalize hooks, update the MD5
  summary, apply directory permissions, export the lowering config and
  README, and run post-finalize hooks.
- ``exportLoweringConfig`` — write the current lowering configuration as JSON
  into the lowering directory, and the lowering README.
- ``rebuildLoweringReadme`` — rebuild the lowering README from its template.
"""

import argparse
import json
import logging
import os
import signal
import sys
import subprocess
import traceback
from os.path import dirname, realpath
import jinja2
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import output_json_data_to_file, set_owner_group_permissions
from server.workers.run_collection_system_transfer import TASK_NAMES as RUN_CDT_TASK_NAMES
from server.workers.lowering_directory import TASK_NAMES as LOWERING_DIR_TASK_NAMES
from server.lib.openvdm import OpenVDM
from server.lib.readme import (DEFAULT_LOWERING_TEMPLATE, build_lowering_readme_context, readme_filename,
                               readme_settings, render_readme, write_readme)
from server.lib.transfer_utils import redact_payload
from server.lib.transfer_jobs import report_missed, run_transfer_jobs
from server.lib.transfer_lock import CST

# Gearman task names this worker registers.
TASK_NAMES = {
    'CREATE_LOWERING': 'setupNewLowering',
    'FINALIZE_LOWERING': 'finalizeCurrentLowering',
    'EXPORT_LOWERING_CONFIG': 'exportLoweringConfig',
    'REBUILD_LOWERING_README': 'rebuildLoweringReadme'
}

class OVDMGearmanWorker(python3_gearman.GearmanWorker): # pylint: disable=too-many-instance-attributes
    """Gearman worker for lowering setup and finalization.

    Attributes:
        stop: Flag set to ``True`` to halt after the current job.
        ovdm: OpenVDM API client.
        task: Metadata dict for the task being processed.
        cruise_id: Current cruise identifier.
        lowering_id: Current lowering identifier.
        lowering_start_date: Start date of the current lowering.
        shipboard_data_warehouse_config: Warehouse configuration snapshot.
        lowering_dir: Absolute path to the lowering data directory.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.cruise_id = None
        self.lowering_id = None
        self.lowering_start_date = None
        self.shipboard_data_warehouse_config = None
        self.lowering_dir = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    def build_logfile_dirpath(self):
        """Return the transfer log directory, creating it if needed.

        Returns:
            str: The directory from ``OpenVDM.get_transfer_log_dir()``.
        """

        log_dir = self.ovdm.get_transfer_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        return log_dir


    def export_lowering_config(self, finalize=False):
        """Write the current lowering configuration to the lowering config file.

        Collection system transfer entries are reduced to their name, long
        name, description and destination directory (no credentials), and
        ``loweringExtent`` is left out while it isn't set. When
        the file already exists, its ``loweringFinalizedOn`` value is kept.
        Queues an MD5 summary update for the file.

        Args:
            finalize: Mark the configuration as finalized (sets
                ``loweringFinalizedOn``).

        Returns:
            dict: ``{'verdict': True}``, or ``{'verdict': False, 'reason':
            ...}``.
        """

        lowering_config_fn = self.shipboard_data_warehouse_config['loweringConfigFn']
        lowering_config_relfilepath = os.path.join(self.lowering_dir, lowering_config_fn)
        lowering_config_filepath = os.path.join(self.cruise_dir, lowering_config_relfilepath)
        lowering_config = self.ovdm.get_lowering_config()

        if finalize:
            lowering_config['loweringFinalizedOn'] = lowering_config['configCreatedOn']
        elif os.path.isfile(lowering_config_filepath):
            logging.debug("Reading existing configuration file")
            try:
                with open(lowering_config_filepath, mode='r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                # Not JSON (e.g. truncated) fails the export rather than losing the finalized date (#548)
                if not isinstance(existing_data, dict):
                    raise ValueError("not a JSON object")
                lowering_config['loweringFinalizedOn'] = existing_data.get('loweringFinalizedOn')
            except (OSError, ValueError) as exc:
                reason = f"Unable to read the existing configuration file {lowering_config_fn}: {exc}"
                logging.error(reason)
                return {'verdict': False, 'reason': reason}

        logging.debug(json.dumps(lowering_config))

        def _scrub_transfers(transfer_list):
            for transfer in transfer_list:

                allowed_keys = ['name', 'longName', 'description', 'destDir']
                for key in list(transfer.keys()):
                    if key not in allowed_keys:
                        transfer.pop(key)

        _scrub_transfers(lowering_config.get('collectionSystemTransfersConfig', []))

        # The lowering's bounding box (#399), left out until build_lowering_tracks sets it
        if not lowering_config.get('loweringExtent'):
            lowering_config.pop('loweringExtent', None)

        results = output_json_data_to_file(lowering_config_filepath, lowering_config)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], lowering_config_filepath)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        self.ovdm.update_md5_summary(updated=[lowering_config_relfilepath], cruise_id=self.cruise_id,
                                      background=False)

        return {'verdict': True}


    def build_lowering_readme(self):  # pylint: disable=too-many-locals,too-many-return-statements
        """Write the lowering README from its template (#445).

        Run after :meth:`export_lowering_config`: the lowering's details come
        from the config file it wrote, so the README matches it. The settings
        are the ``loweringReadme`` block of ``openvdm.yaml``
        (:func:`server.lib.readme.readme_settings`). A file with the README's
        name that OpenVDM didn't write is left alone. Queues an MD5 summary
        update for the README.

        Returns:
            dict: ``{'verdict': True}``, with ``'skipped': True`` when the
            README is turned off; or ``{'verdict': False, 'reason': ...}``.
        """

        try:
            settings = readme_settings(self.ovdm.config, 'loweringReadme', DEFAULT_LOWERING_TEMPLATE)
        except ValueError as exc:
            return {'verdict': False, 'reason': str(exc)}

        if not settings['enable']:
            logging.info("The lowering README is turned off (loweringReadme in openvdm.yaml)")
            return {'verdict': True, 'skipped': True}

        try:
            readme_fn = readme_filename(settings['filename'], self.cruise_id, self.lowering_id)
        except ValueError as exc:
            return {'verdict': False, 'reason': str(exc)}

        lowering_config_filepath = os.path.join(self.cruise_dir, self.lowering_dir,
                                                self.shipboard_data_warehouse_config['loweringConfigFn'])
        try:
            with open(lowering_config_filepath, 'r', encoding='utf-8') as f:
                lowering_config = json.load(f)
        except (OSError, ValueError) as exc:
            return {'verdict': False, 'reason': f"Unable to read the lowering config file: {exc}"}
        lowering_config['loweringID'] = self.lowering_id

        try:
            cruise_config = self.ovdm.get_cruise_config()
            collection_systems = self.ovdm.get_collection_system_transfers()
            extra_directories = self.ovdm.get_extra_directories()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return {'verdict': False, 'reason': f"Unable to get the configuration from OpenVDM: {exc}"}

        context = build_lowering_readme_context(
            lowering_config, cruise_config, collection_systems, extra_directories,
            self.ovdm.get_vessel_config(), readme_fn)

        try:
            text = render_readme(settings['template'], context)
        except (jinja2.TemplateError, OSError) as exc:
            line = f", line {exc.lineno}" if getattr(exc, 'lineno', None) else ''
            return {'verdict': False, 'reason': f"Unable to build the README from {settings['template']}{line}: {exc}"}

        readme_relpath = os.path.join(self.lowering_dir, readme_fn)
        readme_path = os.path.join(self.cruise_dir, readme_relpath)
        written, reason = write_readme(readme_path, text)
        if not written:
            return {'verdict': False, 'reason': reason}

        results = set_owner_group_permissions(self.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], readme_path)
        if not results['verdict']:
            return {'verdict': False, 'reason': results['reason']}

        self.ovdm.update_md5_summary(updated=[readme_relpath], cruise_id=self.cruise_id, background=False)

        return {'verdict': True}


    def on_job_execute(self, current_job):
        """Set up and run a job for this worker's task.

        Reads the job's JSON payload (``cruiseID``, ``loweringID``,
        ``loweringStartDate``, ``loweringEndDate``; any it omits default to the
        current cruise/lowering settings), loads what the task needs from the
        OpenVDM API, then runs the task handler.

        Args:
            current_job: The Gearman job.

        Returns:
            str: The job result: the task handler's JSON result, or an early
            failure result (e.g. if the payload can't be parsed).
        """

        self.stop = False
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        # The task comes from the job, not its payload: look it up first, so a
        # payload that can't be parsed fails this task (#544)
        self.task = self.ovdm.get_task_by_name(current_job.task)

        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", redact_payload(current_job.data))
        except Exception:
            reason = "Failed to parse current job payload"
            logging.exception(reason)
            return self._fail_job(current_job, "Retrieve job data", reason)

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)

        logging.info("Job Started: %s", current_job.handle)

        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())

        if not self.lowering_id:
            return self._fail_job(current_job, "Verify lowering ID", "Lowering ID is undefined")

        self.lowering_start_date = payload_obj.get('loweringStartDate', self.ovdm.get_lowering_start_date())
        self.lowering_end_date = payload_obj.get('loweringEndDate', self.ovdm.get_lowering_end_date())

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.lowering_dir = os.path.join(self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id)

        if current_job.task == TASK_NAMES['FINALIZE_LOWERING']:

            gm_data = {
                'cruiseID': self.cruise_id,
                'loweringID': self.lowering_id,
                'loweringStartDate': self.lowering_start_date,
                'loweringEndDate': self.lowering_end_date
            }

            # Collect pre-finalize jobs
            pre_finalize_jobs = []
            for task in self.ovdm.get_tasks_for_hook("preFinalizeCurrentLowering"):
                logging.info("Adding pre-finalize task: %s", task)
                pre_finalize_jobs.append({"task": task, "data": json.dumps(gm_data)})

            if not pre_finalize_jobs:
                logging.info("No pre-finalize tasks found, skipping.")
                return super().on_job_execute(current_job)

            # Submit jobs to Gearman
            gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

            try:
                submitted_job_requests = gm_client.submit_multiple_jobs(
                    pre_finalize_jobs,
                    background=False,
                    wait_until_complete=False,  # we'll handle completion below
                )

                # Wait until all jobs complete
                gm_client.wait_until_jobs_completed(submitted_job_requests)

                # Log results
                for job in submitted_job_requests:
                    if job.complete:
                        logging.info("Task %s completed successfully", job.job.unique)
                    elif job.timed_out:
                        logging.error("Task %s timed out", job.job.unique)
                    else:
                        logging.error("Task %s failed: %s", job.job.unique, job.exception)

            except Exception as e:
                logging.exception("Error while submitting or running pre-finalize jobs: %s", e)

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """Handle an exception raised while running the job.

        Sets the task's status to error and sends it back to Gearman as a
        failed job part.

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

        if int(self.task['taskID']) > 0:
            self.ovdm.set_error_task(self.task['taskID'], f'Worker crashed: {reason}')
        else:
            self.ovdm.send_msg(f"{self.task['longName']} failed", f'Worker crashed: {reason}')

        return super().on_job_exception(current_job, exc_info)


    def on_job_complete(self, current_job, job_result):
        """Record the job's outcome, then report completion to Gearman.

        The outcome is the last entry in the result's ``parts``: ``Fail`` sets
        the task's status to error, with that part's reason; anything else sets
        it to idle. Tasks with an ID of 0 (this worker's ``CUSTOM_TASKS``) have
        no status in OpenVDM.

        After a lowering is set up or finalized, submits the hook tasks
        configured for that task in ``openvdm.yaml``.

        Args:
            current_job: The Gearman job.
            job_result: The task handler's JSON result.

        Returns:
            The base ``GearmanWorker`` completion result.
        """

        results = json.loads(job_result)

        if current_job.task in (TASK_NAMES['CREATE_LOWERING'], TASK_NAMES['FINALIZE_LOWERING']):

            gm_data = {
                'cruiseID': self.cruise_id,
                'loweringID': self.lowering_id,
                'loweringStartDate': self.lowering_start_date,
                'loweringEndDate': self.lowering_end_date
            }

            # Collect pre-finalize jobs
            post_hook_jobs = []
            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post-hook task: %s", task)
                post_hook_jobs.append({"task": task, "data": json.dumps(gm_data)})

            # Without hook tasks, go on to complete the job (#547)
            if not post_hook_jobs:
                logging.info("No post-hook tasks found, skipping.")
            else:
                # Submit jobs to Gearman
                gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

                try:
                    submitted_job_requests = gm_client.submit_multiple_jobs(
                        post_hook_jobs,
                        background=False,
                        wait_until_complete=False,  # we'll handle completion below
                    )

                    # Wait until all jobs complete
                    gm_client.wait_until_jobs_completed(submitted_job_requests)

                    # Log results
                    for job in submitted_job_requests:
                        if job.complete:
                            logging.info("Task %s completed successfully", job.job.unique)
                        elif job.timed_out:
                            logging.error("Task %s timed out", job.job.unique)
                        else:
                            logging.error("Task %s failed: %s", job.job.unique, job.exception)

                except Exception as e:
                    logging.exception("Error while submitting or running post-hook jobs: %s", e)

        parts = results.get('parts', [])
        final_verdict = parts[-1] if parts else None

        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', 'Unknown failure')
            if int(self.task['taskID']) > 0:
                self.ovdm.set_error_task(self.task['taskID'], reason)
            else:
                self.ovdm.send_msg(f"{self.task['longName']} failed", reason)
        else:
            self.ovdm.set_idle_task(self.task['taskID'])

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job Completed: %s", current_job.handle)

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
        shortcut for completing the current job as failed
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


def _add_readme_part(worker, job_results):
    """Write the lowering README and add the result to *job_results*.

    Nothing is added when the README is turned off. The README comes after
    the config export, the last step these tasks report, so a failure here
    is the task's outcome: its status and reason say what went wrong.

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        job_results: The job's results; a ``Write lowering README`` part is
            appended.
    """

    logging.info("Writing the lowering README")
    output_results = worker.build_lowering_readme()

    if output_results.get('skipped'):
        return

    if output_results['verdict']:
        job_results['parts'].append({"partName": "Write lowering README", "result": "Pass"})
        return

    logging.error("Unable to write the lowering README: %s", output_results['reason'])
    job_results['parts'].append({"partName": "Write lowering README", "result": "Fail", "reason": output_results['reason']})


def task_setup_new_lowering(worker, current_job):
    """Gearman task: set up a new lowering.

    Creates the lowering directory structure, and exports the lowering config
    and writes the lowering README.

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        current_job: The Gearman job.

    Returns:
        str: JSON job results: ``parts`` (each with ``partName``, ``result``
        and, on failure, ``reason``).
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    logging.info("Creating lowering data directory")
    worker.send_job_status(current_job, 2, 10)

    completed_job_request = gm_client.submit_job(LOWERING_DIR_TASK_NAMES['CREATE_LOWERING_DIRECTORY'], current_job.data)

    results = json.loads(completed_job_request.result)

    if results['parts'][-1]['result'] == "Fail": # Final Verdict
        logging.error("Failed to create lowering data directory")
        job_results['parts'].append({"partName": "Create lowering data directory structure", "result": "Fail", "reason": results['parts'][-1]['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Create lowering data directory structure", "result": "Pass"})


    logging.info("Exporting lowering configuration")
    worker.send_job_status(current_job, 5, 10)

    output_results = worker.export_lowering_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    _add_readme_part(worker, job_results)

    logging.info("Updating lowering size")
    worker.send_job_status(current_job, 9, 10)

    lowering_size_proc = subprocess.run(['du','-sb', os.path.join(worker.cruise_dir, worker.lowering_dir)], capture_output=True, text=True, check=False)
    if lowering_size_proc.returncode == 0:
        logging.debug("Lowering Size: %s", lowering_size_proc.stdout.split()[0])
        worker.ovdm.set_lowering_size(lowering_size_proc.stdout.split()[0])
    else:
        worker.ovdm.set_lowering_size("0")

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)

def task_finalize_current_lowering(worker, current_job):
    """Gearman task: finalize the current lowering.

    Checks the lowering directory exists, runs the lowering's collection system
    transfers one last time, exports the finalized lowering config, and writes
    the lowering README. A transfer that another job is running gets its last
    run once that job ends; one still running after an hour is reported in an
    OpenVDM message and skipped (#480).

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        current_job: The Gearman job.

    Returns:
        str: JSON job results: ``parts`` (each with ``partName``, ``result``
        and, on failure, ``reason``).
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    full_lowering_dir = os.path.join(worker.cruise_dir, worker.lowering_dir)

    if not os.path.exists(full_lowering_dir):
        reason = f"Lowering directory does not exist: {worker.lowering_dir}"
        logging.error(reason)
        job_results['parts'].append({"partName": "Verify lowering directory exists", "result": "Fail", "reason": reason})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Verify lowering directory exists", "result": "Pass"})

    logging.info("Queuing collection system transfers jobs")
    worker.send_job_status(current_job, 2, 10)

    gm_client = python3_gearman.GearmanClient([worker.ovdm.get_gearman_server()])

    gm_data = {
        'loweringID': worker.lowering_id,
        'loweringStartDate': worker.lowering_start_date,
        'loweringEndDate': worker.lowering_end_date,
        'systemStatus': "On",
        'collectionSystemTransfer': {}
    }

    collection_system_transfer_jobs = {}
    collection_system_transfers = worker.ovdm.get_active_collection_system_transfers(cruise=False)

    for collection_system_transfer in collection_system_transfers:
        logging.debug("Queuing %s job for %s", RUN_CDT_TASK_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'], collection_system_transfer['name'])
        cst_id = collection_system_transfer['collectionSystemTransferID']
        collection_system_transfer_jobs[cst_id] = {**gm_data, 'collectionSystemTransfer': {'collectionSystemTransferID': cst_id}}

    logging.info("Submitting %s jobs", RUN_CDT_TASK_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'])
    worker.send_job_status(current_job, 3, 10)

    # A transfer another job is running gets its final pass once that job
    # ends (#480)
    missed = run_transfer_jobs(gm_client, RUN_CDT_TASK_NAMES['RUN_COLLECTION_SYSTEM_TRANSFER'], CST,
                               collection_system_transfer_jobs,
                               should_stop=lambda: worker.stop)

    if worker.stop:
        # Stopped during the transfers' final pass: end here, so the task
        # goes back to Idle without going on to the next steps (#487)
        job_results['parts'].append({"partName": "Run collection system transfers jobs", "result": "Ignore", "reason": "Stopped"})
        return json.dumps(job_results)

    if missed:
        report_missed(worker.ovdm, job_results, f"Finalizing {worker.lowering_id}: collection system transfers still running",
                      "Final pass of collection system transfers",
                      [cst['name'] for cst in collection_system_transfers if cst['collectionSystemTransferID'] in missed])

    job_results['parts'].append({"partName": "Run collection system transfers jobs", "result": "Pass"})

    logging.info("Exporting lowering configuration")
    worker.send_job_status(current_job, 9, 10)

    output_results = worker.export_lowering_config(finalize=True)

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    _add_readme_part(worker, job_results)

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_export_lowering_config(worker, current_job):
    """Gearman task: write the lowering config file and the lowering README.

    Exports the current lowering configuration to the lowering's config file
    (``loweringConfigFn``), writes the lowering README (#445), and queues MD5
    summary updates for both.

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        current_job: The Gearman job.

    Returns:
        str: JSON job results: ``parts`` (each with ``partName``, ``result``
        and, on failure, ``reason``).
    """

    job_results = {'parts':[]}

    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.export_lowering_config()

    if not output_results['verdict']:
        job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Fail", "reason": output_results['reason']})
        return json.dumps(job_results)

    job_results['parts'].append({"partName": "Export lowering config data to file", "result": "Pass"})

    _add_readme_part(worker, job_results)

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


def task_rebuild_lowering_readme(worker, current_job):
    """Gearman task: rebuild the lowering README from its template (#445).

    For changes the README would otherwise only pick up at the next config
    export, e.g. an edited template or a directory's new description. A
    README that OpenVDM didn't write is still left alone. When the README is
    turned off in ``openvdm.yaml``, the task fails and says so, since nothing
    was rebuilt.

    Args:
        worker: The worker, set up by ``on_job_execute()``.
        current_job: The Gearman job.

    Returns:
        str: JSON job results: ``parts`` (each with ``partName``, ``result``
        and, on failure, ``reason``).
    """

    job_results = {'parts':[]}

    logging.info("Rebuilding the lowering README")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.build_lowering_readme()

    if output_results.get('skipped'):
        job_results['parts'].append({"partName": "Write lowering README", "result": "Fail",
                                     "reason": "The lowering README is turned off (loweringReadme in openvdm.yaml)"})
    elif not output_results['verdict']:
        job_results['parts'].append({"partName": "Write lowering README", "result": "Fail", "reason": output_results['reason']})
    else:
        job_results['parts'].append({"partName": "Write lowering README", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle Lowering-Level tasks')
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

    # global new_worker
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

    logging.info("\tTask: %s", TASK_NAMES['CREATE_LOWERING'])
    new_worker.register_task(TASK_NAMES['CREATE_LOWERING'], task_setup_new_lowering)

    logging.info("\tTask: %s", TASK_NAMES['FINALIZE_LOWERING'])
    new_worker.register_task(TASK_NAMES['FINALIZE_LOWERING'], task_finalize_current_lowering)

    logging.info("\tTask: %s", TASK_NAMES['EXPORT_LOWERING_CONFIG'])
    new_worker.register_task(TASK_NAMES['EXPORT_LOWERING_CONFIG'], task_export_lowering_config)

    logging.info("\tTask: %s", TASK_NAMES['REBUILD_LOWERING_README'])
    new_worker.register_task(TASK_NAMES['REBUILD_LOWERING_README'], task_rebuild_lowering_readme)

    logging.info("Waiting for jobs...")
    new_worker.work()
