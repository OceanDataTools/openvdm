# Open Vessel Data Management

## Installation Guide
At the time of this writing OpenVDM was built and tested against Debian 12/13, Ubuntu 22.04/24.04/26.04, Rocky 8/9/10 and AlmaLinux 8/9/10 operating systems.

### Operating Systems
 - Debian 12: <https://wiki.debian.org/DebianBookworm>
 - Debian 13: <https://wiki.debian.org/DebianTrixie>
 - Ubuntu 22.04: <https://releases.ubuntu.com/22.04/>
 - Ubuntu 24.04: <https://releases.ubuntu.com/24.04/>
 - Ubuntu 26.04: <https://releases.ubuntu.com/26.04/>
 - Rocky 8: <https://rockylinux.org/news/rocky-linux-8-10-ga-release>
 - Rocky 9: <https://rockylinux.org/news/rocky-linux-9-8-ga-release>
 - Rocky 10: <https://rockylinux.org/news/rocky-linux-10-2-ga-release>
 - AlmaLinux 8: <https://almalinux.org/get-almalinux/>
 - AlmaLinux 9: <https://almalinux.org/get-almalinux/>
 - AlmaLinux 10: <https://almalinux.org/get-almalinux/>

> **Note for Rocky/AlmaLinux/RHEL 10:** These releases ship PHP 8.3 natively so the Remi repository is not used. The `php-gearman` extension is not packaged and is built automatically from source via PECL during installation. This requires an active internet connection and adds a few minutes to the install time.

### If you are installing OpenVDM remotely

If this is going to be a remote install then SSH Server must be installed.
 - Debian/Ubuntu
```
apt install -y ssh
```

 - Rocky/AlmaLinux
```
dnf install ssh
```

### Install OpenVDM and it's dependencies
Log into the Server as root

Download the install script
```
export OPENVDM_REPO=raw.githubusercontent.com/oceandatatools/openvdm
export BRANCH=master
wget -O install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm.sh
```

If the wget utility is not available you can download the install script using this `curl` command:
```
curl -L -o install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm.sh
```

Run the install script
```
bash ./install-openvdm.sh
```

You will need to answer some questions about your configuration.  For each of the questions there is a default answer. To accept the default answer hit <ENTER>.

```
#####################################################################
OpenVDM configuration script
#####################################################################
Name to assign to host (openvdm)? 
Hostname will be 'openvdm-2vcpu-4gb-nyc2-01'
Hostname already in /etc/hosts

OpenVDM install root? (/opt) 
Install root will be '/opt'

Repository to install from? (https://github.com/oceandatatools/openvdm) 
Repository branch to install? (master) 

Will install from github.com
Repository: 'https://github.com/oceandatatools/openvdm'
Branch: 'master'
Installation Directory: /opt
```
```
#####################################################################
IP Address or URL users will access OpenVDM from? (127.0.0.1) 

Access URL: 'http://127.0.0.1'
```
 
```
#####################################################################
OpenVDM user to create? (survey) 
Checking if user survey exists yet
id: ‘survey’: no such user
...
New password: 
Retype new password: 
passwd: password updated successfully
```

```
#####################################################################
Gathing information for MySQL installation/configuration
Root database password will be empty on initial installation. If this
is the initial installation, hit return when prompted for root
database password, otherwise enter the password you used during the
initial installation.

Current root database password (hit return if this is the initial
installation)? 
New database password for root? () weak_password

New database password for user survey? (survey) weak_password
```

```
#####################################################################
Root data directory for OpenVDM? (/data) 
Root data directory /data does not exists... create it?  (yes) 
```

```
#####################################################################
The supervisord service provides an optional web-interface that enables
operators to start/stop/restart the OpenVDM main processes from a web-
browser.

Enable Supervisor Web-interface?  (no) yes
Enable user/pass on Supervisor Web-interface?  (no) yes
Username? (survey) 
Password? (survey) weak_password
```

