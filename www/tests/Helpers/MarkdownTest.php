<?php
/**
 * Tests for Helpers\Markdown (#460): descriptions rendered as on the READMEs,
 * with their HTML escaped and unsafe links dropped, and as escaped plain
 * text when league/commonmark can't run (#643).
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

    /**
     * Pretend that what's listed is missing (null: check again).
     */
    private function setMissing(?array $missing): void
    {
        (new \ReflectionProperty(Markdown::class, 'missing'))->setValue(null, $missing);
    }

    protected function tearDown(): void
    {
        $this->setMissing(null);
    }

    public function testNothingMissingHere(): void
    {
        $this->assertSame(array(), Markdown::missing());
        $this->assertSame('', Markdown::alert());
    }

    public static function requirements(): array
    {
        $package = 'the league/commonmark Composer package';
        $mbstring = "PHP's mbstring extension";
        return array('both installed' => array(true, true, array()),
                     'no package' => array(false, true, array($package)),
                     'no mbstring' => array(true, false, array($mbstring)),
                     'neither' => array(false, false, array($package, $mbstring)));
    }

    #[DataProvider('requirements')]
    public function testFindMissing(bool $package, bool $mbstring, array $expected): void
    {
        $classes = array();
        $missing = Markdown::findMissing(
            function ($class) use ($package, &$classes) { $classes[] = $class; return $package; },
            function ($extension) use ($mbstring) { return $extension === 'mbstring' ? $mbstring : true; }
        );
        $this->assertSame($expected, $missing);
        $this->assertSame(array('League\CommonMark\CommonMarkConverter'), $classes);
    }

    public function testPlainTextWithoutThePackage(): void
    {
        $this->setMissing(array('the league/commonmark Composer package'));
        $this->assertSame("<p>Raw **sonar** &lt;b&gt;files&lt;/b&gt;<br>\n- `*.raw`</p>\n",
                          Markdown::render("Raw **sonar** <b>files</b>\r\n- `*.raw`"));
        $this->assertSame('', Markdown::render(' '));
    }

    public function testAlertSaysWhatsMissing(): void
    {
        $this->setMissing(array('the league/commonmark Composer package'));
        $this->assertStringContainsString("plain text: the league/commonmark Composer package isn't installed.",
                                          Markdown::alert());
        $this->setMissing(array('the league/commonmark Composer package', "PHP's mbstring extension"));
        $this->assertStringContainsString(
            'the league/commonmark Composer package and PHP&#039;s mbstring extension aren\'t installed. Re-run the OpenVDM installer',
            Markdown::alert()
        );
    }

    public function testTheGuideShowsTheAlert(): void
    {
        $view = file_get_contents(__DIR__ . '/../../app/views/Config/fileNamingGuide.php');
        $this->assertStringContainsString('\Helpers\Markdown::alert()', $view);
    }
}
