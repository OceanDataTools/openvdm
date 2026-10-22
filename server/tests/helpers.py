"""Shared test helpers, used by conftest.py's fixtures and by tests (#506).

Tests import from here (``from server.tests.helpers import PASS``), not from
conftest.py, which pytest imports under its own name: importing it again
would make a second copy of everything in it.
"""

import importlib.machinery
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable, Dict, List, Optional, Union

from server.lib.openvdm import OpenVDM

ROOT = Path(__file__).resolve().parents[2]

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
