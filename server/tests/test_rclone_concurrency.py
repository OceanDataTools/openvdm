"""Tests for rclone transfer limits from the server configuration."""

import pytest
import yaml
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from server.lib import connection_utils
from server.lib.connection_utils import build_rclone_options
from server.workers.run_ship_to_shore_transfer import OVDMGearmanWorker


@pytest.mark.parametrize('concurrency, values', [
    (None, None),
    ({}, ('1', '2', '0')),
    ({'transfers': 2}, ('2', '2', '0')),
    ({'transfers': 2, 'checkers': 4, 'multiThreadStreams': 3}, ('2', '4', '3')),
])
def test_concurrency_options_and_defaults(concurrency, values):
    """Add configured limits without changing existing transfer options."""
    command, flags = build_rclone_options(
        {'destDir': '/destination', 'syncToDest': '1', 'skipEmptyDirs': '0',
         'bandwidthLimit': '47500'}, mode='real', concurrency=concurrency)
    expected = ['--progress', '--create-empty-src-dirs', '-v', '--bwlimit', '47500k']
    if values is not None:
        expected += ['--transfers', values[0], '--checkers', values[1],
                     '--multi-thread-streams', values[2]]
    assert (command, flags) == ('sync', expected)


def test_shipped_yaml_matches_fallback_defaults():
    """New and existing installations receive the same conservative limits."""
    template = Path(__file__).parents[1] / 'etc' / 'openvdm.yaml.dist'
    settings = yaml.safe_load(template.read_text(encoding='utf-8'))['rcloneConcurrency']
    config = {'destDir': '/destination'}
    assert build_rclone_options(config, concurrency=settings) == (
        build_rclone_options(config, concurrency={}))


@pytest.mark.parametrize('config, values', [
    ({}, ('1', '2', '0')),
    ({'rcloneConcurrency': {'transfers': 2, 'checkers': 4, 'multiThreadStreams': 3}},
     ('2', '4', '3')),
])
def test_ship_to_shore_uses_yaml_limits(
        monkeypatch: pytest.MonkeyPatch, config: dict, values: tuple) -> None:
    """Exercise the worker command with defaults and configured concurrency."""
    monkeypatch.setattr(connection_utils, 'get_rclone_remote_type', lambda name: 'sftp')
    worker = SimpleNamespace(
        ovdm=SimpleNamespace(config=config), cruise_id='cruise',
        cruise_data_transfer={'destDir': 'shore:archive'},
        shipboard_data_warehouse_config={'shipboardDataWarehouseBaseDir': '/data'},
        build_filelist=lambda: {'verdict': True, 'files': {'include': ['video.mp4']}},
        run_transfer_command=Mock(return_value=(['video.mp4'], [], [])))

    result = OVDMGearmanWorker.transfer_to_destination(worker, None)

    assert result['verdict'] is True
    assert result['files']['new'] == ['video.mp4']
    _, command, file_count = worker.run_transfer_command.call_args.args
    assert command[:4] == ['rclone', 'copy', '/data/', 'shore:archive/']
    for flag, value in zip(('--transfers', '--checkers', '--multi-thread-streams'), values):
        assert command[command.index(flag) + 1] == value
    assert '--files-from' in command
    assert '-v' in command
    assert file_count == 1
