#!/bin/bash -e

# OpenVDM is available as open source under the MIT License at
#   https:/github.com/oceandatatools/openvdm
#
# This script installs and configures OpenVDM to run on Rocky 8.4.  It
# is designed to be run as root. It should take a (relatively) clean
# Rocky 8.4 installation and install and configure all the components
# to run the full OpenVDM system.
#
# It should be re-run whenever the code has been refresh. Preferably
# by first running 'git pull' to get the latest copy of the script,
# and then running 'utils/build_openvdm_rocky8.4.sh' to run that
# script.
#
# The script has been designed to be idempotent, that is, if can be
# run over again with no ill effects.
#
# This script is somewhat rudimentary and has not been extensively
# tested. If it fails on some part of the installation, there is no
# guarantee that fixing the specific issue and simply re-running will
# produce the desired result.  Bug reports, and even better, bug
# fixes, will be greatly appreciated.

# set -o nounset
# set -o errexit
# set -o pipefail

PREFERENCES_FILE='.install_openvdm_preferences'

###########################################################################
###########################################################################
function exit_gracefully {
    echo Exiting.

    # Try deactivating virtual environment, if it's active
    if [ -n "$INSTALL_ROOT" ];then
        deactivate
    fi
    return -1 2> /dev/null || exit -1  # exit correctly if sourced/bashed
}

#########################################################################
#########################################################################
# Return a normalized yes/no for a value
yes_no() {
    QUESTION=$1
    DEFAULT_ANSWER=$2

    while true; do
        read -p "$QUESTION ($DEFAULT_ANSWER) " yn
        case $yn in
            [Yy]* )
                YES_NO_RESULT=yes
                break;;
            [Nn]* )
                YES_NO_RESULT=no
                break;;
            "" )
                YES_NO_RESULT=$DEFAULT_ANSWER
                break;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

###########################################################################
###########################################################################
# Read any pre-saved default variables from file
function set_default_variables {
    # Defaults that will be overwritten by the preferences file, if it
    # exists.
    DEFAULT_HOSTNAME=$HOSTNAME
    DEFAULT_INSTALL_ROOT=/opt

    DEFAULT_DATA_ROOT=/data

    DEFAULT_OPENVDM_REPO=https://github.com/oceandatatools/openvdm
    DEFAULT_OPENVDM_BRANCH=master
    DEFAULT_OPENVDM_SITEROOT=127.0.0.1

    DEFAULT_OPENVDM_USER=survey

    DEFAULT_INSTALL_MAPPROXY=no

    DEFAULT_INSTALL_PUBLICDATA=yes
    DEFAULT_INSTALL_VISITORINFORMATION=no

    DEFAULT_SUPERVISORD_WEBINTERFACE=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=no

    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e $PREFERENCES_FILE ]; then
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source $PREFERENCES_FILE
        echo branch $DEFAULT_OPENVDM_BRANCH
    fi
}


###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > $PREFERENCES_FILE <<EOF
# Defaults written by/to be read by install_openvdm_rocky8.4.sh

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=$INSTALL_ROOT

DEFAULT_OPENVDM_REPO=$OPENVDM_REPO
DEFAULT_OPENVDM_BRANCH=$OPENVDM_BRANCH

DEFAULT_DATA_ROOT=$DATA_ROOT
DEFAULT_OPENVDM_SITEROOT=$OPENVDM_SITEROOT

DEFAULT_OPENVDM_USER=$OPENVDM_USER

DEFAULT_INSTALL_MAPPROXY=$INSTALL_MAPPROXY

DEFAULT_INSTALL_PUBLICDATA=$INSTALL_PUBLICDATA
DEFAULT_INSTALL_VISITORINFORMATION=$INSTALL_VISITORINFORMATION

DEFAULT_SUPERVISORD_WEBINTERFACE=$SUPERVISORD_WEBINTERFACE
DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=$SUPERVISORD_WEBINTERFACE_AUTH
EOF
}


###########################################################################
###########################################################################
# Set hostname
function set_hostname {
    HOSTNAME=$1

    hostnamectl set-hostname $HOSTNAME
    # echo "HOSTNAME=$HOSTNAME" > /etc/sysconfig/network # not sure if needed

    ETC_HOSTS_LINE="127.0.1.1 $HOSTNAME $HOSTNAME"
    if grep -q "$ETC_HOSTS_LINE" /etc/hosts ; then
        echo Hostname already in /etc/hosts
    else
        echo "$ETC_HOSTS_LINE" >> /etc/hosts
    fi
}

###########################################################################
###########################################################################
# Create user
function create_user {

    OPENVDM_USER=$1

    echo "Checking if user $OPENVDM_USER exists yet"
    if id -u $OPENVDM_USER > /dev/null; then
        echo User exists, skipping
        return
    fi

    echo "Creating $OPENVDM_USER"
    adduser $OPENVDM_USER
    passwd $OPENVDM_USER
    usermod -a -G tty $OPENVDM_USER
    usermod -a -G wheel $OPENVDM_USER
}

