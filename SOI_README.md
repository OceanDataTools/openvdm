# OpenVDM — Schmidt Ocean Institute Fork

This repository is a fork of [OpenVDM](https://github.com/oceandatatools/openvdm) maintained by
Schmidt Ocean Institute (SOI) for deployment aboard **R/V Falkor (too)**. It tracks the upstream
`master` branch and layers SOI-specific defaults, share paths, hooks, and parser configurations on
top.

## What is different from upstream

### Installation defaults

The install script (`utils/install-openvdm.sh`) ships with SOI-specific defaults so that hitting
`<Enter>` at every prompt produces a correct Falkor (too) deployment:

| Prompt | SOI default | Upstream default |
|---|---|---|
| Repository URL | `https://github.com/schmidtocean/openvdm` | `https://github.com/oceandatatools/openvdm` |
| Branch | `openvdm-soi` | `master` |
| OpenVDM user | `mt` | `survey` |
| CruiseData path | `/mnt/CruiseData` | `/data/CruiseData` |
| ParticipantData path | `/mnt/CruiseSandbox/ParticipantData` | `/data/PublicData` |
| VisitorInformation path | `/mnt/soi_data1/VisitorInformation` | `/data/VisitorInformation` |
| ScienceData path | `/mnt/soi_data1/ScienceData` | *(not present upstream)* |

### SMB shares

This fork adds a **ScienceData** SMB share (written to `/etc/samba/sciencedata.conf`, included from
`smb.conf`) that is world-readable/writable with no authentication required. It is intended for
scientists to post intermeditate dataset to be included in the final cruise dataset. The share lives on the secondary storage volume at
`/mnt/soi_data1/ScienceData` by default.

The four shares exposed after installation:

| Share name | Default path | Access |
|---|---|---|
| `CruiseData` | `/mnt/CruiseData` | Read-only for guests; `mt` user has write access |
| `ParticipantData` | `/mnt/CruiseSandbox/ParticipantData` | Read/write for all (no auth) |
| `VisitorInformation` | `/mnt/soi_data1/VisitorInformation` | Read-only for guests; `mt` user has write access |
| `ScienceData` | `/mnt/soi_data1/ScienceData` | Read/write for all (no auth) |

### Hostname and site root

The expected hostname for the OpenVDM server aboard Falkor (too) is **`rvfk-openvdm`**. The
`openvdm.yaml.dist` template defaults `siteRoot` to `http://rvfk-openvdm/` rather than the
upstream `http://127.0.0.1/`. The install script sets this value from the URL you supply at the
"IP Address or URL" prompt.

### Terminology

| Concept | SOI label | Upstream label |
|---|---|---|
| Vehicle deployments | Dive | Lowering |
| Vehicle data directory | Vehicles | Vehicle |
| Participant file share | ParticipantData | PublicData |

These are set in `www/app/Core/Config.php` at install time and reflected throughout the web UI.

### Cruise visibility

`showOnlyCurrentCruiseDir` is set to `True` in `openvdm.yaml.dist`, hiding all cruise directories
except the active one from the OpenVDM web interface and the `CruiseData` SMB share.

### Post-hook integrations

`server/etc/openvdm.yaml` contains two distinct hook mechanisms that work together.

#### `hooks` — Gearman task chaining

The `hooks` section lists additional OpenVDM Gearman tasks to fire as background jobs after a
primary task completes.  These are internal OpenVDM tasks, not shell commands.  The SOI
configuration wires them as follows:

| Primary task | Chained tasks (in order) |
|---|---|
| `runCollectionSystemTransfer` | `updateDataDashboard` → `updateMD5Summary` → `postCollectionSystemTransfer` |
| `updateDataDashboard` | `updateMD5Summary` → `postDataDashboard` |
| `rebuildDataDashboard` | `updateMD5Summary` → `postDataDashboard` |
| `setupNewCruise` | `postSetupNewCruise` |
| `setupNewLowering` | `postSetupNewLowering` |
| `preFinalizeCurrentCruise` | `preFinalizeCurrentCruise` |
| `finalizeCurrentCruise` | `postFinalizeCurrentCruise` |
| `preFinalizeCurrentLowering` | `preFinalizeCurrentLowering` |
| `finalizeCurrentLowering` | `postFinalizeCurrentLowering` |

The `post*` and `pre*` tasks in this list are handled by the `post_hooks.py` Gearman worker, which
executes the shell commands defined in the `postHookCommands` section below.

#### `postHookCommands` — shell commands

These are the actual external scripts that run for each lifecycle event.  Commands in the
`postCollectionSystemTransfer` and `postDataDashboard` hooks are **filtered by collection system
name** — each entry specifies a `collectionSystemTransferName` and only runs when the triggering
transfer matches that name.  All other hooks run a flat `commandList` unconditionally.

##### Token substitution

The following tokens are replaced in command arguments at runtime:

| Token | Value | Available in |
|---|---|---|
| `{cruiseID}` | Current cruise identifier | All hooks |
| `{loweringID}` | Current lowering identifier | All hooks |
| `{collectionSystemTransferID}` | Numeric ID of the triggering transfer | `postCollectionSystemTransfer`, `postDataDashboard` only |
| `{collectionSystemTransferName}` | Name of the triggering transfer | `postCollectionSystemTransfer`, `postDataDashboard` only |
| `{newFiles}` | Space-separated list of newly transferred file paths | `postCollectionSystemTransfer`, `postDataDashboard` only |
| `{updatedFiles}` | Space-separated list of updated file paths | `postCollectionSystemTransfer`, `postDataDashboard` only |

Tokens whose source data is unavailable in a given hook context are left as the literal token
string — they will not cause an error but also will not expand.  Command arguments that resolve to
an empty or whitespace-only string after substitution are silently dropped.  `{newFiles}` and
`{updatedFiles}` expand to a single space-joined string, not individual shell arguments.

##### `postCollectionSystemTransfer`

No active commands (the R2R NavManager example is commented out).  Add entries here to run
commands filtered to a specific collection system after every transfer cycle.

##### `postDataDashboard`

Runs after the data dashboard is updated for a collection system.  Two entries are active:

| Collection system | Command | Purpose |
|---|---|---|
| `OpenRVDAS` | `build_cruise_tracks.py OpenRVDAS` | Regenerate GeoJSON/KML cruise track files from GNSS dashboard data |
| `Processed_MB` | `build_overlay_layers.py Processed_MB` | Regenerate multibeam overlay GeoJSON from processed bathymetry dashboard data |

##### `postSetupNewCruise`

Runs after a new cruise is created in OpenVDM.  Two commands fire in sequence:

1. **Build OpenRVDAS logger config** — SSHes to `mt@10.23.9.21` and runs
   `/home/mt/shipboard-configurations/Systems/OpenRVDAS/bin/build_openrvdas_logger_config.sh`
   to generate a fresh OpenRVDAS configuration for the new cruise.

2. **Create Sealog cruise record** — SSHes to `mt@10.23.9.24` and runs
   `/opt/sealog-server-FKt/venv/bin/python /opt/sealog-server-FKt/misc/sealog_create_cruise_from_openvdm.py`
   to create a matching cruise record in the ship-side Sealog instance.

##### `postSetupNewLowering`

No active commands.  Add entries here to run commands when a new dive is created.

##### `preFinalizeCurrentCruise`

Runs before cruise finalization begins.  One command is active:

1. **Export Sealog cruise data** — SSHes to `mt@10.23.9.24` and runs
   `/opt/sealog-server-FKt/venv/bin/python /opt/sealog-server-FKt/misc/sealog_data_export.py`
   to export Sealog event records before the cruise data package is locked.

##### `postFinalizeCurrentCruise`

No active commands.  Add entries here to run commands after a cruise has been finalized.

##### `preFinalizeCurrentLowering`

Runs before lowering finalization begins.  Two commands fire in sequence:

1. **Export Sealog dive data** — SSHes to `mt@10.23.9.24` and runs
   `/opt/sealog-server-Sub/venv/bin/python /opt/sealog-server-Sub/misc/sealog_data_export.py`
   to export sub-side Sealog event records before the dive data is locked.

2. **Build lowering tracklines** — runs `build_lowering_tracks.py ROV_Tracklines` to generate
   GeoJSON/KML track files for the dive from the `ROV_Tracklines` extra directory.

##### `postFinalizeCurrentLowering`

No active commands (the `sealog_post_dive_export.py` call is commented out).

#### SSH prerequisites

The `postSetupNewCruise`, `preFinalizeCurrentCruise`, and `preFinalizeCurrentLowering` hooks issue
SSH commands to remote hosts.  Passwordless SSH from the OpenVDM server (`rvfk-openvdm`) to each
target must be configured in advance:

| Target | User | Purpose |
|---|---|---|
| `10.23.9.21` | `mt` | OpenRVDAS server — logger config generation |
| `10.23.9.24` | `mt` | Sealog ship server (FKt) — cruise record creation |
| `10.23.9.24` | `mt` | Sealog ship server (FKt) — cruise data export |
| `10.23.9.24` | `mt` | Sealog sub server (Sub) — dive data export |

Add the OpenVDM server's root public key (`/root/.ssh/id_rsa.pub`) to
`~/.ssh/authorized_keys` on each target host under the appropriate user.

### GPS sources for cruise track building

`bin/build_cruise_tracks.py.dist` is configured to pull position data from three sources in the
OpenRVDAS collection system:

| Device | Data type |
|---|---|
| DPS122 (DP sensor) | `dpsi1-gga` |
| POS/MV | `posmv-gga` |
| Seapath | `seapath-gga` |

### Data dashboard

`www/etc/datadashboard.yaml.dist` includes panel definitions for the primary navigation and
environmental sensors aboard Falkor (too): three GNSS/heading sources (DPS122, POS/MV, Seapath),
three gyrocompasses, MET sensors, and others. These are the defaults that appear when the data
dashboard YAML is initialized from the template.

### Parsers

All parsers in `server/plugins/parsers/` have been updated to the v2.15 plugin architecture
(Google-style docstrings, type annotations, `pdoc`-compatible module docstrings, no legacy
`FILE:/DESCRIPTION:/AUTHOR:` header blocks). The `openrvdas_plugin.py.dist` is wired to the full
set of sensors present on Falkor (too):

- Navigation: `GGAParser`, `HDTParser`, `VTGParser`, `PashrParser`
- Depth/sound velocity: `DBSParser`, `DPTParser`, `MiniSVSParser`, `SVPParser`
- Meteorology: `MetPakProParser`, `PARParser`, `MWDParser`
- Oceanography: `SBE45TSGParser`

---

## Installation

Follow the standard OpenVDM installation procedure in [INSTALL.md](INSTALL.md). When run on a
fresh Falkor (too) server the defaults at every prompt are already SOI-correct, so the typical
install is:

```bash
# Download the install script (run as root)
export OPENVDM_REPO=raw.githubusercontent.com/schmidtocean/openvdm
export BRANCH=openvdm-soi
wget -O install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm.sh

# Run the installer
bash ./install-openvdm.sh
```

Accept the defaults unless a specific setting needs to differ from the SOI standard
(e.g. a different CruiseData mount point or a different access URL).

### Post-install checklist

After the installer completes, verify or complete the following SOI-specific steps:

1. **Mount points** — Confirm `/mnt/CruiseData`, `/mnt/CruiseSandbox`, and `/mnt/soi_data1` are
   all mounted from the appropriate storage volumes before starting a cruise. The install script
   will create these directories if they do not exist, but they will be local paths rather than
   mounts.

2. **Worker API key** — The installer generates a random `WORKER_API_KEY` and writes it to both
   `server/etc/openvdm.yaml` and `www/app/Core/Config.php`. Verify the same key is present in
   both files:
   ```bash
   grep workerApiKey /opt/openvdm/server/etc/openvdm.yaml
   grep WORKER_API_KEY /opt/openvdm/www/app/Core/Config.php
   ```

3. **OpenRVDAS integration scripts** — Ensure the following scripts exist at the paths referenced
   in `openvdm.yaml` before starting a cruise:
   - `/opt/openvdm/bin/build_cruise_tracks.py`
   - `/opt/openvdm/bin/build_lowering_tracks.py`
   - `/opt/openvdm/bin/build_overlay_layers.py`

4. **Copy config templates** — If the config files were not created by the installer:
   ```bash
   cp /opt/openvdm/server/etc/openvdm.yaml.dist /opt/openvdm/server/etc/openvdm.yaml
   cp /opt/openvdm/www/app/Core/Config.php.dist  /opt/openvdm/www/app/Core/Config.php
   ```
   Then set `siteRoot` in `openvdm.yaml` to the actual access URL (e.g. `http://rvfk-openvdm/`)
   and replace the `WORKER_API_KEY` placeholder in both files with the same strong random value
   (`openssl rand -hex 32`).

5. **Samba passwords** — The installer sets the Samba password for the `mt` user to match the
   database password entered during install. If that password is later changed, update Samba with:
   ```bash
   smbpasswd -a mt
   ```

6. **Supervisor web interface** — Accessible at `http://rvfk-openvdm:9001` with the credentials
   entered during install. Use this to monitor and restart OpenVDM worker processes.

---

## Database backup and restore

The `bin/db_backup_restore.py` script creates and restores timestamped SQL dumps of the OpenVDM
MySQL database. It reads credentials directly from `www/app/Core/Config.php`, so no separate
credentials file is needed. `OVDM_Messages` rows are excluded from backups (the table structure is
preserved, but the transient message history is not).

The script is distributed as `bin/db_backup_restore.py.dist`. Copy it once after installation:

```bash
cp /opt/openvdm/bin/db_backup_restore.py.dist /opt/openvdm/bin/db_backup_restore.py
```

All commands below assume they are run from `/opt/openvdm` as root (or as the `mt` user with
`sudo` access).

### Create a backup

```bash
source venv/bin/activate
python bin/db_backup_restore.py backup
```

The backup is written to `database/backups/openvdm_YYYYMMDD_HHMMSS.sql` by default. To write to a
different directory:

```bash
python bin/db_backup_restore.py backup --output-dir /path/to/dir
```

Add `-v` for progress messages or `-vv` to log the exact mysqldump commands being run.

### Restore from a backup

To restore from a specific file:

```bash
python bin/db_backup_restore.py restore database/backups/openvdm_20250601_120000.sql
```

Omit the filename to choose interactively from all files in `database/backups/` (listed
newest-first):

```bash
python bin/db_backup_restore.py restore
```

The target database must already exist. A restore overwrites all current table contents, so take a
fresh backup first if the current state matters.

### Adding a backup to the repository

Database backups committed to `database/backups/` serve as a versioned record of the ship's OpenVDM
configuration (collection system transfers, cruise data transfers, extra directories, etc.) and are
the recommended way to snapshot configuration before upgrades or major changes.

```bash
cd /opt/openvdm

# Take a backup
source venv/bin/activate
python bin/db_backup_restore.py backup

# Stage the new file (git will show it as untracked)
git add database/backups/openvdm_YYYYMMDD_HHMMSS.sql

# Commit with a descriptive message
git commit -m "Add OpenVDM DB backup — pre-upgrade snapshot"
```

Push to the remote repository so the backup is preserved off-ship:

```bash
git push origin openvdm-soi
```

To restore a configuration from a past commit on a fresh installation, check out that commit or
copy the SQL file from git history and run:

```bash
cd /opt/openvdm
source venv/bin/activate
python bin/db_backup_restore.py restore <file>`.
```

If you do not supply a file name the script will present you with a list of available backup files from the `database/backups` directory

---

## Updating from upstream

To pull new upstream changes into this fork:

```bash
git fetch upstream
git checkout openvdm-soi
git merge upstream/master
# resolve any conflicts, then push
git push origin openvdm-soi
```

To update an existing ship installation after the branch is updated:

```bash
cd /opt/openvdm
git pull
bash utils/install-openvdm.sh   # re-run is idempotent; updates packages and web assets
```

---

## Reporting issues

Ship-specific issues (hooks, share paths, Falkor (too) sensor configuration) should be reported to
the SOI data team. Issues with the underlying OpenVDM platform should be reported upstream at
<https://github.com/oceandatatools/openvdm/issues>.