```
#####################################################################
Optionally install: MapProxy
MapProxy is used for caching map tiles from ESRI and Google. This can
reduce ship-to-shore network traffic for GIS-enabled webpages.

Install MapProxy?  (no) yes

Where should the cached tiles be stored? It is recommended that the
tile cache directory be located on a mounted volume that is
independent of the volume used for the operating system.

Cache data directory for MapProxy? (/data/cache_data)
Cache data directory /data/cache_data does not exist... create it?  (yes)
```

```
#####################################################################
Optionally install TiTiler, a dynamic tile server for Cloud Optimized
GeoTIFFs (COGs). TiTiler is required for the geotiff_titiler_parser
plugin used by the sample data configuration.

Install TiTiler?  (no) yes
Port for TiTiler service? (8000)
```

```
#####################################################################
Setup a PublicData SMB Share for scientists and crew to share files,
pictures, etc. These files will be copied to the cruise data
directory at the end of the cruise. This behavior can be disabled in
the /opt/openvdm/server/etc/openvdm.yaml file.

Setup PublicData Share?  (yes)
```

```
#####################################################################
Setup a VisitorInformation SMB Share for sharing documentation, print
drivers, etc with crew and scientists.

Setup VisitorInformation Share?  (no)
```

```
#####################################################################
Optionally install sample data from the openvdm_sample_data repository.
This configures demonstration collection systems, cruise data transfers,
and ship-to-shore transfers using local sample instrument data.
WARNING: This will replace any existing transfer configuration in the
OpenVDM database.

Install sample data?  (no) yes
Root directory for sample data? (/data/sample_data)
Sample data repository? (https://github.com/oceandatatools/openvdm_sample_data)
Sample data branch? (master)
```

The sample data also sets up local test servers for each transfer type: Samba shares, rsync daemon modules and an FTP server. The FTP server (`utils/sample_ftp_server.py`, run by Supervisor as `openvdm_sample_ftp`) listens on localhost only:
- port 2121 supports `MLSD`; port 2122 doesn't, like many older instrument FTP servers;
- the OpenVDM user, with the OpenVDM password, can read the sample data root and write only to `ftp_destination`;
- anonymous users can read `ftp_source`.

The sample data includes lowering-level transfers, so installing it also turns on lowering components. After setting up the cruise, the installer sets up the current lowering (`ROV0001` on a new install) and runs its transfers along with the cruise's.

### All done... almost ###
When the script completes successfully there will a message containing how to access the OpenVDM web-interface:
```
#####################################################################
OpenVDM Installation: Complete
OpenVDM WebUI available at: http://127.0.0.1
Login with user: survey, pass: weak_password
Cruise Data will be stored at: /data/CruiseData
```
 
At this point there should be a working installation of OpenVDM however the vessel operator will still need to configure data dashboard collection system transfers, cruise data transfers and the shoreside data warehouse.

To access the OpenVDM web-application go to address specified in the completetion message.

### An error has been reported ###
If at anypoint you see this message in the OpenVDM web-interface you can see what the error was by going to: `<http://<hostname>/errorlog.html>`.  That should hopefully provide you with enough information as to what's gone wrong.

## Upgrading from 2.7 or earlier.

OpenVDM v2.8 introducted some database schema changes that will require existing user to perform some additional steps.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Backup the existing database BEFORE running the schema update script.  To do this run the `./utils/export_openvdm_db.sh` script and redirect the output to a file.  In the event there is a problem updating the database the output from this script can be used to restore the database to a known good state.
3. Start the mysql cli `mysql -p`
4. Select the OpenVDM database by typing: `use openvdm;` (`openvdm` is the default name of the database)
5. Run the update script: `source <path to openvdm>/database/openvdm_27_to_28.sql`  You should see that the database was updated.  If you see any errors please save those errors to a text file and contact Webb Pinner at OceanDataTools.
 
There are also some web-dependencies that were updated as part of this release. To update those run:
```
cd <openvdm_root>/www
composer install
```

## Upgrading from 2.8.

