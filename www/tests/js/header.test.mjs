/**
 * Tests for header.js's System Status card (#637): its refresh from
 * api/warehouse/getSystemStatus keeps the card yellow while the time is
 * outside the cruise's dates, as header.php renders it, and shows the
 * question mark whose popup says why.
 */

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {loadPage, shown} from './helpers.mjs';

const CARD = `<a href="/config/disableSystem">
  <div id="systemStatusPanel" class="panel panel-green"><div class="panel-heading">
    <div id="systemStatus" class="huge">On</div>
    <div class="text-right"><i id="systemStatusWarning" class="fa fa-question-circle" data-toggle="tooltip" title=""
      style="display: none;"></i> System Status</div>
  </div></div></a>`;

const WARNING = 'The current time (2026/10/25 12:00 UTC) is after the Cruise\'s end date (2026/10/20 00:00 UTC).';

test('the fixture matches header.php', () => {
    const header = readFileSync(new URL('../../app/templates/default/header.php', import.meta.url), 'utf8');
    for (const id of ['systemStatusPanel', 'systemStatus', 'systemStatusWarning']) {
        assert.match(header, new RegExp(`id="${id}"`), id);
    }
});

/**
 * The page with header.js, the API answering getSystemStatus with each of
 * *responses* in turn (one per refresh), and Bootstrap's tooltip stubbed to
 * do what header.js relies on: fixTitle moves the title to data-original-title.
 */
async function page(responses) {
    const refreshes = [];
    const tooltips = [];
    const result = await loadPage(CARD, 'header.js', (window) => {
        const $ = window.jQuery;
        window.siteRoot = '/';
        window.Cookies = {get: () => null, set: () => {}, remove: () => {}};
        // Keep the cards' 5 s refreshes to run by hand; jQuery's own timers run as usual
        const setTimeout = window.setTimeout;
        window.setTimeout = (fn, ms) => (ms === 5000 ? refreshes.push(fn) : setTimeout(fn, ms));
        $.getJSON = (url, done) => {
            if (url === '/api/warehouse/getSystemStatus') {
                done(responses.shift(), 'success');
            }
        };
        $.fn.tooltip = function (action) {
            tooltips.push(action);
            return this.each(function () {
                if (action === undefined || action === 'fixTitle') {
                    $(this).attr('data-original-title', $(this).attr('title') || '').attr('title', '');
                }
            });
        };
    });
    // Run the next refresh of the System Status card (the other cards never answer)
    const refresh = () => refreshes.shift()();
    return {...result, refresh, tooltips};
}

function state($) {
    return {
        panel: $('#systemStatusPanel').attr('class'),
        status: $('#systemStatus').text(),
        icon: shown($, '#systemStatusWarning'),
        popup: $('#systemStatusWarning').attr('data-original-title'),
    };
}

test('On within the cruise\'s dates: green, no question mark', async () => {
    const {$} = await page([{systemStatus: 'On'}]);
    assert.deepEqual(state($), {panel: 'panel panel-green', status: 'On', icon: false, popup: ''});
});

test('On outside the cruise\'s dates: yellow, with the question mark and the reason (#637)', async () => {
    const {$} = await page([{systemStatus: 'On', warning: WARNING}]);
    assert.deepEqual(state($), {panel: 'panel panel-yellow', status: 'On', icon: true, popup: WARNING});
});

test('the card follows the dates and the status across refreshes', async () => {
    const {$, refresh} = await page([
        {systemStatus: 'On', warning: WARNING}, {systemStatus: 'On'}, {systemStatus: 'On', warning: WARNING},
        {systemStatus: 'Off'},
    ]);
    assert.equal(state($).panel, 'panel panel-yellow');
    refresh();
    assert.deepEqual(state($), {panel: 'panel panel-green', status: 'On', icon: false, popup: ''});
    refresh();
    assert.deepEqual(state($), {panel: 'panel panel-yellow', status: 'On', icon: true, popup: WARNING});
    refresh();
    assert.deepEqual(state($), {panel: 'panel panel-red', status: 'Off', icon: false, popup: ''});
});

test('the popup is hidden when the reason goes away', async () => {
    const {refresh, tooltips} = await page([{systemStatus: 'On', warning: WARNING}, {systemStatus: 'On'}]);
    assert.ok(!tooltips.includes('hide'));
    refresh();
    assert.ok(tooltips.includes('hide'));
});

test('a click on the question mark shows the popup, not Enable/Disable System', async () => {
    const {$, window} = await page([{systemStatus: 'On', warning: WARNING}]);
    const click = new window.MouseEvent('click', {bubbles: true, cancelable: true});
    $('#systemStatusWarning')[0].dispatchEvent(click);
    assert.equal(click.defaultPrevented, true);
});
