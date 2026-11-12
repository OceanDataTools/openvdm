"""Tests for bin/build_remote_directory.py (#514).

The script copies a template tree onto each collection system's source
directory, filling in ``{cruiseID}`` and ``{loweringID}``, never overwriting
(#428). ``main()`` runs with a command line and the fake ``OpenVDM``: local
directory transfers write to temporary folders, SSH ones go to ``fake_run``,
and the SMB mount is replaced.
"""

import os
import sys
from types import SimpleNamespace

import pytest


def _cst(name, source_dir, transfer_type=1, cruise_or_lowering=0, **extra):
    return {'collectionSystemTransferID': len(name), 'name': name, 'sourceDir': str(source_dir),
            'transferType': transfer_type, 'cruiseOrLowering': cruise_or_lowering, 'sshUseKey': 0,
            'sshServer': 'acq.example', 'sshUser': 'survey', 'sshPass': 'pw', 'smbServer': '//acq/share',
            'smbUser': 'survey', 'smbPass': 'pw', 'smbDomain': '', **extra}


@pytest.fixture
def site(tmp_path, fake_ovdm, monkeypatch):
    """A template (XBT, with a cruise folder and a seed file; ROV with a lowering folder), the
    cruise RV1001 and lowering DIVE07, and the transfers' source folders."""
    template = tmp_path / 'template'
    (template / 'XBT' / '{cruiseID}' / 'raw_data').mkdir(parents=True)
    (template / 'XBT' / '{cruiseID}' / '{cruiseID}_XBT_log.csv').write_text('time,depth\n')
    (template / 'ROV' / '{loweringID}').mkdir(parents=True)
    (template / 'ROV' / '{loweringID}' / '{cruiseID}_{loweringID}.txt').write_text('')
    sources = tmp_path / 'sources'
    (sources / 'xbt').mkdir(parents=True)
    fake_ovdm.get_cruise_id.return_value = 'RV1001'
    fake_ovdm.get_lowering_id.return_value = 'DIVE07'
    csts = {'XBT': _cst('XBT', sources / 'xbt'), 'ROV': _cst('ROV', sources / 'rov', cruise_or_lowering=1),
            'SCS': _cst('SCS', sources / 'scs', transfer_type=2)}
    fake_ovdm.get_active_collection_system_transfers.side_effect = \
        lambda cruise=True, lowering=True: [cst for cst in csts.values()
                                            if (cst['cruiseOrLowering'] == 0 and cruise)
                                            or (cst['cruiseOrLowering'] == 1 and lowering)]
    fake_ovdm.get_collection_system_transfer_by_name.side_effect = csts.get
    owners = []
    return SimpleNamespace(ovdm=fake_ovdm, template=template, sources=sources, csts=csts, owners=owners)


@pytest.fixture
def run(load_dist, monkeypatch, site):
    """Return a function that runs the script's main() with *args* (and ``-t`` the template)."""
    module = load_dist('bin/build_remote_directory.py.dist', name='build_remote_directory')
    monkeypatch.setattr(module, 'OpenVDM', lambda: site.ovdm)

    def owner(user, path):
        site.owners.append((user, path))
        return {'verdict': True}
    monkeypatch.setattr(module, 'set_owner_group_permissions', owner)
    site.module = module

    def run_script(*args, template=True):
        argv = ['build_remote_directory', *(['-t', str(site.template)] if template else []), *args]
        monkeypatch.setattr(sys, 'argv', argv)
        try:
            module.main()
        except SystemExit as exc:
            return exc.code
        return 0
    return run_script


def _tree(root):
    return sorted(str(path.relative_to(root)) for path in root.rglob('*'))


# --- Local directories ----------------------------------------------------------------

def test_cruise_template(run, site) -> None:
    """The cruise transfers get their template, with {cruiseID} filled in; what's created is given
    to the warehouse user. Transfers without a template, or of another type, are skipped."""
    assert run() == 0
    assert _tree(site.sources / 'xbt') == ['RV1001', 'RV1001/RV1001_XBT_log.csv', 'RV1001/raw_data']
    assert (site.sources / 'xbt' / 'RV1001' / 'RV1001_XBT_log.csv').read_text() == 'time,depth\n'
    assert sorted(path for _, path in site.owners) == sorted(
        str(site.sources / 'xbt' / name) for name in _tree(site.sources / 'xbt'))
    assert {user for user, _ in site.owners} == {'survey'}
    assert not (site.sources / 'rov').exists()


