"""Tests that Stop ends a collection system transfer while it lists its source."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from server.workers import run_collection_system_transfer as cst_run

FILTERS = {'ignore_filters': [], 'include_filters': ['*'], 'exclude_filters': []}


def _worker(source: Path, stop: bool = False):
    """A worker set up to list *source* as a local transfer, without __init__."""
    worker = object.__new__(cst_run.OVDMGearmanWorker)
    worker.stop = stop
    worker.source_dir = str(source)
    worker.cruise_id = 'C1'
    worker.lowering_id = None
    worker.data_start_date = '1970/01/01 00:00'
    worker.data_end_date = '9999/12/31 23:59:59'
    worker.collection_system_transfer = {
        'transferType': 1, 'includeFilter': '*', 'excludeFilter': '', 'ignoreFilter': '',
        'staleness': 0, 'skipEmptyFiles': 0, 'skipEmptyDirs': 0, 'syncFromSource': 0}
    return worker


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A source tree of three directories with two files each."""
    for name in ('a', 'b', 'c'):
        (tmp_path / name).mkdir()
        for i in range(2):
            (tmp_path / name / f'{i}.dat').write_text('x')
    return tmp_path


def test_process_batch_stops_before_the_next_file(source: Path) -> None:
    """A stopped batch doesn't stat the rest of its files."""
    batch = [str(p) for p in sorted(source.rglob('*.dat'))]
    assert len(cst_run.process_batch(batch, FILTERS, 0, 2 ** 40)) == 6
    assert cst_run.process_batch(batch, FILTERS, 0, 2 ** 40, lambda: True) == []


def test_listing_runs_normally(source: Path) -> None:
    """Without a stop the listing finds every file."""
    result = _worker(source).build_cst_filelist()
    assert result['verdict'] and not result.get('stopped')
    assert len(result['files']['include']) == 6


def test_listing_stopped_before_it_starts(source: Path) -> None:
    """A stopped job returns no files, so nothing is copied or deleted."""
    result = _worker(source, stop=True).build_cst_filelist()
    assert result['verdict'] and result['stopped']
    assert result['files']['include'] == []


def test_listing_stopped_during_the_walk(monkeypatch: pytest.MonkeyPatch, source: Path) -> None:
    """Stop takes effect at the next directory of the walk."""
    worker = _worker(source)
    real_walk = cst_run.os.walk
    seen = []

    def walk(*args, **kwargs):
        for entry in real_walk(*args, **kwargs):
            seen.append(entry[0])
            yield entry
            worker.stop = True

    monkeypatch.setattr(cst_run.os, 'walk', walk)
    result = worker.build_cst_filelist()

    assert result['stopped'] and result['files']['include'] == []
    assert len(seen) == 2  # the root, then the first subdirectory is where it stops


def test_task_stopped_while_listing_writes_no_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """The job passes with no files: no transfer or exclude log, no hooks."""
    monkeypatch.setattr(cst_run.time, 'sleep', Mock())
    monkeypatch.setattr(cst_run, 'test_cst_source', Mock(return_value=[{'result': 'Pass'}]))
    output = Mock()
    monkeypatch.setattr(cst_run, 'output_json_data_to_file', output)
    worker = Mock()
    worker.collection_system_transfer = {'collectionSystemTransferID': 5, 'name': 'X'}
    worker.test_destination_dir.return_value = [{'result': 'Pass'}]
    worker.transfer_from_source.return_value = {
        'verdict': True, 'stopped': True, 'files': {'new': [], 'updated': [], 'exclude': []}}

    results = json.loads(cst_run.task_run_collection_system_transfer(worker, Mock(handle='H:1')))

    assert results['parts'][-1] == {'partName': 'Transfer Files', 'result': 'Pass'}
    assert results['files'] == {'new': [], 'updated': [], 'exclude': []}
    output.assert_not_called()
