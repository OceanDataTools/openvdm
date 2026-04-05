#!/bin/bash -e

# OpenVDM is available as open source under the MIT License at
#   https://github.com/oceandatatools/openvdm
#
# This script installs and configures OpenVDM.  It supports:
#   - Ubuntu 22.04 (Jammy) and 24.04 (Noble)
#   - Debian 12 (Bookworm) and 13 (Trixie)
#   - AlmaLinux 8/9, Rocky Linux 8/9, RHEL 8/9
#
# It is designed to be run as root. It should take a (relatively) clean
# installation and install and configure all the components to run the
# full OpenVDM system.
#
# It should be re-run whenever the code has been refreshed. Preferably
# by first running 'git pull' to get the latest copy of the script,
# and then running 'utils/install-openvdm.sh' to run that script.
#
# The script has been designed to be idempotent, that is, it can be
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
# set -o xtrace

PREFERENCES_FILE='.install_openvdm_preferences'


###########################################################################
###########################################################################
function exit_gracefully {
    echo Exiting.

    # Try deactivating virtual environment, if it's active
    if [ -n "$INSTALL_ROOT" ]; then
        deactivate 2>/dev/null || true
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
# Run firewall-cmd with the given arguments and reload, but only if
# firewall-cmd is available on this system.
function firewall_cmd_if_available {
    if command -v firewall-cmd > /dev/null 2>&1; then
        firewall-cmd "$@"
        firewall-cmd --reload
    fi
}

###########################################################################
###########################################################################
# Detect the operating system and set distro-specific variables
function detect_os {

    if [ ! -f /etc/os-release ]; then
        echo "ERROR: Cannot detect OS (/etc/os-release not found)"
        exit_gracefully
    fi

    # Source /etc/os-release to get ID, VERSION_ID, VERSION_CODENAME, etc.
    . /etc/os-release
    OS_ID="${ID}"
    OS_ID_LIKE="${ID_LIKE:-}"
    OS_VERSION_ID="${VERSION_ID:-0}"
    OS_VERSION_MAJOR="${VERSION_ID%%.*}"
    OS_CODENAME="${VERSION_CODENAME:-}"

    # Determine OS family
    case "$OS_ID" in
        ubuntu|debian)
            OS_FAMILY="debian"
            ;;
        rhel|centos|rocky|almalinux|fedora)
            OS_FAMILY="rhel"
            ;;
        *)
            if echo "$OS_ID_LIKE" | grep -qE "(debian|ubuntu)"; then
                OS_FAMILY="debian"
            elif echo "$OS_ID_LIKE" | grep -qE "(rhel|fedora|centos)"; then
                OS_FAMILY="rhel"
            else
                echo "ERROR: Unsupported OS: $OS_ID"
                exit_gracefully
            fi
            ;;
    esac

    # Set distro-specific service names and paths
    if [ "$OS_FAMILY" = "debian" ]; then
        APACHE_SERVICE="apache2"
        APACHE_CONF_DIR="/etc/apache2/sites-available"
        # Use the literal Apache variable string (bash heredoc will expand this
        # shell variable to its value, which Apache then interprets at runtime)
        APACHE_LOG_DIR="\${APACHE_LOG_DIR}"
        APACHE_USER="www-data"
        SUPERVISOR_CONF="/etc/supervisor/supervisord.conf"
        SUPERVISOR_CONF_D="/etc/supervisor/conf.d"
        SUPERVISOR_PROG_EXT="conf"
        SUPERVISOR_SERVICE="supervisor"
        # Ubuntu repos ship mysql-server; Debian ships mariadb-server
        MYSQL_SERVICE=$([ "$OS_ID" = "ubuntu" ] && echo "mysql" || echo "mariadb")
        GEARMAN_SERVICE="gearman-job-server"
        SAMBA_SERVICES="smbd nmbd"
        RSYNC_SERVICE="rsync"
        SUDO_GROUP="sudo"
        HAS_SELINUX=false
    else
        APACHE_SERVICE="httpd"
        APACHE_CONF_DIR="/etc/httpd/conf.d"
        APACHE_LOG_DIR="/var/log/httpd"
        APACHE_USER="apache"
        SUPERVISOR_CONF="/etc/supervisord.conf"
        SUPERVISOR_CONF_D="/etc/supervisord.d"
        SUPERVISOR_PROG_EXT="ini"
        SUPERVISOR_SERVICE="supervisord"
        MYSQL_SERVICE="mysqld"
        GEARMAN_SERVICE="gearmand"
        SAMBA_SERVICES="smb nmb"
        RSYNC_SERVICE="rsyncd"
        SUDO_GROUP="wheel"
        HAS_SELINUX=true
    fi

    echo "Detected OS: $OS_ID $OS_VERSION_ID ($OS_FAMILY family)"
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
    DEFAULT_MAPPROXY_CACHE=

    DEFAULT_INSTALL_PUBLICDATA=yes
    DEFAULT_INSTALL_VISITORINFORMATION=no

    DEFAULT_INSTALL_TITILER=no
    DEFAULT_TITILER_PORT=8000

    DEFAULT_INSTALL_SAMPLEDATA=no
    DEFAULT_SAMPLEDATA_ROOT=/data/sample_data
    DEFAULT_SAMPLEDATA_REPO=https://github.com/oceandatatools/openvdm_sample_data
    DEFAULT_SAMPLEDATA_BRANCH=master

    DEFAULT_SUPERVISORD_WEBINTERFACE=no
    DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=no

    # Read in the preferences file, if it exists, to overwrite the defaults.
    if [ -e "$PREFERENCES_FILE" ]; then
        echo Reading pre-saved defaults from "$PREFERENCES_FILE"
        source "$PREFERENCES_FILE"
        echo branch $DEFAULT_OPENVDM_BRANCH
    fi
}


###########################################################################
###########################################################################
# Save defaults in a preferences file for the next time we run.
function save_default_variables {
    cat > "$PREFERENCES_FILE" <<EOF
# Defaults written by/to be read by install-openvdm.sh

DEFAULT_HOSTNAME=$HOSTNAME
DEFAULT_INSTALL_ROOT=$INSTALL_ROOT

DEFAULT_OPENVDM_REPO=$OPENVDM_REPO
DEFAULT_OPENVDM_BRANCH=$OPENVDM_BRANCH

DEFAULT_DATA_ROOT=$DATA_ROOT
DEFAULT_OPENVDM_SITEROOT=$OPENVDM_SITEROOT

DEFAULT_OPENVDM_USER=$OPENVDM_USER

DEFAULT_INSTALL_MAPPROXY=$INSTALL_MAPPROXY
DEFAULT_MAPPROXY_CACHE=$MAPPROXY_CACHE

DEFAULT_INSTALL_PUBLICDATA=$INSTALL_PUBLICDATA
DEFAULT_INSTALL_VISITORINFORMATION=$INSTALL_VISITORINFORMATION

DEFAULT_INSTALL_TITILER=$INSTALL_TITILER
DEFAULT_TITILER_PORT=$TITILER_PORT

DEFAULT_INSTALL_SAMPLEDATA=$INSTALL_SAMPLEDATA
DEFAULT_SAMPLEDATA_ROOT=$SAMPLEDATA_ROOT
DEFAULT_SAMPLEDATA_REPO=$SAMPLEDATA_REPO
DEFAULT_SAMPLEDATA_BRANCH=$SAMPLEDATA_BRANCH

DEFAULT_SUPERVISORD_WEBINTERFACE=$SUPERVISORD_WEBINTERFACE
DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH=$SUPERVISORD_WEBINTERFACE_AUTH
EOF
}

