#!/usr/bin/env python3
"""Python wrapper around the OpenVDM REST API and YAML configuration.

The :class:`OpenVDM` class is the primary interface used by all Gearman
workers and utility scripts to read configuration, query cruise/lowering
state, update transfer statuses, and post messages — all via HTTP calls
to the OpenVDM web API rather than direct database connections.
"""

from datetime import datetime, timezone
import json
import logging
from os.path import dirname, realpath, join
import requests

try:
    from yaml import load, YAMLError, FullLoader
except ModuleNotFoundError:
    pass

DEFAULT_CONFIG_FILE = join(dirname(dirname(dirname(realpath(__file__)))), 'server/etc/openvdm.yaml')

TIMEOUT = 5

class OpenVDM():
    """Python wrapper around the OpenVDM REST API and YAML configuration file.

    All database interaction is performed indirectly through HTTP calls to the
    OpenVDM web API.  The YAML configuration file supplies connection settings
    (site root URL, Gearman server address, plugin directories, hooks, etc.).

    Attributes:
        config: Parsed contents of the OpenVDM YAML configuration file.
    """

    def __init__(self, config_file: str = DEFAULT_CONFIG_FILE) -> None:
        """Initialise the wrapper by loading *config_file*.

        Args:
            config_file: Path to ``openvdm.yaml``.  Defaults to the file
                located at ``server/etc/openvdm.yaml`` relative to the
                repository root.

        Raises:
            IOError: If the configuration file cannot be opened.
            yaml.YAMLError: If the file content is not valid YAML.
            ImportError: If PyYAML is not installed.
        """
        self.config = self.read_config(config_file)


    @staticmethod
    def read_config(filename: str) -> dict:
        """Parse an OpenVDM YAML configuration file into a Python dict.

        Args:
            filename: Path to the YAML configuration file.

        Returns:
            Parsed configuration as a nested dict.

        Raises:
            IOError: If the file cannot be opened.
            yaml.YAMLError: If the file content is not valid YAML.
            ImportError: If PyYAML is not installed.
        """

        def _parse_yaml(source):
            """Read the passed text/stream assuming it's YAML or JSON (a subset of
            YAML) and try to parse it into a Python dict.
            """

            try:
                return load(source, Loader=FullLoader)
            except NameError as name_error:
                raise ImportError('No YAML module available. Please ensure that '
                                  'PyYAML or equivalent is installed (e.g. via '
                                  '"pip3 install PyYAML"') from name_error
            except YAMLError as exc:
                logging.error("Unable to parse configuration file: %s", source)
                raise exc
            except Exception as exc: # handle other exceptions such as attribute errors
                raise exc



        try:
            with open(filename, mode='r', encoding="utf-8") as file:
                return _parse_yaml(file)
        except IOError as exc:
            logging.error("Unable to open configuration file: %s", filename)
            raise exc
        except Exception as exc: # handle other exceptions such as attribute errors
            raise exc


    def _worker_headers(self) -> dict:
        """Return HTTP headers that authenticate this process as a trusted worker.

        Includes the ``X-Worker-Token`` header when ``workerApiKey`` is present
        in the YAML config, allowing the PHP API to return credential fields that
        are otherwise stripped from public responses.

        Returns:
            A dict suitable for passing as *headers* to :mod:`requests` calls.
        """
        token = self.config.get('workerApiKey', '')
        if token:
            return {'X-Worker-Token': token}
        return {}


    def clear_gearman_jobs_from_db(self):
        """
        Clear the current Gearman job request queue.
        """

        url = f"{self.config['siteRoot']}api/gearman/clearAllJobsFromDB"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to clear Gearman Jobs from OpenVDM API")
            raise exc


    def get_plugin_dir(self):
        """Return the directory containing the OpenVDM plugins (from ``openvdm.yaml``).

        Returns:
            str: The plugin directory.
        """

        return self.config['plugins']['pluginDir']


    def get_plugin_suffix(self):
        """Return the plugin filename suffix (from ``openvdm.yaml``).

        Returns:
            str: The suffix, e.g. ``'_plugin.py'``.
        """

        return self.config['plugins']['pluginSuffix']


    def show_only_current_cruise_dir(self):
        """Return whether only the current cruise directory is shown (from ``openvdm.yaml``).

        Returns:
            bool: The ``showOnlyCurrentCruiseDir`` setting.
        """

        return self.config['showOnlyCurrentCruiseDir']


    def get_show_lowering_components(self):
        """Return whether the web UI shows lowering components.

        Returns:
            bool: ``True`` if lowering components are enabled.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getShowLoweringComponents"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return req.text == 'true'
        except Exception as exc:
            logging.error("Unable to retrieve 'showLoweringComponents' flag from OpenVDM API")
            raise exc


    def get_cruise_config(self):
        """Return the current cruise's configuration, as written to the cruise config file.

        Returns:
            dict: The cruise configuration, with ``configCreatedOn`` set to the
            current UTC time.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseConfig"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return_obj['configCreatedOn'] = datetime.now(timezone.utc).strftime("%Y/%m/%dT%H:%M:%SZ")
            return return_obj
        except Exception as exc:
            logging.error("Unable to retrieve cruise configuration from OpenVDM API")
            raise exc


    def get_lowering_config(self):
        """Return the current lowering's configuration, as written to the lowering config file.

        Returns:
            dict: The lowering configuration, with ``configCreatedOn`` set to
            the current UTC time.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringConfig"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return_obj['configCreatedOn'] = datetime.now(timezone.utc).strftime("%Y/%m/%dT%H:%M:%SZ")
            return return_obj
        except Exception as exc:
            logging.error("Unable to retrieve lowering configuration from OpenVDM API")
            raise exc


    def get_gearman_server(self):
        """Return the Gearman server address (from ``openvdm.yaml``).

        Returns:
            str: ``host:port``, e.g. ``'localhost:4730'``.
        """

        return self.config['gearmanServer']


    def get_site_root(self):
        """Return the OpenVDM web app's root URL (from ``openvdm.yaml``).

        Returns:
            str: The site root, ending with ``/``.
        """

        return self.config['siteRoot']


    def get_transfer_public_data(self):
        """Return whether PublicData is copied into the cruise when it is finalized.

        Returns:
            bool: The ``transferPublicData`` setting from ``openvdm.yaml``.
        """

        return self.config['transferPublicData']


    def get_md5_filesize_limit(self):
        """Return the MD5 summary file size limit.

        Returns:
            str | None: The limit in MB, as a string; ``'0'`` means no limit.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getMD5FilesizeLimit"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5FilesizeLimit')
        except Exception as exc:
            logging.error("Unable to retrieve MD5 filesize limit from OpenVDM API")
            raise exc


    def get_md5_filesize_limit_status(self):
        """Return whether the MD5 summary file size limit is enabled.

        Returns:
            str | None: ``'On'`` or ``'Off'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getMD5FilesizeLimitStatus"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5FilesizeLimitStatus')
        except Exception as exc:
            logging.error("Unable to retrieve MD5 filesize limit status from OpenVDM API")
            raise exc


    def get_md5_summary_fn(self):
        """Return the MD5 summary filename.

        Returns:
            str | None: The filename.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getMD5SummaryFn"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5SummaryFn')
        except Exception as exc:
            logging.error("Unable to retrieve MD5 summary filename from OpenVDM API")
            raise exc


    def get_md5_summary_md5_fn(self):
        """Return the filename of the MD5 summary's own MD5 checksum file.

        Returns:
            str | None: The filename.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getMD5SummaryMD5Fn"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('md5SummaryMd5Fn')
        except Exception as exc:
            logging.error("Unable to retrieve MD5 summary MD5 filename from OpenVDM API")
            raise exc


    def get_tasks_for_hook(self, hook_name):
        """Return the Gearman tasks configured to run for a hook.

        Args:
            hook_name: Hook name from the ``hooks`` section of ``openvdm.yaml``
                (e.g. ``postCollectionSystemTransfer``).

        Returns:
            list: The hook's task names, or an empty list if the hook isn't
            configured.
        """

        return self.config['hooks'].get(hook_name, [])


    def get_post_hook_commands(self, post_hook_name):
        """Return the shell commands configured for a post hook.

        Args:
            post_hook_name: Post hook name from the ``postHookCommands``
                section of ``openvdm.yaml``.

        Returns:
            list | None: The hook's command list, or ``None`` if it isn't
            configured.
        """

        post_hook_commands = self.config.get('postHookCommands', {})
        return post_hook_commands.get(post_hook_name)


    def get_transfer_interval(self):
        """Return the collection system transfer interval (from ``openvdm.yaml``).

        Returns:
            int | None: Minutes between transfer runs, or ``None`` if unset.
        """

        return self.config.get('transferInterval')

    def get_transfer_log_dir(self):
        """Return the directory where transfer log files are stored.

        Returns:
            str: The directory; ``'/var/log/openvdm'`` if the API doesn't say.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getTransferLogDir"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('transferLogDir', '/var/log/openvdm')
        except Exception as exc:
            logging.error("Unable to retrieve transferLogDir from OpenVDM API")
            raise exc

    def get_logfile_purge_timedelta(self):
        """Return how old transfer log files must be before they are purged.

        Returns:
            str | None: The ``logfilePurgeTimedelta`` setting from
            ``openvdm.yaml``, e.g. ``"12 hours"``, or ``None`` if unset.
        """

        return self.config.get('logfilePurgeTimedelta')


    def get_cruise_id(self):
        """Return the current cruise ID.

        Returns:
            str | None: The cruise ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseID"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseID')
        except Exception as exc:
            logging.error("Unable to retrieve CruiseID from OpenVDM API")
            raise exc


    def get_cruise_size(self):
        """Return the current cruise directory's size.

        Returns:
            dict: ``cruiseSize`` (bytes) and ``cruiseSizeUpdated``, plus
            ``error`` if the size is unknown.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseSize"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve cruise size from OpenVDM API")
            raise exc


    def get_cruise_start_date(self):
        """Return the current cruise start date.

        Returns:
            str | None: The date as ``'YYYY/MM/DD HH:MM'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseStartDate"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseStartDate')
        except Exception as exc:
            logging.error("Unable to retrieve cruise start date from OpenVDM API")
            raise exc


    def get_cruise_end_date(self):
        """Return the current cruise end date.

        Returns:
            str | None: The date as ``'YYYY/MM/DD HH:MM'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseEndDate"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseEndDate')
        except Exception as exc:
            logging.error("Unable to retrieve cruise end date from OpenVDM API")
            raise exc


    def get_cruise_config_fn(self):
        """Return the cruise config filename.

        Returns:
            str | None: e.g. ``'cruise_config.json'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseConfigFn"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('cruiseConfigFn')
        except Exception as exc:
            logging.error("Unable to retrieve cruise config filename from OpenVDM API")
            raise exc

    def get_cruisedata_url(self):
        """Return the CruiseData web share's URL.

        Returns:
            str: The site root followed by the CruiseData URL path.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruiseDataURLPath"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return f"{self.config['siteRoot'].rstrip('/')}{return_obj.get('cruiseDataURLPath')}"
        except Exception as exc:
            logging.error("Unable to retrieve cruise data URL from OpenVDM API")
            raise exc


    def get_cruisedata_path(self):
        """Return the CruiseData directory on the data warehouse.

        Returns:
            str | None: The directory path.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getDataWarehouseBaseDir"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('dataWarehouseBaseDir')
        except Exception as exc:
            logging.error("Unable to retrieve data warehouse base directory from OpenVDM API")
            raise exc

    def get_cruises(self):
        """Return the cruises found on the data warehouse.

        Returns:
            list[str]: The cruise IDs.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getCruises"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve cruises from OpenVDM API")
            raise exc


    def get_logfile_purge_timedelta_str(self):
        """Return the logfile purge interval from the web API.

        The web app currently has no ``getLogfilePurgeInterval`` endpoint, so
        this fails; nothing calls it. The scheduler uses
        :meth:`get_logfile_purge_timedelta`, which reads ``openvdm.yaml``.

        Returns:
            str | None: The interval, or ``None`` if not set.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLogfilePurgeInterval"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('logfilePurgeInterval') or None
        except Exception as exc:
            logging.error("Unable to retrieve LogfilePurgeInterval from OpenVDM API")
            raise exc


    def get_lowering_id(self):
        """Return the current lowering ID.

        Returns:
            str | None: The lowering ID, or ``None`` if not set.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringID"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringID') or None
        except Exception as exc:
            logging.error("Unable to retrieve LoweringID from OpenVDM API")
            raise exc


    def get_lowering_size(self):
        """Return the current lowering directory's size.

        Returns:
            dict: ``loweringSize`` (bytes) and ``loweringSizeUpdated``, plus
            ``error`` if the size is unknown.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringSize"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve lowering size from OpenVDM API")
            raise exc


    def get_lowering_start_date(self):
        """Return the current lowering start date.

        Returns:
            str | None: The date as ``'YYYY/MM/DD HH:MM'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringStartDate"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringStartDate')
        except Exception as exc:
            logging.error("Unable to retrieve lowering start date from OpenVDM API")
            raise exc


    def get_lowering_end_date(self):
        """Return the current lowering end date.

        Returns:
            str | None: The date as ``'YYYY/MM/DD HH:MM'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringEndDate"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringEndDate')
        except Exception as exc:
            logging.error("Unable to retrieve lowering end date from OpenVDM API")
            raise exc


    def get_lowering_config_fn(self):
        """Return the lowering config filename.

        Returns:
            str | None: e.g. ``'lowering_config.json'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLoweringConfigFn"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('loweringConfigFn')
        except Exception as exc:
            logging.error("Unable to retrieve lowering config filename from OpenVDM API")
            raise exc


    def get_lowerings(self):
        """Return the lowerings found for the current cruise.

        Returns:
            list[str]: The lowering IDs.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getLowerings"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve lowerings from OpenVDM API")
            raise exc


    def get_extra_directory(self, extra_directory_id):
        """Return the extra directory with the given ID from the OpenVDM API.

        Args:
            extra_directory_id: The extra directory's ID.

        Returns:
            dict | None: The extra directory's configuration, or ``None`` if
            there's no extra directory with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/extraDirectories/getExtraDirectory/{extra_directory_id}"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve extra directory: %s from OpenVDM API", extra_directory_id)
            raise exc


    def get_extra_directory_by_name(self, extra_directory_name):
        """Return the extra directory with the given name.

        Args:
            extra_directory_name: The extra directory's name.

        Returns:
            dict | None: The extra directory's configuration from
            ``get_extra_directories()``, or ``None`` if there's no extra
            directory with that name.
        """

        return next((d for d in self.get_extra_directories() if d['name'] == extra_directory_name), None)


    def get_extra_directories(self):
        """Return all extra directory configurations.

        Returns:
            list[dict]: The extra directories.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/extraDirectories/getExtraDirectories"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve extra directories from OpenVDM API")
            raise exc


    def get_active_extra_directories(self, cruise=True, lowering=True):
        """Return the active extra directory configurations.

        Args:
            cruise: Include cruise-level directories.
            lowering: Include lowering-level directories.

        Returns:
            list[dict]: The active extra directories.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/extraDirectories/getActiveExtraDirectories"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            if not cruise:
                return_obj = list(filter(lambda directory: directory['cruiseOrLowering'] != 0, return_obj))
            if not lowering:
                return_obj = list(filter(lambda directory: directory['cruiseOrLowering'] != 1, return_obj))
            return return_obj
        except Exception as exc:
            logging.error("Unable to retrieve active extra directories from OpenVDM API")
            raise exc


    def get_required_extra_directory(self, extra_directory_id):
        """Return the required extra directory with the given ID from the OpenVDM API.

        Args:
            extra_directory_id: The required extra directory's ID.

        Returns:
            dict | None: The required extra directory's configuration, or
            ``None`` if there's no required extra directory with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/extraDirectories/getRequiredExtraDirectory/{extra_directory_id}"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve required extra directory: %s from OpenVDM API", extra_directory_id)
            raise exc


    def get_required_extra_directory_by_name(self, extra_directory_name):
        """Return the required extra directory with the given name.

        Args:
            extra_directory_name: The required extra directory's name.

        Returns:
            dict | None: The required extra directory's configuration from
            ``get_required_extra_directories()``, or ``None`` if there's no
            required extra directory with that name.
        """

        return next((d for d in self.get_required_extra_directories() if d['name'] == extra_directory_name), None)


    def get_required_extra_directories(self):
        """Return the required extra directory configurations.

        Returns:
            list[dict]: The required extra directories.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/extraDirectories/getRequiredExtraDirectories"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve required extra directories from OpenVDM API")
            raise exc


    def get_shipboard_data_warehouse_config(self):
        """Return the shipboard data warehouse configuration.

        Returns:
            dict: Settings including ``shipboardDataWarehouseBaseDir``,
            ``loweringDataBaseDir`` and the config/summary filenames.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getShipboardDataWarehouseConfig"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve shipboard data warehouse configuration from OpenVDM API")
            raise exc


    def get_ship_to_shore_bw_limit_status(self):
        """Return whether the ship-to-shore bandwidth limit is enabled.

        Returns:
            bool: ``True`` if the limit is ``'On'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getShipToShoreBWLimitStatus"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('shipToShoreBWLimitStatus') == "On"
        except Exception as exc:
            logging.error("Unable to retrieve ship-to-shore bandwidth limit status from OpenVDM API")
            raise exc


    def get_ship_to_shore_transfer(self, ship_to_shore_transfer_id):
        """Return the ship-to-shore transfer with the given ID from the OpenVDM API.

        Args:
            ship_to_shore_transfer_id: The ship-to-shore transfer's ID.

        Returns:
            dict | None: The ship-to-shore transfer's configuration, or
            ``None`` if there's no ship-to-shore transfer with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/shipToShoreTransfers/getShipToShoreTransfer/{ship_to_shore_transfer_id}"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve ship-to-shore transfer: %s from OpenVDM API", ship_to_shore_transfer_id)
            raise exc


    def get_ship_to_shore_transfers(self):
        """Return all ship-to-shore transfer configurations.

        Returns:
            list[dict]: The ship-to-shore transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/shipToShoreTransfers/getShipToShoreTransfers"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve ship-to-shore transfers from OpenVDM API")
            raise exc


    def get_required_ship_to_shore_transfers(self):
        """Return the required ship-to-shore transfer configurations.

        Returns:
            list[dict]: The required ship-to-shore transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/shipToShoreTransfers/getRequiredShipToShoreTransfers"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve required ship-to-shore transfers from OpenVDM API")
            raise exc


    def get_system_status(self):
        """Return whether OpenVDM is turned on.

        Returns:
            str | None: ``'On'`` or ``'Off'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getSystemStatus"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('systemStatus')
        except Exception as exc:
            logging.error("Unable to retrieve system status from OpenVDM API")
            raise exc


    def get_tasks(self):
        """Return all tasks.

        Returns:
            list[dict]: The tasks.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/tasks/getTasks"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve tasks from OpenVDM API")
            raise exc


    def get_active_tasks(self):
        """Return the enabled tasks.

        Returns:
            list[dict]: The tasks whose ``enable`` is ``1``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/tasks/getActiveTasks"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve active tasks from OpenVDM API")
            raise exc


    def get_task(self, task_id):
        """Return the task with the given ID from the OpenVDM API.

        Args:
            task_id: The task's ID.

        Returns:
            dict | None: The task's configuration, or ``None`` if there's no
            task with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/tasks/getTask/{task_id}"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve task: %s from OpenVDM API", task_id)
            raise exc


    def get_task_by_name(self, task_name):
        """Return the task with the given name from the OpenVDM API.

        Args:
            task_name: The task's name (its Gearman task name).

        Returns:
            dict | None: The task's configuration, or ``None`` if there's no
            task with that name.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/tasks/getTasks"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next((t for t in return_obj if t['name'] == task_name), None)
        except Exception as exc:
            logging.error("Unable to retrieve task: %s from OpenVDM API", task_name)
            raise exc


    def get_collection_system_transfers(self):
        """Return all collection system transfer configurations.

        Includes credentials, since the request carries the worker API key.

        Returns:
            list[dict]: The collection system transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/getCollectionSystemTransfers"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve collection system transfers from OpenVDM API")
            raise exc


    def get_active_collection_system_transfers(self, sort='name', cruise=True, lowering=True):
        """Return the active collection system transfer configurations.

        Includes credentials (``rsyncPass``, ``smbPass``, ``sshPass``), since
        the request carries the worker API key.

        Args:
            sort: Field to sort by, passed to the API (default ``'name'``).
            cruise: Include cruise-level transfers.
            lowering: Include lowering-level transfers.

        Returns:
            list[dict]: The active collection system transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/getActiveCollectionSystemTransfers/{sort}"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            if not cruise:
                return_obj = list(filter(lambda transfer: int(transfer['cruiseOrLowering']) != 0, return_obj))
            if not lowering:
                return_obj = list(filter(lambda transfer: int(transfer['cruiseOrLowering']) != 1, return_obj))
            return return_obj
        except Exception as exc:
            logging.error("Unable to retrieve active collection system transfers from OpenVDM API")
            raise exc


    def get_collection_system_transfer(self, collection_system_transfer_id):
        """Return the collection system transfer with the given ID from the OpenVDM API.

        Includes credentials, since the request carries the worker API key.

        Args:
            collection_system_transfer_id: The transfer's ID.

        Returns:
            dict | None: The transfer's configuration, or ``None`` if the ID is
            ``None`` or there's no transfer with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """
        if collection_system_transfer_id is None:
            return None

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/getCollectionSystemTransfer/{collection_system_transfer_id}"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve collection system transfer: %s from OpenVDM API", collection_system_transfer_id)
            raise exc


    def get_collection_system_transfer_by_name(self, collection_system_transfer_name):
        """Return the collection system transfer with the given name.

        Args:
            collection_system_transfer_name: The collection system transfer's
                name.

        Returns:
            dict | None: The collection system transfer's configuration from
            ``get_collection_system_transfers()``, or ``None`` if there's no
            collection system transfer with that name.
        """

        return next((d for d in self.get_collection_system_transfers() if d['name'] == collection_system_transfer_name), None)


    def get_cruise_data_transfers(self):
        """Return all cruise data transfer configurations.

        Includes credentials, since the request carries the worker API key.

        Returns:
            list[dict]: The cruise data transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/getCruiseDataTransfers"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve cruise data transfers from OpenVDM API")
            raise exc


    def get_required_cruise_data_transfers(self):
        """Return the required cruise data transfer configurations.

        Returns:
            list[dict]: The required cruise data transfers.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/getRequiredCruiseDataTransfers"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return json.loads(req.text)
        except Exception as exc:
            logging.error("Unable to retrieve required cruise data transfers from OpenVDM API")
            raise exc


    def get_cruise_data_transfer(self, cruise_data_transfer_id):
        """Return the cruise data transfer with the given ID from the OpenVDM API.

        Includes credentials, since the request carries the worker API key.

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.

        Returns:
            dict | None: The cruise data transfer's configuration, or ``None``
            if there's no cruise data transfer with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/getCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve cruise data transfer: %s from OpenVDM API", cruise_data_transfer_id)
            raise exc

    def get_active_cruise_data_transfers(self):
        """Return the enabled cruise data transfer configurations.

        Returns:
            list[dict]: The cruise data transfers whose ``enable`` is ``1``.
        """

        return_obj = self.get_cruise_data_transfers()
        return list(filter(lambda transfer: int(transfer['enable']) == 1, return_obj))


    def get_required_cruise_data_transfer(self, cruise_data_transfer_id):
        """Return the required cruise data transfer with the given ID from the OpenVDM API.

        Args:
            cruise_data_transfer_id: The required cruise data transfer's ID.

        Returns:
            dict | None: The required cruise data transfer's configuration, or
            ``None`` if there's no required cruise data transfer with that ID.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/getRequiredCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            req = requests.get(url, headers=self._worker_headers(), timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return next(iter(return_obj), None)
        except Exception as exc:
            logging.error("Unable to retrieve required cruise data transfer: %s from OpenVDM API", cruise_data_transfer_id)
            raise exc


    def get_cruise_data_transfer_by_name(self, cruise_data_transfer_name):
        """Return the cruise data transfer with the given name.

        Args:
            cruise_data_transfer_name: The cruise data transfer's name.

        Returns:
            dict | None: The cruise data transfer's configuration from
            ``get_cruise_data_transfers()``, or ``None`` if there's no cruise
            data transfer with that name.
        """

        return next((d for d in self.get_cruise_data_transfers() if d['name'] == cruise_data_transfer_name), None)


    def get_required_cruise_data_transfer_by_name(self, cruise_data_transfer_name):
        """Return the required cruise data transfer with the given name.

        Args:
            cruise_data_transfer_name: The required cruise data transfer's
                name.

        Returns:
            dict | None: The required cruise data transfer's configuration from
            ``get_required_cruise_data_transfers()``, or ``None`` if there's no
            required cruise data transfer with that name.
        """

        return next((d for d in self.get_required_cruise_data_transfers() if d['name'] == cruise_data_transfer_name), None)


    def get_data_dashboard_manifest_fn(self):
        """Return the data dashboard manifest filename.

        Returns:
            str | None: e.g. ``'manifest.json'``.

        Raises:
            Exception: If the OpenVDM API can't be reached or returns invalid
                JSON.
        """

        url = f"{self.config['siteRoot']}api/warehouse/getDataDashboardManifestFn"

        try:
            req = requests.get(url, timeout=TIMEOUT)
            return_obj = json.loads(req.text)
            return return_obj.get('dataDashboardManifestFn')
        except Exception as exc:
            logging.error("Unable to retrieve data dashboard manifest filename from OpenVDM API")
            raise exc


    def send_msg(self, message_title, message_body=''):
        """Post a message to OpenVDM's message list.

        Args:
            message_title: The message title.
            message_body: The message body.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/messages/newMessage"

        try:
            payload = {'messageTitle': message_title, 'messageBody':message_body}
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to send message: \"%s: %s\" with OpenVDM API", message_title, message_body)
            raise exc


    def clear_error_collection_system_transfer(self, collection_system_transfer_id, job_status):
        """Reset the collection system transfer's status to idle if it's currently in error.

        Does nothing unless *job_status* is ``3`` (error).

        Args:
            collection_system_transfer_id: The collection system transfer's ID.
            job_status: The collection system transfer's current status (``1``
                running, ``2`` idle, ``3`` error).

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        if job_status != 3:
            return

        # Clear Error for current tranfer in DB via API
        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/setIdleCollectionSystemTransfer/{collection_system_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to clear error status for collection system transfer: %s with OpenVDM API", collection_system_transfer_id)
            raise exc


    def clear_error_cruise_data_transfer(self, cruise_data_transfer_id, job_status):
        """Reset the cruise data transfer's status to idle if it's currently in error.

        Does nothing unless *job_status* is ``3`` (error).

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.
            job_status: The cruise data transfer's current status (``1``
                running, ``2`` idle, ``3`` error).

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        # Ignore request if transfer does not have a error status
        if job_status != 3:
            return

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/setIdleCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to clear error status for cruise data transfer: %s with OpenVDM API", cruise_data_transfer_id)
            raise exc


    def clear_error_task(self, task_id):
        """Reset the task's status to idle if it's currently in error.

        Args:
            task_id: The task's ID.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        task = self.get_task(task_id)

        if task and task['status'] == '3':
            self.set_idle_task(task_id)


    def set_error_collection_system_transfer(self, collection_system_transfer_id, reason=''):
        """Set the collection system transfer's status to error and post a message to OpenVDM.

        The message is titled "<name> Data Transfer failed".

        Args:
            collection_system_transfer_id: The collection system transfer's ID.
            reason: Body of the message, describing the failure.

        Raises:
            ValueError: If there's no collection system transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        title = f"{collection_system_transfer.get('name')} Data Transfer failed"

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/setErrorCollectionSystemTransfer/{collection_system_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as exc:
            logging.error("Unable to set status of collection system transfer: %s to error with OpenVDM API", collection_system_transfer_id)
            raise exc


    def set_error_collection_system_transfer_test(self, collection_system_transfer_id, reason=''):
        """Set the collection system transfer's status to error and post a message to OpenVDM.

        The message is titled "<name> Connection test failed".

        Args:
            collection_system_transfer_id: The collection system transfer's ID.
            reason: Body of the message, describing the failure.

        Raises:
            ValueError: If there's no collection system transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        title = f"{collection_system_transfer.get('name')} Connection test failed"

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/setErrorCollectionSystemTransfer/{collection_system_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as exc:
            logging.error("Unable to set test status of collection system transfer: %s to error with OpenVDM API", collection_system_transfer_id)
            raise exc


    def set_error_cruise_data_transfer(self, cruise_data_transfer_id, reason=''):
        """Set the cruise data transfer's status to error and post a message to OpenVDM.

        The message is titled "<name> Data Transfer failed".

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.
            reason: Body of the message, describing the failure.

        Raises:
            ValueError: If there's no cruise data transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        title = f"{cruise_data_transfer.get('name')} Data Transfer failed"

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/setErrorCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as exc:
            logging.error("Unable to set status of cruise data transfer: %s to error with OpenVDM API", cruise_data_transfer_id)
            raise exc


    def set_error_cruise_data_transfer_test(self, cruise_data_transfer_id, reason=''):
        """Set the cruise data transfer's status to error and post a message to OpenVDM.

        The message is titled "<name> Connection test failed".

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.
            reason: Body of the message, describing the failure.

        Raises:
            ValueError: If there's no cruise data transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        title = f"{cruise_data_transfer.get('name')} Connection test failed"

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/setErrorCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as exc:
            logging.error("Unable to set status of cruise data transfer: %s to error with OpenVDM API", cruise_data_transfer_id)
            raise exc


    def set_error_task(self, task_id, reason=''):
        """Set the task's status to error and post a message to OpenVDM.

        The message is titled "<task long name> failed".

        Args:
            task_id: The task's ID.
            reason: Body of the message, describing the failure.

        Raises:
            ValueError: If there's no task with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        task = self.get_task(task_id)
        if not task:
            raise ValueError("Invalid task id: %s", task_id)

        title = f"{task.get('longName')} failed"

        url = f"{self.config['siteRoot']}api/tasks/setErrorTask/{task_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
            self.send_msg(title, reason)
        except Exception as exc:
            logging.error("Unable to set error status of task: %s with OpenVDM API", task_id)
            raise exc


    def set_idle_collection_system_transfer(self, collection_system_transfer_id):
        """Set the collection system transfer's status to idle in OpenVDM.

        Args:
            collection_system_transfer_id: The collection system transfer's ID.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/setIdleCollectionSystemTransfer/{collection_system_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to set collection system transfer: %s to idle with OpenVDM API", collection_system_transfer_id)
            raise exc


    def set_idle_cruise_data_transfer(self, cruise_data_transfer_id):
        """Set the cruise data transfer's status to idle in OpenVDM.

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/setIdleCruiseDataTransfer/{cruise_data_transfer_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to set cruise data transfer: %s to idle with OpenVDM API", cruise_data_transfer_id)
            raise exc


    def set_idle_task(self, task_id):
        """Set the task's status to idle in OpenVDM.

        Args:
            task_id: The task's ID.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/tasks/setIdleTask/{task_id}"

        try:
            requests.get(url, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to set task: %s to idle with OpenVDM API", task_id)
            raise exc


    def set_running_collection_system_transfer(self, collection_system_transfer_id, job_pid, job_handle):
        """Set the collection system transfer's status to running and track its Gearman job.

        Args:
            collection_system_transfer_id: The collection system transfer's ID.
            job_pid: Process ID of the worker running the job.
            job_handle: The Gearman job handle.

        Raises:
            ValueError: If there's no collection system transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection_system_transfer id: %s", collection_system_transfer_id)

        msg = f"Transfer for {collection_system_transfer.get('name')}"

        url = f"{self.config['siteRoot']}api/collectionSystemTransfers/setRunningCollectionSystemTransfer/{collection_system_transfer_id}"
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(msg, job_pid, job_handle)
        except Exception as exc:
            logging.error("Unable to set collection system transfer: %s to running with OpenVDM API", collection_system_transfer.get('name'))
            raise exc


    def set_running_collection_system_transfer_test(self, collection_system_transfer_id, job_pid, job_handle):
        """Track the Gearman job testing the collection system transfer.

        Unlike the transfer itself, a connection test doesn't change the
        collection system transfer's status; the job is only registered so it
        appears in OpenVDM's job list.

        Args:
            collection_system_transfer_id: The collection system transfer's ID.
            job_pid: Process ID of the worker running the test.
            job_handle: The Gearman job handle.

        Raises:
            ValueError: If there's no collection system transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        collection_system_transfer = self.get_collection_system_transfer(collection_system_transfer_id)
        if not collection_system_transfer:
            raise ValueError("Invalid collection system transfer id: %s", collection_system_transfer_id)

        msg = f"Transfer test for {collection_system_transfer.get('name')}"

        # Add to gearman job tracker
        self.track_gearman_job(msg, job_pid, job_handle)


    def set_running_cruise_data_transfer(self, cruise_data_transfer_id, job_pid, job_handle):
        """Set the cruise data transfer's status to running and track its Gearman job.

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.
            job_pid: Process ID of the worker running the job.
            job_handle: The Gearman job handle.

        Raises:
            ValueError: If there's no cruise data transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise_data_transfer id: %s", cruise_data_transfer_id)

        msg = f"Transfer for {cruise_data_transfer.get('name')}"

        url = f"{self.config['siteRoot']}api/cruiseDataTransfers/setRunningCruiseDataTransfer/{cruise_data_transfer_id}"
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(msg, job_pid, job_handle)
        except Exception as exc:
            logging.error("Unable to set cruise data transfer: %s to running with OpenVDM API", cruise_data_transfer.get('name'))
            raise exc


    def set_running_cruise_data_transfer_test(self, cruise_data_transfer_id, job_pid, job_handle):
        """Track the Gearman job testing the cruise data transfer.

        Unlike the transfer itself, a connection test doesn't change the cruise
        data transfer's status; the job is only registered so it appears in
        OpenVDM's job list.

        Args:
            cruise_data_transfer_id: The cruise data transfer's ID.
            job_pid: Process ID of the worker running the test.
            job_handle: The Gearman job handle.

        Raises:
            ValueError: If there's no cruise data transfer with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        cruise_data_transfer = self.get_cruise_data_transfer(cruise_data_transfer_id)
        if not cruise_data_transfer:
            raise ValueError("Invalid cruise data transfer id: %s", cruise_data_transfer_id)

        msg = f"Transfer test for {cruise_data_transfer.get('name')}"

        # Add to gearman job tracker
        self.track_gearman_job(msg, job_pid, job_handle)


    def set_running_task(self, task_id, job_pid, job_handle):
        """Set the task's status to running and track its Gearman job.

        Args:
            task_id: The task's ID.
            job_pid: Process ID of the worker running the job.
            job_handle: The Gearman job handle.

        Raises:
            ValueError: If there's no task with that ID.
            Exception: If the OpenVDM API can't be reached.
        """

        task = self.get_task(task_id)
        if not task:
            raise ValueError("Invalid task id: %s", task_id)

        # Set Running for the tasks in DB via API
        url = f"{self.config['siteRoot']}api/tasks/setRunningTask/{task_id}"
        payload = {'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)

            # Add to gearman job tracker
            self.track_gearman_job(task.get('longName', 'Unknown Task????'), job_pid, job_handle)
        except Exception as exc:
            logging.error("Unable to set task: %s to running with OpenVDM API", task.get('longName', 'Unknown Task????'))
            raise exc


    def track_gearman_job(self, job_name, job_pid, job_handle):
        """Register a Gearman job with OpenVDM so it appears in the job list.

        Args:
            job_name: Name to show for the job.
            job_pid: Process ID of the worker running the job.
            job_handle: The Gearman job handle.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/gearman/newJob/{job_handle}"
        payload = {'jobName': job_name, 'jobPid': job_pid}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to add new gearman task tracking with OpenVDM API, Task: %s", job_name)
            raise exc


    def set_cruise_size(self, size_in_bytes=None):
        """Record the current cruise's total size in OpenVDM.

        Args:
            size_in_bytes: Size of the cruise directory, in bytes.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/warehouse/setCruiseSize"
        payload = {'bytes': size_in_bytes}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to set cruise size with OpenVDM API")
            raise exc


    def set_lowering_size(self, size_in_bytes=None):
        """Record the current lowering's total size in OpenVDM.

        Args:
            size_in_bytes: Size of the lowering directory, in bytes.

        Raises:
            Exception: If the OpenVDM API can't be reached.
        """

        url = f"{self.config['siteRoot']}api/warehouse/setLoweringSize"
        payload = {'bytes': size_in_bytes}

        try:
            requests.post(url, data=payload, timeout=TIMEOUT)
        except Exception as exc:
            logging.error("Unable to set lowering size with OpenVDM API")
            raise exc
