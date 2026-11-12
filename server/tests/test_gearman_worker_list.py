"""Tests that the web pages' list of worker functions matches the workers (#503).

``Helpers\\GearmanStatus::WORKERS`` lists the Gearman functions each worker
registers, by its Supervisor program, so the Configuration page can warn
about workers that aren't running. These tests read the workers'
``register_task()`` calls and check the list against them.
"""

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKERS_DIR = ROOT / 'server' / 'workers'
GEARMAN_STATUS = ROOT / 'www' / 'app' / 'Helpers' / 'GearmanStatus.php'

REGISTER_TASK = re.compile(
    r"register_task\(\s*(?:TASK_NAMES\[['\"](\w+)['\"]\]|TASK_NAMES\.get\(['\"](\w+)['\"]\)|['\"](\w+)['\"])")


def _registered() -> dict:
    """Return the functions each worker registers, by worker (file) name."""
    registered = {}
    for path in sorted(WORKERS_DIR.glob('*.py')):
        calls = REGISTER_TASK.findall(path.read_text(encoding='utf-8'))
        if not calls:
            continue
        task_names = getattr(importlib.import_module(f'server.workers.{path.stem}'), 'TASK_NAMES', {})
        registered[path.stem] = sorted(task_names[key or get_key] if (key or get_key) else literal
                                       for key, get_key, literal in calls)
    return registered


def _listed() -> dict:
    """Return GearmanStatus::WORKERS, by Supervisor program."""
    text = GEARMAN_STATUS.read_text(encoding='utf-8')
    block = re.search(r"const WORKERS = array\((.*?)\n    \);", text, re.S).group(1)
    return {program: sorted(re.findall(r"'(\w+)'", functions))
            for program, functions in re.findall(r"'(\w+)' => array\((.*?)\)", block, re.S)}


def test_every_worker_is_listed_with_its_functions() -> None:
    """Each worker's functions are listed under its name, which is its Supervisor program."""
    assert _listed() == _registered()


def test_listed_programs_are_supervisor_programs() -> None:
    """The names are the installer's Supervisor programs, as the warning tells users to check."""
    installer = (ROOT / 'utils' / 'install-openvdm.sh').read_text(encoding='utf-8')
    programs = set(re.findall(r'^\[program:(\w+)\]', installer, re.M))
    missing = set(_listed()) - programs
    assert not missing


@pytest.mark.parametrize('call, expected', [
    ("register_task(TASK_NAMES['CREATE_CRUISE'], f)", ('CREATE_CRUISE', '', '')),
    ("register_task(TASK_NAMES.get('SYNC'), f)", ('', 'SYNC', '')),
    ('register_task("stopJob", task_stop_job)', ('', '', 'stopJob')),
])
def test_register_task_forms(call, expected) -> None:
    """The three ways workers name their functions are all read."""
    assert REGISTER_TASK.findall(call) == [expected]
