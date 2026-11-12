<?php
/**
 * Tests for Helpers\DirectoryFields (#630): the server cleans up a transfer's
 * directory fields as the forms' directoryFields.js does. The cases are in
 * www/tests/data/directory_fields.json, which the JavaScript tests check
 * directoryFields.js against too.
 */

namespace Tests\Helpers;

use Helpers\DirectoryFields;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class DirectoryFieldsTest extends TestCase
{
    private static function cases(string $kind): array
    {
        $cases = json_decode(file_get_contents(__DIR__ . '/../data/directory_fields.json'), true)[$kind];
        return array_combine(array_map('json_encode', $cases), $cases);
    }

    public static function absoluteCases(): array
    {
        return self::cases('absolute');
    }

    public static function relativeCases(): array
    {
        return self::cases('relative');
    }

    public static function isRcloneCases(): array
    {
        return self::cases('isRclone');
    }

    public static function rcloneCases(): array
    {
        return self::cases('rclone');
    }

    public static function cdtDestDirCases(): array
    {
        return self::cases('cdtDestDir');
    }

    public static function ssdwDestDirCases(): array
    {
        return self::cases('ssdwDestDir');
    }

    #[DataProvider('absoluteCases')]
    public function testAbsolute(string $typed, string $expected): void
    {
        $this->assertSame($expected, DirectoryFields::absolute($typed));
    }

    #[DataProvider('relativeCases')]
    public function testRelative(string $typed, string $expected): void
    {
        $this->assertSame($expected, DirectoryFields::relative($typed));
    }

    #[DataProvider('isRcloneCases')]
    public function testIsRclone(string $typed, bool $expected): void
    {
        $this->assertSame($expected, DirectoryFields::isRclone($typed));
    }

    #[DataProvider('rcloneCases')]
    public function testRclone(string $typed, string $expected): void
    {
        $this->assertSame($expected, DirectoryFields::rclone($typed));
    }

    #[DataProvider('cdtDestDirCases')]
    public function testCdtDestDir(string $typed, string $transferType, string $expected): void
    {
        $this->assertSame($expected, DirectoryFields::cdtDestDir($typed, $transferType));
    }

    public function testCdtDestDirTakesAnIntegerType(): void
    {
        $this->assertSame('/mnt/usb', DirectoryFields::cdtDestDir('mnt/usb/', 1));
    }

    #[DataProvider('ssdwDestDirCases')]
    public function testSsdwDestDir(string $typed, string $expected): void
    {
        $this->assertSame($expected, DirectoryFields::ssdwDestDir($typed));
    }
}
