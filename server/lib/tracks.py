#!/usr/bin/env python3
"""Build GeoJSON and KML trackline files from OpenVDM's data dashboard files.

Shared by ``bin/build_cruise_tracks.py`` and ``bin/build_lowering_tracks.py``
(#394), which differ only in which cruise or lowering they read, where its
dashboard manifest is, and what they do with the result (the cruise extent).

For each position source (a device and its dashboard data type, from a
``PositionSources`` YAML list), the matching dashboard files are found through
the dashboard manifest, combined into one ``LineString`` trackline (or written
one per file), and saved as ``<prefix>_<device>_Trackline.json`` and ``.kml``.
The files go to an OpenVDM extra directory, where they belong to the
warehouse user and are added to the cruise's MD5 summary, or to a folder
given with ``-o``.
"""

import argparse
import json
import logging
import os

import yaml

from server.lib.file_utils import output_json_data_to_file, set_owner_group_permissions
from server.lib.geojson_utils import combine_geojson_files, convert_to_kml

# Name of the extra directory the trackline files are written to by default.
TRACKLINE_EXTRA_DIR_NAME = "Tracklines"
# Name of the extra directory holding the data dashboard files and manifest.
DASHBOARD_EXTRA_DIR_NAME = "Dashboard_Data"

# ----------------------------------------------------------------------
# Position sources
# ----------------------------------------------------------------------

def load_position_sources_from_yaml(
    *,
    yaml_str: str | None = None,
    yaml_path: str | None = None,
    collection_system: str
) -> list:
    """Parse and validate a position sources YAML definition.

    Exactly one of *yaml_str* or *yaml_path* must be provided.  The YAML must
    describe a mapping with ``CollectionSystem`` and ``PositionSources`` keys
    (``GPSSources``, the old name, is also accepted); the
    ``CollectionSystem`` value must match *collection_system*.  Duplicate device
    names or reused data types raise ``RuntimeError``.

    Args:
        yaml_str: Raw YAML string to parse (mutually exclusive with
            *yaml_path*).
        yaml_path: Path to a YAML file to load (mutually exclusive with
            *yaml_str*).
        collection_system: Expected value of the ``CollectionSystem`` key;
            used to guard against loading a config for the wrong system.

    Returns:
        List of position source dicts, each containing ``device`` and ``type``
        string keys.

    Raises:
        RuntimeError: On missing arguments, file-not-found, YAML parse
            errors, schema violations, or ``CollectionSystem`` mismatch.
    """
    if not yaml_str and not yaml_path:
        raise RuntimeError("Either yaml_str or yaml_path must be provided")

    try:
        if yaml_path:
            if not os.path.isfile(yaml_path):
                raise RuntimeError(f"position sources YAML not found: {yaml_path}")
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        else:
            data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as err:
        raise RuntimeError(f"Invalid position sources YAML: {err}") from err

    if not isinstance(data, dict):
        raise RuntimeError("position sources YAML must be a mapping")

    if data.get("CollectionSystem") != collection_system:
        raise RuntimeError(
            f"position sources CollectionSystem mismatch: "
            f"{data.get('CollectionSystem')} != {collection_system}"
        )

    position_sources = data.get("PositionSources", data.get("GPSSources"))
    if not isinstance(position_sources, list):
        raise RuntimeError("PositionSources must be a list")

    seen_devices: set = set()
    seen_types: set = set()

    for src in position_sources:
        device = src.get("device")
        dtype = src.get("type")

        if not device or not dtype:
            raise RuntimeError(
                "Each position source must define exactly one 'device' and one 'type'"
            )

        if device in seen_devices:
            raise RuntimeError(f"Duplicate position source device: {device}")

        if dtype in seen_types:
            raise RuntimeError(f"Manifest type reused across devices: {dtype}")

        seen_devices.add(device)
        seen_types.add(dtype)

    return position_sources


