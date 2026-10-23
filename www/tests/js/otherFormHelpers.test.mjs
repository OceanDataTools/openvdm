/**
 * Tests for the smaller form helpers (#516): extraDirectoriesFormHelper.js
 * (the destination directory and the Use template button, #449),
 * SSDWFormHelper.js (the shoreside data warehouse's SSH or rclone
 * destination), and cruiseIDFormHelper.js and loweringIDFormHelper.js
 * (choosing an existing cruise or lowering, or editing the current one).
 */

import assert from 'node:assert/strict';
import {describe, test} from 'node:test';
import {checkFixture, choose, enter, knownBug, loadPage} from './helpers.mjs';

describe('extraDirectoriesFormHelper.js', () => {
    const TEMPLATE = "<What's put here>\n\n**Files:**";
    const FORM = `<form><input name="name"><input name="longName">
      <button type="button" class="use-description-template" data-template="${TEMPLATE}">Use template</button>
      <textarea name="description"></textarea><input name="destDir"></form>`;

    checkFixture(FORM, ['addExtraDirectories.php', 'editExtraDirectories.php'], ['Helpers/DescriptionTemplates.php']);

    const page = () => loadPage(FORM, 'extraDirectoriesFormHelper.js');

    test('the destination directory is relative to the cruise, with forward slashes', async () => {
        const {$} = await page();
        enter($, 'destDir', ' \\Products\\CTD_Plots\\ ');
        assert.equal($('[name=destDir]').val(), 'Products/CTD_Plots');
    });

    test('Use template fills an empty description (#449)', async () => {
        const {$} = await page();
        $('.use-description-template').trigger('click');
        assert.equal($('[name=description]').val(), TEMPLATE);
        assert.equal($('.use-description-template').prop('disabled'), true);
    });

    test('a page without a description (required extra directories) still works', async () => {
        const {$} = await loadPage('<form><input name="destDir"></form>', 'extraDirectoriesFormHelper.js');
        enter($, 'destDir', '/Tracklines/');
        assert.equal($('[name=destDir]').val(), 'Tracklines');
    });

    test('submit trims and normalizes', async () => {
        const {$} = await page();
        $('[name=name]').val(' Docs ');
        $('[name=destDir]').val('/Docs/');
        $('form').trigger('submit');
        assert.equal($('[name=name]').val(), 'Docs');
        assert.equal($('[name=destDir]').val(), 'Docs');
    });
});

describe('SSDWFormHelper.js', () => {
    const FORM = `<form><input name="sshServer"><input name="sshUser">
      <input type="radio" name="sshUseKey" value="0" checked><input type="radio" name="sshUseKey" value="1">
      <input type="password" name="sshPass"><input name="destDir"></form>`;

    checkFixture(FORM, ['editShoresideDataWarehouse.php'], ['Controllers/Config/System.php']);

    const page = () => loadPage(FORM, 'SSDWFormHelper.js');
    const disabled = ($) => ['sshServer', 'sshUser', 'sshPass'].map((name) => $(`[name=${name}]`).prop('disabled'));

    test('an rclone remote disables the SSH fields; a path enables them again', async () => {
        const {$} = await page();
        enter($, 'destDir', '/gdrive:/ssdw');
        assert.equal($('[name=destDir]').val(), 'gdrive:/ssdw');
        assert.deepEqual(disabled($), [true, true, true]);
        assert.equal($('[name=sshUseKey]').first().prop('disabled'), true);
        enter($, 'destDir', 'data/ssdw/');
        assert.equal($('[name=destDir]').val(), '/data/ssdw');
        assert.deepEqual(disabled($), [false, false, false]);
    });

    test('an SSH key disables the password, unless the destination is an rclone remote', async () => {
        const {$} = await page();
        choose($, 'sshUseKey', '1');
        assert.deepEqual(disabled($), [false, false, true]);
        enter($, 'destDir', 'remote:x');
        choose($, 'sshUseKey', '0');
        assert.equal($('[name=sshPass]').prop('disabled'), true, 'still disabled for the remote');
    });

    test('the server is a host name only', async () => {
        const {$} = await page();
        enter($, 'sshServer', 'ssh://ssdw.example/home');
        enter($, 'sshUser', ' survey ');
        assert.equal($('[name=sshServer]').val(), 'ssdw.example');
        assert.equal($('[name=sshUser]').val(), 'survey');
    });

    test('submit re-enables the fields (but not the password) so they are posted', async () => {
        const {$} = await page();
        enter($, 'destDir', 'remote:x');
        $('form').trigger('submit');
        assert.deepEqual(disabled($), [false, false, true]);
        assert.equal($('[name=destDir]').val(), 'remote:x');
    });

    knownBug('a destination of "//" is the root (#247)', '#608', async () => {
        const {$} = await page();
        enter($, 'destDir', '//');
        assert.equal($('[name=destDir]').val(), '/');
    });
});

describe('cruiseIDFormHelper.js', () => {
    const FIELDS = ['cruiseName', 'cruiseStartDate', 'cruiseEndDate', 'cruiseStartPort', 'cruiseEndPort', 'cruisePI',
                    'cruiseLocation'];
    const FORM = `<form><select name="cruiseID"><option>RR2601</option><option>RR2602</option></select>
      ${FIELDS.map((name) => `<input name="${name}" id="${name}">`).join('')}<textarea name="cruiseDescription"></textarea></form>`;

    checkFixture(FORM, ['editCruise.php']);

    const page = () => loadPage(FORM, 'cruiseIDFormHelper.js');

    test("choosing another cruise disables editing the current one's details", async () => {
        const {$} = await page();
        enter($, 'cruiseID', 'RR2602', 'change');
        for (const name of [...FIELDS, 'cruiseDescription']) {
            assert.equal($(`[name=${name}]`).prop('disabled'), true, name);
        }
    });

    for (const name of [...FIELDS, 'cruiseDescription']) {
        test(`editing ${name} disables choosing another cruise`, async () => {
            const {$} = await page();
            enter($, name, 'x', 'input');
            assert.equal($('[name=cruiseID]').prop('disabled'), true);
        });
    }

    test('the date pickers count as editing', async () => {
        const {$} = await page();
        $('#cruiseEndDate').trigger('dp.change');
        assert.equal($('[name=cruiseID]').prop('disabled'), true);
    });
});

describe('loweringIDFormHelper.js', () => {
    const FORM = `<form><select name="loweringID"><option>DIVE01</option><option>DIVE02</option></select>
      <input name="loweringStartDate" id="loweringStartDate"><input name="loweringEndDate" id="loweringEndDate"></form>`;

    checkFixture(FORM, ['editLowering.php']);

    const page = () => loadPage(FORM, 'loweringIDFormHelper.js');

    test("choosing another lowering disables editing the current one's dates", async () => {
        const {$} = await page();
        enter($, 'loweringID', 'DIVE02', 'change');
        assert.equal($('[name=loweringStartDate]').prop('disabled'), true);
        assert.equal($('[name=loweringEndDate]').prop('disabled'), true);
    });

    for (const [event, target] of [['input', 'loweringStartDate'], ['input', 'loweringEndDate'],
                                   ['dp.change', 'loweringStartDate'], ['dp.change', 'loweringEndDate']]) {
        test(`${event} on ${target} disables choosing another lowering`, async () => {
            const {$} = await page();
            $(`#${target}`).trigger(event);
            assert.equal($('[name=loweringID]').prop('disabled'), true);
        });
    }
});
