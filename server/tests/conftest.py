"""Shared fixtures for OpenVDM's tests (#506).

- :func:`load_dist`: import a ``.py.dist`` file (a parser, plugin or ``bin/``
  script), which Python can't import by name.
- :func:`warehouse`: a temporary shipboard data warehouse with a cruise
  directory.
- :func:`fake_ovdm`: an ``OpenVDM`` stand-in whose methods are those of the
  real class, configured from ``openvdm.yaml.dist`` and the warehouse.
- :func:`fake_gearman`: a Gearman client that records submitted jobs and
  returns scripted results.

The code behind them is in :mod:`server.tests.helpers`, which tests import.
"""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable, Optional, Union
from unittest.mock import create_autospec

import pytest
import yaml

from server.lib.openvdm import OpenVDM
from server.tests.helpers import CONFIG_METHODS, ROOT, FakeGearmanClient, load_dist_file


@pytest.fixture
def load_dist(monkeypatch) -> Callable[..., ModuleType]:
    """Return a function that imports a ``.py.dist`` file as a module.

    e.g. ``gga = load_dist('server/plugins/parsers/gga_parser.py.dist')``.
    The module is removed from ``sys.modules`` after the test.
    """
    def register(key: str, module: ModuleType) -> None:
        monkeypatch.setitem(sys.modules, key, module)

    def load(path: Union[str, Path], name: Optional[str] = None) -> ModuleType:
        return load_dist_file(path, name, register=register)

    return load


@pytest.fixture
def warehouse(tmp_path) -> SimpleNamespace:
    """A temporary warehouse: its base directory, a cruise and its directory.

    Attributes: ``base_dir``, ``cruise_id`` (``TEST001``), ``cruise_dir``
    (created), ``lowering_base_dir`` (``Vehicle``), ``publicdata_dir``
    (created) and ``config``, the shipboard data warehouse config the API
    would return for them.
    """
    base_dir = tmp_path / 'CruiseData'
    cruise_id = 'TEST001'
    cruise_dir = base_dir / cruise_id
    cruise_dir.mkdir(parents=True)
    publicdata_dir = tmp_path / 'PublicData'
    publicdata_dir.mkdir()
    config = {
        'shipboardDataWarehouseIP': '127.0.0.1',
        'shipboardDataWarehouseBaseDir': str(base_dir),
        'shipboardDataWarehouseApacheDir': str(tmp_path / 'www'),
        'shipboardDataWarehouseUsername': 'survey',
        'shipboardDataWarehousePublicDataDir': str(publicdata_dir),
        'loweringDataBaseDir': 'Vehicle',
        'cruiseConfigFn': 'cruise_config.json',
        'cruiseDataURLPath': '/CruiseData',
        'loweringConfigFn': 'lowering_config.json',
        'dataDashboardManifestFn': 'manifest.json',
        'md5SummaryFn': 'md5_summary.txt',
        'md5SummaryMd5Fn': 'md5_summary.md5',
    }
    return SimpleNamespace(base_dir=base_dir, cruise_id=cruise_id, cruise_dir=cruise_dir,
                           lowering_base_dir='Vehicle', publicdata_dir=publicdata_dir, config=config)


@pytest.fixture
def fake_ovdm(warehouse):
    """An ``OpenVDM`` stand-in that makes no API or Gearman calls.

    Its methods are autospecced from the real class, so calling one that
    doesn't exist, or with the wrong arguments, fails. ``config`` is
    ``openvdm.yaml.dist``'s settings; change it per test.

    - The methods that only read ``config`` (:data:`CONFIG_METHODS`, e.g.
      ``get_gearman_server()``, ``get_vessel_config()``) run the real code
      on it.
    - ``get_shipboard_data_warehouse_config()`` and ``get_cruise_id()``
      return :func:`warehouse`'s.
    - Everything else returns a ``Mock`` unless a test sets it, and records
      its calls (e.g. ``send_msg``, ``set_idle_task``).
    """
    ovdm = create_autospec(OpenVDM, instance=True)
    with open(ROOT / 'server' / 'etc' / 'openvdm.yaml.dist', encoding='utf-8') as file:
        ovdm.config = yaml.safe_load(file)

    for name in CONFIG_METHODS:
        real = getattr(OpenVDM, name)
        getattr(ovdm, name).side_effect = lambda *args, _real=real, **kwargs: _real(ovdm, *args, **kwargs)
    ovdm.get_shipboard_data_warehouse_config.return_value = warehouse.config
    ovdm.get_cruise_id.return_value = warehouse.cruise_id
    return ovdm


@pytest.fixture
def fake_gearman(monkeypatch) -> FakeGearmanClient:
    """A :class:`FakeGearmanClient`, also returned by ``python3_gearman.GearmanClient()``.

    Code that makes its own client (``python3_gearman.GearmanClient([...])``)
    gets this one, so a test can script results and check the jobs either way.
    A module that imported the class by name (``from python3_gearman import
    GearmanClient``, as ``scheduler.py`` does) needs its own name patched too,
    e.g. ``monkeypatch.setattr(scheduler, 'GearmanClient', lambda servers: fake_gearman)``.
    """
    client = FakeGearmanClient()
    monkeypatch.setattr('python3_gearman.GearmanClient', lambda *args, **kwargs: client)
    return client
