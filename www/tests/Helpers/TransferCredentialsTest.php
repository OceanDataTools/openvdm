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
}
