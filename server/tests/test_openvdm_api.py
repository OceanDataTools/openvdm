"""Tests for the OpenVDM API wrapper, server/lib/openvdm.py (#509).

``OpenVDM`` reads ``openvdm.yaml`` and calls the web API for everything else.
The tests replace ``requests.get``/``post`` with :class:`FakeAPI`, which
records each request and answers it from a table, and check each method's
URL, HTTP method, payload, worker token, how it reads the response, and what
it does when the request fails or the response isn't JSON. A last test checks
that every URL ``openvdm.py`` requests has a route in ``www/app/Core/routes.php``,
so a renamed or removed endpoint fails CI rather than a worker at sea.
"""

import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from server.lib import openvdm
from server.tests.helpers import ROOT

SITE = 'http://ovdm.example/'
TOKEN = 'worker-secret'


class FakeAPI:
    """``requests.get``/``post`` for the OpenVDM API: records requests, answers from ``responses``.

    Attributes:
        responses: The response for each API path (after ``siteRoot``): a
            JSON-serialisable value, a ``str`` sent as it is, an exception
            to raise, or ``(status, body)``. Paths not listed get ``[]``.
        calls: Each request as ``SimpleNamespace(method, path, data, headers, timeout)``.
    """

    def __init__(self):
        self.responses = {}
        self.calls = []

    def _request(self, method, url, data=None, headers=None, timeout=None):
        assert url.startswith(SITE), url
        path = url[len(SITE):]
        self.calls.append(SimpleNamespace(method=method, path=path, data=data, headers=headers or {},
                                          timeout=timeout))
        answer = self.responses.get(path, [])
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer if isinstance(answer, tuple) else (200, answer)
        text = body if isinstance(body, str) else json.dumps(body)

        def raise_for_status():
            if status >= 400:
                raise requests.HTTPError(f'{status} Error')
        return SimpleNamespace(status_code=status, text=text, raise_for_status=raise_for_status)

    def get(self, url, headers=None, timeout=None):
        return self._request('GET', url, headers=headers, timeout=timeout)

    def post(self, url, data=None, headers=None, timeout=None):
        return self._request('POST', url, data=data, headers=headers, timeout=timeout)

    def paths(self):
        return [call.path for call in self.calls]


@pytest.fixture
def config_file(tmp_path):
    """A minimal openvdm.yaml."""
    path = tmp_path / 'openvdm.yaml'
    path.write_text(f"siteRoot: {SITE}\nworkerApiKey: {TOKEN}\ngearmanServer: gearman.example:4730\n"
                    "plugins:\n  pluginDir: /opt/openvdm/server/plugins\n  pluginSuffix: _plugin.py\n"
                    "hooks:\n  setupNewCruise:\n    - postSetupNewCruise\n"
                    "postHookCommands:\n  postSetupNewCruise:\n    commandList: []\n"
                    "transferInterval: 5\nlogfilePurgeTimedelta: 12 hours\n")
    return path


@pytest.fixture
def api(monkeypatch):
    """The fake API, as openvdm.py's requests."""
    fake = FakeAPI()
    monkeypatch.setattr(openvdm.requests, 'get', fake.get)
    monkeypatch.setattr(openvdm.requests, 'post', fake.post)
    return fake


@pytest.fixture
def ovdm(config_file, api):
    """An OpenVDM using the minimal config and the fake API."""
    return openvdm.OpenVDM(str(config_file))


# --- Config ---------------------------------------------------------------------

def test_read_config(config_file) -> None:
    """The config is the file's YAML mapping."""
    assert openvdm.OpenVDM.read_config(str(config_file))['siteRoot'] == SITE


@pytest.mark.parametrize('dist, message', [
    (False, 'OpenVDM configuration file not found: {path}'),
    (True, 'OpenVDM configuration file not found: {path}. Copy openvdm.yaml.dist to it, or re-run the installer.'),
])
def test_config_missing(tmp_path, caplog, dist, message) -> None:
    """A missing config says so, and to copy its .dist when there is one (#503)."""
    path = tmp_path / 'openvdm.yaml'
    if dist:
        (tmp_path / 'openvdm.yaml.dist').write_text('siteRoot: x\n')
    with pytest.raises(FileNotFoundError) as err:
        openvdm.OpenVDM(str(path))
    assert str(err.value) == message.format(path=path)
    assert message.format(path=path) in caplog.text


@pytest.mark.parametrize('text, problem', [('', 'is empty'), ('# just a comment\n', 'is empty'),
                                           ('- a list\n', "isn't a mapping of settings"),
                                           ('just a string\n', "isn't a mapping of settings")])
def test_config_not_a_mapping(tmp_path, text, problem) -> None:
    """A config that's empty or isn't a mapping is an error saying which (#503)."""
    path = tmp_path / 'openvdm.yaml'
    path.write_text(text)
    with pytest.raises(ValueError, match=f'OpenVDM configuration file {problem}: '):
        openvdm.OpenVDM(str(path))


def test_config_invalid_yaml(tmp_path, caplog) -> None:
    """Invalid YAML raises YAML's error, logged with the file."""
    path = tmp_path / 'openvdm.yaml'
    path.write_text('siteRoot: [unclosed\n')
    with pytest.raises(openvdm.YAMLError):
        openvdm.OpenVDM(str(path))
    assert f'Unable to parse configuration file {path}' in caplog.text