###########################################################################
###########################################################################
# Install and configure required packages
function install_packages {

    startingDir=${PWD}

    yum install -y epel-release
    yum -y update --nobest

    # Install php7.3, Instructions at:
    # https://wiki.crowncloud.net/?How_to_Install_PHP_7_3_in_Rocky_Linux_8
    # https://techviewleo.com/install-lamp-stack-on-rocky-almalinux-8/
    yum install -y https://rpms.remirepo.net/enterprise/remi-release-8.rpm
    yum module reset php -y
    yum module enable php:remi-7.3 -y
    yum install -y php php-cli php-common php-gearman php-mysqlnd php-yaml php-zip 

    # Install Python3.8 and set to default
    yum install -y python38
    alternatives --set python /usr/bin/python3.8
    yum install -y python38-devel # python3-mod_wsgi

    yum -y install openssh-server sshpass rsync curl git samba samba-common \
    samba-client cifs-utils gearmand libgearman-devel nodejs supervisor \
    mysql-server npm httpd setroubleshoot policycoreutils-python-utils gcc \
    zlib-devel libjpeg-devel make python3-devel proj python3-pyproj python3-mod_wsgi

    pip3 install Pillow MapProxy

    if [ $INSTALL_MAPPROXY == 'yes' ]; then
    
        yum -y install gdal-bin libgeos-dev libgdal-dev proj-bin \
            python3-pyproj
        
        pip3 install MapProxy --quiet
    fi

    npm install --quiet -g bower

    cd ~
    curl -sS https://getcomposer.org/installer | php
    mv composer.phar /usr/local/bin/composer

    cd ${startingDir}
}


###########################################################################
###########################################################################
# Set up Python packages
function install_python_packages {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - path where openvdm is

    # Set up virtual environment
    VENV_PATH=$INSTALL_ROOT/openvdm/venv
    python -m venv $VENV_PATH
    source $VENV_PATH/bin/activate  # activate virtual environment

    pip install --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org --upgrade pip --quiet
    pip install wheel --quiet # To help with the rest of the installations

    sed 's/GDAL/# GDAL/' $INSTALL_ROOT/openvdm/requirements.txt | sed 's/pkg_resources/# pkg_resources/' > $INSTALL_ROOT/openvdm/requirements_no_gdal.txt
    pip install -r $INSTALL_ROOT/openvdm/requirements_no_gdal.txt
    
    deactivate

}


###########################################################################
###########################################################################
# Install and configure supervisor
function configure_supervisor {

    mv /etc/supervisord.conf /etc/supervisord.conf.orig

    sed -e '/### Added by OpenVDM install script ###/,/### Added by OpenVDM install script ###/d' /etc/supervisord.conf.orig |
    sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' > /etc/supervisord.conf

    if [ $SUPERVISORD_WEBINTERFACE == 'yes' ]; then
        cat >> /etc/supervisord.conf <<EOF

### Added by OpenVDM install script ###
[inet_http_server]
port=9001
EOF
        if [ $SUPERVISORD_WEBINTERFACE_AUTH == 'yes' ]; then
            SUPERVISORD_WEBINTERFACE_HASH=`echo -n ${SUPERVISORD_WEBINTERFACE_PASS} | sha1sum | awk '{printf("{SHA}%s",$1)}'`
            cat >> /etc/supervisord.conf <<EOF
username=${SUPERVISORD_WEBINTERFACE_USER}
password=${SUPERVISORD_WEBINTERFACE_HASH} ; echo -n "<password>" | sha1sum | awk '{printf("{SHA}%s",\$1)}'
EOF
        fi

      cat >> /etc/supervisord.conf <<EOF
### Added by OpenVDM install script ###
EOF
    fi

VENV_BIN=${INSTALL_ROOT}/openvdm/venv/bin

    cat > /etc/supervisord.d/openvdm.ini << EOF
[program:cruise]
command=${VENV_BIN}/python server/workers/cruise.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/cruise.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:cruise_directory]
command=${VENV_BIN}/python server/workers/cruise_directory.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/cruiseDirectory.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:data_dashboard]
command=${VENV_BIN}/python server/workers/data_dashboard.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/dataDashboard.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:lowering]
command=${VENV_BIN}/python server/workers/lowering.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/lowering.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:lowering_directory]
command=${VENV_BIN}/python server/workers/lowering_directory.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/lowering_directory.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:md5_summary]
command=${VENV_BIN}/python server/workers/md5_summary.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/md5_summary.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:post_hooks]
command=${VENV_BIN}/python server/workers/post_hooks.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/post_hooks.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:reboot_reset]
command=${VENV_BIN}/python server/workers/reboot_reset.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/reboot_reset.log
user=root
autostart=true
autorestart=false
stopsignal=INT

