#!/usr/bin/env python3
"""Gearman worker that runs user-defined post-hook shell commands.

Registers eight Gearman tasks that fire after key OpenVDM lifecycle events:

- ``postCollectionSystemTransfer`` — after a collection system transfer
- ``postDataDashboard`` — after the data-dashboard update
- ``postSetupNewCruise`` / ``postSetupNewLowering`` — after cruise/lowering creation
- ``preFinalizeCurrentCruise`` / ``postFinalizeCurrentCruise`` — around cruise finalization
- ``preFinalizeCurrentLowering`` / ``postFinalizeCurrentLowering`` — around lowering finalization

Hook commands are configured in ``openvdm.yaml`` under ``postHookCommands``.
Token substitution (``{cruiseID}``, ``{loweringID}``, ``{newFiles}``,
``{updatedFiles}``, etc.) is applied before each command is executed.
"""

import argparse
import json
import logging
import os
import signal
import sys
import copy
import subprocess
from os.path import dirname, realpath
import python3_gearman

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.openvdm import OpenVDM

TASK_NAMES = {
    'POST_RUN_COLLECTION_SYSTEM_TRANSFER_HOOK': 'postCollectionSystemTransfer',
    'POST_UPDATE_DATA_DASHBOARD_HOOK': 'postDataDashboard',
    'POST_CREATE_CRUISE_HOOK': 'postSetupNewCruise',
    'POST_CREATE_LOWERING_HOOK': 'postSetupNewLowering',
    'PRE_FINALIZE_CRUISE_HOOK': 'preFinalizeCurrentCruise',
    'POST_FINALIZE_CRUISE_HOOK': 'postFinalizeCurrentCruise',
    'PRE_FINALIZE_LOWERING_HOOK': 'preFinalizeCurrentLowering',
    'POST_FINALIZE_LOWERING_HOOK': 'postFinalizeCurrentLowering'
}

CUSTOM_TASKS = [
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_RUN_COLLECTION_SYSTEM_TRANSFER_HOOK'],
        "longName": "Post collection system transfer",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_UPDATE_DATA_DASHBOARD_HOOK'],
        "longName": "Post data dashboard processing",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_CREATE_CRUISE_HOOK'],
        "longName": "Post setup new cruise",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_CREATE_LOWERING_HOOK'],
        "longName": "Post setup new lowering",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['PRE_FINALIZE_CRUISE_HOOK'],
        "longName": "Pre-finalize current cruise",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_FINALIZE_CRUISE_HOOK'],
        "longName": "Post-finalize current cruise",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['PRE_FINALIZE_LOWERING_HOOK'],
        "longName": "Pre-finalize current lowering",
    },
    {
        "taskID": 0,
        "name": TASK_NAMES['POST_FINALIZE_LOWERING_HOOK'],
        "longName": "Post-finalize current lowering",
    }
]

