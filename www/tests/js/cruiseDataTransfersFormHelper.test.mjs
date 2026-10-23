/**
 * Tests for cruiseDataTransfersFormHelper.js (#516): the cruise data transfer
 * form's fields for each transfer type, the rclone "remote:path" destination,
 * the mount point field and its warning for /mnt, /media and /net (#464), the
 * destination directory rules for each type (#247), and the exclusion lists'
 * Select all boxes.
 */

import assert from 'node:assert/strict';
import {test} from 'node:test';
import {checkFixture, choose, enter, loadPage, shown} from './helpers.mjs';

const FORM = `<form>
  <input name="name"><input name="longName">
  <select name="transferType"><option value=""></option><option value="1">Local</option><option value="2">Rsync</option>
    <option value="3">SMB</option><option value="4">SSH</option><option value="5">FTP</option></select>
  <input name="destDir">
  <div class="form-group localDir">
    <input type="radio" name="localDirIsMountPoint" value="0" checked><input type="radio" name="localDirIsMountPoint" value="1">
    <p class="mountpointWarning" style="display: none;">warning</p></div>
  <div class="form-group rsyncServer"><input name="rsyncServer"><input name="rsyncUser"><input type="password" name="rsyncPass"></div>
  <div class="form-group smbShare"><input name="smbServer"><input name="smbDomain"><input name="smbUser">
    <input type="password" name="smbPass"></div>
  <div class="form-group sshServer"><input name="sshServer"><input name="sshUser">
    <input type="radio" name="sshUseKey" value="0" checked><input type="radio" name="sshUseKey" value="1">
    <input type="password" name="sshPass"></div>
  <div class="form-group ftpServer"><input name="ftpServer"><input name="ftpUser"><input type="password" name="ftpPass"></div>
  <input type="checkbox" id="selectAllCS">
  <div id="excludedCollectionSystems"><input type="checkbox" value="1"><input type="checkbox" value="2"></div>
  <input type="checkbox" id="selectAllED">
  <div id="excludedExtraDirectories"><input type="checkbox" value="1"></div>
  <input type="submit" name="inlineTest">
</form>`;

const TYPES = {1: 'localDir', 2: 'rsyncServer', 3: 'smbShare', 4: 'sshServer', 5: 'ftpServer'};

checkFixture(FORM, ['addCruiseDataTransfers.php', 'editCruiseDataTransfers.php'],
             ['Controllers/Config/CruiseDataTransfers.php']);

function page() {
    return loadPage(FORM, 'cruiseDataTransfersFormHelper.js');
}

for (const [type, cls] of Object.entries(TYPES)) {
    test(`transfer type ${type} shows only its fields`, async () => {
        const {$} = await page();
        enter($, 'transferType', type, 'change');
        for (const other of Object.values(TYPES)) {
            assert.equal(shown($, `.form-group.${other}`), other === cls, other);
        }
        assert.match($('[name=destDir]').attr('placeholder'), /^e\.g\. /);
    });
}

test('the mount point field is for local directories, not rclone remotes', async () => {
    const {$} = await page();
    enter($, 'transferType', '1', 'change');
    enter($, 'destDir', '/mnt/usb');
    assert.equal(shown($, '.form-group.localDir'), true);
    enter($, 'destDir', 'gdrive:/cruises');
    assert.equal(shown($, '.form-group.localDir'), false);
    assert.equal($('[name=destDir]').val(), 'gdrive:/cruises');
});

const WARNING_CASES = [
    ['/mnt/usb', '1', '0', true], ['/media/backup', '1', '0', true], ['/net/nas/cruises', '1', '0', true],
    ['/mnt/usb', '1', '1', false],          // marked as a mount point
    ['/mnt', '1', '0', false],              // the folder itself, not a mount in it
    ['/data/backup', '1', '0', false], ['/mntdata/x', '1', '0', false],
    ['remote:/mnt/x', '1', '0', false],     // an rclone remote
    ['/mnt/usb', '4', '0', false],          // not a local directory
];

