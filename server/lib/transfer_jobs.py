"""Run transfer jobs that each transfer must run, such as finalize's final pass.

Finalizing a cruise or lowering runs its transfers one last time. A job for a
transfer that another job is already running is ignored ("Transfer is already
in-progress"), and that running job started before the cruise or lowering
ended. :func:`run_transfer_jobs` waits for such a job to end, then submits the
transfer's job again, so each transfer gets its own run with its own payload
(#480).
"""

import json
import logging
import time
from typing import Callable, Dict, List, Optional

from server.lib.transfer_lock import transfer_locked

# The reason a transfer worker gives for ignoring a job whose transfer another
# job is running (#478)
IN_PROGRESS_REASON = "Transfer is already in-progress"

# How long to wait for running jobs to end before giving up on their
# transfers, and how often to check
RUNNING_JOB_WAIT = 60 * 60
POLL_INTERVAL = 5


def ignored_as_in_progress(result: Optional[str]) -> bool:
    """Return whether a transfer job was ignored because another job is running it.

    Args:
        result: The job's JSON result, or ``None`` if the job failed.

    Returns:
        bool: ``True`` if the result's last part is an ``Ignore`` with
        :data:`IN_PROGRESS_REASON`.
    """
    try:
        parts = json.loads(result).get('parts') or []
    except (TypeError, ValueError, AttributeError):
        return False
    return bool(parts) and parts[-1].get('result') == 'Ignore' \
        and parts[-1].get('reason') == IN_PROGRESS_REASON


def run_transfer_jobs(gm_client, task: str, kind: str, payloads: Dict[int, dict],
                      wait: float = RUNNING_JOB_WAIT,
                      should_stop: Optional[Callable[[], bool]] = None) -> List[int]:
    """Run a job for each transfer, waiting for any already running to end first.

    Submits every job and waits for them to complete. A job ignored because
    another job is running its transfer is submitted again once that
    transfer's lock is free. Another scheduled run may take the lock first,
    so this repeats. Once *wait* seconds have passed since the first job was
    ignored, transfers still running are given up on.

    Args:
        gm_client: A ``python3_gearman.GearmanClient``.
        task: The Gearman task, e.g. ``runCollectionSystemTransfer``.
        kind: The transfers' lock kind (``CST`` or ``CDT``).
        payloads: Each transfer's job payload, by transfer ID.
        wait: Longest time, in seconds, to wait for running jobs to end.
        should_stop: Polled while waiting; when it returns ``True``, the wait
            ends (#487).

    Returns:
        list[int]: The IDs of the transfers whose job never ran, because
        another job was still running them after *wait* seconds or the wait
        was stopped.
    """
    deadline = None
    to_run = list(payloads)
    waiting = []

    while True:
        if to_run:
            requests = gm_client.submit_multiple_jobs(
                [{'task': task, 'data': json.dumps(payloads[transfer_id])} for transfer_id in to_run],
                background=False, wait_until_complete=False)
            time.sleep(1)
            gm_client.wait_until_jobs_completed(requests)
            waiting += [transfer_id for transfer_id, request in zip(to_run, requests)
                        if ignored_as_in_progress(request.result)]

        if not waiting:
            return []

        if deadline is None:
            deadline = time.monotonic() + wait
        logging.info("Waiting for running jobs to end: %s %s", kind, waiting)

        # Run the transfers whose job has ended; keep waiting for the rest
        while True:
            if should_stop and should_stop():
                logging.warning("Stopped while waiting for running jobs: %s %s", kind, waiting)
                return waiting
            to_run = [transfer_id for transfer_id in waiting if not transfer_locked(kind, transfer_id)]
            if to_run:
                break
            if time.monotonic() >= deadline:
                logging.warning("Still running after %d minutes: %s %s", wait // 60, kind, waiting)
                return waiting
            time.sleep(POLL_INTERVAL)

        waiting = [transfer_id for transfer_id in waiting if transfer_id not in to_run]


def report_missed(ovdm, job_results: dict, title: str, part_name: str, names: List[str]) -> None:
    """Report transfers whose job :func:`run_transfer_jobs` never ran.

    Posts an OpenVDM message and adds a ``Fail`` part to *job_results*.
    Finalizing a cruise or lowering still completes, and the next scheduled
    run copies these transfers' files, so callers add their ``Pass`` part
    after this one: the last part decides the job's outcome.

    Args:
        ovdm: The worker's ``OpenVDM`` instance.
        job_results: The job's results, whose ``parts`` the part is added to.
        title: The message's title.
        part_name: The part's name.
        names: The transfers' names.
    """
    reason = (f"Still running after {RUNNING_JOB_WAIT // 60} minutes, so they didn't get "
              f"their final pass: {', '.join(names)}")
    logging.warning("%s: %s", title, reason)
    ovdm.send_msg(title, reason)
    job_results['parts'].append({"partName": part_name, "result": "Fail", "reason": reason})
