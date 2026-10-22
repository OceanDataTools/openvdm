"""Tests for the shared test fixtures in conftest.py (#506)."""

import json
import sys

import pytest

from server.lib import openvdm
from server.tests.helpers import CONFIG_METHODS, PASS, FakeGearmanClient


def test_load_dist_imports_a_parser(load_dist) -> None:
    """A .py.dist parser loads as a module, under a name that can't clash."""
    module = load_dist('server/plugins/parsers/gga_parser.py.dist')
    assert module.__name__ == 'dist_gga_parser'
    assert hasattr(module, 'GGAParser')
    assert sys.modules['dist_gga_parser'] is module


def test_load_dist_imports_a_bin_script(load_dist) -> None:
    """bin/ scripts load too, without running their main()."""
    module = load_dist('bin/build_remote_directory.py.dist', name='build_remote_directory')
    assert callable(module.main)


def test_load_dist_cleans_up(load_dist) -> None:
    """The module is gone from sys.modules after the test (checked by the next test)."""
    load_dist('server/plugins/parsers/hdt_parser.py.dist')
    assert 'dist_hdt_parser' in sys.modules


def test_load_dist_cleaned_up() -> None:
    """The previous test's module was removed."""
    assert 'dist_hdt_parser' not in sys.modules


def test_warehouse(warehouse) -> None:
    """The cruise and PublicData directories exist, and the config points to them."""
    assert warehouse.cruise_dir.is_dir() and warehouse.publicdata_dir.is_dir()
    assert warehouse.config['shipboardDataWarehouseBaseDir'] == str(warehouse.cruise_dir.parent)
    assert warehouse.cruise_dir.name == warehouse.cruise_id


def test_fake_ovdm_reads_its_config(fake_ovdm, warehouse) -> None:
    """Config getters run the real code on the config, which a test can change."""
    assert fake_ovdm.get_gearman_server() == fake_ovdm.config['gearmanServer']
    fake_ovdm.config['gearmanServer'] = 'gearman:4730'
    assert fake_ovdm.get_gearman_server() == 'gearman:4730'
    assert fake_ovdm.get_tasks_for_hook('noSuchHook') == []
    assert fake_ovdm.get_shipboard_data_warehouse_config() == warehouse.config
    assert fake_ovdm.get_cruise_id() == 'TEST001'


def test_fake_ovdm_records_api_calls(fake_ovdm) -> None:
    """API methods make no requests; their calls are recorded."""
    fake_ovdm.send_msg('Title', 'Body')
    fake_ovdm.send_msg.assert_called_once_with('Title', 'Body')


def test_fake_ovdm_rejects_unknown_methods_and_arguments(fake_ovdm) -> None:
    """Autospec catches a misspelled method or a wrong signature."""
    with pytest.raises(AttributeError):
        fake_ovdm.send_message('x')
    with pytest.raises(TypeError):
        fake_ovdm.set_idle_task()


def test_config_methods_make_no_calls() -> None:
    """The methods run for real are only config readers, and there are some."""
    assert 'get_gearman_server' in CONFIG_METHODS and 'get_vessel_config' in CONFIG_METHODS
    assert 'get_cruise_id' not in CONFIG_METHODS and 'send_msg' not in CONFIG_METHODS


def test_fake_gearman_records_and_scripts(fake_gearman) -> None:
    """Jobs are recorded with decoded data; results default to PASS or follow the script."""
    fake_gearman.results['runCollectionSystemTransfer'] = ['first', 'second']
    fake_gearman.results['stopJob'] = lambda data: json.dumps({'pid': data['pid']})

    assert fake_gearman.submit_job('updateMD5Summary', json.dumps({'cruiseID': 'C1'})).result == PASS
    requests = fake_gearman.submit_multiple_jobs([
        {'task': 'runCollectionSystemTransfer', 'data': '{"id": 1}'},
        {'task': 'runCollectionSystemTransfer', 'data': '{"id": 2}'},
    ])
    assert [r.result for r in fake_gearman.wait_until_jobs_completed(requests)] == ['first', 'second']
    assert json.loads(fake_gearman.submit_job('stopJob', '{"pid": 7}').result) == {'pid': 7}

    assert fake_gearman.tasks() == ['updateMD5Summary', 'runCollectionSystemTransfer',
                                    'runCollectionSystemTransfer', 'stopJob']
    assert fake_gearman.jobs[0] == ('updateMD5Summary', {'cruiseID': 'C1'})


def test_fake_gearman_replaces_clients_code_makes(fake_gearman) -> None:
    """Code that creates its own GearmanClient gets the fake."""
    client = openvdm.python3_gearman.GearmanClient(['localhost:4730'])
    assert client is fake_gearman
    assert isinstance(client, FakeGearmanClient)
