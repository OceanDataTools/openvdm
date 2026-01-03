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
    Function to combine all the geoJSON-formatted files listed in the 'files' array
    command-line argument.  The function is also passed the cruiseID and device name so
    that this information can be added as a property to the final geoJSON file.

    If the raw datafile cannot be processed the function returns false.  If there were no
    files to process the fuction returns Null.  Otherwise the fuction returns the
    combined geoJSON object
    """

    def normalize_dashboard_geojson(data: dict) -> dict:
        """
        Normalize legacy and current OpenVDM dashboard formats.

        NEW format:
          { "<datatype>": { "visualizerData": [...] } }

        LEGACY format:
          { "visualizerData": [...] }

        Returns:
          { "visualizerData": [...] }
        """

        # NEW format: single datatype key
        if len(data) == 1:
            _, inner = next(iter(data.items()))
            if isinstance(inner, dict) and "visualizerData" in inner:
                if not isinstance(inner["visualizerData"], list):
                    raise ValueError("'visualizerData' must be a list")
                return inner

        # LEGACY format
        if "visualizerData" in data:
            if not isinstance(data["visualizerData"], list):
                raise ValueError("'visualizerData' must be a list")
            return data

        raise ValueError(
            "Unrecognized dashboard GeoJSON format "
            "(expected datatype-wrapped or legacy visualizerData)"
        )

    # Blank geoJson object
    returned_geojson_obj = {
        "type":"FeatureCollection",
        "features":[
            {
                "type":"Feature",
                "geometry":{
                    "type":"LineString",
                    "coordinates":[]
                },
                "properties": {
                    "name": f'{prefix}_{device_name}',
                    "coordTimes":[]
                }
            }
        ]
    }

    if len(input_files) == 0:
        return None

    for file in input_files:

        # Open the dashboardData file
        try:
            with open(file, mode='r', encoding="utf-8") as geojson_file:
                raw_geojson_obj = json.load(geojson_file)
                normalized = normalize_dashboard_geojson(raw_geojson_obj)
                geojson_obj = normalized["visualizerData"][0]

                returned_geojson_obj['features'][0]['geometry']['coordinates'] += geojson_obj['visualizerData'][0]['features'][0]['geometry']['coordinates']
                returned_geojson_obj['features'][0]['properties']['coordTimes'] += geojson_obj['visualizerData'][0]['features'][0]['properties']['coordTimes']

        # If the file cannot be processed return false.
        except Exception as exc:
            logging.error("ERROR: Could not proccess file: %s", file)
            logging.debug(str(exc))
            return None

    # If processing is successful, return the (geo)json object
    return returned_geojson_obj


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
