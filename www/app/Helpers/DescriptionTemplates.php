<?php
/**
 * Description templates helper (#449).
 *
 * A collection system transfer's or extra directory's Description (#432) is
 * shown in the cruise and lowering READMEs, under the folder's heading. So
 * that descriptions are written the same way and read as part of the README,
 * a new one starts from a template with <...> prompts in a standard Markdown
 * structure (#499): a paragraph about the source (or, for an extra directory,
 * its contents), a **Files:** list with one item per file type, and an
 * optional **Sub-directories:** list. The templates are
 * CST_DESCRIPTION_TEMPLATE and EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE in
 * Config.php; a Config.php from before 2.17 gets the defaults below. This
 * helper is the one place that reads them, renders the Description field, and
 * cleans a description before it's saved.
 */

namespace Helpers;

class DescriptionTemplates
{
    /**
     * The templates used when Config.php doesn't define them.
     *
     * @var array
     */
    const DEFAULTS = array(
        'CST_DESCRIPTION_TEMPLATE' =>
            "<The instrument or acquisition system, and what it records>\n" .
            "\n" .
            "**Files:**\n" .
            "- `<file name pattern, e.g. *.raw>`: <what each file holds, and how often new ones appear>\n" .
            "\n" .
            "**Sub-directories:**\n" .
            "- `<name>/`: <what it holds>",
        'EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE' =>
            "<What's put here, and by whom or what>\n" .
            "\n" .
            "**Files:**\n" .
            "- `<file name pattern, e.g. *.pdf>`: <what each file holds>\n" .
            "\n" .
            "**Sub-directories:**\n" .
            "- `<name>/`: <what it holds>",
    );

    /**
     * The collection system transfer description template.
     *
     * @return string the template; empty if the site turned templates off
     */
    public static function collectionSystem()
    {
        return self::get('CST_DESCRIPTION_TEMPLATE');
    }

    /**
     * The extra directory description template.
     *
     * @return string the template; empty if the site turned templates off
     */
    public static function extraDirectory()
    {
        return self::get('EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE');
    }

    /**
     * Clean a submitted description before it's saved.
     *
     * - A line that's still exactly one of the template's prompt lines (a
     *   line with a <...> prompt) is removed, so an unedited template is
     *   saved as an empty description.
     * - A section label from the template (e.g. **Sub-directories:**) left
     *   with nothing under it is removed too, so an unfilled optional section
     *   disappears.
     * - Headings become bold text, since the README puts the description
     *   under a heading of its own (headings()).
     * - Runs of blank lines become one.
     *
     * Fenced code blocks are left as they are.
     *
     * @param string $description the submitted description
     * @param string $template    the template it started from
     *
     * @return string the description to save, trimmed
     */
    public static function clean($description, $template)
    {
        $prompts = array();
        $labels = array();
        foreach (explode("\n", str_replace("\r\n", "\n", (string) $template)) as $line) {
            if (preg_match('/<[^>]+>/', $line)) {
                $prompts[] = trim($line);
            } elseif (trim($line) !== '') {
                $labels[] = trim($line);
            }
        }

        $lines = array();
        foreach (explode("\n", str_replace("\r\n", "\n", (string) $description)) as $line) {
            if (!in_array(trim($line), $prompts, true)) {
                $lines[] = rtrim($line);
            }
        }

        $kept = array();
        foreach ($lines as $i => $line) {
            if (!in_array(trim($line), $labels, true) || !self::emptySection($lines, $i + 1, $labels)) {
                $kept[] = $line;
            }
        }
        return trim(implode("\n", self::headings($kept)));
    }

    /**
     * Render the Description form group: the text box and a Use template button.
     *
     * The button fills an empty text box with the template; it's left out when
     * the template is empty. An empty text box also shows the template as
     * placeholder text.
     *
     * @param string $template the template (collectionSystem() or extraDirectory())
     * @param string $value    the text box's value
     *
     * @return string the HTML
     */
    public static function formGroup($template, $value)
    {
        $html = '<div class="form-group"><label>Description</label>';
        if ($template !== '') {
            $html .= ' <button type="button" class="btn btn-default btn-xs use-description-template" data-template="'
                . htmlspecialchars($template, ENT_QUOTES, 'UTF-8') . '">Use template</button>';
        }
        $params = array('class' => 'form-control', 'rows' => '8', 'name' => 'description', 'value' => (string) $value);
        if ($template !== '') {
            // Form::textBox() doesn't escape the placeholder
            $params['placeholder'] = htmlspecialchars($template, ENT_QUOTES, 'UTF-8');
        }
        return $html . Form::textBox($params) . '</div>';
    }

    /**
     * Whether a section has nothing in it but blank lines.
     *
     * @param array $lines  the description's lines
     * @param int   $start  the index of the line after the section's label
     * @param array $labels the template's section labels
     *
     * @return bool true if no non-blank line comes before the next label or the end
     */
    private static function emptySection($lines, $start, $labels)
    {
        for ($i = $start; $i < count($lines); $i++) {
            if (in_array(trim($lines[$i]), $labels, true)) {
                return true;
            }
            if (trim($lines[$i]) !== '') {
                return false;
            }
        }
        return true;
    }

    /**
     * Turn headings into bold text and runs of blank lines into one.
     *
     * An ATX heading ("## Files") becomes "**Files**". A setext underline
     * ("===" or "---" under a line of text) gets a blank line before it, so
     * it's plain text or a horizontal rule instead of turning the line above
     * into a heading. Lines in fenced code blocks are left as they are.
     *
     * @param array $lines the description's lines
     *
     * @return array the lines
     */
    private static function headings($lines)
    {
        $out = array();
        $fence = null;
        foreach ($lines as $line) {
            if (preg_match('/^ {0,3}(`{3,}|~{3,})/', $line, $m)) {
                if ($fence === null) {
                    $fence = $m[1][0];
                } elseif ($m[1][0] === $fence) {
                    $fence = null;
                }
                $out[] = $line;
                continue;
            }
            if ($fence !== null) {
                $out[] = $line;
                continue;
            }

            $previous = end($out);
            if ($line === '') {
                if ($previous !== false && $previous !== '') {
                    $out[] = '';
                }
                continue;
            }
            if (preg_match('/^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/', $line, $m)) {
                $text = trim($m[1] ?? '');
                $line = $text === '' ? '' : '**' . $text . '**';
                if ($line === '' && ($previous === false || $previous === '')) {
                    continue;
                }
            } elseif (preg_match('/^ {0,3}(=+|-+)[ \t]*$/', $line) && $previous !== false && $previous !== '') {
                $out[] = '';
            }
            $out[] = $line;
        }
        return $out;
    }

    /**
     * A template from Config.php, or its default.
     *
     * @param string $name the constant's name
     *
     * @return string the template
     */
    private static function get($name)
    {
        return defined($name) ? (string) constant($name) : self::DEFAULTS[$name];
    }
}
