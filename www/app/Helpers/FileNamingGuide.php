<?php
/**
 * File Naming Guide helper (#451).
 *
 * Turns a collection system transfer's Include, Exclude and Ignore filters
 * into plain-language rules for the technicians who name the files, for the
 * File Naming Guide page. The explanations follow how
 * server/workers/run_collection_system_transfer.py applies the filters:
 *
 * - the filters are comma-separated fnmatch patterns, case-sensitive, in which
 *   "*" also matches "/";
 * - the placeholders below are filled in first (build_filters());
 * - a file is checked against the default ignores, the date range, the ASCII
 *   rule, then Ignore (skipped, not reported), Include (must match) and
 *   Exclude (not copied, and listed as a filename error on the main page);
 *   anything else is a filename error too (classify_file());
 * - what a pattern is matched against depends on the transfer type: the full
 *   path on the OpenVDM server (local directory), a full path under a
 *   temporary mount point (SMB, FTP), or the path within the source directory
 *   (rsync, SSH).
 *
 * Change this helper when that code changes, so the guide never says a file
 * will be transferred when it won't.
 */

namespace Helpers;

class FileNamingGuide
{
    /**
     * Transfer type IDs (OVDM_TransferTypes).
     */
    const LOCAL = 1;
    const RSYNC = 2;
    const SMB = 3;
    const SSH = 4;
    const FTP = 5;

    /**
     * The date placeholders: what each matches, and its date() format for
     * example names.
     *
     * @var array
     */
    const DATE_PLACEHOLDERS = array(
        '{YYYY}' => array('a 4-digit year from 2000 to 2099', 'Y'),
        '{YY}' => array('a 2-digit year', 'y'),
        '{mm}' => array('a 2-digit month', 'm'),
        '{DD}' => array('a 2-digit day of the month', 'd'),
        '{HH}' => array('a 2-digit hour', 'H'),
        '{MM}' => array('a 2-digit minute', 'i'),
        '{SS}' => array('a 2-digit second', 's'),
    );

    /**
     * The placeholder key for the page: each placeholder, what it matches, and
     * its current value where it has one.
     *
     * @param array $context cruiseID, loweringID and now (a Unix time), see guideFor()
     *
     * @return array rows of placeholder, meaning and value ('' if none)
     */
    public static function placeholderKey($context)
    {
        $rows = array(
            array('{cruiseID}', 'the ' . strtolower(CRUISE_NAME) . ' ID', $context['cruiseID']),
            array('{loweringID}', 'the ' . strtolower(LOWERING_NAME) . ' ID', $context['loweringID']),
        );
        foreach (self::DATE_PLACEHOLDERS as $placeholder => list($meaning, $format)) {
            $rows[] = array($placeholder, $meaning, '');
        }
        return $rows;
    }

    /**
     * The guide's content for one collection system transfer.
     *
     * @param object $cst       the transfer's row (OVDM_CollectionSystemTransfers)
     * @param string $typeName  its transfer type's name
     * @param array  $context   cruiseID, loweringID ('' if none), the
     *                          dates of the cruise and the current lowering
     *                          (cruiseStartDate, cruiseEndDate,
     *                          loweringStartDate, loweringEndDate) and now (a
     *                          Unix time, for example names)
     *
     * @return array id, name, longName, description, lowering (bool), enabled
     *               (bool), typeName, source (label => value), include,
     *               exclude and ignore (lists of describePattern() results)
     *               and rules (sentences)
     */
    public static function guideFor($cst, $typeName, $context)
    {
        $type = (int) $cst->transferType;
        $lowering = (int) $cst->cruiseOrLowering === 1;

        return array(
            'id' => (int) $cst->collectionSystemTransferID,
            'name' => $cst->name,
            'longName' => $cst->longName,
            'description' => (string) ($cst->description ?? ''),
            'lowering' => $lowering,
            'enabled' => (int) $cst->enable === 1,
            'typeName' => $typeName,
            'source' => self::source($cst, $type, $context),
            'include' => self::patterns($cst->includeFilter, $type, $context),
            'exclude' => self::patterns($cst->excludeFilter, $type, $context),
            'ignore' => self::patterns($cst->ignoreFilter, $type, $context),
            'rules' => self::rules($cst, $type, $lowering, $context),
        );
    }

