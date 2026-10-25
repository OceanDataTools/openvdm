<?php
/**
 * Cruise dates helper.
 *
 * The System Status card turns yellow when the system is on but the current
 * time is outside the current cruise's start and end dates. This says why,
 * for the card's popup (templates/default/header.php) and for
 * api/warehouse/getSystemStatus, which header.js refreshes the card from
 * (#637).
 */

namespace Helpers;

class CruiseDates
{
    /**
     * Why the current time is outside the cruise's dates, or '' if it isn't.
     *
     * The dates are OpenVDM's "YYYY/MM/DD HH:MM" strings in UTC, so they
     * compare as strings. A blank end date means the cruise hasn't been
     * given one, and a blank start date (or a missing one, as when the
     * cruise config can't be read) is never a warning.
     *
     * @param array  $cruiseDates the current cruise's dates, as
     *                            \Models\Warehouse::getCruiseDates() returns them
     * @param string $now         the current time in the same format, e.g. gmdate('Y/m/d H:i')
     *
     * @return string the explanation, or '' if the time is within the dates
     */
    public static function warning(array $cruiseDates, string $now): string
    {
        $start = trim((string)($cruiseDates['cruiseStartDate'] ?? ''));
        $end = trim((string)($cruiseDates['cruiseEndDate'] ?? ''));
        if ($start === '') {
            return '';
        }

        if ($start > $now) {
            $where = "before the " . CRUISE_NAME . "'s start date ($start UTC)";
        } elseif ($end !== '' && $end < $now) {
            $where = "after the " . CRUISE_NAME . "'s end date ($end UTC)";
        } else {
            return '';
        }

        return "The current time ($now UTC) is $where. Collection system transfers set to skip files "
            . "created/modified outside of the " . strtolower(CRUISE_NAME) . " start/stop times won't "
            . "transfer files written now. If the dates are wrong, correct them with Edit Current "
            . CRUISE_NAME . ".";
    }
}
