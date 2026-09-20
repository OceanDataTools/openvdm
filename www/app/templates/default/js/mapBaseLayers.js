/**
 * Shared Leaflet basemap definitions for OpenVDM maps.
 *
 * None of these layers require an API key. Loaded automatically wherever the
 * 'leaflet' script bundle is included (see templates/default/footer.php), so
 * dashboard, lowering and custom dashboard scripts can call openvdmBaseLayers().
 */

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
        'OpenTopoMap': L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: 'Map data: &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, <a href="https://viewfinderpanoramas.org" target="_blank" rel="noopener">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org" target="_blank" rel="noopener">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC-BY-SA</a>)',
            maxNativeZoom: 17,
            maxZoom: 20
        }),
        'EMODnet Bathymetry': L.tileLayer('https://tiles.emodnet-bathymetry.eu/2020/baselayer/web_mercator/{z}/{x}/{y}.png', {
            attribution: '<a href="https://emodnet.ec.europa.eu/en/bathymetry" target="_blank" rel="noopener">EMODnet Bathymetry Consortium</a>',
            maxNativeZoom: 12,
            maxZoom: 20
        }),
        'Esri Ocean Basemap': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, Garmin, GEBCO, NOAA NGDC, and other contributors',
            // Open-ocean data ends at zoom 10; beyond that Esri serves a "map data not yet available" tile
            maxNativeZoom: 10,
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
 * These sit on top of the basemap and are off by default. They are mainly
 * useful over the EMODnet, Esri Ocean and GMRT basemaps, which carry no labels
 * of their own (OpenStreetMap and OpenTopoMap already do). Pass the result as
 * the second argument to L.control.layers().
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
        'Place Labels (Esri)': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Labels &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
            maxNativeZoom: 19,
            maxZoom: 20
        })
    };
}
