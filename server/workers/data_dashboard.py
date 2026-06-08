#!/usr/bin/env python3
"""Gearman worker that builds and updates the OpenVDM data-dashboard objects.

Registers two Gearman tasks:

- ``updateDataDashboard`` — run every plugin that matches the new or updated
  files reported by a collection system transfer and write the resulting
  dashboard JSON to the cruise directory.
- ``rebuildDataDashboard`` — walk the entire cruise directory, run all matching
  plugins against every file, and fully regenerate all dashboard objects.

Plugins are discovered at start-up from the ``pluginDir`` path in
``openvdm.yaml``.  Each plugin module is imported via ``importlib`` and must
expose a class that subclasses
:py:class:`~server.lib.openvdm_plugin.OpenVDMPlugin`.
"""

import argparse
import importlib.util
import json
import logging
import os
import signal
import sys

import python3_gearman

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib.file_utils import build_filelist, output_json_data_to_file, set_owner_group_permissions
from server.lib.openvdm import OpenVDM

# PYTHON_BINARY = os.path.join(dirname(dirname(dirname(realpath(__file__)))), 'venv/bin/python')

TASK_NAMES = {
    'UPDATE_DATA_DASHBOARD': 'updateDataDashboard',
    'REBUILD_DATA_DASHBOARD': 'rebuildDataDashboard'
}

CUSTOM_TASKS = [
    {
        "taskID": 0,
        "name": TASK_NAMES['UPDATE_DATA_DASHBOARD'],
        "longName": "Updating data dashboard",
    }
]

