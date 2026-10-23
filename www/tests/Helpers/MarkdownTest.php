<?php
/**
 * Tests for Helpers\Markdown (#460): descriptions rendered as on the READMEs,
 * with their HTML escaped and unsafe links dropped.
 */

namespace Tests\Helpers;

use Helpers\Markdown;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class MarkdownTest extends TestCase
{
    public function testRenders(): void
    {
        $html = Markdown::render("Raw **sonar** files\n\n**Files:**\n- `*.raw`: pings");
        $this->assertSame("<p>Raw <strong>sonar</strong> files</p>\n<p><strong>Files:</strong></p>\n"
                          . "<ul>\n<li><code>*.raw</code>: pings</li>\n</ul>\n", $html);
    }

    public function testSingleLineBreakStays(): void
    {
        $this->assertSame("<p>first<br>\nsecond</p>\n", Markdown::render("first\r\nsecond"));
    }

    public static function emptyTexts(): array
    {
        return array('empty' => array(''), 'blank' => array(" \n\t"), 'null' => array(null));
    }

    #[DataProvider('emptyTexts')]
    public function testEmpty(?string $text): void
    {
        $this->assertSame('', Markdown::render($text));
    }

    public function testHtmlIsEscaped(): void
    {
        $html = Markdown::render('<script>alert(1)</script> <img src=x onerror=alert(1)>');
        $this->assertStringNotContainsString('<script', $html);
        $this->assertStringNotContainsString('<img', $html);
        $this->assertStringContainsString('&lt;script&gt;', $html);
    }

    public static function unsafeLinks(): array
    {
        return array('javascript' => array('[x](javascript:alert(1))'), 'vbscript' => array('[x](vbscript:msgbox)'),
                     'data' => array('[x](data:text/html;base64,PHNjcmlwdD4=)'), 'file' => array('[x](file:///etc/passwd)'));
    }

    #[DataProvider('unsafeLinks')]
    public function testUnsafeLinksAreDropped(string $markdown): void
    {
        $html = Markdown::render($markdown);
        $this->assertDoesNotMatchRegularExpression('/href="(javascript|vbscript|data|file):/i', $html);
    }

    public function testSafeLinksStay(): void
    {
        $this->assertStringContainsString('<a href="https://www.seabird.com/">Sea-Bird</a>',
                                          Markdown::render('[Sea-Bird](https://www.seabird.com/)'));
    }
}