[program:run_collection_system_transfer]
command=${VENV_BIN}/python server/workers/run_collection_system_transfer.py
directory=${INSTALL_ROOT}/openvdm
process_name=%(program_name)s_%(process_num)s
numprocs=2
redirect_stderr=true
stdout_logfile=/var/log/openvdm/run_collection_system_transfer.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:run_cruise_data_transfer]
command=${VENV_BIN}/python server/workers/run_cruise_data_transfer.py
directory=${INSTALL_ROOT}/openvdm
process_name=%(program_name)s_%(process_num)s
numprocs=2
redirect_stderr=true
stdout_logfile=/var/log/openvdm/run_cruise_data_transfer.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:run_ship_to_shore_transfer]
command=${VENV_BIN}/python server/workers/run_ship_to_shore_transfer.py
directory=${INSTALL_ROOT}/openvdm
process_name=%(program_name)s_%(process_num)s
numprocs=2
redirect_stderr=true
stdout_logfile=/var/log/openvdm/run_ship_to_shore_transfer.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:scheduler]
command=${VENV_BIN}/python server/workers/scheduler.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/scheduler.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:size_cacher]
command=${VENV_BIN}/python server/workers/size_cacher.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/size_cacher.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:stop_job]
command=${VENV_BIN}/python server/workers/stop_job.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/stop_job.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:test_collection_system_transfer]
command=${VENV_BIN}/python server/workers/test_collection_system_transfer.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/test_collection_system_transfer.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[program:test_cruise_data_transfer]
command=${VENV_BIN}/python server/workers/test_cruise_data_transfer.py
directory=${INSTALL_ROOT}/openvdm
redirect_stderr=true
stdout_logfile=/var/log/openvdm/test_cruise_data_transfer.log
user=root
autostart=true
autorestart=true
stopsignal=INT

[group:openvdm]
programs=cruise,cruise_directory,data_dashboard,lowering,lowering_directory,md5_summary,post_hooks,reboot_reset,run_collection_system_transfer,run_cruise_data_transfer,run_ship_to_shore_transfer,scheduler,size_cacher,stop_job,test_collection_system_transfer,test_cruise_data_transfer

EOF

    echo "Updating Firewall rules for Supervisor Web Server"
    # TODO Check for firewall
    firewall-cmd --zone=public --add-port=9001/tcp --permanent || echo "No firewall installed"
    firewall-cmd --reload || echo "No firewall installed"

    echo "Starting new supervisor processes"
    systemctl restart supervisord
    systemctl enable supervisord

    supervisorctl reread
    supervisorctl update
    
}


###########################################################################
###########################################################################
# Install and configure gearman
function configure_gearman {
    echo "Starting Gearman Job Server"
    systemctl start gearmand
    systemctl enable gearmand
}


###########################################################################
###########################################################################
# Install and configure samba
function configure_samba {

    echo "Set smbpasswd for ${OPENVDM_USER}, recommended to use same password as system user"
    smbpasswd -a ${OPENVDM_USER}

    mv /etc/samba/smb.conf /etc/samba/smb.conf.orig

    sed -e 's/obey pam restrictions = yes/obey pam restrictions = no/' /etc/samba/smb.conf.orig |
    sed -e '/### Added by OpenVDM install script ###/,/### Added by OpenVDM install script ###/d' |
    sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba'  > /etc/samba/smb.conf
    
    cat >> /etc/samba/smb.conf <<EOF

/### Added by OpenVDM install script ###
include = /etc/samba/openvdm.conf
/### Added by OpenVDM install script ###
EOF

    cat > /etc/samba/openvdm.conf <<EOF
# SMB Shares for OpenVDM

[CruiseData]
  comment=Cruise Data, read-only access to guest
  path=${DATA_ROOT}/CruiseData
  browsable = yes
  public = yes
  hide unreadable = yes
  guest ok = yes
  writable = yes
  write list = ${OPENVDM_USER}
  create mask = 0644
  directory mask = 0755
  veto files = /._*/.DS_Store/.Trashes*/
  delete veto files = yes
EOF

if [ $INSTALL_VISITORINFORMATION == 'yes' ]; then
    cat >> /etc/samba/openvdm.conf <<EOF

[VisitorInformation]
  comment=Visitor Information, read-only access to guest
  path=${DATA_ROOT}/VisitorInformation
  browsable = yes
  public = yes
  guest ok = yes
  writable = yes
  write list = ${OPENVDM_USER}
  create mask = 0644
  directory mask = 0755
  veto files = /._*/.DS_Store/.Trashes*/
  delete veto files = yes
EOF
fi

if [ $INSTALL_PUBLICDATA == 'yes' ]; then
    cat >> /etc/samba/openvdm.conf <<EOF

[PublicData]
  comment=Public Data, read/write access to all
  path=${DATA_ROOT}/PublicData
  browseable = yes
  public = yes
  guest ok = yes
  writable = yes
  create mask = 0000
  directory mask = 0000
  veto files = /._*/.DS_Store/.Trashes*/
  delete veto files = yes
  force create mode = 666
  force directory mode = 777
EOF
fi

    echo "Updating firewall rules for samba"

    # TODO Check if firewall installed
    sudo firewall-cmd --add-service=samba --zone=public --permanent || echo "No firewall installed"
    sudo firewall-cmd --reload || echo "No firewall installed"

    echo "Restarting Samba Service"
    systemctl start smb
    systemctl enable smb
    systemctl start nmb
    systemctl enable nmb

}

