#!/usr/bin/env python3
"""Fill in the placeholders of a destination directory.

A collection system transfer's or extra directory's ``destDir`` can use
``{cruiseID}``, ``{loweringDataBaseDir}`` and ``{loweringID}``. The transfer
and directory workers fill them in with their own ``keyword_replace()``; this
is the shared version for code that reads ``destDir`` from the configuration
outside those workers (#635).
"""

from typing import Optional


def fill_placeholders(path: str, cruise_id: str, lowering_data_base_dir: str,
                      lowering_id: Optional[str] = None) -> str:
    """Return *path* with its placeholders filled in.

    Args:
        path: A destination directory, or a path or filter built from one.
        cruise_id: For ``{cruiseID}``.
        lowering_data_base_dir: For ``{loweringDataBaseDir}``.
        lowering_id: For ``{loweringID}``. Without it ``{loweringID}`` is
            left as it is, for the caller to fill in for each lowering.

    Returns:
        str: The path, with its slashes as they were.
    """
    path = (path or '').replace('{cruiseID}', cruise_id)
    path = path.replace('{loweringDataBaseDir}', lowering_data_base_dir)
    if lowering_id is not None:
        path = path.replace('{loweringID}', lowering_id)
    return path
