<?php
/**
 * Transfer credential helper.
 *
 * Collection system and cruise data transfer rows hold passwords. API
 * responses include them only for the Python workers, which send the shared
 * worker key in the X-Worker-Token header. This helper is the one place that
 * lists the password fields, so a new transfer type's password can't be
 * missed by one of the API controllers (#205).
 */

namespace Helpers;

class TransferCredentials
{
    /**
     * Password fields of collection system and cruise data transfers.
     *
     * @var array
     */
    const FIELDS = array('rsyncPass', 'smbPass', 'sshPass', 'ftpPass');

    /**
     * Whether the request carries the worker key (WORKER_API_KEY in Config.php).
     *
     * @return bool
     */
    public static function isWorkerRequest(): bool
    {
        $token = $_SERVER['HTTP_X_WORKER_TOKEN'] ?? '';
        return defined('WORKER_API_KEY') && WORKER_API_KEY !== '' && hash_equals(WORKER_API_KEY, $token);
    }

    /**
     * Remove the password fields from transfer rows.
     *
     * @param array $rows transfer rows (objects)
     *
     * @return array the same rows without password fields
     */
    public static function strip(array $rows): array
    {
        return array_map(function ($row) {
            foreach (self::FIELDS as $field) {
                unset($row->$field);
            }
            return $row;
        }, $rows);
    }

    /**
     * Remove the password fields unless the request comes from a worker.
     *
     * @param array $rows transfer rows (objects)
     *
     * @return array the rows, without password fields for non-worker requests
     */
    public static function forResponse(array $rows): array
    {
        return self::isWorkerRequest() ? $rows : self::strip($rows);
    }
}
