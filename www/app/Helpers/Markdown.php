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
     * Render Markdown text as HTML.
     *
     * @param string $text the Markdown
     *
     * @return string the HTML; empty for empty text
     */
    public static function render($text)
    {
        $text = str_replace("\r\n", "\n", (string) $text);
        if (trim($text) === '') {
            return '';
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
