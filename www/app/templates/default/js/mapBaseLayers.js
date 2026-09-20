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
