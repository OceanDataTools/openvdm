"""Tests for the MD5 summary worker (#512 part 1).

``md5_summary.py`` rebuilds the cruise's MD5 summary from every file in the
cruise, or updates it for the files a job names, and writes the summary's own
MD5 file. The tests run its task handlers on a temporary cruise directory;
ownership changes are recorded. A bad payload is tested in
``test_bad_payload.py``.
"""

import hashlib
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import md5_summary

SUMMARY = 'md5_summary.txt'
SUMMARY_MD5 = 'md5_summary.md5'


def _job(task='updateMD5Summary', **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


def _md5(data):
    return hashlib.md5(data).hexdigest()


@pytest.fixture
def perms(monkeypatch):
    """Record ``set_owner_group_permissions()`` calls; set ``fail`` to a path suffix to fail them."""
    rec = SimpleNamespace(paths=[], fail=None)

    def owner(user, path):
        rec.paths.append(path)
        if rec.fail and path.endswith(rec.fail):
            return {'verdict': False, 'reason': f'chown {path} failed'}
        return {'verdict': True}

    monkeypatch.setattr(md5_summary, 'set_owner_group_permissions', owner)
    return rec


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = md5_summary.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: 'executed')
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def api(fake_ovdm):
    """The fake API: no MD5 file size limit; rebuildMD5Summary has task ID 7."""
    fake_ovdm.get_cruise_start_date.return_value = '2026/10/01 00:00'
    fake_ovdm.get_md5_filesize_limit.return_value = '10'
    fake_ovdm.get_md5_filesize_limit_status.return_value = 'Off'
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 7, 'name': name, 'longName': 'Rebuild MD5'}
    return fake_ovdm


@pytest.fixture
def cruise(warehouse):
    """The cruise directory, with three files in two collection systems."""
    files = {'SCS/raw/nav.txt': b'nav data\n', 'SCS/raw/met.txt': b'met data\n', 'EM124/a b.all': b'multibeam'}
    for name, data in files.items():
        path = warehouse.cruise_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return SimpleNamespace(dir=warehouse.cruise_dir, files=files, summary=warehouse.cruise_dir / SUMMARY,
                           summary_md5=warehouse.cruise_dir / SUMMARY_MD5)


@pytest.fixture
def worker(monkeypatch, api, gearman_base, perms, cruise):
    """An MD5 summary worker using the fake API, set up for the cruise."""
    monkeypatch.setattr(md5_summary, 'OpenVDM', lambda: api)
    w = md5_summary.OVDMGearmanWorker()
    w.send_job_status = Mock()
    w.send_job_data = Mock()
    w.shutdown = Mock()
    assert w.on_job_execute(_job()) == 'executed'
    return w


def _summary(cruise):
    """The summary as (hash, filename) pairs."""
    return [tuple(line.split(' ', 1)) for line in cruise.summary.read_text().splitlines()]


def _expected(cruise, files=None):
    return sorted(((_md5(data), name) for name, data in (files or cruise.files).items()), key=lambda row: row[1])


def _rebuild(worker):
    return md5_summary.task_rebuild_md5_summary(worker, _job('rebuildMD5Summary'))


def _update(worker, **files):
    return md5_summary.task_update_md5_summary(worker, _job(files=files))


# --- Job setup and completion ---------------------------------------------------

def test_job_setup(worker, api, warehouse) -> None:
    """The cruise and paths come from the current cruise; Update MD5 Summary (no task ID) is tracked
    as a Gearman job, not a task."""
    assert worker.cruise_id == warehouse.cruise_id
    assert worker.md5_summary_filepath == str(warehouse.cruise_dir / SUMMARY)
    assert worker.md5_summary_md5_filepath == str(warehouse.cruise_dir / SUMMARY_MD5)
    api.track_gearman_job.assert_called_once_with('Updating MD5 summary', os.getpid(), 'H:test:1')
    api.set_running_task.assert_not_called()


def test_job_setup_api_task(worker, api, warehouse) -> None:
    """Rebuild MD5 Summary is set running; the payload's cruise wins."""
    worker.on_job_execute(_job('rebuildMD5Summary', cruiseID='OTHER01'))
    api.set_running_task.assert_called_once_with(7, os.getpid(), 'H:test:1')
    assert worker.cruise_dir == str(warehouse.base_dir / 'OTHER01')


@pytest.mark.parametrize('task, result, call', [
    ('updateMD5Summary', 'Fail', ('send_msg', ('Updating MD5 summary failed', 'it broke'))),
    ('rebuildMD5Summary', 'Fail', ('set_error_task', (7, 'it broke'))),
    ('rebuildMD5Summary', 'Pass', ('set_idle_task', (7,))),
    ('updateMD5Summary', 'Pass', ('set_idle_task', (0,))),
])
def test_job_complete(worker, api, task, result, call) -> None:
    """A failed job sets the task's error (or posts a message, for a task without an ID); a
    passed one sets it idle."""
    worker.on_job_execute(_job(task))
    out = json.dumps({'parts': [{'partName': 'Step', 'result': result, 'reason': 'it broke'}]})
    assert worker.on_job_complete(_job(task), out) == out
    getattr(api, call[0]).assert_called_once_with(*call[1])


