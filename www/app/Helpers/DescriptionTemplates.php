<?php
/**
 * Description templates helper (#449).
 *
 * A collection system transfer's or extra directory's Description (#432) is
 * shown in the cruise and lowering READMEs. So that descriptions are written
 * the same way, a new one starts from a template of labelled lines with
 * <...> prompts. The templates are CST_DESCRIPTION_TEMPLATE and
 * EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE in Config.php; a Config.php from
 * before 2.17 gets the defaults below. This helper is the one place that
 * reads them, renders the Description field, and drops the prompts a user
 * left unfilled before a description is saved.
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
            "Source: <instrument or acquisition system, and what it records>\n" .
            "Files: <file types and extensions, naming, how often new files appear>\n" .
            "Sub-directories: <each sub-directory and what it holds, or \"none\">",
        'EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE' =>
            "Contents: <what's put here, and by whom or what>\n" .
            "Files: <file types and extensions>\n" .
            "Sub-directories: <each sub-directory and what it holds, or \"none\">",
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
     * Drop the template's unfilled prompt lines from a submitted description.
     *
     * A line that's still exactly one of the template's prompt lines (a line
     * with a <...> prompt) is removed, so an unedited template is saved as an
     * empty description and a partly filled one keeps only the filled lines.
     *
     * @param string $description the submitted description
     * @param string $template    the template it started from
     *
     * @return string the description to save, trimmed
     */
    public static function clean($description, $template)
    {
        $description = str_replace("\r\n", "\n", (string) $description);
        $prompts = array();
        foreach (explode("\n", str_replace("\r\n", "\n", (string) $template)) as $line) {
            if (preg_match('/<[^>]+>/', $line)) {
                $prompts[] = trim($line);
            }
        }

        $kept = array();
        foreach (explode("\n", $description) as $line) {
            if (!in_array(trim($line), $prompts, true)) {
                $kept[] = rtrim($line);
            }
        }
        return trim(implode("\n", $kept));
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
        $params = array('class' => 'form-control', 'rows' => '4', 'name' => 'description', 'value' => (string) $value);
        if ($template !== '') {
            // Form::textBox() doesn't escape the placeholder
            $params['placeholder'] = htmlspecialchars($template, ENT_QUOTES, 'UTF-8');
        }
        return $html . Form::textBox($params) . '</div>';
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
