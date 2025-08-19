# Open Vessel Data Management

## Installation Guide
At the time of this writing OpenVDM was built and tested against the Ubuntu 22.04 LTS and Rocky 8.5 operating systems.  There are distro-specific install scripts so use the one appropriate for the distro being installed to.  It may be possible to build against other linux-based operating systems however for the purposes of this guide the instructions will assume Ubuntu 22.04 LTS is used.

### Operating Systems
 - Ubuntu 22.04: <https://releases.ubuntu.com/22.04/>
 - Rocky 8.10 <https://rockylinux.org/news/rocky-linux-8-10-ga-release>

### If you are installing OpenVDM remotely

If this is going to be a remote install then SSH Server must be installed.
```
apt install -y ssh
```

### Install OpenVDM and it's dependencies
Log into the Server as root

Download the install script
```
export OPENVDM_REPO=raw.githubusercontent.com/oceandatatools/openvdm
export BRANCH=master
wget -O install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm-ubuntu22.04.sh

# Alternate script for installing on Rocky/RHEL 8
# wget -O install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm-rocky8.10.sh

chmod +x install-openvdm.sh
sudo ./install-openvdm.sh
```

If wget is not available you can install it or use the following `curl` command:
```
curl -L -o install-openvdm.sh https://$OPENVDM_REPO/$BRANCH/utils/install-openvdm-ubuntu22.04.sh
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

Install MapProxy?  (no) 
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
Setup a VistorInformation SMB Share for sharing documentation, print
drivers, etc with crew and scientists.

Setup VisitorInformation Share?  (no) 
```

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