@pytest.mark.parametrize('task, call', [
    ('updateMD5Summary', 'send_msg'), ('rebuildMD5Summary', 'set_error_task')])
def test_job_exception(worker, api, task, call) -> None:
    """A crash is reported with where it happened."""
    worker.on_job_execute(_job(task))
    try:
        raise KeyError('files')
    except KeyError as err:
        info = (type(err), err, err.__traceback__)
    assert worker.on_job_exception(_job(task), info) == 'crashed'
    reason = getattr(api, call).call_args.args[-1]
    assert reason.startswith("Worker crashed: KeyError: 'files' (test_md5_summary_worker.py, line ")
    sent = json.loads(worker.send_job_data.call_args.args[1])
    assert sent[0]['partName'] == 'Worker crashed'


def test_stop_and_quit(worker) -> None:
    """Stop stops the current task; quit also shuts the worker down."""
    worker.stop_task()
    assert worker.stop
    worker.stop = False
    worker.quit_worker()
    assert worker.stop
    worker.shutdown.assert_called_once()


# --- Hashing ----------------------------------------------------------------------

def test_hash_file(cruise) -> None:
    """A file's MD5, read in chunks."""
    path = cruise.dir / 'big.bin'
    data = os.urandom(md5_summary.BUF_SIZE * 2 + 17)
    path.write_bytes(data)
    assert md5_summary.OVDMGearmanWorker.hash_file(str(path)) == _md5(data)


def test_hash_file_without_usedforsecurity(cruise, monkeypatch) -> None:
    """On a Python whose hashlib.md5 has no usedforsecurity argument, the plain one is used."""
    real = hashlib.md5

    def md5(*args, **kwargs):
        if kwargs:
            raise TypeError('unexpected keyword argument')
        return real(*args)
    monkeypatch.setattr(md5_summary.hashlib, 'md5', md5)
    assert md5_summary.OVDMGearmanWorker.hash_file(str(cruise.dir / 'SCS/raw/nav.txt')) == _md5(b'nav data\n')


def test_hash_file_missing(cruise) -> None:
    """A file that can't be read raises."""
    with pytest.raises(FileNotFoundError):
        md5_summary.OVDMGearmanWorker.hash_file(str(cruise.dir / 'missing.txt'))


@pytest.mark.parametrize('status, limit, starred', [('On', '1', True), ('On', '0', False), ('Off', '1', False)])
def test_filesize_limit(worker, api, cruise, status, limit, starred) -> None:
    """With the limit on (and not 0), files at or over it get a placeholder hash instead."""
    (cruise.dir / 'EM124' / 'big.all').write_bytes(b'x' * 1_000_000)
    api.get_md5_filesize_limit_status.return_value = status
    api.get_md5_filesize_limit.return_value = limit
    hashes = {entry['filename']: entry['hash'] for entry in worker.build_md5_hashes(
        _job(), ['EM124/big.all', 'SCS/raw/nav.txt'])}
    assert (hashes['EM124/big.all'] == '*' * 32) is starred
    assert hashes['SCS/raw/nav.txt'] == _md5(b'nav data\n')


def test_unhashable_file_skipped(worker, caplog) -> None:
    """A file that can't be hashed (e.g. gone) is logged and left out."""
    hashes = worker.build_md5_hashes(_job(), ['gone.txt', 'SCS/raw/nav.txt'])
    assert [entry['filename'] for entry in hashes] == ['SCS/raw/nav.txt']
    assert 'Could not generate md5 hash for file: gone.txt' in caplog.text


def test_hashing_reports_progress(worker) -> None:
    """Hashing reports progress from 20 to 80 %."""
    worker.build_md5_hashes(_job(), ['SCS/raw/nav.txt', 'SCS/raw/met.txt'])
    assert [call.args[1:] for call in worker.send_job_status.call_args_list] == [(20, 100), (50, 100)]


# --- Rebuild ----------------------------------------------------------------------