def get_position_sources(args: argparse.Namespace, default_yaml: str) -> list:
    """Return the position sources from ``--position-sources``, or the script's default.

    Args:
        args: Parsed arguments with ``position_sources_file`` and
            ``collectionSystem`` attributes.
        default_yaml: The script's embedded default position sources YAML.

    Returns:
        List of position source dicts validated by
        :func:`load_position_sources_from_yaml`.

    Raises:
        RuntimeError: If the sources can't be loaded (see
            :func:`load_position_sources_from_yaml`).
    """
    if args.position_sources_file:
        logging.info("Loading position sources from %s", args.position_sources_file)
        return load_position_sources_from_yaml(
            yaml_path=args.position_sources_file,
            collection_system=args.collectionSystem,
        )

    logging.debug("Using embedded position sources")
    return load_position_sources_from_yaml(
        yaml_str=default_yaml,
        collection_system=args.collectionSystem,
    )

# ----------------------------------------------------------------------
# Dashboard manifest
# ----------------------------------------------------------------------

def resolve_manifest_path(openvdm, cruise_base_dir: str, cruise_id: str, subdir: str = "") -> str:
    """Locate a data dashboard manifest file.

    Args:
        openvdm: Active :class:`~server.lib.openvdm.OpenVDM` instance.
        cruise_base_dir: Warehouse base directory (e.g. ``/data``).
        cruise_id: The cruise.
        subdir: Folder of the manifest inside the ``Dashboard_Data`` extra
            directory: empty for the cruise's, ``<loweringDataBaseDir>/<loweringID>``
            for a lowering's.

    Returns:
        Absolute path to the manifest file.

    Raises:
        RuntimeError: If the manifest filename cannot be retrieved, the
            ``Dashboard_Data`` extra directory is absent, or the manifest
            file does not exist on disk.
    """
    manifest_fn = openvdm.get_data_dashboard_manifest_fn()
    if not manifest_fn:
        raise RuntimeError("OpenVDM returned no manifest filename")

    extra_dir = openvdm.get_required_extra_directory_by_name(DASHBOARD_EXTRA_DIR_NAME)
    if not extra_dir:
        raise RuntimeError(f"Unable to find extra directory: {DASHBOARD_EXTRA_DIR_NAME}")

    manifest_path = os.path.join(cruise_base_dir, cruise_id, extra_dir["destDir"], subdir, manifest_fn)
    if not os.path.isfile(manifest_path):
        raise RuntimeError(f"Manifest not found: {manifest_path}")

    return manifest_path


def load_manifest(manifest_path: str) -> list:
    """Load and validate a dashboard data manifest JSON file.

    Args:
        manifest_path: Absolute path to the manifest file.

    Returns:
        List of manifest entry dicts, each containing at least ``type`` and
        ``dd_json`` keys.

    Raises:
        RuntimeError: On JSON parse errors, non-list manifests, or entries
            missing required keys.
    """
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Invalid manifest JSON: {err}") from err

    if not isinstance(manifest, list):
        raise RuntimeError("Manifest must be a list")

    for entry in manifest:
        if "type" not in entry or "dd_json" not in entry:
            raise RuntimeError("Manifest entry missing 'type' or 'dd_json'")

    return manifest


def get_dd_json_files_for_position_source(manifest: list, position_source: dict, cruise_base_dir: str) -> list:
    """Return dashboard JSON file paths matching a position source type.

    Args:
        manifest: Loaded manifest list (from :func:`load_manifest`).
        position_source: Position source dict with at least a ``type`` key.
        cruise_base_dir: Warehouse base directory prepended to each ``dd_json``
            entry path.

    Returns:
        Sorted list of absolute file paths for the matching entries.
    """
    wanted_type = position_source["type"]
    return sorted(os.path.join(cruise_base_dir, entry["dd_json"])
                  for entry in manifest if entry["type"] == wanted_type)

# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------

