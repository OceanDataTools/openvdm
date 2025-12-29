#!/usr/bin/env python3
"""
FILE:  openvdm_plugin.py

DESCRIPTION:  OpenVDM parser/plugin python module

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.14
  CREATED:  2016-02-02
 REVISION:  2025-12-30
"""

import fnmatch
import re
import json
import logging
from datetime import datetime
import numpy as np
import pandas as pd

from server.lib.openvdm import OpenVDM
from server.lib.condense_to_ranges import condense_to_ranges
from server.lib.file_utils import NpEncoder


STAT_TYPES = [
    'bounds',
    'geoBounds',
    'rowValidity',
    'timeBounds',
    'totalValue',
    'valueValidity'
]

QUALITY_TEST_RESULT_TYPES = [
    'Failed',
    'Warning',
    'Passed'
]

DEFAULT_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ" # ISO8601 Format, OpenRVDAS style
# DEFAULT_TIME_FORMAT = "%m/%d/%Y %H:%M:%S.%f" # SCS style


class OpenVDMParserQualityTest():
    """
    Defines data object and methods for OpenVDM parser QA tests
    """

    def __init__(self, test_name, test_value):

        if test_value not in QUALITY_TEST_RESULT_TYPES:
            raise ValueError(f"Invalid test result type: type must be one of: {', '.join(QUALITY_TEST_RESULT_TYPES)}")

        self.test_data = {
        'testName':test_name,
        'results': test_value
    }


    def get_test_data(self):
        """
        Return test data object
        """

        return self.test_data


    def to_json(self):
        """
        Return test data object as a json-formatted string
        """

        return json.dumps(self.get_test_data(), cls=NpEncoder)


class OpenVDMParserQualityTestFailed(OpenVDMParserQualityTest):
    """
    Defines data object for a failed OpenVDM QA test
    """

    def __init__(self, test_name):
        super().__init__(test_name=test_name, test_value='Failed')


class OpenVDMParserQualityTestWarning(OpenVDMParserQualityTest):
    """
    Defines data object for a partially failed (warning) OpenVDM QA test
    """

    def __init__(self, test_name):
        super().__init__(test_name=test_name, test_value='Warning')


class OpenVDMParserQualityTestPassed(OpenVDMParserQualityTest):
    """
    Defines data object for a passing OpenVDM QA test
    """

    def __init__(self, test_name):
        super().__init__(test_name=test_name, test_value='Passed')


class OpenVDMParserStat():
    """
    Defines data object and methods for OpenVDM plugin statistic
    """

    def __init__(self, stat_name, stat_type, stat_value, stat_uom=''): # pylint: disable=too-many-branches

        if stat_type not in STAT_TYPES:
            raise ValueError(f"Invalid stat type, must be one of: {', '.join(STAT_TYPES)}")

        if stat_type == 'bounds':
            if not isinstance(stat_value, list) or len(stat_value) != 2:
                raise ValueError("bounds stat requires list of length 2")

            for element in stat_value:
                if not isinstance(element, float) and not isinstance(element, int):
                    raise ValueError("bounds stat requires list of 2 numbers")
        elif stat_type == 'geoBounds':
            if not isinstance(stat_value, list) or len(stat_value) != 4:
                raise ValueError("geoBounds stat requires list of 4 numbers")
            for element in stat_value:
                if not isinstance(element, float) and not isinstance(element, int):
                    raise ValueError("geoBounds stat requires list of 4 numbers")
        elif stat_type == 'rowValidity':
            if not isinstance(stat_value, list) or len(stat_value) != 2:
                raise ValueError("rowValidity stat requires list 2 integers")
            for element in stat_value:
                if not isinstance(element, int):
                    raise ValueError("rowValidity stat requires list 2 integers")
        elif stat_type == 'timeBounds':
            if not isinstance(stat_value, list) or len(stat_value) != 2:
                raise ValueError("timeBounds stat requires list 2 datetime")
            for element in stat_value:
                if not isinstance(element, datetime):
                    logging.debug(type(element))
                    raise ValueError("timeBounds stat requires list 2 datetime objects")
        elif stat_type == 'totalValue':
            if not isinstance(stat_value, list) or len(stat_value) != 1:
                raise ValueError("totalValue stat requires list 1 number")
            for element in stat_value:
                if not isinstance(element, float) and not isinstance(element, int):
                    raise ValueError("totalValue stat requires list 1 number")
        elif stat_type == 'valueValidity':
            if not isinstance(stat_value, list) or len(stat_value) != 2:
                raise ValueError("valueValidity stat requires list 2 numbers")
            for element in stat_value:
                if not isinstance(element, float) and not isinstance(element, int):
                    raise ValueError("valueValidity stat requires list 2 numbers")

        self.stat_data = {
            'statName': stat_name,
            'statType': stat_type,
            'statUnit': stat_uom,
            'statValue': stat_value
        }


    def get_stat_data(self):
        """
        Return the statistic data
        """

        return self.stat_data


    def to_json(self):
        """
        Return the statistic data as a json-formatted string
        """

        return json.dumps(self.get_stat_data(), cls=NpEncoder)


class OpenVDMParserBoundsStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM bounds statistic
    """

    def __init__(self, stat_value, stat_name, stat_uom=''):
        super().__init__(stat_name=stat_name, stat_type="bounds", stat_value=stat_value, stat_uom=stat_uom)


class OpenVDMParserGeoBoundsStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM geoBounds statistic
    """

    def __init__(self, stat_value, stat_name='Geographic Bounds', stat_uom='ddeg'):
        super().__init__(stat_name=stat_name, stat_type="geoBounds", stat_value=stat_value, stat_uom=stat_uom)


class OpenVDMParserRowValidityStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM rowValidity statistic
    """

    def __init__(self, stat_value):
        super().__init__(stat_name="Row Validity", stat_type="rowValidity", stat_value=stat_value, stat_uom='')


class OpenVDMParserTimeBoundsStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM timeBounds statistic
    """

    def __init__(self, stat_value, stat_name='Temporal Bounds', stat_uom='seconds'):
        super().__init__(stat_name=stat_name, stat_type="timeBounds", stat_value=stat_value, stat_uom=stat_uom)


class OpenVDMParserTotalValueStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM totalValue statistic
    """

    def __init__(self, stat_value, stat_name, stat_uom=''):
        super().__init__(stat_name=stat_name, stat_type="totalValue", stat_value=stat_value, stat_uom=stat_uom)


class OpenVDMParserValueValidityStat(OpenVDMParserStat):
    """
    Defines data object and methods for OpenVDM valueValidity statistic
    """

    def __init__(self, stat_value, stat_name):
        super().__init__(stat_name=stat_name, stat_type="valueValidity", stat_value=stat_value, stat_uom='')


class OpenVDMParser():
    """
    Root Class for a OpenVDM parser object
    """

    def __init__(self, use_openvdm_api=False):
        self.openvdm = OpenVDM() if use_openvdm_api else None
        self.plugin_data = {
            'visualizerData': [],
            'qualityTests': [],
            'stats': []
        }


    def get_plugin_data(self):
        """
        Return the plugin data
        """

        if len(self.plugin_data['visualizerData']) > 0 or len(self.plugin_data['qualityTests']) > 0 or len(self.plugin_data['stats']) > 0:
            return self.plugin_data

        return None


    def process_file(self, filepath):
        """
        Legacy entry point. Calls parse() and stores results.
        """
        result = self.parse(filepath)
        return result


    def parse(self, filepath):
        """
        Unified entry point for all parsers (legacy + new)
        """

        # Preferred: new-style parsers override parse()
        if self.__class__.parse is not OpenVDMCSVParser.parse:
            result = self.__class__.parse(self, filepath)
            return result

        # Legacy-style parsers: process_file()
        if hasattr(self, 'process_file'):
            result = self.process_file(filepath)

            # Legacy parsers usually return None but populate self.plugin_data
            if result is not None:
                return result

            if hasattr(self, 'plugin_data') and self.plugin_data:
                return self.plugin_data

            return None

        raise NotImplementedError(
            f"{self.__class__.__name__} must implement parse() or process_file()"
        )


    def add_visualization_data(self, data):
        """
        Add the visualization data to the
        """

        self.plugin_data['visualizerData'].append(data)


    def add_quality_test_failed(self, name):
        """
        Add a failed QA test with the provided name
        """

        test = OpenVDMParserQualityTestFailed(name)
        self.plugin_data['qualityTests'].append(test.get_test_data())


    def add_quality_test_warning(self, name):
        """
        Add a partially failed QA test with the provided name
        """

        test = OpenVDMParserQualityTestWarning(name)
        self.plugin_data['qualityTests'].append(test.get_test_data())


    def add_quality_test_passed(self, name):
        """
        Add a passing QA test with the provided name
        """

        test = OpenVDMParserQualityTestPassed(name)
        self.plugin_data['qualityTests'].append(test.get_test_data())


    def add_bounds_stat(self, value, name, uom=''):
        """
        Add a bounds statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserBoundsStat(value, name, uom)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def add_geobounds_stat(self, value, name='Geographic Bounds', uom='ddeg'):
        """
        Add a geoBounds statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserGeoBoundsStat(value, name, uom)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def add_row_validity_stat(self, value):
        """
        Add a rowValidity statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserRowValidityStat(value)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def add_time_bounds_stat(self, value, name='Temporal Bounds', uom='seconds'):
        """
        Add a timeBounds statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserTimeBoundsStat(value, name, uom)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def add_total_value_stat(self, value, name, uom=''):
        """
        Add a totalValue statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserTotalValueStat(value, name, uom)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def add_value_validity_stat(self, value, name):
        """
        Add a valueValidity statistic with the given name, value and unit of measure
        """

        stat = OpenVDMParserValueValidityStat(value, name)
        self.plugin_data['stats'].append(stat.get_stat_data())


    def get_results(self):
        """
        Return structured parser results or None
        """
        return self.get_plugin_data()


    def to_json(self):
        """
        Return the plugin data and a json-formatted string
        """

        return json.dumps(self.get_plugin_data())