class OVDMGearmanWorker(python3_gearman.GearmanWorker): # pylint: disable=too-many-instance-attributes
    """Gearman worker for data-dashboard generation and updates.

    Attributes:
        stop: Flag set to ``True`` to halt after the current job.
        ovdm: OpenVDM API client.
        task: Metadata dict for the task being processed.
        shipboard_data_warehouse_config: Warehouse configuration snapshot.
        cruise_id: Current cruise identifier.
        cruise_dir: Absolute path to the cruise data directory.
        lowering_id: Current lowering identifier, or ``None``.
        lowering_dir: Absolute path to the lowering data directory, or
            ``None`` when no lowering is active.
    """

    def __init__(self):
        self.stop = False
        self.ovdm = OpenVDM()
        self.task = None
        self.shipboard_data_warehouse_config = None
        self.cruise_id = None
        self.cruise_dir = None
        self.lowering_id = None
        self.lowering_dir = None
        self.data_dashboard_dir = None
        self.data_dashboard_manifest_file_path = None
        self.collection_system_transfer = None

        super().__init__(host_list=[self.ovdm.get_gearman_server()])

    @staticmethod
    def get_custom_task(current_job):
        task = list(filter(lambda task: task['name'] == current_job.task, CUSTOM_TASKS))
        return task[0] if len(task) > 0 else None

    def _get_plugin_callable(self, cfg=None):
        """
        Retrieve the Python plugin callable for a collection system transfer.
        """
        cst_cfg = cfg or self.collection_system_transfer
        plugin_name = cst_cfg['name'].lower()
        plugin_dir = self.ovdm.get_plugin_dir()
        plugin_suffix = self.ovdm.get_plugin_suffix()
        plugin_path = os.path.join(plugin_dir, f"{plugin_name}{plugin_suffix}")

        if not os.path.isfile(plugin_path):
            return None

        spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
        plugin_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin_module)

        if not hasattr(plugin_module, 'process_file'):
            logging.warning("Plugin %s does not have a 'process_file(raw_path)' function", plugin_name)
            return None

        return plugin_module.process_file

    def _build_paths(self, filename):
        json_filename = f'{os.path.splitext(filename)[0]}.json'
        raw_path = os.path.join(self.cruise_dir, filename)
        json_path = os.path.join(self.data_dashboard_dir, json_filename)
        return raw_path, json_path

    def _add_manifest_entry(self, entries, dd_type, json_path, raw_path, base_dir):
        rel_json = json_path.replace(f'{base_dir}/', '')
        rel_raw = raw_path.replace(f'{base_dir}/', '')
        entries.append({"type": dd_type, "dd_json": rel_json, "raw_data": rel_raw})

    def _remove_manifest_entry(self, entries, json_path, raw_path, base_dir):
        rel_json = json_path.replace(f'{base_dir}/', '')
        rel_raw = raw_path.replace(f'{base_dir}/', '')
        entries.append({"dd_json": rel_json, "raw_data": rel_raw})

    def _process_filelist(self, current_job, filelist, plugin_callable, job_results, start=0, end=100):
        """
        Process a list of files using a plugin callable.
        """
        base_dir = self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']
        new_manifest_entries = []
        remove_manifest_entries = []
        file_count = len(filelist)

        for idx, filename in enumerate(filelist):
            if self.stop:
                break

            raw_path, json_path = self._build_paths(filename)

            if not os.path.isfile(raw_path):
                job_results['parts'].append({"partName": f"Verify data file exists: {filename}", "result": "Fail", "reason": "File not found"})
                continue
            if os.stat(raw_path).st_size == 0:
                logging.warning("Skipping empty file: %s", filename)
                continue

            try:
                logging.info("Processing file: %s", filename)
                out_obj = plugin_callable(raw_path)
            except Exception as exc:
                logging.error("Error processing file %s: %s", filename, str(exc))
                job_results['parts'].append({"partName": f"Processing file: {filename}", "result": "Fail", "reason": str(exc)})
                self._remove_manifest_entry(remove_manifest_entries, json_path, raw_path, base_dir)
                continue

            if not out_obj or out_obj.get('error'):
                msg = out_obj.get('error', f"No output from plugin for file: {filename}")
                logging.warning(msg)
                self._remove_manifest_entry(remove_manifest_entries, json_path, raw_path, base_dir)
                continue

            result = output_json_data_to_file(json_path, out_obj)
            if result['verdict']:
                job_results['parts'].append({"partName": f"Write dashboard file: {filename}", "result": "Pass"})
            else:
                msg = f"Error writing dashboard file {filename}: {result['reason']}"
                logging.error(msg)
                job_results['parts'].append({"partName": f"Write dashboard file: {filename}", "result": "Fail", "reason": result['reason']})
                continue

            data_types = list(out_obj.keys()) or ['unknown']
            for dtype in data_types:
                self._add_manifest_entry(new_manifest_entries, dtype, json_path, raw_path, base_dir)

            progress = start + int((end - start) * idx / file_count)
            self.send_job_status(current_job, progress, 100)

        return new_manifest_entries, remove_manifest_entries

    def on_job_execute(self, current_job):
        self.stop = False
        try:
            payload_obj = json.loads(current_job.data)
            logging.debug("payload: %s", current_job.data)
        except Exception:
            return self._fail_job(current_job, "Retrieve job data", "Failed to parse current job payload")

        self.task = self.get_custom_task(current_job) or self.ovdm.get_task_by_name(current_job.task)

        # Configure logging
        logging.getLogger().handlers[0].setFormatter(logging.Formatter(
            f"%(asctime)-15s %(levelname)s - {self.task['longName']}: %(message)s"
        ))

        if int(self.task['taskID']) > 0:
            self.ovdm.set_running_task(self.task['taskID'], os.getpid(), current_job.handle)
        else:
            self.ovdm.track_gearman_job(self.task['longName'], os.getpid(), current_job.handle)

        logging.info("Job Started: %s", current_job.handle)

        self.shipboard_data_warehouse_config = self.ovdm.get_shipboard_data_warehouse_config()
        self.cruise_id = payload_obj.get('cruiseID', self.ovdm.get_cruise_id())
        self.cruise_dir = os.path.join(self.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir'], self.cruise_id)
        self.lowering_id = payload_obj.get('loweringID', self.ovdm.get_lowering_id())
        self.lowering_dir = os.path.join(self.cruise_dir, self.shipboard_data_warehouse_config['loweringDataBaseDir'], self.lowering_id) if self.lowering_id else None
        self.collection_system_transfer = self.ovdm.get_collection_system_transfer(payload_obj.get('collectionSystemTransferID')) if 'collectionSystemTransferID' in payload_obj else None
        self.data_dashboard_dir = os.path.join(self.cruise_dir, self.ovdm.get_required_extra_directory_by_name('Dashboard_Data')['destDir'])
        self.data_dashboard_manifest_file_path = os.path.join(self.data_dashboard_dir, self.shipboard_data_warehouse_config['dataDashboardManifestFn'])

        if current_job.task == TASK_NAMES['UPDATE_DATA_DASHBOARD'] and not self.collection_system_transfer:
            return self.on_job_complete(current_job, json.dumps({
                'parts':[{"partName": "Retrieve Collection System Transfer Data", "result": "Fail", "reason": "Could not find configuration data"}],
                'files': {'new':[], 'updated':[]}
            }))

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
        Function run when the current job completes.
        Handles updating task status, triggering post-tasks, and logging results.
        """
        try:
            payload_obj = json.loads(current_job.data)
            results = json.loads(job_result)
        except Exception as exc:
            logging.error("Failed to parse job data or results: %s", exc)
            results = {'parts': [], 'files': {}}
            payload_obj = {}

        job_data = {
            'cruiseID': self.cruise_id,
            'loweringID': self.lowering_id,
            'files': results.get('files', {})
        }

        gm_client = python3_gearman.GearmanClient([self.ovdm.get_gearman_server()])

        # Handle task-specific post-processing
        if current_job.task == TASK_NAMES['UPDATE_DATA_DASHBOARD']:
            job_data['collectionSystemTransferID'] = payload_obj.get('collectionSystemTransferID')
            for task in self.ovdm.get_tasks_for_hook(current_job.task):
                logging.info("Adding post-task: %s", task)
                gm_client.submit_job(task, json.dumps(job_data), background=True)

        elif current_job.task == TASK_NAMES['REBUILD_DATA_DASHBOARD']:
            for cs_cfg in self.ovdm.get_active_collection_system_transfers():
                job_data['collectionSystemTransferID'] = cs_cfg['collectionSystemTransferID']
                for task in self.ovdm.get_tasks_for_hook(TASK_NAMES['UPDATE_DATA_DASHBOARD']):
                    logging.info("Adding post-task: %s", task)
                    gm_client.submit_job(task, json.dumps(job_data), background=True)

        # Evaluate final verdict
        final_verdict = results.get('parts', [])[-1] if results.get('parts') else None
        if final_verdict and final_verdict.get('result') == "Fail":
            reason = final_verdict.get('reason', 'Unknown failure')
            if int(self.task['taskID']) > 0:
                self.ovdm.set_error_task(self.task['taskID'], reason)
            else:
                self.ovdm.send_msg(f"{self.task['longName']} failed", reason)
        else:
            if int(self.task['taskID']) > 0:
                self.ovdm.set_idle_task(self.task['taskID'])

        logging.debug("Job Results: %s", json.dumps(results, indent=2))
        logging.info("Job Completed: %s", current_job.handle)

        return super().send_job_complete(current_job, job_result)



    def _fail_job(self, current_job, part_name, reason):
        return self.on_job_complete(current_job, json.dumps({
            'parts': [{"partName": part_name, "result": "Fail", "reason": reason}]
        }))

    def stop_task(self):
        self.stop = True
        logging.warning("Stopping current task...")

    def quit_worker(self):
        self.stop = True
        logging.warning("Quitting worker...")
        self.shutdown()


# -------------------------
# Gearman task definitions
# -------------------------
def task_update_data_dashboard(worker, current_job):
    job_results = {'parts':[], 'files':{'new':[], 'updated':[], 'deleted':[]}}
    logging.info("Start of task")
    worker.send_job_status(current_job, 1, 10)

    plugin_callable = worker._get_plugin_callable()
    if plugin_callable is None:
        reason = f"Plugin not found for {worker.collection_system_transfer['name']}"
        logging.warning(reason)
        job_results['parts'].append({"partName": "Verify plugin", "result": "Ignore", "reason": reason})
        return json.dumps(job_results)
    job_results['parts'].append({"partName": "Verify plugin", "result": "Pass"})

    payload_obj = json.loads(current_job.data)
    filelist = payload_obj['files'].get('new', []) + payload_obj['files'].get('updated', [])
    if not filelist:
        reason = "No new or updated files to process"
        logging.warning(reason)
        job_results['parts'].append({"partName": "Retrieve file list", "result": "Ignore", "reason": reason})
        return json.dumps(job_results)
    job_results['parts'].append({"partName": "Retrieve file list", "result": "Pass"})

    new_entries, remove_entries = worker._process_filelist(current_job, filelist, plugin_callable, job_results, start=15, end=90)

    # Load existing manifest
    try:
        with open(worker.data_dashboard_manifest_file_path, 'r', encoding='utf-8') as f:
            existing_entries = json.load(f)
    except Exception:
        existing_entries = []

    # Remove obsolete entries
    base_dir = worker.shipboard_data_warehouse_config['shipboardDataWarehouseBaseDir']
    existing_entries_map = {e['raw_data']: e for e in existing_entries}
    for rm in remove_entries:
        if rm['raw_data'] in existing_entries_map:
            existing_entries.remove(existing_entries_map[rm['raw_data']])
            dd_json_path = os.path.join(base_dir, rm['dd_json'])
            if os.path.isfile(dd_json_path):
                os.remove(dd_json_path)

    # Update/add new entries
    for entry in new_entries:
        if not any(e['raw_data'] == entry['raw_data'] for e in existing_entries):
            existing_entries.append(entry)
            job_results['files']['new'].append(entry['dd_json'])
        else:
            job_results['files']['updated'].append(entry['dd_json'])

    # Write updated manifest
    result = output_json_data_to_file(worker.data_dashboard_manifest_file_path, existing_entries)
    if not result['verdict']:
        job_results['parts'].append({"partName": "Writing dashboard manifest file", "result": "Fail", "reason": result['reason']})
        return json.dumps(job_results)
    job_results['parts'].append({"partName": "Writing dashboard manifest file", "result": "Pass"})

    # Set permissions
    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.data_dashboard_dir)
    part_result = {"partName": "Set file/directory ownership", "result": "Pass" if output_results['verdict'] else "Fail"}
    if not output_results['verdict']:
        part_result['reason'] = output_results['reason']
    job_results['parts'].append(part_result)

    worker.send_job_status(current_job, 100, 100)
    return json.dumps(job_results)


def task_rebuild_data_dashboard(worker, current_job):
    job_results = {'parts':[], 'files':{'new':[], 'updated':[]}}
    logging.info("Rebuilding data dashboard")
    worker.send_job_status(current_job, 1, 100)

    if not os.path.exists(worker.data_dashboard_dir):
        reason = f"Data dashboard directory not found: {worker.data_dashboard_dir}"
        job_results['parts'].append({"partName": "Verify Data dashboard directory exists", "result": "Fail", "reason": reason})
        return json.dumps(job_results)
    job_results['parts'].append({"partName": "Verify Data dashboard directory exists", "result": "Pass"})

    manifest_entries = []
    active_csts = worker.ovdm.get_active_collection_system_transfers()
    for idx, cst in enumerate(active_csts, 1):
        plugin_callable = worker._get_plugin_callable(cfg=cst)
        if plugin_callable is None:
            logging.warning(f"No plugin for {cst['name']}, skipping")
            continue

        # Build file list
        if cst['cruiseOrLowering'] == 0:
            cst_dir = os.path.join(worker.cruise_dir, cst['destDir'])
            filelist = build_filelist(cst_dir).get('include', [])
            filelist = [os.path.join(cst['destDir'], f) for f in filelist]
        else:
            filelist = []
            lowerings = worker.ovdm.get_lowerings()
            for lowering in lowerings:
                cst_dir = os.path.join(worker.cruise_dir, worker.shipboard_data_warehouse_config['loweringDataBaseDir'], lowering, cst['destDir'])
                filelist.extend([os.path.join(worker.shipboard_data_warehouse_config['loweringDataBaseDir'], lowering, cst['destDir'], f) for f in build_filelist(cst_dir).get('include', [])])

        start = int(80 * idx / len(active_csts) + 10)
        end = int(80 * (idx + 1) / len(active_csts) + 10)
        new_entries, _ = worker._process_filelist(current_job, filelist, plugin_callable, job_results, start, end)
        manifest_entries.extend(new_entries)

    # Write updated manifest
    result = output_json_data_to_file(worker.data_dashboard_manifest_file_path, manifest_entries)
    if not result['verdict']:
        job_results['parts'].append({"partName": "Updating manifest file", "result": "Fail", "reason": result['reason']})
        return json.dumps(job_results)
    job_results['parts'].append({"partName": "Updating manifest file", "result": "Pass"})

    # Set permissions
    output_results = set_owner_group_permissions(worker.shipboard_data_warehouse_config['shipboardDataWarehouseUsername'], worker.data_dashboard_dir)
    part_result = {"partName": "Set file/directory ownership", "result": "Pass" if output_results['verdict'] else "Fail"}
    if not output_results['verdict']:
        part_result['reason'] = output_results['reason']
    job_results['parts'].append(part_result)

    worker.send_job_status(current_job, 100, 100)
    return json.dumps(job_results)


# -------------------------
# Main script
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle data dashboard related tasks')
    parser.add_argument('-v', '--verbosity', dest='verbosity', default=0, action='count', help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)
    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    worker = OVDMGearmanWorker()
    worker.set_client_id(__file__)

    signal.signal(signal.SIGQUIT, lambda s, f: worker.stop_task())
    signal.signal(signal.SIGINT, lambda s, f: worker.quit_worker())

    logging.info("Registering worker tasks...")
    worker.register_task(TASK_NAMES['UPDATE_DATA_DASHBOARD'], task_update_data_dashboard)
    worker.register_task(TASK_NAMES['REBUILD_DATA_DASHBOARD'], task_rebuild_data_dashboard)

    logging.info("Waiting for jobs...")
    worker.work()