def test_config_unreadable(tmp_path, caplog) -> None:
    """A config that can't be opened (here, a directory) raises the error."""
    with pytest.raises(OSError):
        openvdm.OpenVDM(str(tmp_path))
    assert 'Unable to open configuration file' in caplog.text


def test_config_without_pyyaml(config_file, monkeypatch) -> None:
    """Without PyYAML, the error says to install it (#503)."""
    monkeypatch.delattr(openvdm, 'load')
    with pytest.raises(ImportError, match='PyYAML'):
        openvdm.OpenVDM(str(config_file))


@pytest.mark.parametrize('method, expected', [
    ('get_plugin_dir', '/opt/openvdm/server/plugins'), ('get_plugin_suffix', '_plugin.py'),
    ('get_gearman_server', 'gearman.example:4730'), ('get_site_root', SITE), ('get_transfer_interval', 5),
    ('get_logfile_purge_timedelta', '12 hours'), ('show_only_current_cruise_dir', False),
    ('get_transfer_public_data', True), ('get_vessel_config', {}),
])
def test_config_getters(ovdm, api, method, expected) -> None:
    """The config getters read openvdm.yaml (with defaults), and don't call the API."""
    assert getattr(ovdm, method)() == expected
    assert api.calls == []


def test_hooks_and_post_hook_commands(ovdm) -> None:
    """A hook's tasks and a post hook's commands, or nothing for one that isn't configured."""
    assert ovdm.get_tasks_for_hook('setupNewCruise') == ['postSetupNewCruise']
    assert ovdm.get_tasks_for_hook('finalizeCurrentCruise') == []
    assert ovdm.get_post_hook_commands('postSetupNewCruise') == {'commandList': []}
    assert ovdm.get_post_hook_commands('postSetupNewLowering') is None
    ovdm.config.pop('postHookCommands')
    assert ovdm.get_post_hook_commands('postSetupNewCruise') is None


def test_vessel_config(ovdm) -> None:
    """The vessel block, as strings, without unset fields or empty sub-blocks (#365)."""
    ovdm.config['vessel'] = {'name': ' Roger Revelle ', 'contact': {'institution': 'SIO', 'email': None},
                             'r2r': {'vesselID': 3301, 'operatorID': '', 'schedulerID': None}}
    assert ovdm.get_vessel_config() == {'name': 'Roger Revelle', 'contact': {'institution': 'SIO'},
                                        'r2r': {'vesselID': '3301'}}
    ovdm.config['vessel'] = {'name': '', 'contact': {'email': ''}}
    assert ovdm.get_vessel_config() == {}
    ovdm.config['vessel'] = 'not a block'
    assert ovdm.get_vessel_config() == {}


@pytest.mark.parametrize('key, headers', [(TOKEN, {'X-Worker-Token': TOKEN}), ('', {}), (None, {}),
                                         (openvdm.WORKER_API_KEY_PLACEHOLDER, {})])
def test_worker_headers(ovdm, key, headers) -> None:
    """The worker token header is sent only when workerApiKey is set."""
    if key is None:
        ovdm.config.pop('workerApiKey')
    else:
        ovdm.config['workerApiKey'] = key
    assert ovdm._worker_headers() == headers


def test_placeholder_worker_key_warned_once(ovdm, monkeypatch, caplog) -> None:
    """The placeholder worker key isn't sent, and a warning says to set a real one, once (#605)."""
    monkeypatch.setattr(openvdm.OpenVDM, '_warned_placeholder_key', False)
    ovdm.config['workerApiKey'] = openvdm.WORKER_API_KEY_PLACEHOLDER
    assert ovdm._worker_headers() == {}
    assert ovdm._worker_headers() == {}
    assert caplog.text.count('workerApiKey in openvdm.yaml is still the placeholder') == 1


def test_placeholder_is_openvdm_yaml_dists() -> None:
    """The placeholder is openvdm.yaml.dist's workerApiKey."""
    assert openvdm.OpenVDM.read_config(str(ROOT / 'server' / 'etc' / 'openvdm.yaml.dist'))['workerApiKey'] == \
        openvdm.WORKER_API_KEY_PLACEHOLDER


# --- Getters --------------------------------------------------------------------

