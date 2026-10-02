/**
 * Shared Leaflet basemap definitions for OpenVDM maps.
 *
 * None of these layers require an API key. Loaded automatically wherever the
 * 'leaflet' script bundle is included (see templates/default/footer.php), so
 * dashboard, lowering and custom dashboard scripts can call openvdmBaseLayers().
 * Also holds helpers for drawing GeoJSON features, lines and points, on them.
 */

/* exported openvdmBaseLayers, openvdmOverlayLayers, openvdmFeaturePositions, openvdmPointMarker, openvdmFeaturePopup */

/**
 * Build a fresh set of basemap layers for the layer switcher.
 *
 * Leaflet layers should not be shared between maps, so call this once per map.
 * The first entry ("OpenStreetMap") is the default layer.
 *
 * @returns {Object} Map of layer name to Leaflet layer, in display order.
 */
function openvdmBaseLayers () {
    return {
        'OpenStreetMap': openvdmDefaultBaseLayer(),
        'Esri Ocean Basemap': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, Garmin, GEBCO, NOAA NGDC, and other contributors',
            // Open-ocean data ends at zoom 10; beyond that Esri serves a "map data not yet available" tile
            maxNativeZoom: 10,
            maxZoom: 20
        }),
        'Esri Dark Gray Canvas': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
            // Open-ocean data ends at zoom 12 (16 near the coast); beyond that Esri serves a
            // "map data not yet available" tile (#253)
            maxNativeZoom: 12,
            maxZoom: 20
        }),
        'Esri Light Gray Canvas': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
            maxNativeZoom: 12,
            maxZoom: 20
        }),
        'GMRT Base': L.tileLayer.wms('https://www.gmrt.org/services/mapserver/wms_merc?', {
            layers: 'topo',
            format: 'image/png',
            attribution: '<a href="https://www.marine-geo.org/portals/gmrt/" target="_blank" rel="noopener">GMRT</a>'
        })
    };
}

/**
 * Build just the default basemap layer (OpenStreetMap).
 *
 * Used directly by the small, non-interactive dashboard preview maps that have
 * no layer switcher.
 *
 * @returns {L.TileLayer} A new OpenStreetMap tile layer.
 */
function openvdmDefaultBaseLayer () {
    return L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        maxNativeZoom: 19,
        maxZoom: 20
    });
}

/**
 * Build a fresh set of transparent label overlays for the layer switcher.
 *
 * These sit on top of the basemap and are off by default. Pass the result as the
 * second argument to L.control.layers().
 *
 * - Ocean Labels (Esri): undersea feature and ocean names for the Esri
 *   basemaps and GMRT, which carry no labels of their own (OpenStreetMap
 *   already does).
 * - OpenSeaMap Seamarks: buoys, lights and other nautical marks. Only drawn
 *   when zoomed in to zoom 12 or closer, so it is a harbor and coastal aid.
 *
 * @returns {Object} Map of overlay name to Leaflet layer, in display order.
 */
function openvdmOverlayLayers () {
    return {
        'Ocean Labels (Esri)': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Labels &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, GEBCO, NOAA, National Geographic, Garmin, HERE, Geonames.org, and other contributors',
            maxNativeZoom: 12,
            maxZoom: 20
        }),
        'OpenSeaMap Seamarks': L.tileLayer('https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png', {
            attribution: 'Map data: &copy; <a href="https://www.openseamap.org" target="_blank" rel="noopener">OpenSeaMap</a> contributors',
            // Buoys, lights and other nautical marks: tiles are blank below zoom 12 and above zoom 18
            minZoom: 12,
            maxNativeZoom: 18,
            maxZoom: 20
        })
    };
}

/**
 * Return a GeoJSON feature's positions as [longitude, latitude] pairs, in order.
 *
 * A Point gives one position and a LineString (a track) all of its own, so code
 * that needs a feature's first or last position works for both (#292).
 *
 * @param {Object} feature - A GeoJSON Feature.
 * @returns {Array} The positions; empty for a missing or unsupported geometry.
 */
function openvdmFeaturePositions (feature) {
    var geometry = feature && feature.geometry;
    if (!geometry || !geometry.coordinates) {
        return [];
    }
    switch (geometry.type) {
    case 'Point':
        return [geometry.coordinates];
    case 'MultiPoint':
    case 'LineString':
        return geometry.coordinates;
    case 'MultiLineString':
        return [].concat.apply([], geometry.coordinates);
    default:
        return [];
    }
}

/**
 * Return a Leaflet pointToLayer function drawing GeoJSON points as circle markers.
 *
 * Without it, L.geoJson draws points as Leaflet's default pin icons.
 *
 * @param {string} [color] - Fill colour, e.g. the data type's track colour.
 * @returns {Function} A pointToLayer function for L.geoJson.
 */
function openvdmPointMarker (color) {
    return function (feature, latlng) {
        return L.circleMarker(latlng, {
            radius: 6,
            weight: 1,
            color: '#000000',
            fillColor: color || '#3388ff',
            fillOpacity: 0.9
        });
    };
}

/**
 * Leaflet onEachFeature function giving a GeoJSON point a popup of its properties.
 *
 * Lists the properties with simple values (e.g. station, cast, time); lines
 * (tracks) get no popup.
 *
 * @param {Object} feature - The GeoJSON Feature.
 * @param {Object} layer - Its Leaflet layer.
 */
function openvdmFeaturePopup (feature, layer) {
    if (!feature.geometry || feature.geometry.type !== 'Point') {
        return;
    }
    var properties = feature.properties || {};
    var rows = Object.keys(properties).filter(function (key) {
        var value = properties[key];
        return value !== null && value !== undefined && typeof value !== 'object';
    }).map(function (key) {
        var name = document.createElement('th');
        var value = document.createElement('td');
        name.textContent = key;
        value.textContent = properties[key];
        return '<tr>' + name.outerHTML + value.outerHTML + '</tr>';
    });
    if (rows.length > 0) {
        layer.bindPopup('<table class="table table-condensed">' + rows.join('') + '</table>');
    }
}
