/**
 * Tests for directoryFields.js (#630): the directory field normalization the
 * transfer forms share. The cases are in tests/data/directory_fields.json,
 * which the PHP tests check Helpers\DirectoryFields against too, so the forms
 * and the server clean up a directory the same way. Each form's tests check
 * its fields give the same results on blur and on submit.
 */

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {test} from 'node:test';
import {directoryCases, loadPage} from './helpers.mjs';

const WWW = fileURLToPath(new URL('../../', import.meta.url));

const {window} = await loadPage('', 'directoryFields.js');

const FUNCTIONS = {
    absolute: 'normalizeAbsolutePath',
    relative: 'normalizeRelativePath',
    isRclone: 'isRclonePath',
    rclone: 'normalizeRclonePath',
    cdtDestDir: 'normalizeCdtDestDir',
    ssdwDestDir: 'normalizeSsdwDestDir',
};

for (const [kind, name] of Object.entries(FUNCTIONS)) {
    for (const testCase of directoryCases(kind)) {
        const args = testCase.slice(0, -1);
        const expected = testCase[testCase.length - 1];
        test(`${name}(${args.map((arg) => JSON.stringify(arg)).join(', ')}) is ${JSON.stringify(expected)}`, () => {
            assert.equal(window[name](...args), expected);
        });
    }
}

// The pages whose form helpers use these functions, and their controllers
const PAGES = [
    ['CollectionSystemTransfers.php', 'collectionSystemTransfersFormHelper'],
    ['CruiseDataTransfers.php', 'cruiseDataTransfersFormHelper'],
    ['System.php', 'SSDWFormHelper'],
];

for (const [controller, helper] of PAGES) {
    test(`${controller} loads directoryFields.js before ${helper}.js`, () => {
        const source = readFileSync(`${WWW}app/Controllers/Config/${controller}`, 'utf8');
        const lists = source.match(new RegExp(`\\$data\\['javascript'\\] = array\\([^)]*'${helper}'[^)]*\\)`, 'g'));
        assert.ok(lists, `${helper} in ${controller}`);
        for (const list of lists) {
            assert.match(list, new RegExp(`'directoryFields',[^)]*'${helper}'`), list);
        }
    });
}
