"""Tests for readme.py, transfer_utils.py and file_utils.py (#507).

The README builder (#431, #445, #447), running rsync and rclone transfers
(#230, #237, #239), and the file helpers the workers share. Transfers run
small stand-in ``rsync``/``rclone`` scripts, so the real output streaming is
tested.
"""

import json
import logging
import os
import stat
import time
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

from server.lib import file_utils as fu
from server.lib import readme
from server.lib import transfer_utils as tu


# --- README: names, settings, context -----------------------------------------

@pytest.mark.parametrize('filename, lowering, expected', [
    ('README.md', None, 'README.md'),
    ('{cruiseID}_README.md', None, 'RR2601_README.md'),
    ('{cruiseID}_{loweringID}_README.md', 'DIVE01', 'RR2601_DIVE01_README.md'),
])
def test_readme_filename(filename, lowering, expected) -> None:
    """{cruiseID} and {loweringID} are filled in (#447)."""
    assert readme.readme_filename(filename, 'RR2601', lowering) == expected


@pytest.mark.parametrize('filename, cruise, lowering', [
    ('{loweringID}.md', 'RR2601', None),
    ('{cruiseID}.md', 'a/b', None),
    ('{cruiseID}', '', None),
    ('..', 'x', None),
])
def test_readme_filename_errors(filename, cruise, lowering) -> None:
    """The cruise README can't use {loweringID}; the name must be a plain file name."""
    with pytest.raises(ValueError):
        readme.readme_filename(filename, cruise, lowering)


def test_readme_settings(tmp_path, monkeypatch) -> None:
    """Defaults without a block; enable as text; the template must exist (#501)."""
    monkeypatch.setattr(readme, 'OPENVDM_ROOT', str(tmp_path))
    (tmp_path / 'server' / 'etc').mkdir(parents=True)
    (tmp_path / readme.DEFAULT_TEMPLATE).write_text('x')
    assert readme.readme_settings({}) == {'enable': True, 'filename': 'README.md',
                                          'template': str(tmp_path / readme.DEFAULT_TEMPLATE)}
    template = tmp_path / 'readme.md.j2'
    template.write_text('x')
    settings = readme.readme_settings({'cruiseReadme': {'enable': 'no', 'filename': ' {cruiseID}.md ',
                                                        'template': str(template)}})
    assert settings == {'enable': False, 'filename': '{cruiseID}.md', 'template': str(template)}


@pytest.mark.parametrize('block, message', [
    ({'filename': {'cruiseID': None}}, 'must be text'),
    ({'filename': 'docs/README.md'}, 'not a path'),
    ({'template': '/no/such/template.j2'}, 'README template not found'),
])
def test_readme_settings_errors(block, message) -> None:
    """A filename that is not text or not a file name, or a missing template."""
    with pytest.raises(ValueError, match=message):
        readme.readme_settings({'cruiseReadme': block})


def test_openvdm_version(monkeypatch, tmp_path) -> None:
    """From www/package.json; '' when it can't be read."""
    with open(os.path.join(readme.OPENVDM_ROOT, 'www', 'package.json'), encoding='utf-8') as package:
        assert readme.openvdm_version() == json.load(package)['version']
    monkeypatch.setattr(readme, 'OPENVDM_ROOT', str(tmp_path))
    assert readme.openvdm_version() == ''


CRUISE_CONFIG = {
    'cruiseID': 'RR2601', 'cruiseName': 'Test cruise', 'cruisePI': 'Dr. Smith', 'cruiseStartDate': '2026/10/01 00:00',
    'cruiseEndDate': '', 'cruiseExtent': '{"westernmost": -121, "easternmost": -120, "southernmost": 44, '
                                         '"northernmost": 45}',
    'warehouseConfig': {'loweringDataBaseDir': '/Vehicle/', 'cruiseConfigFn': 'ovdmConfig.json',
                        'md5SummaryFn': 'MD5_Summary.txt', 'md5SummaryMd5Fn': 'MD5_Summary.md5',
                        'dataDashboardManifestFn': 'manifest.json', 'loweringConfigFn': 'loweringConfig.json'},
}
SYSTEMS = [
    {'name': 'SCS', 'longName': 'Underway', 'destDir': '/SCS/{cruiseID}/', 'cruiseOrLowering': '0', 'enable': '1',
     'description': ' Nav and met ', 'smbPass': 'secret'},
    {'name': 'Off', 'destDir': 'Off', 'cruiseOrLowering': '0', 'enable': '0'},
    {'name': 'Video', 'longName': 'HD video', 'destDir': 'Video/{loweringID}', 'cruiseOrLowering': '1', 'enable': 1},
]
EXTRA_DIRS = [
    {'name': 'Dashboard_Data', 'destDir': 'Dashboard_Data', 'cruiseOrLowering': 0, 'enable': '1'},
    {'name': 'Notes', 'destDir': '{loweringDataBaseDir}/notes', 'cruiseOrLowering': 1},
]
VESSEL = {'name': 'R/V Example', 'contact': {'institution': 'Example U', 'email': 'ops@example.org'}}


