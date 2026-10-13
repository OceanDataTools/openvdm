"""Tests for rclone transfer limits from the server configuration."""

import pytest
import yaml
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from server.lib import connection_utils
from server.lib.connection_utils import (RCLONE_LOCAL_CONCURRENCY, build_rclone_options,
                                         rclone_concurrency, rclone_destination)
from server.workers.run_ship_to_shore_transfer import OVDMGearmanWorker

CONCURRENCY_FLAGS = ('--transfers', '--checkers', '--multi-thread-streams')


@pytest.mark.parametrize('concurrency, expected_limits', [
    (None, []),
    ({}, []),
    ({'transfers': 2}, ['--transfers', '2']),
    ({'transfers': 2, 'checkers': 4, 'multiThreadStreams': 0},
     ['--transfers', '2', '--checkers', '4', '--multi-thread-streams', '0']),
    ({'transfers': None, 'checkers': '', 'multiThreadStreams': 3},
     ['--multi-thread-streams', '3']),
])
def test_build_rclone_options_adds_set_limits(concurrency, expected_limits):
    """Add an option for each limit that's set, after the existing options."""
    command, flags = build_rclone_options(
        {'destDir': '/destination', 'syncToDest': '1', 'skipEmptyDirs': '0',
         'bandwidthLimit': '47500'}, mode='real', concurrency=concurrency)
    expected = ['--progress', '--create-empty-src-dirs', '-v', '--bwlimit', '47500k']
    assert (command, flags) == ('sync', expected + expected_limits)


@pytest.mark.parametrize('transfer_type, dest_dir, expected', [
    ('local', '/mnt/backup', 'local'),
    ('smb', '/tmp/tmpabc/mntpoint/backup', 'local'),
    ('local', 's3remote:bucket/backup', 'remote'),
    ('ssh', 'ssh_dest:/data/backup', 'remote'),
    ('ftp', 'ftp_source:/data/backup', 'remote'),
])
def test_rclone_destination(transfer_type, dest_dir, expected):
    """Local directories and SMB mounts are local; rclone remotes are remote."""
    assert rclone_destination(transfer_type, dest_dir) == expected


@pytest.mark.parametrize('config, local, remote', [
    # No block (openvdm.yaml from before #465), or a malformed one
    ({}, RCLONE_LOCAL_CONCURRENCY, None),
    ({'rcloneConcurrency': None}, RCLONE_LOCAL_CONCURRENCY, None),
    ({'rcloneConcurrency': {'local': 'x', 'remote': 'x'}}, RCLONE_LOCAL_CONCURRENCY, None),
    # Local settings override the defaults one by one; blank ones keep them
    ({'rcloneConcurrency': {'local': {'transfers': 2, 'checkers': None}}},
     {'transfers': 2, 'checkers': 2, 'multiThreadStreams': 0}, None),
    # Remote has no defaults
    ({'rcloneConcurrency': {'remote': {}}}, RCLONE_LOCAL_CONCURRENCY, None),
    ({'rcloneConcurrency': {'remote': {'transfers': 8, 'checkers': ''}}},
     RCLONE_LOCAL_CONCURRENCY, {'transfers': 8}),
    # Unknown settings are ignored
    ({'rcloneConcurrency': {'remote': {'bogus': 1}}}, RCLONE_LOCAL_CONCURRENCY, None),
])
def test_rclone_concurrency(config, local, remote):
    """Local limits default to RCLONE_LOCAL_CONCURRENCY; remote ones to none."""
    assert rclone_concurrency(config, 'local') == local
    assert rclone_concurrency(config, 'remote') == remote


def test_shipped_yaml_matches_defaults():
    """The template's settings are the same as having no block at all."""
    template = Path(__file__).parents[1] / 'etc' / 'openvdm.yaml.dist'
    config = yaml.safe_load(template.read_text(encoding='utf-8'))
    for destination in ('local', 'remote'):
        assert rclone_concurrency(config, destination) == rclone_concurrency({}, destination)


@pytest.mark.parametrize('config, expected_limits', [
    ({}, []),
    ({'rcloneConcurrency': {'local': {'transfers': 1}}}, []),
    ({'rcloneConcurrency': {'remote': {'transfers': 2, 'checkers': 4, 'multiThreadStreams': 0}}},
     ['--transfers', '2', '--checkers', '4', '--multi-thread-streams', '0']),
])
def test_ship_to_shore_uses_remote_limits(
        monkeypatch: pytest.MonkeyPatch, config: dict, expected_limits: list) -> None:
    """Ship-to-shore rclone copies use only the remote limits."""
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
    limits = [part for i, part in enumerate(command)
              if part in CONCURRENCY_FLAGS or (i and command[i - 1] in CONCURRENCY_FLAGS)]
    assert limits == expected_limits
    assert '--files-from' in command
    assert '-v' in command
    assert file_count == 1