def test_rebuild(worker, cruise, perms) -> None:
    """Every file in the cruise is hashed, sorted by name (one with a space included); the summary
    files themselves aren't; the summary's MD5 file is its MD5."""
    cruise.summary.write_text('old summary\n')
    cruise.summary_md5.write_text('old md5')
    assert _parts(_rebuild(worker)) == [
        ('Verify Cruise Directory exists', 'Pass'), ('Retrieve Filelist', 'Pass'), ('Calculate Hashes', 'Pass'),
        ('Writing MD5 Summary file', 'Pass'), ('Set MD5 Summary file ownership/permissions', 'Pass'),
        ('Writing MD5 Summary MD5 file', 'Pass'), ('Set MD5 Summary MD5 file ownership/permissions', 'Pass')]
    assert _summary(cruise) == _expected(cruise)
    assert cruise.summary_md5.read_text() == _md5(cruise.summary.read_bytes())
    assert perms.paths == [str(cruise.summary), str(cruise.summary_md5)]


def test_rebuild_empty_cruise(worker, cruise) -> None:
    """A cruise without files gets an empty summary."""
    for name in cruise.files:
        (cruise.dir / name).unlink()
    assert _parts(_rebuild(worker))[-1] == ('Set MD5 Summary MD5 file ownership/permissions', 'Pass')
    assert cruise.summary.read_text() == ''


def test_rebuild_no_cruise_directory(worker, cruise) -> None:
    """Without the cruise directory, the rebuild fails."""
    worker.cruise_dir = str(cruise.dir / 'missing')
    result = json.loads(_rebuild(worker))
    assert result['parts'] == [{'partName': 'Verify Cruise Directory exists', 'result': 'Fail',
                                'reason': f"Unable to locate the cruise directory: {cruise.dir / 'missing'}"}]


def test_rebuild_stopped(worker, cruise, monkeypatch) -> None:
    """A rebuild stopped while hashing fails, and the summary isn't written."""
    real = worker.hash_file

    def hash_then_stop(path):
        worker.stop = True
        return real(path)
    monkeypatch.setattr(worker, 'hash_file', hash_then_stop)
    assert _parts(_rebuild(worker))[-1] == ('Calculate Hashes', 'Fail')
    assert not cruise.summary.exists()


def test_rebuild_cant_write_summary(worker, cruise) -> None:
    """If the summary can't be written, the rebuild fails."""
    cruise.summary.mkdir()
    result = json.loads(_rebuild(worker))
    assert result['parts'][-1] == {'partName': 'Writing MD5 Summary file', 'result': 'Fail',
                                   'reason': f'Error saving MD5 Summary file: {cruise.summary}'}


def test_rebuild_cant_write_summary_md5(worker, cruise) -> None:
    """If the summary's MD5 file can't be written, the rebuild fails."""
    cruise.summary_md5.mkdir()
    result = json.loads(_rebuild(worker))
    assert result['parts'][-1] == {'partName': 'Writing MD5 Summary MD5 file', 'result': 'Fail',
                                   'reason': f'Error saving MD5 Summary MD5 file: {cruise.summary_md5}'}


@pytest.mark.parametrize('fail, part', [(SUMMARY, 'Set MD5 Summary file ownership/permissions'),
                                        (SUMMARY_MD5, 'Set MD5 Summary MD5 file ownership/permissions')])
def test_rebuild_ownership_fails(worker, perms, fail, part) -> None:
    """If a summary file's ownership can't be set, the rebuild fails with the reason."""
    perms.fail = fail
    result = json.loads(_rebuild(worker))
    assert result['parts'][-1]['partName'] == part and result['parts'][-1]['result'] == 'Fail'
    assert result['parts'][-1]['reason'].endswith(f'{fail} failed')


# --- Update -----------------------------------------------------------------------

def test_update_nothing(worker, cruise) -> None:
    """A job without files has nothing to update."""
    assert json.loads(_update(worker))['parts'] == [
        {'partName': 'Update MD5 Summary', 'result': 'Ignore', 'reason': 'Nothing to update'}]
    assert not cruise.summary.exists()


def test_update_without_summary_rebuilds(worker, cruise) -> None:
    """Without a summary yet, the whole cruise's is built, not one of just the job's files (#348)."""
    parts = _parts(_update(worker, new=['SCS/raw/nav.txt']))
    assert parts[0] == ('Reading pre-existing MD5 Summary file', 'Pass')
    assert parts[1:] == _parts(json.dumps(json.loads(_rebuild(worker))))
    assert _summary(cruise) == _expected(cruise)


