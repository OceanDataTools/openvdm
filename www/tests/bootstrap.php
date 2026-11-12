<?php
/**
 * PHPUnit bootstrap (#515): Composer's autoloader, and the constants the web
 * app defines at run time.
 *
 * Core\Config defines its constants when it's constructed, which also starts
 * a session and installs error handlers, so the tests use the same
 * declarations as PHPStan: each define() in Config.php.dist with its
 * template value (phpstan-bootstrap.php), except the worker key.
 */

require __DIR__ . '/../vendor/autoload.php';

// A worker key for the tests, not Config.php.dist's placeholder
define('WORKER_API_KEY', 'test-worker-key');

require __DIR__ . '/../phpstan-bootstrap.php';