OpenVDM v2.9 introducted some configuration file and database changes that will require existing user to perform some additional steps.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Backup the existing database BEFORE running the schema update script.  To do this run the `./utils/export_openvdm_db.sh` script (you may need to run via sudo) and redirect the output to a file.  In the event there is a problem updating the database the output from this script can be used to restore the database to a known good state.
3. Start the mysql cli `mysql -p`
4. Select the OpenVDM database by typing: `use openvdm;` (`openvdm` is the default name of the database)
5. Run the update script: `source <path to openvdm>/database/openvdm_28_to_29.sql`  You should see that the database was updated.  If you see any errors please save those errors to a text file and contact Webb Pinner at OceanDataTools.
6. Make a backup the webUI config file: `./www/app/Core/Config.php`
7. Make a new webUI config file using the default template: `cp ./www/app/Core/Config.php.dist ./www/app/Core/Config.php`
8. Transfer any customizations from the the backup configuration file to the new configuration file.

There are also some web-dependencies that were updated as part of this release. To update those run:
```
cd <openvdm_root>/www
rm -r bower_components
bower install
composer install
```

## Upgrading from 2.9.

OpenVDM v2.10 added some new server-side functionality and updated how javascript and CSS libraries are installed.  These changes will require existing user to perform some additional steps.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Make a backup the webUI config file: `./www/app/Core/Config.php`
3. Make a new webUI config file using the default template: `cp ./www/app/Core/Config.php.dist ./www/app/Core/Config.php`
4. Transfer any customizations from the the backup configuration file to the new configuration file.
5. Make a backup the server config file: `./server/etc/openvdm.yaml`
6. Make a new server config file using the default template: `cp ./server/etc/openvdm.yaml.dist ./server/etc/openvdm.yaml`
7. Transfer any customizations from the the backup configuration file to the new configuration file.
8. Re-install the javascript and css libraries:
```
cd <openvdm_root>/www
rm -r bower_components
rm -r node_modules
bash composer install
```

If you plan to contribute back to the project (thanks!) please install the pre-commit hook to lint your changes prior to committing:
```
cd <openvdm_root>
source ./venv/bin/activate
pre-commit install
pre-commit run --all-files
deactivate
```

## Upgrading from 2.10.

OpenVDM v2.11 added some new server-side functionality and updates to javascript and CSS libraries.  These changes will require existing user to perform some additional steps.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Make a backup the webUI config file: `./www/app/Core/Config.php`
3. Make a new webUI config file using the default template: `cp ./www/app/Core/Config.php.dist ./www/app/Core/Config.php`
4. Transfer any customizations from the the backup configuration file to the new configuration file.
5. Make a backup the server config file: `./server/etc/openvdm.yaml`
6. Make a new server config file using the default template: `cp ./server/etc/openvdm.yaml.dist ./server/etc/openvdm.yaml`
7. Transfer any customizations from the the backup configuration file to the new configuration file.
8. Re-install the javascript and css libraries:
```
cd <openvdm_root>/www
bash ./post_composer.sh
```
9. Update the python libraries
```
cd <openvdm_root>
source ./venv/bin/activate
pip install -r requirements.txt
```
10. Backup the existing database BEFORE running the schema update script.  To do this run the `bash ./utils/export_openvdm_db.sh` script (you may need to run via sudo) and redirect the output to a file.  In the event there is a problem updating the database the output from this script can be used to restore the database to a known good state.
11. Start the mysql cli `mysql -p`
12. Select the OpenVDM database by typing: `use openvdm;` (`openvdm` is the default name of the database)
13. Run the update script: `source <path to openvdm>/database/openvdm_210_to_211.sql`  You should see that the database was updated.  If you see any errors please save those errors to a text file and contact Webb Pinner at OceanDataTools.
14. Install rclone via `apt-get install rclone` (Ubuntu) or `dnf install rclone` (Rocky/RHEL)

## Upgrading from 2.14.

OpenVDM 2.15 moved from PHP 7.3 to PHP 8.2, and 2.16 needs Python 3.11 or later. There are two ways to upgrade a 2.14 server. Both use the same two database update scripts, which take a 2.14 database to the 2.16 schema.