def test_cruise_readme_context() -> None:
    """Only enabled folders and their safe fields; placeholders filled; the lowerings when used."""
    context = readme.build_cruise_readme_context(CRUISE_CONFIG, SYSTEMS, EXTRA_DIRS, VESSEL, 'README.md',
                                                 finalized_on='2026/10/20 12:00', show_lowerings=True)

    assert context['cruise']['cruiseName'] == 'Test cruise' and context['cruise']['cruiseEndDate'] == ''
    assert context['cruise']['cruiseExtent']['westernmost'] == -121
    assert context['cruise']['cruiseFinalizedOn'] == '2026/10/20 12:00'
    assert context['collection_systems'] == [{'name': 'SCS', 'longName': 'Underway', 'description': 'Nav and met',
                                              'destDir': 'SCS/RR2601'}]
    assert context['files'] == {'readme': 'README.md', 'cruise_config': 'ovdmConfig.json',
                                'md5_summary': 'MD5_Summary.txt', 'md5_summary_md5': 'MD5_Summary.md5',
                                'data_dashboard_manifest': 'Dashboard_Data/manifest.json'}
    lowerings = context['lowerings']
    assert lowerings['base_dir'] == 'Vehicle' and lowerings['config'] == 'loweringConfig.json'
    assert lowerings['collection_systems'][0]['destDir'] == 'Video/<loweringID>'
    assert lowerings['extra_directories'][0]['destDir'] == 'Vehicle/notes'
    assert 'secret' not in json.dumps(context)


def test_cruise_readme_context_without_lowerings_or_extent() -> None:
    """No lowerings, extent, Dashboard_Data or vessel."""
    config = {**CRUISE_CONFIG, 'cruiseExtent': 'not json'}
    context = readme.build_cruise_readme_context(config, [], [], None, 'README.md')
    assert context['lowerings'] is None and context['cruise']['cruiseExtent'] is None
    assert context['files']['data_dashboard_manifest'] is None and context['vessel'] == {}
    for value in ('', '  ', {}, None):
        assert readme._extent(value) is None  # pylint: disable=protected-access
    assert readme._extent({'westernmost': 1}) == {'westernmost': 1}  # pylint: disable=protected-access


def test_lowering_readme_context() -> None:
    """The lowering's folders relative to it, and its files relative to the cruise."""
    lowering = {'loweringID': 'DIVE01', 'loweringStartDate': '2026/10/02 10:00',
                'loweringExtent': {'westernmost': 1}, 'loweringFinalizedOn': None}
    context = readme.build_lowering_readme_context(lowering, CRUISE_CONFIG, SYSTEMS, EXTRA_DIRS, VESSEL, 'README.md')
    assert context['lowering']['loweringID'] == 'DIVE01' and context['lowering']['loweringEndDate'] == ''
    assert context['lowering']['loweringExtent'] == {'westernmost': 1}
    assert context['cruise'] == {'cruiseID': 'RR2601', 'cruiseName': 'Test cruise'}
    assert context['collection_systems'][0]['destDir'] == 'Video/DIVE01'
    assert context['files']['lowering_dir'] == 'Vehicle/DIVE01'
    assert context['files']['data_dashboard_manifest'] == 'Dashboard_Data/Vehicle/DIVE01/manifest.json'


# --- README: rendering and writing --------------------------------------------

def test_render_readme(tmp_path) -> None:
    """The generated line first (a comment in Markdown); runs of blank lines become one."""
    template = tmp_path / 't.md.j2'
    template.write_text('# {{ cruise.cruiseID }}\n\n\n\n{% if false %}x{% endif %}\n\nEnd\n')
    context = {'cruise': {'cruiseID': 'RR2601'}, 'files': {'readme': 'README.md'},
               'openvdm_version': '2.17.0', 'generated_on': '2026-10-22T10:00:00Z'}
    text = readme.render_readme(str(template), context)
    assert text == ('<!-- Generated by OpenVDM 2.17.0 on 2026-10-22T10:00:00Z from t.md.j2; '
                    'changes to this file are overwritten. -->\n# RR2601\n\nEnd\n')

    context.update(files={'readme': 'README.txt'}, openvdm_version='')
    assert readme.render_readme(str(template), context).startswith('Generated by OpenVDM on 2026')


@pytest.mark.parametrize('template, builder', [('cruise_readme.md.j2.dist', 'cruise'),
                                               ('lowering_readme.md.j2.dist', 'lowering')])