def write_outputs(geojson_obj: dict, base_name: str, prefix: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                  trackline_dir: str, args: argparse.Namespace, output_user: str | None,
                  written: list | None = None) -> None:
    """Write GeoJSON and/or KML trackline files for one position source.

    Files are named ``<prefix>_<base_name>_Trackline.json`` / ``.kml``.

    Args:
        geojson_obj: GeoJSON ``FeatureCollection`` dict to serialise.
        base_name: Device name or file stem used to build the output filename.
        prefix: Cruise or lowering ID, used as the filename prefix.
        trackline_dir: Directory where output files are written.
        args: Parsed arguments with ``kml_only`` and ``geojson_only``
            attributes.
        output_user: Username to ``chown`` each file to, or ``None`` to leave
            ownership as it is (``-o``).
        written: List to append ``(path, existed_before)`` to for each file
            written, for the MD5 summary update.
    """
    if written is None:
        written = []

    if not args.kml_only:
        json_path = os.path.join(trackline_dir, f"{prefix}_{base_name}_Trackline.json")
        logging.info("Saving %s", json_path)

        existed = os.path.isfile(json_path)
        result = output_json_data_to_file(json_path, geojson_obj)
        if not result["verdict"]:
            logging.error("Write failed: %s", result["reason"])
        else:
            written.append((json_path, existed))
            if output_user:
                set_owner_group_permissions(output_user, json_path)

    if not args.geojson_only:
        kml_path = os.path.join(trackline_dir, f"{prefix}_{base_name}_Trackline.kml")
        logging.info("Saving %s", kml_path)

        existed = os.path.isfile(kml_path)
        try:
            with open(kml_path, "w", encoding="utf-8") as f:
                f.write(convert_to_kml(geojson_obj))
        except OSError as err:
            logging.error("KML write failed: %s", err)
            return

        written.append((kml_path, existed))
        if output_user:
            set_owner_group_permissions(output_user, kml_path)


def process_position_source(position_source: dict, manifest: list, cruise_base_dir: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
                            prefix: str, trackline_dir: str, args: argparse.Namespace,
                            output_user: str | None, written: list | None = None) -> dict | None:
    """Process one position source: find its dashboard files and write tracklines.

    Unless ``--no-combine`` is given, the source's dashboard files are combined
    into a single trackline.

    Args:
        position_source: Position source dict with ``device`` and ``type`` keys.
        manifest: Loaded manifest list.
        cruise_base_dir: Warehouse base directory.
        prefix: Cruise or lowering ID, used as the filename prefix.
        trackline_dir: Directory where output files are written.
        args: Parsed arguments (``no_combine``, ``kml_only``, ``geojson_only``).
        output_user: Username to ``chown`` each file to, or ``None`` (``-o``).
        written: List of written files, passed to :func:`write_outputs`.

    Returns:
        dict | None: The combined trackline, or ``None`` with
        ``--no-combine`` or if the source has no usable files.
    """
    logging.info("Processing %s (type=%s)", position_source["device"], position_source["type"])

    files = get_dd_json_files_for_position_source(manifest, position_source, cruise_base_dir)

    if not files:
        logging.warning("No manifest entries found for %s", position_source["device"])
        return None

    if not args.no_combine:
        combined = combine_geojson_files(files, prefix, position_source["device"])
        if not combined:
            logging.error("Failed to combine files for %s", position_source["device"])
            return None

        write_outputs(combined, position_source["device"], prefix, trackline_dir, args, output_user, written)
        return combined

    # no-combine mode
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            geojson_obj = data["visualizerData"][0]
        except (OSError, KeyError, IndexError, json.JSONDecodeError) as err:
            logging.error("Invalid dashboard file %s: %s", file, err)
            continue

        base_name = os.path.basename(file).split(".")[0]
        write_outputs(geojson_obj, base_name, prefix, trackline_dir, args, output_user, written)

    return None


