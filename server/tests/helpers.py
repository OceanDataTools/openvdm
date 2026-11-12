"""Shared test helpers, used by conftest.py's fixtures and by tests (#506).

Tests import from here (``from server.tests.helpers import PASS``), not from
conftest.py, which pytest imports under its own name: importing it again
would make a second copy of everything in it.
"""

import importlib.machinery
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable, Dict, List, Optional, Union

from server.lib.openvdm import OpenVDM

ROOT = Path(__file__).resolve().parents[2]

# The parsers' test inputs, and their expected output in expected/ (#513)
PARSER_DATA = ROOT / 'server' / 'tests' / 'data' / 'parsers'

# A job result that passes, as the workers return them
PASS = json.dumps({'parts': [{'partName': 'Done', 'result': 'Pass'}]})


def load_dist_file(path: Union[str, Path], name: Optional[str] = None,
               register: Optional[Callable[[str, ModuleType], None]] = None) -> ModuleType:
    """Import a ``.py.dist`` file as a module.

    Args:
        path: The file, absolute or relative to the repository root.
        name: The module name; by default the file name without
            ``.py.dist``, prefixed with ``dist_`` so it can't clash with a
            real module.
        register: Adds the module to ``sys.modules`` before it runs (some
            code looks itself up there); by default it's set directly.

    Returns:
        ModuleType: The module.
    """
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    name = name or 'dist_' + path.name.removesuffix('.py.dist')
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    (register or sys.modules.__setitem__)(name, module)
    loader.exec_module(module)
    return module


def _reads_config_only(method) -> bool:
    """Whether an ``OpenVDM`` method only reads ``self.config``: no API or Gearman calls."""
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    return 'self.config' in source and not any(
        call in source for call in ('requests.', 'python3_gearman', 'self.get_', 'self._'))


# The OpenVDM methods the fake runs for real, since they only read its config
CONFIG_METHODS = sorted(name for name, method in inspect.getmembers(OpenVDM, inspect.isfunction)
                        if not name.startswith('_') and name != 'read_config' and _reads_config_only(method))


class FakeGearmanClient:
    """A ``python3_gearman.GearmanClient`` that runs nothing.

    Every submitted job is recorded in :attr:`jobs` as ``(task, data)``,
    with ``data`` decoded from JSON when it is JSON. Each job's result is
    :data:`PASS` unless :attr:`results` scripts it: by task name, a string
    result, a list of results returned in turn, or a callable taking the
    decoded data.

    Attributes:
        jobs: The submitted jobs, in order.
        results: Scripted results by task name.
    """

    def __init__(self, host_list: Optional[List[str]] = None) -> None:
        self.host_list = host_list
        self.jobs: List[tuple] = []
        self.results: Dict[str, Union[str, list, Callable]] = {}

    def _result(self, task: str, data) -> Optional[str]:
        scripted = self.results.get(task, PASS)
        if callable(scripted):
            return scripted(data)
        if isinstance(scripted, list):
            return scripted.pop(0)
        return scripted

    def _request(self, task: str, raw) -> SimpleNamespace:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = raw
        self.jobs.append((task, data))
        return SimpleNamespace(result=self._result(task, data), complete=True, timed_out=False,
                               state='COMPLETE', job=SimpleNamespace(task=task, data=raw, unique=None))

    def submit_job(self, task: str, data, **_kwargs) -> SimpleNamespace:
        """Record a job and return its request, already complete."""
        return self._request(task, data)

    def submit_multiple_jobs(self, jobs: List[dict], **_kwargs) -> List[SimpleNamespace]:
        """Record several jobs (``{'task': ..., 'data': ...}``) and return their requests."""
        return [self._request(job['task'], job['data']) for job in jobs]

    def wait_until_jobs_completed(self, requests: list, **_kwargs) -> list:
        """Return the requests, which are complete already."""
        return requests

    def tasks(self) -> List[str]:
        """Return the task names of the submitted jobs, in order."""
        return [task for task, _ in self.jobs]


