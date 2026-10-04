$(function () {
    'use strict';

    // Class of each transfer type's form fields and help text, keyed by
    // transfer type ID (OVDM_TransferTypes.transferTypeID) (#226)
    var transferTypeFieldClasses = {
        1: 'localDir',
        2: 'rsyncServer',
        3: 'smbShare',
        4: 'sshServer',
        5: 'ftpServer'
    };

    // Destination Directory placeholder for each transfer type, keyed by type value (#227)
    var destDirPlaceholders = {
        1: 'e.g. /mnt/backup, or remote:path for an rclone remote',
        2: 'e.g. backups (/ for the top of the module)',
        3: 'e.g. backups (/ for the top of the share)',
        4: 'e.g. /data/cruises',
        5: 'e.g. /data/cruises'
    };

    // ---------------------------------------------------------------------------
    // Field normalization helpers
    // ---------------------------------------------------------------------------

    function normalizeSmbServer(val) {
        val = val.trim();
        // Replace all backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        // Ensure the value starts with // (Windows UNC \\server\share → //server/share)
        if (val.length > 0 && !val.startsWith('//')) {
            val = '//' + val.replace(/^\/+/, '');
        }
        // Strip trailing slashes
        val = val.replace(/\/+$/, '');
        return val;
    }

    function normalizeRsyncServer(val) {
        val = val.trim();
        // Strip protocol prefix
        val = val.replace(/^rsync:\/\//i, '');
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        // Strip leading and trailing slashes
        val = val.replace(/^\/+/, '').replace(/\/+$/, '');
        return val;
    }

    function normalizeSshServer(val) {
        val = val.trim();
        // Strip protocol prefix
        val = val.replace(/^ssh:\/\//i, '');
        // Replace backslashes with forward slashes, then strip leading slashes
        val = val.replace(/\\/g, '/').replace(/^\/+/, '');
        // SSH server field should be hostname/IP only — strip any path component
        var slashIdx = val.indexOf('/');
        if (slashIdx !== -1) {
            val = val.substring(0, slashIdx);
        }
        return val.trim();
    }

    function normalizeFtpServer(val) {
        val = val.trim();
        // Strip protocol prefix
        val = val.replace(/^ftp:\/\//i, '');
        // Replace backslashes with forward slashes, then strip leading slashes
        val = val.replace(/\\/g, '/').replace(/^\/+/, '');
        // FTP server field is host[:port] only — strip any path component
        var slashIdx = val.indexOf('/');
        if (slashIdx !== -1) {
            val = val.substring(0, slashIdx);
        }
        return val.trim();
    }

    function isRcloneDest(val) {
        return val.indexOf(':') !== -1;
    }

    function currentTransferType() {
        return $('select[name=transferType]').val() || '';
    }

    function normalizeDestDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        var transferType = currentTransferType();
        if (transferType === '') {
            // No type chosen yet: don't guess whether the path is absolute
            return val;
        }
        if (transferType === '1') { // Local Directory
            if (isRcloneDest(val)) {
                // rclone remote:path — remote name must not have leading slashes
                val = val.replace(/^\/+/, '');
                return val;
            }
            // Local absolute path — ensure leading slash, strip trailing slash
            if (val.length > 0 && !val.startsWith('/')) {
                val = '/' + val;
            }
            if (val.length > 1) {
                // "//" is still the root, not "" (#247)
                val = val.replace(/\/+$/, '') || '/';
            }
            return val;
        }
        if (transferType === '4' || transferType === '5') {
            // SSH and FTP dests are absolute paths on the remote server
            if (val.length > 0 && !val.startsWith('/')) {
                val = '/' + val;
            }
            if (val.length > 1) {
                // "//" is still the root, not "" (#247)
                val = val.replace(/\/+$/, '') || '/';
            }
            return val;
        }
        // Rsync and SMB: dest dir is relative to the rsync module or SMB share;
        // "/" is its top level, so it isn't stripped to "" (#247)
        var relative = val.replace(/^\/+/, '').replace(/\/+$/, '');
        return (relative === '' && val !== '') ? '/' : relative;
    }

    // ---------------------------------------------------------------------------
    // Apply normalization based on the currently selected transfer type
    // ---------------------------------------------------------------------------

    function normalizeFieldsForTransferType(transferType) {
        switch (transferType) {
        case '2': // Rsync Server
            $('input[name=rsyncServer]').val(normalizeRsyncServer($('input[name=rsyncServer]').val()));
            break;
        case '3': // SMB Share
            $('input[name=smbServer]').val(normalizeSmbServer($('input[name=smbServer]').val()));
            break;
        case '4': // SSH Server
            $('input[name=sshServer]').val(normalizeSshServer($('input[name=sshServer]').val()));
            break;
        case '5': // FTP Server
            $('input[name=ftpServer]').val(normalizeFtpServer($('input[name=ftpServer]').val()));
            break;
        }

        $('input[name=destDir]').val(normalizeDestDir($('input[name=destDir]').val()));
    }

    // ---------------------------------------------------------------------------
    // Existing UI helpers
    // ---------------------------------------------------------------------------

    function setSSHUseKeyField(sshUseKey) {
        if(sshUseKey == 1){
            $('input[name=sshPass]').val("");
            $('input[name=sshPass]').prop('disabled', true);
        } else {
            $('input[name=sshPass]').prop('disabled', false);
        }
    }

    function setTransferTypeFields(transferType) {
        // Show only the selected type's fields; none until a type is chosen
        $.each(transferTypeFieldClasses, function (id, fieldClass) {
            $('.' + fieldClass).toggle(id === transferType);
        });

        $('input[name=destDir]').attr('placeholder', destDirPlaceholders[transferType] || '');
    }

    function setMountpointFieldForDestDir(destDirVal) {
        if (currentTransferType() === '1' && !isRcloneDest(destDirVal)) {
            $('input[name=localDirIsMountPoint]').closest('.form-group').show();
        } else {
            $('input[name=localDirIsMountPoint]').closest('.form-group').hide();
        }
    }

    setTransferTypeFields(currentTransferType());
    setSSHUseKeyField($('input[name=sshUseKey]:checked').val())
    setMountpointFieldForDestDir($('input[name=destDir]').val());

    $('select[name=transferType]').change(function () {
        setTransferTypeFields(currentTransferType());
        setMountpointFieldForDestDir($('input[name=destDir]').val());
    });

    $('input[name=sshUseKey]').change(function () {
        setSSHUseKeyField($(this).val());
    });

    $('#selectAllCS').change(function() {
      var isChecked = $(this).prop('checked');
      $('#excludedCollectionSystems input[type="checkbox"]').prop('checked', isChecked);
    });

    $('#excludedCollectionSystems input[type="checkbox"]').change(function() {
      if ($('#excludedCollectionSystems input[type="checkbox"]:not(:checked)').length > 0) {
        $('#selectAllCS').prop('checked', false);
      } else {
        $('#selectAllCS').prop('checked', true);
      }
    });

    $('#selectAllED').change(function() {
      var isChecked = $(this).prop('checked');
      $('#excludedExtraDirectories input[type="checkbox"]').prop('checked', isChecked);
    });

    $('#excludedExtraDirectories input[type="checkbox"]').change(function() {
      if ($('#excludedExtraDirectories input[type="checkbox"]:not(:checked)').length > 0) {
        $('#selectAllED').prop('checked', false);
      } else {
        $('#selectAllED').prop('checked', true);
      }
    });

    // ---------------------------------------------------------------------------
    // Normalize on blur (immediate feedback) and on submit (safety net)
    // ---------------------------------------------------------------------------

    $('input[name=name], input[name=longName]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=rsyncServer]').on('blur', function () {
        $(this).val(normalizeRsyncServer($(this).val()));
    });

    $('input[name=rsyncUser], input[name=rsyncPass]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=smbServer]').on('blur', function () {
        $(this).val(normalizeSmbServer($(this).val()));
    });

    $('input[name=smbDomain], input[name=smbUser], input[name=smbPass]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=sshServer]').on('blur', function () {
        $(this).val(normalizeSshServer($(this).val()));
    });

    $('input[name=sshUser], input[name=sshPass]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=ftpServer]').on('blur', function () {
        $(this).val(normalizeFtpServer($(this).val()));
    });

    $('input[name=ftpUser], input[name=ftpPass]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=destDir]').on('blur', function () {
        var normalized = normalizeDestDir($(this).val());
        $(this).val(normalized);
        setMountpointFieldForDestDir(normalized);
    });

    $('form').on('keydown', 'input', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            $('input[name=inlineTest]').trigger('click');
        }
    });

    $('form').on('submit', function () {
        $('input[type="text"], input[type="password"], input:not([type])').each(function () {
            $(this).val($(this).val().trim());
        });
        normalizeFieldsForTransferType(currentTransferType());
    });

});