# (method, args, API path, response, return value); a ✓ in TOKEN_PATHS sends the worker token
GETTERS = [
    ('get_show_lowering_components', (), 'api/warehouse/getShowLoweringComponents', 'true', True),
    ('get_md5_filesize_limit', (), 'api/warehouse/getMD5FilesizeLimit', {'md5FilesizeLimit': '10'}, '10'),
    ('get_md5_filesize_limit_status', (), 'api/warehouse/getMD5FilesizeLimitStatus',
     {'md5FilesizeLimitStatus': 'On'}, 'On'),
    ('get_md5_summary_fn', (), 'api/warehouse/getMD5SummaryFn', {'md5SummaryFn': 'MD5_Summary.txt'},
     'MD5_Summary.txt'),
    ('get_md5_summary_md5_fn', (), 'api/warehouse/getMD5SummaryMD5Fn', {'md5SummaryMd5Fn': 'MD5_Summary.md5'},
     'MD5_Summary.md5'),
    ('get_transfer_log_dir', (), 'api/warehouse/getTransferLogDir', {'transferLogDir': '/logs'}, '/logs'),
    ('get_cruise_id', (), 'api/warehouse/getCruiseID', {'cruiseID': 'RR2601'}, 'RR2601'),
    ('get_cruise_size', (), 'api/warehouse/getCruiseSize', {'cruiseSize': '1234'}, {'cruiseSize': '1234'}),
    ('get_cruise_start_date', (), 'api/warehouse/getCruiseStartDate', {'cruiseStartDate': '2026/10/01 00:00'},
     '2026/10/01 00:00'),
    ('get_cruise_end_date', (), 'api/warehouse/getCruiseEndDate', {'cruiseEndDate': '2026/10/20 00:00'},
     '2026/10/20 00:00'),
    ('get_cruise_config_fn', (), 'api/warehouse/getCruiseConfigFn', {'cruiseConfigFn': 'ovdmConfig.json'},
     'ovdmConfig.json'),
    ('get_cruisedata_url', (), 'api/warehouse/getCruiseDataURLPath', {'cruiseDataURLPath': '/CruiseData'},
     'http://ovdm.example/CruiseData'),
    ('get_cruisedata_path', (), 'api/warehouse/getDataWarehouseBaseDir', {'dataWarehouseBaseDir': '/data'}, '/data'),
    ('get_cruises', (), 'api/warehouse/getCruises', ['RR2601', 'RR2602'], ['RR2601', 'RR2602']),
    ('get_lowering_id', (), 'api/warehouse/getLoweringID', {'loweringID': 'DIVE01'}, 'DIVE01'),
    ('get_lowering_size', (), 'api/warehouse/getLoweringSize', {'loweringSize': '5'}, {'loweringSize': '5'}),
    ('get_lowering_start_date', (), 'api/warehouse/getLoweringStartDate', {'loweringStartDate': 'a'}, 'a'),
    ('get_lowering_end_date', (), 'api/warehouse/getLoweringEndDate', {'loweringEndDate': 'b'}, 'b'),
    ('get_lowering_config_fn', (), 'api/warehouse/getLoweringConfigFn', {'loweringConfigFn': 'l.json'}, 'l.json'),
    ('get_lowerings', (), 'api/warehouse/getLowerings', ['DIVE01'], ['DIVE01']),
    ('get_extra_directory', (4,), 'api/extraDirectories/getExtraDirectory/4', [{'name': 'Docs'}], {'name': 'Docs'}),
    ('get_extra_directories', (), 'api/extraDirectories/getExtraDirectories', [{'name': 'Docs'}], [{'name': 'Docs'}]),
    ('get_required_extra_directory', (2,), 'api/extraDirectories/getRequiredExtraDirectory/2',
     [{'name': 'Dashboard_Data'}], {'name': 'Dashboard_Data'}),
    ('get_required_extra_directories', (), 'api/extraDirectories/getRequiredExtraDirectories', [{'name': 'a'}],
     [{'name': 'a'}]),
    ('get_shipboard_data_warehouse_config', (), 'api/warehouse/getShipboardDataWarehouseConfig',
     {'shipboardDataWarehouseBaseDir': '/data'}, {'shipboardDataWarehouseBaseDir': '/data'}),
    ('get_ship_to_shore_bw_limit_status', (), 'api/warehouse/getShipToShoreBWLimitStatus',
     {'shipToShoreBWLimitStatus': 'On'}, True),
    ('get_ship_to_shore_transfer', (3,), 'api/shipToShoreTransfers/getShipToShoreTransfer/3', [{'name': 'Nav'}],
     {'name': 'Nav'}),
    ('get_ship_to_shore_transfers', (), 'api/shipToShoreTransfers/getShipToShoreTransfers', [{'name': 'Nav'}],
     [{'name': 'Nav'}]),
    ('get_required_ship_to_shore_transfers', (), 'api/shipToShoreTransfers/getRequiredShipToShoreTransfers',
     [{'name': 'Logs'}], [{'name': 'Logs'}]),
    ('get_system_status', (), 'api/warehouse/getSystemStatus', {'systemStatus': 'On'}, 'On'),
    ('get_tasks', (), 'api/tasks/getTasks', [{'taskID': 1}], [{'taskID': 1}]),
    ('get_active_tasks', (), 'api/tasks/getActiveTasks', [{'taskID': 1}], [{'taskID': 1}]),
    ('get_task', (7,), 'api/tasks/getTask/7', [{'taskID': 7}], {'taskID': 7}),
    ('get_collection_system_transfers', (), 'api/collectionSystemTransfers/getCollectionSystemTransfers',
     [{'name': 'SCS'}], [{'name': 'SCS'}]),
    ('get_collection_system_transfer', (3,), 'api/collectionSystemTransfers/getCollectionSystemTransfer/3',
     [{'name': 'SCS'}], {'name': 'SCS'}),
    ('get_cruise_data_transfers', (), 'api/cruiseDataTransfers/getCruiseDataTransfers', [{'name': 'USB'}],
     [{'name': 'USB'}]),
    ('get_required_cruise_data_transfers', (), 'api/cruiseDataTransfers/getRequiredCruiseDataTransfers',
     [{'name': 'SSDW'}], [{'name': 'SSDW'}]),
    ('get_cruise_data_transfer', (2,), 'api/cruiseDataTransfers/getCruiseDataTransfer/2', [{'name': 'USB'}],
     {'name': 'USB'}),
    ('get_required_cruise_data_transfer', (4,), 'api/cruiseDataTransfers/getRequiredCruiseDataTransfer/4',
     [{'name': 'SSDW'}], {'name': 'SSDW'}),
    ('get_data_dashboard_manifest_fn', (), 'api/warehouse/getDataDashboardManifestFn',
     {'dataDashboardManifestFn': 'manifest.json'}, 'manifest.json'),
]