class FakeRun:
    """A ``subprocess.run`` that runs nothing, for code that shells out (#508).

    Each call is recorded in :attr:`calls` with its command, its keyword
    arguments and the contents of any file the command names (a path
    argument, or one after ``=``, e.g. ``--password-file=``,
    ``credentials=``), read when the command runs: the credentials and
    password files OpenVDM writes are deleted right after.

    Results come from rules added with :meth:`on`, matched on the
    command's first arguments, the most recently added first; a command no
    rule matches succeeds with no output. As ``subprocess.run`` does, a
    failing result raises ``CalledProcessError`` when the call passed
    ``check=True``.

    Attributes:
        calls: The recorded calls (``cmd``, ``kwargs``, ``files``), in order.
    """

    def __init__(self) -> None:
        self.calls: List[SimpleNamespace] = []
        self._rules: List[tuple] = []

    def on(self, *prefix: str, returncode: int = 0, stdout: str = '', stderr: str = '',  # pylint: disable=too-many-arguments
           raises: Optional[BaseException] = None,
           effect: Optional[Callable[[list, dict], None]] = None) -> 'FakeRun':
        """Script the result of commands starting with *prefix*.

        Args:
            prefix: The command's first arguments, e.g. ``'rclone', 'lsjson'``.
            returncode: The exit status.
            stdout: Its output.
            stderr: Its error output.
            raises: An exception to raise instead, e.g. ``FileNotFoundError()``
                for a command that isn't installed.
            effect: Called with the command and keyword arguments before the
                result is returned, e.g. to write to a file the command was
                given.

        Returns:
            FakeRun: This object, so calls can be chained.
        """
        self._rules.append((list(prefix), SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=stderr, raises=raises, effect=effect)))
        return self

    @staticmethod
    def _files(cmd: list) -> Dict[str, str]:
        """Read the small files a command names."""
        files = {}
        for path in re.findall(r'(/[^\s,=]+)', ' '.join(str(arg) for arg in cmd)):
            if os.path.isfile(path) and os.path.getsize(path) < 65536:
                with open(path, encoding='utf-8', errors='replace') as file:
                    files[path] = file.read()
        return files

    def __call__(self, cmd, **kwargs) -> subprocess.CompletedProcess:
        cmd = [str(arg) for arg in cmd]
        self.calls.append(SimpleNamespace(cmd=cmd, kwargs=kwargs, files=self._files(cmd)))
        result = SimpleNamespace(returncode=0, stdout='', stderr='', raises=None, effect=None)
        for prefix, scripted in reversed(self._rules):
            if cmd[:len(prefix)] == prefix:
                result = scripted
                break
        if result.effect:
            result.effect(cmd, kwargs)
        if result.raises is not None:
            raise result.raises
        if kwargs.get('check') and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout,
                                                stderr=result.stderr)
        return subprocess.CompletedProcess(cmd, result.returncode, result.stdout, result.stderr)

    def commands(self, *prefix: str) -> List[list]:
        """Return the recorded commands, or only those starting with *prefix*."""
        return [call.cmd for call in self.calls if call.cmd[:len(prefix)] == list(prefix)]

    def assert_not_in_commands(self, secret: str) -> None:
        """Fail if *secret* (e.g. a password) is part of any recorded command."""
        for call in self.calls:
            assert not any(secret in arg for arg in call.cmd), f"{secret!r} in {call.cmd}"


def gnu_rsync() -> bool:
    """Whether ``rsync`` is GNU rsync 3, which end-to-end transfer tests need.

    macOS ships openrsync, whose options and output differ; CI and the
    ships' servers have GNU rsync (#510).
    """
    try:
        output = subprocess.run(['rsync', '--version'], capture_output=True, text=True, check=False).stdout
    except OSError:
        return False
    return output.startswith('rsync  version 3')


def parse_output(parser, path) -> Optional[dict]:
    """Return a parser's output for *path*, as the data dashboard saves it (#513).

    Args:
        parser: The parser.
        path: The file to parse.

    Returns:
        dict | None: The parsed ``to_json()``: ``None`` if the parser produced
        no data.
    """
    parser.parse(str(path))
    return json.loads(parser.to_json())


def stat_value(data: dict, name: str):
    """Return the value of the stat called *name* in a parser's output (#513)."""
    return next(stat['statValue'] for stat in data['stats'] if stat['statName'] == name)


def check_expected(name: str, actual, update: bool = False) -> None:
    """Compare a parser's output with its saved expected output (#513).

    Args:
        name: The expected output's name: ``PARSER_DATA/expected/<name>.json``.
        actual: The parser's output, as ``get_plugin_data()`` returns it.
        update: Save *actual* as the expected output instead, for a change to
            a parser's output that's intended (``pytest --update-expected``),
            so the change shows in the diff.

    Raises:
        AssertionError: If *actual* differs from the expected output, or
            there's none saved.
    """
    path = PARSER_DATA / 'expected' / f'{name}.json'
    actual = json.loads(json.dumps(actual))  # as saved: tuples become lists
    if update:
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(actual, indent=2) + '\n', encoding='utf-8')
        return
    assert path.exists(), f"No expected output {path.name}: run pytest with --update-expected"
    assert actual == json.loads(path.read_text(encoding='utf-8')), \
        f"Output differs from {path.name}; if that's intended, run pytest with --update-expected"
