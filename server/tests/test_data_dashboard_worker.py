"""Tests for the data dashboard worker (#512 part 2).

``data_dashboard.py`` runs a collection system transfer's plugin on its new
and updated files (or, for a rebuild, on every file of every transfer),
writes each file's dashboard JSON and keeps the dashboard manifest. The tests
write small plugins to a temporary plugin directory; hook jobs go to the
``fake_gearman`` client and ownership changes are recorded. A bad payload is
tested in ``test_bad_payload.py``.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server.workers import data_dashboard

DASHBOARD = 'OpenVDM/DashboardData'

# A plugin that returns one data type per file, named after its extension, and
# fails or returns nothing for files named so
PLUGIN = '''
import json, os

def process_file(path):
    name = os.path.basename(path)
    if name.startswith('fail'):
        raise ValueError('cannot parse ' + name)
    if name.startswith('nothing'):
        return {}
    if name.startswith('error'):
        return {'error': 'plugin error for ' + name}
    if name.startswith('two'):
        return {'gga': {'stats': [1]}, 'hdt': {'stats': [2]}}
    return {os.path.splitext(name)[1].lstrip('.'): {'stats': [open(path).read()]}}
'''

CSTS = [{'collectionSystemTransferID': 3, 'name': 'SCS', 'destDir': 'SCS', 'cruiseOrLowering': 0},
        {'collectionSystemTransferID': 5, 'name': 'ROV', 'destDir': 'ROV', 'cruiseOrLowering': 1}]


def _job(task='updateDataDashboard', **payload):
    """A Gearman job with the given payload."""
    return SimpleNamespace(data=json.dumps(payload), handle='H:test:1', task=task)


def _parts(result):
    """Each part of a result as (partName, result)."""
    return [(part['partName'], part['result']) for part in json.loads(result)['parts']]


@pytest.fixture
def perms(monkeypatch):
    """Record ``set_owner_group_permissions()`` calls; set ``fail`` to fail them."""
    rec = SimpleNamespace(paths=[], fail=False)

    def owner(user, path):
        rec.paths.append(path)
        return {'verdict': False, 'reason': f'chown {path} failed'} if rec.fail else {'verdict': True}

    monkeypatch.setattr(data_dashboard, 'set_owner_group_permissions', owner)
    return rec


@pytest.fixture
def gearman_base(monkeypatch):
    """GearmanWorker's own job handling: run nothing, and pass results through."""
    base = data_dashboard.python3_gearman.GearmanWorker
    monkeypatch.setattr(base, 'on_job_execute', lambda self, job: 'executed')
    monkeypatch.setattr(base, 'send_job_complete', lambda self, job, result: result)
    monkeypatch.setattr(base, 'on_job_exception', lambda self, job, info: 'crashed')
    return base


@pytest.fixture
def plugins(tmp_path):
    """The plugin directory, with the SCS and ROV plugins (``scs_plugin.py``, ``rov_plugin.py``)."""
    plugin_dir = tmp_path / 'plugins'
    plugin_dir.mkdir()
    for name in ('scs', 'rov'):
        (plugin_dir / f'{name}_plugin.py').write_text(PLUGIN)
    return plugin_dir


@pytest.fixture
def api(fake_ovdm, plugins):
    """The fake API: the SCS (cruise) and ROV (lowering) transfers; rebuildDataDashboard has task ID 8."""
    fake_ovdm.get_plugin_dir.side_effect = None
    fake_ovdm.get_plugin_dir.return_value = str(plugins)
    fake_ovdm.get_plugin_suffix.side_effect = None
    fake_ovdm.get_plugin_suffix.return_value = '_plugin.py'
    fake_ovdm.get_lowering_id.return_value = None
    fake_ovdm.get_collection_system_transfer.side_effect = \
        lambda cst_id: next((cst for cst in CSTS if cst['collectionSystemTransferID'] == int(cst_id)), None)
    fake_ovdm.get_active_collection_system_transfers.return_value = CSTS
    fake_ovdm.get_lowerings.return_value = ['DIVE01', 'DIVE02']
    fake_ovdm.get_required_extra_directory_by_name.return_value = {'name': 'Dashboard_Data', 'destDir': DASHBOARD}
    fake_ovdm.get_task_by_name.side_effect = lambda name: {'taskID': 8, 'name': name, 'longName': 'Rebuild Dashboard'}
    return fake_ovdm


