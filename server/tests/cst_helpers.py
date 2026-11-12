"""A collection system transfer worker set up for tests (#510)."""

from unittest.mock import Mock

from server.workers import run_collection_system_transfer as cst_run

# A local-directory transfer with every option off, and credentials for every type
CST_DEFAULTS = {
    'collectionSystemTransferID': 3, 'name': 'SCS', 'longName': 'Shipboard Computer System',
    'transferType': 1, 'sourceDir': '/data', 'destDir': 'SCS',
    'includeFilter': '*', 'excludeFilter': '', 'ignoreFilter': '',
    'staleness': 0, 'useStartDate': 0, 'cruiseOrLowering': 0, 'syncFromSource': 0,
    'removeSourceFiles': 0, 'skipEmptyDirs': 0, 'skipEmptyFiles': 0, 'bandwidthLimit': 0,
    'enable': 1, 'localDirIsMountPoint': 0,
    'rsyncServer': 'host/module', 'rsyncUser': 'survey', 'rsyncPass': 'rsync-pw',
    'sshServer': 'host', 'sshUser': 'survey', 'sshUseKey': 0, 'sshPass': 'ssh-pw',
    'smbServer': '//nas/share', 'smbDomain': 'WG', 'smbUser': 'survey', 'smbPass': 'smb-pw',
    'ftpServer': 'ftp.example.org', 'ftpUser': 'survey', 'ftpPass': 'ftp-pw',
}


def make_worker(monkeypatch, fake_ovdm, warehouse, lowering_id=None, **cfg) -> cst_run.OVDMGearmanWorker:
    """Return a worker set up as ``_run_job()`` leaves it, for a transfer with *cfg*.

    Its ``ovdm`` is the ``fake_ovdm`` fixture; ``send_job_status`` is a
    ``Mock``. The source and destination directories are built from the
    config, as ``_run_job()`` does, and the data window is unbounded.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        fake_ovdm: The ``fake_ovdm`` fixture.
        warehouse: The ``warehouse`` fixture.
        lowering_id: The current lowering, or ``None``.
        cfg: Settings that differ from :data:`CST_DEFAULTS`.

    Returns:
        cst_run.OVDMGearmanWorker: The worker.
    """
    monkeypatch.setattr(cst_run, 'OpenVDM', lambda: fake_ovdm)
    worker = cst_run.OVDMGearmanWorker()
    worker.send_job_status = Mock()
    worker.collection_system_transfer = {**CST_DEFAULTS, **cfg}
    worker.cruise_id = warehouse.cruise_id
    worker.lowering_id = lowering_id
    worker.shipboard_data_warehouse_config = warehouse.config
    worker.cruise_dir = str(warehouse.cruise_dir)
    worker.source_dir = worker.build_source_dir()
    worker.dest_dir = worker.build_dest_dir() if worker.build_rel_dir() is not None else None
    worker.data_start_date = '1970/01/01 00:00'
    worker.data_end_date = '9999/12/31 23:59:59'
    worker.transfer_start_date = '20261022T100000Z'
    return worker