###########################################################################
###########################################################################
# Setup Apache
function configure_apache {

    echo "Building new vhost file"
    cat > /etc/httpd/conf.d/openvdm.conf <<EOF
<VirtualHost *:80>
    ServerName $HOSTNAME

    ServerAdmin webmaster@localhost
    DocumentRoot /var/www/openvdm

    # Available loglevels: trace8, ..., trace1, debug, info, notice, warn,
    # error, crit, alert, emerg.
    # It is also possible to configure the loglevel for particular
    # modules, e.g.
    #LogLevel info ssl:warn

    ErrorLog /var/log/httpd/openvdm_error.log
    CustomLog /var/log/httpd/openvdm_requests.log combined

    # For most configuration files from conf-available/, which are
    # enabled or disabled at a global level, it is possible to
    # include a line for only one particular virtual host. For example the
    # following line enables the CGI configuration for this host only
    # after it has been globally disabled with "a2disconf".
    #Include conf-available/serve-cgi-bin.conf

    <Directory "/var/www/openvdm">
      AllowOverride all
    </Directory>
EOF

if [ $INSTALL_MAPPROXY == 'yes' ]; then
    cat >> /etc/httpd/conf.d/openvdm.conf <<EOF

    WSGIScriptAlias /mapproxy /var/www/mapproxy/config.py

    <Directory /var/www/mapproxy/>
      Allow from all
      Require all granted
    </Directory>
EOF
fi

cat >> /etc/httpd/conf.d/openvdm.conf <<EOF

    Alias /CruiseData/ $DATA_ROOT/CruiseData/
    <Directory "$DATA_ROOT/CruiseData">
      AllowOverride None
      Options +Indexes -FollowSymLinks +MultiViews
      Order allow,deny
      Allow from all
      Require all granted
    </Directory>
EOF

if [ $INSTALL_PUBLICDATA == 'yes' ]; then
    cat >> /etc/httpd/conf.d/openvdm.conf <<EOF

    Alias /PublicData/ $DATA_ROOT/PublicData/
    <Directory "$DATA_ROOT/PublicData">
      AllowOverride None
      Options +Indexes -FollowSymLinks +MultiViews
      Order allow,deny
      Allow from all
      Require all granted
    </Directory>
EOF
fi

if [ $INSTALL_VISITORINFORMATION == 'yes' ]; then
    cat >> /etc/httpd/conf.d/openvdm.conf <<EOF

    Alias /VisitorInformation/ $DATA_ROOT/VisitorInformation/
    <Directory "$DATA_ROOT/VisitorInformation">
      AllowOverride None
      Options +Indexes -FollowSymLinks +MultiViews
      Order allow,deny
      Allow from all
      Require all granted
    </Directory>
EOF
fi

cat >> /etc/httpd/conf.d/openvdm.conf <<EOF

</VirtualHost>
EOF

    echo "Updating Firewall rules for Apache Web Server"
    # TODO Check for firewall
    firewall-cmd --permanent --add-service={http,https} || echo "No firewall installed"
    firewall-cmd --reload || echo "No firewall installed"

    echo "Setting SELinux exception rules"
    chcon -R -t httpd_sys_content_t ${DATA_ROOT}
    chcon -R -t httpd_sys_rw_content_t /var/www/openvdm/errorlog.html

    if [ $INSTALL_MAPPROXY == 'yes' ]; then
        chcon -R system_u:object_r:httpd_sys_script_exec_t:s0 /var/www/mapproxy
        chcon -R -t httpd_sys_rw_content_t /var/www/mapproxy/cache_data
    fi

    setsebool httpd_tmp_exec on
    setsebool -P httpd_can_network_connect=1

    echo "Restarting Apache Web Server"
    sudo systemctl enable --now httpd
    sudo systemctl restart httpd

}


###########################################################################
###########################################################################
# Install and configure database
function configure_mapproxy {
    
    if [ $INSTALL_MAPPROXY == 'yes' ]; then

        startingDir=${PWD}

        cd ~
        mapproxy-util create -t base-config --force mapproxy

        cat > ~/mapproxy/mapproxy.yaml <<EOF
# -------------------------------
# MapProxy configuration.
# -------------------------------

# Start the following services:
services:
  demo:
  tms:
    use_grid_names: false
    # origin for /tiles service
    origin: 'nw'
  kml:
    #use_grid_names: true
  wmts:
  wms:
    srs: ['EPSG:900913']
    image_formats: ['image/png']
    md:
      title: MapProxy WMS Proxy
      abstract: This is a minimal MapProxy installation.

#Make the following layers available
layers:
  - name: WorldOceanBase
    title: ESRI World Ocean Base
    sources: [esri_worldOceanBase_cache]

  - name: WorldOceanReference
    title: ESRI World Ocean Reference
    sources: [esri_worldOceanReference_cache]

caches:
  esri_worldOceanBase_cache:
    grids: [esri_online]
    sources: [esri_worldOceanBase]

  esri_worldOceanReference_cache:
    grids: [esri_online]
    sources: [esri_worldOceanReference]

sources:
  esri_worldOceanBase:
    type: tile
    url: http://server.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/%(z)s/%(y)s/%(x)s.png
    grid: esri_online

  esri_worldOceanReference:
    type: tile
    transparent: true
    url: http://server.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/%(z)s/%(y)s/%(x)s.png
    grid: esri_online

grids:
  webmercator:
    base: GLOBAL_WEBMERCATOR

  esri_online:
     tile_size: [256, 256]
     srs: EPSG:900913
     origin: 'nw'
     num_levels: 11

globals:
EOF

        cp -r ~/mapproxy /var/www/mapproxy
        mkdir /var/www/mapproxy/cache_data
        chmod 777 /var/www/mapproxy/cache_data

        cd /var/www/mapproxy
        mapproxy-util create -t wsgi-app -f mapproxy.yaml --force config.py

        # sed -e "s|cgi import|html import|" /usr/lib/python3/dist-packages/mapproxy/service/template_helper.py > /usr/lib/python3/dist-packages/mapproxy/service/template_helper.py
        cd ${startingDir}
    fi
}

