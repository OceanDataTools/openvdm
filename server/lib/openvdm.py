#!/usr/bin/env python3
"""
FILE:  openvdm.py

DESCRIPTION:  OpenVDM python module

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.10
  CREATED:  2016-02-02
 REVISION:  2025-04-12
"""

import datetime
import json
import logging
import sys
from os.path import dirname, realpath, join
import requests

sys.path.append(dirname(dirname(dirname(realpath(__file__)))))

from server.lib import read_config

DEFAULT_CONFIG_FILE = join(dirname(dirname(dirname(realpath(__file__)))), 'server/etc/openvdm.yaml')

TIMEOUT = 5

class OpenVDM():
    """
    Class is a python wrapper around the OpenVDM API
    """

    def __init__(self, config_file = DEFAULT_CONFIG_FILE):

        self.config = read_config.read_config(config_file)


    def clear_gearman_jobs_from_db(self):
        """
        Clear the current Gearman job request queue.
        """

        url = self.config['siteRoot'] + 'api/gearman/clearAllJobsFromDB'

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to clear Gearman Jobs from OpenVDM API")
            raise err


    def get_plugin_dir(self):
        """
        Return the directory containing the OpenVDM plugins.
        """

        return self.config['plugins']['pluginDir']


    def get_plugin_suffix(self):
        """
        Return the plugin suffix.
        """

        return self.config['plugins']['pluginSuffix']


    def show_only_current_cruise_dir(self):
        """
        Return whether OpenVDM is configured to only show the current cruise data
        directory.
        """

        return self.config['showOnlyCurrentCruiseDir']


    def get_show_lowering_components(self):
        """
        Return whether OpenVDM should show lowering-related components
        """

        url = self.config['siteRoot'] + 'api/warehouse/getShowLoweringComponents'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return req.text == 'true'
        except Exception as err:
            logging.error("Unable to retrieve 'showLoweringComponents' flag from OpenVDM API")
            raise err


    def get_cruise_config(self):
        """
        Return the current cruise configuration
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseConfig'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return_obj['configCreatedOn'] = datetime.datetime.utcnow().strftime("%Y/%m/%dT%H:%M:%SZ")
            return return_obj
        except Exception as err:
            logging.error("Unable to retrieve cruise configuration from OpenVDM API")
            raise err


    def get_lowering_config(self):
        """
        Return the configuration for the current lowering
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringConfig'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return_obj['configCreatedOn'] = datetime.datetime.utcnow().strftime("%Y/%m/%dT%H:%M:%SZ")
            return return_obj
        except Exception as err:
            logging.error("Unable to retrieve lowering configuration from OpenVDM API")
            raise err


    def get_gearman_server(self):
        """
        Return the ip/port for the Gearman server
        """

        return self.config['gearmanServer']


    def get_site_root(self):
        """
        Return the site root for the OpenVDM data warehouse
        """

        return self.config['siteRoot']


    def get_transfer_public_data(self):
        """
        Return whether to transfer the contents of PublicData to the cruise
        data directory
        """

        return self.config['transferPubicData']


    def get_md5_filesize_limit(self):
        """
        Return the MD5 filesize limit
        """

        url = self.config['siteRoot'] + 'api/warehouse/getMD5FilesizeLimit'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5FilesizeLimit')
        except Exception as err:
            logging.error("Unable to retrieve MD5 filesize limit from OpenVDM API")
            raise err


    def get_md5_filesize_limit_status(self):
        """
        Return whether the MD5 filesize limit should be applied
        """

        url = self.config['siteRoot'] + 'api/warehouse/getMD5FilesizeLimitStatus'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5FilesizeLimitStatus')
        except Exception as err:
            logging.error("Unable to retrieve MD5 filesize limit status from OpenVDM API")
            raise err


    def get_md5_summary_fn(self):
        """
        Return the MD5 summary filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getMD5SummaryFn'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5SummaryFn')
        except Exception as err:
            logging.error("Unable to retrieve MD5 summary filename from OpenVDM API")
            raise err


    def get_md5_summary_md5_fn(self):
        """
        Return the MD5 summary MD5 filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getMD5SummaryMD5Fn'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5SummaryMd5Fn')
        except Exception as err:
            logging.error("Unable to retrieve MD5 summary MD5 filename from OpenVDM API")
            raise err


    def get_tasks_for_hook(self, hook_name):
        """
        Return the tasks associated with the given hook
        """

        return self.config['hooks'].get(hook_name, [])


    def get_post_hook_commands(self, post_hook_name):

        post_hook_commands = self.config.get('postHookCommands', {})
        return post_hook_commands.get(post_hook_name)


    def get_transfer_interval(self):
        """
        Return the transfer interval
        """

        return self.config.get('transferInterval')


    def get_cruise_id(self):
        """
        Return the current cruise id
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseID'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseID')
        except Exception as err:
            logging.error("Unable to retrieve CruiseID from OpenVDM API")
            raise err


    def get_cruise_size(self):
        """
        Return the filesize for the current cruise
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseSize'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve cruise size from OpenVDM API")
            raise err


    def get_cruise_start_date(self):
        """
        Return the start date for the current criuse
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseStartDate'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseStartDate')
        except Exception as err:
            logging.error("Unable to retrieve cruise start date from OpenVDM API")
            raise err


    def get_cruise_end_date(self):
        """
        Return the end date for the current criuse
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseEndDate'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseEndDate')
        except Exception as err:
            logging.error("Unable to retrieve cruise end date from OpenVDM API")
            raise err


    def get_cruise_config_fn(self):
        """
        Return the cruise config filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseConfigFn'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseConfigFn')
        except Exception as err:
            logging.error("Unable to retrieve cruise config filename from OpenVDM API")
            raise err

    def get_cruisedata_url(self):
        """
        Return the cruise config filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruiseDataURLPath'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return self.config['siteRoot'].rstrip('/') + return_obj.get('cruiseDataURLPath')
        except Exception as err:
            logging.error("Unable to retrieve cruise data URL from OpenVDM API")
            raise err


    def get_cruisedata_path(self):
        """
        Return the cruise config filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getDataWarehouseBaseDir'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('dataWarehouseBaseDir')
        except Exception as err:
            logging.error("Unable to retrieve data warehouse base directory from OpenVDM API")
            raise err

    def get_cruises(self):
        """
        Return a list of cruises stored on the data warehouse
        """

        url = self.config['siteRoot'] + 'api/warehouse/getCruises'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve cruises from OpenVDM API")
            raise err


    def get_logfile_purge_timedelta_str(self):
        """
        Return the logfile purge interval
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLogfilePurgeInterval'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('logfilePurgeInterval') or None
        except Exception as err:
            logging.error("Unable to retrieve LogfilePurgeInterval from OpenVDM API")
            raise err


    def get_lowering_id(self):
        """
        Return the current lowering id
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringID'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringID') or None
        except Exception as err:
            logging.error("Unable to retrieve LoweringID from OpenVDM API")
            raise err


    def get_lowering_size(self):
        """
        Return the size of the current lowering
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringSize'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve lowering size from OpenVDM API")
            raise err


    def get_lowering_start_date(self):
        """
        Return the start date for the current lowering
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringStartDate'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringStartDate')
        except Exception as err:
            logging.error("Unable to retrieve lowering start date from OpenVDM API")
            raise err


    def get_lowering_end_date(self):
        """
        Return the end date for the current lowering
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringEndDate'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringEndDate')
        except Exception as err:
            logging.error("Unable to retrieve lowering end date from OpenVDM API")
            raise err


    def get_lowering_config_fn(self):
        """
        Return the lowering config filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLoweringConfigFn'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringConfigFn')
        except Exception as err:
            logging.error("Unable to retrieve lowering config filename from OpenVDM API")
            raise err


    def get_lowerings(self):
        """
        Return the lowerings found for the current cruise
        """

        url = self.config['siteRoot'] + 'api/warehouse/getLowerings'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve lowerings from OpenVDM API")
            raise err


    def get_extra_directory(self, extra_directory_id):
        """
        Return the extra directory configuration based on the extra_directory_id
        """

        url = self.config['siteRoot'] + 'api/extraDirectories/getExtraDirectory/' + extra_directory_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve extra directory: %s from OpenVDM API", extra_directory_id)
            raise err


    def get_extra_directory_by_name(self, extra_directory_name):
        """
        Return the extra directory configuration based on the extra_directory_name
        """

        return next((d for d in self.get_extra_directories() if d['name'] == extra_directory_name), None)


    def get_extra_directories(self):
        """
        Return all extra directory configurations
        """

        url = self.config['siteRoot'] + 'api/extraDirectories/getExtraDirectories'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve extra directories from OpenVDM API")
            raise err


    def get_active_extra_directories(self, cruise=True, lowering=True):
        """
        Return all active extra directory configurations
        """

        url = self.config['siteRoot'] + 'api/extraDirectories/getActiveExtraDirectories'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            if not cruise:
                return_obj = list(filter(lambda directory: directory['cruiseOrLowering'] != "0", return_obj))
            if not lowering:
                return_obj = list(filter(lambda directory: directory['cruiseOrLowering'] != "1", return_obj))
            return return_obj
        except Exception as err:
            logging.error("Unable to retrieve active extra directories from OpenVDM API")
            raise err


    def get_required_extra_directory(self, extra_directory_id):
        """
        Return the required extra directory configuration based on the extra_directory_id
        """

        url = self.config['siteRoot'] + 'api/extraDirectories/getRequiredExtraDirectory/' + extra_directory_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve required extra directory: %s from OpenVDM API", extra_directory_id)
            raise err


    def get_required_extra_directory_by_name(self, extra_directory_name):
        """
        Return the required extra directory configuration based on the extra_directory_name
        """

        return next((d for d in self.get_required_extra_directories() if d['name'] == extra_directory_name), None)


    def get_required_extra_directories(self):
        """
        Return all required extra directories
        """

        url = self.config['siteRoot'] + 'api/extraDirectories/getRequiredExtraDirectories'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve required extra directories from OpenVDM API")
            raise err


    def get_shipboard_data_warehouse_config(self):
        """
        Return the shipboard data warehouse configuration
        """

        url = self.config['siteRoot'] + 'api/warehouse/getShipboardDataWarehouseConfig'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve shipboard data warehouse configuration from OpenVDM API")
            raise err


    def get_ship_to_shore_bw_limit_status(self):
        """
        Return the ship-to-shore transfer bandwidth limit
        """

        url = self.config['siteRoot'] + 'api/warehouse/getShipToShoreBWLimitStatus'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('shipToShoreBWLimitStatus') == "On"
        except Exception as err:
            logging.error("Unable to retrieve ship-to-shore bandwidth limit status from OpenVDM API")
            raise err


    def get_ship_to_shore_transfer(self, ship_to_shore_transfer_id):
        """
        Return the ship-to-shore configuration based on the ship_to_shore_transfer_id
        """

        url = self.config['siteRoot'] + 'api/shipToShoreTransfers/getShipToShoreTransfer/' + ship_to_shore_transfer_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve ship-to-shore transfer: %s from OpenVDM API", ship_to_shore_transfer_id)
            raise err


    def get_ship_to_shore_transfers(self):
        """
        Return all ship-to-shore configurations
        """

        url = self.config['siteRoot'] + 'api/shipToShoreTransfers/getShipToShoreTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve ship-to-shore transfers from OpenVDM API")
            raise err


    def get_required_ship_to_shore_transfers(self):
        """
        Return all required ship-to-shore configurations
        """

        url = self.config['siteRoot'] + 'api/shipToShoreTransfers/getRequiredShipToShoreTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve required ship-to-shore transfers from OpenVDM API")
            raise err


    def get_system_status(self):
        """
        Return the system status
        """

        url = self.config['siteRoot'] + 'api/warehouse/getSystemStatus'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('systemStatus')
        except Exception as err:
            logging.error("Unable to retrieve system status from OpenVDM API")
            raise err


    def get_tasks(self):
        """
        Return the list of all available tasks
        """

        url = self.config['siteRoot'] + 'api/tasks/getTasks'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve tasks from OpenVDM API")
            raise err


    def get_active_tasks(self):
        """
        Return the list of all currently active tasks
        """

        url = self.config['siteRoot'] + 'api/tasks/getActiveTasks'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve active tasks from OpenVDM API")
            raise err


    def get_task(self, task_id):
        """
        Return a task based on the task_id
        """

        url = self.config['siteRoot'] + 'api/tasks/getTask/' + task_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve task: %s from OpenVDM API", task_id)
            raise err


    def get_task_by_name(self, task_name):
        """
        Return a task based on the task_name
        """

        url = self.config['siteRoot'] + 'api/tasks/getTasks'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next((t for t in return_obj if t['name'] == task_name), None)
        except Exception as err:
            logging.error("Unable to retrieve task: %s from OpenVDM API", task_name)
            raise err


    def get_collection_system_transfers(self):
        """
        Return all collection system transfer configurations
        """

        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/getCollectionSystemTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve collection system transfers from OpenVDM API")
            raise err


    def get_active_collection_system_transfers(self, cruise=True, lowering=True):
        """
        Return all active collection system transfer configurations
        """

        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/getActiveCollectionSystemTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            if not cruise:
                return_obj = list(filter(lambda transfer: transfer['cruiseOrLowering'] != "0", return_obj))
            if not lowering:
                return_obj = list(filter(lambda transfer: transfer['cruiseOrLowering'] != "1", return_obj))
            return return_obj
        except Exception as err:
            logging.error("Unable to retrieve active collection system transfers from OpenVDM API")
            raise err


    def get_collection_system_transfer(self, collection_system_transfer_id):
        """
        Return the collection system transfer configuration based on the collection_system_transfer_id
        """

        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/getCollectionSystemTransfer/' + collection_system_transfer_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve collection system transfer: %s from OpenVDM API", collection_system_transfer_id)
            raise err


    def get_collection_system_transfer_by_name(self, collection_system_transfer_name):
        """
        Return the collection system transfer configuration based on the collection_system_transfer_name
        """

        return next((d for d in self.get_collection_system_transfers() if d['name'] == collection_system_transfer_name), None)


    def get_cruise_data_transfers(self):
        """
        Return all cruise data transfers
        """

        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/getCruiseDataTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve cruise data transfers from OpenVDM API")
            raise err


    def get_required_cruise_data_transfers(self):
        """
        Return all requried cruise data transfers
        """

        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/getRequiredCruiseDataTransfers'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as err:
            logging.error("Unable to retrieve required cruise data transfers from OpenVDM API")
            raise err


    def get_cruise_data_transfer(self, cruise_data_transfer_id):
        """
        Return the cruise data transfer based on the cruise_data_transfer_id
        """

        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/getCruiseDataTransfer/' + cruise_data_transfer_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve cruise data transfer: %s from OpenVDM API", cruise_data_transfer_id)
            raise err


    def get_required_cruise_data_transfer(self, cruise_data_transfer_id):
        """
        Return the required cruise data transfer based on the cruise_data_transfer_id
        """

        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/getRequiredCruiseDataTransfer/' + cruise_data_transfer_id

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as err:
            logging.error("Unable to retrieve required cruise data transfer: %s from OpenVDM API", cruise_data_transfer_id)
            raise err


    def get_cruise_data_transfer_by_name(self, cruise_data_transfer_name):
        """
        Return the cruise data transfer based on the cruise_data_transfer_name
        """

        return next((d for d in self.get_cruise_data_transfers() if d['name'] == cruise_data_transfer_name), None)


    def get_required_cruise_data_transfer_by_name(self, cruise_data_transfer_name):
        """
        Return the required cruise data transfer based on the cruise_data_transfer_name
        """

        return next((d for d in self.get_required_cruise_data_transfers() if d['name'] == cruise_data_transfer_name), None)


    def get_data_dashboard_manifest_fn(self):
        """
        Return the data dashboard manifest filename
        """

        url = self.config['siteRoot'] + 'api/warehouse/getDataDashboardManifestFn'

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('dataDashboardManifestFn')
        except Exception as err:
            logging.error("Unable to retrieve data dashboard manifest filename from OpenVDM API")
            raise err


    def send_msg(self, message_title, message_body=''):
        """
        Send a message to OpenVDM
        """

        url = self.config['siteRoot'] + 'api/messages/newMessage'

        try:
            payload = {'messageTitle': message_title, 'messageBody':message_body}
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to send message: \"%s: %s\" with OpenVDM API", message_title, message_body)
            raise err


    def clear_error_collection_system_transfer(self, collection_system_transfer_id, job_status):
        """
        Clear the status flag for the collection system transfer specified by the collection_system_transfer_id
        """

        if job_status != "3":
            return

        # Clear Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/setIdleCollectionSystemTransfer/' + collection_system_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to clear error status for collection system transfer: %s with OpenVDM API", collection_system_transfer_id)
            raise err


    def clear_error_cruise_data_transfer(self, cruise_data_transfer_id, job_status):
        """
        Clear the status flag for the cruise data transfer specified by the cruise_data_transfer_id
        """

        if job_status != "3":
            return

        # Clear Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/' + cruise_data_transfer_id

        logging.info("Clear Error")
        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to clear error status for cruise data transfer: %s with OpenVDM API", cruise_data_transfer_id)
            raise err


    def clear_error_task(self, task_id):
        """
        Clear the status flag for the task specified by the task_id
        """

        task = self.get_task(task_id)

        if task and task['status'] == '3':
            self.set_idle_task(task_id)


    def set_error_collection_system_transfer(self, collection_system_transfer_id, reason=''):
        """
        Set the status flag to error for the collection system transfer specified by the collection_system_transfer_id
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        title = f"{collection_system_transfer.get('name')} Data Transfer failed"

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/setErrorCollectionSystemTransfer/' + collection_system_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as err:
            logging.error("Unable to set status of collection system transfer: %s to error with OpenVDM API", collection_system_transfer_id)
            raise err


    def set_error_collection_system_transfer_test(self, collection_system_transfer_id, reason=''):
        """
        Set the status flag to error for the cruise data transfer specified by the collection_system_transfer_id
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        title = f"{collection_system_transfer.get('name')} Connection test failed"

        # Set Error for current tranfer test in DB via API
        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/setErrorCollectionSystemTransfer/' + collection_system_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as err:
            logging.error("Unable to set test status of collection system transfer: %s to error with OpenVDM API", collection_system_transfer_id)
            raise err


    def set_error_cruise_data_transfer(self, cruise_data_transfer_id, reason=''):
        """
        Set the status flag to error for the cruise data transfer specified by the cruise_data_transfer_id
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        title = f"{cruise_data_transfer.get('name')} Data Transfer failed"

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/setErrorCruiseDataTransfer/' + cruise_data_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as err:
            logging.error("Unable to set status of cruise data transfer: %s to error with OpenVDM API", cruise_data_transfer_id)
            raise err


    def set_error_cruise_data_transfer_test(self, cruise_data_transfer_id, reason=''):
        """
        Set the status flag to error for the cruise data transfer specified by the cruise_data_transfer_id
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        title = f"{cruise_data_transfer.get('name')} Connection test failed"

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/setErrorCruiseDataTransfer/' + cruise_data_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as err:
            logging.error("Unable to set status of cruise data transfer: %s to error with OpenVDM API", cruise_data_transfer_id)
            raise err


    def set_error_task(self, task_id, reason=''):
        """
        Set the status flag to error for the task specified by the task_id
        """

        task = self.get_task(task_id)
        if not task:
            raise ValueError("Invalid task id: %s", task_id)

        title = f"{task.get('name')} failed"

        # Set Error for current task in DB via API
        url = self.config['siteRoot'] + 'api/tasks/setErrorTask/' + task_id

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as err:
            logging.error("Unable to set error status of task: %s with OpenVDM API", task_id)
            raise err


    def set_idle_collection_system_transfer(self, collection_system_transfer_id):
        """
        Set the status flag to idle for the collection system transfer specified by the collection_system_transfer_id
        """

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/setIdleCollectionSystemTransfer/' + collection_system_transfer_id

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to set collection system transfer: %s to idle with OpenVDM API", collection_system_transfer_id)
            raise err


    def set_idle_cruise_data_transfer(self, cruise_data_transfer_id):
        """
        Set the status flag to idle for the cruise data transfer specified by the cruise_data_transfer_id
        """

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/' + cruise_data_transfer_id

        logging.info("Set Idle")
        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to set cruise data transfer: %s to idle with OpenVDM API", cruise_data_transfer_id)
            raise err


    def set_idle_task(self, task_id):
        """
        Set the status flag to idle for the task specified by the task_id
        """

        # Set Idle for the tasks in DB via API
        url = self.config['siteRoot'] + 'api/tasks/setIdleTask/' + task_id

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to set task: %s to idle with OpenVDM API", task_id)
            raise err


    def set_running_collection_system_transfer(self, collection_system_transfer_id, job_pid, job_handle):
        """
        Set the status flag to running for the collection system transfer specified by the collection_system_transfer_id
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        msg = f"Transfer for {collection_system_transfer.get('name')}"

        url = self.config['siteRoot'] + 'api/collectionSystemTransfers/setRunningCollectionSystemTransfer/' + collection_system_transfer_id
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(msg, job_pid, job_handle)
        except Exception as err:
            logging.error("Unable to set collection system transfer: %s to running with OpenVDM API", collection_system_transfer.get('name'))
            raise err


    def set_running_collection_system_transfer_test(self, collection_system_transfer_id, job_pid, job_handle):
        """
        Set the status flag to running for the collection system transfer specified by the collection_system_transfer_id
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection system transfer id: %s", collection_system_transfer_id)

        msg = f"Transfer test for {collection_system_transfer.get('name')}"

        # Add to gearman job tracker
        self.track_gearman_job(msg, job_pid, job_handle)


    def set_running_cruise_data_transfer(self, cruise_data_transfer_id, job_pid, job_handle):
        """
        Set the status flag to running for the cruise data transfer specified by the cruise_data_transfer_id
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        msg = f"Transfer for {cruise_data_transfer.get('name')}"

        url = self.config['siteRoot'] + 'api/cruiseDataTransfers/setRunningCruiseDataTransfer/' + cruise_data_transfer_id
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(msg, job_pid, job_handle)
        except Exception as err:
            logging.error("Unable to set cruise data transfer: %s to running with OpenVDM API", cruise_data_transfer.get('name'))
            raise err


    def set_running_cruise_data_transfer_test(self, cruise_data_transfer_id, job_pid, job_handle):
        """
        Set the status flag to running for the cruise data transfer specified by the cruise_data_transfer_id
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise data transfer id: %s", cruise_data_transfer_id)

        msg = f"Transfer test for {cruise_data_transfer.get('name')}"

        # Add to gearman job tracker
        self.track_gearman_job(msg, job_pid, job_handle)


    def set_running_task(self, task_id, job_pid, job_handle):
        """
        Set the status flag to running for the task specified by the task_id
        """

        task = self.get_task(task_id)
        if not task:
            raise ValueError("Invalid task id: %s", task_id)

        # Set Running for the tasks in DB via API
        url = self.config['siteRoot'] + 'api/tasks/setRunningTask/' + task_id
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(task.get('longName', 'Unknown Task????'), job_pid, job_handle)
        except Exception as err:
            logging.error("Unable to set task: %s to running with OpenVDM API", task.get('longName', 'Unknown Task????'))
            raise err


    def track_gearman_job(self, job_name, job_pid, job_handle):
        """
        Track a gearman task within OpenVDM
        """

        # Add Job to DB via API
        url = self.config['siteRoot'] + 'api/gearman/newJob/' + job_handle
        payload = {'jobName': job_name, 'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to add new gearman task tracking with OpenVDM API, Task: %s", job_name)
            raise err


    def set_cruise_size(self, size_in_bytes=None):
        """
        Set the filesize for the current cruise
        """

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/warehouse/setCruiseSize'
        payload = {'bytes': size_in_bytes}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to set cruise size with OpenVDM API")
            raise err


    def set_lowering_size(self, size_in_bytes=None):
        """
        Set the filesize for the current lowering
        """

        # Set Error for current tranfer in DB via API
        url = self.config['siteRoot'] + 'api/warehouse/setLoweringSize'
        payload = {'bytes': size_in_bytes}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as err:
            logging.error("Unable to set lowering size with OpenVDM API")
            raise err