def queue_md5_update(openvdm, written: list, cruise_id: str) -> str | None:
    """Queue the cruise's MD5 summary update for the trackline files written.

    Args:
        openvdm: Active :class:`~server.lib.openvdm.OpenVDM` instance.
        written: ``(path, existed_before)`` for each file written (from
            :func:`write_outputs`); files that didn't exist are ``new``.
        cruise_id: The cruise whose summary to update.

    Returns:
        str | None: A message if the update couldn't be queued, else ``None``.
    """
    try:
        openvdm.update_md5_summary(new=[path for path, existed in written if not existed],
                                   updated=[path for path, existed in written if existed],
                                   cruise_id=cruise_id)
    except Exception as err:  # pylint: disable=broad-exception-caught
        return f"Unable to queue the MD5 summary update for the tracklines: {err}"
    return None

# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------

def resolve_extra_directory(openvdm, name: str, cruise_dir: str, cruise_id: str,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                            warehouse_cfg: dict, lowering_id: str | None = None) -> str:
    """Return the folder of an OpenVDM extra directory.

    ``{cruiseID}`` and ``{loweringDataBaseDir}`` in its ``destDir`` are
    filled in. For a cruise (no *lowering_id*) a per-lowering directory
    (``{loweringID}``) is refused. For a lowering, ``{loweringID}`` is filled
    in too, and a lowering-level extra directory (``cruiseOrLowering`` 1) is
    inside the lowering, ``<loweringDataBaseDir>/<loweringID>/<destDir>``,
    where OpenVDM creates it.

    Args:
        openvdm: Active :class:`~server.lib.openvdm.OpenVDM` instance.
        name: The extra directory's name.
        cruise_dir: The cruise directory.
        cruise_id: The cruise.
        warehouse_cfg: From ``OpenVDM.get_shipboard_data_warehouse_config()``.
        lowering_id: The lowering, for a lowering's tracklines.

    Returns:
        str: The folder's absolute path.

    Raises:
        RuntimeError: If there's no such extra directory, it isn't enabled,
            it's per lowering for a cruise, or its folder doesn't exist.
    """
    extra_dir = openvdm.get_extra_directory_by_name(name)
    if not extra_dir:
        raise RuntimeError(f"No extra directory named {name}: add it in OpenVDM's Configuration > Extra Directories")
    if str(extra_dir.get("enable")) != "1":
        raise RuntimeError(f"The {name} extra directory isn't enabled")

    dest_dir = extra_dir.get("destDir") or ""
    if lowering_id is None and "{loweringID}" in dest_dir:
        raise RuntimeError(f"The {name} extra directory is per lowering ({dest_dir}), which isn't supported")
    dest_dir = dest_dir.replace("{cruiseID}", cruise_id) \
                       .replace("{loweringDataBaseDir}", warehouse_cfg["loweringDataBaseDir"])
    if lowering_id is not None:
        dest_dir = dest_dir.replace("{loweringID}", lowering_id)
    dest_dir = dest_dir.strip("/")
    if lowering_id is not None and str(extra_dir.get("cruiseOrLowering")) == "1":
        dest_dir = os.path.join(warehouse_cfg["loweringDataBaseDir"], lowering_id, dest_dir)

    folder = os.path.join(cruise_dir, dest_dir)
    if not os.path.isdir(folder):
        raise RuntimeError(f"The {name} extra directory's folder doesn't exist: {folder}")
    return folder


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the mutually exclusive ``-e/--extra-directory`` and ``-o`` options.

    Args:
        parser: The script's argument parser.
    """
    output = parser.add_mutually_exclusive_group()
    output.add_argument("-e", "--extra-directory", dest="extraDirectory",
                        help=f"OpenVDM extra directory to write the tracklines to (default: {TRACKLINE_EXTRA_DIR_NAME})")
    output.add_argument("-o", dest="outputDir",
                        help="folder to write the tracklines to instead of an extra directory; "
                             "they aren't added to the MD5 summary")


def setup_logging(verbosity: int) -> None:
    """Log to stderr at WARNING, INFO (``-v``) or DEBUG (``-vv``).

    Args:
        verbosity: How many times ``-v`` was given.
    """
    logging.basicConfig(format="%(asctime)-15s %(levelname)s - %(message)s")
    logging.getLogger().setLevel([logging.WARNING, logging.INFO, logging.DEBUG][min(verbosity, 2)])