    /**
     * Explain one filter pattern.
     *
     * @param string $pattern the pattern as written in the filter
     * @param int    $type    the transfer type ID
     * @param array  $context see guideFor()
     *
     * @return array pattern (as written), filled (with the cruise and lowering
     *               IDs filled in), sentence (a list of [kind, text] to show
     *               in order, kind 'text' or 'code' for literal name text),
     *               example (a matching name, or '' when one can't be given)
     *               and warning ('' or why the pattern can't match)
     */
    public static function describePattern($pattern, $type, $context)
    {
        return array(
            'pattern' => $pattern,
            'filled' => self::fillIds($pattern, $context),
            'sentence' => self::sentence(self::parts($pattern, $context)),
            'example' => self::example($pattern, $context),
            'warning' => self::warning($pattern, $type),
        );
    }

    /**
     * Put a pattern's pieces into words.
     *
     * "anything, `.raw`" reads as "any name ending in `.raw`", "anything,
     * `RR2601`, anything" as "any name containing `RR2601`"; otherwise the
     * pieces are joined with "then", after "any name starting with" when the
     * pattern has no leading "*".
     *
     * @param array $parts the pieces, from parts()
     *
     * @return array list of [kind, text]
     */
    private static function sentence($parts)
    {
        $any = array('text', 'anything');
        $count = count($parts);
        if ($count === 1 && $parts[0] === array('text', 'any name')) {
            return $parts;
        }
        if ($count === 2 && $parts[0] === $any && $parts[1][0] === 'code') {
            return array(array('text', 'any name ending in '), $parts[1]);
        }
        if ($count === 3 && $parts[0] === $any && $parts[2] === $any && $parts[1][0] === 'code') {
            return array(array('text', 'any name containing '), $parts[1]);
        }

        $sentence = array();
        if ($parts && $parts[0] === $any) {
            $sentence[] = array('text', 'anything, then ');
            array_shift($parts);
        } else {
            $sentence[] = array('text', 'starting with ');
        }
        foreach ($parts as $index => $part) {
            if ($index > 0) {
                $sentence[] = array('text', ', then ');
            }
            $sentence[] = $part === $any && $index === count($parts) - 1 ? array('text', 'anything after that') : $part;
        }
        return $sentence;
    }

    /**
     * Explain each pattern of a comma-separated filter.
     *
     * @param string $filter  the filter
     * @param int    $type    the transfer type ID
     * @param array  $context see guideFor()
     *
     * @return array describePattern() results
     */
    private static function patterns($filter, $type, $context)
    {
        $result = array();
        foreach ($filter === null || $filter === '' ? array() : explode(',', $filter) as $pattern) {
            if ($pattern !== '') {
                $result[] = self::describePattern($pattern, $type, $context);
            }
        }
        return $result;
    }

    /**
     * Fill in the cruise and lowering IDs, as the transfer does.
     *
     * @param string $text    a pattern or directory
     * @param array  $context see guideFor()
     *
     * @return string the text with the IDs filled in ({loweringID} stays
     *                when there's no current lowering, as in the transfer)
     */
    private static function fillIds($text, $context)
    {
        $text = str_replace('{cruiseID}', $context['cruiseID'], (string) $text);
        if ($context['loweringID'] !== '') {
            $text = str_replace('{loweringID}', $context['loweringID'], $text);
        }
        return $text;
    }

