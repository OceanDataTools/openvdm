"""Tests for bin/db_backup_restore.py (#514 part 2).

The script backs up the OpenVDM database with ``mysqldump`` (OVDM_Messages
without its rows) and restores a backup with ``mysql``, using the database
credentials in ``www/app/Core/Config.php``. Its command line is in its
``__main__`` block, so the tests call its functions; ``mysqldump`` and
``mysql`` go to the ``fake_run`` fixture.
"""

import os
import stat

import pytest

CONFIG = """<?php
        define('DB_TYPE', 'mysql');
        define('DB_HOST', 'localhost');
        define('DB_NAME', 'openvdm');
        define('DB_USER', 'openvdmDBUser');
        define('DB_PASS', 's3cret pass');
"""
CREDS = {'host': 'localhost', 'name': 'openvdm', 'user': 'openvdmDBUser', 'password': 's3cret pass'}


@pytest.fixture
def db(load_dist):
    """The script module."""
    return load_dist('bin/db_backup_restore.py.dist', name='db_backup_restore')


@pytest.fixture
def config(tmp_path):
    path = tmp_path / 'Config.php'
    path.write_text(CONFIG)
    return path


# --- Credentials ----------------------------------------------------------------------

def test_load_credentials(db, config) -> None:
    """The database credentials come from Config.php's defines."""
    assert db._load_credentials(str(config)) == CREDS


def test_config_missing(db, tmp_path, caplog) -> None:
    """Without Config.php, the script exits 1, pointing at the installer."""
    with pytest.raises(SystemExit) as exc:
        db._load_credentials(str(tmp_path / 'Config.php'))
    assert exc.value.code == 1
    assert 'Config.php not found' in caplog.text and 'install script' in caplog.text


def test_config_incomplete(db, config, caplog) -> None:
    """A Config.php without a define the script needs exits 1, naming it."""
    config.write_text(CONFIG.replace("define('DB_PASS', 's3cret pass');", ''))
    with pytest.raises(SystemExit):
        db._load_credentials(str(config))
    assert 'Missing define(s)' in caplog.text and 'DB_PASS' in caplog.text


# --- Backup ---------------------------------------------------------------------------

def test_backup(db, fake_run, tmp_path, capsys) -> None:
    """The backup has every table's data except OVDM_Messages', whose structure is appended; the
    password goes in MYSQL_PWD, not on a command line; the folder is created."""
    fake_run.on('mysqldump', '--no-data', stdout='CREATE TABLE OVDM_Messages ...;\n')
    fake_run.on('mysqldump', '-h', stdout='-- the rest\nINSERT INTO OVDM_Tasks ...;\n')
    out = tmp_path / 'backups' / 'new'
    assert db.backup(str(out), CREDS) == 0
    data, structure = fake_run.commands()
    assert data == ['mysqldump', '-h', 'localhost', '-u', 'openvdmDBUser', 'openvdm',
                    '--ignore-table', 'openvdm.OVDM_Messages']
    assert structure == ['mysqldump', '--no-data', '-h', 'localhost', '-u', 'openvdmDBUser', 'openvdm', 'OVDM_Messages']
    assert all(call.kwargs['env']['MYSQL_PWD'] == 's3cret pass' for call in fake_run.calls)
    fake_run.assert_not_in_commands('s3cret')
    [backup] = out.iterdir()
    assert backup.name.startswith('openvdm_') and backup.suffix == '.sql'
    assert backup.read_text() == '-- the rest\nINSERT INTO OVDM_Tasks ...;\n\nCREATE TABLE OVDM_Messages ...;\n'
    assert f'Backup saved to: {backup}' in capsys.readouterr().out


@pytest.mark.parametrize('failing, message', [('-h', 'mysqldump failed: Access denied'),
                                              ('--no-data', 'mysqldump (structure-only) failed: Access denied')])
def test_backup_dump_fails(db, fake_run, tmp_path, caplog, failing, message) -> None:
    """A failed mysqldump fails the backup, with its error; no file is written."""
    fake_run.on('mysqldump', failing, returncode=2, stderr='Access denied\n')
    assert db.backup(str(tmp_path), CREDS) == 1
    assert message in caplog.text
    assert list(tmp_path.iterdir()) == []


def test_backup_no_mysqldump(db, fake_run, tmp_path, caplog) -> None:
    """Without mysqldump, the backup fails saying so."""
    fake_run.on('mysqldump', raises=FileNotFoundError(2, 'No such file'))
    assert db.backup(str(tmp_path), CREDS) == 1
    assert 'mysqldump not found' in caplog.text