# The getters whose responses have transfer credentials: they send the worker token
TOKEN_METHODS = {'get_collection_system_transfers', 'get_active_collection_system_transfers',
                 'get_collection_system_transfer', 'get_cruise_data_transfers', 'get_required_cruise_data_transfers',
                 'get_cruise_data_transfer', 'get_required_cruise_data_transfer'}


@pytest.mark.parametrize('method, args, path, response, expected', GETTERS, ids=[row[0] for row in GETTERS])
def test_getter(ovdm, api, method, args, path, response, expected) -> None:
    """Each getter GETs its URL, with the timeout, and reads the response; only the transfer
    getters send the worker token."""
    api.responses[path] = response
    assert getattr(ovdm, method)(*args) == expected
    assert [(call.method, call.path) for call in api.calls] == [('GET', path)]
    assert api.calls[0].timeout == openvdm.TIMEOUT
    assert api.calls[0].headers == ({'X-Worker-Token': TOKEN} if method in TOKEN_METHODS else {})


@pytest.mark.parametrize('method, args, path, response', [
    ('get_extra_directory', (9,), 'api/extraDirectories/getExtraDirectory/9', []),
    ('get_task', (9,), 'api/tasks/getTask/9', []),
    ('get_collection_system_transfer', (9,), 'api/collectionSystemTransfers/getCollectionSystemTransfer/9', []),
    ('get_lowering_id', (), 'api/warehouse/getLoweringID', {'loweringID': ''}),
    ('get_cruise_id', (), 'api/warehouse/getCruiseID', {}),
])
def test_getter_nothing(ovdm, api, method, args, path, response) -> None:
    """A getter for one thing returns None when there's no such thing (an empty lowering ID too)."""
    api.responses[path] = response
    assert getattr(ovdm, method)(*args) is None


@pytest.mark.parametrize('method, response, expected', [
    ('get_show_lowering_components', 'false', False),
    ('get_ship_to_shore_bw_limit_status', {'shipToShoreBWLimitStatus': 'Off'}, False),
    ('get_transfer_log_dir', {}, '/var/log/openvdm'),
])
def test_getter_other_values(ovdm, api, method, response, expected) -> None:
    """The flags are false for anything but true/On; the log directory has a default."""
    path = next(row[2] for row in GETTERS if row[0] == method)
    api.responses[path] = response
    assert getattr(ovdm, method)() == expected


def test_collection_system_transfer_without_id(ovdm, api) -> None:
    """Without an ID there's no transfer, and the API isn't asked."""
    assert ovdm.get_collection_system_transfer(None) is None
    assert api.calls == []


@pytest.mark.parametrize('method', ['get_cruise_config', 'get_lowering_config'])
def test_config_exports(ovdm, api, method, monkeypatch) -> None:
    """The cruise and lowering configs get configCreatedOn, now in UTC; they don't send the worker
    token, so the export has no credentials."""
    path = {'get_cruise_config': 'api/warehouse/getCruiseConfig',
            'get_lowering_config': 'api/warehouse/getLoweringConfig'}[method]
    api.responses[path] = {'cruiseID': 'RR2601'}

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 23, 12, 0, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(openvdm, 'datetime', FixedNow)
    assert getattr(ovdm, method)() == {'cruiseID': 'RR2601', 'configCreatedOn': '2026/10/23T12:00:01Z'}
    assert api.calls[0].headers == {}


# --- Filters and lookups by name --------------------------------------------------

DIRS = [{'name': 'Docs', 'cruiseOrLowering': 0}, {'name': 'Dives', 'cruiseOrLowering': 1}]
CSTS = [{'name': 'SCS', 'cruiseOrLowering': '0'}, {'name': 'ROV', 'cruiseOrLowering': '1'}]


@pytest.mark.parametrize('kwargs, names', [({}, ['Docs', 'Dives']), ({'cruise': False}, ['Dives']),
                                           ({'lowering': False}, ['Docs']), ({'cruise': False, 'lowering': False}, [])])
def test_active_extra_directories(ovdm, api, kwargs, names) -> None:
    """The active extra directories, without the cruise or lowering ones if asked."""
    api.responses['api/extraDirectories/getActiveExtraDirectories'] = DIRS
    assert [d['name'] for d in ovdm.get_active_extra_directories(**kwargs)] == names


@pytest.mark.parametrize('kwargs, path, names', [
    ({}, 'getActiveCollectionSystemTransfers/name', ['SCS', 'ROV']),
    ({'sort': 'longName', 'cruise': False}, 'getActiveCollectionSystemTransfers/longName', ['ROV']),
    ({'lowering': False}, 'getActiveCollectionSystemTransfers/name', ['SCS']),
])
def test_active_collection_system_transfers(ovdm, api, kwargs, path, names) -> None:
    """Active transfers, sorted by the API, without the cruise or lowering ones if asked; the
    worker token is sent."""
    api.responses[f'api/collectionSystemTransfers/{path}'] = CSTS
    assert [t['name'] for t in ovdm.get_active_collection_system_transfers(**kwargs)] == names
    assert api.calls[0].headers == {'X-Worker-Token': TOKEN}