def test_never_overwrites(run, site) -> None:
    """A second run creates nothing new and leaves edited files alone (#428)."""
    run()
    log = site.sources / 'xbt' / 'RV1001' / 'RV1001_XBT_log.csv'
    log.write_text('edited\n')
    site.owners.clear()
    assert run() == 0
    assert log.read_text() == 'edited\n'
    assert site.owners == []


def test_lowering_template(run, site) -> None:
    """-l builds the lowering transfers', with {loweringID} filled in, creating the source folder with -s."""
    assert run('-l', '-s') == 0
    assert _tree(site.sources / 'rov') == ['DIVE07', 'DIVE07/RV1001_DIVE07.txt']
    assert not (site.sources / 'xbt' / 'RV1001').exists()


def test_missing_source_directory(run, site, caplog) -> None:
    """Without -s, a source folder that doesn't exist fails that transfer, and the script exits 1."""
    (site.sources / 'xbt').rmdir()
    assert run() == 1
    assert "doesn't exist (use -s to create it)" in caplog.text
    assert 'Failed for: XBT' in caplog.text


def test_source_directory_with_placeholders(run, site) -> None:
    """The source folder's placeholders are filled in too."""
    site.csts['XBT']['sourceDir'] = str(site.sources / '{cruiseID}' / 'xbt')
    assert run('-s') == 0
    assert (site.sources / 'RV1001' / 'xbt' / 'RV1001' / 'raw_data').is_dir()


def test_wildcard_source_directory(run, site, caplog) -> None:
    """A source folder with a wildcard can't be built on."""
    site.csts['XBT']['sourceDir'] = str(site.sources / 'xbt*')
    assert run() == 1
    assert 'has a wildcard' in caplog.text


def test_cant_create(run, site, caplog, monkeypatch) -> None:
    """Folders and files that can't be created are reported, and the script exits 1."""
    real_mkdir = site.module.os.mkdir

    def mkdir(path, mode=0o777):
        if str(path).endswith('raw_data') and str(site.sources) in str(path):
            raise PermissionError(13, 'Permission denied')
        real_mkdir(path, mode)
    monkeypatch.setattr(site.module.os, 'mkdir', mkdir)
    assert run() == 1
    assert 'Unable to create directory' in caplog.text


def test_ownership_fails(run, site, caplog, monkeypatch) -> None:
    """If ownership can't be set, that's reported and the script exits 1."""
    monkeypatch.setattr(site.module, 'set_owner_group_permissions',
                        lambda user, path: {'verdict': False, 'reason': f'chown {path} failed'})
    assert run() == 1
    assert 'failed' in caplog.text


# --- Choosing collection systems ------------------------------------------------------

def test_named_collection_system(run, site) -> None:
    """-c builds only the named collection systems."""
    assert run('-c', 'ROV', '-s') == 0
    assert (site.sources / 'rov' / 'DIVE07').is_dir()
    assert not (site.sources / 'xbt' / 'RV1001').exists()


@pytest.mark.parametrize('args, setup, message', [
    (('-c', 'NoSuch'), None, 'Collection System: NoSuch not found'),
    (('-c', 'SCS'), None, 'is not a Local Directory, SMB Share or SSH Server Transfer'),
    (('-c', 'ROV'), 'no_lowering', 'No lowering ID has been defined'),
    (('-l',), 'no_lowering', 'No lowering ID has been defined'),
])
def test_bad_choice(run, site, caplog, args, setup, message) -> None:
    """A named collection system that doesn't exist, isn't supported, or needs a lowering there
    isn't, exits 1; so does -l without a lowering."""
    if setup == 'no_lowering':
        site.ovdm.get_lowering_id.return_value = None
    assert run(*args) == 1
    assert message in caplog.text


def test_no_template_directory(run, caplog, tmp_path) -> None:
    """A template folder that doesn't exist exits 1."""
    assert run('-t', str(tmp_path / 'missing'), template=False) == 1
    assert 'does not exist' in caplog.text


# --- SSH and SMB ------------------------------------------------------------------------