def test_backup_cant_write(db, fake_run, tmp_path, caplog, monkeypatch) -> None:
    """If the backup file can't be written, the backup fails."""
    real_open = open

    def refuse(path, *args, **kwargs):
        if str(path).endswith('.sql'):
            raise PermissionError(13, 'Permission denied')
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr('builtins.open', refuse)
    assert db.backup(str(tmp_path), CREDS) == 1
    assert 'Failed to write backup file' in caplog.text


# --- Restore --------------------------------------------------------------------------

def test_restore(db, fake_run, tmp_path, capsys) -> None:
    """A backup is piped into mysql, with the password in MYSQL_PWD."""
    backup = tmp_path / 'openvdm_20261023_120000.sql'
    backup.write_text('-- dump\n')
    seen = []
    fake_run.on('mysql', effect=lambda cmd, kwargs: seen.append(kwargs['stdin'].read()))
    assert db.restore(str(backup), CREDS, str(tmp_path)) == 0
    assert fake_run.commands() == [['mysql', '-h', 'localhost', '-u', 'openvdmDBUser', 'openvdm']]
    assert seen == ['-- dump\n'] and fake_run.calls[0].kwargs['env']['MYSQL_PWD'] == 's3cret pass'
    assert f'Database restored from: {backup}' in capsys.readouterr().out


def test_restore_missing_file(db, fake_run, tmp_path, caplog) -> None:
    """A backup file that doesn't exist fails the restore; mysql isn't run."""
    assert db.restore(str(tmp_path / 'nope.sql'), CREDS, str(tmp_path)) == 1
    assert 'Backup file not found' in caplog.text and fake_run.calls == []


@pytest.mark.parametrize('raises, message', [(None, 'mysql restore failed: ERROR 1045'),
                                             (FileNotFoundError(2, 'No such file'), 'mysql client not found')])
def test_restore_fails(db, fake_run, tmp_path, caplog, raises, message) -> None:
    """A failed or missing mysql fails the restore."""
    backup = tmp_path / 'b.sql'
    backup.write_text('-- dump\n')
    fake_run.on('mysql', returncode=1, stderr='ERROR 1045\n', raises=raises)
    assert db.restore(str(backup), CREDS, str(tmp_path)) == 1
    assert message in caplog.text


def _backups(tmp_path):
    for name in ('openvdm_20261021_000000.sql', 'openvdm_20261023_000000.sql', 'notes.txt'):
        (tmp_path / name).write_text(f'-- {name}\n')


def test_choose_backup(db, fake_run, tmp_path, monkeypatch, capsys) -> None:
    """Without a file, the backups are listed newest first and the one chosen is restored."""
    _backups(tmp_path)
    monkeypatch.setattr('builtins.input', lambda prompt: '2')
    assert db.restore(None, CREDS, str(tmp_path)) == 0
    out = capsys.readouterr().out
    assert '1) openvdm_20261023_000000.sql' in out and '2) openvdm_20261021_000000.sql' in out
    assert 'notes.txt' not in out
    assert f"Database restored from: {tmp_path / 'openvdm_20261021_000000.sql'}" in out


@pytest.mark.parametrize('answer, code, message', [('0', 0, 'Cancelled.'), ('7', 1, 'Invalid selection'),
                                                   ('x', 1, 'Invalid selection'), (EOFError(), 1, 'Invalid selection'),
                                                   (KeyboardInterrupt(), 1, 'Aborted.')])
def test_choose_backup_cancelled(db, fake_run, tmp_path, monkeypatch, capsys, answer, code, message) -> None:
    """Cancelling, or an answer that isn't a backup, exits without restoring."""
    _backups(tmp_path)

    def ask(prompt):
        if isinstance(answer, BaseException):
            raise answer
        return answer
    monkeypatch.setattr('builtins.input', ask)
    with pytest.raises(SystemExit) as exc:
        db.restore(None, CREDS, str(tmp_path))
    assert exc.value.code == code and message in capsys.readouterr().out
    assert fake_run.calls == []


def test_choose_backup_none(db, tmp_path, caplog) -> None:
    """With no backups to choose from, the script exits 1."""
    with pytest.raises(SystemExit) as exc:
        db.restore(None, CREDS, str(tmp_path / 'missing'))
    assert exc.value.code == 1 and 'No backup files found' in caplog.text


# --- Bugs -----------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="the backup is written with the default umask (#603)")
def test_backup_not_world_readable(db, fake_run, tmp_path) -> None:
    """The backup (which has the transfers' passwords) is readable only by its owner."""
    old = os.umask(0o022)
    try:
        assert db.backup(str(tmp_path), CREDS) == 0
    finally:
        os.umask(old)
    [backup] = tmp_path.iterdir()
    assert stat.S_IMODE(backup.stat().st_mode) & 0o077 == 0