def test_shipped_templates_render(template, builder) -> None:
    """Both shipped templates render with a full context, so a broken edit fails here."""
    if builder == 'cruise':
        context = readme.build_cruise_readme_context(CRUISE_CONFIG, SYSTEMS, EXTRA_DIRS, VESSEL, 'README.md',
                                                     show_lowerings=True)
    else:
        context = readme.build_lowering_readme_context({'loweringID': 'DIVE01'}, CRUISE_CONFIG, SYSTEMS,
                                                       EXTRA_DIRS, VESSEL, 'README.md')
    text = readme.render_readme(os.path.join(readme.OPENVDM_ROOT, 'server', 'etc', template), context)
    assert text.startswith('<!-- Generated by OpenVDM') and 'RR2601' in text and 'R/V Example' in text
    assert '\n\n\n' not in text


def test_write_readme(tmp_path) -> None:
    """Written (and rewritten) when there's no file or OpenVDM's; another file is left alone."""
    path = tmp_path / 'README.md'
    assert readme.write_readme(str(path), '<!-- Generated by OpenVDM -->\nv1\n') == (True, '')
    assert readme.write_readme(str(path), '<!-- Generated by OpenVDM -->\nv2\n') == (True, '')
    assert path.read_text().endswith('v2\n') and not (tmp_path / 'README.md.tmp').exists()

    path.write_text('My own notes\n')
    written, reason = readme.write_readme(str(path), 'Generated by OpenVDM\n')
    assert not written and "wasn't written by OpenVDM" in reason and path.read_text() == 'My own notes\n'


def test_write_readme_errors(tmp_path) -> None:
    """A folder in the way, or a folder that does not exist."""
    (tmp_path / 'README.md').mkdir()
    assert not readme.write_readme(str(tmp_path / 'README.md'), 'x')[0]
    written, reason = readme.write_readme(str(tmp_path / 'missing' / 'README.md'), 'x')
    assert not written and reason.startswith('Unable to write README.md')


def test_write_readme_unreadable_existing_file(tmp_path, monkeypatch) -> None:
    """An existing file that cannot be read is not replaced."""
    path = tmp_path / 'README.md'
    path.write_text('x')
    real_open = open

    def fail_read(file, *args, **kwargs):
        if str(file) == str(path) and (not args or args[0] == 'r'):
            raise PermissionError('denied')
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fail_read)
    assert readme.write_readme(str(path), 'x') == (False, 'Unable to read the existing README.md: denied')


# --- Transfers: helpers -------------------------------------------------------

def test_redact_command() -> None:
    """An sshpass -p password is masked (#240); sshpass -f has nothing to mask."""
    assert tu.redact_command(['/usr/bin/sshpass', '-p', 'secret', 'rsync', 'a']) == '/usr/bin/sshpass -p **** rsync a'
    assert tu.redact_command(['sshpass', '-f', '/tmp/pw', 'ssh']) == 'sshpass -f /tmp/pw ssh'


def test_redact_payload() -> None:
    """Passwords at any depth are masked, empty ones shown; bad JSON isn't shown (#430)."""
    payload = json.dumps({'collectionSystemTransfer': {'smbPass': 'secret', 'rsyncPass': '', 'name': 'SCS'},
                          'list': [{'ftpPass': 'x'}]})
    assert json.loads(tu.redact_payload(payload)) == {
        'collectionSystemTransfer': {'smbPass': '****', 'rsyncPass': '', 'name': 'SCS'}, 'list': [{'ftpPass': '****'}]}
    assert tu.redact_payload({'sshPass': 'p'}, indent=2) == '{\n  "sshPass": "****"\n}'
    assert tu.redact_payload(b'not json') == '<not valid JSON; not shown>'


@pytest.mark.parametrize('tool, lines, expected', [
    ('rsync', ['sending', 'rsync: [sender] x failed', 'rsync error: code 23'], 'rsync: [sender] x failed'),
    ('rsync', ['@ERROR: Unknown module', 'rsync error: code 5'], '@ERROR: Unknown module'),
    ('rsync', ['rsync error: code 12'], 'rsync error: code 12'),
    ('rsync', ['nothing useful'], ''),
    ('rclone', ['2026/10/22 10:00:00 ERROR : a.txt: Failed to copy: denied'], 'a.txt: Failed to copy: denied'),
    ('rclone', ['2026/10/22 10:00:00 Failed to create file system'], 'Failed to create file system'),
    ('rclone', ['INFO : all good'], ''),
])
def test_error_detail(tool, lines, expected) -> None:
    """The most specific error line, without rclone's timestamp and level."""
    assert tu.error_detail(tool, lines) == expected


def test_transfer_command_error() -> None:
    """The message names the tool, the exit code and the detail."""
    error = tu.TransferCommandError('rsync', 23, 'detail')
    assert str(error) == 'rsync exited with code 23: detail' and error.files == {'new': [], 'updated': [], 'deleted': []}
    assert str(tu.TransferCommandError('rclone', 1, '')) == 'rclone exited with code 1'