@pytest.fixture
def cruise(warehouse):
    """The cruise: SCS files, ROV files in two lowerings, and the dashboard directory."""
    files = {'SCS/raw/nav.gga': 'nav', 'SCS/raw/heading.hdt': 'hdg',
             'Vehicle/DIVE01/ROV/ctd.ctd': 'ctd1', 'Vehicle/DIVE02/ROV/ctd.ctd': 'ctd2'}
    for name, data in files.items():
        path = warehouse.cruise_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    dashboard = warehouse.cruise_dir / DASHBOARD
    dashboard.mkdir(parents=True)
    return SimpleNamespace(dir=warehouse.cruise_dir, dashboard=dashboard, manifest=dashboard / 'manifest.json',
                           base=warehouse.base_dir, id=warehouse.cruise_id)


@pytest.fixture
def worker(monkeypatch, api, gearman_base, perms, fake_gearman, cruise):
    """A data dashboard worker using the fake API, set up for an SCS update."""
    monkeypatch.setattr(data_dashboard, 'OpenVDM', lambda: api)
    w = data_dashboard.OVDMGearmanWorker()
    w.send_job_status = Mock()
    w.send_job_data = Mock()
    w.shutdown = Mock()
    assert w.on_job_execute(_job(collectionSystemTransferID=3, files={'new': []})) == 'executed'
    return w


def _update(worker, new=(), updated=()):
    return data_dashboard.task_update_data_dashboard(
        worker, _job(collectionSystemTransferID=3, files={'new': list(new), 'updated': list(updated)}))


def _rebuild(worker):
    worker.on_job_execute(_job('rebuildDataDashboard'))
    return data_dashboard.task_rebuild_data_dashboard(worker, _job('rebuildDataDashboard'))


def _manifest(cruise):
    return json.loads(cruise.manifest.read_text())


def _entry(cruise, dd_type, raw):
    """A manifest entry for raw file *raw* (relative to the cruise)."""
    return {'type': dd_type, 'dd_json': f'{cruise.id}/{DASHBOARD}/{os.path.splitext(raw)[0]}.json',
            'raw_data': f'{cruise.id}/{raw}'}


# --- Job setup and completion ---------------------------------------------------

def test_job_setup(worker, api, cruise) -> None:
    """An update is tracked as a Gearman job, for its transfer; the dashboard paths are the cruise's."""
    assert worker.collection_system_transfer == CSTS[0]
    assert worker.data_dashboard_dir == str(cruise.dashboard)
    assert worker.data_dashboard_manifest_file_path == str(cruise.manifest)
    assert worker.lowering_dir is None
    api.track_gearman_job.assert_called_once_with('Updating data dashboard', os.getpid(), 'H:test:1')


def test_job_setup_lowering_and_rebuild(worker, api, cruise) -> None:
    """A rebuild is set running; a payload's lowering sets the lowering directory."""
    worker.on_job_execute(_job('rebuildDataDashboard', loweringID='DIVE01'))
    api.set_running_task.assert_called_once_with(8, os.getpid(), 'H:test:1')
    assert worker.lowering_dir == str(cruise.dir / 'Vehicle' / 'DIVE01')
    assert worker.collection_system_transfer is None


def test_update_without_transfer(worker, api) -> None:
    """An update for a transfer OpenVDM doesn't know fails."""
    result = worker.on_job_execute(_job(collectionSystemTransferID=99, files={'new': []}))
    assert _parts(result) == [('Retrieve Collection System Transfer Data', 'Fail')]
    api.send_msg.assert_called_once_with('Updating data dashboard failed', 'Could not find configuration data')


def test_update_hooks(worker, fake_gearman) -> None:
    """After an update, its hook tasks get the job's cruise, transfer and files."""
    result = json.dumps({'parts': [], 'files': {'new': ['a.json'], 'updated': []}})
    worker.on_job_complete(_job(collectionSystemTransferID=3, files={'new': []}), result)
    assert fake_gearman.jobs == [(task, {'cruiseID': 'TEST001', 'loweringID': None, 'collectionSystemTransferID': 3,
                                         'files': {'new': ['a.json'], 'updated': []}})
                                 for task in ('updateMD5Summary', 'postDataDashboard')]


