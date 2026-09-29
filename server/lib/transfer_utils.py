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
    logging.debug('Transfer Command: %s', ' '.join(cmd))

    last_percent = -1
    recent = []    # last output lines, for the error message

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
            recent = (recent + [line])[-50:]

            percent = None
            if tool == 'rsync':
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
    if tool == 'rsync' and returncode == 23:
        errors = [line for line in recent if line.startswith('rsync:')]
        if errors and all(RSYNC_VANISHED_RE.match(line) for line in errors):
            ok_codes = (23,)    # only listed files that have since vanished
    if returncode not in ok_codes:
        error = TransferCommandError(tool, returncode, error_detail(tool, recent))
        logging.error("Transfer failed: %s", error)
        raise error
    if returncode != 0:
        logging.warning("%s exited with code %d (%s); treating as success",
                        tool, returncode, error_detail(tool, recent))

    return result
