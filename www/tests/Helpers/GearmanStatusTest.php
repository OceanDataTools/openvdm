<?php
/**
 * Tests for Helpers\GearmanStatus (#503): which OpenVDM workers gearmand
 * has no worker process for, and the Configuration page's warning.
 * server/tests/test_gearman_worker_list.py checks WORKERS against the
 * workers' register_task() calls.
 */

namespace Tests\Helpers;

use Helpers\GearmanStatus;
use PHPUnit\Framework\TestCase;

class GearmanStatusTest extends TestCase
{
    public function testParseStatus(): void
    {
        $text = "runCollectionSystemTransfer\t2\t1\t3\r\nstopJob\t0\t0\t1\nbroken line\n.\nafter\t0\t0\t9\n";
        $this->assertSame(array('runCollectionSystemTransfer' => 3, 'stopJob' => 1), GearmanStatus::parseStatus($text));
        $this->assertSame(array(), GearmanStatus::parseStatus(''));
    }

    private function allRunning(): array
    {
        $available = array();
        foreach (GearmanStatus::WORKERS as $functions) {
            foreach ($functions as $function) {
                $available[$function] = 1;
            }
        }
        return $available;
    }

    public function testNothingMissing(): void
    {
        $this->assertSame(array(), GearmanStatus::missing($this->allRunning()));
        $this->assertSame('', GearmanStatus::alert(array()));
    }

    public function testMissingWorkers(): void
    {
        $available = $this->allRunning();
        $available['stopJob'] = 0;                  // listed with no workers
        unset($available['rebuildMD5Summary']);     // not listed: its worker never started
        $this->assertSame(array('md5_summary' => array('rebuildMD5Summary'), 'stop_job' => array('stopJob')),
                          GearmanStatus::missing($available));
    }

    public function testEveryWorkerMissingWhenNothingIsListed(): void
    {
        $this->assertSame(array_keys(GearmanStatus::WORKERS), array_keys(GearmanStatus::missing(array())));
    }

    public function testAlertListsThem(): void
    {
        $alert = GearmanStatus::alert(array('md5_summary' => array('updateMD5Summary', 'rebuildMD5Summary')));
        $this->assertStringContainsString('<li><strong>md5_summary</strong>: updateMD5Summary, rebuildMD5Summary</li>',
                                          $alert);
        $this->assertStringContainsString('supervisorctl status', $alert);
        $this->assertStringStartsWith('<div class="alert alert-danger">', $alert);
    }

    public function testAlertEscapes(): void
    {
        $alert = GearmanStatus::alert(array('<b>x</b>' => array('a&b')));
        $this->assertStringContainsString('&lt;b&gt;x&lt;/b&gt;', $alert);
        $this->assertStringContainsString('a&amp;b', $alert);
    }

    public function testAlertWhenGearmandIsUnreachable(): void
    {
        $alert = GearmanStatus::alert(null);
        $this->assertStringContainsString('Unable to reach the Gearman job server (gearmand) at 127.0.0.1:4730', $alert);
    }
}