###########################################################################
###########################################################################
# Set hostname
function set_hostname {
    HOSTNAME=$1

    hostnamectl set-hostname "$HOSTNAME"

    if [ "$OS_FAMILY" = "debian" ]; then
        echo "$HOSTNAME" > /etc/hostname
        ETC_HOSTS_LINE="127.0.1.1 $HOSTNAME"
    else
        ETC_HOSTS_LINE="127.0.1.1 $HOSTNAME $HOSTNAME"
    fi

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
    if id -u $OPENVDM_USER > /dev/null 2>&1; then
        echo User exists, skipping
        return
    fi

    echo "Creating $OPENVDM_USER"
    if [ "$OS_FAMILY" = "debian" ]; then
        adduser --gecos "" $OPENVDM_USER
        usermod -a -G $SUDO_GROUP $OPENVDM_USER
    else
        adduser $OPENVDM_USER
        passwd $OPENVDM_USER
        usermod -a -G tty $OPENVDM_USER
        usermod -a -G $SUDO_GROUP $OPENVDM_USER
    fi
}

###########################################################################
###########################################################################
# Install and configure required packages
function install_packages {

    startingDir=${PWD}

    if [ "$OS_FAMILY" = "debian" ]; then
        _install_packages_debian
    else
        _install_packages_rhel
    fi

    # Install Composer (both families)
    cd ~
    curl -sS https://getcomposer.org/installer | php
    mv composer.phar /usr/local/bin/composer

    cd "${startingDir}"
}

