#!/bin/bash
/usr/bin/bower --allow-root install
cd bower_components/chart.js
npm install
npm run build
cd ../chartjs-adapter-luxon
npm install
npm run build
cd ../chartjs-plugin-zoom
npm install
npm run build

cd ../../

if [[ ! -f './app/templates/default/js/chartColors.js' ]]; then
    cp ./app/templates/default/js/chartColors.js.dist ./app/templates/default/js/chartColors.js
fi

