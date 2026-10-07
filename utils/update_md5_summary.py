#!/usr/bin/env python3
"""Queue an MD5 summary update for files in a cruise directory.

For hook commands and tools that write files into the cruise directory, which
no transfer or data dashboard job lists for the MD5 summary (#373). The files
are added to the cruise's MD5 summary, or their checksums replaced; files
given with ``--deleted`` are removed from it. Paths are relative to the cruise
directory, or absolute paths inside it.

Run it with OpenVDM's Python, e.g.::

    /opt/openvdm/venv/bin/python /opt/openvdm/utils/update_md5_summary.py \\
        Products/CTD_QA/ODT2601_ctd_qa_report.pdf

It exits non-zero with a message if a path is outside the cruise directory or
OpenVDM or the Gearman server can't be reached.
"""

import argparse
import logging
import sys
from os.path import dirname, realpath

sys.path.append(dirname(dirname(realpath(__file__))))

from server.lib.openvdm import OpenVDM  # noqa: E402  pylint: disable=wrong-import-position


def main() -> int:
    """Parse the command line and queue the update.

    Returns:
        int: The exit status: 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(description='Queue an MD5 summary update for files in a cruise directory')
    parser.add_argument('files', metavar='FILE', nargs='*',
                        help='file to add to the MD5 summary, or whose checksum changed')
    parser.add_argument('--deleted', metavar='FILE', nargs='+', default=[],
                        help='file to remove from the MD5 summary')
    parser.add_argument('-c', '--cruiseID', default=None, help='cruise (default: the current cruise)')
    parser.add_argument('--wait', action='store_true', help='wait for the update to finish')
    parser.add_argument('-v', '--verbosity', default=0, action='count', help='increase verbosity')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(levelname)s - %(message)s',
                        level=logging.DEBUG if args.verbosity else logging.WARNING)

    if not args.files and not args.deleted:
        parser.error('no files given')

    try:
        OpenVDM().update_md5_summary(updated=args.files, deleted=args.deleted, cruise_id=args.cruiseID,
                                     background=not args.wait)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Unable to queue the MD5 summary update: {exc}", file=sys.stderr)
        return 1

    logging.info("Queued an MD5 summary update for %d file(s)", len(args.files) + len(args.deleted))
    return 0


if __name__ == '__main__':
    sys.exit(main())