###########################################################################
###########################################################################
# Debian/Ubuntu package installation
function _install_packages_debian {

    export NEEDRESTART_MODE=a

    apt-get update -qq
    apt-get install -q -y ca-certificates curl gnupg

    # Use the codename already parsed from /etc/os-release in detect_os()
    # rather than calling lsb_release, which is not installed on minimal Debian.
    CODENAME="${OS_CODENAME}"
    KEYRING_DIR="/etc/apt/keyrings"
    mkdir -p "$KEYRING_DIR"

    if [ "$OS_ID" = "ubuntu" ]; then
        # Ubuntu: software-properties-common provides add-apt-repository
        apt-get install -q -y software-properties-common

        # Ubuntu: use Ondrej's PPA from Launchpad via keyserver.ubuntu.com
        KEYRING_FILE="$KEYRING_DIR/ondrej-php.gpg"
        PHP_PPA_URL="http://ppa.launchpad.net/ondrej/php/ubuntu"
        APACHE_PPA_URL="http://ppa.launchpad.net/ondrej/apache2/ubuntu"
        PHP_PPA_LIST="/etc/apt/sources.list.d/ondrej-php.list"
        APACHE_PPA_LIST="/etc/apt/sources.list.d/ondrej-apache2.list"

        echo "Downloading and importing Ondrej PPA keys..."
        curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x4F4EA0AAE5267A6C" \
            | gpg --dearmor | tee "$KEYRING_FILE" > /dev/null
        curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x71DAEAAB4AD4CAB6" \
            | gpg --dearmor | tee -a "$KEYRING_FILE" > /dev/null

        echo "deb [signed-by=$KEYRING_FILE] $PHP_PPA_URL $CODENAME main" | \
            tee "$PHP_PPA_LIST"
        echo "deb [signed-by=$KEYRING_FILE] $APACHE_PPA_URL $CODENAME main" | \
            tee "$APACHE_PPA_LIST"

        # On Ubuntu 22.04 (jammy) the system Python is 3.10 — too old for
        # some required packages. Install Python 3.12 from the deadsnakes PPA.
        if [ "$CODENAME" = "jammy" ]; then
            add-apt-repository -y ppa:deadsnakes/ppa
        fi

    else
        # Debian: use packages.sury.org (no add-apt-repository needed)
        KEYRING_FILE="$KEYRING_DIR/sury-php.gpg"
        PHP_PPA_LIST="/etc/apt/sources.list.d/sury-php.list"
        APACHE_PPA_LIST="/etc/apt/sources.list.d/sury-apache2.list"

        echo "Downloading and importing Sury packages key..."
        curl -fsSL "https://packages.sury.org/php/apt.gpg" \
            | gpg --dearmor | tee "$KEYRING_FILE" > /dev/null

        echo "deb [signed-by=$KEYRING_FILE] https://packages.sury.org/php/ $CODENAME main" | \
            tee "$PHP_PPA_LIST"
        echo "deb [signed-by=$KEYRING_FILE] https://packages.sury.org/apache2/ $CODENAME main" | \
            tee "$APACHE_PPA_LIST"

        # Debian 12 (bookworm) ships Python 3.11 natively; no backports needed.
        # Debian 13+ (trixie and later) ship Python 3.12+ natively.
        if [ "$CODENAME" = "bookworm" ]; then
            BACKPORTS_LIST="/etc/apt/sources.list.d/bookworm-backports.list"
            if [ ! -f "$BACKPORTS_LIST" ]; then
                echo "Adding Debian bookworm-backports..."
                echo "deb http://deb.debian.org/debian bookworm-backports main" | \
                    tee "$BACKPORTS_LIST"
            fi
        fi
    fi

    # Install Node.js via nvm
    if [ ! -e "/usr/local/bin/npm" ]; then
        cd ~
        curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
        [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
        nvm install --lts
        NODE_VERSION=$(node -v)
        ln -sf "$HOME/.nvm/versions/node/$NODE_VERSION/bin/npm" /usr/local/bin/
        ln -sf "$HOME/.nvm/versions/node/$NODE_VERSION/bin/node" /usr/local/bin/
    fi

    # Run update without -qq so any repo errors (GPG, 404, etc.) are visible
    apt-get update

    # Ubuntu ships mysql-server/mysql-client; Debian ships mariadb-server/mariadb-client
    if [ "$OS_ID" = "ubuntu" ]; then
        MYSQL_PKGS="mysql-client mysql-server"
    else
        MYSQL_PKGS="mariadb-client mariadb-server"
    fi

    NEEDRESTART_MODE=a apt-get install -q -y \
        openssh-server apache2 \
        cifs-utils gdal-bin gearman-job-server git \
        libapache2-mod-php8.2 libapache2-mod-wsgi-py3 libgearman-dev \
        $MYSQL_PKGS \
        php8.2 php8.2-cli php8.2-curl php8.2-gearman php8.2-mysql php8.2-yaml php8.2-zip \
        python3 python3-dev python3-pip python3-venv \
        rclone rsync samba smbclient sshpass supervisor

    # Install newest available Python >= 3.12.
    # Try versioned packages from newest to oldest; fall back to system python3
    # if it is already >= 3.11 (e.g. trixie ships python3.13 as python3).
    _PYTHON_INSTALLED=false
    for _VER in 3.15 3.14 3.13 3.12 3.11; do
        if apt-cache show "python${_VER}" > /dev/null 2>&1; then
            _PKGS="python${_VER} python${_VER}-dev python${_VER}-venv"
            NEEDRESTART_MODE=a apt-get install -y $_PKGS
            if command -v "python${_VER}" > /dev/null 2>&1; then
                _PYTHON_INSTALLED=true
                break
            fi
        fi
    done

    if [ "$_PYTHON_INSTALLED" = "false" ]; then
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            echo "No versioned python3.11+ package found; system python3 is $(python3 --version)"
            NEEDRESTART_MODE=a apt-get install -q -y python3-dev python3-venv
        else
            echo "ERROR: Python >= 3.11 is required but no suitable version is available."
            exit_gracefully
            exit 1
        fi
    fi

    if [ "$INSTALL_MAPPROXY" = "yes" ]; then
        NEEDRESTART_MODE=a apt-get install -q -y \
            libgeos-dev libgdal-dev proj-bin \
            python3-pyproj gdal-bin libfreetype6-dev libjpeg-dev apache2-dev
    fi
}

###########################################################################
###########################################################################
# RHEL/Rocky/Alma package installation
function _install_packages_rhel {

    dnf install -y epel-release

    # Enable powertools (v8) or crb (v9+)
    if [ "$OS_VERSION_MAJOR" -ge 9 ]; then
        dnf config-manager --set-enabled crb
    else
        dnf config-manager --set-enabled powertools
    fi

    dnf -y update --nobest

    # Install Remi PHP 8.2 repository
    if [ "$OS_VERSION_MAJOR" -ge 9 ]; then
        dnf install -y "https://rpms.remirepo.net/enterprise/remi-release-9.rpm"
    else
        dnf install -y "https://rpms.remirepo.net/enterprise/remi-release-8.rpm"
    fi
    dnf module reset php -y
    dnf module enable php:remi-8.2 -y
    dnf install -y php php-cli php-common php-gearman php-mysqlnd php-yaml php-zip

    # On RHEL 9+, MySQL is delivered as an AppStream module; enable it before install.
    if [ "$OS_VERSION_MAJOR" -ge 9 ]; then
        dnf module reset mysql -y
        dnf module enable mysql:8.0 -y
    fi

    # Install newest available Python >= 3.11.
    # Try versioned packages from newest to oldest.
    _PYTHON_INSTALLED=false
    for _VER in 3.15 3.14 3.13 3.12 3.11; do
        if dnf info "python${_VER}" > /dev/null 2>&1; then
            dnf install -y "python${_VER}" "python${_VER}-devel"
            _PYTHON_INSTALLED=true
            break
        fi
    done

    if [ "$_PYTHON_INSTALLED" = "false" ]; then
        if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            echo "No versioned python3.11+ package found; system python3 is $(python3 --version)"
            python3 -m pip install --upgrade pip --quiet
        else
            echo "ERROR: Python >= 3.11 is required but no suitable version is available."
            exit_gracefully
        fi
    fi

    # Core packages
    dnf -y install \
        cifs-utils curl gcc gcc-c++ gdal gearmand git httpd httpd-devel \
        gdal-devel libgearman-devel geos-devel libjpeg-devel make redhat-rpm-config \
        mysql-server nodejs npm \
        openssh-server policycoreutils-python-utils proj proj-devel \
        python3-pyproj \
        rsync samba samba-client samba-common samba-common-tools \
        setroubleshoot sshpass supervisor unzip zlib-devel

    # rclone is not in RHEL/AlmaLinux repos — install from official script
    if ! command -v rclone > /dev/null 2>&1; then
        curl -fsSL https://rclone.org/install.sh | bash
    fi

}

###########################################################################
###########################################################################
# Set up Python packages
function install_python_packages {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT - path where openvdm is

    startingDir=${PWD}

    cd $INSTALL_ROOT/openvdm

    ${PYTHON_CMD} -m venv ./venv
    source ./venv/bin/activate  # activate virtual environment

    pip install --trusted-host pypi.org \
        --trusted-host files.pythonhosted.org --upgrade pip --quiet
    pip install wheel --quiet

    pip install -r requirements.txt --quiet

    if [ "$INSTALL_MAPPROXY" = "yes" ]; then
        pip install geographiclib==1.52 geopy==2.2.0 --quiet
        _GDAL_VER=$(gdal-config --version)
        _GDAL_MAJOR=$(echo "$_GDAL_VER" | cut -d. -f1)
        _GDAL_MINOR=$(echo "$_GDAL_VER" | cut -d. -f2)
        if [ "$_GDAL_MAJOR" -gt 3 ] || { [ "$_GDAL_MAJOR" -eq 3 ] && [ "$_GDAL_MINOR" -ge 3 ]; }; then
            pip install --config-settings="--global-option=build_ext" \
                        --config-settings="--global-option=-I/usr/include/gdal" \
                        GDAL=="${_GDAL_VER}" \
                        --quiet
        else
            echo "WARNING: System GDAL ${_GDAL_VER} < 3.3; Python GDAL bindings skipped (incompatible with modern setuptools). The geotiff_parser plugin will not be functional."
        fi
    fi

    deactivate

    chown -R ${OPENVDM_USER}:${OPENVDM_USER} ${INSTALL_ROOT}/openvdm/venv

    cd $startingDir
}

###########################################################################
###########################################################################
# Detect the best installed Python >= 3.11 and set PYTHON_CMD / PYTHON_VERSION.
# Must be called after install_packages so the packages are already present.
function detect_python {

    for _ver in 3.15 3.14 3.13 3.12 3.11; do
        if command -v "python${_ver}" > /dev/null 2>&1; then
            PYTHON_CMD="python${_ver}"
            PYTHON_VERSION="${_ver}"
            echo "Using Python ${_ver} (${PYTHON_CMD})"
            return 0
        fi
    done

    # Fall back to the system python3 if it is already >= 3.11
    if command -v python3 > /dev/null 2>&1 && \
       python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PYTHON_CMD="python3"
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        echo "Using system Python ${PYTHON_VERSION} (python3)"
        return 0
    fi

    echo "ERROR: Python >= 3.11 is required but no suitable version was found."
    exit_gracefully
    exit 1
}

###########################################################################
###########################################################################
# Install and configure supervisor
function configure_supervisor {

    VENV_BIN=${INSTALL_ROOT}/openvdm/venv/bin

    # Backup and strip any previous OpenVDM supervisor config
    if [ -e "${SUPERVISOR_CONF}" ]; then
        cp "${SUPERVISOR_CONF}" "${SUPERVISOR_CONF}.orig"
        sed -e '/### Added by OpenVDM install script ###/,/### Added by OpenVDM install script ###/d' \
            "${SUPERVISOR_CONF}.orig" |
        sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' > "${SUPERVISOR_CONF}"
    fi

    if [ "$SUPERVISORD_WEBINTERFACE" = "yes" ]; then
        cat >> "${SUPERVISOR_CONF}" <<EOF

### Added by OpenVDM install script ###
[inet_http_server]
port=9001
EOF
        if [ "$SUPERVISORD_WEBINTERFACE_AUTH" = "yes" ]; then
            SUPERVISORD_WEBINTERFACE_HASH=$(echo -n "${SUPERVISORD_WEBINTERFACE_PASS}" | sha1sum | awk '{printf("{SHA}%s",$1)}')
            cat >> "${SUPERVISOR_CONF}" <<EOF
username=${SUPERVISORD_WEBINTERFACE_USER}
password=${SUPERVISORD_WEBINTERFACE_HASH} ; echo -n "<password>" | sha1sum | awk '{printf("{SHA}%s",\$1)}'
EOF
        fi

        cat >> "${SUPERVISOR_CONF}" <<EOF
### Added by OpenVDM install script ###
EOF
    fi

    cat > "${SUPERVISOR_CONF_D}/openvdm.${SUPERVISOR_PROG_EXT}" << EOF
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

    # On RHEL, open firewall port for supervisor web interface if enabled
    if [ "$OS_FAMILY" = "rhel" ] && [ "$SUPERVISORD_WEBINTERFACE" = "yes" ]; then
        echo "Updating Firewall rules for Supervisor Web Server"
        firewall_cmd_if_available --zone=public --add-port=9001/tcp --permanent
    fi

    echo "Starting new supervisor processes"
    systemctl restart "${SUPERVISOR_SERVICE}"
    systemctl enable "${SUPERVISOR_SERVICE}"
    supervisorctl reread
    supervisorctl update
}

###########################################################################
###########################################################################
# Install and configure gearman
function configure_gearman {
    echo "Starting Gearman Job Server"
    systemctl start "${GEARMAN_SERVICE}"
    systemctl enable "${GEARMAN_SERVICE}"
}

###########################################################################
###########################################################################
# Install and configure samba
function configure_samba {

    echo "Creating SMB user: ${OPENVDM_USER}, password set to same as OpenVDM DB user"
    (echo "${OPENVDM_DATABASE_PASSWORD}"; echo "${OPENVDM_DATABASE_PASSWORD}") | smbpasswd -s -a "${OPENVDM_USER}"

    if [ -e /etc/samba/smb.conf ]; then
        mv /etc/samba/smb.conf /etc/samba/smb.conf.orig

        sed -e 's/obey pam restrictions = yes/obey pam restrictions = no/' /etc/samba/smb.conf.orig |
        sed -e '/### Added by OpenVDM install script ###/,/### Added by OpenVDM install script ###/d' |
        sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' > /etc/samba/smb.conf
    fi

    cat >> /etc/samba/smb.conf <<EOF

### Added by OpenVDM install script ###
include = /etc/samba/openvdm.conf
### Added by OpenVDM install script ###
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

    if [ "$INSTALL_VISITORINFORMATION" = "yes" ]; then
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

    if [ "$INSTALL_PUBLICDATA" = "yes" ]; then
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

    if [ "$OS_FAMILY" = "rhel" ]; then
        echo "Updating firewall rules for samba"
        firewall_cmd_if_available --add-service=samba --zone=public --permanent
    fi

    echo "Restarting Samba Service"
    for svc in $SAMBA_SERVICES; do
        systemctl start "${svc}"
        systemctl enable "${svc}"
    done
}

###########################################################################
###########################################################################
# Setup Apache
function configure_apache {

    echo "Building new vhost file"
    VHOST_FILE="${APACHE_CONF_DIR}/openvdm.conf"

    cat > "${VHOST_FILE}" <<EOF
<VirtualHost *:80>
    ServerName $HOSTNAME

    ServerAdmin webmaster@localhost
    DocumentRoot /var/www/openvdm

    ErrorLog ${APACHE_LOG_DIR}/openvdm_error.log
    CustomLog ${APACHE_LOG_DIR}/openvdm_requests.log combined

    <Directory "/var/www/openvdm">
      AllowOverride all
    </Directory>
EOF

    if [ "$INSTALL_MAPPROXY" = "yes" ]; then
        # On RHEL, venv site-packages may be in lib64/ rather than lib/.
        # Compute the path now using PYTHON_CMD so it can be written directly
        # into the WSGIDaemonProcess directive without a post-hoc sed fixup.
        _WSGI_PYTHON_HOME="python-home=/opt/mapproxy"
        if [ "$OS_FAMILY" = "rhel" ]; then
            _MP_PYTHON_VER=$("${PYTHON_CMD}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            if "${PYTHON_CMD}" -c "import sysconfig; print(sysconfig.get_path('purelib'))" | grep -q lib64; then
                _MP_VENV_SITE="/opt/mapproxy/lib64/python${_MP_PYTHON_VER}/site-packages"
            else
                _MP_VENV_SITE="/opt/mapproxy/lib/python${_MP_PYTHON_VER}/site-packages"
            fi
            _WSGI_PYTHON_HOME="python-home=/opt/mapproxy python-path=${_MP_VENV_SITE}"
        fi
        cat >> "${VHOST_FILE}" <<EOF

    WSGIDaemonProcess mapproxy user=${APACHE_USER} group=${APACHE_USER} ${_WSGI_PYTHON_HOME} threads=5
    WSGIProcessGroup mapproxy
    WSGIApplicationGroup %{GLOBAL}
    WSGIScriptAlias /mapproxy /opt/mapproxy/config/mapproxy.wsgi

    <Directory /opt/mapproxy/config>
      Require all granted
    </Directory>
EOF
    fi

    cat >> "${VHOST_FILE}" <<EOF

    Alias /CruiseData/ $DATA_ROOT/CruiseData/
    <Directory "$DATA_ROOT/CruiseData">
      AllowOverride None
      Options +Indexes -FollowSymLinks +MultiViews
      Order allow,deny
      Allow from all
      Require all granted
    </Directory>
EOF

    if [ "$INSTALL_PUBLICDATA" = "yes" ]; then
        cat >> "${VHOST_FILE}" <<EOF

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

    if [ "$INSTALL_VISITORINFORMATION" = "yes" ]; then
        cat >> "${VHOST_FILE}" <<EOF

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

    if [ "$INSTALL_TITILER" = "yes" ]; then
        cat >> "${VHOST_FILE}" <<EOF

    ProxyPreserveHost On
    ProxyPass /titiler/ http://127.0.0.1:${TITILER_PORT}/
    ProxyPassReverse /titiler/ http://127.0.0.1:${TITILER_PORT}/
EOF
    fi

    cat >> "${VHOST_FILE}" <<EOF

</VirtualHost>
EOF

    if [ "$OS_FAMILY" = "debian" ]; then
        echo "Enabling rewrite Module"
        a2enmod -q rewrite

        if [ "$INSTALL_TITILER" = "yes" ]; then
            echo "Enabling proxy modules for TiTiler"
            a2enmod -q proxy proxy_http
        fi

        echo "Disabling default vhost"
        a2dissite -q 000-default

        echo "Enabling new vhost"
        a2ensite -q openvdm
    else
        # RHEL: open firewall ports and configure SELinux
        echo "Updating Firewall rules for Apache Web Server"
        firewall_cmd_if_available --permanent --add-service={http,https}

        echo "Setting SELinux exception rules"
        chcon -R -t httpd_sys_content_t ${DATA_ROOT}
        chcon -R -t httpd_sys_rw_content_t /var/www/openvdm/errorlog.html

        setsebool httpd_tmp_exec on
        setsebool -P httpd_can_network_connect=1
    fi

    # Enable Apache so it starts on boot. Only start/restart it now if MapProxy
    # is not being installed — if it is, mod_wsgi and /opt/mapproxy won't exist
    # yet and Apache would fail to parse the WSGIDaemonProcess directive.
    # configure_mapproxy will do the final restart once everything is in place.
    systemctl enable "${APACHE_SERVICE}"
    if [ "$INSTALL_MAPPROXY" != "yes" ]; then
        echo "Starting Apache Web Server"
        systemctl restart "${APACHE_SERVICE}"
    fi
}

###########################################################################
###########################################################################
# Install and configure MapProxy
function configure_mapproxy {

    if [ "$INSTALL_MAPPROXY" = "yes" ] && [ ! -e "${INSTALL_ROOT}/mapproxy/config/mapproxy.yaml" ]; then

        startingDir=${PWD}

        # On Debian, use system python3 so the venv matches libapache2-mod-wsgi-py3.
        # On RHEL, system python3 may be too old for MapProxy 6.x (requires 3.9+),
        # so use ${PYTHON_CMD} (3.11+) and pip-compile mod_wsgi to match.
        if [ "$OS_FAMILY" = "debian" ]; then
            python3 -m venv --clear /opt/mapproxy
        else
            ${PYTHON_CMD} -m venv --clear /opt/mapproxy
        fi
        source /opt/mapproxy/bin/activate
        pip install --upgrade pip --quiet
        _GDAL_VER=$(gdal-config --version)
        _GDAL_MAJOR=$(echo "$_GDAL_VER" | cut -d. -f1)
        _GDAL_MINOR=$(echo "$_GDAL_VER" | cut -d. -f2)
        if [ "$_GDAL_MAJOR" -gt 3 ] || { [ "$_GDAL_MAJOR" -eq 3 ] && [ "$_GDAL_MINOR" -ge 3 ]; }; then
            pip install gdal==${_GDAL_VER}
        else
            echo "WARNING: System GDAL ${_GDAL_VER} < 3.3; Python GDAL bindings skipped for MapProxy venv."
        fi
        pip install MapProxy

        # Create a starter config
        mapproxy-util create -t base-config /opt/mapproxy/config

        cat > /opt/mapproxy/config/mapproxy.yaml <<EOF
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
    url: https://server.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/%(z)s/%(y)s/%(x)s.png
    grid: esri_online

  esri_worldOceanReference:
    type: tile
    transparent: true
    url: https://server.arcgisonline.com/arcgis/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/%(z)s/%(y)s/%(x)s.png
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
  cache:
    base_dir: ${MAPPROXY_CACHE}
    lock_dir: ${MAPPROXY_CACHE}/locks
EOF

        mkdir -p "${MAPPROXY_CACHE}/locks"
        chown -R "${APACHE_USER}:${APACHE_USER}" "${MAPPROXY_CACHE}"
        chmod -R 755 /opt/mapproxy/config

        mkdir -p /var/log/mapproxy
        chown "${APACHE_USER}:${APACHE_USER}" /var/log/mapproxy

        mapproxy-util create -t wsgi-app -f /opt/mapproxy/config/mapproxy.yaml /opt/mapproxy/config/mapproxy.wsgi
        mapproxy-util create -t log-ini /opt/mapproxy/config/log.ini
        sed -i -e "s|# from logging.config import fileConfig|from logging.config import fileConfig|" /opt/mapproxy/config/mapproxy.wsgi
        sed -i -e "s|# import os.path|import os.path|" /opt/mapproxy/config/mapproxy.wsgi
        sed -i -e "s|# fileConfig(r'/opt/mapproxy/config/log.ini', {'here': os.path.dirname(__file__)})|fileConfig(r'/opt/mapproxy/config/log.ini', {'here': '/var/log/mapproxy'})|" /opt/mapproxy/config/mapproxy.wsgi

        if [ "$OS_FAMILY" = "debian" ]; then
            # Use the system mod_wsgi package (libapache2-mod-wsgi-py3), which is
            # compiled for the same system python3 used by the venv above.
            a2enmod wsgi-py3
        else
            # RHEL: pip-compile mod_wsgi for the same Python used by the venv,
            # then load it as an Apache module.
            pip install mod_wsgi --quiet
            _MODWSGI_SO=$(/opt/mapproxy/bin/mod_wsgi-express module-location)
            echo "LoadModule wsgi_module ${_MODWSGI_SO}" > /etc/httpd/conf.modules.d/10-wsgi-openvdm.conf
        fi

        if [ "$OS_FAMILY" = "rhel" ]; then
            chcon -R system_u:object_r:httpd_sys_script_exec_t:s0 /opt/mapproxy
            chcon -R -t httpd_sys_rw_content_t "${MAPPROXY_CACHE}" 2>/dev/null || true
        fi

        systemctl restart "${APACHE_SERVICE}"
        deactivate

        cd "${startingDir}"
    fi
}

###########################################################################
###########################################################################
# Install and configure TiTiler
function configure_titiler {

    if [ "$INSTALL_TITILER" != "yes" ]; then
        return
    fi

    echo "Installing TiTiler in /opt/titiler"

    ${PYTHON_CMD} -m venv /opt/titiler
    source /opt/titiler/bin/activate
    pip install --upgrade pip --quiet
    pip install "titiler.application" "uvicorn[standard]" --quiet
    deactivate

    # Middleware wrapper that sets root_path and app_root_path on every
    # request so all URL generation inside TiTiler (url_for, base_url,
    # OpenAPI servers) includes the /titiler prefix. Apache strips the
    # /titiler prefix before forwarding, so TiTiler sees plain paths.
    cat > /opt/titiler/wrapper.py << 'PYEOF'
from titiler.application.main import app as titiler_app


class RootPathMiddleware:
    def __init__(self, app, root_path):
        self.app = app
        self.root_path = root_path

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope["root_path"] = self.root_path
            scope["app_root_path"] = self.root_path
        await self.app(scope, receive, send)


app = RootPathMiddleware(titiler_app, "/titiler")
PYEOF

    mkdir -p /var/log/titiler

    cat > "${SUPERVISOR_CONF_D}/titiler.${SUPERVISOR_PROG_EXT}" << EOF
[program:titiler]
command=/opt/titiler/bin/uvicorn wrapper:app --host 127.0.0.1 --port ${TITILER_PORT}
directory=/opt/titiler
redirect_stderr=true
stdout_logfile=/var/log/titiler/titiler.log
user=${OPENVDM_USER}
autostart=true
autorestart=true
stopsignal=INT
EOF

    if [ "$OS_FAMILY" = "rhel" ]; then
        echo "Setting SELinux exception for TiTiler"
        chcon -R -t httpd_sys_content_t /opt/titiler 2>/dev/null || true
        setsebool -P httpd_can_network_connect=1
    fi

    supervisorctl reread
    supervisorctl update

    echo "TiTiler installed and running on port ${TITILER_PORT}"
    echo "Accessible via Apache at http://${OPENVDM_SITEROOT}/titiler/"
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

    systemctl enable "${MYSQL_SERVICE}"
    systemctl start "${MYSQL_SERVICE}"

    # MySQL 8.4+ removed mysql_native_password as a default auth plugin.
    # Re-enable it so PHP drivers and existing SQL statements work on 8.4+.
    # MariaDB (Debian) already uses native password by default — skip this block.
    if [ "$MYSQL_SERVICE" = "mysql" ] || [ "$MYSQL_SERVICE" = "mysqld" ]; then
        MYSQL_MAJOR_MINOR=$(mysql --version | grep -oP '\d+\.\d+' | head -1)
        MYSQL_MAJOR=$(echo $MYSQL_MAJOR_MINOR | cut -d. -f1)
        MYSQL_MINOR=$(echo $MYSQL_MAJOR_MINOR | cut -d. -f2)
        if [ "$MYSQL_MAJOR" -gt 8 ] || { [ "$MYSQL_MAJOR" -eq 8 ] && [ "$MYSQL_MINOR" -ge 4 ]; }; then
            echo "MySQL 8.4+ detected: enabling mysql_native_password plugin"
            if [ "$OS_FAMILY" = "debian" ]; then
                MYSQLD_CONF="/etc/mysql/mysql.conf.d/mysqld.cnf"
            else
                MYSQLD_CONF="/etc/my.cnf"
            fi
            if ! grep -q "^mysql_native_password" "$MYSQLD_CONF"; then
                echo "mysql_native_password=ON" >> "$MYSQLD_CONF"
            fi
            systemctl restart "${MYSQL_SERVICE}"
        fi
    fi

    # MariaDB uses simpler IDENTIFIED BY syntax; MySQL needs explicit plugin name
    if [ "$MYSQL_SERVICE" = "mariadb" ]; then
        MYSQL_AUTH_CLAUSE="IDENTIFIED BY"
    else
        MYSQL_AUTH_CLAUSE="IDENTIFIED WITH mysql_native_password BY"
    fi

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
ALTER USER 'root'@'localhost' $MYSQL_AUTH_CLAUSE '$NEW_ROOT_DATABASE_PASSWORD';
FLUSH PRIVILEGES;
EOF

    # If there's a current root password
    [ -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root -p$CURRENT_ROOT_DATABASE_PASSWORD 2> /dev/null < /tmp/set_pwd

    # If there's no current root password
    [ ! -z $CURRENT_ROOT_DATABASE_PASSWORD ] || mysql -u root < /tmp/set_pwd
    rm -f /tmp/set_pwd

    if [ "$OS_FAMILY" = "debian" ]; then
        # Ensure mysql starts on boot via update-rc.d
        update-rc.d ${MYSQL_SERVICE} defaults
    fi

    echo "Setting up OpenVDM database user: ${OPENVDM_USER}"
    mysql -u root -p$NEW_ROOT_DATABASE_PASSWORD 2> /dev/null <<EOF
drop user if exists '$OPENVDM_USER'@'localhost';
create user '$OPENVDM_USER'@'localhost' $MYSQL_AUTH_CLAUSE '$OPENVDM_DATABASE_PASSWORD';
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

        mkdir -p ${DATA_ROOT}/CruiseData

        if [ "$INSTALL_PUBLICDATA" = "yes" ]; then
            mkdir -p ${DATA_ROOT}/PublicData
            chmod -R 777 ${DATA_ROOT}/PublicData
        fi

        if [ "$INSTALL_VISITORINFORMATION" = "yes" ]; then
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
    if [ "$OS_FAMILY" = "debian" ]; then
        echo "Etc/UTC" > /etc/timezone
        dpkg-reconfigure --frontend noninteractive tzdata
    else
        timedatectl set-timezone UTC
    fi
}

###########################################################################
###########################################################################
# Set system ssh
function setup_ssh {

    # Generate SSH keypair for root if missing
    if [ ! -d ~/.ssh ] || [ ! -e ~/.ssh/id_rsa.pub ]; then
        mkdir -p ~/.ssh
        chmod 700 ~/.ssh
        ssh-keygen -q -N "" -t rsa -f ~/.ssh/id_rsa
        chmod 600 ~/.ssh/id_rsa ~/.ssh/id_rsa.pub
    fi

    # Authorize root's key for passwordless login as root
    if ! grep -qF "$(cat ~/.ssh/id_rsa.pub)" ~/.ssh/authorized_keys 2>/dev/null; then
        cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
        chmod 600 ~/.ssh/authorized_keys
    fi

    # Authorize root's key for passwordless login as OPENVDM_USER
    if ! grep -qF "$(cat ~/.ssh/id_rsa.pub)" "/home/${OPENVDM_USER}/.ssh/authorized_keys" 2>/dev/null; then
        mkdir -p "/home/${OPENVDM_USER}/.ssh"
        chmod 700 "/home/${OPENVDM_USER}/.ssh"
        cat ~/.ssh/id_rsa.pub >> "/home/${OPENVDM_USER}/.ssh/authorized_keys"
        chmod 600 "/home/${OPENVDM_USER}/.ssh/authorized_keys"
        chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "/home/${OPENVDM_USER}/.ssh"
    fi

    # Pre-accept host key to allow passwordless SSH to OPENVDM_USER@HOSTNAME
    ssh -o StrictHostKeyChecking=accept-new "${OPENVDM_USER}@${HOSTNAME}" ls > /dev/null
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
        git clone -q -b $OPENVDM_BRANCH $OPENVDM_REPO ./openvdm
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
            git clone -q -b $OPENVDM_BRANCH $OPENVDM_REPO ./openvdm
            chown -R ${OPENVDM_USER}:${OPENVDM_USER} ./openvdm
        fi
    fi

    cd ${INSTALL_ROOT}/openvdm

    if mysql --user=root --password=${NEW_ROOT_DATABASE_PASSWORD} -e 'use openvdm' 2> /dev/null; then
        echo "OpenVDM database found, skipping database setup"
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

        if [ "$INSTALL_PUBLICDATA" = "no" ]; then
            sed -i -e "/Public Data/d" ${INSTALL_ROOT}/openvdm/database/openvdm_db_custom.sql
        fi

        if [ "$INSTALL_VISITORINFORMATION" = "no" ]; then
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
    chown -R ${OPENVDM_USER}:${OPENVDM_USER} ${INSTALL_ROOT}/openvdm/www

    echo "Installing web-app"

    if [ ! -e /var/www/openvdm ]; then
        ln -s ${INSTALL_ROOT}/openvdm/www /var/www/openvdm
    fi

    if [ ! -e ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml ] ; then
        echo "Building server configuration file"
        sed -e "s/127.0.0.1/${HOSTNAME}/" ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml.dist > ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml

        if [ "$INSTALL_PUBLICDATA" = "no" ]; then
            sed -i -e "s/transferPublicData: True/transferPublicData: False/" ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml
        fi

        chown -R ${OPENVDM_USER}:${OPENVDM_USER} ${INSTALL_ROOT}/openvdm/server/etc/openvdm.yaml
    fi

    cd ${startingDir}
}


###########################################################################
###########################################################################
# Install sample data from the openvdm_sample_data repository
function install_sample_data {
    # Expect the following shell variables to be appropriately set:
    # INSTALL_ROOT          - root directory where openvdm is installed
    # OPENVDM_USER          - valid userid
    # OPENVDM_DATABASE_PASSWORD - OpenVDM DB/SMB password (reused for sample SMB shares)
    # NEW_ROOT_DATABASE_PASSWORD - MySQL root password
    # SAMPLEDATA_ROOT       - where sample data files will be extracted
    # SAMPLEDATA_REPO       - git repository URL for openvdm_sample_data
    # SAMPLEDATA_BRANCH     - branch to clone/checkout

    local startingDir="${PWD}"
    local SAMPLEDATA_INSTALL_DIR="${INSTALL_ROOT}/openvdm_sample_data"

    echo "Installing OpenVDM Sample Data"

    # Clone or update the openvdm_sample_data repository
    if [ ! -d "${SAMPLEDATA_INSTALL_DIR}" ]; then
        echo "Cloning OpenVDM Sample Data repository"
        cd "${INSTALL_ROOT}"
        git clone -q -b "${SAMPLEDATA_BRANCH}" "${SAMPLEDATA_REPO}" ./openvdm_sample_data
        chown -R "${OPENVDM_USER}:${OPENVDM_USER}" ./openvdm_sample_data
    else
        cd "${SAMPLEDATA_INSTALL_DIR}"
        if [ -e .git ]; then
            echo "Updating existing OpenVDM Sample Data repository"
            sudo -u "${OPENVDM_USER}" git pull
            sudo -u "${OPENVDM_USER}" git checkout "${SAMPLEDATA_BRANCH}"
            sudo -u "${OPENVDM_USER}" git pull
        else
            echo "Reinstalling OpenVDM Sample Data from repository"
            cd "${INSTALL_ROOT}"
            rm -rf openvdm_sample_data
            git clone -q -b "${SAMPLEDATA_BRANCH}" "${SAMPLEDATA_REPO}" ./openvdm_sample_data
            chown -R "${OPENVDM_USER}:${OPENVDM_USER}" ./openvdm_sample_data
        fi
    fi

    # Extract sample data files
    echo "Extracting sample data to ${SAMPLEDATA_ROOT}"
    mkdir -p "${SAMPLEDATA_ROOT}"
    tar xzf "${SAMPLEDATA_INSTALL_DIR}/sample_data.tgz" -C "${SAMPLEDATA_ROOT}" --warning=no-unknown-keyword

    chmod -R 777 "${SAMPLEDATA_ROOT}/anon_destination"
    chmod -R 777 "${SAMPLEDATA_ROOT}/anon_source"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/auth_destination"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/auth_source"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/local_destination"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/local_source"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/rsync_destination"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/rsync_source"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/ssdw"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/ssh_destination"
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${SAMPLEDATA_ROOT}/ssh_source"

    if [ "$HAS_SELINUX" = true ]; then
        chcon -R -t samba_share_t "${SAMPLEDATA_ROOT}" 2>/dev/null || true
    fi

    # Build customized SQL: substitute default paths/user/password with local values.
    # Strip DROP TABLE and CREATE TABLE blocks from the sample data SQL so that the
    # table schema installed by openvdm_db.sql is preserved; use TRUNCATE instead to
    # clear existing rows before inserting sample data.
    echo "Importing sample data database configuration"
    sed -e "s|/data/sample_data|${SAMPLEDATA_ROOT}|g" \
        "${SAMPLEDATA_INSTALL_DIR}/openvdm_sample_data.sql" | \
    sed -e "s/survey/${OPENVDM_USER}/g" | \
    sed -e "s/sample_smb_passwd/${OPENVDM_DATABASE_PASSWORD}/g" | \
    sed -e '/^DROP TABLE/d' \
        -e '/^CREATE TABLE/,/^) ENGINE=/d' \
        -e '/^\/\*!40101 SET @saved_cs_client/d' \
        -e '/^\/\*!5[0-9][0-9][0-9][0-9] SET character_set_client/d' \
        -e '/^\/\*!40101 SET character_set_client = @saved_cs_client/d' | \
    sed -e 's/^LOCK TABLES `\(.*\)` WRITE;/TRUNCATE TABLE `\1`;\nLOCK TABLES `\1` WRITE;/' \
    > /tmp/openvdm_sample_data_custom.sql

    mysql -u root -p"${NEW_ROOT_DATABASE_PASSWORD}" 2>/dev/null <<EOF
USE openvdm;
source /tmp/openvdm_sample_data_custom.sql;
flush privileges;
\q
EOF
    rm -f /tmp/openvdm_sample_data_custom.sql

    # Enable sample data plugins (copy .dist files only if active copy does not exist)
    echo "Enabling sample data plugins"
    local PLUGIN_DIR="${INSTALL_ROOT}/openvdm/server/plugins"
    for dist_file in \
        em302_plugin.py \
        openrvdas_plugin.py \
        rov_openrvdas_plugin.py; do
        if [ -e "${PLUGIN_DIR}/${dist_file}.dist" ] && [ ! -e "${PLUGIN_DIR}/${dist_file}" ]; then
            cp "${PLUGIN_DIR}/${dist_file}.dist" "${PLUGIN_DIR}/${dist_file}"
        fi
    done
    for dist_file in \
        geotiff_titiler_parser.py \
        gga_parser.py \
        met_parser.py \
        ssv_parser.py \
        tsg45_parser.py \
        twind_parser.py; do
        if [ -e "${PLUGIN_DIR}/parsers/${dist_file}.dist" ] && [ ! -e "${PLUGIN_DIR}/parsers/${dist_file}" ]; then
            cp "${PLUGIN_DIR}/parsers/${dist_file}.dist" "${PLUGIN_DIR}/parsers/${dist_file}"
        fi
    done
    chown -R "${OPENVDM_USER}:${OPENVDM_USER}" "${PLUGIN_DIR}"

    # Add Samba shares for sample data
    echo "Configuring Samba shares for sample data"
    sed -i '/### Added by openvdm_sample_data install script ###/,/### Added by openvdm_sample_data install script ###/d' \
        /etc/samba/openvdm.conf 2>/dev/null || true

    cat >> /etc/samba/openvdm.conf <<EOF

### Added by openvdm_sample_data install script ###
[SampleAuthSource]
  comment=Sample Data, read-only authenticated access
  path=${SAMPLEDATA_ROOT}/auth_source
  browsable = yes
  public = yes
  hide unreadable = yes
  guest ok = no
  writable = no

[SampleAnonSource]
  comment=Sample Data, read-only guest access
  path=${SAMPLEDATA_ROOT}/anon_source
  browsable = yes
  public = yes
  hide unreadable = yes
  guest ok = yes
  writable = no

[SampleAuthDestination]
  comment=Sample Destination, authenticated write access
  path=${SAMPLEDATA_ROOT}/auth_destination
  browsable = yes
  public = yes
  hide unreadable = yes
  guest ok = no
  writable = yes
  write list = ${OPENVDM_USER}
  create mask = 0644
  directory mask = 0755
  veto files = /._*/.DS_Store/.Trashes*/
  delete veto files = yes

[SampleAnonDestination]
  comment=Sample Destination, guest write access
  path=${SAMPLEDATA_ROOT}/anon_destination
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
### Added by openvdm_sample_data install script ###
EOF

    for svc in $SAMBA_SERVICES; do
        systemctl restart "${svc}"
    done

    # Configure rsync daemon for sample data
    echo "Configuring rsync daemon for sample data"
    sed -i '/### Added by openvdm_sample_data install script ###/,/### Added by openvdm_sample_data install script ###/d' \
        /etc/rsyncd.conf 2>/dev/null || true
    sed -i '/### Added by openvdm_sample_data install script ###/,/### Added by openvdm_sample_data install script ###/d' \
        /etc/rsyncd.passwd 2>/dev/null || true

    cat >> /etc/rsyncd.conf <<EOF

### Added by openvdm_sample_data install script ###
lock file = /var/run/rsync.lock
log file = /var/log/rsyncd.log
pid file = /var/run/rsyncd.pid

[sample_data]
    path = ${SAMPLEDATA_ROOT}/rsync_source
    uid = ${OPENVDM_USER}
    gid = ${OPENVDM_USER}
    read only = yes
    list = yes
    auth users = ${OPENVDM_USER}
    secrets file = /etc/rsyncd.passwd
    hosts allow = 127.0.0.1/255.255.255.0, localhost

[sample_dest]
    path = ${SAMPLEDATA_ROOT}/rsync_destination
    uid = ${OPENVDM_USER}
    gid = ${OPENVDM_USER}
    read only = no
    list = yes
    auth users = ${OPENVDM_USER}
    secrets file = /etc/rsyncd.passwd
    hosts allow = 127.0.0.1/255.255.255.0, localhost
### Added by openvdm_sample_data install script ###
EOF

    printf '### Added by openvdm_sample_data install script ###\n%s:b4dPassword!\n### Added by openvdm_sample_data install script ###\n' \
        "${OPENVDM_USER}" >> /etc/rsyncd.passwd
    chmod 600 /etc/rsyncd.passwd

    systemctl enable "${RSYNC_SERVICE}"
    systemctl restart "${RSYNC_SERVICE}"

    echo "Sample data installation complete"

    cd "${startingDir}"
}

###########################################################################
###########################################################################
# Start of actual script
###########################################################################

# Detect OS and set distro-specific variables
detect_os

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

###########################################################################
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
echo "Installation Directory: ${INSTALL_ROOT}"
echo

echo "#####################################################################"
read -p "IP Address or URL users will access OpenVDM from? ($DEFAULT_OPENVDM_SITEROOT) " OPENVDM_SITEROOT
OPENVDM_SITEROOT=${OPENVDM_SITEROOT:-$DEFAULT_OPENVDM_SITEROOT}
echo
echo "Access URL: 'http://$OPENVDM_SITEROOT'"
echo

###########################################################################
# Create user if they don't exist yet
echo "#####################################################################"
read -p "OpenVDM user to create? ($DEFAULT_OPENVDM_USER) " OPENVDM_USER
OPENVDM_USER=${OPENVDM_USER:-$DEFAULT_OPENVDM_USER}
create_user $OPENVDM_USER
echo

echo "#####################################################################"
echo "Gathering information for MySQL installation/configuration"
echo "Root database password will be empty on initial installation. If this"
echo "is the initial installation, hit \"return\" when prompted for root"
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
echo "single cruise worth of data but ideally should be large enough to"
echo "hold several cruises worth of data."
echo
echo "It is recommended that the root data directory be located on a"
echo "mounted volume that is independent of the volume used for the"
echo "operating system. This simplifies disaster recovery and system"
echo "updates"
echo
read -p "Root data directory for OpenVDM? ($DEFAULT_DATA_ROOT) " DATA_ROOT
DATA_ROOT=${DATA_ROOT:-$DEFAULT_DATA_ROOT}

if [ ! -d "$DATA_ROOT" ]; then
    yes_no "Root data directory ${DATA_ROOT} does not exist... create it? " "yes"

    if [ "$YES_NO_RESULT" = "no" ]; then
        exit_gracefully
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

if [ "$SUPERVISORD_WEBINTERFACE" = "yes" ]; then

    yes_no "Enable user/pass on Supervisor Web-interface? " $DEFAULT_SUPERVISORD_WEBINTERFACE_AUTH
    SUPERVISORD_WEBINTERFACE_AUTH=$YES_NO_RESULT

    if [ "$SUPERVISORD_WEBINTERFACE_AUTH" = "yes" ]; then

        read -p "Username? ($OPENVDM_USER) " SUPERVISORD_WEBINTERFACE_USER
        SUPERVISORD_WEBINTERFACE_USER=${SUPERVISORD_WEBINTERFACE_USER:-$OPENVDM_USER}

        read -p "Password? ($OPENVDM_USER) " SUPERVISORD_WEBINTERFACE_PASS
        SUPERVISORD_WEBINTERFACE_PASS=${SUPERVISORD_WEBINTERFACE_PASS:-$OPENVDM_USER}
    fi
else
  SUPERVISORD_WEBINTERFACE_AUTH=no
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

MAPPROXY_CACHE=${DEFAULT_MAPPROXY_CACHE:-}
if [ "$INSTALL_MAPPROXY" = "yes" ]; then

    echo "Where should the cached tiles be stored? It is recommended that the"
    echo "tile cache directory be located on a mounted volume that is"
    echo "independent of the volume used for the operating system."
    echo
    read -p "Cache data directory for MapProxy? ($DATA_ROOT/cache_data) " MAPPROXY_CACHE
    MAPPROXY_CACHE=${MAPPROXY_CACHE:-$DATA_ROOT/cache_data}

    if [ ! -d "$MAPPROXY_CACHE" ]; then
        yes_no "Cache data directory ${MAPPROXY_CACHE} does not exist... create it? " "yes"

        if [ "$YES_NO_RESULT" = "no" ]; then
            exit_gracefully
        fi
    fi
fi
echo

#########################################################################
# Install TiTiler?
echo "#####################################################################"
echo "Optionally install TiTiler, a dynamic tile server for Cloud Optimized"
echo "GeoTIFFs (COGs). TiTiler is required for the geotiff_titiler_parser"
echo "plugin used by the sample data configuration."
echo
yes_no "Install TiTiler? " $DEFAULT_INSTALL_TITILER
INSTALL_TITILER=$YES_NO_RESULT

if [ "$INSTALL_TITILER" = "yes" ]; then
    read -p "Port for TiTiler service? ($DEFAULT_TITILER_PORT) " TITILER_PORT
    TITILER_PORT=${TITILER_PORT:-$DEFAULT_TITILER_PORT}
else
    TITILER_PORT=${DEFAULT_TITILER_PORT}
fi
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
echo "Setup a VisitorInformation SMB Share for sharing documentation, print"
echo "drivers, etc with crew and scientists."
echo
yes_no "Setup VisitorInformation Share? " $DEFAULT_INSTALL_VISITORINFORMATION
INSTALL_VISITORINFORMATION=$YES_NO_RESULT
echo

#########################################################################
# Install sample data?
echo "#####################################################################"
echo "Optionally install sample data from the openvdm_sample_data repository."
echo "This configures demonstration collection systems, cruise data transfers,"
echo "and ship-to-shore transfers using local sample instrument data."
echo "WARNING: This will replace any existing transfer configuration in the"
echo "OpenVDM database."
echo
yes_no "Install sample data? " $DEFAULT_INSTALL_SAMPLEDATA
INSTALL_SAMPLEDATA=$YES_NO_RESULT

if [ "$INSTALL_SAMPLEDATA" = "yes" ]; then
    read -p "Root directory for sample data? ($DEFAULT_SAMPLEDATA_ROOT) " SAMPLEDATA_ROOT
    SAMPLEDATA_ROOT=${SAMPLEDATA_ROOT:-$DEFAULT_SAMPLEDATA_ROOT}

    read -p "Sample data repository? ($DEFAULT_SAMPLEDATA_REPO) " SAMPLEDATA_REPO
    SAMPLEDATA_REPO=${SAMPLEDATA_REPO:-$DEFAULT_SAMPLEDATA_REPO}

    read -p "Sample data branch? ($DEFAULT_SAMPLEDATA_BRANCH) " SAMPLEDATA_BRANCH
    SAMPLEDATA_BRANCH=${SAMPLEDATA_BRANCH:-$DEFAULT_SAMPLEDATA_BRANCH}
else
    SAMPLEDATA_ROOT=${DEFAULT_SAMPLEDATA_ROOT}
    SAMPLEDATA_REPO=${DEFAULT_SAMPLEDATA_REPO}
    SAMPLEDATA_BRANCH=${DEFAULT_SAMPLEDATA_BRANCH}
fi

if [ "$INSTALL_SAMPLEDATA" = "yes" ] && [ "$INSTALL_TITILER" != "yes" ]; then
    echo "Sample data requires TiTiler — enabling TiTiler install."
    INSTALL_TITILER=yes
fi
echo

#########################################################################
# Save defaults in a preferences file for the next time we run.
save_default_variables

#########################################################################
#########################################################################

echo "#####################################################################"
echo "Installing required software packages and libraries"
install_packages

echo "#####################################################################"
echo "Detecting Python version"
detect_python
echo

echo "#####################################################################"
echo "Setting system timezone to UTC"
setup_timezone
echo

echo "#####################################################################"
echo "Setting ssh public/private keys"
setup_ssh
echo

echo "#####################################################################"
echo "Creating required directories"
configure_directories
echo

echo "#####################################################################"
echo "Configuring Samba"
configure_samba
echo

echo "#####################################################################"
echo "Configuring Gearman Job Server"
configure_gearman
echo

echo "#####################################################################"
echo "Configuring MySQL"
configure_mysql
echo

echo "#####################################################################"
echo "Installing/Configuring OpenVDM"
install_openvdm
echo

echo "#####################################################################"
echo "Installing additional python libraries"
install_python_packages
echo

echo "#####################################################################"
echo "Configuring Apache"
configure_apache
echo

echo "#####################################################################"
echo "Installing/Configuring MapProxy"
configure_mapproxy
echo

echo "#####################################################################"
echo "Configuring Supervisor"
configure_supervisor
echo

echo "#####################################################################"
echo "Installing/Configuring TiTiler"
configure_titiler
echo

if [ "$INSTALL_SAMPLEDATA" = "yes" ]; then
    echo "#####################################################################"
    echo "Installing Sample Data"
    install_sample_data
    echo
fi

echo "#####################################################################"
echo "Running post-install OpenVDM tasks"
sleep 3

OVDM_CRUISE_ID=$(mysql -u root -p"${NEW_ROOT_DATABASE_PASSWORD}" openvdm -sNe \
    "SELECT value FROM OVDM_CoreVars WHERE name='cruiseID';" 2>/dev/null)
OVDM_CRUISE_START_DATE=$(mysql -u root -p"${NEW_ROOT_DATABASE_PASSWORD}" openvdm -sNe \
    "SELECT value FROM OVDM_CoreVars WHERE name='cruiseStartDate';" 2>/dev/null)
OVDM_CST_IDS=$(mysql -u root -p"${NEW_ROOT_DATABASE_PASSWORD}" openvdm -sNe \
    "SELECT collectionSystemTransferID FROM OVDM_CollectionSystemTransfers WHERE enable=1 AND cruiseOrLowering=0;" \
    2>/dev/null | tr '\n' ',')
OVDM_CRUISE_DIR="${DATA_ROOT}/CruiseData/${OVDM_CRUISE_ID}"

export OVDM_CRUISE_ID OVDM_CRUISE_START_DATE OVDM_CST_IDS OVDM_CRUISE_DIR INSTALL_SAMPLEDATA
"${INSTALL_ROOT}/openvdm/venv/bin/python3" - <<'PYEOF'
import os, sys, json

try:
    import python3_gearman
except ImportError as e:
    print(f'Warning: python3_gearman not available: {e}', file=sys.stderr)
    sys.exit(0)

cruise_id = os.environ.get('OVDM_CRUISE_ID', '')
cruise_start_date = os.environ.get('OVDM_CRUISE_START_DATE', '')
cst_ids = [x for x in os.environ.get('OVDM_CST_IDS', '').split(',') if x]
cruise_dir = os.environ.get('OVDM_CRUISE_DIR', '')
install_sampledata = os.environ.get('INSTALL_SAMPLEDATA', 'no') == 'yes'

gm = python3_gearman.GearmanClient(['localhost:4730'])

if not os.path.exists(cruise_dir):
    # Fresh install: setupNewCruise creates the directory, MD5 files,
    # cruise_config.json, and data dashboard manifest in one shot.
    print('  Setting up new cruise...')
    try:
        gm.submit_job('setupNewCruise', '{}', wait_until_complete=True, poll_timeout=120)
        print('  Setup new cruise: done')
    except Exception as e:
        print(f'  Warning: setupNewCruise failed: {e}', file=sys.stderr)
else:
    # Re-install: cruise directory already exists; just re-export config
    # and rebuild the directory structure.
    for label, task, timeout in [
        ('Re-export cruise configuration', 'exportOVDMConfig',      30),
        ('Rebuild cruise directory',        'rebuildCruiseDirectory', 120),
    ]:
        print(f'  {label}...')
        try:
            gm.submit_job(task, '{}', wait_until_complete=True, poll_timeout=timeout)
            print(f'  {label}: done')
        except Exception as e:
            print(f'  Warning: {label} failed: {e}', file=sys.stderr)

if install_sampledata and cst_ids:
    print(f'  Running {len(cst_ids)} collection system transfer(s)...')
    try:
        jobs = []
        for cst_id in cst_ids:
            payload = json.dumps({
                'cruiseID': cruise_id,
                'cruiseStartDate': cruise_start_date,
                'systemStatus': 'On',
                'collectionSystemTransfer': {'collectionSystemTransferID': cst_id}
            })
            jobs.append({'task': 'runCollectionSystemTransfer', 'data': payload})
        gm.submit_multiple_jobs(jobs, background=False, wait_until_complete=True, poll_timeout=600)
        print('  Collection system transfers: done')
    except Exception as e:
        print(f'  Warning: collection system transfers failed: {e}', file=sys.stderr)
PYEOF
echo

echo "#####################################################################"
echo "OpenVDM Installation: Complete"
echo "OpenVDM WebUI available at: http://${OPENVDM_SITEROOT}"
echo "Login with user: ${OPENVDM_USER}, pass: ${OPENVDM_DATABASE_PASSWORD}"
echo "Cruise Data will be stored at: ${DATA_ROOT}/CruiseData"
echo

#########################################################################
#########################################################################