def test_active_cruise_data_transfers(ovdm, api) -> None:
    """The enabled cruise data transfers."""
    api.responses['api/cruiseDataTransfers/getCruiseDataTransfers'] = [{'name': 'USB', 'enable': '1'},
                                                                       {'name': 'NAS', 'enable': 0}]
    assert [t['name'] for t in ovdm.get_active_cruise_data_transfers()] == ['USB']


@pytest.mark.parametrize('method, path, name, found', [
    ('get_task_by_name', 'api/tasks/getTasks', 'rebuildMD5Summary', True),
    ('get_task_by_name', 'api/tasks/getTasks', 'other', False),
    ('get_extra_directory_by_name', 'api/extraDirectories/getExtraDirectories', 'rebuildMD5Summary', True),
    ('get_required_extra_directory_by_name', 'api/extraDirectories/getRequiredExtraDirectories', 'rebuildMD5Summary',
     True),
    ('get_collection_system_transfer_by_name', 'api/collectionSystemTransfers/getCollectionSystemTransfers',
     'rebuildMD5Summary', True),
    ('get_cruise_data_transfer_by_name', 'api/cruiseDataTransfers/getCruiseDataTransfers', 'other', False),
    ('get_required_cruise_data_transfer_by_name', 'api/cruiseDataTransfers/getRequiredCruiseDataTransfers',
     'rebuildMD5Summary', True),
])
def test_by_name(ovdm, api, method, path, name, found) -> None:
    """The lookups by name find the one with that name in the list, or None."""
    api.responses[path] = [{'name': 'first'}, {'name': 'rebuildMD5Summary', 'id': 2}]
    result = getattr(ovdm, method)(name)
    assert result == ({'name': 'rebuildMD5Summary', 'id': 2} if found else None)


# --- Setters --------------------------------------------------------------------

TRANSFERS = {
    'api/collectionSystemTransfers/getCollectionSystemTransfer/3': [{'name': 'SCS'}],
    'api/cruiseDataTransfers/getCruiseDataTransfer/2': [{'name': 'USB'}],
    'api/tasks/getTask/7': [{'longName': 'Rebuild MD5 Summary'}],
}