def test_rebuild_hooks(worker, fake_gearman, api) -> None:
    """After a rebuild, the update hook tasks run once per active transfer; the task goes idle."""
    worker.on_job_execute(_job('rebuildDataDashboard'))
    worker.on_job_complete(_job('rebuildDataDashboard'), json.dumps({'parts': [], 'files': {}}))
    assert [(task, data['collectionSystemTransferID']) for task, data in fake_gearman.jobs] == [
        ('updateMD5Summary', 3), ('postDataDashboard', 3), ('updateMD5Summary', 5), ('postDataDashboard', 5)]
    api.set_idle_task.assert_called_once_with(8)


@pytest.mark.parametrize('task, call', [('updateDataDashboard', 'send_msg'), ('rebuildDataDashboard', 'set_error_task')])
def test_job_complete_failed(worker, api, task, call) -> None:
    """A failed job sets the task's error, or posts a message for a task without an ID."""
    worker.on_job_execute(_job(task, collectionSystemTransferID=3, files={'new': []}))
    worker.on_job_complete(_job(task, collectionSystemTransferID=3, files={'new': []}),
                           json.dumps({'parts': [{'partName': 'Step', 'result': 'Fail', 'reason': 'it broke'}]}))
    assert getattr(api, call).call_args.args[-1] == 'it broke'


def test_job_complete_unreadable_result(worker, api, caplog) -> None:
    """A result that isn't JSON is logged; the job still completes."""
    assert worker.on_job_complete(_job(collectionSystemTransferID=3, files={}), 'not json') == 'not json'
    assert 'Failed to parse job results' in caplog.text


@pytest.mark.parametrize('task, call', [('updateDataDashboard', 'send_msg'), ('rebuildDataDashboard', 'set_error_task')])
def test_job_exception(worker, api, task, call) -> None:
    """A crash is reported with where it happened."""
    worker.on_job_execute(_job(task, collectionSystemTransferID=3, files={'new': []}))
    try:
        raise KeyError('files')
    except KeyError as err:
        info = (type(err), err, err.__traceback__)
    assert worker.on_job_exception(_job(task), info) == 'crashed'
    assert getattr(api, call).call_args.args[-1].startswith("Worker crashed: KeyError: 'files' (test_data_dashboard")


def test_stop_and_quit(worker) -> None:
    """Stop stops the current task; quit also shuts the worker down."""
    worker.stop_task()
    assert worker.stop
    worker.quit_worker()
    worker.shutdown.assert_called_once()


# --- Plugins ----------------------------------------------------------------------

def test_no_plugin(worker, plugins) -> None:
    """A transfer without a plugin is ignored."""
    (plugins / 'scs_plugin.py').unlink()
    assert json.loads(_update(worker, new=['SCS/raw/nav.gga']))['parts'] == [
        {'partName': 'Verify plugin', 'result': 'Ignore', 'reason': 'Plugin not found for SCS'}]


def test_plugin_without_process_file(worker, plugins, caplog) -> None:
    """A plugin without process_file() is logged, and ignored like a missing one."""
    (plugins / 'scs_plugin.py').write_text('x = 1\n')
    assert _parts(_update(worker, new=['SCS/raw/nav.gga'])) == [('Verify plugin', 'Ignore')]
    assert "does not have a 'process_file(raw_path)' function" in caplog.text


def test_plugin_wont_load(worker, plugins) -> None:
    """A plugin that won't import fails the update, with the reason."""
    (plugins / 'scs_plugin.py').write_text('import no_such_parser\n')
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    assert result['parts'] == [{'partName': 'Load plugin', 'result': 'Fail', 'reason':
                                "Unable to load plugin scs_plugin.py: ModuleNotFoundError: No module named "
                                "'no_such_parser'"}]


