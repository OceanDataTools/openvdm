<?php
/**
 * Gearman worker status helper (#503).
 *
 * A worker that can't start (a missing Python package, a missing
 * openvdm.yaml, a crash on import) is only reported in Supervisor's log,
 * while the web pages carry on as if its tasks could run. This asks gearmand
 * which functions have workers, with the admin protocol's "status" command
 * (as `gearadmin --status` does), and lists the OpenVDM workers that have
 * none, so the Configuration page can warn about them.
 *
 * WORKERS lists the functions each standard worker registers, by its
 * Supervisor program name. server/tests/test_gearman_worker_list.py checks
 * it against the workers' register_task() calls.
 */

namespace Helpers;

class GearmanStatus
{
    /**
     * The functions each worker registers, by Supervisor program.
     *
     * @var array
     */
    const WORKERS = array(
        'cruise' => array('setupNewCruise', 'finalizeCurrentCruise', 'exportOVDMConfig',
                          'rsyncPublicDataToCruiseData', 'rebuildCruiseReadme'),
        'cruise_directory' => array('createCruiseDirectory', 'setCruiseDataDirectoryPermissions',
                                    'rebuildCruiseDirectory'),
        'data_dashboard' => array('updateDataDashboard', 'rebuildDataDashboard'),
        'lowering' => array('setupNewLowering', 'finalizeCurrentLowering', 'exportLoweringConfig',
                            'rebuildLoweringReadme'),
        'lowering_directory' => array('createLoweringDirectory', 'setLoweringDataDirectoryPermissions',
                                      'rebuildLoweringDirectory'),
        'md5_summary' => array('updateMD5Summary', 'rebuildMD5Summary'),
        'post_hooks' => array('postCollectionSystemTransfer', 'postDataDashboard', 'postSetupNewCruise',
                              'postSetupNewLowering', 'preFinalizeCurrentCruise', 'postFinalizeCurrentCruise',
                              'preFinalizeCurrentLowering', 'postFinalizeCurrentLowering'),
        'run_collection_system_transfer' => array('runCollectionSystemTransfer'),
        'run_cruise_data_transfer' => array('runCruiseDataTransfer'),
        'run_ship_to_shore_transfer' => array('runShipToShoreTransfer'),
        'stop_job' => array('stopJob'),
        'test_collection_system_transfer' => array('testCollectionSystemTransfer'),
        'test_cruise_data_transfer' => array('testCruiseDataTransfer'),
    );

    /**
     * gearmand's address: the default that GearmanClient::addServer() uses
     * everywhere else in the web pages.
     */
    const HOST = '127.0.0.1';
    const PORT = 4730;

    /** Seconds to wait for gearmand to connect and to answer. */
    const TIMEOUT = 2;

    /**
     * The workers that have no worker process registered with gearmand.
     *
     * A function gearmand doesn't list, which is the case after a reboot
     * when its worker never started, counts as having no worker, the same
     * as one listed with 0 workers.
     *
     * @return array|null program => its functions with no worker, for each
     *                    program that has any; null if gearmand can't be
     *                    reached
     */
    public static function missingWorkers()
    {
        $available = self::availableWorkers();
        if ($available === null) {
            return null;
        }
        return self::missing($available);
    }

    /**
     * The workers whose functions have no worker in a gearmand status.
     *
     * @param array $available function => number of available workers
     *
     * @return array program => its functions with no worker
     */
    public static function missing($available)
    {
        $missing = array();
        foreach (self::WORKERS as $program => $functions) {
            foreach ($functions as $function) {
                if (($available[$function] ?? 0) < 1) {
                    $missing[$program][] = $function;
                }
            }
        }
        return $missing;
    }

    /**
     * The warning to show for a status, as HTML.
     *
     * @param array|null $missing missingWorkers()'s result
     *
     * @return string an alert, or '' when every worker is running
     */
    public static function alert($missing)
    {
        if ($missing === null) {
            return '<div class="alert alert-danger"><i class="fa fa-warning"></i> '
                . 'Unable to reach the Gearman job server (gearmand) at ' . self::HOST . ':' . self::PORT
                . ', so no OpenVDM tasks or transfers can run. Check that gearmand is running.</div>';
        }
        if (!$missing) {
            return '';
        }

        $items = '';
        foreach ($missing as $program => $functions) {
            $items .= '<li><strong>' . htmlspecialchars($program, ENT_QUOTES, 'UTF-8') . '</strong>: '
                . htmlspecialchars(implode(', ', $functions), ENT_QUOTES, 'UTF-8') . '</li>';
        }
        return '<div class="alert alert-danger"><i class="fa fa-warning"></i> '
            . 'These OpenVDM workers aren\'t running, so their tasks won\'t run:'
            . '<ul>' . $items . '</ul>'
            . 'Check <code>supervisorctl status</code> and the worker\'s log in <code>/var/log/openvdm/</code>. '
            . 'A worker that fails as it starts, e.g. because of a missing Python package, '
            . 'posts the reason as an OpenVDM message.</div>';
    }

    /**
     * Parse gearmand's answer to "status".
     *
     * Each line is "function<TAB>queued<TAB>running<TAB>available workers",
     * and a line holding "." ends it.
     *
     * @param string $text the answer
     *
     * @return array function => number of available workers
     */
    public static function parseStatus($text)
    {
        $available = array();
        foreach (explode("\n", str_replace("\r", '', (string) $text)) as $line) {
            if ($line === '.') {
                break;
            }
            $fields = explode("\t", $line);
            if (count($fields) >= 4) {
                $available[$fields[0]] = (int) $fields[3];
            }
        }
        return $available;
    }

    /**
     * Ask gearmand for the number of available workers of each function.
     *
     * @return array|null function => number of available workers; null if
     *                    gearmand can't be reached or doesn't answer
     */
    private static function availableWorkers()
    {
        $socket = @fsockopen(self::HOST, self::PORT, $errno, $errstr, self::TIMEOUT);
        if ($socket === false) {
            return null;
        }
        stream_set_timeout($socket, self::TIMEOUT);

        $text = '';
        if (fwrite($socket, "status\n") !== false) {
            while (($line = fgets($socket)) !== false) {
                $text .= $line;
                if (rtrim($line, "\r\n") === '.') {
                    break;
                }
            }
        }
        $timedOut = stream_get_meta_data($socket)['timed_out'];
        fclose($socket);

        if ($timedOut || !preg_match('/^\.\r?$/m', $text)) {
            return null;
        }
        return self::parseStatus($text);
    }
}
