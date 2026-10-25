<?php
/**
 * Tests for Helpers\CruiseDates (#637): why the System Status card is
 * yellow, when the current time is outside the cruise's dates.
 */

namespace Tests\Helpers;

use Helpers\CruiseDates;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class CruiseDatesTest extends TestCase
{
    private const DATES = array('cruiseStartDate' => '2026/10/01 00:00', 'cruiseEndDate' => '2026/10/20 12:00');

    public static function withinProvider(): array
    {
        return array(
            'during the cruise' => array(self::DATES, '2026/10/10 08:30'),
            'at the start' => array(self::DATES, '2026/10/01 00:00'),
            'at the end' => array(self::DATES, '2026/10/20 12:00'),
            'no end date' => array(array('cruiseStartDate' => '2026/10/01 00:00', 'cruiseEndDate' => ''), '2030/01/01 00:00'),
            'no start date' => array(array('cruiseStartDate' => '', 'cruiseEndDate' => '2026/10/20 12:00'), '2030/01/01 00:00'),
            'no cruise config' => array(array('Error' => 'Could not find cruise config file.'), '2030/01/01 00:00'),
        );
    }

    #[DataProvider('withinProvider')]
    public function testNoWarningWithinTheDates(array $dates, string $now): void
    {
        $this->assertSame('', CruiseDates::warning($dates, $now));
    }

    public function testBeforeTheStart(): void
    {
        $warning = CruiseDates::warning(self::DATES, '2026/09/30 23:59');
        $this->assertStringStartsWith(
            "The current time (2026/09/30 23:59 UTC) is before the Cruise's start date (2026/10/01 00:00 UTC).",
            $warning
        );
        $this->assertStringContainsString('outside of the cruise start/stop times', $warning);
        $this->assertStringEndsWith('correct them with Edit Current Cruise.', $warning);
    }

    public function testAfterTheEnd(): void
    {
        $this->assertStringStartsWith(
            "The current time (2026/10/20 12:01 UTC) is after the Cruise's end date (2026/10/20 12:00 UTC).",
            CruiseDates::warning(self::DATES, '2026/10/20 12:01')
        );
    }

    public function testHeaderAndApiUseTheHelper(): void
    {
        $app = __DIR__ . '/../../app/';
        foreach (array('templates/default/header.php', 'Controllers/Api/Warehouse.php') as $file) {
            $this->assertStringContainsString('\Helpers\CruiseDates::warning(', file_get_contents($app . $file), $file);
        }
    }
}
