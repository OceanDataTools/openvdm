# Changelog

All notable changes to OpenVDM are documented here, organized by release tag against the `master` branch.

---

## [2.16.0] – 2026-09-28

**Upgrading:** follow "Upgrading from 2.15" in [INSTALL.md](INSTALL.md). The database needs updating with `database/openvdm_215_to_216.sql`. Several plugins, parsers and `bin/` scripts need their updated `.dist` files copied by hand, and GeoTIFF sites should rebuild the data dashboard.

### Added
- Add FTP Server as a collection system transfer and cruise data transfer type. As a collection system transfer source, OpenVDM mounts the source directory on the FTP server with `rclone mount` and copies from it with `rsync`, as for SMB shares, so file filters, staleness, wildcard source directories and removing source files work as for other types. The transfer form takes the server (with an optional `:port`, e.g. `ftp.example.org:2121`; default 21), username and password; `anonymous` needs no password. **Test Setup** checks the login, the mount, the source directory and, when source files are removed, write access. As a cruise data transfer destination, the cruise is copied (or synced) to `<Destination Directory>/<cruiseID>` on the FTP server with rclone, as for SSH destinations, and **Test Setup** checks the login, the destination directory and write access (#199). Only plain FTP is supported, not FTPS. Existing installs must run `database/openvdm_215_to_216.sql`; the installer now also installs `fuse3`, which `rclone mount` needs (#17)
- Add a depth profile chart to the data dashboard: `visType: json-profile` draws depth down the vertical axis and the other series across, each on its own x axis, with points joined in time order (e.g. a CTD cast or an ROV dive). The optional `depthSeries` (default `Depth`) and `profileSeries` (default: all other series) keys choose the series. Profiles work on default and lowering tabs, where they can be zoomed along depth, and as main-page tiles for data types not also charted against time. No plugin changes are needed: it uses the same visualizer data as the time-series charts. See `www/etc/datadashboard.yaml.dist`; the example Lowering tab now includes a `rov-ctd` profile. Sites with their own `datadashboard.yaml` add profile charts by hand (#274)
- Add a parser for Sea-Bird SBE 9plus CTD casts, `ctd_profile_parser.py.dist` (`CTDProfileParser`). It decodes a cast's `.hex` file with the calibration coefficients in its `.XMLCON`, and returns pressure, temperature, conductivity and salinity, which the dashboard can draw as a depth profile (`visType: json-profile`, `depthSeries: Pressure`). It can also save a PNG profile plot (`plot_dir` / `--plotDir`; needs matplotlib, which `requirements.txt` doesn't install). Based on original code by Oscar Garcia (CSIC). Pressure comes from the Digiquartz equation with the sensor's temperature compensation, and salinity from PSS-78; on the sample casts, pressure, temperature, conductivity and salinity match Sea-Bird's own data conversion (SBE Data Processing 7.26.7) scan for scan. A matching plugin template, `server/plugins/ctd_plugin.py.dist`, runs it on a collection system's `.hex` files (data type `ctd`); copy it to `<collection system name>_plugin.py` to use it, as for the sample `CTD` transfer (#286). When a cast's `.xmlcon` arrives after its `.hex`, or is updated, the data dashboard re-parses the cast: plugins can now define an optional `get_source_files(filepath)` that maps a new or updated file to the raw files to process (#288). Installing the sample data enables the CTD plugin, and the Seawater tab in `datadashboard.yaml.dist` draws CTD casts as depth profiles (#290)
- The default cruise record of a new install now matches the sample data, a Gulf of Mexico transit: location Gulf of Mexico, ports Pascagoula, MS to Galveston, TX (were New England Seamounts, Newport, RI to Norfolk, VA). Existing installs are unchanged (#293)
- Data dashboard maps can show GeoJSON points as well as tracks: points are drawn as circle markers in the data type's track colour, with a popup listing their properties, and Latest Position, Start/End Positions and the main page's map tile treat a point as its own first and last position. Before, a point broke those markers. Also fixes the lowering tab's Start/End Positions start marker not being removed when unticked (#292)
- On data dashboard maps, a data type of points (e.g. `ctd-position`, `xbt-position`) no longer gets a **Latest Position** checkbox, which only put a second marker on its latest point; tracks keep it (#316). Likewise on lowering tabs, such a data type no longer gets a **Start/End Positions** checkbox, which put both markers on the point (#322)
- Show where CTD casts were taken: a new parser, `CTDPositionParser` (in `ctd_profile_parser.py.dist`, #324), reads the NMEA position, times and station from a cast's `.hex` header (no `.xmlcon` needed), and the CTD plugin returns it as data type `ctd-position`, a map point with a popup (cast, station, start and end time, bottom depth). The Position tab in `datadashboard.yaml.dist` shows it with the ship's track. Sites using the CTD plugin need the updated `ctd_plugin.py.dist` and `ctd_profile_parser.py.dist` copied; existing `datadashboard.yaml` files need `ctd-position` added to their map by hand (#292)
- The CTD profile parser now returns the cast's **Depth**, computed from pressure with Sea-Bird's salt-water depth formula (UNESCO 1983, as SBE Data Processing's `depSM`), and `datadashboard.yaml.dist` draws CTD profiles against it (`depthSeries: Depth`, was `Pressure`). The latitude it needs comes from the NMEA position the deck unit appends to each scan, or the cast's header, or a new `latitude` parser option (`--latitude`) for casts with no position; without any of them there's no Depth series, and `depthSeries: Pressure` still works. Its stats add the depth range and **Geographic Bounds** (from the same positions). On the sample casts both match SBE Data Processing's output (depth within 0.001 m, positions exactly). Sites using the CTD plugin need the updated `ctd_profile_parser.py.dist` copied, and `depthSeries: Depth` set in their own `datadashboard.yaml` to draw profiles against depth (#304)
- Add a parser for Sippican/Lockheed Martin MK21 XBT casts, `xbt_parser.py.dist`, built on Peter Shanks' (AADC) [xbt-edf-qc](https://github.com/botheredbybees/xbt-edf-qc) library. `XBTParser` reads a cast's `.EDF` file and runs the library's automated CSIRO XBT QC Cookbook checks on it (surface transient, spikes, wire break, range checks, position on land; not the checks that compare casts with each other). It returns depth, temperature and sound velocity without the points QC flags as bad, for a depth profile (`visType: json-profile`, `depthSeries: Depth`), with quality tests for the temperature profile, position and probe type. `XBTPositionParser` returns the launch position as a map point (cast, probe type, launch time, serial number, maximum depth). The template `server/plugins/xbt_plugin.py.dist` runs both on a collection system's `.EDF` files (data types `xbt` and `xbt-position`). xbt-edf-qc isn't in `requirements.txt`; installing the sample data installs it into OpenVDM's virtual environment, pinned to a tested commit, and enables the XBT plugin, and `datadashboard.yaml.dist` draws XBT casts on the Seawater tab and their positions on the Position tab. Other sites install it as the parser's docstring says (#300)
- The CTD and XBT position parsers (`ctd-position`, `xbt-position`) only return the map point, with no stats or quality tests, so those data types aren't listed on the Data Quality tab; each cast's stats are under `ctd` / `xbt` (#314)
- The CTD and XBT position popups show their times as ISO 8601 UTC to the second (e.g. `2012-04-28T12:35:00Z`, was `2012-04-28T12:35:00+00:00`, with fractional seconds on a CTD cast's end). Plugins can use the new `format_iso8601()` in `server/lib/openvdm_plugin.py` for the same format (#320)

### Changed
- Replace the CARTO basemap, which now requires an API key, with keyless providers. The map layer switcher now offers OpenStreetMap, Esri Ocean, Esri Dark Gray and Light Gray canvas basemaps, and GMRT, plus Esri label and OpenSeaMap seamark overlays. The layers are defined once in the new `mapBaseLayers.js` and shared by the data dashboard, lowering and custom maps (#121). Installs with a customized `www/app/templates/default/js/custom1.js` still point at CARTO. Update that file from `custom1.js.dist`.
- Add an ESLint check for bugs only (undefined names, unused and duplicate variables), plus a `php -l` syntax check, to the pre-commit hooks, and clean up the unused variables and duplicate declarations it found in the dashboard, lowering, welcome-page and header scripts. No behavior changes. The `chartColors.js.dist`, `custom1.js.dist` and `dataDashboardMainCustom.js.dist` templates changed only by removing an unused variable or adding a lint comment, so sites don't need to update their copies (#128)
- Add `moment`, used by the date pickers, to `www/package.json` as a direct dependency. It was already installed (2.30.1) as a dependency of the datetimepicker package, and the version is unchanged (#128)
- Bump pandas from 2.3.1 to 2.3.3 in `requirements.txt`, the first 2.3.x release with Python 3.14 wheels. The installer uses the newest Python 3.11+ the OS offers, which is 3.14 on current Rocky Linux 9; pandas 2.3.1 had to be compiled from source there. No change in behavior: the sample plugins and parsers give identical output with either version (#330)
- The installer now runs `composer install --no-dev`, so Composer dev dependencies (currently only PHPStan) aren't installed on ship servers. Re-running the installer removes any already present (#130)
- Add PHPStan static analysis (level 1, with a baseline of existing findings) for the web app's PHP, run from the pre-commit hooks. It's a development tool with no effect on running installs. The bugs it found are fixed below (#132, #135) (#130)
- Fix `pylint` failing on every run with `ImportError: cannot import name 'find_pylintrc'`: the `.pylintrc` `init-hook` used a function removed in pylint 3.0. Developer tooling only (#140)
- Standardize the parser and plugin template docstrings: the remaining legacy `FILE:`/`USAGE:` headers are replaced with pdoc module docstrings, missing method docstrings are added, and class docstrings that named the wrong instrument are corrected. Documentation only; sites don't need to update their copies (#141)
- Remove the DBS parser's unused `no_mag` constructor option. No shipped plugin uses the DBS parser; a site plugin passing `no_mag` to it will now get a `TypeError` (#147)
- Add docstrings to the remaining undocumented public functions in `server/lib/connection_utils.py` and the data dashboard and ship-to-shore workers, and replace the last legacy `FILE:` headers. Documentation only (#143)
- Add Google-style `Args`/`Returns`/`Raises` sections to every public function and method in `server/lib/` (the API used by workers and site plugins), correct several inaccurate docstrings, and clarify in CLAUDE.md which documentation rules apply to new vs. existing code. Documentation only (#144)
- Document the remaining `bin/` script and OpenRVDAS plugin functions, comment the module-level constants, and verify the Python API docs build cleanly with pdoc (command added to CLAUDE.md). Documentation only (#160)
- Add Google-style `Args`/`Returns` sections to every public function and method in the Gearman workers (`server/workers/`), and correct several inaccurate worker docstrings. Documentation only (#161)
- Remove `OpenVDM.get_logfile_purge_timedelta_str()`, which called a web API endpoint that doesn't exist and was never used. Log purging still uses `logfilePurgeTimedelta` from `openvdm.yaml` (#169)
- Remove a no-op `setTimeout(updateBounds(...), 5000)` from the data dashboard, lowering and custom-dashboard map setup. It called `updateBounds()` immediately, before any layer had loaded; each layer already refits the map when it loads, so map behavior is unchanged. Sites don't need to update their `custom1.js` (#131)
- PHP cleanup with no behavior change: class namespace declarations now match their directories (`Models`, `Models\Config`, `Controllers\Config`, `ShipToShoreTransfers`); `catch` blocks in the cruise/lowering config forms and `Helpers\Database` now reference the right exception classes; framework helpers that fell off the end now return `null` explicitly; and the undefined `SITEEMAIL` constant is guarded (#135)
- Update `js-cookie` to 3.0.8 and pin the date picker's `moment-timezone` dependency to 0.5.x (0.5.48) with an npm override, clearing the js-cookie (high), moment-timezone (moderate) and datetimepicker (low) `npm audit` findings. None were exploitable in how OpenVDM uses them. `npm audit` now reports only Bootstrap 3, which needs a Bootstrap 5 migration (#178). The installer's `npm install` picks this up; nothing needs copying by hand (#181)
- Data dashboard maps draw geoJSON tracks in the chart palette's colors (`colors` in the site's `chartColors.js`) instead of all in Leaflet's default blue. Each data type gets its own color, shared by all its tracks, with a matching swatch next to its title in the map's file list; colors don't change when tracks are toggled. Tabs that don't load `charts` keep the default style (#195)
- The installer now builds the web app (`composer install`, and `npm install` through `post_composer.sh`) as the OpenVDM user instead of root, so package install scripts no longer run as root. On Debian and Ubuntu it installs Node.js (nvm) in the OpenVDM user's home instead of root's, so that user can run npm. Re-running the installer over an existing install removes the old root-owned `/root/.nvm` and its lines in root's `.bashrc` (unless root installed other global npm packages there) (#183)
- The cruise data transfer form rejects a `:` in the Destination Directory unless the transfer type is Local Directory, where `remote:path` means an rclone remote. For the other types, a `:` made **Test Setup** treat the path as an rclone remote and fail (#199)
- The sample data install now also sets up a local FTP server for testing FTP transfers: a pyftpdlib server run by Supervisor as `openvdm_sample_ftp`, serving the sample data's `ftp_source` and `ftp_destination` on localhost only. Port 2121 supports `MLSD`; port 2122 doesn't, like many older instrument FTP servers. The OpenVDM user can read the sample data and write to `ftp_destination`; anonymous users can read `ftp_source`. Installs without sample data are unchanged (#200)
- Installing the sample data now turns on lowering components, sets up the current lowering (`ROV0001` on a new install) and runs its transfers along with the cruise's, so a sample install also exercises the lowering features. It also uncomments the data dashboard's example **Lowering** tab in `www/etc/datadashboard.yaml`, unless that file already has one (#272). Installs without sample data are unchanged (#201)
- The collection system and cruise data transfer forms now show example values (placeholders) in the server fields and in the Source/Destination Directory fields. The directory examples change with the selected transfer type. The Rsync Server help text now says the field includes the rsync module (#227)
- The collection system and cruise data transfer forms now choose the **Transfer Type** from a dropdown instead of radio buttons. A new transfer starts with no type selected ("Select a transfer type…"), and only the chosen type's fields are shown (#226)
- Add system and NAS folders and files that are never instrument data to the default ignore list: `lost+found`, Linux trash folders (`.Trash-*`), NFS `.nfs*` files, Windows recycle bins (`$RECYCLE.BIN`), `System Volume Information` and `ehthumbs.db`, macOS volume folders (`.Trashes`, `.Spotlight-V100`, `.fseventsd`, `.TemporaryItems`, `.DocumentRevisions-V100`), NAS recycle bins and snapshots (`#recycle`, `.snapshot`, `~snapshot`, `.zfs`), and Office lock files (`~$*`, `.~lock.*#`). Collection system transfers now skip ignored folders while listing the source, instead of listing and then dropping their files, so an unreadable `lost+found` no longer fails an rsync, SSH, SMB or FTP transfer, and snapshot folders aren't scanned on every run. Cruise data and ship-to-shore transfers also leave the new patterns out (#265)
- The data dashboard no longer shows what has nothing to show. The **Data Quality** tab leaves out files with neither quality tests nor stats, and data types with no files left; before, a file whose dashboard data had no quality tests at all stopped the whole page with a PHP error. On the other tabs, a map or chart card is left out when none of its data types has any files (for the selected lowering, on lowering tabs), instead of showing "No Data Found."; a lowering tab with nothing for the selected lowering says so (#310)
- INSTALL.md's "Upgrading from 2.14" is now a step-by-step guide with two routes: in place on Rocky Linux/AlmaLinux 8 or 9 (re-run the 2.16 installer, then the database update scripts), or on a fresh OS (install 2.16, restore the 2.14 backup, run `openvdm_214_to_215.sql` then `openvdm_215_to_216.sql`, check the data warehouse settings), then merging site customizations into the 2.16 files. Checked against MySQL 8.0: a migrated 2.14.1 database has exactly the 2.16 schema, and keeps its transfers, passwords, users and cruise. The in-place route has been tested end to end on Rocky Linux 9; it sets `openvdm.yaml` and `datadashboard.yaml` aside as `.214` copies so the installer builds the 2.16 files, then diffs them (#338). Also corrects "Upgrading from 2.15": **Rebuild Data Dashboard** is a button under Maintenance Tasks on the Configuration page. Documentation only (#326)

### Fixed
- Fix a new password typed into a collection system or cruise data transfer edit form being lost when **Test Setup** was clicked before **Update**. The password is now kept server-side for the following Update (#119)
- Fix every page using the default header, and `/api/messages/getNewMessagesTotal`, returning an empty HTTP 500 once the Messages table grew large; message totals are now counted in MySQL instead of loading every row into PHP (#123)
- Fix `Undefined array key` PHP warnings (e.g. `cruisePI`) when switching the current cruise to one whose `ovdmConfig.json` omits blank fields (#125)
- Fix `api/dashboardData/getDashboardDataTypes/<cruiseID>` passing an undefined variable to the model, which logged an `Undefined variable` warning on every call (#132)
- Fix PHP 8.2+ `Creation of dynamic property` deprecation notices from the Ship-to-Shore config page (a misspelled property name), the data dashboard and the lowerings list (undeclared properties) (#132)
- Fix data dashboard tabs configured with `view: lowering` or `view: dataDashboard` in `datadashboard.yaml` showing "An error occured" instead of the tab, caused by undefined variables in those views. The shipped config uses `view: default` for every tab, so default installs weren't affected (#135)
- Fix the TiTiler GeoTIFF parser placing the data dashboard map overlay in the wrong place for GeoTIFFs not in lat/lon (e.g. UTM, Web Mercator): it used TiTiler's `/cog/info` bounds, which are in the file's own coordinate system. It now uses WGS84 bounds from `/cog/info.geojson`, and also adds a Geographic Bounds stat and, for data rasters such as bathymetry, per-band value range and valid-pixel stats. Sites must copy `server/plugins/parsers/geotiff_titiler_parser.py.dist` over their `geotiff_titiler_parser.py` to get this (#138)
- Fix Geographic Bounds on the Data Quality page: both GeoTIFF parsers recorded the bounds as west/south/east/north instead of north/east/south/west, so GeoTIFF bounds were mislabelled; and each data type's combined bounds kept the smallest of its files' East values instead of the largest (all parsers). Sites must copy `server/plugins/parsers/geotiff_parser.py.dist` and `geotiff_titiler_parser.py.dist` over their `.py` copies, then rebuild the data dashboard to regenerate existing stats (#158)
- Fix `bin/build_remote_directory.py` creating local directories with the wrong permissions (`mode=755` decimal instead of `0o755`), which left the owner unable to list them. Sites must copy `bin/build_remote_directory.py.dist` over their `build_remote_directory.py`; directories it already created can be fixed with `chmod 755` (#164)
- Fix the cruise data transfer **Test Setup** message for a local destination that isn't writable: it said "Unable to delete source files from: … on SMB share" and now says "Unable to write to destination directory: …" (#165)
- Fix error messages for an invalid transfer or task ID in `server/lib/openvdm.py` showing as a tuple (`('Invalid task id: %s', '12')`) instead of `Invalid task id: 12` (#167)
- Fix the cruise data transfer **Test Setup** for rclone destinations: a misspelled or undefined remote (or a missing rclone config file) passed "Rclone remote config" and was then tested as a local directory; it now fails that check. A destination path containing a second `:` no longer raises an error (#166)
- Fix `OpenVDMCSVParser.round_data(df)` raising `AttributeError` when called without a precision; it now returns the data unchanged. Only affects site-written parsers; the shipped parsers always pass one (#168)
- Fix the SBE 45 TSG parser failing with `ValueError: All arrays must be of the same length` for files without SBE 38 data when a parser with the SBE 38 option had already run in the same process: the option modified a list shared by all instances. Sites that parse TSG files both with and without an SBE 38 must copy `server/plugins/parsers/tsg45_parser.py.dist` over their `tsg45_parser.py` (#146)
- Fix the HPR and GNSS parsers producing no output: roll was parsed as an integer, so fractional roll values (the normal case) rejected every row, and whole-number values crashed the stats step. Stats now also accept numpy numbers, so an integer-typed column can't crash a parser. Sites using these parsers must copy `server/plugins/parsers/hpr_parser.py.dist` and `gnss_parser.py.dist` over their `.py` copies (#152)
- Fix time cropping (`start_dt`/`stop_dt`, or `--startDT`/`--stopDT` on the command line) in the CSV parsers: 16 parsers failed with `KeyError: 'date_time'`, and all of them failed with `TypeError` for crop times without a timezone. Crop times without a timezone are now treated as UTC. Fixed in the shared parser library, so no parser files need updating (#149)
- Fix the ROV OpenRVDAS plugin, which couldn't run: it was never updated to the current plugin interface, so the data dashboard worker skipped it. It now also crops each file's data to that file's lowering, using the Sealog descending/floats-on-surface milestones (falling back to the lowering's start/stop times) or the lowering's OpenVDM dates, so a dashboard rebuild crops each lowering to its own dive. Sites using it must copy `server/plugins/rov_openrvdas_plugin.py.dist` over their `rov_openrvdas_plugin.py`, keeping their `SEALOG_SERVER_URL` and `SEALOG_JWT` (#150)
- Fix Rebuild Cruise Directory, and cruise setup and finalize, failing with `KeyError: 'transferPublicData'` on installs whose `server/etc/openvdm.yaml` predates 2.15.5: the setting now defaults to `True`. Re-running the installer adds `transferPublicData` and `workerApiKey` to such files when they're missing. Without `workerApiKey`, workers got no transfer passwords from the web app, so transfers that use a password failed (#187)
- "Worker crashed" messages now name the file and line that raised the error, instead of always `worker.py, line 233` (#187)
- Turning on Show Lowering Components from the New Cruise form now creates the lowering base directory in the current cruise, as Edit Cruise already did. Rebuild Cruise Directory and Setup New Lowering no longer report a failed step as both Fail and Pass and carry on (#189)
- Fix the data dashboard Position tab logging `Map container is already initialized`: the shipped `datadashboard.yaml.dist` loaded both `dataDashboardDefault.js` and `lowering.js` on it, and each builds every map on the page. Also fix lowering tabs (`view: lowering` with `lowering.js`), whose maps, charts and start/end positions hadn't loaded since 2.14.0: they now send the data type the dashboard API requires, and charts render into a `<canvas>`. `datadashboard.yaml.dist` documents the `lowering` view and includes a commented-out example Lowering tab. Sites must delete the `- lowering` line from their own Position tab (#185)
- Fix the data dashboard crashing ("Worker crashed") when a collection system transfer's plugin fails to import, e.g. the ROV OpenRVDAS plugin without site copies of the parsers it uses. The failure is now reported for that transfer, and Rebuild Data Dashboard carries on with the others, ending in error with the plugins that didn't load (#191)
- Fix the data dashboard map markers' shadow image returning 404 since 2.11.0 (#193)
- Fix cruise data transfer **Test Setup** passing rclone destinations of types other than local, SMB, Google Cloud Storage and SFTP (e.g. FTP, S3, Google Drive, WebDAV) without testing them. Every rclone remote now gets a destination check (the bucket, for bucket-based stores such as S3 and B2) and a write test. Unreachable remotes fail in about 15 seconds instead of hanging, and failures include rclone's error message (#179)
- Fix a collection system transfer whose source couldn't be listed passing with no files. With **Sync from source** on, that emptied the transfer's destination in the cruise. A missing local, SMB or FTP source directory, or an error while listing an SMB or FTP source, now fails the transfer. For wildcard source directories, every match is listed before anything is copied, and the transfer fails if any listing fails. Local sources still skip unreadable paths, with a warning in the log (#206)
- Fix transfer cleanup deleting files on an SMB share (or FTP server) when the share couldn't be unmounted: the temporary directory it was mounted in was deleted anyway, through the mount. Cleanup now also tries a lazy unmount, and leaves the temporary directory in place if the share is still mounted. Affects SMB collection system transfers that remove source files, and SMB cruise data transfer destinations (#207)
- Fix failed transfers being reported as successful: when rsync or rclone exited with an error (e.g. a wrong password, an unreachable server, or a destination that can't be written), collection system, cruise data and ship-to-shore transfers still reported "Transfer Files: Pass". They now fail with the tool's error. rsync's "files vanished" results (a file deleted between listing and transfer) still count as success. A cruise data transfer whose rsync dry run fails no longer reports "nothing to transfer". Also fix cruise data transfers that use rclone (local, SMB, SSH and rclone-remote destinations) and ship-to-shore transfers that log in with a password never reporting which files they transferred, and rclone transfers never reporting progress; cruise data transfers now also report the files a sync deleted (#230)
- The installer now reports a failed or timed-out cruise setup step after install (Setup New Cruise, or re-exporting the configuration and rebuilding the cruise directory on a re-install) as a warning with the reason, instead of "done" (#212)
- Fix rsync cruise data transfers to a subdirectory of the rsync module: the Destination Directory was appended to the Rsync Server with no `/` (`host/module` + `backups` became the module `modulebackups`), so **Test Setup** and the transfer failed unless the Destination Directory was blank or started with `/`. The Destination Directory is now a directory within the module, with or without a leading `/`, and the form's help text says so (#228)
- **Test Setup** for an rsync cruise data transfer no longer leaves a `write_test.txt` in the destination directory: the write test now deletes it again. If the rsync server refuses deletes, Test Setup still passes and a warning is logged (#233)
- Fix collection system transfers from an rsync server or SSH server reporting success with no files when listing the source failed (e.g. the server was down or the module unavailable). With **Sync from source** on, that deleted every file already collected in the destination directory. A failed listing, a failed staleness re-listing, or a file list that can't be written now fails the transfer, and the reason includes rsync's error (e.g. `@ERROR: Unknown module`) (#238). A listing missing only folders inside the source that the transfer user can't read (rsync code 23) fails the transfer only with **Sync from source** on; otherwise rsync's errors are logged as warnings and the listed files are copied, as in earlier releases (#264). A source directory that can't be entered or listed still fails the transfer, and the staleness re-check drops files the second listing didn't see (#284)
- Fix rsync transfers failing with exit code 23 when the only problem was a listed file that was deleted before the transfer started. The check only looked at rsync's last 50 output lines, so for more than a few files it missed the errors and failed the transfer (or, the other way round, could miss a real error). A failed transfer's reason now names the first failing file, e.g. `send_files failed to open "...": Permission denied`, instead of rsync's generic "some files/attrs were not transferred" (#237)
- Fix the SSH password of a transfer that doesn't use an SSH key being written to the worker log in plain text when debug logging is on. The transfer command is now logged with `sshpass -p ****` (#240)
- When a collection system transfer fails partway, the files it copied before the failure (including those from wildcard source directories already done) now get their ownership set and are passed to the hooks (MD5 summary, data dashboard, ...). Before, a failed transfer reported no files, and because the next run found them up to date, those files were never processed (#239)
- Fix cruise data transfers to an **rsync server** copying nothing. The dry run that counts the files to send wrote to a local temporary directory but was given the rsync server's `--password-file` option, which rsync rejects without an rsync daemon (`syntax or usage error (code 1)`). Until #230 that failure was ignored and the transfer reported success with nothing copied; since #230 it failed with "Dry run failed". The dry run now leaves out the destination's remote-only options (#249)
- Fix a cruise data transfer to the top of an rsync module or SMB share being impossible to save: the form erased a Destination Directory of `/`, then rejected the empty field as required. `/` is now kept (and `//` no longer becomes empty for the other types), and the help text and placeholders say to use `/` for the top of the module or share (#247)
- Fix the data dashboard's `json-inverted` and `json-reversedY-inverted` charts, which haven't swapped their axes since the move to Chart.js. Time again runs down the left, earliest at the top, with the values across (reversed for `json-reversedY-inverted`), on default and lowering tabs and the main dashboard page. Zoom and pan follow the time axis, and inverted charts start taller on tabs. The chart visTypes are now documented in `datadashboard.yaml.dist` (#275)
- Charts on lowering tabs (`view: lowering`) now match the default tabs: each y axis's ticks are colored like its line, lines are thinner, and clicking a legend entry hides the series together with its axis. They also zoom and pan with the mouse wheel and drag (along time, or along depth for profiles), with a reset button, when the tab loads `charts-zoom`. The example Lowering tab in `datadashboard.yaml.dist` now does. Sites with their own Lowering tab add `charts-zoom` to its `jsArray` to get zoom; without it, charts work as before (#278)
- On data dashboard tabs (default and lowering), a data type's file names no longer wrap inside a narrow grid cell with most of the row empty: files sit side by side and only wrap between files, or when a name is wider than the whole card. The blank line after a map's Latest Position or Start/End Positions checkbox on narrower screens is gone too (#280, #282)
- Fix GeoTIFF layers served through TiTiler (`geotiff_titiler_parser`) not showing on lowering tabs: their map requested pre-rendered tiles from an `undefined` directory. The default tab, lowering tab and main page now build tile layers with one shared function in `mapBaseLayers.js`, which handles both pre-rendered tiles and TiTiler. `custom1.js.dist` uses it too; sites with their own `custom1.js` can update its `addTMSToMap()` to match (#298)
- Fix the data dashboard page jumping up when a different file is chosen on the last chart of a tab (default and lowering tabs), most noticeably on an expanded chart or a depth profile. Redrawing a chart briefly shrank its canvas, so a page scrolled to the bottom lost its scroll position (#302)
- Fix a data type's stats on the Data Quality page (and `api/dashboardData/getDataTypeStats`) when its files don't all have the same stats: each file's stats were merged into the summary by their place in the list, so a file missing one (e.g. a CTD cast without a position, which has no Depth or Geographic Bounds) had its other stats merged into the wrong ones, and a first file with fewer stats than a later one, or a file without stats, stopped the summary with a PHP error. Stats are now merged by name and type (#306)
- **Rebuild Data Dashboard** now deletes the dashboard files its new manifest doesn't list, e.g. for raw files removed from the cruise or that no longer parse; before, they stayed in the data dashboard directory (not shown, since the dashboard reads only the manifest). Only `.json` files are deleted, never `manifest.json`, after the new manifest is written, and not after a stopped rebuild (#318)
- Fix re-running the installer over a Python virtual environment made with another Python version (e.g. a 2.14 install on Rocky 9, whose venv used the system Python 3.9): `venv/bin/python` stayed on the old Python while the requirements were installed for the new one, so the workers ran the old interpreter with old or missing packages. The installer now rebuilds a venv whose Python doesn't match (or no longer runs), for OpenVDM's venv and TiTiler's; a matching venv is reused as before. Packages installed into the venv by hand (e.g. matplotlib) need reinstalling after a rebuild (#328)
- Fix the installer leaving an existing install on its old code: it updated the checkout as the OpenVDM user, which couldn't replace files the 2.14 installer had left owned by root (`www/`), and carried on when git failed, so a 2.14 → 2.16 upgrade kept 2.14's web app (e.g. `Undefined variable $date` in `TransferLogs.php`). It now gives the OpenVDM user the whole checkout first, discards npm's rewrite of `www/package-lock.json`, and stops with git's message if fetching, checking out or fast-forwarding the branch fails. Also fix the installer's error checks (no supported OS, PHP or Python, gearmand build failure) printing "Exiting." and carrying on instead of stopping (#334)
- Remove leftover debug output: the data dashboard wrote a bare data type name into pages and `api/dashboardData` responses (corrupting the JSON) when a file had no visualizer data, stats or quality tests for the requested data type, and **Finalize Current Lowering** printed two timestamps before redirecting, which could stop the redirect (#308). A lowering tab also dumped the raw `datadashboard.yaml` entry of a data type whose `visType` it doesn't draw; it now says "No data found", like default tabs (#312)
- Fix the Configuration page after **Setup New Lowering** logging `Undefined array key "requiredCruiseDataTransfers"` (and `cruiseDataTransfers`) and showing empty cruise data transfer status panels. The actions that show the page after a task each built their own copy of its data and had drifted apart; after any task, the Finalize buttons also showed as not finalized, and after Setup New Cruise the lowering panel was hidden. They now share one set (#336)

---

## [2.15.8] – 2026-09-19

### Fixed
- Fix cruise data transfer connection test passing when a required local destination mountpoint is unmounted, and fix an `UnboundLocalError` on the equivalent active-transfer validation path (#112)
- Fix collection system transfer ownership/permissions failure being reported as both Fail and Pass and the job continuing anyway; fix a malformed (non-f-string) reason string in `set_owner_group_permissions` (#114)
- Fix collection system transfer destination ownership/permissions being skipped based on the source directory's mountpoint flag instead of always being applied, since the destination is never itself a mountpoint for CST (#116)

---

## [2.15.7] – 2026-09-12

### Fixed
- Clarify the "Incorrect Filenames Detected" panel: it now switches to a danger-styled panel with a tooltip only when incorrectly named files are actually present, making clear those files were not transferred into the cruise data directory (#109)

---

## [2.15.6] – 2026-09-04

### Fixed
- Fix `stop_job` selecting the first running cruise data transfer or scheduled task with a nonzero PID instead of the one matching the requested PID, which could stop the wrong job (#104)
- Fix cruise data transfer exclusion lists going stale during long-running rclone transfers: lowering-level excluded collection systems, extra directories, and lowering config files are now matched with a wildcard on the lowering ID instead of an explicit list of lowerings known at transfer start, so lowerings created mid-transfer are still excluded (#103)

---

## [2.15.5] – 2026-08-19

### Fixed
- Fix data dashboard manifest incorrectly dropping entries when a single raw data file is processed into multiple dashboard data types (e.g. a plugin running more than one parser against the same file); the incremental update and removal logic now keys on raw file + data type instead of raw file alone
- Fix `FutureWarning` from deprecated `DataFrame.swapaxes` in the GGA parser's gap-splitting logic

### Changed
- Dependency versions updated to latest safe patch/minor releases

---

## [2.15.4] – 2026-07-23

### Changed
- Dependency versions updated to latest safe patch/minor releases
- Install script now aborts with a clear error if building gearmand/libgearman from source fails on RHEL-based installs, instead of continuing with a broken PHP-gearman build

### Fixed
- Fix wildcard source directory expansion for SSH Server collection system transfers: a misplaced `--protect-args` flag broke the remote directory listing
- Failed remote directory listings during wildcard expansion (rsync/SSH) are no longer silently reported as "no directories matched"; the underlying connection/command error is now logged

---

## [2.15.3] – 2026-06-23

### Fixed
- `postFinalizeCurrentCruise` hooks now run before Cruise Data Transfers so files they produce are included in transfers (closes #102)
- Fix PHP warning when `DATA_ROOT` is unreadable by the web server (`scandir` now guarded with `is_readable`)
- Fix `chcon` errors on SELinux-disabled systems or NFS-mounted `DATA_ROOT`
- Enable `httpd_use_cifs` SELinux boolean on RHEL-based installs to allow Apache to read SMB-mounted directories
- Set SELinux context on `/var/log/openvdm` so Apache can read transfer logs on RHEL-based installs

---

## [2.15.2] – 2026-06-19

### Changed
- Migrate `build_lowering_tracks` and `build_overlay_layers` workers to `build_cruise_tracks` architecture
- Migrate legacy parsers to `read_lines_with_timestamps` architecture (closes #100)

### Fixed
- Fix install script for Ubuntu 26.04: dynamic PHP version detection and MySQL fallback

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