for (const [destDir, type, mountPoint, warned] of WARNING_CASES) {
    test(`the mount warning for ${destDir} (type ${type}, mount point ${mountPoint}): ${warned} (#464)`, async () => {
        const {$} = await page();
        enter($, 'transferType', type, 'change');
        choose($, 'localDirIsMountPoint', mountPoint);
        enter($, 'destDir', destDir, 'input');
        assert.equal(shown($, '.mountpointWarning'), warned);
    });
}

test('the warning follows the mount point choice', async () => {
    const {$} = await page();
    enter($, 'transferType', '1', 'change');
    enter($, 'destDir', '/media/backup', 'input');
    assert.equal(shown($, '.mountpointWarning'), true);
    choose($, 'localDirIsMountPoint', '1');
    assert.equal(shown($, '.mountpointWarning'), false);
});

const DEST_DIRS = [
    ['', ' backup\\cruises\\ ', ' backup\\cruises\\ '.trim().replace(/\\/g, '/')],   // no type yet: not guessed
    ['1', 'mnt/backup/', '/mnt/backup'],
    ['1', '//', '/'],
    ['1', '/remote:path', 'remote:path'],
    ['2', '/backups/', 'backups'],
    ['2', '/', '/'],
    ['3', '\\backups\\', 'backups'],
    ['3', '//', '/'],
    ['4', 'data/cruises/', '/data/cruises'],
    ['4', '//', '/'],
    ['5', 'data', '/data'],
];

for (const [type, typed, expected] of DEST_DIRS) {
    test(`type ${type || 'none'}: destination "${typed}" becomes "${expected}" (#247)`, async () => {
        const {$} = await page();
        enter($, 'transferType', type, 'change');
        enter($, 'destDir', typed);
        assert.equal($('[name=destDir]').val(), expected);
    });
}

test('servers are normalized as on the collection system form', async () => {
    const {$} = await page();
    enter($, 'rsyncServer', 'rsync://host/module/');
    enter($, 'smbServer', '\\\\nas\\share');
    enter($, 'sshServer', 'ssh://host/path');
    enter($, 'ftpServer', 'ftp://host:21/x');
    assert.deepEqual(['rsyncServer', 'smbServer', 'sshServer', 'ftpServer'].map((name) => $(`[name=${name}]`).val()),
                     ['host/module', '//nas/share', 'host', 'host:21']);
});

test('an SSH key disables and clears the password', async () => {
    const {$} = await page();
    enter($, 'sshPass', 'secret', 'input');
    choose($, 'sshUseKey', '1');
    assert.equal($('[name=sshPass]').prop('disabled'), true);
    assert.equal($('[name=sshPass]').val(), '');
});

test('Select all checks and unchecks every box, and follows them', async () => {
    const {$} = await page();
    $('#selectAllCS').prop('checked', true).trigger('change');
    assert.equal($('#excludedCollectionSystems :checked').length, 2);
    $('#excludedCollectionSystems input').first().prop('checked', false).trigger('change');
    assert.equal($('#selectAllCS').prop('checked'), false);
    $('#excludedCollectionSystems input').first().prop('checked', true).trigger('change');
    assert.equal($('#selectAllCS').prop('checked'), true);
    $('#selectAllED').prop('checked', true).trigger('change');
    assert.equal($('#excludedExtraDirectories :checked').length, 1);
    $('#excludedExtraDirectories input').prop('checked', false).trigger('change');
    assert.equal($('#selectAllED').prop('checked'), false);
    $('#excludedExtraDirectories input').prop('checked', true).trigger('change');
    assert.equal($('#selectAllED').prop('checked'), true);
});

test('submit trims and normalizes the chosen type\'s fields', async () => {
    const {$} = await page();
    enter($, 'transferType', '5', 'change');
    $('[name=ftpServer]').val(' ftp://host/x ');
    $('[name=destDir]').val('data/');
    $('form').trigger('submit');
    assert.equal($('[name=ftpServer]').val(), 'host');
    assert.equal($('[name=destDir]').val(), '/data');
});

test('Enter in a field runs Test Setup', async () => {
    const {$, window} = await page();
    let tested = 0;
    $('[name=inlineTest]').on('click', (event) => { tested++; event.preventDefault(); });
    $('[name=destDir]')[0].dispatchEvent(new window.KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
    assert.equal(tested, 1);
});
