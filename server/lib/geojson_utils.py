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
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring

def combine_geojson_files(input_files, prefix, device_name):
    """
    Combine GeoJSON LineString data from OpenVDM dashboard files.

    - Supports legacy and new (multi-datatype) dashboard formats
    - Ignores non-GeoJSON visualizerData entries (timeseries, plots, stats)
    - Returns None if no usable GeoJSON data is found or on error
    """

    def iter_visualizer_entries(data: dict):
        """
        Yield every visualizerData entry from legacy or new dashboard JSON.
        """

        # Legacy format
        if "visualizerData" in data and isinstance(data["visualizerData"], list):
            yield from data["visualizerData"]

        # New format: multiple datatypes possible
        for value in data.values():
            if (
                isinstance(value, dict)
                and "visualizerData" in value
                and isinstance(value["visualizerData"], list)
            ):
                yield from value["visualizerData"]

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

            for entry in iter_visualizer_entries(raw):
                # Only GeoJSON FeatureCollections are relevant
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
        logging.warning("No GeoJSON track data found for %s", device_name)
        return None

    return combined




def convert_to_kml(geojson_obj):
    """
    Convert a GeoJSON FeatureCollection with coordTimes into a KML 2.2 string.
    Adds a <TimeSpan> to the Placemark using the first and last coordTimes.
    """

    def _to_kml_time(value):
        """
        Convert coordTimes value to ISO-8601 string for KML.
        Supports:
          - ISO strings (pass-through)
          - epoch milliseconds
          - epoch seconds
        """
        if isinstance(value, str):
            return value

        if isinstance(value, (int, float)):
            # Heuristic: milliseconds vs seconds
            if value > 1e12:
                value /= 1000.0
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")

        raise ValueError(f"Unsupported coordTime type: {type(value)}")

    feature = geojson_obj["features"][0]
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    coord_times = props.get("coordTimes", [])

    kml = Element("kml")
    kml.set("xmlns", "http://www.opengis.net/kml/2.2")
    kml.set("xmlns:gx", "http://www.google.com/kml/ext/2.2")
    kml.set("xmlns:kml", "http://www.opengis.net/kml/2.2")
    kml.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    document = SubElement(kml, "Document")
    name = SubElement(document, "name")
    name.text = f"{props.get('name', 'Trackline')}_Trackline.kml"

    placemark = SubElement(document, "Placemark")

    pm_name = SubElement(placemark, "name")
    pm_name.text = "path1"

    # --------------------------------------------------
    # TimeSpan (optional, but recommended)
    # --------------------------------------------------

    if coord_times and len(coord_times) >= 2:
        try:
            begin = _to_kml_time(coord_times[0])
            end = _to_kml_time(coord_times[-1])

            if begin and end:
                timespan = SubElement(placemark, "TimeSpan")
                begin_el = SubElement(timespan, "begin")
                begin_el.text = begin
                end_el = SubElement(timespan, "end")
                end_el.text = end

        except Exception as err:
            logging.warning("Skipping TimeSpan due to invalid coordTimes: %s", err)


    # --------------------------------------------------
    # Geometry
    # --------------------------------------------------

    linestring = SubElement(placemark, "LineString")

    tessellate = SubElement(linestring, "tessellate")
    tessellate.text = "1"

    coordinates_el = SubElement(linestring, "coordinates")

    coordinates_text = []
    for lon, lat, *rest in coords:
        coordinates_text.append(f"{lon},{lat},0")

    coordinates_el.text = " ".join(coordinates_text)

    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        + tostring(kml, encoding="utf-8").decode("utf-8")
    )
