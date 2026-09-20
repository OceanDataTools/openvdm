<?php
/**
 * Pending password helper.
 *
 * Edit forms for records with credentials never pre-populate password inputs,
 * so a password typed before "Test Setup" is blank again when the page is
 * re-rendered. This helper keeps such a password server-side (in the session)
 * so it can still be applied when the user clicks "Update".
 */
namespace Helpers;

class PendingPasswords
{
    /**
     * Password fields handled by this helper.
     *
     * @var array
     */
    private static $fields = array('rsyncPass', 'smbPass', 'sshPass');

    /**
     * Build the session key for one record.
     *
     * @param string $scope record type, e.g. 'cst' or 'cdt'
     * @param mixed  $id    record ID
     *
     * @return string
     */
    private static function key($scope, $id)
    {
        return 'pendingPasswords_' . $scope . '_' . (int)$id;
    }

    /**
     * Resolve the password values to use for a submitted edit form.
     *
     * Precedence: value posted with the form, then a password remembered from
     * an earlier "Test Setup", then the stored password.
     *
     * @param string $scope    record type, e.g. 'cst' or 'cdt'
     * @param mixed  $id       record ID
     * @param array  $posted   posted values keyed by field name
     * @param object $row      the stored record
     * @param bool   $remember remember non-empty posted values for a later request
     *
     * @return array resolved values keyed by field name
     */
    public static function resolve($scope, $id, array $posted, $row, $remember = false)
    {
        $pending = Session::get(self::key($scope, $id));
        $pending = is_array($pending) ? $pending : array();

        $resolved = array();
        foreach (self::$fields as $field) {
            $value = $posted[$field] ?? '';
            if ($value !== '') {
                $pending[$field] = $value;
            } elseif (!empty($pending[$field])) {
                $value = $pending[$field];
            } elseif (!empty($row->$field)) {
                $value = $row->$field;
            }
            $resolved[$field] = $value;
        }

        if ($remember) {
            Session::set(self::key($scope, $id), $pending);
        }

        return $resolved;
    }

    /**
     * Report which passwords are remembered, without exposing their values.
     *
     * @param string $scope record type, e.g. 'cst' or 'cdt'
     * @param mixed  $id    record ID
     *
     * @return array booleans keyed by field name
     */
    public static function flags($scope, $id)
    {
        $pending = Session::get(self::key($scope, $id));
        $pending = is_array($pending) ? $pending : array();

        $flags = array();
        foreach (self::$fields as $field) {
            $flags[$field] = !empty($pending[$field]);
        }

        return $flags;
    }

    /**
     * Forget any remembered passwords for a record.
     *
     * @param string $scope record type, e.g. 'cst' or 'cdt'
     * @param mixed  $id    record ID
     */
    public static function clear($scope, $id)
    {
        Session::pull(self::key($scope, $id));
    }
}
