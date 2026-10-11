# Changelog

All notable changes to OpenVDM are documented here, organized by release tag against the `master` branch.

---

## [2.17.0] – Unreleased

**Upgrading:** the step-by-step instructions will be in INSTALL.md.
- **Database:** update it with `database/openvdm_216_to_217.sql`. From 2.16.0, run `database/openvdm_2160_to_2161.sql` first.
- **Trackline hooks:** in your `openvdm.yaml`, remove `-u` from the `build_cruise_tracks.py` and `build_lowering_tracks.py` hooks, and change any 2.16.0 option names that 2.16.1 and 2.16.2 warned about: `--no_combine`, `--kml_only`, `--geojson_only`, `--config_file` and `--gps-sources` (#388, #392).
- **Trackline scripts:** copy the updated `build_cruise_tracks.py.dist` and `build_lowering_tracks.py.dist` over your copies, keeping your own position sources (#366, #399).
- **Vessel settings:** re-run the installer, which asks for them, or copy the `vessel` block from `openvdm.yaml.dist` into your `openvdm.yaml` (#365).
- **Python packages:** 2.17 needs Jinja2 for the cruise README. Re-running the installer installs it, or run `pip install -r requirements.txt` in OpenVDM's venv as the OpenVDM user. Then restart the workers (#431).

### Added
- **Cruise Description:** an optional, multi-line description on the Setup New Cruise and Edit Cruise forms. It's returned by `getCruiseConfig` (and `api/warehouse/getCruiseDescription`), saved in each cruise's `ovdmConfig.json`, and shown on the main page's cruise information panel. Cruises from before 2.17 have an empty description. The CoreVars `value` column becomes `text`, since `tinytext` holds only 255 bytes (#367).
- **Vessel settings in `openvdm.yaml`:** a `vessel` block with the vessel's name and contact (institution, email), and, only for vessels that submit data to R2R, an `r2r` sub-block with R2R's vessel, operator and scheduler IDs.
  - The installer asks for them. It asks for the R2R IDs only if the vessel submits data to R2R (default no), and on a re-run it keeps the values in `openvdm.yaml`.
  - Each cruise's `ovdmConfig.json` gets the block as `vessel`, and `OpenVDM.get_vessel_config()` returns it for plugins and hooks (#365).
- **Descriptions for collection systems and extra directories:** an optional, multi-line Description on the add and edit forms of collection system transfers and extra directories, required ones included, says what a directory holds. It's shown as a tooltip on the long name in their lists, returned by the API and `getCruiseConfig`/`getLoweringConfig`, and saved with each entry in `ovdmConfig.json` and the lowering config file. The required `Dashboard_Data` and `From_PublicData` directories come with a description; the database update adds it unless you've written your own. Existing entries have no description until you add one (#432).
- **File Naming Guide:** a new page, linked from the Collection System Transfers page, tells the technicians who set up the acquisition systems what each collection system's files must be called to be copied, from its Include, Exclude and Ignore filters as they are now. It's laid out to print (or save as PDF) to post by a workstation.
  - **For each enabled collection system** (disabled ones optionally, or one at a time): its description, where its files are collected from (no credentials), and its patterns in words with the cruise and lowering IDs filled in, e.g. `*{cruiseID}*.raw` is "anything, then `RR2601`, then anything, then `.raw`", with an example name where the pattern pins one down.
  - **What happens to each file:** copied (matches an Include pattern), not copied and listed under Filename Errors (matches an Exclude pattern, or no Include pattern), or skipped without being reported (Ignore). Plus the other rules that apply: case-sensitive names, ASCII-only names, the cruise or lowering dates (Use start date), files still being written, empty files and the default-ignored system files.
  - **Patterns that can never match** for their transfer type are flagged, e.g. an SMB or FTP pattern that doesn't start with `*`, since those files are checked by a path under a temporary mount point.
  - A key explains the placeholders (`{cruiseID}`, `{loweringID}`, `{YYYY}`, `{YY}`, `{mm}`, `{DD}`, `{HH}`, `{MM}`, `{SS}`) (#451).
- **Description templates:** so that descriptions are written the same way, a new collection system transfer's Description starts from a template asking for its source, files and file types, and sub-directories, and a new extra directory's for its contents, file types and sub-directories. The add forms start with the template; on the edit forms, a **Use template** button fills an empty Description with it. A line still showing its `<...>` prompt when the form is saved is left out, so an untouched template saves no description. The templates are `CST_DESCRIPTION_TEMPLATE` and `EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE` in `Config.php` (set one to `''` to turn it off); without them, as in a `Config.php` from before 2.17, the defaults are used. The required `Dashboard_Data` and `From_PublicData` directories' descriptions follow the template, and the READMEs keep each line of a description on its own line (#449).
- **Cruise README:** OpenVDM writes a `README.md` at the top of the cruise directory describing the cruise and its layout, for whoever opens the cruise data later. It's rebuilt whenever the cruise config is exported: Setup New Cruise, Edit Cruise, Finalize (before the cruise data transfers) and Export OpenVDM Config.
  - **Contents:** the cruise details (name, description, vessel, chief scientist, dates, ports, location, extent, finalized date, contact); each enabled collection system's and extra directory's folder with its long name and description (#432); each lowering's layout, when lowerings are used; and OpenVDM's own files (cruise config, MD5 summary, data dashboard manifest).
  - **Template:** a Jinja2 template, `server/etc/cruise_readme.md.j2`, which the installer copies from its `.dist` when it doesn't exist yet; edit it to change the README. Until there's a copy (e.g. an upgrade without re-running the installer), the `.dist` is used. The new `cruiseReadme` block in `openvdm.yaml` turns the README off, renames it or points to another template. Without the block, the README is written as `README.md` from the default template.
  - **An existing README is kept:** OpenVDM marks the first line of the file it writes, and won't replace a file of that name it didn't write, e.g. one a collection system copied to the top of the cruise directory. It reports that instead.
  - **Rebuild it any time:** the new **Rebuild the Cruise README** maintenance task on the Configuration page rebuilds it from the template, e.g. after you edit the template or a directory's description. It too leaves a README that OpenVDM didn't write alone. The database update adds the task.
  - **Failures:** a README that can't be written fails Export OpenVDM Config and Rebuild the Cruise README. Setup New Cruise and Finalize carry on and post an OpenVDM message.
  - The README is added to the MD5 summary and belongs to the warehouse user (#431).
- **Cruise extent:** `bin/build_cruise_tracks.py` sets the current cruise's bounding box (`cruiseExtent`) from one position source's whole track on every run.
  - **Source:** the position source marked `extent: true`, else the first.
  - **Antimeridian:** a track that crosses it gives westernmost > easternmost, as R2R does.
  - **Where it's available:** `getCruiseConfig` (and `api/warehouse/getCruiseExtent`) and each cruise's `ovdmConfig.json`.
  - **New cruises and switching:** Setup New Cruise clears it, and switching cruises in Edit Cruise loads that cruise's extent.
  - **Setting it:** only workers can, through `api/warehouse/setCruiseExtent` with the worker key. `--no-extent` skips it. If nav-qa-processing's OpenVDM hook sets the extent from its quality-checked fixes, add `--no-extent` to the `build_cruise_tracks.py` hook.
  - **Failures:** if setting the extent fails, the script reports it and exits 1, as it does for a failed MD5 update, so the hook's OpenVDM message says why (#366, #388).
- **Lowering README:** each lowering's directory gets a `README.md` too, for when a dive's folder is handed on by itself (#445).
  - **Contents:** the lowering's ID, dates, extent and finalized date; the cruise it belongs to and the vessel; each enabled lowering-level collection system's and extra directory's folder with its long name and description; and its config file, with where the cruise's MD5 summary and the lowering's data dashboard manifest are.
  - **When it's built:** after each lowering config export (Setup New Lowering, Finalize Lowering, Export Lowering Config), and by the new **Rebuild the Lowering README** maintenance task (shown when lowerings are used). Unlike the cruise README, a failure fails these tasks, since the README is their last step.
  - **Template and settings:** `server/etc/lowering_readme.md.j2`, which the installer copies from its `.dist` when it doesn't exist (the `.dist` is used until then), and a `loweringReadme` block in `openvdm.yaml` like `cruiseReadme`.
- **README file names with the cruise or lowering ID:** the `filename` of `cruiseReadme` may use `{cruiseID}`, and that of `loweringReadme` `{cruiseID}` and `{loweringID}`, e.g. `"{cruiseID}_{loweringID}_README.md"` for `RR2601_J2-1601_README.md`, so a README is still identifiable once it's separated from its folder. Keep the quotes: a name starting with `{` is a YAML error without them. `{loweringID}` can't be used for the cruise README, which covers every lowering (#447).
  - The same safeguards as the cruise README: no credentials reach the template, a README OpenVDM didn't write is never replaced, and the file belongs to the warehouse user and is added to the MD5 summary.
- **Lowering extent:** `bin/build_lowering_tracks.py` sets the current lowering's bounding box (`loweringExtent`) the way `build_cruise_tracks.py` sets the cruise's, for tools that need a dive's area.
  - **Source:** the position source marked `extent: true`, else the first. Across the antimeridian, westernmost > easternmost. `--no-extent` skips it, and with `-l` it's only set for OpenVDM's current lowering. If setting it fails, the script exits 1.
  - **Where it's available:** `getLoweringConfig` (and `api/warehouse/getLoweringExtent`), and so each lowering's `loweringConfig.json`, which is where earlier lowerings' extents are kept. Only workers can set it, through `api/warehouse/setLoweringExtent` with the worker key.
  - **Setup and switching:** Setup New Lowering and Setup New Cruise clear it. Switching to another lowering (in Edit Lowering, or the latest lowering Edit Cruise selects) loads that lowering's extent from its `loweringConfig.json`.
  - The code that picks the source and computes the extent is shared by both scripts in `server/lib/tracks.py` (#399).
- **`openvdm.yaml.dist` trackline hook examples:** commented-out `postDataDashboard` blocks for `build_cruise_tracks.py` and `build_lowering_tracks.py`. Each uses the `{collectionSystemTransferName}` token for the collection system, and shows `--position-sources`, `--extra-directory` and `--no-extent` commented out (#396).

### Changed
- **Setup New Cruise deletes all OpenVDM messages,** so the Messages page and the navbar's new-message count only show messages about the current cruise. They're deleted once the form passes its checks, before the new cruise is set up, so a message the setup posts (e.g. that it failed) is kept. A rejected form deletes nothing, and Edit Cruise, Finalize and switching cruises don't delete messages (#403).

### Removed
- **Trackline scripts' 2.16.0 options:** `build_cruise_tracks.py` and `build_lowering_tracks.py` no longer accept the names that 2.16.1 deprecated:
  - `--no_combine`, `--kml_only` and `--geojson_only`; use `--no-combine`, `--kml-only` and `--geojson-only`;
  - `--config_file` and `--gps-sources`; use `--position-sources`.
  - `-u/--username` is removed too: `-o` output keeps whoever wrote it, and extra directory output belongs to the warehouse user, as before.
  - A hook that still uses one stops with a usage error (#388, #392).

### Fixed
- **Transfer passwords in the workers' debug logs:** when a worker runs with debug logging (`-v`, e.g. while troubleshooting; Supervisor starts them without it), it logged each job's payload as it was. A Test Setup job's payload carries the add or edit form's fields, including any password typed into it. The SSH cruise data transfer also logged its rclone remote's `pass`, which `rclone reveal` turns back into the password. Payloads are now logged with every non-empty `rsyncPass`, `smbPass`, `sshPass` and `ftpPass` shown as `****` (`transfer_utils.redact_payload()`), a payload that isn't valid JSON isn't logged, and the rclone remote's `pass` is shown as `****` (#430).

---

## [2.16.2] – 2026-10-11

**Upgrading:** follow "Upgrading from 2.16.1" in [INSTALL.md](INSTALL.md). There's no database update, and the installer doesn't need to be re-run:
- re-copy the `.dist` version of the parsers you use over your copies (`git pull` doesn't update them): `gga`, `dpt`, the other NMEA parsers, and the parsers with direction charts (#410, #416, #418, #419);
- in your plugins, change `DBTParser` to `DPTParser` (#419), and add `'require_checksum': False` to the `parser_options` of any NMEA parser whose instrument doesn't send a checksum (#418);
- copy the updated `bin/build_remote_directory.py.dist` if you use it (#426, #428), and remove the `CollectionSystem:` line from `DEFAULT_POSITION_SOURCES_YAML` in your trackline scripts (#412);
- set `SITETITLE` in `Config.php` to v2.16.2, restart the workers (`supervisorctl restart openvdm:*`) so transfers stop putting SMB and SSH passwords on the command line (#424, #426), and rebuild the data dashboard.

### Added
- **Scripps MetAcq `$WICOR` parser** (`wicor_parser.py.dist`), for SIO's ships, which log MetAcq's underway data with OpenRVDAS (R/V Robert Gordon Sproul and R/V Sally Ride). It reads OpenRVDAS log files of `$WICOR` lines; MetAcq's own `.COR` files aren't supported. It reads the `value,TAGn` pairs by tag, since each ship's MetAcq setup decides which values are written and in what order. A second sensor with the same tag is `<tag>_2`, e.g. `WS_2`. Values flagged out of range, emulated or invalid (digit 7, 8 or 9), and the `-99` and `99999999` markers, are left out and counted in that value's Validity stat. Lines with a bad checksum are rejected.
  - **One output per category:** `category` charts every field of one kind in the file, second sensors included, so each kind is its own data type on the Data Dashboard with only a few series: `air` (air temperature, relative humidity and sea-level pressure), `dew_point`, `precipitation`, `radiation`, `wind_speed`, `wind_direction`, `water_temp`, `tsg`, `oxygen`, `fluorometer`, `optics_chem` (optics and carbonate chemistry) or `usw_system` (underway seawater flow, line pressure, pump and overflow status). `fields` picks the values instead; one of the two is required. The met, radiation, wind and seawater tags in SIO's OpenRVDAS `wicor_params.yaml` can be charted, with their units. The Fahrenheit and knots copies of values, the RH module's air temperature, the station barometer, the uncorrected TSG conductivity, and navigation (position included), depth, gravity, magnetics, winch and CTD values, are left out; other parsers handle the latter.
  - `max_delta_t` (default 60 s) is the longest expected time between lines; longer gaps count against the DeltaT Validity stat, whose name gives the limit, and the DeltaT quality test.
  - The parser isn't listed in `openrvdas_plugin.py.dist`: SIO's ships add it to their own `openrvdas_plugin.py`, one entry per category (#408).
- **Valeport thru-hull SVS parser** (`ssv_valeport_parser.py.dist`), for R/V Sally Ride's Valeport SVS logged by OpenRVDAS (logger `ssv_valeport`): each line is temperature (°C) and sound velocity (m/s) separated by a space, e.g. `21.830 1487.9`, which `ssv_parser` can't read. Charts sound velocity and temperature, with Bounds and Validity stats and quality tests for both (#422).

### Fixed
- **Direction charts near north:** the data dashboard's 1-minute averages took a plain mean of wind direction, heading and course, so readings either side of north (e.g. 359° and 1°) plotted as the opposite direction (180°), a false spike whenever the value crossed north within a minute. `resample_data()` now takes `angle_cols`, which it averages as angles (from the mean sine and cosine) and returns in 0–360°. The `met`, `metpakpro`, `twind`, `mwv`, `wind_gill_wo75`, `mwd`, `hdt`, `vtg`, `gnss`, `hpr`, `pashr` and `psxn23` parsers pass their direction columns, and `wicor_parser` uses it instead of its own averaging. Only the plotted series change; the stats and quality tests come from the raw values, as before. A direction logged as −180–180° is now plotted as 0–360° (#410).
- **Trackline scripts with another collection system:** `build_cruise_tracks.py` and `build_lowering_tracks.py` stopped with `position sources CollectionSystem mismatch: OpenRVDAS != <name>` when run for a collection system not named in their built-in position sources (`OpenRVDAS`, `ROV_OpenRVDAS`), unless given a `--position-sources` file. The `CollectionSystem` key of a position sources YAML is now optional: without it, the sources apply to the collection system the hook names; with it, it must still match. The built-in sources no longer set it (#412).
- **GGA parser and corrupt sentences:** the parser didn't check the NMEA checksum, so sentences that a serial logger had spliced together or cut short were read as positions. Out-of-range ones stopped the whole file (`Latitude must be in the [-90; 90] range.`), and the rest skewed the track, Geographic Bounds and Distance Traveled; on an R/V Sally Ride Hemisphere log, 14% of the GGA lines were corrupt. A GGA line now counts as a bad row unless its checksum is present and matches, it has its 15 fields, its latitude and longitude are `ddmm.mmmm`/`dddmm.mmmm` with `N`/`S` and `E`/`W`, and its altitude units are `M`. `OpenVDMCSVParser.nmea_checksum_ok()` is the shared checksum check (#416).
- **`dpt_parser` read DBT, not DPT:** it's documented as a parser for NMEA DPT (depth) sentences and uses DPT's fields, but it filtered on `DBT`. So DPT logs gave no depth at all, and DBT logs gave their first field, depth in feet, labelled as metres (about 3.3 times too deep). It now reads DPT sentences. The class is renamed `DPTParser`: a plugin that imports `DBTParser` now fails to load until it's changed. DBT sentences aren't read; they'd need their own parser (#419).
- **NMEA parsers and corrupt sentences:** like the GGA parser (#416), the `hdt`, `vtg`, `mwd`, `mwv`, `dbs`, `dpt`, `xdr`, `psxn23`, `psxn24`, `pashr`, `gnss` and `hpr` parsers read whatever a spliced or truncated sentence held; on R/V Sally Ride's Hemisphere log, VTG course over ground reached 24 million degrees and HDT heading 260,188°. A line now counts as a bad row if its checksum doesn't match; where the sentence has a fixed number of fields or fixed unit letters (HDT, VTG, MWD, MWV, DBS, DPT, PSXN,23/24), if those don't match either. A line without a checksum is a bad row too, as for GGA; for instruments that don't send one, set the new `require_checksum` parser option to `False` (`--allow-missing-checksum` on the command line). `OpenVDMCSVParser.check_nmea_sentence()` is the shared check (#418).
- **SMB passwords in transfer error messages:** a failed SMB mount or share listing could show the transfer's password in clear text in the OpenVDM message, the transfer's error status and the Test Setup results, for collection system and cruise data transfers alike. The password was on the `mount` and `smbclient` command lines, and when the command failed without an error message (or `smbclient` timed out), the reason was Python's error text, which includes the command line. The username and password are now passed in a temporary credentials file readable only by its owner (`mount.cifs` `credentials=`, `smbclient -A`), deleted as soon as the command finishes, so they're never on the command line or in `ps`. This also lets an SMB password contain a comma, which split the old mount options. The SSH cruise data transfer now passes its password to `rclone obscure` on stdin, as FTP already did, for the same reason (#424).
- **SSH passwords on the command line:** SSH transfers that log in with a password ran `sshpass -p <password>`, so until `sshpass` started any local user could see the password in `ps`, as could any error text that included the command line. The collection system transfer (source listing and transfer), the ship-to-shore transfer, Test Setup's SSH checks and the macOS check now pass the password to `sshpass -f` in a temporary file readable only by its owner, deleted as soon as the command finishes. `bin/build_remote_directory.py.dist` did the same with SSH and SMB passwords and also wrote them to its debug log; it now uses `sshpass -f` and an `smbclient -A` credentials file (#426).
- **`build_remote_directory.py` did nothing:** the `postSetupNewCruise`/`postSetupNewLowering` hook script compared each transfer's type with strings (`"1"`, `"3"`, `"4"`), but the API returns numbers, so it skipped every collection system. Its commands were broken too: template paths kept the collection system's directory and unreplaced `{cruiseID}`s (`<source_dir>/XBT/{cruiseID}/raw_data` instead of `<source_dir>/RV1001/raw_data`), seed files were copied from the destination instead of the template, and its `smbclient` and `ssh` commands were malformed. It's rewritten:
  - The template is copied with `{cruiseID}` and `{loweringID}` replaced in every directory and file name, as its documentation describes.
  - SMB shares are mounted read-write and copied to like a local directory; SSH servers get `ssh mkdir -p` (or a `test -d` check) and `rsync --ignore-existing`, using the transfer's key or password (`sshUseKey`), and the workers' timeouts and host-key options.
  - Files that already exist are never overwritten, so it can be run again; the source directory must exist unless `-s` is given; a source directory with a wildcard is an error.
  - It exits with status 1 if any collection system failed, instead of always 0 (#428).

## [2.16.1] – 2026-10-10

**Upgrading:** follow "Upgrading from 2.16.0" in [INSTALL.md](INSTALL.md):
- update the database with `database/openvdm_2160_to_2161.sql` (#389);
- copy the updated `.dist` files you use over your copies: the CTD profile parser, `build_cruise_tracks.py` and `build_lowering_tracks.py` (keeping your own position sources), and the new `plot_ctd_casts.py` if wanted;
- change your trackline hooks to the new option names and remove `-u`; the `Tracklines` extra directory they write to must exist and be enabled;
- set `SITETITLE` in `Config.php` to v2.16.1, restart the workers (`supervisorctl restart openvdm:*`), and rebuild the data dashboard to add the new CTD tests and stats to existing casts.

### Added
- **CTD profile quality tests** for problems that used to pass silently:
  - `XMLCON NMEA Position`: the deck unit is set to append the NMEA position to each scan;
  - `HEX Header Position` and `HEX Scan Positions`: the `.hex` header and scans have positions;
  - `HEX Lost Scans`: gaps in the scans' modulo counter;
  - `Ranges`: temperature, conductivity, salinity and pressure within plausible limits, with a `<Variable> Validity` stat for each. The `ranges` parser option (`--<variable>Range` on the command line) changes the limits, e.g. for fresh water (#368).
- **Queue an MD5 summary update for files a hook or script writes** into the cruise directory, which no transfer or data dashboard job lists: `OpenVDM.update_md5_summary()` in Python, or `utils/update_md5_summary.py FILE... [--deleted FILE...] [-c/--cruise-id ID] [--wait]` on the command line. Paths are relative to the cruise directory, or absolute inside it (#373, #398).
- **CTD profile plots in an extra directory:** `bin/plot_ctd_casts.py.dist`, run as a `postCollectionSystemTransfer` hook (example in `openvdm.yaml.dist`), saves a PNG plot of each new or updated cast, or of a cast whose `.xmlcon` arrives later, in an extra directory (`CTD_Plots` by default). The plots are part of the cruise, owned by the warehouse user and added to the MD5 summary. `--all --collection-system <name>` re-plots every cast. Its options: `-e/--extra-directory`, `--collection-system`, `-c/--cruise-id`, `--all` (#398). The script needs matplotlib (not in `requirements.txt`) and exits with a message if it's missing (#372).

### Changed
- **CTD profile plot header:** the Date is the cast's start date (`System UTC`), the Cast is the file's basename, and Depth is the cast's maximum depth calculated from pressure, left out when it can't be calculated. They had come from `** Date:`, `** Cast:` and `** Bottom Depth:` header lines, which most ships don't write that way (#376).
- **CTD profile plot position:** the plot header gives the cast's position in decimal degrees (`Position: lat 27.61917, lng -93.86167`): the header's NMEA position, else the first scan's. It's left out when the cast has no position (#379, #381).
- **Post-hook failures say why:** the OpenVDM message for a failed hook command now gives the command's name, exit status and the end of its error output (stderr, or stdout if that's empty), instead of only its command line. Message titles and bodies are now shown as text on the Messages page and in the message list, not as HTML (#378).

### Fixed
- **Cruise data exclusions for paths saved with a trailing `/`:** a collection system or extra directory whose destination directory ended in `/` (saved before the forms started removing it, #96) gave an exclusion such as `Sensors/Example//**`, which excluded nothing, so cruise data transfers copied it anyway. `database/openvdm_2160_to_2161.sql` removes the trailing `/` from existing records (root paths, empty values and NULL are left as they are). Start running transfers again afterwards so they rebuild their filters (#389).
- **Trackline scripts' output folder:** `build_cruise_tracks.py` and `build_lowering_tracks.py` crashed when there was no `Tracklines` extra directory, used its `destDir` without filling in `{cruiseID}` and `{loweringDataBaseDir}`, and wrote to it when disabled. They now exit with a message when it's missing, disabled or has no folder; `build_cruise_tracks.py` refuses a per-lowering one. `build_lowering_tracks.py` puts the tracklines in the lowering when `Tracklines` is a lowering-level extra directory, where OpenVDM creates it, not in the cruise. `-e/--extra-directory NAME` writes to another extra directory; it can't be used with `-o` (#401).
- **Tracklines in the MD5 summary:** the trackline files written to an extra directory are queued for the cruise's MD5 summary (new or updated); a failed update exits 1 with a message. They always belong to the warehouse user; `-u/--username` now applies only to `-o` output, which still isn't added to the summary (#401).
- **Trackline scripts share their code:** the code common to both scripts is now in `server/lib/tracks.py` (as in 2.17, #394), so future fixes arrive with an OpenVDM update instead of a new `.dist` copy. The scripts take the 2.17 option names: `--no-combine`, `--kml-only`, `--geojson-only`, and `--position-sources` for `--config_file` (cruise) or `--gps-sources` (lowering). The sources YAML's list can be called `PositionSources` (`GPSSources` still works). The 2.16.0 names `--no_combine`, `--kml_only`, `--geojson_only`, `--config_file`, `--gps-sources` and `-u/--username` still work but print a deprecation warning, and post it as an OpenVDM message (`<script> uses deprecated options`, posted again only after it's been read): they will be removed in 2.17, so change your `openvdm.yaml` hooks to the new names and drop `-u` (#401).
- **`openvdm.yaml.dist`:** removed the `postCollectionSystemTransfer` example for `bin/r2r_nav_manager.py`, which doesn't exist (#401).

---

## [2.16.0] – 2026-09-28

**Highlights**
- **FTP Server transfers**, for collection system sources and cruise data destinations.
- **Depth profile charts**, and parsers for **Sea-Bird SBE 9plus CTD** and **MK21 XBT** casts, with each cast's position on the map.
- **Transfers report failures**: a failed rsync or rclone transfer, or a source that can't be listed, no longer passes. With Sync from source on, an unlistable source had emptied the destination.
- **Keyless basemaps** (CARTO now needs an API key), tracks colored by data type, and point markers.
- **Installer**: tested with fresh installs and 2.15.8 upgrades on Rocky Linux and AlmaLinux 9 and 10, and Ubuntu 22.04 and 24.04. Safer re-runs, and step-by-step upgrades from 2.14 and 2.15.

**Upgrading:** follow "Upgrading from 2.15" (or "from 2.14") in [INSTALL.md](INSTALL.md):
- set aside `Config.php`, `openvdm.yaml` and `datadashboard.yaml`, re-run the installer, and merge your settings back into the 2.16 files;
- update the database with `database/openvdm_215_to_216.sql`;
- copy the updated `.dist` files you use over your copies:
  - the GeoTIFF, TSG45, HPR and GNSS parsers;
  - the ROV OpenRVDAS plugin (keep `SEALOG_SERVER_URL` and `SEALOG_JWT`);
  - `bin/build_remote_directory.py`;
  - `custom1.js`;
- in your own `datadashboard.yaml`, remove `- lowering` from the Position tab's `jsArray`, and add `charts-zoom` to any Lowering tab;
- rebuild the data dashboard.

The detailed notes for each change are in the [full 2.16.0 changelog](https://github.com/OceanDataTools/openvdm/blob/f1d28e7d83cbc2e1b95d6d7e4b51f454796cdd55/CHANGELOG.md#2160--2026-09-28) and the linked issues.

### Added
- **FTP Server transfers**:
  - collection system sources are mounted with `rclone mount` and copied with rsync, as for SMB;
  - cruise data destinations are copied with rclone, as for SSH;
  - the server field takes `host[:port]`;
  - plain FTP only, not FTPS;
  - needs the database update. The installer adds `fuse3` (#17, #199).
- **Depth profile charts** (`visType: json-profile`, with optional `depthSeries` and `profileSeries`) on default and lowering tabs and the main page (#274). The inverted charts (`json-inverted`, `json-reversedY-inverted`) work again (#275).
- **Sea-Bird SBE 9plus CTD parser and plugin** (`ctd_profile_parser.py.dist`, `ctd_plugin.py.dist`), based on code by Oscar Garcia (CSIC):
  - pressure, temperature, conductivity, salinity and depth, matching Sea-Bird's own data conversion;
  - the cast's geographic bounds;
  - its position on the map (`ctd-position`);
  - optional PNG plots (#286, #290, #292, #304, #324).
- **MK21 XBT parser and plugin** (`xbt_parser.py.dist`, `xbt_plugin.py.dist`), built on Peter Shanks' (AADC) xbt-edf-qc library:
  - QC'd temperature and sound velocity profiles, and launch positions (`xbt-position`);
  - the library isn't in `requirements.txt`, and the sample data install adds it (#300).
  - The position data types have no stats, and show times as ISO 8601 UTC (#314, #320).
- **Plugin API**: optional `get_source_files(filepath)` to re-parse a related file, e.g. a CTD cast when its `.xmlcon` arrives (#288); `format_iso8601()` in `openvdm_plugin.py` (#320).
- **Maps show GeoJSON points** as circle markers with property popups. Point data types get no Latest Position or Start/End Positions checkbox (#292, #316, #322).
- **New installs' default cruise** matches the sample data (Gulf of Mexico) (#293).

### Changed
- **Basemaps**:
  - CARTO is replaced by keyless OpenStreetMap, Esri and GMRT layers, with label and seamark overlays;
  - all maps share one tile-layer helper in `mapBaseLayers.js`;
  - sites with their own `custom1.js` update it from `custom1.js.dist` (#121, #298).
- **Map tracks** are drawn in the chart palette's colors, one per data type (#195).
- **The data dashboard leaves out what has nothing to show**:
  - on the Data Quality tab, files without stats or quality tests;
  - on the other tabs, cards with no files (#310).
  - Rebuild Data Dashboard deletes dashboard files that are no longer in the manifest (#318).
- **Transfer forms**:
  - a Transfer Type dropdown and example placeholders (#226, #227);
  - a `:` in a cruise data Destination Directory (an rclone remote) is allowed only for Local Directory (#199).
- **More system and NAS folders and files are ignored by default** (`lost+found`, recycle bins, snapshots, Office lock files, …), and they're skipped while listing the source (#265).
- **SSH-key transfers** use the key ssh would use (`~/.ssh/config`, or root's default keys), not only `id_rsa` (#340).
- **Installer**:
  - builds the web app as the OpenVDM user, with nvm in that user's home on Debian/Ubuntu, and runs `composer install --no-dev` (#130, #183);
  - on Debian/Ubuntu, installs PHP 8.3 (8.5 on Ubuntu 26.04, the only version there); uses Python 3.11–3.14 (#352);
  - creates root's SSH key with the system's default type, and relabels it for SELinux (#340);
  - installs the kernel modules for `cifs` and `fuse` when they're missing (#356);
  - defaults the OpenVDM user's database password to root's, and the Supervisor password to that user's (#344).
  - With sample data, it also sets up a local FTP server, turns on lowering components, and sets up a sample lowering and the example Lowering tab (#200, #201, #272).
- **Dependencies**: pandas 2.3.3 (#330); js-cookie 3.0.8, moment-timezone 0.5.x, and moment as a direct dependency (#128, #181). Bootstrap 3's `npm audit` finding remains (#178).
- **Removed**:
  - the DBS parser's unused `no_mag` option; site plugins passing it get a `TypeError` (#147);
  - the unused `OpenVDM.get_logfile_purge_timedelta_str()` (#169).
- **Development**: ESLint, `php -l` and PHPStan run in the pre-commit hooks; pylint is fixed; docstrings across `server/` (pdoc). No effect on running installs (#128, #130, #131, #132, #135, #140, #141, #143, #144, #160, #161).
- **INSTALL.md**: step-by-step upgrades from 2.14 (in place, or on a fresh OS) and from 2.15 (#326, #338, #354).

### Fixed
**Transfers**
- Failed rsync and rclone transfers are no longer reported as successful. The reason includes the tool's error and the first failing file (#230, #237).
- A source that can't be listed (rsync, SSH, SMB, FTP, local) fails the transfer instead of passing with no files. With Sync from source on, that had emptied the destination (#206, #238, #264, #284).
- Cleanup no longer deletes files through an SMB or FTP share that's still mounted (#207).
- A collection system transfer that fails partway still processes the files it copied (#239).
- **rsync cruise data transfers**:
  - copied nothing (#249);
  - broke on subdirectory paths (#228);
  - couldn't use `/` as the destination (#247);
  - Test Setup left a `write_test.txt` behind (#233).
- Cruise data Test Setup now tests every rclone remote type, and its messages are clearer (#165, #166, #179).
- An SSH password was logged in plain text at debug level (#240).
- A password typed before Test Setup was lost on Update (#119).

**Data dashboard and parsers**
- Pages returned HTTP 500 once the Messages table grew large (#123).
- **GeoTIFF**:
  - overlays were misplaced for files not in lat/lon, and Geographic Bounds were mislabelled (#138, #158);
  - TiTiler layers didn't show on lowering tabs (#298).
- Lowering tabs' maps and charts hadn't loaded since 2.14, and the Position tab logged `Map container is already initialized`. Lowering-tab charts now match the default tabs (#185, #278).
- **Parsers**:
  - HPR and GNSS gave no output (#152);
  - TSG45 failed when files with and without an SBE 38 were parsed together (#146);
  - time cropping failed (#149);
  - the ROV OpenRVDAS plugin couldn't run (#150);
  - `round_data()` failed without a precision (#168).
- **Smaller dashboard fixes**:
  - a data type's stats were merged by position, not name (#306);
  - the page jumped when a chart was redrawn (#302);
  - file names wrapped in narrow cells (#280, #282);
  - the map marker shadow returned 404 (#193);
  - one plugin's import failure crashed the whole rebuild (#191).
- The Configuration page broke after Setup New Lowering (#336). Leftover debug output is removed (#308, #312).
- PHP warnings and deprecation notices (#125, #132, #135).

**Workers and installer**
- Update MD5 Summary failed when the cruise had no summary yet (#348).
- **Pre-2.15.5 `openvdm.yaml` files**: `KeyError: 'transferPublicData'`, and workers without `workerApiKey` got no transfer passwords (#187). Worker crash messages now name the real file and line (#187).
- The lowering base directory is created from New Cruise. A failed step is no longer reported as both Fail and Pass (#189).
- Error messages showed a tuple for an invalid transfer or task ID (#167). `bin/build_remote_directory.py` made directories with the wrong permissions (#164).
- **Installer**:
  - a venv made with another Python version is rebuilt (#328);
  - a 2.14 upgrade could be left on 2.14's code, and error checks didn't stop the install (#334);
  - a stale `composer.lock` warning (#346);
  - a `mysql:8.0` module error on RHEL 9 (#350);
  - failed setup steps are now reported (#212).

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
