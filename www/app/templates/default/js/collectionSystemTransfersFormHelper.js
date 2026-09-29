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

    // Source Directory placeholder for each transfer type, keyed by type value (#227)
    var sourceDirPlaceholders = {
        1: 'e.g. /mnt/xbt',
        2: 'e.g. /EM302',
        3: 'e.g. /XBT',
        4: 'e.g. /data/openrvdas',
        5: 'e.g. /data'
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

    function normalizeSourceDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        // Strip Windows drive letter (e.g. C:/ → /)
        val = val.replace(/^[A-Za-z]:/, '');
        // Ensure leading slash
        if (val.length > 0 && !val.startsWith('/')) {
            val = '/' + val;
        }
        // Strip trailing slash unless the entire value is just "/"
        if (val.length > 1) {
            val = val.replace(/\/+$/, '');
        }
        return val;
    }

    function normalizeDestDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        // Strip leading and trailing slashes (dest dir is relative within cruise dir)
        val = val.replace(/^\/+/, '').replace(/\/+$/, '');
        return val;
    }

    // ---------------------------------------------------------------------------
    // Apply normalization based on the currently selected transfer type
    // ---------------------------------------------------------------------------

    function currentTransferType() {
        return $('select[name=transferType]').val() || '';
    }

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

        $('input[name=sourceDir]').val(normalizeSourceDir($('input[name=sourceDir]').val()));
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

        $('input[name=sourceDir]').attr('placeholder', sourceDirPlaceholders[transferType] || '');
    }

    function setCustomStalenessField(staleness) {
        if(staleness == "0"){
            $(".staleness").hide();
        } else {
            $(".staleness").show();
        }
    }

    function setCustomRemoveSourceField() {
        const staleness = $('input[name=staleness]:checked').val();
        const transferType = currentTransferType();

	if(staleness == 0 || transferType == 2){
            $(".removeSource").hide();
        } else {
            $(".removeSource").show();
        }
    }

    setTransferTypeFields(currentTransferType());
    setSSHUseKeyField($('input[name=sshUseKey]:checked').val())
    setCustomStalenessField($('input[name=staleness]:checked').val())
    setCustomRemoveSourceField()

    $('select[name=transferType]').change(function () {
        setTransferTypeFields(currentTransferType());
        setCustomRemoveSourceField()
    });

    $('input[name=sshUseKey]').change(function () {
        setSSHUseKeyField($(this).val());
    });

    $('input[name=staleness]').change(function () {
        setCustomStalenessField($(this).val());
        setCustomRemoveSourceField()
    })

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

    $('input[name=sourceDir]').on('blur', function () {
        $(this).val(normalizeSourceDir($(this).val()));
    });

    $('input[name=destDir]').on('blur', function () {
        $(this).val(normalizeDestDir($(this).val()));
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
