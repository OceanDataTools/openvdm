<?php
/**
 * Tests for Helpers\PendingPasswords (#119): a password typed before Test
 * Setup is remembered in the session, so a later Update still applies it.
 */

namespace Tests\Helpers;

use Helpers\PendingPasswords;
use PHPUnit\Framework\TestCase;

class PendingPasswordsTest extends TestCase
{
    protected function setUp(): void
    {
        $_SESSION = array();
    }

    private function row(): object
    {
        return (object) array('rsyncPass' => '', 'smbPass' => 'stored-smb', 'sshPass' => 'stored-ssh', 'ftpPass' => '');
    }

    public function testResolveOrder(): void
    {
        // Posted, then remembered, then stored
        PendingPasswords::resolve('cst', 3, array('sshPass' => 'remembered'), $this->row(), true);
        $resolved = PendingPasswords::resolve('cst', 3, array('smbPass' => 'posted'), $this->row());
        $this->assertSame(array('rsyncPass' => '', 'smbPass' => 'posted', 'sshPass' => 'remembered', 'ftpPass' => ''),
                          $resolved);
    }

    public function testOnlyTestSetupRemembers(): void
    {
        PendingPasswords::resolve('cst', 3, array('sshPass' => 'typed'), $this->row());
        $this->assertSame('stored-ssh', PendingPasswords::resolve('cst', 3, array(), $this->row())['sshPass']);
    }

    public function testFlagsDontExposeValues(): void
    {
        PendingPasswords::resolve('cdt', '7', array('ftpPass' => 'secret'), $this->row(), true);
        $flags = PendingPasswords::flags('cdt', 7);
        $this->assertSame(array('rsyncPass' => false, 'smbPass' => false, 'sshPass' => false, 'ftpPass' => true), $flags);
        $this->assertNotContains('secret', $flags);
    }

    public function testRecordsAreSeparate(): void
    {
        PendingPasswords::resolve('cst', 3, array('sshPass' => 'cst3'), $this->row(), true);
        $this->assertFalse(PendingPasswords::flags('cst', 4)['sshPass']);
        $this->assertFalse(PendingPasswords::flags('cdt', 3)['sshPass']);
        $this->assertSame('stored-ssh', PendingPasswords::resolve('cdt', 3, array(), $this->row())['sshPass']);
    }

    public function testClear(): void
    {
        PendingPasswords::resolve('cst', 3, array('sshPass' => 'typed'), $this->row(), true);
        PendingPasswords::clear('cst', 3);
        $this->assertFalse(PendingPasswords::flags('cst', 3)['sshPass']);
        $this->assertSame(array(), $_SESSION);
        PendingPasswords::clear('cst', 3);   // nothing to clear
        $this->assertSame(array(), $_SESSION);
    }

    public function testSessionHoldingSomethingElse(): void
    {
        $_SESSION[SESSION_PREFIX . 'pendingPasswords_cst_3'] = 'not an array';
        $this->assertFalse(PendingPasswords::flags('cst', 3)['smbPass']);
        $this->assertSame('stored-smb', PendingPasswords::resolve('cst', 3, array(), $this->row())['smbPass']);
    }
}
