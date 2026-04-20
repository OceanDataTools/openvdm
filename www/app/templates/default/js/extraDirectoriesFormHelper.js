$(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // Field normalization helpers
    // ---------------------------------------------------------------------------

    function normalizeDestDir(val) {
        val = val.trim();
        // Replace backslashes with forward slashes
        val = val.replace(/\\/g, '/');
        // Strip leading and trailing slashes (dest dir is relative within cruise dir)
        val = val.replace(/^\/+/, '').replace(/\/+$/, '');
        return val;
    }

    // ---------------------------------------------------------------------------
    // Normalize on blur (immediate feedback) and on submit (safety net)
    // ---------------------------------------------------------------------------

    $('input[name=name], input[name=longName]').on('blur', function () {
        $(this).val($(this).val().trim());
    });

    $('input[name=destDir]').on('blur', function () {
        $(this).val(normalizeDestDir($(this).val()));
    });

    $('form').on('submit', function () {
        $('input[type="text"], input[type="password"], input:not([type])').each(function () {
            $(this).val($(this).val().trim());
        });
        $('input[name=destDir]').val(normalizeDestDir($('input[name=destDir]').val()));
    });

});
