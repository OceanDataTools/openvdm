<?php
/**
 * Tests for Helpers\FileNamingGuide (#451): a transfer's filters explained in
 * words. The example names and "never matches" warnings in
 * server/tests/data/file_naming_guide.json are checked here against the
 * guide, and by server/tests/test_file_naming_guide.py against the transfer's
 * own filters, so the guide can't say a file will be copied when it won't.
 */

namespace Tests\Helpers;

use Helpers\FileNamingGuide;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class FileNamingGuideTest extends TestCase
{
    private static function cases(): array
    {
        return json_decode(file_get_contents(__DIR__ . '/../../../server/tests/data/file_naming_guide.json'), true);
    }

    private static function context(array $overrides = array()): array
    {
        return $overrides + self::cases()['context'] + array(
            'cruiseStartDate' => '2026/10/01 00:00', 'cruiseEndDate' => '2026/10/20 00:00',
            'loweringStartDate' => '2026/10/05 08:00', 'loweringEndDate' => '');
    }

    public static function sharedPatterns(): array
    {
        $cases = array();
        foreach (self::cases()['patterns'] as $case) {
            $cases[$case['type'] . ':' . $case['pattern']] = array($case['pattern'], $case['type'], $case['example'],
                                                                   $case['never_matches']);
        }
        return $cases;
    }

    #[DataProvider('sharedPatterns')]
    public function testSharedPatterns(string $pattern, int $type, string $example, bool $neverMatches): void
    {
        $described = FileNamingGuide::describePattern($pattern, $type, self::context());
        if (!$neverMatches) {
            $this->assertSame($example, $described['example']);
            $this->assertSame('', $described['warning']);
        } else {
            $this->assertStringStartsWith('This pattern never matches', $described['warning']);
        }
    }

    public function testAlwaysSkippedFilesAreNamed(): void
    {
        // The shared file's always_skipped names, one for each, as the guide's rule writes them
        $named = array('.DS_Store', '._*', 'Thumbs.db', 'desktop.ini', '~$*', '.~lock.*#', 'lost+found',
                       '$RECYCLE.BIN', '.Trashes', '.snapshot');
        $this->assertCount(count(self::cases()['rules']['always_skipped']), $named);
        $rules = FileNamingGuide::guideFor($this->cst(), 'Local Directory', self::context())['rules'];
        foreach ($named as $name) {
            $this->assertStringContainsString($name, end($rules));
        }
    }

    public static function sentences(): array
    {
        return array(
            'any name' => array('*', array(array('text', 'any name'))),
            'ending in' => array('*.raw', array(array('text', 'any name ending in '), array('code', '.raw'))),
            'containing' => array('*{cruiseID}*', array(array('text', 'any name containing '), array('code', 'RR2601'))),
            'starting with' => array('{cruiseID}_*', array(array('text', 'starting with '), array('code', 'RR2601_'),
                                                            array('text', ', then '), array('text', 'anything after that'))),
            'pieces' => array('*/EM124_{YYYY}????.all', array(
                array('text', 'anything, then '), array('code', '/EM124_'), array('text', ', then '),
                array('text', 'a 4-digit year from 2000 to 2099'), array('text', ', then '),
                array('text', 'any 4 characters'), array('text', ', then '), array('code', '.all'))),
            'digits and sets' => array('[0-9][0-9][abc][!x]', array(
                array('text', 'starting with '), array('text', '2 digits'), array('text', ', then '),
                array('text', 'one of abc'), array('text', ', then '), array('text', 'one character other than x'))),
            'two stars are one' => array('a**b', array(array('text', 'starting with '), array('code', 'a'),
                                                       array('text', ', then '), array('text', 'anything'),
                                                       array('text', ', then '), array('code', 'b'))),
            'unclosed bracket is literal' => array('a[b', array(array('text', 'starting with '), array('code', 'a[b'))),
        );
    }

    #[DataProvider('sentences')]
    public function testSentences(string $pattern, array $sentence): void
    {
        $this->assertSame($sentence, FileNamingGuide::describePattern($pattern, FileNamingGuide::RSYNC, self::context())['sentence']);
    }

    public function testLoweringIdWithoutALowering(): void
    {
        $described = FileNamingGuide::describePattern('*{loweringID}.dat', FileNamingGuide::LOCAL,
                                                      self::context(array('loweringID' => '')));
        $this->assertSame('*{loweringID}.dat', $described['filled']);
        $this->assertSame(array('text', 'the lowering ID'), $described['sentence'][1]);
        $this->assertSame('', $described['example']);
    }

    public function testUnknownPlaceholderWarning(): void
    {
        $described = FileNamingGuide::describePattern('*{date}.dat', FileNamingGuide::LOCAL, self::context());
        $this->assertSame("{date} isn't a placeholder OpenVDM fills in, so it's matched as written.", $described['warning']);
    }

    private function cst(array $overrides = array()): object
    {
        return (object) ($overrides + array(
            'collectionSystemTransferID' => '3', 'name' => 'SCS', 'longName' => 'Underway', 'description' => null,
            'cruiseOrLowering' => '0', 'enable' => '1', 'transferType' => '1', 'sourceDir' => '/data/{cruiseID}',
            'includeFilter' => '*.raw,,*{cruiseID}.txt', 'excludeFilter' => '*bad*', 'ignoreFilter' => '',
            'useStartDate' => '0', 'staleness' => '0', 'skipEmptyFiles' => '0',
            'rsyncServer' => '', 'smbServer' => '', 'sshServer' => '', 'ftpServer' => '', 'smbPass' => 'secret'));
    }

    public function testGuideFor(): void
    {
        $guide = FileNamingGuide::guideFor($this->cst(), 'Local Directory', self::context());
        $this->assertSame(3, $guide['id']);
        $this->assertSame('', $guide['description']);
        $this->assertFalse($guide['lowering']);
        $this->assertTrue($guide['enabled']);
        $this->assertSame(array('Directory' => '/data/RR2601'), $guide['source']);
        $this->assertSame(array('*.raw', '*{cruiseID}.txt'), array_column($guide['include'], 'pattern'));
        $this->assertSame(array('*bad*'), array_column($guide['exclude'], 'pattern'));
        $this->assertSame(array(), $guide['ignore']);
        $this->assertStringNotContainsString('secret', json_encode($guide));
        $this->assertStringContainsString("full path on the OpenVDM server", $guide['rules'][0]);
    }

    public static function sources(): array
    {
        return array(
            'rsync' => array(FileNamingGuide::RSYNC, 'rsyncServer', 'Server', 'path within the source directory'),
            'SMB' => array(FileNamingGuide::SMB, 'smbServer', 'Share', 'temporary mount point'),
            'SSH' => array(FileNamingGuide::SSH, 'sshServer', 'Server', 'path within the source directory'),
            'FTP' => array(FileNamingGuide::FTP, 'ftpServer', 'Server', 'temporary mount point'),
        );
    }

    #[DataProvider('sources')]
    public function testSourceAndMatchedPath(int $type, string $field, string $label, string $matched): void
    {
        $guide = FileNamingGuide::guideFor($this->cst(array('transferType' => (string) $type, $field => 'host.example')),
                                           'type', self::context());
        $this->assertSame(array($label => 'host.example', 'Directory' => '/data/RR2601'), $guide['source']);
        $this->assertStringContainsString($matched, $guide['rules'][0]);
    }

    public function testOptionalRules(): void
    {
        $guide = FileNamingGuide::guideFor($this->cst(array('cruiseOrLowering' => '1', 'useStartDate' => '1',
                                                            'staleness' => '30', 'skipEmptyFiles' => '1')),
                                           'Local Directory', self::context());
        $rules = implode("\n", $guide['rules']);
        $this->assertTrue($guide['lowering']);
        $this->assertStringContainsString('last modified during the lowering (2026/10/05 08:00 to now, UTC)', $rules);
        $this->assertStringContainsString("hasn't changed for 30 seconds", $rules);
        $this->assertStringContainsString("Empty (0-byte) files aren't copied.", $rules);
    }

    public function testDateRuleWithoutDates(): void
    {
        $guide = FileNamingGuide::guideFor($this->cst(array('useStartDate' => '1')), 'Local Directory',
                                           self::context(array('cruiseStartDate' => '', 'cruiseEndDate' => '')));
        $this->assertStringContainsString('Only files last modified during the cruise are copied', implode("\n", $guide['rules']));
    }

    public function testPlaceholderKey(): void
    {
        $key = FileNamingGuide::placeholderKey(self::context());
        $this->assertSame(array('{cruiseID}', 'the cruise ID', 'RR2601'), $key[0]);
        $this->assertSame(array('{loweringID}', 'the lowering ID', 'DIVE07'), $key[1]);
        $this->assertSame(array('{YYYY}', 'a 4-digit year from 2000 to 2099', ''), $key[2]);
        $this->assertCount(2 + count(FileNamingGuide::DATE_PLACEHOLDERS), $key);
    }
}
