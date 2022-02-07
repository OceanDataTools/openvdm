$(function () {
    'use strict';
    
    var MAPPROXY_DIR = '/mapproxy';
    
    const colors = ['#337ab7', '#5cb85c', '#d9534f', '#f0ad4e', '#606060']

    var greenIcon = null;
    var redIcon = null;    
    
    var chartHeight = 200;

    var mapObjects = [],
        chartObjects = [];
    
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
            iconUrl: '/bower_components/leaflet-color-markers/img/marker-icon-green.png',
            shadowUrl: '/bower_components/leaflet/dist/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        });

        redIcon = new L.Icon({
            iconUrl: '/bower_components/leaflet-color-markers/img/marker-icon-red.png',
            shadowUrl: '/bower_components/leaflet/dist/images/marker-shadow.png',
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

        //Add basemap layer, use ESRI Oceans Base Layer
        //var worldOceanBase = L.esri.basemapLayer('Oceans'),
        //    worldOceanReference = L.esri.basemapLayer('OceansLabels'),
        //    gmrtBase = L.tileLayer.wms('http://gmrt.marine-geo.org/cgi-bin/mapserv?map=/public/mgg/web/gmrt.marine-geo.org/htdocs/services/map/wms_merc.map', {
        //        layers: 'topo',
        //        transparent: true,
        //        //format: 'image/png',
        //        version: '1.1.1',
        //        crs: L.CRS.EPSG4326,
        //        attribution: '<a href="http://www.marine-geo.org/portals/gmrt/" target="_blank">GMRT</a>'
        //    });
        
        var worldOceanBase = L.tileLayer(window.location.origin + MAPPROXY_DIR +'/tms/1.0.0/WorldOceanBase/EPSG900913/{z}/{x}/{y}.png', {
            tms:true,
            zoomOffset:-1,
            minZoom:1,
            maxNativeZoom:9,
            attribution: '<a href="http://www.esri.com" target="_blank" style="border: none;">esri</a>'
        }),
        worldOceanReference = L.tileLayer(window.location.origin + MAPPROXY_DIR +'/tms/1.0.0/WorldOceanReference/EPSG900913/{z}/{x}/{y}.png', {
            tms:true,
            zoomOffset:-1,
            minZoom:1,
            maxNativeZoom:9,
            attribution: '<a href="http://www.esri.com" target="_blank" style="border: none;">esri</a>'
        }),
        gmrtBase = L.tileLayer(window.location.origin + MAPPROXY_DIR +'/tms/1.0.0/GMRTBase/EPSG900913/{z}/{x}/{y}.png', {
            tms:true,
            zoomOffset:-1,
            minZoom:1,
            attribution: '<a href="http://www.marine-geo.org/portals/gmrt/" target="_blank">GMRT</a>'
        });
        
        worldOceanBase.addTo(mapObject['map']);
        worldOceanBase.bringToBack();
        worldOceanReference.addTo(mapObject['map']);
        
        var baseLayers = {
            "World Ocean Base" : worldOceanBase,
            "GMRT Base" : gmrtBase
        };

        var overlays = {
            "World Ocean Reference" : worldOceanReference
        };
        
        L.control.layers(baseLayers, overlays).addTo(mapObject['map']);

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
            
            if ($(this).hasClass( "json-reversedY-radio" )) {
                updateChart(chartObjects[i], $(this).val(), true, false);
            } else if ($(this).hasClass( "json-reversedY-inverted-radio" )) {
                updateChart(chartObjects[i], $(this).val(), true, true);
            } else if ($(this).hasClass( "json-inverted-radio" )) {
                updateChart(chartObjects[i], $(this).val(), false, true);
            } else {
                updateChart(chartObjects[i], $(this).val());
            }
        }); 
    }
    
    function addLatestPositionToMap(mapObject, dataType) {
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getLatestVisualizerDataByType/' + cruiseID + '/' + dataType;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {
                
                if ('error' in data) {
                    $('#' + mapObject['placeholderID']).html('<strong>Error: ' + data.error + '</strong>');
                } else {
                    //Get the last coordinate from the latest trackline
                    var lastCoordinate = data[0].features[data[0].features.length - 1].geometry.coordinates[data[0].features[data[0].features.length - 1].geometry.coordinates.length - 1];
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
               
               var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + files[0]['dd_json'];
               $.getJSON(getVisualizerDataURL, function (data, status) {
                    if (status === 'success' && data !== null) {

                        if ('error' in data) {
                            $('#' + mapObject['placeholderID']).html('<strong>Error: ' + data.error + '</strong>');
                        } else {
                    
                            //Get the last coordinate from the latest trackline
                            var firstCoordinate = data[0].features[data[0].features.length - 1].geometry.coordinates[0];
                            var startPosition = L.latLng(firstCoordinate[1], firstCoordinate[0]);

                            if (firstCoordinate[0] < 0) {
                                startPosition = startPosition.wrap(360, 0);
                            } else {
                                startPosition = startPosition.wrap();
                            }

                            var lastCoordinate = data[0].features[data[0].features.length - 1].geometry.coordinates[data[0].features[data[0].features.length - 1].geometry.coordinates.length - 1];
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
        delete mapObject['markers']['StartPositios-' + dataType];
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
                        style: { weight: 3 },
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

                    // Build the layer
                    mapObject['tmsLayers'][tmsObjectJsonName] = L.tileLayer(location.protocol + '//' + location.host + cruiseDataDir + '/' + data[0]['tileDirectory'] + '/{z}/{x}/{y}.png', {
                        tms:true,
                        bounds:L.latLngBounds(southwest, northeast),
                        zIndex: 10
                    });
                    
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
                    //console.log(mapObject['mapBounds'][tmsObjectJsonName]);
                        
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
    
    function updateChart(chartObject, dataObjectJsonName, reversedY, inverted) {
        var reversedY = reversedY || false;
        var inverted = inverted || false;
        var getVisualizerDataURL = siteRoot + 'api/dashboardData/getDashboardObjectVisualizerDataByJsonName/' + cruiseID + '/' + dataObjectJsonName;
        $.getJSON(getVisualizerDataURL, function (data, status) {
            if (status === 'success' && data !== null) {
 
                var placeholder = '#' + chartObject['placeholderID'];
                if ('error' in data){
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
                        });
                                
                        scales[data[i].label] = {
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
                                        console.log("hide/show");
                                        console.log(legendItem);
                                        //get the index of the clicked legend
                                        var index = legendItem.datasetIndex;
                                        //toggle chosen dataset's visibility
                                        chartObject['chart'].data.datasets[index].hidden = 
                                            !chartObject['chart'].data.datasets[index].hidden;
                                        //toggle the related labels' visibility
                                        console.log(chartObject['chart'].options);
                                        console.log(chartObject['chart'].options.scales.Hummidity);
                                        // console.log(chartObject['chart'].options.scales.yAxes);
                                        // console.log(chartObject['chart'].options.scales.yAxes[index]);
                                        chartObject['chart'].options.scales.y.display =                 
                                            !chartObject['chart'].options.scales.y.display
                                        // chartObject['chart'].options.scales.yAxes[index].display =                 
                                        //     !chartObject['chart'].options.scales.yAxes[index].display;
                                        chartObject['chart'].update();
                                    }
                                }
                            },
                        },
                        data: seriesData
                    };

                    const ctx = document.getElementById(chartObject['placeholderID']).getContext('2d');
                            
                    if (chartObject['chart'] !== null) {
                        chartObject['chart'].destroy();
                    }

                    chartObject['chart'] = new Chart(ctx, chartOptions);
                    $('#' + chartObject['placeholderID']).css({height: chartObject['expanded'] ? 500 : 200});
                }
            }
        });
    }
    
    //Initialize the mapObjects
    $( '.map' ).each(function( index ) {
        var mapPlaceholderID = $( this ).attr('id');
        var tempArray = mapPlaceholderID.split("_");
        tempArray.pop();
        var objectListPlaceholderID =  tempArray.join('_') + '_objectList-placeholder';
        mapObjects.push(initMapObject(mapPlaceholderID, objectListPlaceholderID));
    });
    
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
        setTimeout(updateBounds(mapObjects[i]), 5000);
    }
    
    //build the charts
    for(var i = 0; i < chartObjects.length; i++) {
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
            if ($(this).hasClass( "json-reversedY-radio" )) {
                updateChart(chartObjects[i], $(this).val(), true, false);
            } else if ($(this).hasClass( "json-reversedY-inverted-radio" )) {
                updateChart(chartObjects[i], $(this).val(), true, true);
            } else if ($(this).hasClass( "json-inverted-radio" )) {
                updateChart(chartObjects[i], $(this).val(), false, true);
            } else {
                updateChart(chartObjects[i], $(this).val());
            }
        });
        
        $( '#' + chartObjects[i]['dataType'] + '_expand-btn').click(function() {
            chartObjects[i]['expanded'] = !chartObjects[i]['expanded'];
            $('#' + chartObjects[i]['placeholderID']).css({height: chartObjects[i]['expanded'] ? 500 : 200});
            $(this).removeClass(chartObjects[i]['expanded'] ? 'fa-expand' : 'fa-compress');
            $(this).addClass(chartObjects[i]['expanded'] ? 'fa-compress' : 'fa-expand');
        });
    });
});
