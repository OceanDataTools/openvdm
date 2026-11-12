/**
 * Directory field normalization shared by the transfer forms (#630).
 *
 * The collection system transfer, cruise data transfer and shoreside data
 * warehouse forms load this before their own scripts (their controllers list
 * it first in $data['javascript']). Helpers\DirectoryFields applies the same
 * rules on the server, so a value saved without the form's scripts is
 * cleaned up too. Both are tested against www/tests/data/directory_fields.json:
 * change them together.
 */

/* exported normalizeAbsolutePath, normalizeRelativePath, isRclonePath, normalizeRclonePath,
   normalizeCdtDestDir, normalizeSsdwDestDir */

// A Windows drive letter, "C:" alone or before a slash (backslashes already turned into slashes)
var WINDOWS_DRIVE = /^[A-Za-z]:(?=\/|$)/;

/**
 * Trim a directory, turn backslashes into slashes and collapse runs of slashes.
 *
 * @param {string} val the directory as typed
 * @returns {string} the cleaned directory
 */
function cleanPath(val) {
    return val.trim().replace(/\\/g, '/').replace(/\/{2,}/g, '/');
}

/**
 * Whether a destination is an rclone remote:path. A Windows path (C:\data) isn't one.
 *
 * @param {string} val the directory as typed
 * @returns {boolean} whether it names an rclone remote
 */
function isRclonePath(val) {
    val = val.trim().replace(/\\/g, '/');
    return val.indexOf(':') !== -1 && !WINDOWS_DRIVE.test(val);
}

/**
 * An rclone remote:path, without leading slashes on the remote's name.
 *
 * @param {string} val the directory as typed
 * @returns {string} the remote:path
 */
function normalizeRclonePath(val) {
    return val.trim().replace(/\\/g, '/').replace(/^\/+/, '');
}

/**
 * An absolute path: a leading slash and no trailing one, so "/" for the root.
 * A Windows drive letter is dropped (C:\data → /data).
 *
 * @param {string} val the directory as typed
 * @returns {string} the path, or "" if nothing was typed
 */
function normalizeAbsolutePath(val) {
    val = cleanPath(val);
    if (val === '') {
        return '';
    }
    return '/' + val.replace(WINDOWS_DRIVE, '').replace(/^\/|\/$/g, '');
}

/**
 * A path relative to a top directory (the cruise directory, an rsync module
 * or an SMB share): no leading or trailing slash, and "/" for the top
 * directory itself (#247, #629).
 *
 * @param {string} val the directory as typed
 * @returns {string} the path, or "" if nothing was typed
 */
function normalizeRelativePath(val) {
    val = cleanPath(val);
    if (val === '') {
        return '';
    }
    return val.replace(/^\/|\/$/g, '') || '/';
}

/**
 * A cruise data transfer's Destination Directory, for its transfer type:
 * absolute for Local Directory (unless it's an rclone remote:path), SSH and
 * FTP; relative to the rsync module or SMB share otherwise. Without a type
 * it isn't known whether the path is absolute, so it's only trimmed.
 *
 * @param {string} val the directory as typed
 * @param {string} transferType the transfer type (OVDM_TransferTypes ID), or ''
 * @returns {string} the directory
 */
function normalizeCdtDestDir(val, transferType) {
    switch (String(transferType)) {
    case '':
        return val.trim().replace(/\\/g, '/');
    case '1':
        return isRclonePath(val) ? normalizeRclonePath(val) : normalizeAbsolutePath(val);
    case '4':
    case '5':
        return normalizeAbsolutePath(val);
    default:
        return normalizeRelativePath(val);
    }
}

/**
 * The shoreside data warehouse's Destination Directory: an rclone
 * remote:path, or an absolute path on its SSH server.
 *
 * @param {string} val the directory as typed
 * @returns {string} the directory
 */
function normalizeSsdwDestDir(val) {
    return isRclonePath(val) ? normalizeRclonePath(val) : normalizeAbsolutePath(val);
}
