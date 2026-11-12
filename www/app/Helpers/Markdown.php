<?php
/**
 * Markdown helper (#460).
 *
 * A collection system transfer's or extra directory's Description (#432)
 * goes into the cruise and lowering READMEs as-is, so Markdown in it is
 * formatted there. This renders it the same way on OpenVDM's own pages,
 * on the server so that a printed page matches.
 *
 * Descriptions are user input: HTML in them is escaped rather than passed
 * through, and links with unsafe schemes (javascript: etc.) are dropped. A
 * single line break stays a line break, as in the READMEs (#449, #499).
 *
 * league/commonmark is a Composer package and needs PHP's mbstring
 * extension. Without either, descriptions are shown as escaped plain text,
 * and alert() says what's missing, instead of the page failing (#643).
 */

namespace Helpers;

use League\CommonMark\CommonMarkConverter;

class Markdown
{
    /**
     * The converter, made on first use.
     *
     * @var CommonMarkConverter|null
     */
    private static $converter = null;

    /**
     * What league/commonmark needs that isn't installed, once checked.
     *
     * @var string[]|null
     */
    private static $missing = null;

    /**
     * What league/commonmark needs that isn't installed (checked once).
     *
     * @return string[] the missing package or extension, each in words; empty if none
     */
    public static function missing(): array
    {
        if (self::$missing === null) {
            self::$missing = self::findMissing('class_exists', 'extension_loaded');
        }
        return self::$missing;
    }

    /**
     * What league/commonmark needs that isn't installed, from the checks given.
     *
     * @param callable $classExists     class_exists(), or a stand-in
     * @param callable $extensionLoaded extension_loaded(), or a stand-in
     *
     * @return string[] the missing package or extension, each in words; empty if none
     */
    public static function findMissing(callable $classExists, callable $extensionLoaded): array
    {
        $missing = array();
        if (!$classExists(CommonMarkConverter::class)) {
            $missing[] = 'the league/commonmark Composer package';
        }
        if (!$extensionLoaded('mbstring')) {
            $missing[] = "PHP's mbstring extension";
        }
        return $missing;
    }

    /**
     * A warning that descriptions are shown as plain text, saying what's missing.
     *
     * @return string the warning's HTML; empty when Markdown can be rendered
     */
    public static function alert(): string
    {
        $missing = self::missing();
        if (!$missing) {
            return '';
        }
        return '<div class="alert alert-warning no-print"><i class="fa fa-warning"></i> '
            . 'Descriptions are shown as plain text: ' . htmlspecialchars(implode(' and ', $missing), ENT_QUOTES, 'UTF-8')
            . (count($missing) > 1 ? " aren't" : " isn't") . ' installed. Re-run the OpenVDM installer, '
            . 'or see "PHP packages" in the 2.17.0 upgrade notes in CHANGELOG.md.</div>';
    }

    /**
     * Render Markdown text as HTML.
     *
     * @param string $text the Markdown
     *
     * @return string the HTML; empty for empty text. Escaped plain text
     *                with its line breaks kept if league/commonmark can't run
     */
    public static function render($text)
    {
        $text = str_replace("\r\n", "\n", (string) $text);
        if (trim($text) === '') {
            return '';
        }
        if (self::missing()) {
            return '<p>' . nl2br(htmlspecialchars($text, ENT_QUOTES, 'UTF-8'), false) . "</p>\n";
        }
        if (self::$converter === null) {
            self::$converter = new CommonMarkConverter(array(
                'html_input' => 'escape',
                'allow_unsafe_links' => false,
                'max_nesting_level' => 20,
                'renderer' => array('soft_break' => "<br>\n"),
            ));
        }
        return (string) self::$converter->convert($text);
    }
}