class OpenVDMCSVParser(OpenVDMParser):
    """
    OpenVDM parser for a CSV-style input file
    """

    TIMESTAMP_RE = re.compile(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z'
    )

    def __init__(self, raw_cols, proc_cols, start_dt=None, stop_dt=None,
                 time_format=None, skip_header=False, timestamp_separator=None,
                 use_openvdm_api=False):

        self.raw_cols = raw_cols
        self.proc_cols = proc_cols
        self.start_dt = start_dt
        self.stop_dt = stop_dt
        self.time_format = time_format or DEFAULT_TIME_FORMAT
        self.skip_header = skip_header
        self.use_openvdm_api = use_openvdm_api
        self.timestamp_separator=timestamp_separator or ','
        self.tmpdir = None

        # timestamp can appear anywhere
        self.timestamp_re = self.TIMESTAMP_RE

        super().__init__(use_openvdm_api=use_openvdm_api)

    def _sanitize_for_json(self, obj):
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    @classmethod
    def add_cli_arguments(cls, parser: "argparse.ArgumentParser"):  # noqa
        """
        Subclasses can override this to add custom CLI arguments.
        """
        pass

    def read_lines_with_timestamps(self, filepath, nmea_filter=None):
        """
        Generator that yields (lineno, timestamp, remainder) for each valid line in the file.

        Args:
            filepath (str): Path to the raw data file.
            nmea_filter (callable or str, optional):
                - If str, only lines where first field endswith this string are yielded.
                - If callable, should accept fields list and return True/False.
        Yields:
            lineno (int), timestamp_str (str), remainder (str)
        """
        errors = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for lineno, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    if (lineno == 0 and self.skip_header) or line.startswith('#'):
                        continue

                    timestamp_str, remainder = self.extract_timestamp_and_payload(line)
                    if not timestamp_str or not remainder:
                        errors.append(lineno)
                        continue

                    fields = remainder.split(',')

                    # Filter by NMEA sentence type
                    if nmea_filter:
                        if isinstance(nmea_filter, str):
                            if not fields[0].endswith(nmea_filter):
                                continue
                        elif callable(nmea_filter):
                            if not nmea_filter(fields):
                                continue

                    yield lineno, timestamp_str, remainder, fields

        except Exception as err:
            logging.error("Failed to read file %s: %s", filepath, err)
            return


    def crop_data(self, data_frame):
        """
        Crop the data to the start/stop time specified in the parser object
        """

        try:
            if self.start_dt is not None:
                logging.debug("  start_dt: %s", self.start_dt)
                data_frame = data_frame[(data_frame['date_time'] >= self.start_dt)]

            if self.stop_dt is not None:
                logging.debug("  stop_dt: %s", self.stop_dt)
                data_frame = data_frame[(data_frame['date_time'] <= self.stop_dt)]
        except Exception as exc:
            logging.error("Could not crop data")
            logging.error(str(exc))
            raise exc

        return data_frame


    @staticmethod
    def resample_data(data_frame, resample_interval='1min'):
        """
        Resample the data to the specified interval
        """

        try:
            resample_df = data_frame.resample(resample_interval, label='right', closed='right').mean()
        except Exception as exc:
            logging.error("Could not resample data")
            logging.error(str(exc))
            raise exc

        # reset index
        return resample_df.reset_index()


    @staticmethod
    def round_data(data_frame, precision=None):
        """
        Round the data to the specified precision
        """

        if precision is None or bool(precision):
            try:
                decimals = pd.Series(precision.values(), index=precision.keys())
                return data_frame.round(decimals)
            except Exception as exc:
                logging.error("Could not round data")
                logging.error(str(exc))
                raise exc
        return data_frame

    def extract_timestamp_and_payload(self, line):
        """
        Extract ISO8601 timestamp and payload after it.
        Returns (timestamp_str, payload) or (None, None)
        """

        match = self.timestamp_re.search(line)
        if not match:
            return None, None

        # If prefix regex was used, timestamp is in group(1)
        timestamp_str = match.group(1) if match.lastindex else match.group(0)

        remainder = line[match.end():]

        # Strip the configured timestamp_separator from payload
        if self.timestamp_separator:
            payload = remainder.lstrip(self.timestamp_separator)
        else:
            payload = remainder

        return timestamp_str, payload.strip()

    def send_error_msg(self, errors, filepath):

        error_msg = ''
        if len(errors) > 0:
            error_msg = f'Error(s) parsing datafile {filepath} on row(s): {", ".join(condense_to_ranges(errors))}'
            logging.error(error_msg)

        if self.openvdm and error_msg:
            self.openvdm.send_msg(
                'Parsing Error',
                error_msg
            )


    def to_json(self):
        """
        Output the plugin data as a json-formatted string.
        """

        return json.dumps(self.get_plugin_data(), cls=NpEncoder)

    @classmethod
    def run_cli(cls):
        import argparse
        import logging
        from datetime import datetime

        parser = argparse.ArgumentParser(description=f'{cls.__name__} CLI')
        parser.add_argument('-v', '--verbosity', dest='verbosity',
                            default=0, action='count',
                            help='Increase output verbosity')
        parser.add_argument('--timeFormat', help='timestamp format', default=None)
        parser.add_argument('--startDT', default=None,
                            type=lambda s: datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ'),
                            help='Crop start timestamp (iso8601)')
        parser.add_argument('--stopDT', default=None,
                            type=lambda s: datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ'),
                            help='Crop stop timestamp (iso8601)')
        parser.add_argument('dataFile', metavar='dataFile',
                            help='The raw data file to process')

        # Call hook to add subclass-specific arguments
        cls.add_cli_arguments(parser)

        args = parser.parse_args()

        # Setup logging
        LOGGING_FORMAT = '%(asctime)-15s %(levelname)s - %(message)s'
        logging.basicConfig(format=LOGGING_FORMAT)
        LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
        args.verbosity = min(args.verbosity, max(LOG_LEVELS))
        logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

        # Instantiate parser with common args
        instance_kwargs = {
            'start_dt': getattr(args, 'startDT', None),
            'stop_dt': getattr(args, 'stopDT', None),
            'time_format': getattr(args, 'timeFormat', None)
        }

        # Include subclass-specific kwargs if method exists
        if hasattr(cls, '_extract_custom_cli_kwargs'):
            instance_kwargs.update(cls._extract_custom_cli_kwargs(args))

        parser_instance = cls(**instance_kwargs)

        try:
            logging.info("Processing file: %s", args.dataFile)
            parser_instance.process_file(args.dataFile)
            print(parser_instance.to_json())
            logging.info("Done!")
        except Exception as err:
            logging.error(str(err))
            raise


class OpenVDMPlugin():
    """
    OpenVDM plugin object
    """

    def __init__(self, file_type_filters):
        self.file_type_filters = file_type_filters


    ###################################
    def get_data_types(self, filepath):
        """
        Return a list of data types associated with the file.
        """
        return [
            f["data_type"]
            for f in self.file_type_filters
            if fnmatch.fnmatch(filepath, f["regex"])
        ]


    def parse_file(self, filepath):
        """
        Parse the given file
        """

        raise NotImplementedError('parse_file must be implemented by subclass')


    def get_json_str(self, filepath):
        """
        Return the plugin output corresponding to the given file.
        Ensures output is JSON-serializable (legacy + new parsers).
        """

        data = self.parse_file(filepath)

        # Legacy parsers may return None but populate self.plugin_data
        if data is None and hasattr(self, 'plugin_data'):
            data = self.plugin_data

        if not data:
            return None

        return json.dumps(data, cls=NpEncoder)
