/**
 * Loading a page script into a test page (#516).
 *
 * The form helpers are page scripts wrapped in jQuery's $(function () {...}).
 * loadPage() builds a jsdom page from a small HTML fixture of the form, loads
 * jQuery from node_modules and then the script, as the browser would, so
 * the tests drive the real scripts through their events. checkFixture()
 * keeps a fixture honest: each field name and class it gives the script must
 * be in the form's PHP view too.
 */

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {JSDOM} from 'jsdom';

const WWW = fileURLToPath(new URL('../../', import.meta.url));
const JQUERY = readFileSync(`${WWW}node_modules/jquery/dist/jquery.js`, 'utf8');

/**
 * A page with *html* in its body and the page script *script* loaded and run.
 *
 * jQuery runs $(function () {...}) asynchronously even when the page has
 * loaded, so this waits for it, after the script's own.
 *
 * @param {string} html the form's fixture
 * @param {string|string[]} scripts the script's file name in app/templates/default/js, or the
 *     names of the scripts the page loads, in order (e.g. directoryFields.js before the form's)
 * @returns {Promise<{window: object, $: Function}>} the page's window and its jQuery
 */
export async function loadPage(html, scripts) {
    const dom = new JSDOM(`<!DOCTYPE html><html><body>${html}</body></html>`, {runScripts: 'outside-only'});
    dom.window.eval(JQUERY);
    for (const script of [].concat(scripts)) {
        dom.window.eval(readFileSync(`${WWW}app/templates/default/js/${script}`, 'utf8'));
    }
    await new Promise((resolve) => dom.window.jQuery(resolve));
    return {window: dom.window, $: dom.window.jQuery};
}

/**
 * The directory field cases of one kind from tests/data/directory_fields.json
 * (#630), which the PHP tests check Helpers\DirectoryFields against too.
 *
 * @param {string} kind the cases' kind, e.g. 'absolute' or 'cdtDestDir'
 * @returns {Array[]} the cases: [typed, expected], or [typed, transfer type, expected]
 */
export function directoryCases(kind) {
    return JSON.parse(readFileSync(`${WWW}tests/data/directory_fields.json`, 'utf8'))[kind];
}

/**
 * Whether the page script has hidden an element (jQuery's hide() and
 * toggle(false) set display: none; jsdom has no layout for :visible).
 *
 * @param {Function} $ the page's jQuery
 * @param {string} selector the element
 * @returns {boolean} whether it's shown
 */
export function shown($, selector) {
    const element = $(selector);
    assert.equal(element.length, 1, `one ${selector} in the fixture`);
    return element.css('display') !== 'none';
}

/**
 * Set a field's value and fire the event the script listens for.
 *
 * @param {Function} $ the page's jQuery
 * @param {string} name the field's name
 * @param {string} value the value
 * @param {string} event the event: change, input or blur
 */
export function enter($, name, value, event = 'blur') {
    const field = $(`[name=${name}]`).not('[type=radio]');
    field.val(value).trigger(event);
}

/**
 * Check a radio button and fire its change event.
 *
 * @param {Function} $ the page's jQuery
 * @param {string} name the radio buttons' name
 * @param {string} value the value to check
 */
export function choose($, name, value) {
    $(`input[name=${name}][value="${value}"]`).prop('checked', true).trigger('change');
}

/**
 * Check that the field names and classes a fixture gives a script are in
 * the form's PHP view, as quoted strings or class names. Names and classes
 * can also come from *others*: the controller (radio buttons' names are in
 * its option lists) or a helper that renders part of the form.
 *
 * @param {string} html the fixture
 * @param {string[]} views the views' file names in app/views/Config
 * @param {string[]} others other files, relative to app/, e.g. 'Helpers/DescriptionTemplates.php'
 */
export function checkFixture(html, views, others = []) {
    test('the fixture matches the form views', () => {
        const page = new JSDOM(html).window.document;
        const names = new Set([...page.querySelectorAll('[name]')].map((element) => element.getAttribute('name')));
        const classes = new Set([...page.querySelectorAll('[class]')].flatMap((element) => [...element.classList]));
        for (const view of views) {
            const source = [`views/Config/${view}`, ...others]
                .map((file) => readFileSync(`${WWW}app/${file}`, 'utf8')).join('\n');
            for (const name of names) {
                assert.match(source, new RegExp(`['"]${name}['"]`), `${name} in ${view}`);
            }
            for (const cls of classes) {
                assert.match(source, new RegExp(`class=["'][^"']*\\b${cls}\\b`), `class ${cls} in ${view}`);
            }
        }
    });
}

/**
 * A test for a known bug: it fails while the bug is there, and the test
 * passes. Once the bug is fixed, it fails, saying to make it a plain test
 * (like pytest's strict xfail).
 *
 * @param {string} name the test's name
 * @param {string} issue the bug's issue, e.g. '#123'
 * @param {Function} body the test (may be async), as it should pass once the bug is fixed
 */
export function knownBug(name, issue, body) {
    test(`${name} (known bug ${issue})`, async () => {
        let fixed = true;
        try {
            await body();
        } catch (error) {
            if (!(error instanceof assert.AssertionError)) {
                throw error;
            }
            fixed = false;
        }
        assert.ok(!fixed, `${issue} looks fixed: make "${name}" a plain test`);
    });
}
