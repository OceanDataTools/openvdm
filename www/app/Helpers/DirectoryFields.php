<?php
/**
 * Directory fields helper.
 *
 * The transfer forms clean up their directory fields as they're typed
 * (templates/default/js/directoryFields.js). This applies the same rules when
 * the CST, CDT and shoreside data warehouse forms are saved or tested, so a
 * value posted without the form's scripts is cleaned up too (#630). Both are
 * tested against www/tests/data/directory_fields.json: change them together.
 */

namespace Helpers;

class DirectoryFields
{
    /**
     * A Windows drive letter, "C:" alone or before a slash (backslashes
     * already turned into slashes).
     */
    const WINDOWS_DRIVE = '/^[A-Za-z]:(?=\/|$)/';

    /**
     * Trim a directory, turn backslashes into slashes and collapse runs of slashes.
     */
    private static function clean(string $val): string
    {
        return preg_replace('#/{2,}#', '/', str_replace('\\', '/', trim($val)));
    }

    /**
     * Whether a destination is an rclone remote:path. A Windows path (C:\data) isn't one.
     *
     * @param string $val the directory as posted
     *
     * @return bool whether it names an rclone remote
     */
    public static function isRclone(string $val): bool
    {
        $val = str_replace('\\', '/', trim($val));
        return strpos($val, ':') !== false && !preg_match(self::WINDOWS_DRIVE, $val);
    }

    /**
     * An rclone remote:path, without leading slashes on the remote's name.
     *
     * @param string $val the directory as posted
     *
     * @return string the remote:path
     */
    public static function rclone(string $val): string
    {
        return ltrim(str_replace('\\', '/', trim($val)), '/');
    }

    /**
     * An absolute path: a leading slash and no trailing one, so "/" for the
     * root. A Windows drive letter is dropped (C:\data → /data).
     *
     * @param string $val the directory as posted
     *
     * @return string the path, or '' if it's empty
     */
    public static function absolute(string $val): string
    {
        $val = self::clean($val);
        if ($val === '') {
            return '';
        }
        return '/' . trim(preg_replace(self::WINDOWS_DRIVE, '', $val), '/');
    }

    /**
     * A path relative to a top directory (the cruise directory, an rsync
     * module or an SMB share): no leading or trailing slash, and "/" for the
     * top directory itself (#247, #629).
     *
     * @param string $val the directory as posted
     *
     * @return string the path, or '' if it's empty
     */
    public static function relative(string $val): string
    {
        $val = self::clean($val);
        if ($val === '') {
            return '';
        }
        $val = trim($val, '/');
        return $val === '' ? '/' : $val;
    }

    /**
     * A cruise data transfer's Destination Directory, for its transfer type:
     * absolute for Local Directory (unless it's an rclone remote:path), SSH
     * and FTP; relative to the rsync module or SMB share otherwise. Without a
     * type it's only trimmed, as the form leaves it.
     *
     * @param string     $val          the directory as posted
     * @param int|string $transferType the transfer type (OVDM_TransferTypes ID), or ''
     *
     * @return string the directory
     */
    public static function cdtDestDir(string $val, $transferType): string
    {
        switch ((string)$transferType) {
            case '':
                return str_replace('\\', '/', trim($val));
            case '1':
                return self::isRclone($val) ? self::rclone($val) : self::absolute($val);
            case '4':
            case '5':
                return self::absolute($val);
            default:
                return self::relative($val);
        }
    }

    /**
     * The shoreside data warehouse's Destination Directory: an rclone
     * remote:path, or an absolute path on its SSH server.
     *
     * @param string $val the directory as posted
     *
     * @return string the directory
     */
    public static function ssdwDestDir(string $val): string
    {
        return self::isRclone($val) ? self::rclone($val) : self::absolute($val);
    }
}
