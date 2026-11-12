<?php
/**
 * Tests for Helpers\Terms (#684): what the install calls cruises and
 * lowerings, as Config.php names them.
 */

namespace Tests\Helpers;

use Helpers\Terms;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class TermsTest extends TestCase
{
    public function testConfigNames(): void
    {
        // The test bootstrap declares Config.php.dist's values
        $this->assertSame(array('cruise' => 'Cruise', 'cruises' => 'Cruises',
                                'lowering' => 'Lowering', 'lowerings' => 'Lowerings'), Terms::all());
        $this->assertSame('cruise', Terms::cruise(true));
        $this->assertSame('lowerings', Terms::lowerings(true));
    }

    public static function lowered(): array
    {
        return array(
            'one word' => array('Voyage', 'voyage'),
            'two words' => array('Research Expedition', 'research expedition'),
            'acronym kept' => array('ROV Dive', 'ROV dive'),
            'hyphenated' => array('Sea-Trial', 'sea-trial'),
            'single capital letter lowered' => array('A Dive', 'a dive'),
            'non-ASCII' => array('Ékspedition', 'ékspedition'),
        );
    }

    #[DataProvider('lowered')]
    public function testLower(string $name, string $expected): void
    {
        $this->assertSame($expected, Terms::lower($name));
    }
}