# --- Transfers: running commands ----------------------------------------------

def _tool(tmp_path, name, output, code=0, then=''):
    """A stand-in for rsync or rclone that prints *output* and exits with *code*."""
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\ncat <<'EOF'\n{output}\nEOF\n{then}\nexit {code}\n")
    script.chmod(0o755)
    return [str(script), '--fake']


RSYNC_OUTPUT = """\
sending incremental file list
>f+++++++++ new.txt
      1,024 100%  0.00kB/s  0:00:00 (xfr#1, to-chk=2/4)
>f.st...... sub/updated.txt
*deleting   old.txt
<f+++++++++ remote_new.txt
      2,048 100%  0.00kB/s  0:00:00 (xfr#2, to-chk=0/4)
"""


def test_rsync_transfer(tmp_path) -> None:
    """New, updated and deleted files from -i, and progress from to-chk."""
    progress = []
    result = tu.run_transfer_command(_tool(tmp_path, 'rsync', RSYNC_OUTPUT), 4, progress.append)
    assert result == {'new': ['new.txt', 'remote_new.txt'], 'updated': ['sub/updated.txt'], 'deleted': ['old.txt'],
                      'stopped': False}
    assert progress == [50, 100]


def test_rclone_transfer(tmp_path) -> None:
    """Files from rclone -v, and progress from Transferred: lines."""
    output = ('2026/10/22 10:00:00 INFO  : a.txt: Copied (new)\n'
              '2026/10/22 10:00:01 INFO  : b.txt: Copied (replaced existing)\n'
              '2026/10/22 10:00:02 INFO  : c.txt: Deleted\n'
              'Transferred:   1.000 MiB / 2.000 MiB, 50%, 1 MiB/s, ETA 1s\n'
              'Transferred:   2.000 MiB / 2.000 MiB, 100%, 1 MiB/s, ETA 0s\n')
    progress = []
    result = tu.run_transfer_command(['sshpass', '-f', '/x'][:0] + _tool(tmp_path, 'rclone', output), 3,
                                     progress.append)
    assert result == {'new': ['a.txt'], 'updated': ['b.txt'], 'deleted': ['c.txt'], 'stopped': False}
    assert progress == [50, 100]


def test_nothing_to_transfer() -> None:
    """With no files expected the command isn't run."""
    assert tu.run_transfer_command(['/no/such/rsync'], 0) == {'new': [], 'updated': [], 'deleted': [],
                                                               'stopped': False}


@pytest.mark.parametrize('code', [24, 23])
def test_vanished_files_are_not_errors(tmp_path, code, caplog) -> None:
    """Exit 24, and 23 with only vanished listed files, count as success."""
    output = '>f+++++++++ a.txt\nrsync: [sender] link_stat "/src/gone.txt" failed: No such file or directory (2)'
    with caplog.at_level(logging.WARNING):
        result = tu.run_transfer_command(_tool(tmp_path, 'rsync', output, code), 2)
    assert result['new'] == ['a.txt']
    assert ('vanished' if code == 23 else 'treating as success') in caplog.text


def test_rsync_failure_keeps_the_first_errors(tmp_path) -> None:
    """The first real error and how many more, and what was copied before it (#237, #239)."""
    output = '\n'.join(['>f+++++++++ copied.txt'] +
                       [f'rsync: [sender] send_files failed to open "/src/f{i}": Permission denied (13)'
                        for i in range(12)] +
                       ['rsync error: some files/attrs were not transferred (code 23)'])
    with pytest.raises(tu.TransferCommandError) as exc:
        tu.run_transfer_command(_tool(tmp_path, 'rsync', output, 23), 13)
    assert exc.value.returncode == 23 and exc.value.files['new'] == ['copied.txt']
    assert exc.value.detail.endswith('"/src/f0": Permission denied (13) (and 11 more errors)')


def test_rsync_failure_without_error_lines(tmp_path) -> None:
    """Without rsync: lines, the most specific other line."""
    with pytest.raises(tu.TransferCommandError) as exc:
        tu.run_transfer_command(_tool(tmp_path, 'rsync', 'rsync error: unexplained error (code 255)', 255), 1)
    assert exc.value.detail == 'rsync error: unexplained error (code 255)'

    with pytest.raises(tu.TransferCommandError) as exc:
        tu.run_transfer_command(_tool(tmp_path, 'rsync', 'rsync: one problem', 12), 1)
    assert exc.value.detail == 'rsync: one problem'


def test_rclone_failure(tmp_path) -> None:
    """A failed rclone copy raises with rclone's error."""
    output = '2026/10/22 10:00:00 ERROR : a.txt: Failed to copy: 403 Forbidden'
    with pytest.raises(tu.TransferCommandError) as exc:
        tu.run_transfer_command(_tool(tmp_path, 'rclone', output, 1), 1)
    assert str(exc.value) == 'rclone exited with code 1: a.txt: Failed to copy: 403 Forbidden'


