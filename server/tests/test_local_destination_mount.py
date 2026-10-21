"""Tests for the mount checks on local cruise data transfer destinations."""

import pytest

from server.lib import connection_utils


@pytest.mark.parametrize('dest_dir, expected', [
    ('/mnt/backup', True),
    ('/mnt/backup/cruises/', True),
    ('/media/survey/USB', True),
    ('/net/nas/cruises', True),
    ('/mnt', False),
    ('/mnt/', False),
    ('/mntdata/backup', False),
    ('/data/backup', False),
])
def test_under_mount_parent_dir(dest_dir, expected):
    """Only directories inside /mnt, /media and /net count."""
    assert connection_utils.under_mount_parent_dir(dest_dir) is expected


def _parts(results):
    return {part['partName']: part['result'] for part in results}


@pytest.fixture
def mount_parent(monkeypatch, tmp_path):
    """Make tmp_path a mount parent directory and return a destination in it."""
    monkeypatch.setattr(connection_utils, 'MOUNT_PARENT_DIRS', (str(tmp_path),))
    dest_dir = tmp_path / 'backup'
    dest_dir.mkdir()
    return str(dest_dir)


def test_unmounted_destination_fails(monkeypatch, mount_parent):
    """A destination in a mount parent directory on the root filesystem fails."""
    monkeypatch.setattr(connection_utils, '_on_root_filesystem', lambda path: True)

    results = connection_utils.test_local_destination(mount_parent, 0)

    assert _parts(results) == {'Destination directory': 'Pass',
                               'Destination directory is mounted': 'Fail',
                               'Write test': 'Fail'}
    assert 'root filesystem' in results[1]['reason']


def test_mounted_destination_passes(monkeypatch, mount_parent):
    """A destination in a mount parent directory on another filesystem passes."""
    monkeypatch.setattr(connection_utils, '_on_root_filesystem', lambda path: False)

    results = connection_utils.test_local_destination(mount_parent, 0)

    assert _parts(results) == {'Destination directory': 'Pass',
                               'Destination directory is mounted': 'Pass',
                               'Write test': 'Pass'}


def test_missing_destination_in_mount_parent(monkeypatch, tmp_path):
    """A missing destination in a mount parent directory fails every part."""
    monkeypatch.setattr(connection_utils, 'MOUNT_PARENT_DIRS', (str(tmp_path),))

    results = connection_utils.test_local_destination(str(tmp_path / 'missing'), 0)

    assert _parts(results) == {'Destination directory': 'Fail',
                               'Destination directory is mounted': 'Fail',
                               'Write test': 'Fail'}


def test_destination_elsewhere_isnt_checked(monkeypatch, tmp_path):
    """A destination outside the mount parent directories isn't checked."""
    monkeypatch.setattr(connection_utils, 'MOUNT_PARENT_DIRS', ('/no/such/parent',))
    monkeypatch.setattr(connection_utils, '_on_root_filesystem', lambda path: True)

    results = connection_utils.test_local_destination(str(tmp_path), 0)

    assert _parts(results) == {'Destination directory': 'Pass', 'Write test': 'Pass'}


def test_marked_mount_point_uses_its_own_check(monkeypatch, mount_parent):
    """A destination marked as a mount point keeps the existing check."""
    monkeypatch.setattr(connection_utils, '_on_root_filesystem', lambda path: True)
    monkeypatch.setattr(connection_utils.os.path, 'ismount', lambda path: True)

    results = connection_utils.test_local_destination(mount_parent, 1)

    assert _parts(results) == {'Destination directory': 'Pass',
                               'Destination directory is a mount point': 'Pass',
                               'Write test': 'Pass'}
