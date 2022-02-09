#!/bin/bash
/usr/local/bin/bower --allow-root install
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