def test_stop_terminates_the_command(tmp_path) -> None:
    """Stop ends the command and returns the files so far, without failing."""
    lines = iter([False, True])
    started = time.monotonic()
    result = tu.run_transfer_command(_tool(tmp_path, 'rsync', '>f+++++++++ a.txt\n>f+++++++++ b.txt', 0,
                                           then='exec sleep 30'), 2, should_stop=lambda: next(lines, True))
    assert result == {'new': ['a.txt'], 'updated': [], 'deleted': [], 'stopped': True}
    assert time.monotonic() - started < 10


# --- Files: listing and list files --------------------------------------------

def _tree(root, paths):
    """Create files under root."""
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text('x')


def test_build_filelist(tmp_path) -> None:
    """Relative paths; non-ASCII excluded; ignored files, folders and symlinks skipped (#265)."""
    _tree(tmp_path, ['a.txt', 'sub/b.txt', 'café.txt', '.DS_Store', '@eaDir/thumb.jpg'])
    os.symlink(tmp_path / 'a.txt', tmp_path / 'link.txt')
    files = fu.build_filelist(str(tmp_path))
    assert sorted(files['include']) == ['a.txt', 'sub/b.txt'] and files['exclude'] == ['café.txt']
    assert files['new'] == [] and files['updated'] == []


def test_write_list_file(tmp_path) -> None:
    """One entry per line, each ending in a newline (#255); unwritable is False."""
    path = tmp_path / 'list.txt'
    assert fu.write_list_file(['a', 'b c'], str(path)) and path.read_text() == 'a\nb c\n'
    assert fu.write_list_file([], str(path)) and path.read_text() == ''
    assert fu.write_list_file(['a'], str(tmp_path / 'missing' / 'list.txt')) is False


def test_clear_directory(tmp_path) -> None:
    """Everything inside is deleted, symlinks too; delete_self removes the directory."""
    _tree(tmp_path / 'target', ['a.txt', 'sub/deep/b.txt'])
    os.symlink(tmp_path / 'elsewhere', tmp_path / 'target' / 'dangling')
    assert fu.clear_directory(str(tmp_path / 'target')) == {'verdict': True, 'reason': []}
    assert os.listdir(tmp_path / 'target') == []
    assert fu.clear_directory(str(tmp_path / 'target'), delete_self=True)['verdict']
    assert not (tmp_path / 'target').exists()
    assert fu.clear_directory(str(tmp_path / 'missing')) == {
        'verdict': False, 'reason': [f"Directory not found: {tmp_path / 'missing'}"]}


