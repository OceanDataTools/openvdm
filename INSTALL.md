# Open Vessel Data Management

## Installation Guide
At the time of this writing OpenVDM was built and tested against the Ubuntu 22.04 LTS and Rocky 8.5 operating systems.  There are distro-specific install scripts so use the one appropriate for the distro being installed to.  It may be possible to build against other linux-based operating systems however for the purposes of this guide the instructions will assume Ubuntu 22.04 LTS is used.

### Operating System
Goto <https://releases.ubuntu.com/22.04/>

### If you are installing OpenVDM remotely

If this is going to be a remote install then SSH Server must be installed.
```
apt install -y ssh
```

### Install OpenVDM and it's dependencies
Log into the Server as root

Download the install script
```
cd ~
curl https://raw.githubusercontent.com/oceandatatools/openvdm/master/utils/install-openvdm-ubuntu20.04.sh > ~/install-openvdm-ubuntu22.04.sh
```
If you see an error it could be because curl is not yet installed. Run the following command and try to download the install script again.
```
apt install -y curl
```

Run the install script
```
chmod +x ~/install-openvdm-ubuntu20.04.sh
~/install-openvdm-ubuntu20.04.sh
```

You will need to answer some questions about your configuration.

 - Name to assign to host? --> *This is the host name of the server*

 - Repository to install from? --> *This is the which OpenVDM repo you want to install from*
 
 - Repository branch to install? --> *This is the branch of the specified repo to download*

 - OpenVDM user to create? --> *This is the system user that will own the cruise data files.  This is also the username used to connect the OpenVDM web-app to the backend database*
 
 - OpenVDM Database password to use for user <user>? --> *This is the DATABASE user password for the database user.*

 - Current database password for root (hit return if this is the initial installation)? --> *This is the root password for the database*

 - Root data directory for OpenVDM? --> *This is the root directory that will contain all the cruise data for all cruises managed by OpenVDM. If this directory does not already exist you will be asked if you want it created.*

### All done... almost ###
At this point the warehouse should have a working installation of OpenVDM however the vessel operator will still need to configure data dashboard collection system transfers, cruise data transfers and the shoreside data warehouse.

To access the OpenVDM web-application goto: `<http://<hostname>>`
The default username/passwd is admin/demo

#### Reset the default password
 #Goto `<http://<hostname>>` and login (user icon, upper-right)
 #Click the user icon again and select "User Settings"
 #Set the desired password and optional change the admin username.

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