class OVDMGearmanWorker(python3_gearman.GearmanWorker): # pylint: disable=too-many-instance-attributes
    """Gearman worker that executes configured post-hook shell commands.

    Attributes:
        stop: Flag set to ``True`` when the worker should halt after the
            current job.
        ovdm: OpenVDM API client.
        task: Metadata dict for the task being processed.
        files: Dict with ``new`` and ``updated`` file-path lists from the
            triggering transfer, used for ``{newFiles}``/``{updatedFiles}``
            token substitution.
        cruise_id: Current cruise identifier, used for ``{cruiseID}`` tokens.
        lowering_id: Current lowering identifier, used for ``{loweringID}``
            tokens.
        shipboard_data_warehouse_config: Warehouse configuration snapshot.
        job_data: Parsed JSON payload from the incoming Gearman job.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.files = None
        self.cruise_id = None
        self.lowering_id = None
        self.shipboard_data_warehouse_config = None

        self.job_data = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])


    @staticmethod
    def _get_custom_task(current_job):
        """
        Fetch task metadata
        """

        return next((task for task in CUSTOM_TASKS if task['name'] == current_job.task), None)


    @staticmethod
    def _run_command(command):
        """
        Run the commands in the command_list
        """

        try:
            logging.debug("Command: %s", ' '.join(command['command']))
            proc = subprocess.run(command['command'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

            if len(proc.stdout) > 0:
                logging.debug("stdout: %s", proc.stdout)

            if len(proc.stderr) > 0:
                logging.debug("stderr: %s", proc.stderr)

        except Exception as exc:
            reason = f"Error executing {command['name']}: {' '.join(command['command'])}"
            logging.error(reason)
            logging.debug(str(exc))
            return {"verdict": False, "reason": reason}

        return {"verdict": True}


    def _build_commands(self, command_list: list, cst_cfg: dict = None) -> list:
        """Apply token substitution to a list of command dicts.

        Replaces placeholder tokens in each command argument with runtime
        values (cruise ID, lowering ID, transfer ID/name, new/updated file
        lists).  Empty arguments produced by substitution are dropped.

        Args:
            command_list: List of command dicts, each with ``name`` and
                ``command`` (list of argument strings) keys.
            cst_cfg: Optional collection system transfer config dict; required
                to resolve ``{collectionSystemTransferID}`` and
                ``{collectionSystemTransferName}`` tokens.

        Returns:
            A deep-copied command list with tokens substituted, or ``None``
            if *command_list* is falsy.
        """

        if not command_list:
            return None

        command_list = copy.deepcopy(command_list)

        def _replace_tokens(text, replacements):
            for token, value in replacements.items():
                text = text.replace(token, value)
            return text

        # Build replacements dict conditionally
        replacements = {
            '{cruiseID}': self.cruise_id,
            '{loweringID}': self.lowering_id,
            '{collectionSystemTransferID}':
                str(cst_cfg.get('collectionSystemTransferID')) if isinstance(cst_cfg, dict) else None,

            '{collectionSystemTransferName}':
                cst_cfg.get('name') if isinstance(cst_cfg, dict) else None,

            '{newFiles}': ' '.join(self.files.get('new', [])) if self.files else None,
            '{updatedFiles}': ' '.join(self.files.get('updated', [])) if self.files else None
        }

        # Remove only None (not empty strings)
        replacements = {k: v for k, v in replacements.items() if v is not None}

        for command in command_list:
            logging.debug("Raw Command: %s", json.dumps(command))
            command['command'] = [
                _replace_tokens(arg, replacements) for arg in command['command']
            ]
            command['command'] = [s for s in command['command'] if s.strip() != ""]

        logging.debug("Processed Command: %s", json.dumps(command_list))
        return command_list


    def get_command_list(self):
        """
        Retrieve list of commands for the specified hook_name
        """

        if not self.hook_commands:
            return {'verdict': True, 'commandList': None}

        cst_cfg = None

        if self.task['name'] in [
            TASK_NAMES['POST_RUN_COLLECTION_SYSTEM_TRANSFER_HOOK'],
            TASK_NAMES['POST_UPDATE_DATA_DASHBOARD_HOOK']
        ]:
            cst_cfg = self.ovdm.get_collection_system_transfer(self.job_data.get('collectionSystemTransferID'))
            if not cst_cfg:
                return {'verdict': False, 'reason': 'Could not find collection system transfer'}

            command_list = next(
                (x.get('commandList') for x in self.hook_commands
                 if x.get('collectionSystemTransferName') == cst_cfg['name']),
                None
            )
        else:
            command_list = self.hook_commands.get('commandList')

        return {"verdict": True, "commandList": self._build_commands(command_list, cst_cfg)}


    def on_job_execute(self, current_job):
        """
        Function run when a new job arrives
        """
        self.stop = False
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(LOGGING_FORMAT))

        try:
            self.job_data = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)
        except Exception:
            reason = "Failed to parse current job payload"
            logging.exception(reason)
            return self._fail_job(current_job, "Retrieve job data", reason)

        self.task = self._get_custom_task(current_job) or self.ovdm.get_task_by_name(current_job.task)
        if not self.task:
            return self._fail_job(current_job, "Retrieve task", "Task not found")

        # Set logging format with cruise transfer name
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        self.hook_commands = self.ovdm.get_post_hook_commands(self.task.get('name'))

        logging.debug("post-hook commands: %s", self.hook_commands)

        if not self.hook_commands:
            return self._ignore_job(current_job, "Retrieve commands", "No commands found")

        self.ovdm.track_gearman_job(self.task['longName'], os.getpid(), current_job.handle)

        logging.info("Job Started: %s", current_job.handle)

        self.cruise_id = self.job_data['cruiseID'] if 'cruiseID' in self.job_data else self.ovdm.get_cruise_id()
        self.lowering_id = self.job_data['loweringID'] if 'loweringID' in self.job_data else self.ovdm.get_lowering_id()

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()

        self.files = self.job_data['files'] if 'files' in self.job_data else { 'new':[], 'updated':[] }

        return super().on_job_execute(current_job)


    def on_job_exception(self, current_job, exc_info):
        """
        Function run when the current job has an exception
        """

        logging.error("Job Failed: %s", current_job.handle)

        exc_type, exc_value, exc_tb = exc_info
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb else "unknown"
        lineno = exc_tb.tb_lineno if exc_tb else "?"
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
        """
        Function run when the current job completes
        """

        results = json.loads(job_result)
        parts = results.get('parts', [])
        final_part = parts[-1] if parts else {}
        final_verdict = final_part.get("result", None)

        if not final_verdict or final_verdict == "Ignore":
            return super().send_job_complete(current_job, job_result)

        if final_verdict == "Fail":
            reason = final_part.get('reason', 'Unknown failure')
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
        Shortcut for completing the current job as failed
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))


    def _ignore_job(self, current_job, part_name, reason):
        """
        Shortcut for completing the current job as ignored
        """

        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Ignore", "reason": reason}]
        }))


def task_post_hook(worker: OVDMGearmanWorker, current_job) -> str:
    """Gearman task handler: retrieve and execute configured post-hook commands.

    Fetches the command list for the active hook, performs token substitution
    via :py:meth:`OVDMGearmanWorker.get_command_list`, then runs each command
    in sequence.  A job is marked ``Ignore`` when no commands are configured,
    ``Fail`` if any command exits with an error, and ``Pass`` otherwise.

    Args:
        worker: The active :py:class:`OVDMGearmanWorker` instance.
        current_job: The Gearman job object provided by the framework.

    Returns:
        JSON-encoded results dict with a ``parts`` list indicating Pass/Fail/Ignore
        for each step.
    """

    job_results = {'parts':[]}

    logging.info("Retrieving commands")
    worker.send_job_status(current_job, 1, 10)

    output_results = worker.get_command_list()

    if not output_results['verdict']:
        return json.dumps({
            'parts': [{"partName": 'Get command list', "result": "Fail", "reason": output_results['reason']}]
        })

    logging.debug("Command list: %s", json.dumps(output_results['commandList'], indent=2))

    if not output_results['commandList']:
        return json.dumps({
            'parts': [{"partName": 'Running commands', "result": "Ignore", "reason": "No commands found"}]
        })

    job_results['parts'].append({"partName": "Get Commands", "result": "Pass"})

    logging.info("Running commands")
    worker.send_job_status(current_job, 2, 10)

    reasons = []

    cmd_length = len(output_results['commandList'])
    for idx, cmd in enumerate(output_results['commandList']):
        worker.send_job_status(current_job, int(80 * (idx+1)/cmd_length) + 20, 100)

        logging.info("Executing: %s", cmd['name'])
        output_results = worker._run_command(cmd)

        if not output_results['verdict']:
            reasons.append(output_results['reason'])

    if len(reasons) > 0:
        job_results['parts'].append({"partName": "Running commands", "result": "Fail", "reason": '\n'.join(reasons)})
    else:
        job_results['parts'].append({"partName": "Running commands", "result": "Pass"})

    worker.send_job_status(current_job, 10, 10)
    return json.dumps(job_results)


# -------------------------------------------------------------------------------------
# Required python code for running the script as a stand-alone utility
# -------------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle post-hook processes')
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

    logging.info("\tTask: %s", TASK_NAMES['POST_RUN_COLLECTION_SYSTEM_TRANSFER_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_RUN_COLLECTION_SYSTEM_TRANSFER_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['POST_UPDATE_DATA_DASHBOARD_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_UPDATE_DATA_DASHBOARD_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['POST_CREATE_CRUISE_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_CREATE_CRUISE_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['POST_CREATE_LOWERING_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_CREATE_LOWERING_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['PRE_FINALIZE_CRUISE_HOOK'])
    new_worker.register_task(TASK_NAMES['PRE_FINALIZE_CRUISE_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['POST_FINALIZE_CRUISE_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_FINALIZE_CRUISE_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['PRE_FINALIZE_LOWERING_HOOK'])
    new_worker.register_task(TASK_NAMES['PRE_FINALIZE_LOWERING_HOOK'], task_post_hook)

    logging.info("\tTask: %s", TASK_NAMES['POST_FINALIZE_LOWERING_HOOK'])
    new_worker.register_task(TASK_NAMES['POST_FINALIZE_LOWERING_HOOK'], task_post_hook)

    logging.info("Waiting for jobs...")
    new_worker.work()
