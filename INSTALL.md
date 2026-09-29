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

OpenVDM v2.15 moves away from PHP 7.3 to PHP 8.2.  This isn't a trivial change and will require the installation of PHP 8.2 and reconfiguration of Apache to use the new version.  Recommend backing up the OpenVDM database and reinstalling OpenVDM onto a fresh OS install using the updated ./utils/install_openvdm.sh script. 

## Upgrading from 2.15.

OpenVDM v2.16 adds FTP Server as a collection system transfer type (#17), which needs a database update (step 3). Several plugins, parsers and `bin/` scripts were also fixed, and the installer doesn't update your copies of those. See the 2.16.0 entry in [CHANGELOG.md](CHANGELOG.md) for the details of each change.

1. Make sure OpenVDM is set to Off and that there are no running transfers or tasks.
2. Update the code and dependencies by re-running the installer. It's safe to run over an existing install. It pulls the latest code, runs `composer install --no-dev` (which also removes any Composer development packages, such as PHPStan) and reinstalls the JavaScript libraries (`npm install`). Both now run as the OpenVDM user instead of root. On Debian and Ubuntu the installer also moves Node.js (nvm) from root's home directory to the OpenVDM user's, so that user can run npm, and removes the old `/root/.nvm` and its lines in root's `.bashrc`. If root installed other global npm packages in `/root/.nvm`, it's kept and the installer says so. It asks the same questions as the original install, with your previous answers as the defaults:
```
cd <openvdm_root>
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

5. Update two settings files by hand (the installer doesn't change your copies):
   - In `www/etc/datadashboard.yaml`, delete the `- lowering` line from the Position tab's `jsArray`. The shipped Position tab listed both `dataDashboardDefault` and `lowering`; each one builds every map on the page, so loading both logs `Map container is already initialized` (#185). The same applies to any other tab that lists both: keep `lowering` (without `dataDashboardDefault`) only on tabs that use the `lowering` view. `lowering.js` and the `lowering` view themselves are fixed by the code update: their maps, charts and start/end positions hadn't loaded since 2.14. To add a lowering tab, see the commented-out example Lowering tab at the end of `www/etc/datadashboard.yaml.dist`.
   - Optional: to show the new version in the web interface's title, change `SITETITLE` in `www/app/Core/Config.php` to `'Open Vessel Data Management v2.16.0'`.

   No other settings in `Config.php`, `openvdm.yaml` or `datadashboard.yaml` changed.
6. Restart the OpenVDM workers so they load the updated code and plugins:
```
sudo supervisorctl restart openvdm:*
```
7. Set OpenVDM back to On.
8. If you use either GeoTIFF parser, rebuild the data dashboard so existing Geographic Bounds stats are regenerated in the right order. While logged in to the web interface, open `http://<openvdm_host>/config/rebuildDataDashboard`. There's no button for this. This rebuilds the current cruise only; dashboard stats for earlier cruises keep the old (mislabelled) order.
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
