#!/usr/bin/env python3
"""
FILE:  openvdm_plugin.py

DESCRIPTION:  OpenVDM parser/plugin python module

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.11
  CREATED:  2016-02-02
 REVISION:  2025-04-12
"""

import fnmatch
import json
import logging
from datetime import datetime
import numpy as np
import pandas as pd

from server.lib.openvdm import OpenVDM

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

class NpEncoder(json.JSONEncoder):
    """
    Custom JSON string encoder used to deal with NumPy arrays
    """

    def default(self, o): # pylint: disable=arguments-differ

        if isinstance(o, np.integer):
            return int(o)

        if isinstance(o, np.floating):
            return float(o)

        if isinstance(o, np.ndarray):
            return o.tolist()

        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        return super().default(o)


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
        Process the given file
        """

        raise NotImplementedError('process_file must be implemented by subclass')


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


    def to_json(self):
        """
        Return the plugin data and a json-formatted string
        """

        return json.dumps(self.get_plugin_data())


class OpenVDMCSVParser(OpenVDMParser):
    """
    OpenVDM parser for a CSV-style input file
    """

    def __init__(self, raw_cols, proc_cols, start_dt=None, stop_dt=None, time_format=None, skip_header=False, use_openvdm_api=False):
        self.raw_cols = raw_cols
        self.proc_cols = proc_cols
        self.start_dt = start_dt
        self.stop_dt = stop_dt
        self.time_format = time_format or DEFAULT_TIME_FORMAT
        self.skip_header = skip_header
        self.use_openvdm_api = use_openvdm_api
        self.tmpdir = None
        super().__init__(use_openvdm_api=use_openvdm_api)


    def process_file(self, filepath):
        """
        Process the given file
        """

        raise NotImplementedError('process_file must be implemented by subclass')


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
    def resample_data(data_frame, resample_interval='1T'):
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


    def to_json(self):
        """
        Output the plugin data as a json-formatted string.
        """

        return json.dumps(self.get_plugin_data(), cls=NpEncoder)


class OpenVDMPlugin():
    """
    OpenVDM plugin object
    """

    def __init__(self, file_type_filters):
        self.file_type_filters = file_type_filters


    def get_data_type(self, filepath):
        """
        Return the data type for the given file
        """

        file_type_filter = list(filter(lambda file_type_filter: fnmatch.fnmatch(filepath, file_type_filter['regex']), self.file_type_filters))

        if len(file_type_filter) == 0:
            return None

        return file_type_filter[0]['data_type']


    def get_parser(self, filepath):
        """
        Return the OpenVDM parser object appropriate for the given file
        """

        raise NotImplementedError('process_file must be implemented by subclass')


    def get_json_str(self, filepath):
        """
        Return the plugin output corresponding to the given file.
        """

        parser = self.get_parser(filepath)

        if parser is None:
            return None

        parser.process_file(filepath)

        return parser.to_json()
