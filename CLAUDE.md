# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenVDM is a ship-wide data management platform for research vessels. It retrieves and organizes files from multiple instrument/data acquisition systems into a unified cruise data package, with web-based access and a plugin architecture for custom data processing.

## Architecture

OpenVDM is a 3-tier distributed system:

**Tier 1 — Web Frontend (PHP + JavaScript)**
- Location: `www/`
- Framework: custom `simple-mvc-framework` (Composer-managed)
- Controllers: `www/app/Controllers/` — split between `Api/` (REST endpoints) and `Config/` (admin UI)
- Models: `www/app/Models/` — `Config/`, `Api/`, `TransferLogs/`, `Warehouse/`
- Routes: `www/app/Core/routes.php`
- Views/templates: `www/app/views/` and `www/app/templates/`
- JS dependencies (Bootstrap, Chart.js, Leaflet, DataTables, Luxon, jQuery) managed via `package.json`

**Tier 2 — Python Backend**
- Location: `server/`
- Core API wrapper: `server/lib/openvdm.py` — primary interface to the MySQL database via the web API
- Connection utilities: `server/lib/connection_utils.py` — handles local, rsync, SMB, SSH, and rclone transfers
- Plugin base classes: `server/lib/openvdm_plugin.py` — `OpenVDMPlugin` and `OpenVDMParserQualityTest`
- File utilities: `server/lib/file_utils.py`, `server/lib/geojson_utils.py`

**Tier 3 — Gearman Workers (async task queue)**
- Location: `server/workers/`
- Each worker registers one or more Gearman task handlers (e.g. `runCollectionSystemTransfer`, `updateDataDashboard`, `setupNewCruise`)
- Key workers: `run_collection_system_transfer.py`, `run_cruise_data_transfer.py`, `run_ship_to_shore_transfer.py`, `data_dashboard.py`, `md5_summary.py`, `cruise.py`, `lowering.py`, `scheduler.py`
- Workers are managed by Supervisor in production

**Plugin System**
- Location: `server/plugins/`
- Plugins have suffix `_plugin.py` (configurable in `server/etc/openvdm.yaml`)
- Parsers live in `server/plugins/parsers/`
- Plugins subclass `OpenVDMPlugin` from `server/lib/openvdm_plugin.py`

**Configuration**
- Server config: `server/etc/openvdm.yaml` (copy from `openvdm.yaml.dist`)
- Web config: `www/app/Core/Config.php` (copy from `Config.php.dist`)
- Hooks in `openvdm.yaml` map Gearman task names to downstream tasks; `postHookCommands` run shell commands after task completion

## Development Setup

Python (use virtual environment at `./venv/`):
```bash
source ./venv/bin/activate
pip install -r requirements.txt
```

PHP dependencies:
```bash
cd www/
composer install
bash ./post_composer.sh
```

JavaScript dependencies:
```bash
cd www/
npm install
```

## Common Commands

**Run tests** (required before submitting PRs):
```bash
./manage.py test
```

**Run a specific worker test file:**
```bash
source ./venv/bin/activate
python -m pytest server/workers/test_collection_system_transfer.py
```

**Lint Python code:**
```bash
pylint server/
ruff check --fix server/
```

**Run pre-commit checks:**
```bash
pre-commit run --all-files
```

## Code Style

- **Python**: PEP8, 100-character line limit, use `pylint` and `ruff` (configured in `.pylintrc` and `ruff.toml`)
- **JavaScript**: JavaScript Standard Style
- **PHP**: follows existing MVC conventions in `www/app/`
- Ruff is configured to auto-fix on commit via `.pre-commit-config.yaml`

### Python documentation standard

All Python files (including `.py.dist` templates) must use **pdoc-compatible inline documentation**:

- Every module must have a concise summary line as the first sentence of its module docstring, followed by a blank line and any extended description. pdoc uses the summary line as the module's one-line description in index pages.
- Every public class, function, and method must have a docstring.
- Use **Google-style** docstrings with `Args:`, `Returns:`, `Raises:`, and `Attributes:` sections where applicable.
- Include Python type annotations on function signatures; this allows pdoc to render types without duplicating them in the docstring.
- The legacy `FILE: / DESCRIPTION: / AUTHOR: / REVISION:` header block must **not** be used — replace it with a proper module docstring.
- Private helpers (names starting with `_`) should have docstrings when their purpose is non-obvious.

## Testing

### Known false-positive pytest errors

`test_cst_source`, `test_cdt_destination`, and `test_cdt_rclone_destination` in `server/lib/connection_utils.py` are **not pytest tests** — they are OpenVDM connection-testing functions whose names happen to match pytest's default collection pattern. pytest will report them as errors (missing fixture) when running the full suite. These errors are pre-existing and expected; they do not indicate a regression.

## Git Workflow

- `master` — production releases
- `dev` — integration branch (PRs target `dev`, not `master`)
- Feature/fix branches use naming convention `issue_NNN`
- Run `./manage.py test` before opening a PR

## Supported Transfer Methods

The `connection_utils.py` module handles five transfer types: local directory, rsync server, SMB (Samba) share, SSH server, and rclone (cloud storage). Transfer type logic branches on these in workers.

### connection_utils.py return conventions

Low-level connection test functions (`mount_smb_share`, `detect_smb_version`, `test_rsync_connection`, `test_rsync_write_access`, `test_ssh_connection`, `test_ssh_remote_directory`, `test_ssh_write_access`) return `(bool, str)` tuples — success flag plus stderr detail. The higher-level functions (`test_cst_source`, `test_cdt_destination`, `test_smb_destination`) return `list[dict]` with `partName`/`result`/`reason` keys. Maintain this distinction when adding new connection tests.

### rclone destination convention

A `:` character in a destination directory field signals an rclone remote path (`remote:path` format). This affects path normalization (no leading slash on the remote name) and UI behavior in the form helpers. Relevant to `run_cruise_data_transfer.py`, `run_ship_to_shore_transfer.py`, and the CDT/SSDW form helpers.

### CDT destDir semantics

For cruise data transfers, `destDir` interpretation depends on transfer type:
- **Local Directory, no `:`** — absolute path on the local filesystem (leading `/` required)
- **Local Directory, contains `:`** — rclone `remote:path` (no leading slash on remote name)
- **All other transfer types** — relative path within the cruise directory (no leading slash)

## Database

- MySQL; schema: `database/openvdm_db.sql`
- Migration scripts for version upgrades are in `database/`
- The Python backend communicates with MySQL exclusively through the PHP REST API (via `server/lib/openvdm.py`), not via direct DB connections
