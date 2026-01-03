#!/usr/bin/env python3
"""
FILE:  condense_ranges.py

DESCRIPTION:  Utilities for working with geojson and kml files.

     BUGS:
    NOTES:
   AUTHOR:  Webb Pinner
  VERSION:  2.14
  CREATED:  2024-06-01
"""

import json
import logging
from xml.etree.ElementTree import Element, SubElement, tostring

def combine_geojson_files(input_files, prefix, device_name):
    """
    Combine GeoJSON trackline data from OpenVDM dashboard files.

    Ignores non-GeoJSON visualizerData entries (e.g. timeseries).
    Returns None on failure or if no usable GeoJSON data is found.
    """

    def extract_visualizer_data(data: dict) -> list[dict]:
        """
        Return the raw visualizerData list from legacy or new formats.
        """

        # New format: datatype-wrapped
        if len(data) == 1:
            _, inner = next(iter(data.items()))
            if isinstance(inner, dict) and "visualizerData" in inner:
                vdata = inner["visualizerData"]
                if isinstance(vdata, list):
                    return vdata

        # Legacy format
        if "visualizerData" in data and isinstance(data["visualizerData"], list):
            return data["visualizerData"]

        raise ValueError("Unrecognized dashboard JSON format")

    # ------------------------------------------------------------------

    if not input_files:
        return None

    combined = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [],
                },
                "properties": {
                    "name": f"{prefix}_{device_name}",
                    "coordTimes": [],
                },
            }
        ],
    }

    out_feature = combined["features"][0]
    found_geojson = False

    # ------------------------------------------------------------------

    for file in input_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                raw = json.load(f)

            visualizers = extract_visualizer_data(raw)

            for entry in visualizers:
                # Skip non-GeoJSON visualizers (timeseries, stats, etc.)
                if (
                    not isinstance(entry, dict)
                    or entry.get("type") != "FeatureCollection"
                    or not isinstance(entry.get("features"), list)
                ):
                    continue

                found_geojson = True

                for feature in entry["features"]:
                    geom = feature.get("geometry", {})
                    props = feature.get("properties", {})

                    if geom.get("type") != "LineString":
                        continue

                    coords = geom.get("coordinates", [])
                    times = props.get("coordTimes", [])

                    if not isinstance(coords, list) or not isinstance(times, list):
                        continue

                    out_feature["geometry"]["coordinates"].extend(coords)
                    out_feature["properties"]["coordTimes"].extend(times)

        except Exception as exc:
            logging.error("ERROR: Could not process file: %s", file)
            logging.debug(str(exc))
            return None

    if not found_geojson:
        logging.warning(
            "No GeoJSON FeatureCollections found for %s", device_name
        )
        return None

    return combined



def convert_to_kml(geojson_obj):
    """
    Function to convert a geoJSON object to a KML (v2.2) string.
    Function returns a KML-formatted string
    """

    kml = Element('kml')
    kml.set('xmlns', 'http://www.opengis.net/kml/2.2')
    kml.set('xmlns:gx','http://www.google.com/kml/ext/2.2')
    kml.set('xmlns:kml','http://www.opengis.net/kml/2.2')
    kml.set('xmlns:atom','http://www.w3.org/2005/Atom')
    document = SubElement(kml, 'Document')
    name = SubElement(document, 'name')
    name.text = f"{geojson_obj['features'][0]['properties']['name']}_Trackline.kml"
    placemark = SubElement(document, 'Placemark')
    name2 = SubElement(placemark, 'name')
    name2.text = "path1"
    linestring = SubElement(placemark, 'LineString')
    tessellate = SubElement(linestring, 'tessellate')
    tessellate.text = "1"
    coordinates = SubElement(linestring, 'coordinates')

    coordinates_text = ''

    for coordinate in geojson_obj['features'][0]['geometry']['coordinates']:
        coordinates_text += f'{coordinate[0]},{coordinate[1]},0 '

    coordinates_text = coordinates_text.rstrip(' ')
    coordinates.text = coordinates_text

    return f'<?xml version="1.0" encoding="utf-8"?>{tostring(kml).decode("utf8")}'
