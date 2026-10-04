# Open Vessel Data Management

## Installation Guide
OpenVDM is built and tested on Debian 12/13, Ubuntu 22.04/24.04/26.04, Rocky Linux 8/9/10 and AlmaLinux 8/9/10.

> **Rocky/AlmaLinux/RHEL 10** ship PHP 8.3, so the Remi repository isn't used. `php-gearman` isn't packaged there; the installer builds it with PECL, which needs internet access and takes a few extra minutes.

For a remote install, install an SSH server first: `apt install -y ssh` (Debian/Ubuntu) or `dnf install -y openssh-server` (Rocky/AlmaLinux).

### Install OpenVDM and its dependencies
As root, download and run the install script (or use `curl -L -o install-openvdm.sh <url>` if `wget` isn't available):
```
wget -O install-openvdm.sh https://raw.githubusercontent.com/oceandatatools/openvdm/master/utils/install-openvdm.sh
bash ./install-openvdm.sh
```

The installer asks the following questions. Press <ENTER> to accept a default. When you re-run it, your previous answers are the defaults.

| Question | Default | Notes |
|---|---|---|
| Name to assign to host | `openvdm` | |
| OpenVDM install root directory | `/opt` | OpenVDM goes in `<root>/openvdm` |
| Repository / branch to install | GitHub `oceandatatools/openvdm`, `master` | |
| IP address or URL users will access OpenVDM from | `127.0.0.1` | |
| OpenVDM user to create | `survey` | You're asked for its Linux password |
| Current / new MySQL root password | empty | On a first install, press <ENTER> for the current password |
| Password for the OpenVDM MySQL user | the root password | Also the user's web interface and Samba password |
| Root data directory | `/data` | Cruise data goes in `<data root>/CruiseData` |
| Enable the Supervisor web interface, with a username and password | no | Starts and stops OpenVDM's processes from a browser. The username and password default to the OpenVDM user's |
| Install MapProxy, and its cache directory | no, `<data root>/cache_data` | Caches map tiles to cut ship-to-shore traffic. Put the cache on a volume separate from the OS |
| Install TiTiler, and its port | no, `8000` | Tile server for Cloud Optimized GeoTIFFs; needed by `geotiff_titiler_parser` and the sample data |
| Set up the PublicData share | yes | SMB share for scientists and crew; copied to the cruise data at the end of the cruise (set `transferPublicData` in `server/etc/openvdm.yaml` to change this) |
| Set up the VisitorInformation share | no | SMB share for documentation, print drivers, etc. |
| Install sample data, its directory, repository and branch | no, `/data/sample_data`, GitHub `oceandatatools/openvdm_sample_data`, `master` | **Replaces any existing transfer configuration** |

The sample data sets up demonstration collection systems, cruise data and ship-to-shore transfers, and a local test server for each transfer type: Samba shares, rsync modules, and an FTP server (`utils/sample_ftp_server.py`, Supervisor program `openvdm_sample_ftp`) that listens on localhost only:
- port 2121 supports `MLSD`; port 2122 doesn't, like many older instrument FTP servers;
- the OpenVDM user, with the OpenVDM password, can read the sample data root and write only to `ftp_destination`;
- anonymous users can read `ftp_source`.

The sample data includes lowering transfers, so it also turns on lowering components and sets up the current lowering (`ROV0001` on a new install).

When the installer finishes, it prints the web interface address, the login, and where cruise data is stored:
```
OpenVDM Installation: Complete
OpenVDM WebUI available at: http://127.0.0.1
Login with user: survey, pass: weak_password
Cruise Data will be stored at: /data/CruiseData
```
You still need to configure the collection system transfers, cruise data transfers, shoreside data warehouse and data dashboard.

If the web interface reports an error, the details are at `http://<hostname>/errorlog.html`.

## Upgrading from 2.14.

2.15 moved from PHP 7.3 to 8.2, and 2.16 needs Python 3.11 or later. Choose one route; both use the same two database update scripts. If the server is a virtual machine, take a snapshot first.

- **In place:** re-run the 2.16 installer on the same server. Only on Rocky Linux or AlmaLinux 8 or 9 (tested on Rocky Linux 9), where the installer moves PHP to 8.2 from Remi. On Debian/Ubuntu, 2.14 ran Apache's PHP 7.3 module, which the installer doesn't switch off; use the fresh-OS route.
- **On a fresh OS:** install 2.16 on a new or reinstalled server and bring the database, settings and cruise data across.

### In place (Rocky Linux / AlmaLinux 8 or 9)

1. Set OpenVDM to Off and wait until no transfers or tasks are running.
2. Back up the database (the script asks for the MySQL root password twice):
```
cd <openvdm_root>
sudo bash ./utils/export_openvdm_db.sh > ~/openvdm_2.14_backup.sql
```
3. Give the OpenVDM user the checkout (2.14 left `www/` owned by root), then set your settings files aside as `.214` copies:
```
cd <openvdm_root>
sudo chown -R <openvdm_user>:<openvdm_user> <openvdm_root>
sudo -u <openvdm_user> cp www/app/Core/Config.php www/app/Core/Config.php.214
sudo -u <openvdm_user> mv server/etc/openvdm.yaml server/etc/openvdm.yaml.214
sudo -u <openvdm_user> mv www/etc/datadashboard.yaml www/etc/datadashboard.yaml.214
```
   The installer rewrites `Config.php` on every run but reads the worker API key from it, so copy it. It builds the YAML files from their 2.16 templates only when they're missing, so move those: a kept 2.14 `openvdm.yaml` only gets `workerApiKey` and `transferPublicData` appended, and a kept `datadashboard.yaml` lacks 2.16's panels and breaks the Position map (#185).
4. Update the code and re-run the installer. Give the 2.14 install's answers, especially the OpenVDM user and data root, and don't install the sample data. If you installed 2.14 from a tag, answer `master` for the branch.
```
sudo -u <openvdm_user> git fetch origin
sudo -u <openvdm_user> git checkout master
sudo -u <openvdm_user> git pull --ff-only
sudo bash ./utils/install-openvdm.sh
```
   The installer moves PHP to 8.2; installs Python 3.11+ and rebuilds `<openvdm_root>/venv` if it was made with another version (reinstall anything you'd added to it yourself, e.g. matplotlib); writes new `Config.php`, `openvdm.yaml` and `datadashboard.yaml` with a new worker API key; and rewrites the Apache, Samba and Supervisor configuration. It doesn't change the database.
5. Update the database (each command asks for the MySQL root password and prints nothing on success):
```
mysql -u root -p openvdm < ./database/openvdm_214_to_215.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
   Run each once; a second run of `openvdm_215_to_216.sql` stops with `Duplicate column name 'ftpServer'` and changes nothing. For any other error, save it, contact OceanDataTools, and restore the backup from step 2.
6. Continue with [After upgrading](#after-upgrading).

### On a fresh OS

On the 2.14 server:
1. Set OpenVDM to Off and wait until no transfers or tasks are running.
2. Back up the database as in step 2 above.
3. Copy to the new server the backup and the files you've customized:
   - `server/etc/openvdm.yaml`, `www/app/Core/Config.php` and `www/etc/datadashboard.yaml`. After installing 2.16, put them next to the new files with a `.214` suffix; don't copy them over the new ones;
   - your plugins and parsers (`server/plugins/*_plugin.py`, `server/plugins/parsers/*_parser.py`);
   - anything else you've changed, e.g. `www/app/templates/default/js/custom1.js` or scripts in `bin/`.
4. If the new server won't use the same disk, copy the cruise data (`<data root>/CruiseData`), keeping it owned by the OpenVDM user.

On the new server:

5. [Install OpenVDM 2.16](#install-openvdm-and-its-dependencies). Give the 2.14 install's answers where they still apply, especially the OpenVDM user and data root, and don't install the sample data.
6. Stop the workers, restore the backup, and update it to 2.16. The backup replaces every table, including the web interface users, so afterwards log in with your 2.14 accounts. The same notes apply as in step 5 of the in-place route.
```
sudo supervisorctl stop openvdm:*
cd <openvdm_root>
mysql -u root -p openvdm < ~/openvdm_2.14_backup.sql
mysql -u root -p openvdm < ./database/openvdm_214_to_215.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
7. The database still has the 2.14 server's data warehouse settings. On **Configuration** › **System**, edit **Shipboard Data Warehouse (SBDW)** and check the server IP, username and directories.
8. Continue with [After upgrading](#after-upgrading).

Transfer logs are no longer kept in the cruise directory: 2.15 moved them to `/var/log/openvdm` (`TRANSFER_LOG_DIR` in `Config.php`), and `openvdm_214_to_215.sql` removes the old Transfer_Logs extra directory and ship-to-shore transfer. Existing cruises' `OpenVDM/TransferLogs` folders are left alone.

## Upgrading from 2.15.

2.16 adds the FTP Server transfer type, which needs a database update, and fixes several plugins, parsers and scripts that the installer doesn't update for you. See the 2.16.0 entry in [CHANGELOG.md](CHANGELOG.md).

1. Set OpenVDM to Off and wait until no transfers or tasks are running.
2. As the OpenVDM user, set your settings files aside as `.215` copies (copy `Config.php`, move the YAML files, for the reasons in [step 3 of the 2.14 route](#in-place-rocky-linux--almalinux-8-or-9)), and update the code. Then re-run the installer, keeping your previous answers:
```
cd <openvdm_root>
sudo -u <openvdm_user> cp www/app/Core/Config.php www/app/Core/Config.php.215
sudo -u <openvdm_user> mv server/etc/openvdm.yaml server/etc/openvdm.yaml.215
sudo -u <openvdm_user> mv www/etc/datadashboard.yaml www/etc/datadashboard.yaml.215
sudo -u <openvdm_user> git pull --ff-only
sudo bash ./utils/install-openvdm.sh
```
   Run `git pull` as the OpenVDM user: git refuses a checkout owned by another user ("detected dubious ownership"). The installer now runs `composer install --no-dev` and `npm install` as the OpenVDM user (removing development packages such as PHPStan), and on Debian/Ubuntu moves nvm from `/root/.nvm` to that user's home (it keeps `/root/.nvm` if root installed other global npm packages there).
3. Back up and update the database:
```
sudo bash ./utils/export_openvdm_db.sh > ~/openvdm_backup_before_2.16.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
   The update prints nothing on success. For any error, save it and contact OceanDataTools.
4. Copy the updated `.dist` templates you use over your copies (the installer only copies a `.dist` file when your copy doesn't exist). If you've customized one, e.g. a plugin's `FILE_TYPE_FILTERS`, merge instead; `diff <file>.dist <file>` shows the changes. Other `.dist` files changed only in their documentation.

| File (in `<openvdm_root>`) | Why |
|---|---|
| `server/plugins/parsers/geotiff_titiler_parser.py` | Overlay placement for GeoTIFFs not in lat/lon; Geographic Bounds and band stats (#138, #158) |
| `server/plugins/parsers/geotiff_parser.py` | Geographic Bounds order (#158) |
| `server/plugins/parsers/tsg45_parser.py` | Failures when files with and without an SBE 38 are parsed together (#146) |
| `server/plugins/parsers/hpr_parser.py`, `gnss_parser.py` | No output for files with fractional roll values (#152) |
| `server/plugins/rov_openrvdas_plugin.py` | Couldn't run; now crops data to each lowering (#150). **Keep your `SEALOG_SERVER_URL` and `SEALOG_JWT`.** |
| `bin/build_remote_directory.py` | Created directories with the wrong permissions (#164) |
| `www/app/templates/default/js/custom1.js` | CARTO basemaps now need an API key; replaced with keyless maps (#121) |

5. Continue with [After upgrading](#after-upgrading). If you use either GeoTIFF parser, the dashboard rebuild there also corrects the Geographic Bounds stats, for the current cruise only.

## After upgrading

1. Merge your settings from the `.214`/`.215` copies into the new files; don't copy the old files back. `diff` shows the differences (use `.214` if you're upgrading from 2.14):
```
cd <openvdm_root>
diff server/etc/openvdm.yaml.215 server/etc/openvdm.yaml
diff www/etc/datadashboard.yaml.215 www/etc/datadashboard.yaml
diff www/app/Core/Config.php.215 www/app/Core/Config.php
```
   - **`openvdm.yaml`:** add your hooks, `postHookCommands` and other changed settings. Keep the new `workerApiKey` (it matches `WORKER_API_KEY` in `Config.php`; without it, transfers that use a password fail) and `transferPublicData` (2.14.1's template misspelled it `transferPubicData`).
   - **`datadashboard.yaml`:** add your own tabs and panels. The new file has 2.16's: CTD and XBT cast positions on the Position map, CTD and XBT depth profiles on the Seawater tab, and a commented-out example Lowering tab. Put `lowering` in a tab's `jsArray` only on tabs that use the `lowering` view, and never with `dataDashboardDefault`: older Position tabs had both, which logs `Map container is already initialized` (#185).
   - **`Config.php`:** copy over only settings you changed yourself; the rest come from the 2.16 template and your installer answers.
   - Keep the copies until the upgrade works. Git doesn't ignore them, so `git status` lists them.
2. From 2.14 only: bring each plugin and parser you use up to its 2.16 `.dist` template and redo your changes in it; don't keep the 2.14 versions. A collection system transfer's plugin is `<transfer name in lower case>_plugin.py`.
3. If you've used `bin/build_remote_directory.py` on a local-directory collection system, fix the permissions of the directories it created (#164): `chmod 755 <directory>`.
4. Restart the workers and set OpenVDM back to On:
```
sudo supervisorctl restart openvdm:*
```
5. On **Configuration** › **Maintenance Tasks**, run **Rebuild Data Dashboard**. From 2.14, also run **Rebuild Cruise Directory**, **Re-export the OpenVDM Configuration** and **Rebuild MD5 Summary**, and, if you use lowerings, **Rebuild Lowering Directory** and **Re-export the Lowering Configuration**. (The task names include your cruise and lowering IDs.)

If you update the web app's PHP or JavaScript libraries by hand rather than with the installer, run Composer as the OpenVDM user (it also runs `npm install`):
```
cd <openvdm_root>/www
sudo -H -u <openvdm_user> /usr/local/bin/composer install --no-dev
```

Contributors: `pre-commit` now also runs ESLint, `php -l` and PHPStan; run `composer install` (without `--no-dev`) in `www/` to install PHPStan. See CONTRIBUTING.md.

## Upgrading from 2.13 or earlier

Upgrade to 2.14 first, following the [2.14.1 INSTALL.md](https://github.com/OceanDataTools/openvdm/blob/2.14.1/INSTALL.md), then follow "Upgrading from 2.14" above.