def test_source_files(worker, plugins, cruise) -> None:
    """A plugin's get_source_files() maps a file to the raw files to process; a mapping that fails
    keeps the file, and one outside the cruise is skipped (#288)."""
    (plugins / 'scs_plugin.py').write_text(PLUGIN + '''
def get_source_files(path):
    if path.endswith('.cal'):
        return [path[:-4] + '.gga']
    if path.endswith('.bad'):
        raise OSError('broken')
    if path.endswith('.out'):
        return ['/etc/passwd']
    return [path]
''')
    (cruise.dir / 'SCS/raw/nav.cal').write_text('cal')
    (cruise.dir / 'SCS/raw/x.bad').write_text('bad')
    (cruise.dir / 'SCS/raw/y.out').write_text('out')
    json.loads(_update(worker, new=['SCS/raw/nav.cal', 'SCS/raw/nav.gga', 'SCS/raw/x.bad', 'SCS/raw/y.out']))
    assert sorted(entry['raw_data'] for entry in _manifest(cruise)) == ['TEST001/SCS/raw/nav.gga',
                                                                        'TEST001/SCS/raw/x.bad']


# --- Update -----------------------------------------------------------------------

def test_update(worker, cruise, perms) -> None:
    """Each file's plugin output is written beside the others under Dashboard_Data, the manifest gets
    an entry per data type, and the dashboard's ownership is set."""
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga'], updated=['SCS/raw/heading.hdt']))
    assert _parts(json.dumps(result)) == [
        ('Verify plugin', 'Pass'), ('Retrieve file list', 'Pass'), ('Write dashboard file: SCS/raw/nav.gga', 'Pass'),
        ('Write dashboard file: SCS/raw/heading.hdt', 'Pass'), ('Writing dashboard manifest file', 'Pass'),
        ('Set file/directory ownership', 'Pass')]
    assert json.loads((cruise.dashboard / 'SCS/raw/nav.json').read_text()) == {'gga': {'stats': ['nav']}}
    assert _manifest(cruise) == [_entry(cruise, 'gga', 'SCS/raw/nav.gga'), _entry(cruise, 'hdt', 'SCS/raw/heading.hdt')]
    assert result['files'] == {'new': [f'TEST001/{DASHBOARD}/SCS/raw/nav.json',
                                       f'TEST001/{DASHBOARD}/SCS/raw/heading.json'], 'updated': [], 'deleted': []}
    assert perms.paths == [str(cruise.dashboard)]


def test_update_again(worker, cruise) -> None:
    """Updating a file again rewrites its dashboard file; its manifest entry is reported updated."""
    _update(worker, new=['SCS/raw/nav.gga'])
    (cruise.dir / 'SCS/raw/nav.gga').write_text('nav, more')
    result = json.loads(_update(worker, updated=['SCS/raw/nav.gga']))
    assert result['files']['updated'] == [f'TEST001/{DASHBOARD}/SCS/raw/nav.json']
    assert json.loads((cruise.dashboard / 'SCS/raw/nav.json').read_text()) == {'gga': {'stats': ['nav, more']}}
    assert len(_manifest(cruise)) == 1


def test_update_two_data_types(worker, cruise) -> None:
    """A file with two data types gets a manifest entry for each."""
    (cruise.dir / 'SCS/raw/two.txt').write_text('both')
    _update(worker, new=['SCS/raw/two.txt'])
    assert _manifest(cruise) == [_entry(cruise, 'gga', 'SCS/raw/two.txt'), _entry(cruise, 'hdt', 'SCS/raw/two.txt')]


def test_update_no_files(worker) -> None:
    """A job without new or updated files is ignored."""
    assert _parts(_update(worker)) == [('Verify plugin', 'Pass'), ('Retrieve file list', 'Ignore')]


def test_update_missing_and_empty_files(worker, cruise, caplog) -> None:
    """A file that isn't there fails its part; an empty file is skipped."""
    (cruise.dir / 'SCS/raw/empty.gga').write_text('')
    parts = _parts(_update(worker, new=['SCS/raw/gone.gga', 'SCS/raw/empty.gga']))
    assert ('Verify data file exists: SCS/raw/gone.gga', 'Fail') in parts
    assert 'Skipping empty file: SCS/raw/empty.gga' in caplog.text


