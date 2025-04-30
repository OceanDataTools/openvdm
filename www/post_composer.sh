#!/bin/bash
npm install

if [[ ! -f './app/templates/default/js/chartColors.js' ]]; then
    cp ./app/templates/default/js/chartColors.js.dist ./app/templates/default/js/chartColors.js
fi

