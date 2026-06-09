# Changelog

All notable changes to OpenVDM are documented here, organized by release tag against the `master` branch.

---

## [2.15.1] – 2026-06-09

### Fixed
- CDT SSH `destDir` normalizer no longer strips the required leading slash from absolute remote paths
- CDT add form now preserves the selected transfer type after an inline connection test
- Fixed undefined array key errors on CST and CDT add form initial load
- Fixed copy-paste error in CDT form page guide text
- 'Destination Directory is mountpoint?' check is no longer shown for non-local CDT transfer types

---

## [2.15.0] – 2026-06-07

### Added
- Wildcard glob support in collection system transfer source directories (issue #57)
- Database backup/restore utility script at `bin/db_backup_restore.py.dist` (issue #98)
- AlmaLinux/Rocky/RHEL 10 and Ubuntu 26.04 (Resolute) install support
- Unified install script `utils/install-openvdm.sh` replacing the two platform-specific scripts
- `workerApiKey` shared secret: install script now generates a key and injects it into both `openvdm.yaml` and `Config.php`; key is preserved across re-runs and when 3rd-party tools depend on it

### Changed
- Transfer logs relocated from inside the cruise data directory to `TRANSFER_LOG_DIR` (default `/var/log/openvdm`); database migration removes the `Transfer_Logs` extra directory entry
- Dependency versions updated to latest safe patch/minor releases
- All server-side Python files now use pdoc-compatible inline documentation with Google-style docstrings (issue #97)

### Fixed
- **Security:** Credential fields (`rsyncPass`, `smbPass`, `sshPass`) are now stripped from all CST/CDT/Warehouse API responses unless the request carries a valid `X-Worker-Token` header (issue #99)
- **Security:** CST and CDT edit forms no longer pre-populate password inputs via `value=`; blank submit preserves the stored credential (issue #99)
- **Security:** Fixed SQL injection, command injection, and XSS vulnerabilities
- **Security:** `errorlog.html` permission changed from `0777` to `0664` with Apache group ownership; MySQL root password no longer written to a world-readable `/tmp` file during install; preferences file locked to `0600` after write
- SMB version detection no longer incorrectly relies on the `mount` command output (issue #94)
- Improved error detail surfaced from worker crash reports and connection test failures (issue #94)
- Auto-correct server/path syntax, trim whitespace, and handle rclone destinations in transfer forms (issue #96)
- Progress tracking fixed to prevent values exceeding 100% or going backwards (issue #95)
- PHP 8.2 compatibility fixes
- Fixed HY093 PDO parameter name collision in message search queries
- Read-only warehouse config fields are now preserved on validation error re-render
- Fixed KeyError crashes when credential fields are absent from API responses
- Fixed rsync and Samba sample data setup on RHEL/AlmaLinux 10
- Various AlmaLinux/Rocky/RHEL 10 install fixes (gearmand source build, rsyncd service, php-fpm restart, IPv6 loopback)

---

## [2.14.1] – 2026-03-04

### Fixed
- Ubuntu install script now works for both 22.04 and 24.04
- Install Python 3.12 via deadsnakes PPA on Ubuntu 22.04 for package compatibility
- Install script bugs: invalid package reference, missing `mysql-server`, samba idempotency, `transferPublicData` typo, `mysql_native_password` compatibility, dynamic `CODENAME` detection

---

## [2.14.0] – 2026-03-03

### Added
- New and updated instrument parsers: DBS, DBT, HDT, SV, SBE38, SBE45, XDR, PSXN-23, fluorometer, flowrate, Gill anemometer, MWD, MWV, SVP/SSV
- OpenRVDAS plugin
- GeoJSON `combine_geojson_files` now handles both legacy and new dashboard formats
- TimeSpan syntax support in KML output
- ISO 8601 timestamps in data dashboard outputs (replaced epoch values)

### Changed
- Reduced data dashboard JSON file sizes by removing pretty-printing
- Renamed `svp_parser` to `ssv_parser` for accuracy

### Fixed
- Restored Data Quality Dashboard functionality
- Fixed incorrect conditional logic for rsync destination paths
- Fixed post-hook commands being overwritten on repeated calls
- Security: updated `urllib3`

---

## [2.13.2] – 2025-11-05

### Fixed
- Fixed progress percentage tracking regression
- Fixed collection system transfer filter logic

---

## [2.13.1] – 2025-10-26

### Fixed
- Synology `@eaDir` metadata directories are now correctly ignored during transfers
- Various minor bug fixes

---

## [2.13.0] – 2025-10-14

### Added
- Configurable date display in UI via `SHOW_DATES_IN_UI` flag (issue #83)
- Expanded cruise metadata panel showing all cruise metadata fields

### Changed
- Standardized API controller responses and code style
- Removed dates from page header; moved to configurable metadata panel

### Fixed
- Bug fix for issue #84 (cruise metadata display)

---

## [2.12.0] – 2025-10-06

### Added
- SSH-based cruise data transfers now use rclone (issue #75)
- rclone added to install scripts
- Pre-finalized task support for lowerings
- Cruise data transfer execution can be triggered from the scheduler
- Improved post-hook task logic with better task monitoring

### Changed
- Job status percentage values adjusted for accuracy
- Logging message format improvements

### Fixed
- Cruise end date now correctly set when finalizing a cruise
- Fixed scheduler issue that could double-submit jobs
- Fixed rclone remote name generation from SSH hostname

---

## [2.11.0] – 2025-08-19

### Added
- rclone support for ship-to-shore transfers (issue #72)
- Post-hooks worker for automated task chaining
- Write access test for rsync-server CDT destinations
- Exclude logfiles now visible in the WebUI
- Skip empty files/directories option for rsync transfers
- Connection utilities extracted into `server/lib/connection_utils.py`

### Changed
- Major refactor of all Gearman workers for clarity, consistency, and maintainability
- Standardized task name constants across all workers
- Improved logging throughout (f-strings, consistent format, reduced noise)

### Fixed
- Workers now correctly return `Ignore` instead of `Fail` when nothing to do
- Fixed default ignore patterns for rsync partial files and system files
- Fixed directory ownership setting for local transfers
- Fixed bug where jobs set tasks to idle when they should have been ignored

---

## [2.10.1] – 2025-07-12

### Fixed
- Resolved issue #64 (collection system transfer path bug)

---

## [2.10.0] – 2025-04-30

### Added
- TiTiler-based GeoTIFF parser with support for both traditional and TiTiler formats
- Shorthand date/time notation in source/destination directory templates (issue #61)
- Transfer log purging
- Build overlay layers utility script (`build_overlay_layers.py`)
- Ability to skip mapping tiles generated by the data dashboard

### Changed
- Major refactor of collection system transfer worker: unified all transfer types into a single transfer function (issue #66)
- Replaced bower with npm for JavaScript dependency management (leaflet, chart.js, jQuery)
- jQuery updated to v3; improved modal reliability (issue #60)
- UI layout improvements across collection system and cruise data transfer config pages
- Cruise data transfer exclusions changed from dropdowns to checkboxes

### Fixed
- Fixed SMB transfer source directory path calculation
- Fixed file path prefix stripping when building file lists
- Fixed edge case where a deleted transfer config could crash a queued job
- Fixed modals not always appearing on first click (issue #60)
- Fixed `setting 'transferPublicData' to False` no longer creates `From_PublicData` directory

---

## [2.9.8] – 2025-01-19

### Added
- MacOS (Darwin) detection for SSH-based transfers to handle `rsync` flag incompatibilities
- Abstracted MD5 hashing via `hashlib` for FIPS-compliant systems
- Trackline build script improvements and updated default dist files
- Rocky Linux install script improvements

### Fixed
- Divide by zero error in transfer progress calculation (issue #53)
- Bug related to issue #46 (transfer logic edge case)
- Install script cleanup

---

## [2.9.7] – 2024-08-22

### Added
- Favicon added to web UI

### Fixed
- Disabled `chown` when CDT destination is a mount point (avoids permission errors)
- Fixed GeoTIFF parser
- Fixed EM302 plugin

---

## [2.9.6] – 2024-06-15

### Changed
- Default install location changed from `/vault` to `/data`
- Message search now also searches `messageBody` text

### Fixed
- Fixed rsync include/exclude list file writing due to upstream rsync bug
- Fixed message pagination so search works across multiple pages

---

## [2.9.5] – 2024-04-13

### Added
- Message title search capability in the web UI
- Node.js now installed via NVM instead of nodesource

### Changed
- Updated TSG and other default parsers
- Improved log messages to include transfer names
- `build_remote_directory` script: corrected variable assignment

---

## [2.9.3] – 2023-12-03

### Changed
- Updated Node.js install method in install script

---

## [2.9.2] – 2023-11-03

### Fixed
- Bug fixes discovered during R/V Sally Ride deployment

---

## [2.9.1] – 2023-08-17

### Added
- Automatic lowering end date update when finalizing a lowering for the first time (issue #34)
- Additional end-of-lowering hooks

### Changed
- Migrated leaflet and chart.js from bower to npm
- Removed ESRI Ocean basemap (deprecated); switched to GMRT

### Fixed
- Fixed PublicData path definition timing — path is now only defined when PublicData transfer is enabled
- Fixed rsync-server-based collection system transfers
- Fixed database error on larger transfer jobs

---

## [2.9.0] – 2023-05-15

### Added
- Ubuntu 22.04 install script
- Lowering directory worker and associated DB schema
- Start/End Port fields in cruise configuration
- `--remove-source-files` rsync option for collection system and ship-to-shore transfers
- Timeout added to rsync server connection tests

### Changed
- PublicData directory definition moved from database to `Config.php`
- Config filenames moved to database for flexibility
- Refactored parsers to support optional header records
- Significant code cleanup and refactoring across cruise, lowering, and collection system workers

### Fixed
- Fixed web routing issues introduced during refactor
- Fixed `data_dashboard` worker crash when root directory checked
- Various bug fixes discovered on R/V Revelle (RR2212)

---

## [2.8.0] – 2022-07-12

### Added
- `--remove-source-files` rsync flag support in cruise data transfer UI
- Start/End Port definitions in cruise metadata

### Changed
- PublicData end-of-cruise behavior revised
- Default install location changed from `/vault/FTPRoot` to `/vault`

### Fixed
- Fixed SSH-based cruise data transfers
- Fixed end-of-cruise task logic
- Various bug fixes from R/V Odyssey deployment

---

## [2.7.0] – 2022-03-12

### Added
- Zoom and pan functionality for data dashboard charts (Chart.js integration)
- Customizable chart colors via `chartColors.js`
- Profile data display support in data dashboard
- Inverted X/Y chart display option
- DBT and DBS NMEA parsers
- MapProxy install instructions added to install script

### Changed
- Cruise data transfer configuration UI redesigned — exclusions now use checkboxes
- Option to include/exclude OVDM system files from cruise data transfers
- ExtraDirectories, CruiseDataTransfers, and ship-to-shore transfer index pages now sort by long name

### Fixed
- Fixed spaces in SSH source directory names for collection system and cruise data transfers
- Fixed sorting on CollectionSystemTransfers configuration page
- Fixed remaining hard-coded "Cruise" references

---

## [2.6.10] – 2022-01-19

### Added
- `build_remote_directory.py` utility with lowering support (`-l` flag)
- NMEA PSXN-23 and PSXN-24 parsers
- SBE38 instrument parser
- Updated PAR2, SBE45, and other default parsers

### Changed
- Collection system filter logic now validates timestamp before filtering

### Fixed
- Fixed timezone handling in staleness logic
- Fixed blank password support in transfers
- Fixed staleness date parsing crash when cruise/lowering end date is undefined

---

## [2.6.9] – 2022-01-05

### Added
- Rocky Linux 8.4 install script
- Config setting to disable transfer of PublicData to cruise directory

### Fixed
- Fixed cruise data transfers where `destDir` contained `{cruiseID}`
- Divide by zero bug fix in cruise size calculation
- Fixed header styling when file size errors occur

---

## [2.6.8] – 2021-11-02

### Added
- Configurable custom staleness time per collection system transfer

### Fixed
- Hotfix: mis-formatted date string in staleness logic

---

## [2.6.7] – 2021-10-21

### Added
- SSH collection system and cruise data transfers now handle spaces in source/destination directory names
- Added profile data display to data dashboard
- Added inverted chart support
- Added DBT and DBS parsers

### Changed
- Config index pages for ExtraDirectories, CruiseDataTransfers, and ship-to-shore now sort by long name

### Fixed
- Fixed remaining hard-coded "Cruise" label references
- Fixed sorting on collection system transfer config page

---

## [2.6.6] – 2021-09-16

### Fixed
- Fixed rsync stdout/stderr output parsing and message handling
- Fixed subprocess communication to prevent lost stdout messages
- Fixed bug where detecting an in-progress transfer incorrectly set it to idle

---

## [2.6.5] – 2021-09-11

### Added
- Filter for rsync partial files (`.filepart`)
- Configurable label for the "Cruise" concept throughout the UI

### Fixed
- Fixed long-standing variable naming issue
- Various JavaScript fixes

---

## [2.6.4] – 2021-08-22

### Added
- API route for retrieving combined stats for a data type

### Fixed
- Fixed MD5 summary worker bug in filename handling
- Fixed cruise worker directory and file passing logic
- Hot fix for cruise data transfer failures

---

## [2.6.3] – 2021-06-17

### Fixed
- Install script bug fixes

---

## [2.6.2] – 2021-05-30

### Fixed
- Initialization errors in lowering and lowering_directory workers
- Bug fixes from R/V Atlantic Explorer install
- Lint and code style fixes

---

## [2.6.1] – 2021-05-25

### Fixed
- Fixed lowering parent directory not being created correctly
- Fixed directory name construction for lowering transfers
- ASCII filepath validation added to file filtering
- Install script fixes (added missing library)

---

## [2.6.0] – 2021-02-16

Initial tagged release.
