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
- Core API wrapper: `server/lib/openvdm.py` — primary interface to the MySQL database via the web API. Code that writes files into the cruise directory outside a transfer or data dashboard job queues their MD5 summary update with `OpenVDM.update_md5_summary()` (`utils/update_md5_summary.py` from the shell, #373)
- Connection utilities: `server/lib/connection_utils.py` — handles local, rsync, SMB, SSH, FTP, and rclone transfers
- Plugin base classes: `server/lib/openvdm_plugin.py` — `OpenVDMPlugin` and `OpenVDMParserQualityTest`
- File utilities: `server/lib/file_utils.py`, `server/lib/geojson_utils.py`
- Transfer commands: `server/lib/transfer_utils.py` — `run_transfer_command()` runs rsync/rclone for all transfer workers, collects new/updated/deleted files (rsync `-i`, rclone `-v`) and raises `TransferCommandError` on failure (rsync codes 24, and 23 for vanished listed files, count as success); callers must turn that into a failed transfer (#230)

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
- `openvdm.yaml`'s `vessel` block (name, contact, optional `r2r` IDs) is set by the installer and read with `OpenVDM.get_vessel_config()`; the cruise worker copies it into each `ovdmConfig.json` (#365)

## Development Setup

Python (use virtual environment at `./venv/`):
```bash
source ./venv/bin/activate
pip install -r requirements.txt
```

PHP dependencies:
```bash
cd www/
composer install            # includes PHPStan; production installs use --no-dev
bash ./post_composer.sh
```

JavaScript dependencies:
```bash
cd www/
npm install
```

## Common Commands

**Checks to run before submitting a PR:**
```bash
source ./venv/bin/activate
python -m pytest server                  # only the known false-positive errors are expected (see Testing)
ruff check server/
pre-commit run --all-files               # ruff, ESLint, php -l and PHPStan
```

There is no automated test suite for the PHP or JavaScript. Changes to the web UI need a manual check in a browser.

**Lint Python code:**
```bash
pylint server/
ruff check --fix server/
```

**Lint JavaScript** (ESLint via pre-commit; config in `eslint.config.mjs`):
```bash
pre-commit run eslint --all-files
```

**Generate Python API docs** (pdoc, not in `requirements.txt`; install it in a separate venv along with the requirements):
```bash
PYTHONPATH=. pdoc -d google -o <output_dir> server.lib server.workers
```
`-d google` renders the `Args:`/`Returns:` sections; `PYTHONPATH=.` lets pdoc import the `server` package. The `.py.dist` templates in `bin/` and `server/plugins/` aren't importable modules, so pdoc doesn't cover them.

**Analyse PHP** (PHPStan, a Composer dev dependency; config in `www/phpstan.neon`):
```bash
cd www/
vendor/bin/phpstan analyse
# after fixing a finding listed in phpstan-baseline.neon:
vendor/bin/phpstan analyse --generate-baseline phpstan-baseline.neon
```

## Code Style

- **Python**: PEP8, 100-character line limit, use `pylint` and `ruff` (configured in `.pylintrc` and `ruff.toml`)
- **JavaScript**: match the existing code: 4-space indentation, semicolons, `var`, and page scripts wrapped in jQuery `$(function () { ... })`. ESLint (`eslint.config.mjs`) checks for bugs only (undefined names, unused and duplicate variables, unreachable code), not formatting. Variables defined outside the file being linted (libraries, the inline `<script>` in `templates/default/footer.php`, helpers such as `mapBaseLayers.js`) must be listed in the config's globals; a script that defines a helper for other files marks it with `/* exported name */`.
- **PHP**: follows existing MVC conventions in `www/app/`. PHPStan runs at level 1 with a baseline (`www/phpstan-baseline.neon`) of the findings that existed when it was added (#130); new code must not add to it. `www/phpstan-bootstrap.php` declares the `Config.php.dist` constants. Views get `$data`/`$error` from `Core\View::render()`, so those are ignored in `app/views` and `app/templates`. Type class properties (e.g. `private \Models\Warehouse $_warehouseModel;`) so PHPStan can check method calls on them, and declare every property (dynamic properties are deprecated in PHP 8.2+).
- Ruff (auto-fix), ESLint, a `php -l` syntax check and PHPStan run on commit via `.pre-commit-config.yaml`. The PHP checks use the locally installed `php` (8.3 matches production) and are skipped with a message if PHP or PHPStan (`composer install` in `www/`) isn't installed.

### Python documentation standard

All Python files (including `.py.dist` templates) must use **pdoc-compatible inline documentation**:

- Every module must have a concise summary line as the first sentence of its module docstring, followed by a blank line and any extended description. pdoc uses the summary line as the module's one-line description in index pages.
- Every public class, function, and method must have a docstring.
- Use **Google-style** docstrings with `Args:`, `Returns:`, `Raises:`, and `Attributes:` sections where applicable.
- Include Python type annotations on function signatures; this allows pdoc to render types without duplicating them in the docstring.
- The legacy `FILE: / DESCRIPTION: / AUTHOR: / REVISION:` header block must **not** be used — replace it with a proper module docstring.
- Private helpers (names starting with `_`) should have docstrings when their purpose is non-obvious.

**What's required now vs. what's a goal.** All of the above is required for new code and for functions you change. For existing code the state is:

- Module docstrings (no legacy headers) and a docstring on every public class/function/method: done across `server/` (#141, #143). Keep it that way.
- Google-style `Args:`/`Returns:`/`Raises:` sections: complete for `server/lib/` (#144), which is the API used by workers and site plugins. Workers and parsers still have many short docstrings without sections; add sections when you touch a function.
- Type annotations: a goal only. Most existing functions have none, and nothing checks them. Add them in new code; don't mass-annotate existing code until a type checker (mypy/pyright) is run on it, since unchecked annotations can be wrong without anyone noticing.

**Parsers and plugins** (`server/plugins/parsers/*_parser.py.dist`, `server/plugins/*_plugin.py.dist`) follow a lighter, uniform form (issue #141):

- Module docstring: a summary line, then one paragraph. For parsers: `"""Parser for <instrument / data type>.` followed by `Parses <file format and contents> and returns the JSON-formatted plugin data used by OpenVDM's Data Dashboard.` Plugins use `Plugin for <system>.` and say what they dispatch to.
- Don't repeat command-line usage/options (argparse `--help` is authoritative) or `requirements.txt` packages. Do mention dependencies that `requirements.txt` doesn't install (e.g. GDAL command-line tools).
- A one-line docstring is enough for `parse()`/`process_file()`/`parse_file()` and other methods whose only argument is `filepath`, e.g. `"""Parse the DBS file and populate the plugin data."""`. Say "return plugin data dict" only if the method actually returns it.
- Methods with other parameters, including constructors that add parser-specific options and `add_cli_arguments()`, get Google-style `Args:` (and `Returns:`/`Raises:` where applicable). Constructors that only take the standard `OpenVDMCSVParser` options don't need a docstring.

## Testing

### Known false-positive pytest errors

`test_cst_source`, `test_cdt_destination`, and `test_cdt_rclone_destination` in `server/lib/connection_utils.py` are **not pytest tests** — they are OpenVDM connection-testing functions whose names happen to match pytest's default collection pattern. pytest will report them as errors (missing fixture) when running the full suite. These errors are pre-existing and expected; they do not indicate a regression.

## Git Workflow

- `master` — production releases
- `dev` — integration branch (PRs target `dev`, not `master`)
- Feature/fix branches use naming convention `issue_NNN`
- Run the checks under **Common Commands** before opening a PR

## Supported Transfer Methods

The `connection_utils.py` module handles six transfer types: local directory, rsync server, SMB (Samba) share, SSH server, FTP server, and rclone (cloud storage). Transfer type logic branches on these in workers.

`OVDM_TransferTypes` is shared by collection system and cruise data transfers; both support all five types. The CDT controller's `UNSUPPORTED_TRANSFER_TYPES` can hide a type from the CDT form and reject it on submit (#210); it's empty since FTP destinations were added (#199). The FTP form rules (`Helpers\FtpFields`: validation and the #211 password rule) are shared by both controllers. `Helpers\TransferFields` lists each type's connection fields; both controllers' add/edit handlers blank the other types' fields with `clearOthers()` on the data they save or send to Test Setup (#243), so a new type's fields only need adding there.

### FTP transfers

FTP **destinations** (cruise data transfers, #199) work like SSH destinations: the transfer writes a temporary rclone remote (`prepare_ftp_config()`), creates `<destDir>/<cruiseID>` with `rclone mkdir`, and copies or syncs with rclone; no mount. Test Setup (`test_cdt_destination()`) checks the login, the destination directory and write access (`test_ftp_write_access()`).

FTP **sources** (collection system transfers):

FTP sources (#17) are mounted with `rclone mount` (FUSE, `fuse3`) in the transfer's temporary directory, and rsync copies from the mount point. Only the source directory (or a wildcard source's parent, `ftp_mount_base()`) is mounted, not the server root, which some accounts can't list; `mount_path()` maps a server path into the mount (#209). SMB shares are still mounted at their root, with `sourceDir` relative to the share. The FTP Server field is `host[:port]` (default 21; `[ipv6]:port`); there's no separate port column. `split_ftp_server()` parses it, and the CST controller's `_checkFtpFields()` validates it with the same rules (#224). Test Setup and the transfer share the setup steps `prepare_ftp_config()` (password available, rclone config written) and `prepare_ftp_mount()` (#214). `build_rclone_config_for_ftp()` writes the remote to a config file in the temporary directory (password obscured via stdin, never on the command line). The file list (and the staleness re-check) comes from one `rclone lsjson -R` call (`list_ftp_source()`), not from walking the mount: that avoids a `stat` per file over FTP, and `lsjson` fails on directories the server refuses to list, which the mount shows as empty (#208). `mount_ftp_source()` waits until the mount point is really mounted (older rclone returns early, #206), and must not read the daemonized rclone's output through a pipe (the daemon holds it open while mounted). Test functions for FTP stay in the `(bool, str)` style; `list_ftp_source()` returns `(bool, list | str)`.

### connection_utils.py return conventions

Low-level connection test functions (`mount_smb_share`, `detect_smb_version`, `test_rsync_connection`, `test_rsync_write_access`, `test_ssh_connection`, `test_ssh_remote_directory`, `test_ssh_write_access`, `test_ftp_connection`, `mount_ftp_source`) return `(bool, str)` tuples — success flag plus stderr detail. The higher-level functions (`test_cst_source`, `test_cdt_destination`, `test_smb_destination`) return `list[dict]` with `partName`/`result`/`reason` keys. Maintain this distinction when adding new connection tests.

### rclone destination convention

A `:` character in a destination directory field signals an rclone remote path (`remote:path` format). For cruise data transfers this only applies to the Local Directory type: the CDT form rejects a `:` in the destination directory of any other type, and the workers route Test Setup to `test_cdt_rclone_destination()` on the `:`, so don't relax that check without routing by transfer type. This affects path normalization (no leading slash on the remote name) and UI behavior in the form helpers. Relevant to `run_cruise_data_transfer.py`, `run_ship_to_shore_transfer.py`, and the CDT/SSDW form helpers.

### CDT destDir semantics

For cruise data transfers, `destDir` interpretation depends on transfer type:
- **Local Directory, no `:`** — absolute path on the local filesystem (leading `/` required)
- **Local Directory, contains `:`** — rclone `remote:path` (no leading slash on remote name)
- **SSH Server** — absolute path on the remote server (leading `/` required; used as `user@host:destDir/cruiseID`)
- **FTP Server** — absolute path on the FTP server (leading `/` required; used as `<remote>:destDir/cruiseID`)
- **Rsync / SMB** — path within the rsync module (part of the Rsync Server field) or SMB share (the form strips the leading and trailing slashes); `/` for its top level, which the form keeps (#247). Join rsync ones with `rsync_dest_path()` (#228)

## Database

- MySQL; schema: `database/openvdm_db.sql`
- Migration scripts for version upgrades are in `database/`
- The Python backend communicates with MySQL exclusively through the PHP REST API (via `server/lib/openvdm.py`), not via direct DB connections

## Security

### Password fields in edit forms

Edit forms for records with credentials (CST, CDT, Ship-to-Shore) must **not** pre-populate password inputs via `value=`. Embedding stored credentials in the HTML response exposes them in page source and browser dev tools.

Convention (established in issue #99):
- Render password inputs without a `value=` attribute; use `placeholder="(leave blank to keep existing)"`.
- In the Config controller's `edit()` handler, after reading password fields from `$_POST`, apply a fallback before validation: if the submitted value is empty and `$data['row'][0]->{field}` is non-empty, preserve the stored value. Apply this in both the `submit` and `inlineTest` branches.
- In error re-render blocks, do not assign password fields back to `$data['row'][0]`.
- A password typed before **Test Setup** is kept server-side (session) by `Helpers\PendingPasswords` (issue #119) so a later **Update** still applies it. In the CST/CDT `edit()` handlers, resolve passwords with `PendingPasswords::resolve()` (posted > remembered > stored; pass `$remember = true` only in the `inlineTest` branch), clear on successful update and on any non-POST page load, and expose only booleans (`PendingPasswords::flags()`) to the view for the placeholder text.

### REST API credential gating (shared-secret header)

The `Api/CollectionSystemTransfers`, `Api/CruiseDataTransfers` and `Api/Warehouse` (`getCruiseConfig`, `getLoweringConfig`) controllers strip transfer passwords from all responses unless the request includes a valid `X-Worker-Token` header. They all use `Helpers\TransferCredentials` (`forResponse()`), whose `FIELDS` constant is the one list of password fields (`rsyncPass`, `smbPass`, `sshPass`, `ftpPass`); `PendingPasswords` uses the same list. A new transfer type's password field only needs adding there (#205).

- The expected token is `WORKER_API_KEY` defined in `www/app/Core/Config.php`.
- The same value must be set as `workerApiKey` in `server/etc/openvdm.yaml`.
- Python workers send the header automatically via `OpenVDM._worker_headers()`, which reads the key from the YAML config.
- `hash_equals()` is used for the comparison to prevent timing attacks.
- When deploying, change the placeholder value (`change-me-to-a-strong-random-value`) to a strong random string in both files (e.g. `openssl rand -hex 32`).
