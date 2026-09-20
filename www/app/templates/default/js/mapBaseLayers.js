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
        'Esri Ocean Basemap': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, Garmin, GEBCO, NOAA NGDC, and other contributors',
            // Open-ocean data ends at zoom 10; beyond that Esri serves a "map data not yet available" tile
            maxNativeZoom: 10,
            maxZoom: 20
        }),
        'Esri Dark Gray Canvas': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
            // Data ends at zoom 16; beyond that Esri serves a "map data not yet available" tile
            maxNativeZoom: 16,
            maxZoom: 20
        }),
        'Esri Light Gray Canvas': L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
            maxNativeZoom: 16,
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
