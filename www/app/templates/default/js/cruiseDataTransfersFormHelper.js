$(function () {
    'use strict';

    var transferTypeOptions = [
        {"value" : 1, "text" : "Local Directory"},
        {"value" : 2, "text" : "Rsync Server"},
        {"value" : 3, "text" : "SMB Share"},
        {"value" : 4, "text" : "SSH Server"},
        {"value" : 5, "text" : "NFS Share"}
    ];

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

    function isRcloneDest(val) {
        return val.indexOf(':') !== -1;
    }

    function currentTransferTypeText() {
        var transferType = $('input[name=transferType]:checked').val() || '1';
        return transferTypeOptions[parseInt(transferType, 10) - 1].text;
    }

    function normalizeDestDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        if (currentTransferTypeText() === 'Local Directory') {
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
                val = val.replace(/\/+$/, '');
            }
            return val;
        }
        // All other transfer types: dest dir is relative within cruise dir
        val = val.replace(/^\/+/, '').replace(/\/+$/, '');
        return val;
    }

    // ---------------------------------------------------------------------------
    // Apply normalization based on the currently selected transfer type
    // ---------------------------------------------------------------------------

    function normalizeFieldsForTransferType(transferType) {
        if (transferType === '') { transferType = '1'; }

        var transferTypeText = transferTypeOptions[parseInt(transferType, 10) - 1].text;

        switch (transferTypeText) {
        case 'Rsync Server':
            $('input[name=rsyncServer]').val(normalizeRsyncServer($('input[name=rsyncServer]').val()));
            break;
        case 'SMB Share':
            $('input[name=smbServer]').val(normalizeSmbServer($('input[name=smbServer]').val()));
            break;
        case 'SSH Server':
            $('input[name=sshServer]').val(normalizeSshServer($('input[name=sshServer]').val()));
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

        if (transferType === '') { transferType = 1; }
        var transferTypeText = transferTypeOptions[parseInt(transferType, 10) - 1].text;

        switch (transferTypeText) {
        case "Local Directory":
            $(".localDir").show();
            $(".rsyncServer").hide();
            $(".smbShare").hide();
            $(".sshServer").hide();
            $(".nfsShare").hide();
            break;
        case "Rsync Server":
            $(".localDir").hide();
            $(".rsyncServer").show();
            $(".smbShare").hide();
            $(".sshServer").hide();
            $(".nfsShare").hide();
            break;
        case "SMB Share":
            $(".localDir").hide();
            $(".rsyncServer").hide();
            $(".smbShare").show();
            $(".sshServer").hide();
            $(".nfsShare").hide();
            break;
        case "SSH Server":
            $(".localDir").hide();
            $(".rsyncServer").hide();
            $(".smbShare").hide();
            $(".sshServer").show();
            $(".nfsShare").hide();
            break;
        case "NFS Share":
            $(".localDir").hide();
            $(".rsyncServer").hide();
            $(".smbShare").hide();
            $(".sshServer").hide();
            $(".nfsShare").show();
            break;
        default:
        }
    }

    function setMountpointFieldForDestDir(destDirVal) {
        if (currentTransferTypeText() === 'Local Directory' && isRcloneDest(destDirVal)) {
            $('input[name=localDirIsMountPoint]').closest('.form-group').hide();
        } else {
            $('input[name=localDirIsMountPoint]').closest('.form-group').show();
        }
    }

    setTransferTypeFields($('input[name=transferType]:checked').val());
    setSSHUseKeyField($('input[name=sshUseKey]:checked').val())
    setMountpointFieldForDestDir($('input[name=destDir]').val());

    $('input[name=transferType]').change(function () {
        setTransferTypeFields($(this).val());
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
        normalizeFieldsForTransferType($('input[name=transferType]:checked').val());
    });

});
