<?php
/**
 * Tests for Helpers\DescriptionTemplates (#449, #499): the description
 * templates, the Description form group, and cleaning a description before
 * it's saved.
 */

namespace Tests\Helpers;

use Helpers\DescriptionTemplates;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\TestCase;

class DescriptionTemplatesTest extends TestCase
{
    private const TEMPLATE = DescriptionTemplates::DEFAULTS['CST_DESCRIPTION_TEMPLATE'];

    public function testDefaultsWithoutConfig(): void
    {
        // The test bootstrap doesn't define the (multi-line) templates, as a pre-2.17 Config.php doesn't
        $this->assertSame(self::TEMPLATE, DescriptionTemplates::collectionSystem());
        $this->assertSame(DescriptionTemplates::DEFAULTS['EXTRA_DIRECTORY_DESCRIPTION_TEMPLATE'],
                          DescriptionTemplates::extraDirectory());
    }

    public function testTemplatesFollowTheStandardStructure(): void
    {
        // A source (or contents) paragraph, a **Files:** list and an optional **Sub-directories:** list (#499)
        foreach (DescriptionTemplates::DEFAULTS as $template) {
            $this->assertMatchesRegularExpression('/^<[^>]+>\n\n\*\*Files:\*\*\n- .+\n\n\*\*Sub-directories:\*\*\n- .+$/',
                                                  $template);
        }
    }

    public static function cleaned(): array
    {
        $template = self::TEMPLATE;
        return array(
            'unedited template' => array($template, ''),
            'filled in, optional section left' => array(
                "Seapath 380 navigation\n\n**Files:**\n- `*.raw`: positions, one file an hour\n\n**Sub-directories:**\n"
                . "- `<name>/`: <what it holds>",
                "Seapath 380 navigation\n\n**Files:**\n- `*.raw`: positions, one file an hour"),
            'everything filled in' => array(
                "Seapath\n\n**Files:**\n- `*.raw`: positions\n\n**Sub-directories:**\n- `logs/`: system logs",
                "Seapath\n\n**Files:**\n- `*.raw`: positions\n\n**Sub-directories:**\n- `logs/`: system logs"),
            'prompt line edited is kept' => array(
                "<The instrument or acquisition system> is a Seapath",
                "<The instrument or acquisition system> is a Seapath"),
            'CRLF and trailing spaces' => array("Seapath  \r\n\r\n**Files:**\r\n- `*.raw`: x\r\n", "Seapath\n\n**Files:**\n- `*.raw`: x"),
            'blank line runs' => array("one\n\n\n\ntwo\n\n", "one\n\ntwo"),
            'ATX headings become bold' => array("# Seapath\n## Files ##\nx\n###", "**Seapath**\n**Files**\nx"),
            'setext underline' => array("Seapath\n===\nnav\n---", "Seapath\n\n===\nnav\n\n---"),
            'fenced code kept' => array("```\n# not a heading\n\n\n```\n~~~\n## nor this\n~~~", "```\n# not a heading\n\n\n```\n~~~\n## nor this\n~~~"),
            'empty' => array('', ''),
        );
    }

    #[DataProvider('cleaned')]
    public function testClean(string $description, string $expected): void
    {
        $this->assertSame($expected, DescriptionTemplates::clean($description, self::TEMPLATE));
    }

    public function testCleanWithoutTemplate(): void
    {
        // With templates turned off, nothing is a prompt or a label
        $this->assertSame("**Files:**\n\n<keep this>", DescriptionTemplates::clean("**Files:**\n\n<keep this>", ''));
    }

    public function testLabelWithContentAfterAnEmptySection(): void
    {
        $description = "Seapath\n\n**Files:**\n\n**Sub-directories:**\n- `logs/`: system logs";
        $this->assertSame("Seapath\n\n**Sub-directories:**\n- `logs/`: system logs",
                          DescriptionTemplates::clean($description, self::TEMPLATE));
    }

    public function testFormGroup(): void
    {
        $html = DescriptionTemplates::formGroup("<Source & files>\n**Files:**", 'a "quoted" <b>value</b>');
        $this->assertStringContainsString('class="btn btn-default btn-xs use-description-template"', $html);
        $this->assertStringContainsString('data-template="&lt;Source &amp; files&gt;' . "\n" . '**Files:**"', $html);
        $this->assertStringContainsString("placeholder='&lt;Source &amp; files&gt;", $html);
        $this->assertStringContainsString('a &quot;quoted&quot; &lt;b&gt;value&lt;/b&gt;</textarea>', $html);
        $this->assertStringContainsString("name='description'", $html);
    }

    public function testFormGroupWithoutTemplate(): void
    {
        $html = DescriptionTemplates::formGroup('', '');
        $this->assertStringNotContainsString('use-description-template', $html);
        $this->assertStringNotContainsString('placeholder', $html);
    }
}