def test_update_plugin_fails_removes_entry(worker, cruise) -> None:
    """A file the plugin now fails on loses its dashboard file and manifest entries."""
    (cruise.dir / 'SCS/raw/two.txt').write_text('both')
    _update(worker, new=['SCS/raw/two.txt', 'SCS/raw/nav.gga'])
    (cruise.dir / 'SCS/raw/two.txt').rename(cruise.dir / 'SCS/raw/fail.txt')
    (cruise.dashboard / 'SCS/raw/two.json').rename(cruise.dashboard / 'SCS/raw/fail.json')
    manifest = [dict(entry, raw_data=entry['raw_data'].replace('two', 'fail'),
                     dd_json=entry['dd_json'].replace('two', 'fail')) for entry in _manifest(cruise)]
    cruise.manifest.write_text(json.dumps(manifest))
    result = json.loads(_update(worker, updated=['SCS/raw/fail.txt']))
    assert {'partName': 'Processing file: SCS/raw/fail.txt', 'result': 'Fail',
            'reason': 'cannot parse fail.txt'} in result['parts']
    assert _manifest(cruise) == [_entry(cruise, 'gga', 'SCS/raw/nav.gga')]
    assert not (cruise.dashboard / 'SCS/raw/fail.json').exists()


@pytest.mark.parametrize('name, logged', [('nothing.gga', 'No output from plugin for file: SCS/raw/nothing.gga'),
                                          ('error.gga', 'plugin error for error.gga')])
def test_update_no_output(worker, cruise, caplog, name, logged) -> None:
    """A file the plugin returns nothing (or an error) for gets no dashboard file or manifest entry."""
    (cruise.dir / 'SCS/raw' / name).write_text('x')
    _update(worker, new=[f'SCS/raw/{name}'])
    assert _manifest(cruise) == []
    assert logged in caplog.text


def test_update_cant_write_dashboard_file(worker, cruise) -> None:
    """A dashboard file that can't be written fails its part, and gets no manifest entry."""
    (cruise.dashboard / 'SCS').write_text('a file where the folder should be')
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    assert ('Write dashboard file: SCS/raw/nav.gga', 'Fail') in _parts(json.dumps(result))
    assert _manifest(cruise) == []


def test_update_cant_write_manifest(worker, cruise, monkeypatch) -> None:
    """A manifest that can't be written fails the update."""
    write = data_dashboard.output_json_data_to_file
    monkeypatch.setattr(data_dashboard, 'output_json_data_to_file', lambda path, data: (
        {'verdict': False, 'reason': 'disk full'} if path == str(cruise.manifest) else write(path, data)))
    assert _parts(_update(worker, new=['SCS/raw/nav.gga']))[-1] == ('Writing dashboard manifest file', 'Fail')


def test_update_ownership_fails(worker, perms) -> None:
    """If the dashboard's ownership can't be set, the update fails with the reason."""
    perms.fail = True
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    assert result['parts'][-1]['result'] == 'Fail' and result['parts'][-1]['reason'].endswith('failed')


def test_update_stopped(worker) -> None:
    """A stopped update processes no more files."""
    worker.stop = True
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    assert not any(part['partName'].startswith('Write dashboard file') for part in result['parts'])


# --- Rebuild ----------------------------------------------------------------------

def test_rebuild(worker, cruise, perms) -> None:
    """Every file of every active transfer is processed, the ROV's in each lowering; the manifest is
    rewritten, and dashboard files it no longer lists are deleted, with emptied folders."""
    old = cruise.dashboard / 'Old' / 'gone.json'
    old.parent.mkdir()
    old.write_text('{}')
    (cruise.dashboard / 'keep.png').write_text('not a dashboard file')
    cruise.manifest.write_text(json.dumps([{'type': 'x', 'dd_json': 'stale', 'raw_data': 'stale'}]))
    result = _rebuild(worker)
    assert _parts(result)[-3:] == [('Updating manifest file', 'Pass'), ('Remove old dashboard files', 'Pass'),
                                   ('Set file/directory ownership', 'Pass')]
    assert sorted(entry['raw_data'] for entry in _manifest(cruise)) == [
        'TEST001/SCS/raw/heading.hdt', 'TEST001/SCS/raw/nav.gga', 'TEST001/Vehicle/DIVE01/ROV/ctd.ctd',
        'TEST001/Vehicle/DIVE02/ROV/ctd.ctd']
    assert not old.parent.exists()
    assert (cruise.dashboard / 'keep.png').exists()


