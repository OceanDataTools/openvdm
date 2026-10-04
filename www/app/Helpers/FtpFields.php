<?php
/**
 * FTP Server transfer fields helper.
 *
 * Validation and password handling for the FTP Server fields shared by the
 * collection system transfer and cruise data transfer forms (#199), so the
 * rules live in one place (#213).
 */

namespace Helpers;

class FtpFields
{
    /**
     * Transfer type ID of FTP Server in OVDM_TransferTypes.
     *
     * @var int
     */
    const TRANSFER_TYPE = 5;

    /**
     * Validate the FTP Server fields of a submitted transfer.
     *
     * For an FTP Server transfer, checks the server (host, with an optional
     * :port from 1 to 65535; [brackets] around an IPv6 address with a port),
     * the username and the password (not needed for anonymous). The port
     * defaults to 21 (#224). Other transfer types' FTP fields are blanked on
     * save by TransferFields::clearOthers() (#243).
     *
     * @param mixed  $transferType submitted transfer type
     * @param string $ftpServer    FTP server, host[:port]
     * @param string $ftpUser      FTP username
     * @param string $ftpPass      FTP password
     *
     * @return array validation errors; empty if valid or not an FTP transfer
     */
    public static function check($transferType, $ftpServer, $ftpUser, $ftpPass)
    {

        if ($transferType != self::TRANSFER_TYPE) {
            return array();
        }

        $errors = array();
        if($ftpServer == ''){
            $errors[] = 'FTP Server is required';
        } else {
            // Same rules as split_ftp_server() in server/lib/connection_utils.py
            $port = null;
            if($ftpServer[0] === '['){
                if(preg_match('/^\[[^\]]+\](?::(\d*))?$/', $ftpServer, $matches)){
                    $port = $matches[1] ?? '';
                } else {
                    $errors[] = 'FTP Server must be a hostname or IP address, optionally followed by :port (e.g. "[2001:db8::1]:2121" for IPv6)';
                }
            } elseif(substr_count($ftpServer, ':') == 1){
                $port = explode(':', $ftpServer)[1];
            }

            if($port !== null && $port !== '' && (!ctype_digit($port) || (int)$port < 1 || (int)$port > 65535)){
                $errors[] = 'FTP Server port must be a number from 1 to 65535';
            }
        }

        if($ftpUser == ''){
            $errors[] = 'FTP Username is required';
        }

        if($ftpUser != 'anonymous' && $ftpPass == ''){
            $errors[] = 'FTP Password is required';
        }

        return $errors;
    }

    /**
     * Return the FTP password to use for an edit form submission.
     *
     * A blank password field normally keeps the existing password (a
     * password remembered from Test Setup, else the stored one, see
     * PendingPasswords). But a password saved for another FTP login isn't
     * sent (#211): not for anonymous access unless one is typed, and not
     * after the username changed (validation then asks for the new user's
     * password).
     *
     * @param string $ftpUser    submitted FTP username
     * @param string $ftpPass    password resolved by PendingPasswords::resolve()
     * @param string $postedPass password typed in the form ('' if blank)
     * @param object $row        the stored transfer
     *
     * @return string the password to use
     */
    public static function resolvePassword($ftpUser, $ftpPass, $postedPass, $row)
    {
        if ($postedPass === '') {
            if ($ftpUser == 'anonymous') {
                return '';
            }
            if ($ftpUser != $row->ftpUser && $ftpPass === $row->ftpPass) {
                return '';
            }
        }
        return $ftpPass;
    }
}