@pytest.mark.parametrize('method, args, path', [
    ('clear_gearman_jobs_from_db', (), 'api/gearman/clearAllJobsFromDB'),
    ('set_idle_collection_system_transfer', (3,), 'api/collectionSystemTransfers/setIdleCollectionSystemTransfer/3'),
    ('set_idle_cruise_data_transfer', (2,), 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/2'),
    ('set_idle_task', (7,), 'api/tasks/setIdleTask/7'),
])
def test_simple_setters(ovdm, api, method, args, path) -> None:
    """These setters GET their URL."""
    getattr(ovdm, method)(*args)
    assert [(call.method, call.path, call.timeout) for call in api.calls] == [('GET', path, openvdm.TIMEOUT)]


def test_send_msg(ovdm, api) -> None:
    """A message is POSTed with its title and body."""
    ovdm.send_msg('Title', 'Body')
    assert [(call.method, call.path, call.data) for call in api.calls] == [
        ('POST', 'api/messages/newMessage', {'messageTitle': 'Title', 'messageBody': 'Body'})]


@pytest.mark.parametrize('method, args, get_path, set_path, title', [
    ('set_error_collection_system_transfer', (3, 'it broke'), 'api/collectionSystemTransfers/getCollectionSystemTransfer/3',
     'api/collectionSystemTransfers/setErrorCollectionSystemTransfer/3', 'SCS Data Transfer failed'),
    ('set_error_collection_system_transfer_test', (3, 'it broke'),
     'api/collectionSystemTransfers/getCollectionSystemTransfer/3',
     'api/collectionSystemTransfers/setErrorCollectionSystemTransfer/3', 'SCS Connection test failed'),
    ('set_error_cruise_data_transfer', (2, 'it broke'), 'api/cruiseDataTransfers/getCruiseDataTransfer/2',
     'api/cruiseDataTransfers/setErrorCruiseDataTransfer/2', 'USB Data Transfer failed'),
    ('set_error_cruise_data_transfer_test', (2, 'it broke'), 'api/cruiseDataTransfers/getCruiseDataTransfer/2',
     'api/cruiseDataTransfers/setErrorCruiseDataTransfer/2', 'USB Connection test failed'),
    ('set_error_task', (7, 'it broke'), 'api/tasks/getTask/7', 'api/tasks/setErrorTask/7',
     'Rebuild MD5 Summary failed'),
])
def test_set_error(ovdm, api, method, args, get_path, set_path, title) -> None:
    """Setting an error sets the status and posts a message titled after the transfer or task."""
    api.responses.update(TRANSFERS)
    getattr(ovdm, method)(*args)
    assert [(call.method, call.path) for call in api.calls] == [('GET', get_path), ('GET', set_path),
                                                                ('POST', 'api/messages/newMessage')]
    assert api.calls[-1].data == {'messageTitle': title, 'messageBody': 'it broke'}


@pytest.mark.parametrize('method', ['set_error_collection_system_transfer_test', 'set_error_cruise_data_transfer_test'])
def test_set_error_test_message_only(ovdm, api, method) -> None:
    """A connection test's error can be posted without setting the status (a job is running it, #478)."""
    api.responses.update(TRANSFERS)
    getattr(ovdm, method)(3 if 'collection' in method else 2, 'it broke', set_status=False)
    assert [call.path for call in api.calls][1:] == ['api/messages/newMessage']


@pytest.mark.parametrize('method, args', [
    ('set_error_collection_system_transfer', (9,)), ('set_error_collection_system_transfer_test', (9,)),
    ('set_error_cruise_data_transfer', (9,)), ('set_error_cruise_data_transfer_test', (9,)),
    ('set_error_task', (9,)), ('set_running_collection_system_transfer', (9, 1, 'H:1')),
    ('set_running_collection_system_transfer_test', (9, 1, 'H:1')), ('set_running_cruise_data_transfer', (9, 1, 'H:1')),
    ('set_running_cruise_data_transfer_test', (9, 1, 'H:1')), ('set_running_task', (9, 1, 'H:1')),
])
def test_unknown_id(ovdm, api, method, args) -> None:
    """Setting the status of a transfer or task OpenVDM doesn't have is an error; nothing is set."""
    with pytest.raises(ValueError, match='Invalid'):
        getattr(ovdm, method)(*args)
    assert all(call.method == 'GET' and '/get' in call.path for call in api.calls)


@pytest.mark.parametrize('method, args, set_path, job_name', [
    ('set_running_collection_system_transfer', (3, 1234, 'H:host:9'),
     'api/collectionSystemTransfers/setRunningCollectionSystemTransfer/3', 'Transfer for SCS'),
    ('set_running_cruise_data_transfer', (2, 1234, 'H:host:9'),
     'api/cruiseDataTransfers/setRunningCruiseDataTransfer/2', 'Transfer for USB'),
    ('set_running_task', (7, 1234, 'H:host:9'), 'api/tasks/setRunningTask/7', 'Rebuild MD5 Summary'),
    ('set_running_collection_system_transfer_test', (3, 1234, 'H:host:9'), None, 'Transfer test for SCS'),
    ('set_running_cruise_data_transfer_test', (2, 1234, 'H:host:9'), None, 'Transfer test for USB'),
])
def test_set_running(ovdm, api, method, args, set_path, job_name) -> None:
    """Setting a transfer or task running POSTs the job's PID and tracks its Gearman job; a connection
    test only tracks its job."""
    api.responses.update(TRANSFERS)
    getattr(ovdm, method)(*args)
    posts = [(call.path, call.data) for call in api.calls if call.method == 'POST']
    expected = [(set_path, {'jobPid': 1234})] if set_path else []
    assert posts == expected + [('api/gearman/newJob/H:host:9', {'jobName': job_name, 'jobPid': 1234})]


@pytest.mark.parametrize('method, path, payload', [
    ('set_cruise_size', 'api/warehouse/setCruiseSize', {'bytes': 1234}),
    ('set_lowering_size', 'api/warehouse/setLoweringSize', {'bytes': 1234}),
])
def test_set_sizes(ovdm, api, method, path, payload) -> None:
    """Sizes are POSTed in bytes."""
    getattr(ovdm, method)(1234)
    assert [(call.method, call.path, call.data) for call in api.calls] == [('POST', path, payload)]


@pytest.mark.parametrize('method, path', [('set_cruise_extent', 'api/warehouse/setCruiseExtent'),
                                          ('set_lowering_extent', 'api/warehouse/setLoweringExtent')])
def test_set_extent(ovdm, api, method, path) -> None:
    """An extent is POSTed as JSON with the worker token (#366, #399); None clears it; a refused
    extent (e.g. a wrong token) raises."""
    extent = {'westernmost': -120.5, 'easternmost': -117.2, 'southernmost': 32.1, 'northernmost': 33.9}
    getattr(ovdm, method)(extent)
    assert api.calls[0].data == {'extent': json.dumps(extent)}
    assert api.calls[0].headers == {'X-Worker-Token': TOKEN}
    getattr(ovdm, method)(None)
    assert api.calls[1].data == {'extent': ''}
    api.responses[path] = (403, 'Forbidden')
    with pytest.raises(requests.HTTPError):
        getattr(ovdm, method)(extent)


@pytest.mark.parametrize('method, transfer_id, path', [
    ('clear_error_collection_system_transfer', 3, 'api/collectionSystemTransfers/setIdleCollectionSystemTransfer/3'),
    ('clear_error_cruise_data_transfer', 2, 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/2'),
])
def test_clear_error(ovdm, api, method, transfer_id, path) -> None:
    """Clearing an error sets the transfer idle only if its status is error (3)."""
    getattr(ovdm, method)(transfer_id, 2)
    assert api.calls == []
    getattr(ovdm, method)(transfer_id, 3)
    assert api.paths() == [path]


# --- Failures -----------------------------------------------------------------------

# Every method that calls the API, with arguments (the transfer and task lookups succeed)
API_CALLS = [(row[0], row[1]) for row in GETTERS] + [
    ('clear_gearman_jobs_from_db', ()), ('get_cruise_config', ()), ('get_lowering_config', ()),
    ('get_active_extra_directories', ()), ('get_active_collection_system_transfers', ()),
    ('get_task_by_name', ('x',)), ('send_msg', ('t', 'b')), ('clear_error_collection_system_transfer', (3, 3)),
    ('clear_error_cruise_data_transfer', (2, 3)), ('set_error_collection_system_transfer', (3,)),
    ('set_error_collection_system_transfer_test', (3,)), ('set_error_cruise_data_transfer', (2,)),
    ('set_error_cruise_data_transfer_test', (2,)), ('set_error_task', (7,)),
    ('set_idle_collection_system_transfer', (3,)), ('set_idle_cruise_data_transfer', (2,)), ('set_idle_task', (7,)),
    ('set_running_collection_system_transfer', (3, 1, 'H:1')), ('set_running_cruise_data_transfer', (2, 1, 'H:1')),
    ('set_running_task', (7, 1, 'H:1')), ('track_gearman_job', ('Job', 1, 'H:1')), ('set_cruise_size', (5,)),
    ('set_lowering_size', (5,)), ('set_cruise_extent', (None,)), ('set_lowering_extent', (None,)),
]


@pytest.mark.parametrize('method, args', API_CALLS, ids=[call[0] for call in API_CALLS])
def test_api_unreachable(ovdm, api, caplog, method, args) -> None:
    """When the API can't be reached, the error is logged and raised."""
    # A setter's own lookup of its transfer or task succeeds; then the API goes away
    api.responses.update({path: requests.ConnectionError('connection refused') for _, _, path, _, _ in GETTERS})
    if not method.startswith('get_'):
        api.responses.update(TRANSFERS)
    for path in ('api/messages/newMessage', 'api/gearman/newJob/H:1', 'api/gearman/clearAllJobsFromDB',
                 'api/warehouse/getCruiseConfig', 'api/warehouse/getLoweringConfig',
                 'api/extraDirectories/getActiveExtraDirectories',
                 'api/collectionSystemTransfers/getActiveCollectionSystemTransfers/name',
                 'api/collectionSystemTransfers/setErrorCollectionSystemTransfer/3',
                 'api/collectionSystemTransfers/setIdleCollectionSystemTransfer/3',
                 'api/collectionSystemTransfers/setRunningCollectionSystemTransfer/3',
                 'api/cruiseDataTransfers/setErrorCruiseDataTransfer/2',
                 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/2',
                 'api/cruiseDataTransfers/setRunningCruiseDataTransfer/2', 'api/tasks/setErrorTask/7',
                 'api/tasks/setIdleTask/7', 'api/tasks/setRunningTask/7', 'api/warehouse/setCruiseSize',
                 'api/warehouse/setLoweringSize', 'api/warehouse/setCruiseExtent', 'api/warehouse/setLoweringExtent'):
        api.responses[path] = requests.ConnectionError('connection refused')
    with pytest.raises(requests.ConnectionError):
        getattr(ovdm, method)(*args)
    assert 'OpenVDM API' in caplog.text


JSON_GETTERS = [row for row in GETTERS if row[0] != 'get_show_lowering_components'] + [
    ('get_cruise_config', (), 'api/warehouse/getCruiseConfig', None, None)]


@pytest.mark.parametrize('method, args, path', [row[:3] for row in JSON_GETTERS], ids=[row[0] for row in JSON_GETTERS])
def test_not_json(ovdm, api, caplog, method, args, path) -> None:
    """A response that isn't JSON (e.g. a PHP error page) raises, and the error is logged."""
    api.responses[path] = (500, '<html>Internal Server Error</html>')
    with pytest.raises(json.JSONDecodeError):
        getattr(ovdm, method)(*args)
    assert 'from OpenVDM API' in caplog.text


# --- MD5 summary jobs -------------------------------------------------------------

@pytest.fixture
def warehouse_api(api, tmp_path):
    api.responses['api/warehouse/getCruiseID'] = {'cruiseID': 'RR2601'}
    api.responses['api/warehouse/getShipboardDataWarehouseConfig'] = {'shipboardDataWarehouseBaseDir': str(tmp_path)}
    return tmp_path / 'RR2601'


def test_update_md5_summary(ovdm, warehouse_api, fake_gearman) -> None:
    """An updateMD5Summary job lists the files relative to the cruise (absolute paths inside it too)."""
    assert ovdm.update_md5_summary(new=['Tracks/a.geojson', str(warehouse_api / 'Tracks' / 'b.kml')],
                                   updated=['Tracks/./c.kml'], deleted=['old.txt']) is True
    assert fake_gearman.jobs == [('updateMD5Summary', {'cruiseID': 'RR2601', 'files': {
        'new': ['Tracks/a.geojson', 'Tracks/b.kml'], 'updated': ['Tracks/c.kml'], 'deleted': ['old.txt']}})]


def test_update_md5_summary_other_cruise(ovdm, warehouse_api, api, fake_gearman) -> None:
    """A job for another cruise doesn't ask for the current one."""
    ovdm.update_md5_summary(new=['a.txt'], cruise_id='RR2600')
    assert fake_gearman.jobs[0][1]['cruiseID'] == 'RR2600'
    assert 'api/warehouse/getCruiseID' not in api.paths()


def test_update_md5_summary_nothing(ovdm, warehouse_api, fake_gearman) -> None:
    """With no files, no job is queued."""
    assert ovdm.update_md5_summary() is False
    assert fake_gearman.jobs == []


@pytest.mark.parametrize('path', ['../other/a.txt', '/etc/passwd', '.', 'a/../..'])
def test_update_md5_summary_outside_cruise(ovdm, warehouse_api, fake_gearman, path) -> None:
    """A path outside the cruise directory is an error, and no job is queued."""
    with pytest.raises(ValueError, match='is not in the cruise directory'):
        ovdm.update_md5_summary(new=[path])
    assert fake_gearman.jobs == []


def test_update_md5_summary_no_cruise(ovdm, api, fake_gearman) -> None:
    """Without a cruise there's no summary to update."""
    api.responses['api/warehouse/getCruiseID'] = {'cruiseID': None}
    with pytest.raises(ValueError, match='No cruise'):
        ovdm.update_md5_summary(new=['a.txt'])


# --- Routes -------------------------------------------------------------------------

def _routes():
    """The API routes in routes.php: (HTTP method or 'ANY', regex of the path)."""
    text = (ROOT / 'www' / 'app' / 'Core' / 'routes.php').read_text()
    routes = []
    for verb, pattern in re.findall(r"Router::(any|get|post)\('(api/[^']*)'", text):
        regex = re.escape(pattern).replace(r'\(:num\)', r'\d+').replace(r'\(:any\)', r'[^/]+').replace(
            r'\(:all\)', r'.+')
        routes.append((verb.upper(), re.compile(f'{regex}$')))
    return routes


# URLs openvdm.py requests that have no route (#592)
KNOWN_UNROUTED = {'GET api/extraDirectories/getRequiredExtraDirectory/2',
                  'GET api/shipToShoreTransfers/getShipToShoreTransfer/3'}


def _unrouted(calls):
    routes = _routes()
    return {f'{call.method} {call.path}' for call in calls
            if not any(verb in ('ANY', call.method) and regex.match(call.path) for verb, regex in routes)}


def _call_everything(ovdm, api):
    api.responses.update({path: response for _, _, path, response, _ in GETTERS})
    api.responses.update(TRANSFERS)
    api.responses['api/warehouse/getCruiseConfig'] = api.responses['api/warehouse/getLoweringConfig'] = {}
    api.responses['api/tasks/getTasks'] = [{'taskID': 7, 'name': 'x'}]
    for method, args in API_CALLS:
        getattr(ovdm, method)(*args)
    ovdm.get_active_collection_system_transfers(sort='longName')


def test_every_api_url_has_a_route(ovdm, api, warehouse_api, fake_gearman) -> None:
    """Every URL openvdm.py requests matches a route in routes.php, for its HTTP method."""
    _call_everything(ovdm, api)
    assert sorted(_unrouted(api.calls) - KNOWN_UNROUTED) == []
    # and every URL openvdm.py builds was requested, so none goes unchecked
    source = (ROOT / 'server' / 'lib' / 'openvdm.py').read_text()
    templates = set(re.findall(r'siteRoot\'\]\}(api/[^"]+)"', source))
    missed = [template for template in templates
              if not any(re.fullmatch(re.sub(r'\\\{\w+\\\}', '[^/]+', re.escape(template)), call.path)
                         for call in api.calls)]
    assert len(templates) >= 60 and missed == []


@pytest.mark.xfail(strict=True, reason="two methods call endpoints that don't exist (#592)")
def test_known_unrouted_urls(ovdm, api) -> None:
    """get_required_extra_directory() and get_ship_to_shore_transfer() have routes."""
    _call_everything(ovdm, api)
    assert not _unrouted(api.calls) & KNOWN_UNROUTED


def test_route_check_catches_a_missing_route(ovdm, api) -> None:
    """The route check fails for a URL with no route."""
    routes = _routes()
    assert not any(regex.match('api/warehouse/getNoSuchThing') for _, regex in routes)
    assert not any(verb in ('ANY', 'GET') and regex.match('api/warehouse/setCruiseSize') for verb, regex in routes)


# --- Bugs ---------------------------------------------------------------------------

@pytest.mark.parametrize('status, cleared', [(3, True), ('3', True), (1, False), (2, False)])
def test_clear_error_task(ovdm, api, status, cleared) -> None:
    """Clearing a task's error sets it idle only if its status is error, 3: a number, as the API
    sends it, or a string (#593)."""
    api.responses['api/tasks/getTask/7'] = [{'taskID': 7, 'status': status}]
    ovdm.clear_error_task(7)
    assert ('api/tasks/setIdleTask/7' in api.paths()) == cleared


@pytest.mark.parametrize('method, args, path', [
    ('set_idle_task', (7,), 'api/tasks/setIdleTask/7'),
    ('send_msg', ('t', 'b'), 'api/messages/newMessage'),
    ('set_cruise_size', (5,), 'api/warehouse/setCruiseSize'),
    ('set_idle_cruise_data_transfer', (7,), 'api/cruiseDataTransfers/setIdleCruiseDataTransfer/7'),
    ('track_gearman_job', ('job', 1, 'H:1'), 'api/gearman/newJob/H:1'),
    ('clear_gearman_jobs_from_db', (), 'api/gearman/clearAllJobsFromDB'),
])
def test_setter_http_error(ovdm, api, method, args, path) -> None:
    """A setter the API answers with an error (e.g. a 404 for a route that's gone, or a 500) raises (#594)."""
    api.responses[path] = (404, 'Not Found')
    with pytest.raises(requests.HTTPError):
        getattr(ovdm, method)(*args)
