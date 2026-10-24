"""Tests for server/lib/placeholders.py (#635)."""

from server.lib.placeholders import fill_placeholders


def test_fills_every_placeholder() -> None:
    """Each placeholder is filled in, as often as it appears; slashes are kept."""
    assert fill_placeholders('/{loweringDataBaseDir}/{loweringID}/{cruiseID}_{loweringID}/', 'TEST001', 'Vehicle',
                             'DIVE01') == '/Vehicle/DIVE01/TEST001_DIVE01/'


def test_lowering_id_left_without_one() -> None:
    """Without a lowering ID, {loweringID} is left for the caller."""
    assert fill_placeholders('{loweringDataBaseDir}/{loweringID}/SCS', 'TEST001', 'Vehicle') == 'Vehicle/{loweringID}/SCS'


def test_no_path() -> None:
    """A missing destination directory is empty."""
    assert fill_placeholders(None, 'TEST001', 'Vehicle') == ''
