$(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // Field normalization helpers
    // ---------------------------------------------------------------------------

    function isRcloneDest(val) {
        return val.indexOf(':') !== -1;
    }

    function normalizeSshServer(val) {
        val = val.trim();
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

    function normalizeDestDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');

        if (isRcloneDest(val)) {
            // rclone remote:path — remote name must not have leading slashes
            val = val.replace(/^\/+/, '');
            return val;
        }

        // Regular SSH absolute path
        if (val.length > 0 && !val.startsWith('/')) {
            val = '/' + val;
        }
        if (val.length > 1) {
            val = val.replace(/\/+$/, '');
        }
        return val;
    }

    // ---------------------------------------------------------------------------
    // Existing UI helpers
    // ---------------------------------------------------------------------------

    function setSSHUseKeyField(sshUseKey) {
        if (isRcloneDest($('input[name=destDir]').val())) {
            return;
        }
        if(sshUseKey == 1){
            $('input[name=sshPass]').val("");
            $('input[name=sshPass]').prop('disabled', true);
        } else {
            $('input[name=sshPass]').prop('disabled', false);
        }
    }

    function setSshFieldsForDestDir(destDirVal) {
        if (isRcloneDest(destDirVal)) {
            $('input[name=sshServer]').prop('disabled', true);
            $('input[name=sshUser]').prop('disabled', true);
            $('input[name=sshPass]').prop('disabled', true);
            $('input[name=sshUseKey]').prop('disabled', true);
        } else {
            $('input[name=sshServer]').prop('disabled', false);
            $('input[name=sshUser]').prop('disabled', false);
            $('input[name=sshUseKey]').prop('disabled', false);
            setSSHUseKeyField($('input[name=sshUseKey]:checked').val());
        }
    }

    setSshFieldsForDestDir($('input[name=destDir]').val());

    $('input[name=sshUseKey]').change(function () {
        setSSHUseKeyField($(this).val());
    });

    // ---------------------------------------------------------------------------
    // Normalize on blur (immediate feedback) and on submit (safety net)
    // ---------------------------------------------------------------------------

    $('input[name=sshServer]').on('blur', function () {
        $(this).val(normalizeSshServer($(this).val()));
    });

    $('input[name=sshUser], input[name=sshPass]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=destDir]').on('blur', function () {
        var normalized = normalizeDestDir($(this).val());
        $(this).val(normalized);
        setSshFieldsForDestDir(normalized);
    });

    $('form').on('submit', function () {
        // Re-enable disabled fields so their values are included in the POST
        $('input').prop('disabled', false);
        $('input[type="text"], input[type="password"], input:not([type])').each(function () {
            $(this).val($(this).val().trim());
        });
        $('input[name=sshServer]').val(normalizeSshServer($('input[name=sshServer]').val()));
        $('input[name=destDir]').val(normalizeDestDir($('input[name=destDir]').val()));
    });

});
