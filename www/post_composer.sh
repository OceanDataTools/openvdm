#!/bin/bash
# The web pages' packages only: the dev dependencies (jsdom, for the
# JavaScript tests, #516) aren't needed, or served, on a ship. Run
# npm install yourself for the tests.
npm install --omit=dev

if [[ ! -f './app/templates/default/js/chartColors.js' ]]; then
    cp ./app/templates/default/js/chartColors.js.dist ./app/templates/default/js/chartColors.js
fi