@pytest.mark.parametrize('cst, dirs', [(0, ['']), (1, ['Vehicle/DIVE01/', 'Vehicle/DIVE02/'])])
def test_rebuild_dest_dir_root(worker, cruise, monkeypatch, cst, dirs) -> None:
    """A destination directory of "/" is the cruise (or each lowering's) directory, not the
    filesystem root (#629)."""
    monkeypatch.setitem(CSTS[cst], 'destDir', '/')
    listed = []
    real = data_dashboard.build_filelist

    def build_filelist(path, *args, **kwargs):
        listed.append(path)
        return real(path, *args, **kwargs)
    monkeypatch.setattr(data_dashboard, 'build_filelist', build_filelist)
    _rebuild(worker)
    assert '/' not in listed
    assert all(os.path.join(cruise.dir, d) in listed for d in dirs)
    raw = [entry['raw_data'] for entry in _manifest(cruise)]
    assert {'TEST001/SCS/raw/nav.gga', 'TEST001/Vehicle/DIVE01/ROV/ctd.ctd'} <= set(raw)
    assert all('//' not in path for path in raw)


@pytest.mark.parametrize('cst, dest_dir, raw', [
    (0, '{cruiseID}_SCS', ['TEST001_SCS/nav.gga']),
    (0, '{loweringDataBaseDir}/{loweringID}/SCS', ['Vehicle/DIVE01/SCS/nav.gga', 'Vehicle/DIVE02/SCS/nav.gga']),
    (1, '{cruiseID}_ROV/', ['Vehicle/DIVE01/TEST001_ROV/nav.gga', 'Vehicle/DIVE02/TEST001_ROV/nav.gga']),
])
def test_rebuild_dest_dir_placeholders(worker, cruise, monkeypatch, cst, dest_dir, raw) -> None:
    """Placeholders in a destination directory are filled in, as the transfer does: a cruise
    transfer with {loweringID} is rebuilt from each lowering (#635)."""
    monkeypatch.setitem(CSTS[cst], 'destDir', dest_dir)
    for name in raw:
        (cruise.dir / name).parent.mkdir(parents=True, exist_ok=True)
        (cruise.dir / name).write_text('nav')
    _rebuild(worker)
    rebuilt = {entry['raw_data'] for entry in _manifest(cruise)}
    assert {f'{cruise.id}/{name}' for name in raw} <= rebuilt
    assert not any('{' in path for path in rebuilt)


def test_dashboard_dir_placeholders(worker, api, cruise) -> None:
    """The Dashboard_Data directory's placeholders are filled in (#635)."""
    api.get_required_extra_directory_by_name.return_value = {'name': 'Dashboard_Data', 'destDir': '/{cruiseID}_Dashboard/'}
    worker.on_job_execute(_job('rebuildDataDashboard'))
    assert worker.data_dashboard_dir == str(cruise.dir / f'{cruise.id}_Dashboard')


def test_rebuild_no_dashboard_directory(worker, cruise) -> None:
    """Without the dashboard directory, the rebuild fails."""
    cruise.dashboard.rmdir()
    assert _parts(_rebuild(worker)) == [('Verify Data dashboard directory exists', 'Fail')]


def test_rebuild_skips_transfer_without_plugin(worker, plugins, cruise, caplog) -> None:
    """A transfer without a plugin is skipped."""
    (plugins / 'rov_plugin.py').unlink()
    _rebuild(worker)
    assert 'No plugin for ROV, skipping' in caplog.text
    assert all('ROV' not in entry['raw_data'] for entry in _manifest(cruise))


def test_rebuild_plugin_wont_load(worker, plugins, cruise) -> None:
    """A plugin that won't load fails its transfer, and the rebuild ends failed; the rest are rebuilt."""
    (plugins / 'rov_plugin.py').write_text('import no_such_parser\n')
    result = json.loads(_rebuild(worker))
    assert result['parts'][-1]['partName'] == 'Load plugins' and result['parts'][-1]['result'] == 'Fail'
    assert 'rov_plugin.py' in result['parts'][-1]['reason']
    assert len(_manifest(cruise)) == 2


def test_rebuild_stopped_keeps_old_files(worker, cruise) -> None:
    """A stopped rebuild doesn't delete dashboard files: its manifest is only partial (#318)."""
    old = cruise.dashboard / 'gone.json'
    old.write_text('{}')
    worker.on_job_execute(_job('rebuildDataDashboard'))
    worker.stop = True
    result = data_dashboard.task_rebuild_data_dashboard(worker, _job('rebuildDataDashboard'))
    assert 'Remove old dashboard files' not in [name for name, _ in _parts(result)]
    assert old.exists()


