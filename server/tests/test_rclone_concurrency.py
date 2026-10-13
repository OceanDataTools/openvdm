"""Tests for cruise-data rclone limits from the server configuration."""

import pytest
import yaml
from pathlib import Path

from server.lib.connection_utils import build_rclone_options


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
