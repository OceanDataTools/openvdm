"""Run rsync and rclone transfer commands for the transfer workers.

One implementation, shared by the collection system, cruise data and
ship-to-shore transfer workers (and the cruise worker's PublicData copy), of
running a transfer command while reporting progress and collecting the new,
updated and deleted files. A command that fails raises
:class:`TransferCommandError`, so the caller can fail the transfer instead of
reporting it as successful (#230).
"""

import logging
import os
import re
import subprocess
from collections import deque
from typing import Callable, Optional

# rsync --progress: "to-chk=<remaining>/<total>"
TO_CHK_RE = re.compile(r'to-chk=(\d+)/(\d+)')

# rclone --progress: "Transferred: 1.2 MiB / 3.4 MiB, 35%, ..."
RCLONE_PROGRESS_RE = re.compile(r'Transferred:\s+[\d.]+\s*\w+\s+/\s+[\d.]+\s*\w+,\s+(\d+)%')

# rsync --itemize-changes: ">f+++++++++ path" (new), ">f.st...... path" (updated);
# "<f" when sending to a remote
RSYNC_FILE_RE = re.compile(r'^[<>]f([+.c])\S*\s+(.+)$')

# rclone -v: "INFO  : path: Copied (new)" (1.53 and later)
RCLONE_FILE_RE = re.compile(
    r'INFO\s*:\s*(.+): (Copied \(new\)|Copied \(replaced existing\)|Deleted)\s*$')

# rsync exit codes that don't mean the transfer failed: 24 is "some source
# files vanished before they could be transferred", normal for live data
RSYNC_OK_CODES = (0, 24)

# A file listed for the transfer (--files-from) but gone by the time rsync
# looks for it gives code 23 with only this error; that's also a vanished file
RSYNC_VANISHED_RE = re.compile(r'^rsync: (\[sender\] )?link_stat ".*" failed: No such file or directory')


class TransferCommandError(Exception):
    """A transfer command exited with an error.

    Attributes:
        returncode: The command's exit code.
        detail: The command's most specific error line.
    """

    def __init__(self, command: str, returncode: int, detail: str):
        self.returncode = returncode
        self.detail = detail
        super().__init__(f"{command} exited with code {returncode}"
                         + (f": {detail}" if detail else ""))


def redact_command(cmd: list) -> str:
    """Return a command line for logging, with any ``sshpass -p`` password masked.

    Args:
        cmd: The command as a list of strings.

    Returns:
        The command joined with spaces, with the argument after
        ``sshpass -p`` replaced by ``****`` (#240).
    """
    parts = list(cmd)
    for i in range(len(parts) - 2):
        if os.path.basename(parts[i]) == 'sshpass' and parts[i + 1] == '-p':
            parts[i + 2] = '****'
    return ' '.join(parts)


def _rsync_failure_detail(errors: list, error_count: int, recent) -> str:
    """Return the reason for a failed rsync command.

    Args:
        errors: The first error lines that aren't vanished listed files.
        error_count: How many such error lines rsync printed in all.
        recent: rsync's last output lines, used when there are no errors.

    Returns:
        The first error line, and how many more there were, or the most
        specific line from *recent*.
    """
    if not errors:
        return error_detail('rsync', recent)
    more = error_count - 1
    return errors[0] + (f" (and {more} more error{'s' if more > 1 else ''})" if more else '')


def error_detail(tool: str, lines: list) -> str:
    """Return the most specific error line from a command's output.

    Args:
        tool: ``'rsync'`` or ``'rclone'``.
        lines: The command's output lines (most recent last).

    Returns:
        The error line, without rclone's timestamp and level, or ``''``.
    """
    if tool == 'rsync':
        # "@ERROR: <cause>" (from an rsync daemon, e.g. an unknown module) and
        # "rsync: <cause>" are more useful than "rsync error: ... (code N)"
        for prefix in ('@ERROR', 'rsync:', 'rsync error:'):
            matches = [line for line in lines if line.startswith(prefix)]
            if matches:
                return matches[-1]
        return ''

    matches = [line for line in lines if 'Failed to' in line or 'ERROR' in line]
    if not matches:
        return ''
    return re.sub(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\s+)?([A-Z]+\s*:\s*)?', '', matches[-1])


