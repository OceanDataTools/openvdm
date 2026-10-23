/**
 * Tests for collectionSystemTransfersFormHelper.js (#516): the collection
 * system transfer form's fields for each transfer type (#226, #227), the
 * staleness and remove-source fields, the Use template button (#449), and
 * how it normalizes what's typed.
 */

import assert from 'node:assert/strict';
import {test} from 'node:test';
import {checkFixture, choose, enter, knownBug, loadPage, shown} from './helpers.mjs';

const TEMPLATE = '<The instrument>\n\n**Files:**';

const FORM = `<form>
  <input name="name"><input name="longName">
  <div class="form-group"><label>Description</label>
    <button type="button" class="use-description-template" data-template="${TEMPLATE}">Use template</button>
    <textarea name="description"></textarea></div>
  <input name="destDir">
  <input type="radio" name="staleness" value="0" checked><input type="radio" name="staleness" value="5">
  <div class="form-group staleness"><input name="customStaleness"></div>
  <div class="form-group removeSource">
    <input type="radio" name="removeSourceFiles" value="0" checked><input type="radio" name="removeSourceFiles" value="1">
  </div>
  <select name="transferType"><option value=""></option><option value="1">Local</option><option value="2">Rsync</option>
    <option value="3">SMB</option><option value="4">SSH</option><option value="5">FTP</option></select>
  <input name="sourceDir">
  <div class="form-group localDir"><input type="radio" name="localDirIsMountPoint" value="0" checked></div>
  <div class="form-group rsyncServer"><input name="rsyncServer"><input name="rsyncUser"><input type="password" name="rsyncPass"></div>
  <div class="form-group smbShare"><input name="smbServer"><input name="smbDomain"><input name="smbUser">
    <input type="password" name="smbPass"></div>
  <div class="form-group sshServer"><input name="sshServer"><input name="sshUser">
    <input type="radio" name="sshUseKey" value="0" checked><input type="radio" name="sshUseKey" value="1">
    <input type="password" name="sshPass"></div>
  <div class="form-group ftpServer"><input name="ftpServer"><input name="ftpUser"><input type="password" name="ftpPass"></div>
  <input type="submit" name="inlineTest">
</form>`;

const TYPES = {1: 'localDir', 2: 'rsyncServer', 3: 'smbShare', 4: 'sshServer', 5: 'ftpServer'};

checkFixture(FORM, ['addCollectionSystemTransfers.php', 'editCollectionSystemTransfers.php'],
             ['Helpers/DescriptionTemplates.php', 'Controllers/Config/CollectionSystemTransfers.php']);

function page() {
    return loadPage(FORM, 'collectionSystemTransfersFormHelper.js');
}

test('no transfer type shows no type fields', async () => {
    const {$} = await page();
    for (const cls of Object.values(TYPES)) {
        assert.equal(shown($, `.form-group.${cls}`), false, cls);
    }
    assert.equal($('[name=sourceDir]').attr('placeholder'), '');
});

for (const [type, cls] of Object.entries(TYPES)) {
    test(`transfer type ${type} shows only its fields (#226)`, async () => {
        const {$} = await page();
        enter($, 'transferType', type, 'change');
        for (const other of Object.values(TYPES)) {
            assert.equal(shown($, `.form-group.${other}`), other === cls, other);
        }
        assert.match($('[name=sourceDir]').attr('placeholder'), /^e\.g\. \//);
    });
}

test('staleness and remove source: hidden without staleness, and for rsync', async () => {
    const {$} = await page();
    assert.equal(shown($, '.staleness'), false);
    assert.equal(shown($, '.removeSource'), false);
    choose($, 'staleness', '5');
    assert.equal(shown($, '.staleness'), true);
    assert.equal(shown($, '.removeSource'), true);
    enter($, 'transferType', '2', 'change');
    assert.equal(shown($, '.removeSource'), false, 'rsync sources keep their files');
    enter($, 'transferType', '4', 'change');
    assert.equal(shown($, '.removeSource'), true);
});

test('an SSH key disables and clears the password', async () => {
    const {$} = await page();
    enter($, 'sshPass', 'secret', 'input');
    choose($, 'sshUseKey', '1');
    assert.equal($('[name=sshPass]').prop('disabled'), true);
    assert.equal($('[name=sshPass]').val(), '');
    choose($, 'sshUseKey', '0');
    assert.equal($('[name=sshPass]').prop('disabled'), false);
});

test('Use template fills an empty description, and is only enabled while it is empty (#449)', async () => {
    const {$} = await page();
    const button = $('.use-description-template');
    assert.equal(button.prop('disabled'), false);
    button.trigger('click');
    assert.equal($('[name=description]').val(), TEMPLATE);
    assert.equal(button.prop('disabled'), true);
    enter($, 'description', '  ', 'input');
    assert.equal(button.prop('disabled'), false);
    enter($, 'description', 'Seapath', 'input');
    button.prop('disabled', false).trigger('click');
    assert.equal($('[name=description]').val(), 'Seapath', "doesn't replace a description");
});

const NORMALIZED = [
    ['rsyncServer', ' rsync://host\\module/ ', 'host/module'],
    ['smbServer', '\\\\server\\share\\', '//server/share'],
    ['smbServer', 'server/share', '//server/share'],
    ['sshServer', 'ssh://host.example/home/survey', 'host.example'],
    ['ftpServer', 'ftp://ftp.example:2121/data', 'ftp.example:2121'],
    ['sourceDir', 'C:\\data\\xbt\\', '/data/xbt'],
    ['sourceDir', 'data/xbt', '/data/xbt'],
    ['sourceDir', '/', '/'],
    ['destDir', '\\XBT\\raw\\', 'XBT/raw'],
    ['name', '  XBT  ', 'XBT'],
    ['smbUser', ' survey ', 'survey'],
];

for (const [name, typed, expected] of NORMALIZED) {
    test(`${name}: "${typed}" becomes "${expected}" on blur`, async () => {
        const {$} = await page();
        enter($, name, typed);
        assert.equal($(`[name=${name}]`).val(), expected);
    });
}

test('submit trims every field and normalizes the chosen type\'s server', async () => {
    const {$} = await page();
    enter($, 'transferType', '3', 'change');
    $('[name=smbServer]').val('server\\share');
    $('[name=sshServer]').val('ssh://other/path');    // another type's: only trimmed
    $('[name=rsyncPass]').val(' pw ');
    $('[name=sourceDir]').val('data');
    $('form').trigger('submit');
    assert.equal($('[name=smbServer]').val(), '//server/share');
    assert.equal($('[name=sshServer]').val(), 'ssh://other/path');
    assert.equal($('[name=rsyncPass]').val(), 'pw');
    assert.equal($('[name=sourceDir]').val(), '/data');
});

test('Enter in a field runs Test Setup instead of submitting', async () => {
    const {$, window} = await page();
    let tested = 0;
    $('[name=inlineTest]').on('click', (event) => { tested++; event.preventDefault(); });
    const event = new window.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true});
    $('[name=name]')[0].dispatchEvent(event);
    assert.equal(tested, 1);
    assert.equal(event.defaultPrevented, true);
});

knownBug('a source directory of "//" is the root, as the CDT form keeps it (#247)', '#608', async () => {
    const {$} = await page();
    enter($, 'sourceDir', '//');
    assert.equal($('[name=sourceDir]').val(), '/');
});