###########################################################################
###########################################################################
# Install and configure database
function configure_mysql {
    # Expect the following shell variables to be appropriately set:
    # OPENVDM_USER - valid userid
    # OPENVDM_DATABASE_PASSWORD - current OpenVDM user MySQL database password
    # NEW_ROOT_DATABASE_PASSWORD - new root password to use for MySQL
    # CURRENT_ROOT_DATABASE_PASSWORD - current root password for MySQL

    echo "Enabling MySQL Database Server"

    systemctl enable mysqld    # to make it start on boot
    systemctl start mysqld     # to manually start db server

    echo "Setting up database root user and permissions"
    # Verify current root password for mysql
    while true; do
        # Check whether they're right about the current password; need
        # a special case if the password is empty.
        PASS=TRUE
        [ ! -z $CURRENT_ROOT_DATABASE_PASSWORD ] || (mysql -u root  < /dev/null) || PASS=FALSE
        [ -z $CURRENT_ROOT_DATABASE_PASSWORD ] || (mysql -u root -p$CURRENT_ROOT_DATABASE_PASSWORD 2> /dev/null < /dev/null) || PASS=FALSE
        case $PASS in
            TRUE ) break;;
            * ) echo "Database root password failed";read -p "Current database password for root? (if one exists - hit return if not) " CURRENT_ROOT_DATABASE_PASSWORD;;
        esac
    done

    # Set the new root password
    cat > /tmp/set_pwd <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$NEW_ROOT_DATABASE_PASSWORD';
