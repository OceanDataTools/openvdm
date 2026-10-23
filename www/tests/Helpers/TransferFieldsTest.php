<?php
/**
 * Tests for Helpers\TransferFields (#243): a transfer keeps only its own
 * type's connection fields.
 */

namespace Tests\Helpers;

use Helpers\TransferFields;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class TransferFieldsTest extends TestCase
{
    private function transfer(int $type): array
    {
        return array(
            'name' => 'SCS', 'transferType' => $type, 'sourceDir' => '/data',
            'localDirIsMountPoint' => 1,
            'rsyncServer' => 'rsync.example/module', 'rsyncUser' => 'ru', 'rsyncPass' => 'rp',
            'smbServer' => '//smb/share', 'smbUser' => 'su', 'smbPass' => 'sp', 'smbDomain' => 'WG',
            'sshServer' => 'ssh.example', 'sshUser' => 'hu', 'sshUseKey' => 1, 'sshPass' => 'hp',
            'ftpServer' => 'ftp.example:2121', 'ftpUser' => 'fu', 'ftpPass' => 'fp',
        );
    }

    public static function types(): array
    {
        return array('local' => array(1), 'rsync' => array(2), 'smb' => array(3), 'ssh' => array(4), 'ftp' => array(5));
    }

    #[DataProvider('types')]
    public function testKeepsOnlyItsOwnTypesFields(int $type): void
    {
        $original = $this->transfer($type);
        $cleared = TransferFields::clearOthers($original);
        foreach (TransferFields::FIELDS as $fieldType => $fields) {
            foreach ($fields as $field => $blank) {
                $this->assertSame($fieldType === $type ? $original[$field] : $blank, $cleared[$field], $field);
            }
        }
        $this->assertSame('SCS', $cleared['name']);
        $this->assertSame('/data', $cleared['sourceDir']);
    }

    public function testObjectsStayObjects(): void
    {
        $cleared = TransferFields::clearOthers((object) $this->transfer(4));
        $this->assertIsObject($cleared);
        $this->assertSame('ssh.example', $cleared->sshServer);
        $this->assertSame('', $cleared->ftpPass);
    }

    public function testTypeAsAString(): void
    {
        // A transfer type posted from a form is a string
        $cleared = TransferFields::clearOthers(array('transferType' => '5') + $this->transfer(5));
        $this->assertSame('fp', $cleared['ftpPass']);
        $this->assertSame('', $cleared['smbPass']);
    }

    public function testNoTypeBlanksEverything(): void
    {
        $transfer = $this->transfer(1);
        unset($transfer['transferType']);
        $cleared = TransferFields::clearOthers($transfer);
        $this->assertSame(0, $cleared['localDirIsMountPoint']);
        $this->assertSame('', $cleared['rsyncPass']);
    }

    public function testEveryPasswordFieldIsATypesField(): void
    {
        // A new transfer type's password must be blanked here and stripped by TransferCredentials
        $fields = array_merge(...array_map('array_keys', array_values(TransferFields::FIELDS)));
        foreach (\Helpers\TransferCredentials::FIELDS as $password) {
            $this->assertContains($password, $fields);
        }
    }
}
