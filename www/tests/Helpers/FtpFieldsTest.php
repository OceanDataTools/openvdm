<?php
/**
 * Tests for Helpers\FtpFields: the FTP Server fields' validation (#224, the
 * same rules as split_ftp_server() in server/lib/connection_utils.py) and
 * the password kept on edit (#211).
 */

namespace Tests\Helpers;

use Helpers\FtpFields;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class FtpFieldsTest extends TestCase
{
    public function testOtherTypesArentChecked(): void
    {
        $this->assertSame(array(), FtpFields::check(4, '', '', ''));
    }

    public static function validServers(): array
    {
        return array(
            'host' => array('ftp.example'), 'host and port' => array('ftp.example:2121'),
            'IPv4' => array('192.168.0.21'), 'IPv4 and port' => array('192.168.0.21:21'),
            'bare IPv6' => array('2001:db8::1'), 'bracketed IPv6' => array('[2001:db8::1]'),
            'bracketed IPv6 and port' => array('[2001:db8::1]:2121'), 'empty port' => array('ftp.example:'),
            'lowest port' => array('ftp.example:1'), 'highest port' => array('ftp.example:65535'),
        );
    }

    #[DataProvider('validServers')]
    public function testValidServers(string $server): void
    {
        $this->assertSame(array(), FtpFields::check(5, $server, 'survey', 'pw'));
    }

    public static function invalidServers(): array
    {
        $port = 'FTP Server port must be a number from 1 to 65535';
        return array(
            'empty' => array('', 'FTP Server is required'),
            'port 0' => array('ftp.example:0', $port), 'port too high' => array('ftp.example:65536', $port),
            'port not a number' => array('ftp.example:ftp', $port), 'negative port' => array('ftp.example:-1', $port),
            'bracketed port too high' => array('[2001:db8::1]:70000', $port),
            'unclosed bracket' => array('[2001:db8::1', 'FTP Server must be a hostname or IP address, optionally followed by :port (e.g. "[2001:db8::1]:2121" for IPv6)'),
            'text after bracket' => array('[2001:db8::1]x', 'FTP Server must be a hostname or IP address, optionally followed by :port (e.g. "[2001:db8::1]:2121" for IPv6)'),
        );
    }

    #[DataProvider('invalidServers')]
    public function testInvalidServers(string $server, string $error): void
    {
        $this->assertSame(array($error), FtpFields::check('5', $server, 'survey', 'pw'));
    }

    public function testUsernameAndPassword(): void
    {
        $this->assertSame(array('FTP Username is required', 'FTP Password is required'),
                          FtpFields::check(5, 'ftp.example', '', ''));
        $this->assertSame(array('FTP Password is required'), FtpFields::check(5, 'ftp.example', 'survey', ''));
        // Anonymous access needs no password
        $this->assertSame(array(), FtpFields::check(5, 'ftp.example', 'anonymous', ''));
    }

    private function row(): object
    {
        return (object) array('ftpUser' => 'survey', 'ftpPass' => 'stored');
    }

    public function testTypedPasswordIsUsed(): void
    {
        $this->assertSame('typed', FtpFields::resolvePassword('anonymous', 'typed', 'typed', $this->row()));
        $this->assertSame('typed', FtpFields::resolvePassword('other', 'typed', 'typed', $this->row()));
    }

    public function testBlankKeepsTheSameUsersPassword(): void
    {
        $this->assertSame('stored', FtpFields::resolvePassword('survey', 'stored', '', $this->row()));
        // ...or one remembered from Test Setup
        $this->assertSame('remembered', FtpFields::resolvePassword('other', 'remembered', '', $this->row()));
    }

    public function testBlankDoesntSendTheStoredPasswordToAnotherLogin(): void
    {
        $this->assertSame('', FtpFields::resolvePassword('anonymous', 'stored', '', $this->row()));
        $this->assertSame('', FtpFields::resolvePassword('other', 'stored', '', $this->row()));
    }
}
