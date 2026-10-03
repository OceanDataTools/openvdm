$(function () {
    'use strict';


    var greenIcon = null;
    var redIcon = null;


    var mapObjects = [],
        chartObjects = [];

    // Track colors: the chart palette from chartColors.js, which the page only
    // loads when its jsArray includes "charts". Without it, tracks keep
    // Leaflet's default style.
    var trackColors = (typeof colors !== 'undefined') ? colors : null;

    // All tracks of a data type share a color, chosen by the data type's
    // position in the map's file list, so colors don't change when tracks are
    // toggled. Track checkbox values are "<dataType>/<dd_json>".
    function geoJSONColor(mapObject, dataObjectJsonName) {
        if (!trackColors) {
            return null;
        }
        var dataTypes = [];
        $('#' + mapObject['objectListID']).find('.geoJSON-checkbox').each(function () {
            var dataType = $(this).val().split('/')[0];
            if (dataTypes.indexOf(dataType) === -1) {
                dataTypes.push(dataType);
            }
        });
        var index = dataTypes.indexOf(dataObjectJsonName.split('/')[0]);
        return trackColors[Math.max(index, 0) % trackColors.length];
    }

    function geoJSONStyle(mapObject, dataObjectJsonName) {
        var style = { weight: 3 };
        var color = geoJSONColor(mapObject, dataObjectJsonName);
        if (color) {
            style.color = color;
        }
        return style;
    }

    function updateBounds(mapObject) {
        if (mapObject['map']) {
            // Center the map based on the bounds
            var mapBoundsArray = [];
            for (var item in mapObject['mapBounds'] ){
                mapBoundsArray.push( mapObject['mapBounds'][ item ] );
            }

            if (mapBoundsArray.length > 0) {
                mapObject['map'].fitBounds(mapBoundsArray);
            }
        }
    }

    function initMapObject(placeholderID, objectListID) {

        var mapObject = [];

        greenIcon = new L.Icon({
            iconUrl: '/node_modules/@vectorial1024/leaflet-color-markers/img/marker-icon-green.png',
            shadowUrl: '/node_modules/@vectorial1024/leaflet-color-markers/img/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        });

        redIcon = new L.Icon({
            iconUrl: '/node_modules/@vectorial1024/leaflet-color-markers/img/marker-icon-red.png',
            shadowUrl: '/node_modules/@vectorial1024/leaflet-color-markers/img/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        });

        //Build mapObject object
        mapObject['placeholderID'] = placeholderID;
        mapObject['objectListID'] = objectListID;
        mapObject['markers'] = [];
        mapObject['geoJSONLayers'] = [];
        mapObject['tmsLayers'] = [];
        mapObject['mapBounds'] = [];

        //Build the map
        mapObject['map'] = L.map(mapObject['placeholderID'], {
            //maxZoom: 13,
            fullscreenControl: true,
        }).setView(L.latLng(0, 0), 2);

        //Add basemap layers, default to OpenStreetMap (see mapBaseLayers.js)
        var baseLayers = openvdmBaseLayers();

        baseLayers["OpenStreetMap"].addTo(mapObject['map']);
        baseLayers["OpenStreetMap"].bringToBack();

        L.control.layers(baseLayers, openvdmOverlayLayers()).addTo(mapObject['map']);

        L.easyPrint({
            title: 'Export current map view',
            tileLayer: baseLayers,
            position: 'topright',
            hideControlContainer: true,
            exportOnly: true,
            filename: 'openvdm_map_export'
            // sizeModes: ['A4Portrait', 'A4Landscape']
        }).addTo(mapObject['map']);

        return mapObject;
    }

    function initChartObject(placeholderID, objectListID, dataType) {

        var chartObject = [];

        //Build chartObject object
        chartObject['placeholderID'] = placeholderID;
        chartObject['objectListID'] = objectListID;

        var tempArray = chartObject['placeholderID'].split("_");
        tempArray.pop();

        chartObject['dataType'] = tempArray.join('_');
        chartObject['expanded'] = false; //chartHeight;
        chartObject['chart'] = null;
        chartObject['heights'] = [200, 500]; //normal, expanded

        return chartObject;
    }

    function mapChecked(mapObject) {
        $( '#' + mapObject['objectListID']).find(':checkbox:checked').each(function() {
            if ($(this).hasClass("lp-checkbox")) {
                addLatestPositionToMap(mapObject, $(this).val());
            } else if ($(this).hasClass("se-checkbox")) {
                addStartEndPositionsToMap(mapObject, $(this).val());
            } else if ($(this).hasClass("geoJSON-checkbox")) {
                addGeoJSONToMap(mapObject, $(this).val());
            } else if ($(this).hasClass("tms-checkbox")) {
                addTMSToMap(mapObject, $(this).val());
            }
        });
    }

    function chartChecked(chartObject) {
        $( '#' + chartObject['objectListID']).find(':radio:checked').each(function() {
            drawChart(chartObject, $(this));
        });
    }

    //Draw the chart for a data file's radio button, by its visType
    function drawChart(chartObject, radio) {
        if (radio.hasClass( "json-profile-radio" )) {
            updateProfileChart(chartObject, radio.attr('name'), radio.val(), radio.data('profile'));
        } else if (radio.hasClass( "json-reversedY-radio" )) {
            updateChart(chartObject, radio.val(), true, false);
        } else if (radio.hasClass( "json-reversedY-inverted-radio" )) {
            updateChart(chartObject, radio.val(), true, true);
        } else if (radio.hasClass( "json-inverted-radio" )) {
            updateChart(chartObject, radio.val(), false, true);
        } else {
            updateChart(chartObject, radio.val());
        }
    }

    function addLatestPositionToMap(mapObject, dataType) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getLatestVisualizerDataByType/' + cruiseID + '/' + dataType;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {

                if ('error' in data) {
                    $('#' + mapObject['placeholderID']).html('<strong>Error: ' + data.error + '</strong>');
                } else {
                    //Get the last position of the latest feature (a track or a point, #292)
                    var positions = openvdmFeaturePositions(data[0].features[data[0].features.length - 1]);
                    if (positions.length === 0) {
                        return;
                    }
                    var lastCoordinate = positions[positions.length - 1];
                    var latestPosition = L.latLng(lastCoordinate[1], lastCoordinate[0]);

                    if (lastCoordinate[0] < 0) {
                        latestPosition = latestPosition.wrap(360, 0);
                    } else {
                        latestPosition = latestPosition.wrap();
                    }

                    var bounds = new L.LatLngBounds([latestPosition]);
                    mapObject['mapBounds']['LatestPosition-' + dataType] = bounds;

                    // Add marker at the last coordinate
                    mapObject['markers']['LatestPosition-' + dataType] = L.marker(latestPosition);
                    mapObject['markers']['LatestPosition-' + dataType].addTo(mapObject['map']);

                    updateBounds(mapObject);
                }
            }
        });
    }

    function addStartEndPositionsToMap(mapObject, dataType) {
        var loweringID = $('#lowering_sel').val();
        var getDashboardDataFilesURL = siteRoot + 'api/dashboardData/getDataObjectsByType/' + cruiseID + '/' + dataType;
        $.getJSON(getDashboardDataFilesURL, function (data, status) {
            if (status === 'success' && data !== null) {

               var files = data.filter(function(object) {
                   return object['raw_data'].includes(loweringID)
               })

               var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + dataType + '/' + files[0]['dd_json'];
               $.getJSON(getVisualizerDataURL, function (data, status) {
                    if (status === 'success' && data !== null) {

                        if ('error' in data) {
                            $('#' + mapObject['placeholderID']).html('<strong>Error: ' + data.error + '</strong>');
                        } else {

                            var latestFeature = data[0].features[data[0].features.length - 1];

                            //A data type of map points (e.g. cast positions) has no track to
                            //mark the ends of: drop its Start/End Positions checkbox instead (#322)
                            if (latestFeature && latestFeature.geometry && /Point$/.test(latestFeature.geometry.type)) {
                                $('#' + mapObject['objectListID']).find('.se-checkbox').filter(function () {
                                    return this.value === dataType;
                                }).closest('div').remove();
                                return;
                            }

                            //Get the first and last positions of the latest feature (a track or a point, #292)
                            var positions = openvdmFeaturePositions(latestFeature);
                            if (positions.length === 0) {
                                return;
                            }
                            var firstCoordinate = positions[0];
                            var startPosition = L.latLng(firstCoordinate[1], firstCoordinate[0]);

                            if (firstCoordinate[0] < 0) {
                                startPosition = startPosition.wrap(360, 0);
                            } else {
                                startPosition = startPosition.wrap();
                            }

                            var lastCoordinate = positions[positions.length - 1];
                            var endPosition = L.latLng(lastCoordinate[1], lastCoordinate[0]);

                            if (lastCoordinate[0] < 0) {
                                endPosition = endPosition.wrap(360, 0);
                            } else {
                                endPosition = endPosition.wrap();
                            }

                            var bounds = new L.LatLngBounds([startPosition, endPosition]);
                            mapObject['mapBounds']['StartEndPositions-' + dataType] = bounds;

                            // Add marker at the last coordinate
                            mapObject['markers']['StartPosition-' + dataType] = L.marker(startPosition, {icon: greenIcon});
                            mapObject['markers']['StartPosition-' + dataType].addTo(mapObject['map']);

                            mapObject['markers']['EndPosition-' + dataType] = L.marker(endPosition, {icon: redIcon});
                            mapObject['markers']['EndPosition-' + dataType].addTo(mapObject['map']);

                            updateBounds(mapObject);
                        }
                    }
                });
            }
        });
    }

    function removeStartEndPositionsFromMap(mapObject, dataType) {
        mapObject['map'].removeLayer(mapObject['markers']['StartPosition-' + dataType]);
        mapObject['map'].removeLayer(mapObject['markers']['EndPosition-' + dataType]);

        //remove the bounds and re-center/re-zoom the map
        delete mapObject['markers']['StartPosition-' + dataType];
        delete mapObject['markers']['EndPosition-' + dataType];
        delete mapObject['mapBounds']['StartEndPositions-' + dataType]

        updateBounds(mapObject);
    }

    function removeLatestPositionFromMap(mapObject, dataType) {
        mapObject['map'].removeLayer(mapObject['markers']['LatestPosition-' + dataType]);

        //remove the bounds and re-center/re-zoom the map
        delete mapObject['markers']['LatestPosition-' + dataType];
        delete mapObject['mapBounds']['LatestPosition-' + dataType]
        updateBounds(mapObject);
    }

    function addGeoJSONToMap(mapObject, dataObjectJsonName) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + dataObjectJsonName;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var placeholder = '#' + mapObject['placeholderID'];
                if ('error' in data) {
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {
                    // Build the layer
                    //mapObject['geoJSONLayers'][dataObjectJsonName] = L.timeDimension.layer.geoJson(data[0], {
                    mapObject['geoJSONLayers'][dataObjectJsonName] = L.geoJson(data[0], {
                        style: geoJSONStyle(mapObject, dataObjectJsonName),
                        pointToLayer: openvdmPointMarker(geoJSONColor(mapObject, dataObjectJsonName)),
                        onEachFeature: openvdmFeaturePopup,
                        //udpateTimeDimension: true,
                        addLastPoint: true,
                        waitForReady: true,
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
                    });

                    // Calculate the bounds of the layer
                    mapObject['mapBounds'][dataObjectJsonName] = mapObject['geoJSONLayers'][dataObjectJsonName].getBounds();

                    // Add the layer to the map
                    mapObject['geoJSONLayers'][dataObjectJsonName].addTo(mapObject['map']);

                    updateBounds(mapObject);
                }
            }
        });
    }

    function removeGeoJSONFromMap(mapObject, dataObjectJsonName) {
        mapObject['map'].removeLayer(mapObject['geoJSONLayers'][dataObjectJsonName]);
        delete mapObject['geoJSONLayers'][dataObjectJsonName];

        //remove the bounds and re-center/re-zoom the map
        delete mapObject['mapBounds'][dataObjectJsonName];

        updateBounds(mapObject);
    }

    function addTMSToMap(mapObject, tmsObjectJsonName) {
        var getDataObjectFileURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + tmsObjectJsonName;
        $.getJSON(getDataObjectFileURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var placeholder = '#' + mapObject['placeholderID'];
                if ('error' in data){
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {

                    // Calculate the bounds of the layer
                    var coords = data[0]['mapBounds'].split(','),
                        southwest = L.latLng(parseFloat(coords[1]), parseFloat(coords[0])),
                        northeast = L.latLng(parseFloat(coords[3]), parseFloat(coords[2]));

                    // Build the layer: pre-rendered tiles or a TiTiler GeoTIFF (#298)
                    mapObject['tmsLayers'][tmsObjectJsonName] = openvdmTileLayer(data[0], cruiseDataDir, { zIndex: 10 });
                    if (!mapObject['tmsLayers'][tmsObjectJsonName]) {
                        delete mapObject['tmsLayers'][tmsObjectJsonName];
                        return;
                    }

                    if (parseFloat(coords[0]) < 0) {
                        southwest = southwest.wrap(360, 0);
                    } else {
                        southwest = southwest.wrap();
                    }

                    if (parseFloat(coords[2]) < 0) {
                        northeast = northeast.wrap(360, 0);
                    } else {
                        northeast = northeast.wrap();
                    }

                    mapObject['mapBounds'][tmsObjectJsonName] = L.latLngBounds(southwest, northeast);

                    // Add the layer to the map
                    mapObject['tmsLayers'][tmsObjectJsonName].addTo(mapObject['map']);

                    updateBounds(mapObject);
                }
            }
        });
    }

    function removeTMSFromMap(mapObject, tmsObjectJsonName) {

        //remove the layer
        mapObject['map'].removeLayer(mapObject['tmsLayers'][tmsObjectJsonName]);
        delete mapObject['tmsLayers'][tmsObjectJsonName];

        //remove the bounds and re-center/re-zoom the map
        delete mapObject['mapBounds'][tmsObjectJsonName];

        updateBounds(mapObject);
    }

    //Draw a depth profile (json-profile, #274). The data type comes from the
    //data file's radio button, so the placeholder id needn't be the data type.
    function updateProfileChart(chartObject, dataType, dataObjectJsonName, profileOptions) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + dataType + '/' + dataObjectJsonName;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var placeholder = '#' + chartObject['placeholderID'];
                var errorID = chartObject['placeholderID'] + '_error';
                var profile = openvdmProfileChartConfig(data, profileOptions);
                $('#' + errorID).remove();
                if ('error' in profile) {
                    // A canvas doesn't show text, so the error goes next to it
                    if (chartObject['chart'] !== null) {
                        chartObject['chart'].destroy();
                        chartObject['chart'] = null;
                    }
                    $(placeholder).hide().after($('<div>').attr('id', errorID).append($('<strong>').text('Error: ' + profile.error)));
                } else {
                    $(placeholder).show();

                    //Zoom and pan the depth axis
                    profile.config.options.plugins.zoom = {
                        limits: {
                            y: {min: 'original', max: 'original'},
                        },
                        zoom: {
                            wheel: {
                                enabled: true,
                            },
                            drag: {
                                modifierKey: 'shift',
                                enabled: true,
                            },
                            mode: 'y',
                            onZoomComplete({chart}) { showZoomResetBtn(chart, placeholder) }
                        },
                        pan: {
                            enabled: true,
                            mode: 'y',
                            onPanComplete({chart}) { showZoomResetBtn(chart, placeholder) }
                        },
                    };

                    const ctx = document.getElementById(chartObject['placeholderID']).getContext('2d');

                    if (chartObject['chart'] !== null) {
                        chartObject['chart'].destroy();
                        $( placeholder.replace('_placeholder', '') + '_zoom-reset-btn').addClass('hidden');
                    }

                    // Size the canvas before drawing. destroy() puts back the canvas's style from
                    // when the chart was made; a canvas that shrinks, even briefly, pulls the page
                    // up when it's scrolled to the bottom (#302)
                    chartObject['heights'] = [400, 800];
                    $(placeholder).css({height: chartObject['heights'][chartObject['expanded'] ? 1 : 0]});
                    chartObject['chart'] = new Chart(ctx, profile.config);
                }
            }
        });
    }

    function updateChart(chartObject, dataObjectJsonName, reversedY, inverted) {
        reversedY = reversedY || false;
        inverted = inverted || false;
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + chartObject.dataType + '/' + dataObjectJsonName;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {

                var placeholder = '#' + chartObject['placeholderID'];
                if ('error' in data){
                    $(placeholder).html('<strong>Error: ' + data.error + '</strong>');
                } else {

                    var scales = { x: {
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
                        });

                        scales[data[i].label] = {
			    ticks: {
			        color: colors[i%colors.length],
			    },
		            type: 'linear',
                            display: true,
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
                                mode: 'index'
                            },
                            plugins: {
                                legend: {
                                    position: 'bottom',
                                    onClick: function(event, legendItem) {
                                        //get the index of the clicked legend
                                        var index = legendItem.datasetIndex;

                                        //toggle chosen dataset's visibility
                                        chartObject['chart'].data.datasets[index].hidden =
                                            !chartObject['chart'].data.datasets[index].hidden;

                                        //toggle the related labels' visibility
                                        chartObject['chart'].options.scales[chartObject['chart'].data.datasets[index].yAxisID].display =
                                            !chartObject['chart'].options.scales[chartObject['chart'].data.datasets[index].yAxisID].display

                                        chartObject['chart'].update();
                                    }
                                },
                                zoom: {
                                    limits: {
                                        x: {min: 'original', max: 'original', minRange: 60 * 1000},
                                    },
                                    zoom: {
                                        wheel: {
                                            enabled: true,
                                        },
                                        drag: {
                                            modifierKey: 'shift',
                                            enabled: true,
                                        },
                                        mode: 'x',
                                        onZoomComplete({chart}) { showZoomResetBtn(chart, placeholder) }
                                    },
                                    pan: {
                                        enabled: true,
                                        mode: 'x',
                                        onPanComplete({chart}) { showZoomResetBtn(chart, placeholder) }
                                    },
                                }
                            },
                        },
                        data: seriesData
                    };

                    if (inverted) {
                        openvdmInvertTimeChart(chartOptions);
                    }

                    const ctx = document.getElementById(chartObject['placeholderID']).getContext('2d');

                    if (chartObject['chart'] !== null) {
                        chartObject['chart'].destroy();
                        $( placeholder.replace('_placeholder', '') + '_zoom-reset-btn').addClass('hidden');
                    }

                    // Size the canvas before drawing. destroy() puts back the canvas's style from
                    // when the chart was made; a canvas that shrinks, even briefly, pulls the page
                    // up when it's scrolled to the bottom (#302)
                    chartObject['heights'] = inverted ? [400, 800] : [200, 500];
                    $('#' + chartObject['placeholderID']).css({height: chartObject['heights'][chartObject['expanded'] ? 1 : 0]});
                    chartObject['chart'] = new Chart(ctx, chartOptions);
                }
            }
        });
    }

    function showZoomResetBtn(chart, placeholder) {

        if( chart.isZoomedOrPanned() ) {
            $( placeholder.replace('_placeholder', '') + '_zoom-reset-btn').removeClass('hidden');
        }
        else {
            $( placeholder.replace('_placeholder', '') + '_zoom-reset-btn').addClass('hidden');
        }
    }

    //Initialize the mapObjects
    $( '.map' ).each(function( index ) {
        var mapPlaceholderID = $( this ).attr('id');
        var tempArray = mapPlaceholderID.split("_");
        tempArray.pop();
        var objectListPlaceholderID =  tempArray.join('_') + '_objectList-placeholder';
        mapObjects.push(initMapObject(mapPlaceholderID, objectListPlaceholderID));
    });

    //Show each data type's track color to the right of its title. Each data
    //type is a row in the map's file list: a <strong> title, then its checkboxes.
    if (trackColors) {
        $.each(mapObjects, function (i) {
            $('#' + mapObjects[i]['objectListID']).find('div.row').each(function () {
                var checkbox = $(this).find('.geoJSON-checkbox').first();
                if (checkbox.length > 0) {
                    $(this).find('strong').first().after('<span class="track-swatch" style="display:inline-block; width:10px; height:10px; margin-left:6px; vertical-align:middle; background-color:' +
                        geoJSONColor(mapObjects[i], checkbox.val()) + '"></span>');
                }
            });
        });
    }

    //Initialize the chartObjects
    $( '.chart' ).each(function( index ) {
        var chartPlaceholderID = $( this ).attr('id');
        var tempArray = chartPlaceholderID.split("_");
        tempArray.pop();
        var objectListPlaceholderID =  tempArray.join('_') + '_objectList-placeholder';
        chartObjects.push(initChartObject(chartPlaceholderID, objectListPlaceholderID));
    });

    //build the maps
    for(var i = 0; i < mapObjects.length; i++) {
        mapChecked(mapObjects[i]);
    }

    //build the charts
    for(i = 0; i < chartObjects.length; i++) {
        chartChecked(chartObjects[i]);
    }

    //Check for updates
    $.each(mapObjects, function(i) {
        $( '#' + mapObjects[i]['objectListID']).find(':checkbox:checked').change(function() {
            if ($(this).is(":checked")) {
                if ($(this).hasClass("se-checkbox")) {
                    addStartEndPositionsToMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("lp-checkbox")) {
                    addLatestPositionToMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("geoJSON-checkbox")) {
                    addGeoJSONToMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("tms-checkbox")) {
                    addTMSToMap(mapObjects[i], $(this).val());
                }
            } else {
                if ($(this).hasClass("se-checkbox")) {
                    removeStartEndPositionsFromMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("lp-checkbox")) {
                    removeLatestPositionFromMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("geoJSON-checkbox")) {
                    removeGeoJSONFromMap(mapObjects[i], $(this).val());
                } else if ($(this).hasClass("tms-checkbox")) {
                    removeTMSFromMap(mapObjects[i], $(this).val());
                }
            }
        });

        $( '#' + mapObjects[i]['objectListID']).find('.clearAll').click(function() {
            var row = $(this).closest("div.row")
            $.each(row.find(':checkbox'), function () {
                if ($(this).prop('checked')) {
                    $(this).prop('checked', false); // Unchecks it
                    $(this).trigger('change');
                }
            });
        });

        $( '#' + mapObjects[i]['objectListID']).find('.selectAll').click(function() {
            var row = $(this).closest("div.row")
            $.each(row.find(':checkbox'), function () {
                if (!$(this).prop('checked')) {
                    $(this).prop('checked', true); // Unchecks it
                    $(this).trigger('change');
                }
            });
        });

    });

    //Check for updates
    $.each(chartObjects, function(i) {
        $( '#' + chartObjects[i]['objectListID']).find(':radio').change(function() {
            drawChart(chartObjects[i], $(this));
        });

        $( '#' + chartObjects[i]['dataType'] + '_expand-btn').click(function() {
            chartObjects[i]['expanded'] = !chartObjects[i]['expanded'];
            $('#' + chartObjects[i]['placeholderID']).css({height: chartObjects[i]['heights'][chartObjects[i]['expanded'] ? 1 : 0]});
            $(this).removeClass(chartObjects[i]['expanded'] ? 'fa-expand' : 'fa-compress');
            $(this).addClass(chartObjects[i]['expanded'] ? 'fa-compress' : 'fa-expand');
        });

        $( '#' + chartObjects[i]['dataType'] + '_zoom-reset-btn').click(function() {
            chartObjects[i]['chart'].resetZoom();
            $(this).addClass('hidden');
        });
    });
});