def test_clear_directory_reports_files_it_cant_delete(tmp_path, monkeypatch) -> None:
    """A file at the top that can't be deleted is reported."""
    _tree(tmp_path, ['a.txt'])
    monkeypatch.setattr(fu.os, 'remove', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    result = fu.clear_directory(str(tmp_path))
    assert not result['verdict'] and result['reason'][0].startswith('Failed to delete')


def test_clear_directory_unlistable(tmp_path, monkeypatch) -> None:
    """A directory that cannot be listed is reported."""
    monkeypatch.setattr(fu.os, 'listdir', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    assert fu.clear_directory(str(tmp_path))['reason'][0].startswith('Failed to list contents')


def test_clear_directory_reports_failures_in_subdirectories(tmp_path, monkeypatch) -> None:
    """A file inside a subdirectory that can't be deleted is reported too (#539)."""
    _tree(tmp_path, ['sub/a.txt'])
    monkeypatch.setattr(fu.os, 'remove', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    result = fu.clear_directory(str(tmp_path))
    assert not result['verdict'] and any('a.txt' in reason for reason in result['reason'])


def test_delete_from_dest(tmp_path) -> None:
    """Files not in the list are deleted, then empty folders (Sync from source)."""
    _tree(tmp_path, ['keep.txt', 'old.txt', 'sub/keep2.txt', 'gone/x.txt'])
    deleted = fu.delete_from_dest(str(tmp_path), ['keep.txt', 'sub/keep2.txt'])
    assert sorted(deleted) == ['gone/x.txt', 'old.txt']
    assert sorted(os.listdir(tmp_path)) == ['keep.txt', 'sub']


@pytest.mark.parametrize('error, message', [(FileNotFoundError, 'not found'),
                                            (PermissionError, 'permission errors'),
                                            (OSError, 'OS error')])
def test_delete_from_dest_errors(tmp_path, monkeypatch, caplog, error, message) -> None:
    """A file that cannot be deleted is logged and not reported as deleted."""
    _tree(tmp_path, ['old.txt'])
    monkeypatch.setattr(fu.os, 'remove', lambda path: (_ for _ in ()).throw(error('x')))
    assert fu.delete_from_dest(str(tmp_path), []) == []
    assert message in caplog.text


def test_delete_from_dest_folder_error(tmp_path, monkeypatch, caplog) -> None:
    """An empty folder that cannot be removed is logged."""
    (tmp_path / 'empty').mkdir()
    monkeypatch.setattr(fu.os, 'rmdir', lambda path: (_ for _ in ()).throw(OSError('busy')))
    fu.delete_from_dest(str(tmp_path), [])
    assert 'Directory not deleted' in caplog.text


# --- Files: purging old logs --------------------------------------------------

def _aged(path, hours):
    """Create a file last modified *hours* ago."""
    path.write_text('x')
    then = time.time() - hours * 3600
    os.utime(path, (then, then))


def test_purge_old_files(tmp_path) -> None:
    """Older than the age are deleted, except excluded names; subfolders only when recursive."""
    _aged(tmp_path / 'old.log', 13)
    _aged(tmp_path / 'new.log', 1)
    _aged(tmp_path / 'SCS_Exclude.log', 100)
    (tmp_path / 'sub').mkdir()
    _aged(tmp_path / 'sub' / 'old.log', 13)

    fu.purge_old_files(str(tmp_path), excludes='*Exclude.log')
    assert sorted(os.listdir(tmp_path)) == ['SCS_Exclude.log', 'new.log', 'sub']
    assert os.listdir(tmp_path / 'sub') == ['old.log']

    fu.purge_old_files(str(tmp_path), timedelta_str='0 days 2 hours 3 minutes 4 seconds', recursive=True)
    assert os.listdir(tmp_path / 'sub') == []


@pytest.mark.parametrize('value', ['2 hours', '1 day', '30 minutes', '90 seconds'])
def test_purge_units(tmp_path, value) -> None:
    """Days, hours, minutes and seconds."""
    _aged(tmp_path / 'old.log', 48)
    fu.purge_old_files(str(tmp_path), timedelta_str=value)
    assert not (tmp_path / 'old.log').exists()


@pytest.mark.parametrize('error, message', [(FileNotFoundError, 'not found'), (PermissionError, 'permission'),
                                            (OSError, 'OS error')])
def test_purge_errors(tmp_path, monkeypatch, caplog, error, message) -> None:
    """A file that cannot be purged is logged."""
    _aged(tmp_path / 'old.log', 48)
    monkeypatch.setattr(fu.os, 'remove', lambda path: (_ for _ in ()).throw(error('x')))
    fu.purge_old_files(str(tmp_path))
    assert message in caplog.text


@pytest.mark.parametrize('value, message', [
    ('12', 'expected pairs of a number and a unit'),
    ('1 fortnight', "unknown unit 'fortnight'"),
    ('twelve hours', "'twelve' isn't a number"),
])
def test_purge_with_an_unusable_age_doesnt_raise(tmp_path, value, message, caplog) -> None:
    """An age it can't parse is logged and nothing purged, instead of raising into the
    scheduler, which calls it every cycle (#540)."""
    _aged(tmp_path / 'old.log', 48)
    fu.purge_old_files(str(tmp_path), timedelta_str=value)
    assert (tmp_path / 'old.log').exists()
    assert 'unusable logfilePurgeTimedelta' in caplog.text and message in caplog.text


@pytest.mark.parametrize('value, purged', [('1 week', False), ('1 weeks', False), ('1.5 days', True),
                                           ('1 Day 12 HOURS', True)])
def test_purge_weeks_and_decimals(tmp_path, value, purged) -> None:
    """Weeks, as datetime.timedelta takes, decimals and any case (#540)."""
    _aged(tmp_path / 'old.log', 48)
    fu.purge_old_files(str(tmp_path), timedelta_str=value)
    assert (tmp_path / 'old.log').exists() is not purged


def test_purge_missing_directory(tmp_path, caplog) -> None:
    """A log directory that doesn't exist yet is skipped with a warning (#540)."""
    fu.purge_old_files(str(tmp_path / 'missing'))
    assert "isn't a directory" in caplog.text


def test_purge_listing_error(tmp_path, monkeypatch, caplog) -> None:
    """An error listing the directory is logged, not raised (#540)."""
    monkeypatch.setattr(fu.os, 'listdir', lambda path: (_ for _ in ()).throw(PermissionError('denied')))
    fu.purge_old_files(str(tmp_path))
    assert 'Error purging old files' in caplog.text


# --- Files: JSON, ownership, directories --------------------------------------

def test_output_json_data_to_file(tmp_path) -> None:
    """Parent folders are created; numpy values and datetimes are written."""
    path = tmp_path / 'a' / 'b' / 'data.json'
    data = {'n': np.int64(3), 'f': np.float32(0.5), 'arr': np.array([1, 2]), 't': datetime(2026, 10, 22, 10)}
    assert fu.output_json_data_to_file(str(path), data) == {'verdict': True}
    assert json.loads(path.read_text()) == {'n': 3, 'f': 0.5, 'arr': [1, 2], 't': '2026-10-22T10:00:00.000000Z'}
    assert fu.output_json_data_to_file(str(path), [1])['verdict']


def test_output_json_data_to_file_errors(tmp_path, monkeypatch) -> None:
    """A parent folder that can't be created, a failed write, or an unexpected error."""
    (tmp_path / 'file').write_text('x')
    result = fu.output_json_data_to_file(str(tmp_path / 'file' / 'sub' / 'data.json'), {})
    assert result['verdict'] is False and 'Unable to create parent' in result['reason']

    def fail_dump(*args, **kwargs):
        raise IOError('disk full')

    monkeypatch.setattr(fu.json, 'dump', fail_dump)
    assert fu.output_json_data_to_file(str(tmp_path / 'd.json'), {})['reason'].startswith('Unable to create data file')

    monkeypatch.setattr(fu.os, 'makedirs', lambda path: (_ for _ in ()).throw(RuntimeError('odd')))
    with pytest.raises(RuntimeError):
        fu.output_json_data_to_file(str(tmp_path / 'x' / 'd.json'), {})


def test_output_json_data_to_file_that_cant_be_opened(tmp_path) -> None:
    """A file that can't be opened (e.g. a folder in its place) is a failed verdict, not an exception (#541)."""
    (tmp_path / 'data.json').mkdir()
    assert fu.output_json_data_to_file(str(tmp_path / 'data.json'), {}) == {
        'verdict': False, 'reason': f"Unable to create data file: {tmp_path / 'data.json'}"}


def test_output_json_data_that_cant_be_serialized(tmp_path) -> None:
    """Data JSON can't hold is a failed verdict too."""
    assert fu.output_json_data_to_file(str(tmp_path / 'd.json'), {'s': {1, 2}})['verdict'] is False


def test_np_encoder_rejects_other_types() -> None:
    """Types it does not know still fail."""
    with pytest.raises(TypeError):
        json.dumps({'s': {1, 2}}, cls=fu.NpEncoder)


@pytest.fixture
def chown(monkeypatch):
    """Record os.chown calls (tests can't change ownership) and give the user ids."""
    calls = []
    monkeypatch.setattr(fu, 'getpwnam', lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1001))
    monkeypatch.setattr(fu.os, 'chown', lambda path, uid, gid: calls.append((path, uid, gid)))
    return calls


def test_set_owner_group_permissions(tmp_path, chown) -> None:
    """Every file 644 and folder 755, owned by the user."""
    _tree(tmp_path, ['a.txt', 'sub/b.txt'])
    assert fu.set_owner_group_permissions('survey', str(tmp_path)) == {'verdict': True}
    assert {path for path, _, _ in chown} == {str(tmp_path), str(tmp_path / 'a.txt'), str(tmp_path / 'sub'),
                                              str(tmp_path / 'sub' / 'b.txt')}
    assert stat.S_IMODE(os.stat(tmp_path / 'sub').st_mode) == 0o755
    assert stat.S_IMODE(os.stat(tmp_path / 'a.txt').st_mode) == 0o644
    assert fu.set_owner_group_permissions('survey', str(tmp_path / 'a.txt')) == {'verdict': True}


def test_set_owner_group_permissions_failures(tmp_path, monkeypatch) -> None:
    """Ownership that cannot be set is counted in the reason."""
    _tree(tmp_path, ['a.txt', 'sub/b.txt'])
    monkeypatch.setattr(fu, 'getpwnam', lambda user: SimpleNamespace(pw_uid=0, pw_gid=0))
    monkeypatch.setattr(fu.os, 'chown', lambda *args: (_ for _ in ()).throw(PermissionError('not root')))
    assert fu.set_owner_group_permissions('root', str(tmp_path)) == {
        'verdict': False, 'reason': 'Unable to set ownership/permissions for 4 file(s)'}
    assert fu.set_owner_group_permissions('root', str(tmp_path / 'a.txt'))['verdict'] is False


def test_create_directories(tmp_path, monkeypatch) -> None:
    """Missing ones (with parents) are created, existing ones skipped, failures reported."""
    (tmp_path / 'exists').mkdir()
    assert fu.create_directories([str(tmp_path / 'exists'), str(tmp_path / 'a' / 'b')]) == {'verdict': True}
    assert (tmp_path / 'a' / 'b').is_dir()
    (tmp_path / 'file').write_text('x')
    result = fu.create_directories([str(tmp_path / 'file' / 'sub')])
    assert result == {'verdict': False, 'reason': f"Unable to create directory: {tmp_path / 'file' / 'sub'}"}


def test_lockdown_directory(tmp_path) -> None:
    """Files 600 and folders 700 at the top level, except exempt folders."""
    _tree(tmp_path, ['a.txt', 'private/x.txt', 'PublicData/y.txt'])
    assert fu.lockdown_directory(str(tmp_path), ['PublicData']) == {'verdict': True}
    assert stat.S_IMODE(os.stat(tmp_path / 'a.txt').st_mode) == 0o600
    assert stat.S_IMODE(os.stat(tmp_path / 'private').st_mode) == 0o700
    assert stat.S_IMODE(os.stat(tmp_path / 'PublicData').st_mode) != 0o700
    os.chmod(tmp_path / 'private', 0o755)


def test_lockdown_directory_errors(tmp_path, monkeypatch) -> None:
    """Exempt folders must be a list; listing and chmod failures are reported."""
    with pytest.raises(ValueError):
        fu.lockdown_directory(str(tmp_path), 'PublicData')
    assert fu.lockdown_directory(str(tmp_path / 'missing'))['reason'].startswith('Failed to list contents')
    _tree(tmp_path, ['a.txt', 'sub/b.txt'])
    monkeypatch.setattr(fu.os, 'chmod', lambda *args: (_ for _ in ()).throw(PermissionError('x')))
    assert fu.lockdown_directory(str(tmp_path))['reason'].count('Unable to set permissions') == 2


def test_test_write_access(tmp_path) -> None:
    """A writable folder passes and is left empty; a missing one fails."""
    assert fu.test_write_access(str(tmp_path)) is True and os.listdir(tmp_path) == []
    assert fu.test_write_access(str(tmp_path / 'missing')) is False


def test_process_alive(monkeypatch) -> None:
    """Our own process is alive; a missing one isn't; another user's counts as alive."""
    assert fu._process_alive(os.getpid()) is True  # pylint: disable=protected-access
    monkeypatch.setattr(fu.os, 'kill', lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    assert fu._process_alive(1) is False  # pylint: disable=protected-access
    monkeypatch.setattr(fu.os, 'kill', lambda pid, sig: (_ for _ in ()).throw(PermissionError()))
    assert fu._process_alive(1) is True  # pylint: disable=protected-access


def test_temporary_directory_cleans_up_after_an_error() -> None:
    """The directory is removed after an exception, or kept with preserve_on_error."""
    with pytest.raises(RuntimeError):
        with fu.temporary_directory() as tmpdir:
            raise RuntimeError('boom')
    assert not os.path.exists(tmpdir)

    with pytest.raises(RuntimeError):
        with fu.temporary_directory(preserve_on_error=True) as kept:
            raise RuntimeError('boom')
    assert os.path.isdir(kept)
    os.rmdir(kept)


def test_readme_settings_suggests_copying_the_dist(tmp_path) -> None:
    """A missing template whose .dist exists says to copy it (#501)."""
    (tmp_path / 'readme.md.j2.dist').write_text('x')
    with pytest.raises(ValueError, match='Copy readme.md.j2.dist to it, or re-run the installer'):
        readme.readme_settings({'cruiseReadme': {'template': str(tmp_path / 'readme.md.j2')}})


def test_temporary_directory_that_cant_be_deleted(monkeypatch, caplog) -> None:
    """A temporary directory that can't be removed is logged, not raised."""
    monkeypatch.setattr(fu.shutil, 'rmtree', lambda path: (_ for _ in ()).throw(OSError('busy')))
    with fu.temporary_directory() as tmpdir:
        pass
    assert f'Could not delete temp dir {tmpdir}: busy' in caplog.text
    os.rmdir(tmpdir)


def test_orphan_deleted_by_another_process_is_skipped(tmp_path, monkeypatch) -> None:
    """A directory another process deletes just as it's opened is skipped, not an error."""
    (tmp_path / f'{fu.TEMP_DIR_PREFIX}99999999-abc').mkdir()
    monkeypatch.setattr(fu, '_process_alive', lambda pid: False)
    monkeypatch.setattr(fu.os, 'open', lambda path, flags: (_ for _ in ()).throw(FileNotFoundError(path)))
    assert fu.cleanup_orphaned_temporary_directories(str(tmp_path)) == []


def test_orphan_another_cleanup_holds_is_skipped(tmp_path, monkeypatch) -> None:
    """A directory whose lock another cleanup holds is left to it."""
    (tmp_path / f'{fu.TEMP_DIR_PREFIX}99999999-abc').mkdir()
    monkeypatch.setattr(fu, '_process_alive', lambda pid: False)
    monkeypatch.setattr(fu.fcntl, 'flock', lambda fd, op: (_ for _ in ()).throw(BlockingIOError()))
    assert fu.cleanup_orphaned_temporary_directories(str(tmp_path)) == []
    assert (tmp_path / f'{fu.TEMP_DIR_PREFIX}99999999-abc').is_dir()