FLUSH PRIVILEGES;
EOF

    # If there's a current root password
    [ -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root -p$CURRENT_ROOT_DATABASE_PASSWORD 2> /dev/null < /tmp/set_pwd

    # If there's no current root password
    [ ! -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root < /tmp/set_pwd
    rm -f /tmp/set_pwd

    echo "Setting up OpenVDM database user"
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD 2> /dev/null <<EOF
drop user if exists '$OPENVDM_USER'@'localhost';
create user '$OPENVDM_USER'@'localhost' IDENTIFIED WITH mysql_native_password BY '$OPENVDM_DATABASE_PASSWORD';
flush privileges;
\q
EOF
    echo "Done setting up MySQL"
}

###########################################################################
###########################################################################
# Create the various directories needed for the install
function configure_directories {

    if [ ! -d $DATA_ROOT ]; then
        echo "Creating initial data directory structure starting at: $DATA_ROOT"

        mkdir -p ${DATA_ROOT}/CruiseData/Test_Cruise/Vehicle/Test_Lowering
        mkdir -p ${DATA_ROOT}/CruiseData/Test_Cruise/OpenVDM/DashboardData
        mkdir -p ${DATA_ROOT}/CruiseData/Test_Cruise/OpenVDM/TransferLogs

        echo "[]" > ${DATA_ROOT}/CruiseData/Test_Cruise/OpenVDM/DashboardData/manifest.json
        echo "{}" > ${DATA_ROOT}/CruiseData/Test_Cruise/ovdmConfig.json
        echo "{}" > ${DATA_ROOT}/CruiseData/Test_Cruise/Vehicle/Test_Lowering/loweringConfig.json
        touch ${DATA_ROOT}/CruiseData/Test_Cruise/MD5_Summary.md5
        touch ${DATA_ROOT}/CruiseData/Test_Cruise/MD5_Summary.txt

        if [ $INSTALL_PUBLICDATA == 'yes' ]; then
            mkdir -p ${DATA_ROOT}/PublicData
            chmod -R 777 ${DATA_ROOT}/PublicData
        fi

        if [ $INSTALL_VISITORINFORMATION == 'yes' ]; then
            mkdir -p ${DATA_ROOT}/VisitorInformation
        fi

        chown -R ${OPENVDM_USER}:${OPENVDM_USER} $DATA_ROOT/*
    fi

    if [ ! -d  /var/log/openvdm ]; then
        echo "Creating logfile directory"
        mkdir -p /var/log/openvdm
    fi

}



###########################################################################
###########################################################################
# Set system timezone
function setup_timezone {
    sudo timedatectl set-timezone UTC
}


###########################################################################
###########################################################################
# Set system ssh
function setup_ssh {

    if [ ! -e ~/.ssh/id_rsa.pub ]; then
        cat /dev/zero | ssh-keygen -q -N "" > /dev/null
        cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
    fi

    if [ ! -e /home/${OPENVDM_USER}/.ssh/authorized_keys ]; then
        mkdir -p /home/${OPENVDM_USER}/.ssh
        cat ~/.ssh/id_rsa.pub >> /home/${OPENVDM_USER}/.ssh/authorized_keys
    
        chown -R ${OPENVDM_USER}:${OPENVDM_USER} /home/${OPENVDM_USER}/.ssh
        chmod 600 /home/${OPENVDM_USER}/.ssh/authorized_keys
    fi

    ssh ${OPENVDM_USER}@${HOSTNAME} ls > /dev/null
}


###########################################################################
###########################################################################
# Install OpenVDM
function install_openvdm {
    # Expect the following shell variables to be appropriately set:
    # DATA_ROOT - path where data will be stored is
    # OPENVDM_USER - valid userid
    # OPENVDM_REPO - path to OpenVDM repo
    # OPENVDM_BRANCH - branch of rep to install

    startingDir=${PWD}

    if [ ! -d ${INSTALL_ROOT}/openvdm ]; then  # New install
        echo "Downloading OpenVDM repository"
        cd $INSTALL_ROOT
        git clone -b $OPENVDM_BRANCH $OPENVDM_REPO ./openvdm
        chown -R ${OPENVDM_USER}:${OPENVDM_USER} ./openvdm

    else
        cd ${INSTALL_ROOT}/openvdm

        if [ -e .git ] ; then   # If we've already got an installation
            echo "Updating existing OpenVDM repository"
            sudo -u ${OPENVDM_USER} git pull
            sudo -u ${OPENVDM_USER} git checkout $OPENVDM_BRANCH
            sudo -u ${OPENVDM_USER} git pull

        else
            echo "Reinstalling OpenVDM from repository"  # Bad install, re-doing
            cd ..
            rm -rf openvdm
            sudo -u ${OPENVDM_USER} git clone -b $OPENVDM_BRANCH $OPENVDM_REPO ./openvdm
        fi
    fi

    cd ${INSTALL_ROOT}/openvdm

    if mysql --user=root --password=${NEW_ROOT_DATABASE_PASSWORD} -e 'use openvdm' 2> /dev/null; then
        echo "openvdm database found, skipping database setup"
        mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD 2> /dev/null <<EOF
GRANT ALL PRIVILEGES ON openvdm.* TO '$OPENVDM_USER'@'localhost';
flush privileges;
\q
EOF

    else
        echo "Creating OpenVDM database"
        sed -e "s/survey/${OPENVDM_USER}/" ${INSTALL_ROOT}/openvdm/database/openvdm_db.sql | \
        sed -e "s/127\.0\.0\.1/${OPENVDM_SITEROOT}/" \
        > ${INSTALL_ROOT}/openvdm/database/openvdm_db_custom.sql

        if [ $INSTALL_PUBLICDATA == 'no' ]; then
            sed -i -e "/Public Data/d" ${INSTALL_ROOT}/openvdm/database/openvdm_db_custom.sql 
        fi

        if [ $INSTALL_VISITORINFORMATION == 'no' ]; then
            sed -i -e "/Visitor Information/d" ${INSTALL_ROOT}/openvdm/database/openvdm_db_custom.sql
        fi

        hashed_password=$(php -r "echo password_hash('${OPENVDM_DATABASE_PASSWORD}', PASSWORD_DEFAULT);")
    cat >> ${INSTALL_ROOT}/openvdm/database/openvdm_db_custom.sql <<EOF 

INSERT INTO OVDM_Users (username, password)
VALUES ('${OPENVDM_USER}', '${hashed_password}');
EOF

        mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD 2> /dev/null <<EOF
create database if not exists openvdm character set utf8;
GRANT ALL PRIVILEGES ON openvdm.* TO '$OPENVDM_USER'@'localhost';
USE openvdm;
source ./database/openvdm_db_custom.sql;
flush privileges;
\q
EOF
    fi

    echo "Building web-app"
    cd ${INSTALL_ROOT}/openvdm/www
    /usr/local/bin/composer -q install


    if [ ! -e ${INSTALL_ROOT}/openvdm/www/.htaccess ] ; then
        cp ${INSTALL_ROOT}/openvdm/www/.htaccess.dist ${INSTALL_ROOT}/openvdm/www/.htaccess
    fi

    if [ ! -e ${INSTALL_ROOT}/openvdm/www/etc/datadashboard.yaml ] ; then
        cp ${INSTALL_ROOT}/openvdm/www/etc/datadashboard.yaml.dist ${INSTALL_ROOT}/openvdm/www/etc/datadashboard.yaml
    fi

    sed -s "s/define('DB_USER', 'openvdmDBUser');/define('DB_USER', '${OPENVDM_USER}');/" ${INSTALL_ROOT}/openvdm/www/app/Core/Config.php.dist | \
    sed -e "s/define('DB_PASS', 'oxhzbeY8WzgBL3');/define('DB_PASS', '${OPENVDM_DATABASE_PASSWORD}');/" | \
    sed -e "s|define('CRUISEDATA_BASEDIR', '/data/CruiseData');|define('CRUISEDATA_BASEDIR', '${DATA_ROOT}/CruiseData');|" | \
    sed -e "s|define('PUBLICDATA_DIR', '/data/PublicData');|define('PUBLICDATA_DIR', '${DATA_ROOT}/PublicData');|" \
    > ${INSTALL_ROOT}/openvdm/www/app/Core/Config.php

    if [ -e ${INSTALL_ROOT}/openvdm/www/errorlog.html ] ; then
        rm ${INSTALL_ROOT}/openvdm/www/errorlog.html
    fi

    touch ${INSTALL_ROOT}/openvdm/www/errorlog.html
    chmod 777 ${INSTALL_ROOT}/openvdm/www/errorlog.html
    chown -R root:root ${INSTALL_ROOT}/openvdm/www

    echo "Installing web-app"

    if [ ! -e /var/www/openvdm ]; then
        ln -s ${INSTALL_ROOT}/openvdm/www /var/www/openvdm
    fi

    if [ ! -e ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml ] ; then
        echo "Building server configuration file"
        sed -e "s/127.0.0.1/${HOSTNAME}/" ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml.dist > ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml

        if [ $INSTALL_PUBLICDATA == 'no' ]; then
            sed -i -e "s/transferPubicData: True/transferPubicData: False/" ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml
        fi

        chown -R ${OPENVDM_USER}:${OPENVDM_USER} ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml
    fi

    cd ${startingDir}
}


###########################################################################
###########################################################################
# Start of actual script
###########################################################################

# Read from the preferences file in $PREFERENCES_FILE, if it exists
set_default_variables

if [ "$(whoami)" != "root" ]; then
    echo "ERROR: installation script must be run as root."
    exit_gracefully
fi


echo "#####################################################################"
echo "OpenVDM configuration script"
echo "#####################################################################"
read -p "Name to assign to host ($DEFAULT_HOSTNAME)? " HOSTNAME
HOSTNAME=${HOSTNAME:-$DEFAULT_HOSTNAME}
echo "Hostname will be '$HOSTNAME'"
# Set hostname
set_hostname $HOSTNAME
echo

read -p "OpenVDM install root directory? ($DEFAULT_INSTALL_ROOT) " INSTALL_ROOT
INSTALL_ROOT=${INSTALL_ROOT:-$DEFAULT_INSTALL_ROOT}

read -p "Repository to install from? ($DEFAULT_OPENVDM_REPO) " OPENVDM_REPO
OPENVDM_REPO=${OPENVDM_REPO:-$DEFAULT_OPENVDM_REPO}

read -p "Repository branch to install? ($DEFAULT_OPENVDM_BRANCH) " OPENVDM_BRANCH
OPENVDM_BRANCH=${OPENVDM_BRANCH:-$DEFAULT_OPENVDM_BRANCH}
echo

echo "Will install from github.com"
echo "Repository: '$OPENVDM_REPO'"
echo "Branch: '$OPENVDM_BRANCH'"
echo "Access URL: 'http://$OPENVDM_SITEROOT'"
echo

echo "#####################################################################"
read -p "IP Address or URL users will access OpenVDM from? ($DEFAULT_OPENVDM_SITEROOT) " OPENVDM_SITEROOT
OPENVDM_SITEROOT=${OPENVDM_SITEROOT:-$DEFAULT_OPENVDM_SITEROOT}
echo
echo "Access URL: 'http://$OPENVDM_SITEROOT'"
echo

# Create user if they don't exist yet
echo "#####################################################################"
read -p "OpenVDM user to create? ($DEFAULT_OPENVDM_USER) " OPENVDM_USER
OPENVDM_USER=${OPENVDM_USER:-$DEFAULT_OPENVDM_USER}
create_user $OPENVDM_USER
echo

echo "#####################################################################"
echo "Gathing information for MySQL installation/configuration"
echo "Root database password will be empty on initial installation. If this"
echo "is the initial installation, hit "return" when prompted for root"
echo "database password, otherwise enter the password you used during the"
echo "initial installation."
echo
echo "Current root user password for MySQL (hit return if this is the"
read -p "initial installation)? " CURRENT_ROOT_DATABASE_PASSWORD
read -p "New/updated root user password for MySQL? ($CURRENT_ROOT_DATABASE_PASSWORD) " NEW_ROOT_DATABASE_PASSWORD
NEW_ROOT_DATABASE_PASSWORD=${NEW_ROOT_DATABASE_PASSWORD:-$CURRENT_ROOT_DATABASE_PASSWORD}
echo

read -p "New password for MySQL user: $OPENVDM_USER? ($OPENVDM_USER) " OPENVDM_DATABASE_PASSWORD
OPENVDM_DATABASE_PASSWORD=${OPENVDM_DATABASE_PASSWORD:-$OPENVDM_USER}
echo

echo "#####################################################################"
echo "Gathering information on where OpenVDM should store cruise data files"
echo "The root data directory needs to be large enough to store at least a"
echo "single cruise worth of data but ideally should be large enougn to"
echo "hold several cruises worth of data."
echo
echo "It is recommended that the root data directory be located on a"
echo "mounted volume that is independent of the volume used for the"
echo "operating system. This simplifies disaster recovery and system"
echo "updates"
echo
read -p "Root data directory for OpenVDM? ($DEFAULT_DATA_ROOT) " DATA_ROOT
DATA_ROOT=${DATA_ROOT:-$DEFAULT_DATA_ROOT}

if [ ! -d $DATA_ROOT ]; then
    yes_no "Root data directory ${DATA_ROOT} does not exists... create it? " "yes"
    
    if [ $YES_NO_RESULT == "no" ]; then
        exit
    fi
fi
echo

#########################################################################
# Enable Supervisor web-interface?
echo "#####################################################################"
echo "The supervisord service provides an optional web-interface that enables"
echo "operators to start/stop/restart the OpenVDM main processes from a web-"
echo "browser."
echo
yes_no "Enable Supervisor Web-interface? " $DEFAULT_SUPERVISORD_WEBINTERFACE
SUPERVISORD_WEBINTERFACE=$YES_NO_RESULT

if [ $SUPERVISORD_WEBINTERFACE == 'yes' ]; then

    yes_no "Enable user/pass on Supervisor Web-interface? " $DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH
    SUPERVISORD_WEBINTERFACE_AUTH=$YES_NO_RESULT

    if [ $SUPERVISORD_WEBINTERFACE_AUTH == 'yes' ]; then

        read -p "Username? ($OPENVDM_USER) " SUPERVISORD_WEBINTERFACE_USER
        SUPERVISORD_WEBINTERFACE_USER=${SUPERVISORD_WEBINTERFACE_USER:-$OPENVDM_USER}

        read -p "Password? ($OPENVDM_USER) " SUPERVISORD_WEBINTERFACE_PASS
        SUPERVISORD_WEBINTERFACE_PASS=${SUPERVISORD_WEBINTERFACE_PASS:-$OPENVDM_USER}
    fi
fi
echo

#########################################################################
# Install MapProxy?
echo "#####################################################################"
echo "Optionally install: MapProxy"
echo "MapProxy is used for caching map tiles from ESRI and Google. This can"
echo "reduce ship-to-shore network traffic for GIS-enabled webpages."
echo
yes_no "Install MapProxy? " $DEFAULT_INSTALL_MAPPROXY
INSTALL_MAPPROXY=$YES_NO_RESULT
echo

#########################################################################
# Install PublicData?
echo "#####################################################################"
echo "Setup a PublicData SMB Share for scientists and crew to share files,"
echo "pictures, etc. These files will be copied to the cruise data "
echo "directory at the end of the cruise. This behavior can be disabled in"
echo "the ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml file."
echo
yes_no "Setup PublicData Share? " $DEFAULT_INSTALL_PUBLICDATA
INSTALL_PUBLICDATA=$YES_NO_RESULT
echo

#########################################################################
# Install VisitorInformation?
echo "#####################################################################"
echo "Setup a VistorInformation SMB Share for sharing documentation, print"
echo "drivers, etc with crew and scientists."
echo
yes_no "Setup VisitorInformation Share? " $DEFAULT_INSTALL_VISITORINFORMATION
INSTALL_VISITORINFORMATION=$YES_NO_RESULT
echo

#########################################################################
#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

#########################################################################
# The rest of the installtion
echo "#####################################################################"
echo "Installing required software packages and libraries"
install_packages

echo "#####################################################################"
echo "Setting system timezone to UTC"
setup_timezone

echo "#####################################################################"
echo "Setting ssh pubic/private keys"
setup_ssh

echo "#####################################################################"
echo "Creating required directories"
configure_directories

echo "#####################################################################"
echo "Configuring Samba"
configure_samba

echo "#####################################################################"
echo "Configuring Gearman Job Server"
configure_gearman

echo "#####################################################################"
echo "Configuring MySQL"
configure_mysql

echo "#####################################################################"
echo "Installing/Configuring OpenVDM"
install_openvdm

echo "#####################################################################"
echo "Installing additional python libraries"
install_python_packages

echo "#####################################################################"
echo "Installing/Configuring MapProxy"
configure_mapproxy

echo "#####################################################################"
echo "Configuring Apache2"
configure_apache

echo "#####################################################################"
echo "Configuring Supervisor"
configure_supervisor

echo "#####################################################################"
echo "OpenVDM Installation: Complete"
echo "OpenVDM WebUI available at: http://${OPENVDM_SITEROOT}"
echo "Login with user: ${OPENVDM_USER}, pass: ${OPENVDM_DATABASE_PASSWORD}"
echo "Cruise Data will be stored at: ${DATA_ROOT}/CruiseData"
echo

#########################################################################
#########################################################################
