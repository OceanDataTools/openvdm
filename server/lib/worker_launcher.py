"""Run an OpenVDM worker and report it in an OpenVDM message when it fails.

Supervisor starts each worker through this module (#503)::

    python -m server.lib.worker_launcher server/workers/cruise.py [options]

The worker runs as ``__main__``, as if started directly. When it raises an
exception, at any point including while it's imported, the failure would
otherwise only be in its log: the web pages carry on as if its tasks could
run. A missing Python package, for example, stops the worker as it's
imported, before its own code can report anything. So the launcher prints the
traceback to the log, posts an OpenVDM message naming the worker and the
error, and exits with status 1, so Supervisor still sees the failure.

Supervisor restarts a failed worker several times, and a worker with several
processes fails in each, so the same error is posted at most once an hour
for each worker (:data:`REPEAT_AFTER`).

A worker that can't load ``openvdm.yaml`` can't post the message, since the
site's address is in that file. The Configuration page's warning about
workers that aren't running covers that case.
"""

import logging
import os
import runpy
import sys
import time
import traceback
from os.path import basename, dirname, join, realpath, splitext
from typing import List, Optional

# Where the last reported failure of each worker is recorded, and how long
# before the same failure is reported again
REPORT_DIR = '/run/openvdm'
REPEAT_AFTER = 60 * 60


def _summary(exc: BaseException) -> str:
    """Return the exception's last traceback line, e.g. ``ModuleNotFoundError: ...``."""
    return ''.join(traceback.format_exception_only(type(exc), exc)).strip()


def _first_report(worker: str, summary: str, now: Optional[float] = None) -> bool:
    """Record a failure; return whether it should be reported.

    Args:
        worker: The worker's name.
        summary: The failure, from :func:`_summary`.
        now: The current time (for tests).

    Returns:
        bool: ``False`` when the same failure was reported less than
        :data:`REPEAT_AFTER` seconds ago; ``True`` otherwise, including when
        the record can't be read or written.
    """
    now = time.time() if now is None else now
    record = join(REPORT_DIR, f'worker-{worker}.failed')
    try:
        with open(record, encoding='utf-8') as file:
            if file.read() == summary and now - os.path.getmtime(record) < REPEAT_AFTER:
                return False
    except OSError:
        pass

    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(record, 'w', encoding='utf-8') as file:
            file.write(summary)
    except OSError as exc:
        logging.warning("Unable to record the failure in %s: %s", record, exc)
    return True


def report_failure(worker: str, exc: BaseException) -> None:
    """Post an OpenVDM message about a worker that failed.

    Args:
        worker: The worker's name, which is also its Supervisor program and
            log file name.
        exc: The exception it failed with.
    """
    summary = _summary(exc)
    if not _first_report(worker, summary):
        logging.info("Already reported in the last hour: %s", summary)
        return

    if isinstance(exc, ModuleNotFoundError):
        hint = ("A Python package is missing. Install OpenVDM's packages (re-run the installer, or "
                "run pip install -r requirements.txt in OpenVDM's venv), then restart the workers.")
    else:
        hint = f"See its log, /var/log/openvdm/{worker}.log."

    try:
        # Imported here: it needs packages that may be the ones missing
        from server.lib.openvdm import OpenVDM  # pylint: disable=import-outside-toplevel
        OpenVDM().send_msg(f"Worker {worker} stopped", f"{summary}. {hint}")
    except Exception as report_exc:  # pylint: disable=broad-exception-caught
        logging.error("Unable to post an OpenVDM message about it: %s", report_exc)


def main(argv: Optional[List[str]] = None) -> int:
    """Run the worker script named by the first argument.

    Args:
        argv: The worker script and its arguments; ``sys.argv[1:]`` by default.

    Returns:
        int: 0 when the worker ended normally, 1 when it raised an exception
        (2 for a usage error). A worker exiting with ``sys.exit()`` exits
        with its own status.
    """
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m server.lib.worker_launcher <worker script> [options]", file=sys.stderr)
        return 2

    script = argv[0]
    worker = splitext(basename(script))[0]

    # As if the script were run directly: its own arguments, and its
    # directory first on the path
    sys.argv = list(argv)
    sys.path.insert(0, dirname(realpath(script)))

    try:
        runpy.run_path(script, run_name='__main__')
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # pylint: disable=broad-exception-caught
        traceback.print_exc()
        sys.stderr.flush()
        report_failure(worker, exc)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