def test_rebuild_cant_remove_old_file(worker, cruise, monkeypatch) -> None:
    """An old dashboard file that can't be deleted fails that part, naming it."""
    (cruise.dashboard / 'gone.json').write_text('{}')
    real = os.remove

    def remove(path):
        if path.endswith('gone.json'):
            raise PermissionError(13, 'Permission denied')
        real(path)
    monkeypatch.setattr(data_dashboard.os, 'remove', remove)
    result = json.loads(_rebuild(worker))
    part = next(part for part in result['parts'] if part['partName'] == 'Remove old dashboard files')
    assert part == {'partName': 'Remove old dashboard files', 'result': 'Fail',
                    'reason': f"{cruise.dashboard / 'gone.json'}: Permission denied"}


def test_rebuild_cant_write_manifest(worker, cruise) -> None:
    """A manifest that can't be written fails the rebuild."""
    cruise.manifest.mkdir()
    assert _parts(_rebuild(worker))[-1] == ('Updating manifest file', 'Fail')


def test_rebuild_ownership_fails(worker, perms, plugins) -> None:
    """If ownership fails, that's the rebuild's last (failed) part, even with plugin failures."""
    perms.fail = True
    (plugins / 'rov_plugin.py').write_text('import no_such_parser\n')
    assert _parts(_rebuild(worker))[-1] == ('Set file/directory ownership', 'Fail')


def test_plugin_returns_none(worker, plugins, cruise, caplog) -> None:
    """A plugin that returns None for a file is treated as no output, not a crash (#581)."""
    (plugins / 'scs_plugin.py').write_text('def process_file(path):\n    return None\n')
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    assert _parts(json.dumps(result))[-1] == ('Set file/directory ownership', 'Pass')
    assert 'No output from plugin for file: SCS/raw/nav.gga' in caplog.text


@pytest.mark.parametrize('content', [None, '[{"raw_data": ', '{"raw_data": "x"}'])
def test_update_with_unreadable_manifest(worker, cruise, content) -> None:
    """An update fails, leaving the manifest, if the manifest can't be read (cut short, not a list
    or not a file), and suggests a rebuild (#582)."""
    if content is None:
        cruise.manifest.mkdir()
    else:
        cruise.manifest.write_text(content)
    result = json.loads(_update(worker, new=['SCS/raw/nav.gga']))
    part = result['parts'][-1]
    assert (part['partName'], part['result']) == ('Read dashboard manifest file', 'Fail')
    assert part['reason'].endswith('Run Rebuild Data Dashboard to rebuild it')
    if content is not None:
        assert cruise.manifest.read_text() == content


def test_update_drops_old_data_types(worker, cruise) -> None:
    """A file reprocessed with fewer data types loses the manifest entries for the others (#583)."""
    (cruise.dir / 'SCS/raw/two.txt').write_text('both')
    _update(worker, new=['SCS/raw/two.txt'])
    (cruise.dir / 'SCS/raw/two.txt').rename(cruise.dir / 'SCS/raw/one.gga')
    manifest = [dict(entry, raw_data=entry['raw_data'].replace('two.txt', 'one.gga'),
                     dd_json=entry['dd_json'].replace('two', 'one')) for entry in _manifest(cruise)]
    cruise.manifest.write_text(json.dumps(manifest))
    _update(worker, new=['SCS/raw/heading.hdt'])
    _update(worker, updated=['SCS/raw/one.gga'])
    # other files' entries are left alone
    assert sorted((entry['raw_data'].rsplit('/', 1)[-1], entry['type']) for entry in _manifest(cruise)) == [
        ('heading.hdt', 'hdt'), ('one.gga', 'gga')]


def test_rebuild_progress_within_100(worker) -> None:
    """A rebuild's progress stays within 100% and never goes back (#584)."""
    _rebuild(worker)
    progress = [100 * call.args[1] / call.args[2] for call in worker.send_job_status.call_args_list]
    assert all(value <= 100 for value in progress)
    assert progress == sorted(progress)