    /**
     * Split a pattern into the pieces a file name must have, in order.
     *
     * @param string $pattern the pattern as written
     * @param array  $context see guideFor()
     *
     * @return array list of [kind, text]; kind 'code' is literal text
     */
    private static function parts($pattern, $context)
    {
        if ($pattern === '*') {
            return array(array('text', 'any name'));
        }

        $parts = array();
        $literal = '';
        $add = function ($kind, $text) use (&$parts, &$literal) {
            if ($literal !== '') {
                $parts[] = array('code', $literal);
                $literal = '';
            }
            if ($kind !== null) {
                $parts[] = array($kind, $text);
            }
        };

        $length = strlen($pattern);
        for ($i = 0; $i < $length; $i++) {
            $char = $pattern[$i];

            if ($char === '{' && preg_match('/^\{[A-Za-z]+\}/', substr($pattern, $i), $match)) {
                $placeholder = $match[0];
                if ($placeholder === '{cruiseID}' || ($placeholder === '{loweringID}' && $context['loweringID'] !== '')) {
                    $literal .= $placeholder === '{cruiseID}' ? $context['cruiseID'] : $context['loweringID'];
                    $i += strlen($placeholder) - 1;
                    continue;
                }
                if ($placeholder === '{loweringID}') {
                    $add('text', 'the ' . strtolower(LOWERING_NAME) . ' ID');
                    $i += strlen($placeholder) - 1;
                    continue;
                }
                if (isset(self::DATE_PLACEHOLDERS[$placeholder])) {
                    $add('text', self::DATE_PLACEHOLDERS[$placeholder][0]);
                    $i += strlen($placeholder) - 1;
                    continue;
                }
            }

            if ($char === '*') {
                $add(null, null);
                if (!$parts || end($parts) !== array('text', 'anything')) {
                    $parts[] = array('text', 'anything');
                }
                continue;
            }
            if ($char === '?') {
                $add('text', 'any one character');
                continue;
            }
            if ($char === '[') {
                $close = strpos($pattern, ']', $i + 2);
                if ($close !== false) {
                    $set = substr($pattern, $i + 1, $close - $i - 1);
                    if ($set === '0-9') {
                        $add('text', 'one digit');
                    } elseif ($set[0] === '!') {
                        $add('text', 'one character other than ' . substr($set, 1));
                    } else {
                        $add('text', 'one of ' . $set);
                    }
                    $i = $close;
                    continue;
                }
            }
            $literal .= $char;
        }
        $add(null, null);

        // "any one character" x 4 -> "any 4 characters", "one digit" x 2 -> "2 digits"
        $collapsed = array();
        foreach ($parts as $part) {
            $last = count($collapsed) - 1;
            if ($last >= 0 && $part[0] === 'text' && in_array($part[1], array('any one character', 'one digit'), true)
                && preg_match('/^(?:any (\d+) characters|(\d+) digits|any one character|one digit)$/', $collapsed[$last][1], $match)
                && (($part[1] === 'one digit') === (strpos($collapsed[$last][1], 'digit') !== false))) {
                $n = (int) ($match[1] ?? 0) + (int) ($match[2] ?? 0);
                $n = ($n === 0 ? 1 : $n) + 1;
                $collapsed[$last] = array('text', $part[1] === 'one digit' ? "$n digits" : "any $n characters");
                continue;
            }
            $collapsed[] = $part;
        }
        return $collapsed;
    }

    /**
     * A file name the pattern matches, when the pattern pins it down.
     *
     * A leading "*" (any folder) is dropped; any other wildcard means there's
     * no single example, so none is given. Date placeholders use now.
     *
     * @param string $pattern the pattern as written
     * @param array  $context see guideFor()
     *
     * @return string the example, or ''
     */
    private static function example($pattern, $context)
    {
        $name = self::fillIds($pattern, $context);
        foreach (self::DATE_PLACEHOLDERS as $placeholder => list($meaning, $format)) {
            $name = str_replace($placeholder, gmdate($format, $context['now']), $name);
        }
        $name = ltrim($name, '*');
        $name = preg_replace('#^/#', '', $name);
        if ($name === '' || $name[0] === '.' || preg_match('/[*?\[{]/', $name)) {
            return '';
        }
        return basename($name) === $name || strpos($pattern, '*') === 0 ? basename($name) : $name;
    }

