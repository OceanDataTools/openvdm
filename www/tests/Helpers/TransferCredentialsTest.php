<?php
/**
 * Tests for Helpers\TransferCredentials (#205): the API strips transfer
 * passwords from responses unless the request carries the worker key.
 */

namespace Tests\Helpers;

use Helpers\TransferCredentials;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class TransferCredentialsTest extends TestCase
{
    protected function tearDown(): void
    {
        unset($_SERVER['HTTP_X_WORKER_TOKEN']);
    }

    private function rows(): array
    {
        return array(
            (object) array('name' => 'SCS', 'rsyncPass' => 'r', 'smbPass' => 's', 'sshPass' => 'h', 'ftpPass' => 'f'),
            (object) array('name' => 'USB', 'smbPass' => 's2'),
        );
    }

    public function testFieldsAreEveryTransferTypesPassword(): void
    {
        $this->assertSame(array('rsyncPass', 'smbPass', 'sshPass', 'ftpPass'), TransferCredentials::FIELDS);
    }

    public function testStripRemovesThePasswords(): void
    {
        $rows = TransferCredentials::strip($this->rows());
        $this->assertSame(array('name' => 'SCS'), (array) $rows[0]);
        $this->assertSame(array('name' => 'USB'), (array) $rows[1]);
    }

    public function testWorkerRequestKeepsThePasswords(): void
    {
        $_SERVER['HTTP_X_WORKER_TOKEN'] = WORKER_API_KEY;
        $this->assertTrue(TransferCredentials::isWorkerRequest());
        $this->assertSame('r', TransferCredentials::forResponse($this->rows())[0]->rsyncPass);
    }

    public static function notWorkerTokens(): array
    {
        return array('no header' => array(null), 'empty' => array(''), 'wrong' => array('guess'),
                     'prefix' => array(substr(WORKER_API_KEY, 0, 5)));
    }

    #[DataProvider('notWorkerTokens')]
    public function testOtherRequestsGetNoPasswords(?string $token): void
    {
        if ($token !== null) {
            $_SERVER['HTTP_X_WORKER_TOKEN'] = $token;
        }
        $this->assertFalse(TransferCredentials::isWorkerRequest());
        $this->assertSame(array('name' => 'SCS'), (array) TransferCredentials::forResponse($this->rows())[0]);
    }

    public static function tokens(): array
    {
        $placeholder = TransferCredentials::PLACEHOLDER;
        return array(
            'the key' => array('a-real-key', 'a-real-key', true),
            'another token' => array('a-real-key', 'other', false),
            'no key set' => array('', '', false),
            // #605: the placeholder is public, so it's never a worker's key
            'placeholder key and token' => array($placeholder, $placeholder, false),
            'placeholder key, other token' => array($placeholder, 'a-real-key', false),
        );
    }

    #[DataProvider('tokens')]
    public function testIsWorkerToken(string $key, string $token, bool $worker): void
    {
        $this->assertSame($worker, TransferCredentials::isWorkerToken($key, $token));
    }

    public function testPlaceholderIsConfigPhpDists(): void
    {
        $this->assertStringContainsString("define('WORKER_API_KEY', '" . TransferCredentials::PLACEHOLDER . "');",
                                          file_get_contents(__DIR__ . '/../../app/Core/Config.php.dist'));
    }
}