def run_transfer_command(cmd: list, file_count: int,
                         progress_callback: Optional[Callable[[int], None]] = None,
                         should_stop: Optional[Callable[[], bool]] = None) -> dict:
    """Run an rsync or rclone transfer command and collect the files it transferred.

    Streams the command's output, reporting progress from rsync's ``to-chk=``
    or rclone's ``Transferred: …, NN%`` lines, and collects files from rsync's
    itemized changes (``-i``) or rclone's per-file log lines (``-v``).

    Args:
        cmd: The command, starting with ``rsync`` or ``rclone`` (or a wrapper
            such as ``sshpass``, followed by one of them).
        file_count: Number of files expected; with ``0`` the command isn't run.
        progress_callback: Called with the percentage (0–100) when it changes.
        should_stop: Polled for each output line; when it returns ``True``, the
            command is terminated and the files so far are returned.

    Returns:
        dict: ``new``, ``updated`` and ``deleted`` (lists of paths relative to
        the source/destination) and ``stopped`` (bool).

    Raises:
        TransferCommandError: If the command exits with an error, unless it
            was stopped. For rsync, code 24 (source files vanished), and code
            23 when its only errors are listed files that no longer exist,
            aren't errors.
    """
    result = {'new': [], 'updated': [], 'deleted': [], 'stopped': False}

    if file_count == 0:
        logging.info("Skipping Transfer Command: nothing to transfer")
        return result

    tool = next((os.path.basename(part) for part in cmd
                 if os.path.basename(part) in ('rsync', 'rclone')), os.path.basename(cmd[0]))
    logging.debug('Transfer Command: %s', redact_command(cmd))

    last_percent = -1
    recent = deque(maxlen=50)    # last output lines, for the error message
    # rsync prints its errors as they happen, often long before it exits, so
    # they're collected separately from the recent lines (#237)
    errors = []           # the first errors that aren't vanished listed files
    error_count = 0
    vanished_count = 0

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        for line in proc.stdout:
            if should_stop and should_stop():
                logging.info("Stopping")
                proc.terminate()
                result['stopped'] = True
                break

            line = line.strip()
            if not line:
                continue
            recent.append(line)

            percent = None
            if tool == 'rsync':
                if line.startswith(('rsync:', '@ERROR')):
                    if RSYNC_VANISHED_RE.match(line):
                        vanished_count += 1
                    else:
                        error_count += 1
                        if len(errors) < 10:
                            errors.append(line)
                match = RSYNC_FILE_RE.match(line)
                if match:
                    result['new' if match.group(1) == '+' else 'updated'].append(match.group(2))
                elif line.startswith('*deleting'):
                    result['deleted'].append(line.split(None, 1)[1])
                match = TO_CHK_RE.search(line)
                if match and int(match.group(2)) > 0:
                    remaining, total = int(match.group(1)), int(match.group(2))
                    percent = int(100 * (total - remaining) / total)
            else:
                match = RCLONE_FILE_RE.search(line)
                if match:
                    path, action = match.group(1), match.group(2)
                    result['new' if action == 'Copied (new)' else
                           'updated' if action.startswith('Copied') else 'deleted'].append(path)
                match = RCLONE_PROGRESS_RE.search(line)
                if match:
                    percent = int(match.group(1))

            if percent is not None:
                percent = max(last_percent, min(100, percent))
                if percent != last_percent:
                    logging.info("Progress Update: %d%%", percent)
                    if progress_callback:
                        progress_callback(percent)
                    last_percent = percent

        returncode = proc.wait()

    if result['stopped']:
        return result

    ok_codes = RSYNC_OK_CODES if tool == 'rsync' else (0,)
    if tool == 'rsync' and returncode == 23 and vanished_count and not error_count:
        ok_codes = (23,)    # only listed files that have since vanished
    if returncode not in ok_codes:
        detail = (_rsync_failure_detail(errors, error_count, recent) if tool == 'rsync'
                  else error_detail(tool, recent))
        error = TransferCommandError(tool, returncode, detail)
        logging.error("Transfer failed: %s", error)
        raise error
    if returncode == 23:
        logging.warning("rsync exited with code 23: %d listed file%s vanished before the "
                        "transfer; treating as success", vanished_count, 's' if vanished_count > 1 else '')
    elif returncode != 0:
        logging.warning("%s exited with code %d (%s); treating as success",
                        tool, returncode, error_detail(tool, recent))

    return result