def test_ssh(run, site, fake_run) -> None:
    """An SSH transfer's source folder is checked (or created with -s) over ssh, then the template
    is copied with rsync --ignore-existing, with the password through sshpass."""
    site.csts['XBT'].update(transferType=4, sourceDir='/data/xbt dir')
    assert run('-s') == 0
    ssh = next(call.cmd for call in fake_run.calls if "mkdir -p '/data/xbt dir'" in call.cmd)
    rsync = next(call.cmd for call in fake_run.calls if 'rsync' in call.cmd)
    assert ssh[:2] == ['sshpass', '-f'] and ssh[-1] == "mkdir -p '/data/xbt dir'"
    assert '--ignore-existing' in rsync and '--protect-args' in rsync
    assert rsync[-1] == 'survey@acq.example:/data/xbt dir/'
    fake_run.assert_not_in_commands('pw')


def test_ssh_source_missing(run, site, fake_run, caplog) -> None:
    """Without -s, an SSH source folder that doesn't exist fails, with ssh's message."""
    site.csts['XBT'].update(transferType=4, sourceDir='/data/xbt', sshUseKey=1)
    fake_run.on('ssh', returncode=1)
    assert run() == 1
    assert "Source directory /data/xbt doesn't exist on acq.example (use -s to create it): exit code 1" in caplog.text
    assert 'BatchMode=yes' in fake_run.calls[0].cmd


@pytest.mark.parametrize('fails, message', [('mkdir', 'Unable to create source directory /data/xbt on acq.example'),
                                            ('rsync', 'Unable to copy the template to /data/xbt on acq.example')])
def test_ssh_fails(run, site, fake_run, caplog, fails, message) -> None:
    """A failed ssh or rsync fails the transfer with its error."""
    site.csts['XBT'].update(transferType=4, sourceDir='/data/xbt')

    def fail(cmd, kwargs):
        if any(fails in arg for arg in cmd):
            raise OSError('connection refused')
    fake_run.on('sshpass', effect=fail)
    assert run('-s') == 1
    assert f'{message}: connection refused' in caplog.text


def test_smb(run, site, monkeypatch, tmp_path) -> None:
    """An SMB share is mounted read-write, and the template copied onto it."""
    site.csts['XBT'].update(transferType=3, sourceDir='/xbt')
    mounts = []

    def mount(cfg, mntpoint, version):
        mounts.append((cfg['removeSourceFiles'], version))
        (tmp_path / 'share').mkdir(exist_ok=True)
        os.rmdir(mntpoint)
        os.symlink(tmp_path / 'share', mntpoint)
        return True, ''
    monkeypatch.setattr(site.module, 'detect_smb_version', lambda cfg: ('3.0', ''))
    monkeypatch.setattr(site.module, 'mount_smb_share', mount)
    assert run('-s') == 0
    assert mounts == [(1, '3.0')]
    assert (tmp_path / 'share' / 'xbt' / 'RV1001' / 'RV1001_XBT_log.csv').is_file()


@pytest.mark.parametrize('version, mounted, message', [
    (None, True, 'Unable to connect to SMB server //acq/share: no reply'),
    ('3.0', False, 'Unable to mount SMB share //acq/share: permission denied'),
])
def test_smb_fails(run, site, monkeypatch, caplog, version, mounted, message) -> None:
    """A share that can't be reached or mounted fails the transfer."""
    site.csts['XBT'].update(transferType=3, sourceDir='/xbt')
    monkeypatch.setattr(site.module, 'detect_smb_version', lambda cfg: (version, 'no reply'))
    monkeypatch.setattr(site.module, 'mount_smb_share', lambda cfg, mnt, v: (mounted, 'permission denied'))
    assert run() == 1
    assert message in caplog.text


def test_smb_source_missing(run, site, monkeypatch, caplog) -> None:
    """Without -s, a source folder that isn't on the share fails, naming the share."""
    site.csts['XBT'].update(transferType=3, sourceDir='/xbt')
    monkeypatch.setattr(site.module, 'detect_smb_version', lambda cfg: ('3.0', ''))
    monkeypatch.setattr(site.module, 'mount_smb_share', lambda cfg, mnt, v: (True, ''))
    assert run() == 1
    assert "Source directory /xbt on //acq/share doesn't exist" in caplog.text
