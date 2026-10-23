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
     * Config.php.dist's worker key, which is public, so never a worker's (#605).
     *
     * @var string
     */
    const PLACEHOLDER = 'change-me-to-a-strong-random-value';

    /**
     * Whether the request carries the worker key (WORKER_API_KEY in Config.php).
     *
     * @return bool
     */
    public static function isWorkerRequest(): bool
    {
        return defined('WORKER_API_KEY')
            && self::isWorkerToken(WORKER_API_KEY, $_SERVER['HTTP_X_WORKER_TOKEN'] ?? '');
    }

    /**
     * Whether a token is the worker key.
     *
     * A key that's empty, or still Config.php.dist's placeholder, matches no
     * token: the placeholder is public, so a site that never set its key
     * would give the passwords to anyone (#605).
     *
     * @param string $key   the worker key
     * @param string $token the request's X-Worker-Token
     *
     * @return bool
     */
    public static function isWorkerToken(string $key, string $token): bool
    {
        return $key !== '' && $key !== self::PLACEHOLDER && hash_equals($key, $token);
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
