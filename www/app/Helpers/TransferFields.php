<?php
/**
 * Transfer type fields helper.
 *
 * Collection system and cruise data transfers keep every transfer type's
 * connection fields in one row, but only the selected type's fields apply.
 * This helper is the one place that lists which fields belong to which type,
 * so the add and edit handlers of both config controllers blank the other
 * types' fields the same way (#243).
 */

namespace Helpers;

class TransferFields
{
    /**
     * Connection fields of each transfer type (OVDM_TransferTypes ID), with
     * the value each is blanked to.
     *
     * @var array
     */
    const FIELDS = array(
        1 => array('localDirIsMountPoint' => 0),
        2 => array('rsyncServer' => '', 'rsyncUser' => '', 'rsyncPass' => ''),
        3 => array('smbServer' => '', 'smbUser' => '', 'smbPass' => '', 'smbDomain' => ''),
        4 => array('sshServer' => '', 'sshUser' => '', 'sshUseKey' => 0, 'sshPass' => ''),
        5 => array('ftpServer' => '', 'ftpUser' => '', 'ftpPass' => ''),
    );

    /**
     * Blank the connection fields of every transfer type but the transfer's own.
     *
     * Used on the data a handler saves or sends to Test Setup, so a row never
     * keeps another type's server, username or password.
     *
     * @param array|object $transfer transfer data with a transferType field
     *
     * @return array|object the same data (same type) with the other types' fields blanked
     */
    public static function clearOthers($transfer)
    {
        $isObject = is_object($transfer);
        $fields = (array)$transfer;

        foreach (self::FIELDS as $type => $typeFields) {
            if ($type == ($fields['transferType'] ?? null)) {
                continue;
            }
            foreach ($typeFields as $field => $blank) {
                $fields[$field] = $blank;
            }
        }

        return $isObject ? (object)$fields : $fields;
    }
}