- **In place:** re-run the 2.16 installer on the same server. Use this on Rocky Linux or AlmaLinux 8 or 9, where the installer moves PHP to 8.2 from the Remi repository. This route has been tested end to end on Rocky Linux 9. On Ubuntu and Debian, 2.14 ran PHP 7.3 as Apache's PHP module (`libapache2-mod-php7.3`), and the 2.16 installer doesn't switch Apache off it. Use the fresh-OS route there.
- **On a fresh OS:** install 2.16 on a new or reinstalled server, and bring the 2.14 database, settings and cruise data across.

Whichever you choose, if the server is a virtual machine, take a snapshot first.

### In place (Rocky Linux / AlmaLinux 8 or 9)

1. Set OpenVDM to Off and wait until no transfers or tasks are running.
2. Back up the database. The script asks for the MySQL root password twice:
```
cd <openvdm_root>
sudo bash ./utils/export_openvdm_db.sh > ~/openvdm_2.14_backup.sql
```
3. Set your configuration files aside as `.214` copies. The installer builds `openvdm.yaml` and `datadashboard.yaml` from their 2.16 `.dist` templates only when they don't exist, and it always rewrites `Config.php`, so this gets you clean 2.16 files. You'll merge your changes back in from the copies afterwards.
```
cd <openvdm_root>
sudo cp www/app/Core/Config.php www/app/Core/Config.php.214
sudo mv server/etc/openvdm.yaml server/etc/openvdm.yaml.214
sudo mv www/etc/datadashboard.yaml www/etc/datadashboard.yaml.214
```
   `Config.php` is copied, not moved: the installer rewrites it anyway, and it reads the worker API key from it. If the installer stops before it gets that far, the web app keeps its working `Config.php`. The two YAML files have to be moved, because the installer only builds them when they're missing.

   Don't skip the two renames. If you keep 2.14's `openvdm.yaml`, the installer only appends `workerApiKey` and `transferPublicData` to it. If you keep 2.14's `datadashboard.yaml`, it misses 2.16's panels and keeps a Position tab setting that breaks its map (#185).
4. Update the code and re-run the installer. Give the same answers as for the 2.14 install, especially the OpenVDM user and the data root directory. Don't install the sample data. The 2.14 installer left `www/` owned by root, and the OpenVDM user does the updating, so give it the whole checkout first. If you installed 2.14 from a tag (e.g. `2.14.1`), answer `master` at the installer's branch question.
```
cd <openvdm_root>
sudo chown -R <openvdm_user>:<openvdm_user> <openvdm_root>
sudo -u <openvdm_user> git fetch origin
sudo -u <openvdm_user> git checkout master
sudo -u <openvdm_user> git pull --ff-only
sudo ./utils/install-openvdm.sh
```
   Check that the update worked: `grep -c "date = ''" www/app/Models/TransferLogs.php` prints `1` on 2.16, and `0` if you're still on 2.14's code.
   The installer:
   - moves PHP to 8.2;
   - installs Python 3.11 or later, and rebuilds OpenVDM's virtual environment (`<openvdm_root>/venv`) when it was made with another Python version: 2.14's uses Python 3.11, and the installer picks the newest Python 3.11+ the OS offers (3.14 on current Rocky 9). Anything you installed into the venv yourself (for example matplotlib) has to be installed again.
   - rewrites `Config.php` from the 2.16 template, with the database password you give it;
   - builds a new `server/etc/openvdm.yaml` and `www/etc/datadashboard.yaml` from their `.dist` templates. It generates a worker API key and writes it to both `openvdm.yaml` and `Config.php`;
   - rewrites the Apache, Samba and Supervisor configuration;
   - leaves the database alone.
5. Update the database to 2.16 by running the two update scripts, in this order. Each asks for the MySQL root password and prints nothing when it succeeds:
```
cd <openvdm_root>
mysql -u root -p openvdm < ./database/openvdm_214_to_215.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
   Run each script once. Running `openvdm_215_to_216.sql` again stops with `Duplicate column name 'ftpServer'` and changes nothing. If you see any other errors, save them and contact OceanDataTools; restore the backup from step 2 and try again.
6. Continue with [After either route](#after-either-route).

### On a fresh OS

**On the 2.14 server:**

1. Set OpenVDM to Off and wait until no transfers or tasks are running.
2. Back up the database. The script asks for the MySQL root password twice:
```
cd <openvdm_root>
sudo bash ./utils/export_openvdm_db.sh > ~/openvdm_2.14_backup.sql
```
3. Copy the backup to the new server, along with your copies of the files you've customized. You'll merge your changes into the 2.16 versions of these files, so don't copy them over the new ones. Once 2.16 is installed, put the first three next to the new files as `server/etc/openvdm.yaml.214`, `www/app/Core/Config.php.214` and `www/etc/datadashboard.yaml.214`:
   - `server/etc/openvdm.yaml`, for your hooks and `postHookCommands`;
   - `www/app/Core/Config.php`;
   - `www/etc/datadashboard.yaml`;
   - your plugins and parsers: the `server/plugins/*_plugin.py` and `server/plugins/parsers/*_parser.py` files (not the `.dist` templates);
   - anything else you've changed, for example `www/app/templates/default/js/custom1.js` or scripts in `bin/`.
4. If the new server won't use the same disk, copy the cruise data (`<data root>/CruiseData`, `/data/CruiseData` by default) to it. Keep the files owned by the OpenVDM user.

**On the new server:**

5. Install OpenVDM 2.16 on a fresh OS (see [Install OpenVDM and it's dependencies](#install-openvdm-and-its-dependencies)). Where the 2.14 install's answers still apply, give the same ones, especially the OpenVDM user and the data root directory. Don't install the sample data.
6. Stop the workers:
```
sudo supervisorctl stop openvdm:*
```
7. Restore the 2.14 backup over the new database, then update it to 2.16 by running the two update scripts, in this order. The backup replaces every table, including the web interface's users: afterwards, log in with your 2.14 accounts, not the one the installer created. Each command asks for the MySQL root password, and prints nothing when it succeeds:
```
cd <openvdm_root>
mysql -u root -p openvdm < ~/openvdm_2.14_backup.sql
mysql -u root -p openvdm < ./database/openvdm_214_to_215.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
   Run each script once. Running `openvdm_215_to_216.sql` again stops with `Duplicate column name 'ftpServer'` and changes nothing. If you see any other errors, save them and contact OceanDataTools; the backup can be restored and the steps repeated.
8. The database keeps the 2.14 server's data warehouse settings. In the web interface, open **Configuration**, the **System** tab, and click **Edit** on the **Shipboard Data Warehouse (SBDW)** row. Check that the server IP and username are the new server's, and that the directories match what you gave the installer.
9. Continue with [After either route](#after-either-route).

### After either route

1. Merge your 2.14 settings into the 2.16 files. `diff` shows the differences:
```
cd <openvdm_root>
diff server/etc/openvdm.yaml.214 server/etc/openvdm.yaml
diff www/etc/datadashboard.yaml.214 www/etc/datadashboard.yaml
diff www/app/Core/Config.php.214 www/app/Core/Config.php
```
   Make your changes in the 2.16 files. Don't copy the `.214` files back.
   - `server/etc/openvdm.yaml`: add your hooks and `postHookCommands`, and any other settings you'd changed. Keep the new file's `workerApiKey`, which must match `WORKER_API_KEY` in `Config.php`, and its `transferPublicData` (2.14.1's template misspelled it as `transferPubicData`).
   - `www/etc/datadashboard.yaml`: add your own tabs and panels. The new file already has 2.16's, such as the profile charts. Keep `lowering` in a tab's `jsArray` only on tabs that use the `lowering` view, and never together with `dataDashboardDefault`; 2.14's Position tab had both (#185).
   - `www/app/Core/Config.php`: copy over only settings you'd changed yourself. The rest differ because of the 2.16 template and your installer answers.
   - Keep the `.214` copies until the upgrade is working. Git doesn't ignore them, so `git status` lists them as untracked.
2. Bring each plugin and parser you use up to its 2.16 `.dist` template, then make your changes in it again. Many plugins and parsers were fixed in 2.15 and 2.16, so don't keep or copy back the 2.14 versions.
   - A collection system transfer's plugin is named after the transfer: `<transfer name in lower case>_plugin.py`.
   - Bring its parsers up to date too.
   - `diff <your copy> <file>.dist` shows what changed.
3. Start the workers and set OpenVDM back to On:
```
sudo supervisorctl restart openvdm:*
```
4. In the web interface, on the **Configuration** page under **Maintenance Tasks**, run **Rebuild Cruise Directory**, **Re-export the OpenVDM Configuration**, **Rebuild Data Dashboard** and **Rebuild MD5 Summary**. If you use lowerings, also run **Rebuild Lowering Directory** and **Re-export the Lowering Configuration**. These tasks are named with your cruise and lowering names, for example "Rebuild Cruise Directory".

Transfer logs are no longer kept in the cruise directory. 2.15 moved them to `/var/log/openvdm` (`TRANSFER_LOG_DIR` in `Config.php`), and `openvdm_214_to_215.sql` removes the old Transfer_Logs extra directory and ship-to-shore transfer. Existing cruises' `OpenVDM/TransferLogs` folders are left as they are.

For what changed in each release, see [CHANGELOG.md](CHANGELOG.md). Also see "Upgrading from 2.15" below for its note on directories made by `bin/build_remote_directory.py`.

## Upgrading from 2.15.

OpenVDM v2.16 adds FTP Server as a collection system transfer type (#17), which needs a database update (step 3). Several plugins, parsers and `bin/` scripts were also fixed, and the installer doesn't update your copies of those. See the 2.16.0 entry in [CHANGELOG.md](CHANGELOG.md) for the details of each change.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Update the code and dependencies by re-running the installer. It's safe to run over an existing install. It pulls the latest code, runs `composer install --no-dev` (which also removes any Composer development packages, such as PHPStan) and reinstalls the JavaScript libraries (`npm install`). Both now run as the OpenVDM user instead of root. On Debian and Ubuntu the installer also moves Node.js (nvm) from root's home directory to the OpenVDM user's, so that user can run npm, and removes the old `/root/.nvm` and its lines in root's `.bashrc`. If root installed other global npm packages in `/root/.nvm`, it's kept and the installer says so. It asks the same questions as the original install, with your previous answers as the defaults:
   First set two settings files aside as `.215` copies.
   - **`Config.php`:** the installer rewrites it from the 2.16 template on every run, so any changes you've made to it are lost. Copy it rather than moving it: the installer reads the worker API key from it, and if the installer stops before rewriting it, the web app keeps working.
   - **`datadashboard.yaml`:** the installer builds a new one from its 2.16 template only when there isn't one, so move it.
   - **`server/etc/openvdm.yaml`:** keep it as it is. 2.16 didn't change its settings.
```
cd <openvdm_root>
sudo cp www/app/Core/Config.php www/app/Core/Config.php.215
sudo mv www/etc/datadashboard.yaml www/etc/datadashboard.yaml.215
git pull
sudo ./utils/install-openvdm.sh
```
If your `server/etc/openvdm.yaml` is older than 2.15.5, the installer also adds the two settings added in that release: `workerApiKey`, set to the same key as `WORKER_API_KEY` in `www/app/Core/Config.php`, and `transferPublicData`, set from your PublicData answer. Without `workerApiKey` the workers don't receive transfer passwords from the web app, so transfers that use a password fail. Without `transferPublicData`, older releases' Rebuild Cruise Directory and cruise setup/finalize crashed with `KeyError: 'transferPublicData'`; 2.16.0 defaults it to `True` (#187). To check:
```
grep -E 'workerApiKey|transferPublicData' <openvdm_root>/server/etc/openvdm.yaml
```
3. Update the database. FTP Server needs a new transfer type and four new columns in the collection system transfers table; the installer doesn't change an existing database. Back up the database first, so it can be restored if the update fails. The backup script asks for the MySQL root password twice, and the update once:
```
cd <openvdm_root>
sudo bash ./utils/export_openvdm_db.sh > ~/openvdm_backup_before_2.16.sql
mysql -u root -p openvdm < ./database/openvdm_215_to_216.sql
```
The update prints nothing when it succeeds. If you see errors, save them and contact OceanDataTools.
4. Copy the updated plugin, parser and script templates over your copies. The installer only copies a `.dist` file when your copy doesn't exist yet, so it won't update these for you. Only the files you actually use need copying. If you've customized a file (for example a plugin's `FILE_TYPE_FILTERS`), merge the changes into your copy instead of overwriting it; `diff <file>.dist <file>` shows what changed.

| File (in `<openvdm_root>`) | Why |
|---|---|
| `server/plugins/parsers/geotiff_titiler_parser.py` | Map overlay placement for GeoTIFFs not in lat/lon; new Geographic Bounds and band stats; stats order (#138, #158) |
| `server/plugins/parsers/geotiff_parser.py` | Geographic Bounds order (#158) |
| `server/plugins/parsers/tsg45_parser.py` | Parsing failures when TSG files with and without an SBE 38 are handled by the same worker (#146) |
| `server/plugins/parsers/hpr_parser.py`, `gnss_parser.py` | No output for any file with fractional roll values (#152) |
| `server/plugins/rov_openrvdas_plugin.py` | The plugin couldn't run; now also crops data to each lowering (#150). **Keep your `SEALOG_SERVER_URL` and `SEALOG_JWT` values.** |
| `bin/build_remote_directory.py` | Directories created with the wrong permissions (#164) |
| `www/app/templates/default/js/custom1.js` | The CARTO basemap now requires an API key; replaced with keyless maps (#121) |

For example:
```
cd <openvdm_root>/server/plugins/parsers
cp geotiff_titiler_parser.py.dist geotiff_titiler_parser.py
```
The other `.dist` files changed in this release have documentation-only changes and don't need copying.

5. Merge your settings into the two files the installer rebuilt. `diff` shows the differences:
```
cd <openvdm_root>
diff www/etc/datadashboard.yaml.215 www/etc/datadashboard.yaml
diff www/app/Core/Config.php.215 www/app/Core/Config.php
```
   Make your changes in the 2.16 files; don't copy the `.215` files back.
   - **`www/etc/datadashboard.yaml`:** add your own tabs and panels. The new file has 2.16's:
     - CTD and XBT cast positions on the Position map;
     - CTD Casts and XBT Casts depth profiles on the Seawater tab;
     - a commented-out example Lowering tab.
   - **Its Position tab** no longer lists `lowering` in `jsArray`. 2.15's listed both `dataDashboardDefault` and `lowering`; each one builds every map on the page, so loading both logs `Map container is already initialized` (#185). Keep `lowering`, without `dataDashboardDefault`, only on tabs that use the `lowering` view. `lowering.js` and the `lowering` view themselves are fixed by the code update: their maps, charts and start/end positions hadn't loaded since 2.14.
   - **`www/app/Core/Config.php`:** copy over only the settings you'd changed yourself. The installer has already set `SITETITLE` to v2.16.0.
   - Keep the `.215` copies until the upgrade is working. Git doesn't ignore them, so `git status` lists them as untracked.
6. Restart the OpenVDM workers so they load the updated code and plugins:
```
sudo supervisorctl restart openvdm:*
```
7. Set OpenVDM back to On.
8. If you use either GeoTIFF parser, rebuild the data dashboard so existing Geographic Bounds stats are regenerated in the right order. Run **Rebuild Data Dashboard** under **Maintenance Tasks** on the **Configuration** page. This rebuilds the current cruise only; dashboard stats for earlier cruises keep the old (mislabelled) order.
9. If you've run `bin/build_remote_directory.py` to create template directories on a local-directory collection system, fix the permissions of the directories it created:
```
chmod 755 <directory>
```

If you update the web app's PHP or JavaScript libraries by hand instead of re-running the installer, run the commands as the OpenVDM user so the files it owns stay owned by it:
```
cd <openvdm_root>/www
sudo -H -u <openvdm_user> /usr/local/bin/composer install --no-dev
```
`composer install` also runs `npm install` (through `post_composer.sh`).

If you contribute to OpenVDM: `pre-commit` now also runs ESLint, `php -l` and PHPStan. Run `composer install` (without `--no-dev`) in `www/` to install PHPStan, and see CONTRIBUTING.md.