def test_update(worker, cruise, perms) -> None:
    """New files are added, updated ones get their new hash, deleted ones are removed; the others
    stay; the summary stays sorted and its MD5 file matches."""
    _rebuild(worker)
    perms.paths.clear()
    (cruise.dir / 'SCS/raw/nav.txt').write_bytes(b'nav data, more\n')
    (cruise.dir / 'SCS/raw/gga.txt').write_bytes(b'gga\n')
    (cruise.dir / 'SCS/raw/met.txt').unlink()
    result = _update(worker, new=['SCS/raw/gga.txt'], updated=['SCS/raw/nav.txt'], deleted=['SCS/raw/met.txt'])
    assert _parts(result) == [
        ('Calculate Hashes', 'Pass'), ('Reading pre-existing MD5 Summary file', 'Pass'),
        ('Writing MD5 Summary file', 'Pass'), ('Set MD5 Summary file ownership/permissions', 'Pass'),
        ('Writing MD5 Summary MD5 file', 'Pass'), ('Set MD5 Summary MD5 file ownership/permissions', 'Pass')]
    assert _summary(cruise) == _expected(cruise, {'EM124/a b.all': b'multibeam', 'SCS/raw/gga.txt': b'gga\n',
                                                  'SCS/raw/nav.txt': b'nav data, more\n'})
    assert cruise.summary_md5.read_text() == _md5(cruise.summary.read_bytes())
    assert perms.paths == [str(cruise.summary), str(cruise.summary_md5)]


def test_update_only_deleted(worker, cruise) -> None:
    """A job with only deleted files removes them."""
    _rebuild(worker)
    _update(worker, deleted=['EM124/a b.all', 'not/in/summary.txt'])
    assert [name for _, name in _summary(cruise)] == ['SCS/raw/met.txt', 'SCS/raw/nav.txt']


def test_update_ignores_blank_lines(worker, cruise) -> None:
    """Lines without a hash and a name in the existing summary are dropped."""
    cruise.summary.write_text(f"{_md5(b'met data')} SCS/raw/met.txt\n\nnonsense\n")
    _update(worker, new=['SCS/raw/nav.txt'])
    assert [name for _, name in _summary(cruise)] == ['SCS/raw/met.txt', 'SCS/raw/nav.txt']


def test_update_cant_read_summary(worker, cruise) -> None:
    """If the existing summary can't be read, the update fails."""
    cruise.summary.mkdir()
    result = json.loads(_update(worker, new=['SCS/raw/nav.txt']))
    assert result['parts'][-1] == {'partName': 'Reading pre-existing MD5 Summary file', 'result': 'Fail',
                                   'reason': f'Error reading pre-existing MD5 Summary file: {cruise.summary}'}


def test_update_cant_write_summary(worker, cruise, monkeypatch) -> None:
    """If the summary can't be written, the update fails."""
    _rebuild(worker)
    monkeypatch.setattr(worker, 'build_md5_summary', lambda hashes: {'verdict': False, 'reason': 'disk full'})
    result = json.loads(_update(worker, new=['SCS/raw/nav.txt']))
    assert result['parts'][-1] == {'partName': 'Writing MD5 Summary file', 'result': 'Fail', 'reason': 'disk full'}


def test_update_cant_write_summary_md5(worker, cruise) -> None:
    """If the summary's MD5 file can't be written, the update fails."""
    _rebuild(worker)
    cruise.summary_md5.unlink()
    cruise.summary_md5.mkdir()
    result = json.loads(_update(worker, new=['SCS/raw/nav.txt']))
    assert result['parts'][-1]['partName'] == 'Writing MD5 Summary MD5 file'
    assert result['parts'][-1]['result'] == 'Fail'


@pytest.mark.parametrize('fail, part', [(SUMMARY, 'Set MD5 Summary file ownership/permissions'),
                                        (SUMMARY_MD5, 'Set MD5 Summary MD5 file ownership/permissions')])
def test_update_ownership_fails(worker, perms, fail, part) -> None:
    """If a summary file's ownership can't be set, the update fails with the reason."""
    _rebuild(worker)
    perms.fail = fail
    result = json.loads(_update(worker, new=['SCS/raw/nav.txt']))
    assert result['parts'][-1]['partName'] == part and result['parts'][-1]['result'] == 'Fail'


def test_build_md5_summary_fails(worker, cruise) -> None:
    """build_md5_summary() returns the reason when the summary can't be written."""
    cruise.summary.mkdir()
    assert worker.build_md5_summary([]) == {'verdict': False,
                                            'reason': f'Error updating MD5 Summary file: {cruise.summary}'}


# --- Bugs -----------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="the update doesn't check Stop (#579)")
def test_update_stopped(worker, cruise, monkeypatch) -> None:
    """An update stopped while hashing fails, as a stopped rebuild does, and leaves the summary as it was."""
    _rebuild(worker)
    before = cruise.summary.read_text()
    real = worker.hash_file

    def hash_then_stop(path):
        worker.stop = True
        return real(path)
    monkeypatch.setattr(worker, 'hash_file', hash_then_stop)
    (cruise.dir / 'SCS/raw/nav.txt').write_bytes(b'changed\n')
    (cruise.dir / 'SCS/raw/met.txt').write_bytes(b'changed too\n')
    result = _update(worker, updated=['SCS/raw/nav.txt', 'SCS/raw/met.txt'])
    assert _parts(result)[-1] == ('Calculate Hashes', 'Fail')
    assert cruise.summary.read_text() == before
