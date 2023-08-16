$(function () {
    'use strict';
    
    var MAPPROXY_DIR = '/mapproxy';

    var max_values = 5;
    
    function displayLatestJSON(dataType, reversedY, inverted) {
        var reversedY = reversedY || false;
        var inverted = inverted || false;
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getLatestVisualizerDataByType/' + cruiseID + '/' + dataType;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {
                
                var placeholderID = dataType + '-placeholder',
                    placeholder = '#' + placeholderID;
                if (data.indexOf('error') > 0) {
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {

                    var scales = { x: (inverted === true) ? { type: null } : {
                        type: 'time',
                        adapters: { date: { zone: 0 } },
                        time: {
                            displayFormats: {
                                millisecond: 'HH:MM:ss.SSS',
                                second: 'HH:mm:ss',
                                minute: 'HH:mm',
                                hour: 'HH:mm',
                                day: 'LL/dd ',
                                month: 'LL/yyyy',
                                year: 'yyyy'
                            }
                        }
                    }}

                    var seriesData = { datasets: []}

                    var i = 0;
                    for (i = 0; i < data.length; i++) {
                        seriesData['datasets'].push({
                            data: data[i].data.map(elem => {
                                return { x:luxon.DateTime.fromMillis(elem[0], { zone: 'UTC'}).toISO(), y:elem[1] }
                            }),
                            label: data[i].label + ' (' + data[i].unit + ')',
                            yAxisID: data[i].label,
                            borderColor: colors[i%colors.length],
                            borderWidth: 1.5,
                            backgroundColor: colors[i%colors.length],
                            color: colors[i%colors.length]
                        });
                                
                        scales[data[i].label] = {
                            type: 'linear',
                            display: false,
                            reverse: (reversedY || data[i].label == "Depth") ? true : false,
                            position: (i%2) ? 'left' : 'right',
                            grid: {
                                drawOnChartArea: (i==0) ? true : false
                            }
                        }
                    }
                
                    var chartOptions = {
                        type: 'line',
                        options: {
                            animation: false,
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: scales,
                            radius: 0,
                            interaction: {
                                mode: 'none'
                            },
                            plugins: {
                                legend: {
                                    display: false
                                }
                            },
                            onClick: function (e) {
                                window.location.href = siteRoot + 'dataDashboard/customTab/' + subPages[dataType] + '#' + dataType;
                            }
                        },
                        data: seriesData,
                        events: {
                            click: function (e) {
                                window.location.href = siteRoot + 'dataDashboard/customTab/' + subPages[dataType] + '#' + dataType;
                            }
                        }
                    };

                    const ctx = document.getElementById(placeholderID).getContext('2d');
                    var chart = new Chart(ctx, chartOptions);
                }
            }
        });
    }
        
    function displayLatestGeoJSON(dataType) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getLatestVisualizerDataByType/' + cruiseID + '/' + dataType;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var placeholder = '#' + dataType + '-placeholder';
                if ('error' in data) {
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {
                    //Get the last coordinate from the latest trackline
                    var lastCoordinate = data[0].features[0].geometry.coordinates[data[0].features[0].geometry.coordinates.length - 1],
                        latLng = L.latLng(lastCoordinate[1], lastCoordinate[0]);
                    
                    if (lastCoordinate[0] < 0) {
                        latLng = latLng.wrap(360, 0);
                    } else {
                        latLng = latLng.wrap();
                    }
                    
                    // Add latest trackline (GeoJSON)
                    var ggaData = L.geoJson(data[0], {
                        style: { weight: 3 },
                        coordsToLatLng: function (coords) {
                            var longitude = coords[0],
                                latitude = coords[1];

                            var latlng = L.latLng(latitude, longitude);

                            if (longitude < 0) {
                                return latlng.wrap(360, 0);
                            } else {
                                return latlng.wrap();
                            }
                        }
                    }),
                        mapBounds = ggaData.getBounds();
                    
                    mapBounds.extend(latLng);

                    //Build the map
                    var mapdb = L.map(placeholder.split('#')[1], {
                        maxZoom: 13,
                        zoomControl: false,
                        dragging: false,
                        doubleClickZoom: false,
                        touchZoom: false,
                        scrollWheelZoom: false
                    }).fitBounds(mapBounds).zoomOut(1);
                    
                    mapdb.on('click', function(e) {
                        window.location.href = siteRoot + 'dataDashboard/customTab/' + subPages[dataType] + '#' + dataType;
                    });

                    //Add basemap layer
                    L.tileLayer('http://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png', {
                        attribution: '&copy <a href="http://www.openstreetmap.org/copyright", target="_blank", rel="noopener">OpenStreetMap</a>, contributors &copy; <a href="https://carto.com/about-carto/">rastertiles/voyager</a>',
                        maxZoom: 20
                    }).addTo(mapdb);
                    
                    // Add latest trackline (GeoJSON)
                    ggaData.addTo(mapdb);
                    
                    // Add marker at the last coordinate
                    var marker = L.marker(latLng).addTo(mapdb);
                    
                }
            }
        });
    }
    
    function displayLatestTMS(dataType) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getLatestVisualizerDataByType/' + cruiseID + '/' + dataType;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {
                
                var placeholder = '#' + dataType + '-placeholder';
                if ('error' in data) {
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {
                    
                    var coords = data[0]['mapBounds'].split(','),
                            southwest = L.latLng(parseFloat(coords[1]), parseFloat(coords[0])),
                            northeast = L.latLng(parseFloat(coords[3]), parseFloat(coords[2]));
                        
                    //Build Leaflet latLng object
                    var mapBounds = L.latLngBounds(southwest, northeast);
                    var latLng = mapBounds.getCenter();

                    //Build the map
                    var mapdb = L.map(placeholder.split('#')[1], {
                        maxZoom: 9,
                        zoomControl: false,
                        dragging: false,
                        doubleClickZoom: false,
                        touchZoom: false,
                        scrollWheelZoom: false
                    });
                    
                    mapdb.on('click', function(e) {
                        window.location.href = siteRoot + 'dataDashboard/customTab/' + subPages[dataType] + '#' + dataType;
                    });

                    //Add basemap layer
                    L.tileLayer('http://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png', {
                        // attribution: '&copy <a href="http://www.openstreetmap.org/copyright", target="_blank", rel="noopener">OpenStreetMap</a>, contributors &copy; <a href="https://carto.com/about-carto/">rastertiles/voyager</a>',
                        maxZoom: 20
                    }).addTo(mapdb);
                    
                    // Add latest trackline (GeoJSON)
                    L.tileLayer(location.protocol + '//' + location.host + cruiseDataDir + '/' + data[0]['tileDirectory'] + '/{z}/{x}/{y}.png', {
                        tms: true,
                        bounds:mapBounds
                    }).addTo(mapdb);
                    mapdb.fitBounds(mapBounds);
                }
            }
        });
    }

    function displayLatestData() {
        
        var i = 0;
        for (i = 0; i < geoJSONTypes.length; i++) {
            if ($('#' + geoJSONTypes[i] + '-placeholder').length) {
                displayLatestGeoJSON(geoJSONTypes[i]);
            }
        }

        for (i = 0; i < tmsTypes.length; i++) {
            if ($('#' + tmsTypes[i] + '-placeholder').length) {
                displayLatestTMS(tmsTypes[i]);
            }
        }
        for (i = 0; i < jsonTypes.length; i++) {
            if ($('#' + jsonTypes[i] + '-placeholder').length) {
        displayLatestJSON(jsonTypes[i]);
            }
        }
        for (i = 0; i < jsonReversedYTypes.length; i++) {
            if ($('#' + jsonReversedYTypes[i] + '-placeholder').length) {
                displayLatestJSON(jsonReversedYTypes[i], true, false);
            }
        }
        for (i = 0; i < jsonReversedYInvertedTypes.length; i++) {
            if ($('#' + jsonReversedYInvertedTypes[i] + '-placeholder').length) {
                displayLatestJSON(jsonReversedYInvertedTypes[i], true, true);
            }
        }
        for (i = 0; i < jsonInvertedTypes.length; i++) {
            if ($('#' + jsonInvertedTypes[i] + '-placeholder').length) {
                displayLatestJSON(jsonInvertedTypes[i], false, true);
            }
        }
    }
    
    displayLatestData();
});