    /**
     * Why a pattern can never match for this transfer type, or ''.
     *
     * @param string $pattern the pattern as written
     * @param int    $type    the transfer type ID
     *
     * @return string the warning
     */
    private static function warning($pattern, $type)
    {
        if (preg_match('/\{(?!cruiseID\}|loweringID\}|YYYY\}|YY\}|mm\}|DD\}|HH\}|MM\}|SS\})[A-Za-z]+\}/', $pattern, $match)) {
            return $match[0] . ' isn\'t a placeholder OpenVDM fills in, so it\'s matched as written.';
        }
        $first = $pattern[0] ?? '';
        if (($type === self::SMB || $type === self::FTP) && $first !== '*') {
            return 'This pattern never matches: OpenVDM checks SMB and FTP files by a path under a temporary mount point, so a pattern must start with *.';
        }
        if ($type === self::LOCAL && $first !== '*' && $first !== '/') {
            return 'This pattern never matches: OpenVDM checks local files by their full path on the OpenVDM server, so a pattern must start with * (or with that full path).';
        }
        if (($type === self::RSYNC || $type === self::SSH) && $first === '/') {
            return 'This pattern never matches: OpenVDM checks rsync and SSH files by their path within the source directory, which doesn\'t start with /.';
        }
        return '';
    }

    /**
     * Where the files are collected from (no credentials).
     *
     * @param object $cst     the transfer's row
     * @param int    $type    the transfer type ID
     * @param array  $context see guideFor()
     *
     * @return array label => value
     */
    private static function source($cst, $type, $context)
    {
        $servers = array(self::RSYNC => 'rsyncServer', self::SMB => 'smbServer', self::SSH => 'sshServer', self::FTP => 'ftpServer');
        $source = array();
        if (isset($servers[$type]) && !empty($cst->{$servers[$type]})) {
            $source[$type === self::SMB ? 'Share' : 'Server'] = $cst->{$servers[$type]};
        }
        $source['Directory'] = self::fillIds($cst->sourceDir, $context);
        return $source;
    }

    /**
     * The rules besides the filters that decide whether a file is copied.
     *
     * @param object $cst      the transfer's row
     * @param int    $type     the transfer type ID
     * @param bool   $lowering whether it's a lowering-level transfer
     * @param array  $context  see guideFor()
     *
     * @return array sentences
     */
    private static function rules($cst, $type, $lowering, $context)
    {
        if ($type === self::RSYNC || $type === self::SSH) {
            $matched = 'the file\'s path within the source directory, e.g. subfolder/file.raw';
        } elseif ($type === self::LOCAL) {
            $matched = 'the file\'s full path on the OpenVDM server';
        } else {
            $matched = 'the file\'s full path under a temporary mount point, so start each pattern with *';
        }
        $rules = array(
            'Patterns are matched against ' . $matched . '. A * also matches across folders, so *.raw matches .raw files in every sub-folder.',
            'Names are case-sensitive: *.raw doesn\'t match FILE.RAW.',
            'Names must use plain ASCII characters only (no accented letters or symbols such as °); a file with any other character in its path isn\'t copied and is listed as a filename error.',
        );

        if ((int) $cst->useStartDate === 1) {
            $name = $lowering ? LOWERING_NAME : CRUISE_NAME;
            $start = $context[$lowering ? 'loweringStartDate' : 'cruiseStartDate'];
            $end = $context[$lowering ? 'loweringEndDate' : 'cruiseEndDate'];
            $rules[] = 'Only files last modified during the ' . strtolower($name)
                . ($start !== '' || $end !== '' ? ' (' . ($start !== '' ? $start : 'any time') . ' to ' . ($end !== '' ? $end : 'now') . ', UTC)' : '')
                . ' are copied; files modified before or after it are skipped without being reported.';
        }
        if ((int) $cst->staleness > 0) {
            $rules[] = 'Files still being written are left for the next transfer: a file is only copied once its size hasn\'t changed for ' . (int) $cst->staleness . ' seconds.';
        }
        if ((int) $cst->skipEmptyFiles === 1) {
            $rules[] = 'Empty (0-byte) files aren\'t copied.';
        }
        $rules[] = 'System and temporary files are always skipped without being reported: .DS_Store, ._*, Thumbs.db, desktop.ini, Office lock files (~$*, .~lock.*#), rsync temporary files, and recycle bins, snapshots and system folders such as lost+found, $RECYCLE.BIN, .Trashes and .snapshot.';
        return $rules;
    }
}
