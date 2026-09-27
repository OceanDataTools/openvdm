<?php
/**
 * PHPStan bootstrap: declare the constants the web app defines at runtime.
 *
 * Core\Config defines its constants in its constructor, which also installs
 * error handlers and starts a session, so it can't simply be instantiated
 * here. Instead, read the define() calls from Config.php.dist and declare
 * each constant with its template value. index.php defines ROOT and SMVC.
 */

define('ROOT', __DIR__ . DIRECTORY_SEPARATOR);
define('SMVC', __DIR__ . DIRECTORY_SEPARATOR);

$configSource = file_get_contents(__DIR__ . '/app/Core/Config.php.dist');
preg_match_all(
    "/^\s*define\('([A-Z0-9_]+)',\s*(.+?)\);/m",
    $configSource,
    $matches,
    PREG_SET_ORDER
);

foreach ($matches as [, $name, $value]) {
    if (defined($name)) {
        continue;
    }
    if ($value === 'true' || $value === 'false') {
        define($name, $value === 'true');
    } elseif (preg_match("/^'(.*)'$/", $value, $string)) {
        define($name, $string[1]);
    } elseif (is_numeric($value)) {
        define($name, $value + 0);
    }
}

unset($configSource, $matches, $name, $value, $string);
