"""Tests for utils/update_md5_summary.py (#514).

The script queues an MD5 summary update for files hook commands and tools
write into the cruise directory (#373), with ``OpenVDM.update_md5_summary()``
(tested in ``test_openvdm_api.py``).
"""

import sys

import pytest


@pytest.fixture
def run(load_dist, monkeypatch, fake_ovdm):
    """Return a function that runs the script's main() with *args*; returns its exit status."""
    module = load_dist('utils/update_md5_summary.py', name='update_md5_summary_util')
    monkeypatch.setattr(module, 'OpenVDM', lambda: fake_ovdm)

    def run_script(*args):
        monkeypatch.setattr(sys, 'argv', ['update_md5_summary.py', *args])
        try:
            return module.main()
        except SystemExit as exc:
            return exc.code
    return run_script


def test_queue(run, fake_ovdm) -> None:
    """The files are queued as updated, in the background, for the current cruise."""
    assert run('Products/report.pdf', 'Products/plot.png') == 0
    fake_ovdm.update_md5_summary.assert_called_once_with(
        updated=['Products/report.pdf', 'Products/plot.png'], deleted=[], cruise_id=None, background=True)


def test_options(run, fake_ovdm) -> None:
    """--deleted, -c and --wait."""
    assert run('-v', 'new.txt', '--deleted', 'old.txt', 'older.txt', '-c', 'RR2601', '--wait') == 0
    fake_ovdm.update_md5_summary.assert_called_once_with(
        updated=['new.txt'], deleted=['old.txt', 'older.txt'], cruise_id='RR2601', background=False)


def test_only_deleted(run, fake_ovdm) -> None:
    """Deleted files on their own are enough."""
    assert run('--deleted', 'old.txt') == 0


def test_no_files(run, fake_ovdm, capsys) -> None:
    """Without files, it's a usage error (exit 2)."""
    assert run() == 2
    assert 'no files given' in capsys.readouterr().err
    fake_ovdm.update_md5_summary.assert_not_called()


def test_fails(run, fake_ovdm, capsys) -> None:
    """If the update can't be queued (e.g. a path outside the cruise), it exits 1 with the reason."""
    fake_ovdm.update_md5_summary.side_effect = ValueError('/etc/passwd is not in the cruise directory /data/RR2601')
    assert run('/etc/passwd') == 1
    assert capsys.readouterr().err == \
        'Unable to queue the MD5 summary update: /etc/passwd is not in the cruise directory /data/RR2601\n'
