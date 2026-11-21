"""Run rsync and rclone transfer commands for the transfer workers.

One implementation, shared by the collection system, cruise data and
ship-to-shore transfer workers (and the cruise worker's PublicData copy), of
running a transfer command while reporting progress and collecting the new,
updated and deleted files. A command that fails raises
:class:`TransferCommandError`, so the caller can fail the transfer instead of
reporting it as successful (#230). Also the helpers that mask passwords in
what the workers log (:func:`redact_command`, :func:`redact_payload`), and
the limits on rsync over the network: its I/O timeout for listings and
copies, and the time limit on listing a collection system transfer's rsync
or SSH source (:func:`rsync_timeouts`, :func:`run_listing_command`, #689, #711).
"""

import json
import logging
import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from typing import Any, Callable, Optional, Union

# Transfer password fields, as in the PHP Helpers\TransferCredentials::FIELDS
PASSWORD_FIELDS = ('rsyncPass', 'smbPass', 'sshPass', 'ftpPass')

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

# Limits on rsync over the network, in seconds, for those openvdm.yaml's
# rsyncTimeouts block doesn't set: rsync's --timeout (nothing received) for
# listings and copies (#689, #711), and the time a source listing may take
RSYNC_TIMEOUT_DEFAULTS = {'ioTimeout': 300, 'listingTimeLimit': 3600}

# The ssh that rsync lists and copies over: it gives up connecting after 30 s,
# and on a connection that stops answering 4 keepalives 15 s apart (#689, #711)
SSH_COMMAND = 'ssh -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=4'

# A file listed for the transfer (--files-from) but gone by the time rsync
# looks for it gives code 23 with only this error; that's also a vanished file
RSYNC_VANISHED_RE = re.compile(r'^rsync: (\[sender\] )?link_stat ".*" failed: No such file or directory')

# rclone refuses a file that changed while it was being copied and, when that
# happens on every attempt, exits with code 6. Like rsync's vanished files
# that's normal for live data: the file is copied on a later run (#668)
RCLONE_CHANGED_CODE = 6
RCLONE_ERROR_RE = re.compile(r'\bERROR\s*:\s*(.*)$')
RCLONE_CHANGED_RE = re.compile(r"^(.+): Failed to copy: can't copy - source file is being updated")
# The ERROR lines that follow from those: each attempt's summary, the final one
# (rclone 1.60) and, for sync, the skipped deletions
RCLONE_FOLLOW_ON_RE = re.compile(r'^(Attempt \d+/\d+ failed with|Failed to (sync|copy)( with \d+ errors)?:)')
RCLONE_NOT_DELETING_RE = re.compile(r': not deleting (files|directories) as there were IO errors$')


class TransferCommandError(Exception):
    """A transfer command exited with an error.

    Attributes:
        returncode: The command's exit code.
        detail: The command's most specific error line.
        files: The files the command transferred before it failed: ``new``,
            ``updated`` and ``deleted`` lists, as :func:`run_transfer_command`
            returns them (#239).
    """

    def __init__(self, command: str, returncode: int, detail: str, files: Optional[dict] = None,
                 message: Optional[str] = None):
        """Record the failure.

        Args:
            command: The tool, e.g. ``'rsync'``.
            returncode: Its exit code.
            detail: Its most specific error line.
            files: What it transferred before failing.
            message: The error's text, in place of "<command> exited with
                code <returncode>: <detail>", e.g. for a command OpenVDM
                ended (#711).
        """
        self.returncode = returncode
        self.detail = detail
        self.files = files if files is not None else {'new': [], 'updated': [], 'deleted': []}
        super().__init__(message or (f"{command} exited with code {returncode}"
                                     + (f": {detail}" if detail else "")))


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



def _redact_passwords(value: Any) -> Any:
    """Return a copy of *value* with every non-empty password field masked.

    Args:
        value: Parsed JSON: a dict, list or scalar, nested to any depth.

    Returns:
        The same structure, with the value of each :data:`PASSWORD_FIELDS`
        key replaced by ``****`` unless it's empty (an empty value shows that
        no password was given).
    """
    if isinstance(value, dict):
        return {key: '****' if key in PASSWORD_FIELDS and val else _redact_passwords(val)
                for key, val in value.items()}
    if isinstance(value, list):
        return [_redact_passwords(item) for item in value]
    return value


def redact_payload(payload: Union[str, bytes, dict, list], indent: Optional[int] = None) -> str:
    """Return a Gearman job payload for logging, with transfer passwords masked.

    A Test Setup job's payload carries the add or edit form's fields,
    including any password typed into it, so the workers' ``payload: ...``
    debug lines must not log it as it is (#430).

    Args:
        payload: The job's data (a JSON string or bytes), or the payload
            already parsed.
        indent: Passed to :func:`json.dumps`, e.g. ``2`` to pretty-print.

    Returns:
        The payload as JSON with each non-empty ``rsyncPass``, ``smbPass``,
        ``sshPass`` and ``ftpPass`` value, at any depth, replaced by ``****``.
        A payload that isn't valid JSON isn't shown.
    """
    if isinstance(payload, (str, bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except ValueError:
            return "<not valid JSON; not shown>"
    return json.dumps(_redact_passwords(payload), indent=indent)

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


def _changed_files(paths: list) -> str:
    """Return the files rclone didn't copy because they changed, for a warning.

    Args:
        paths: The files, in the order rclone reported them.

    Returns:
        e.g. ``1 file (a.log)`` or ``12 files (a.log, …, j.log and 2 more)``.
    """
    shown = ', '.join(paths[:10]) + (f' and {len(paths) - 10} more' if len(paths) > 10 else '')
    return f"{len(paths)} file{'s' if len(paths) > 1 else ''} ({shown})"


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


def _rsync_bytes_read(pid: int) -> Optional[int]:
    """Return the bytes read so far by the rsync processes of a command (#711).

    The sum of ``rchar`` in ``/proc/<pid>/io`` over the ``rsync`` processes
    among *pid* and its descendants. It grows while rsync receives anything,
    file list entries and checksums included, so it shows a copy is still
    working when rsync prints nothing (it prints nothing for unchanged
    files). ``ssh`` isn't counted: its keepalive replies keep arriving after
    the other end's rsync has stopped.

    Args:
        pid: The command's process ID, e.g. ``sshpass`` or ``rsync``.

    Returns:
        int | None: The bytes read, or ``None`` without ``/proc`` (e.g. on
        macOS) or once the command has exited.
    """
    if not os.path.isdir(f'/proc/{pid}'):
        return None
    parents = {}
    names = {}
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open(f'/proc/{entry}/stat', encoding='utf-8') as stat:
                fields = stat.read()
        except OSError:
            continue
        # "<pid> (<comm>) <state> <ppid> ...": comm may contain spaces
        name = fields[fields.find('(') + 1:fields.rfind(')')]
        names[int(entry)] = name
        parents[int(entry)] = int(fields[fields.rfind(')') + 2:].split()[1])
    tree, todo = set(), [pid]
    while todo:
        current = todo.pop()
        tree.add(current)
        todo.extend(child for child, parent in parents.items() if parent == current and child not in tree)
    total = 0
    for member in tree:
        if names.get(member) != 'rsync':
            continue
        try:
            with open(f'/proc/{member}/io', encoding='utf-8') as io:
                total += next(int(line.split()[1]) for line in io if line.startswith('rchar:'))
        except (OSError, StopIteration, ValueError):
            continue
    return total


def run_transfer_command(cmd: list, file_count: int,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                         progress_callback: Optional[Callable[[int], None]] = None,
                         should_stop: Optional[Callable[[], bool]] = None,
                         idle_timeout: int = 0, poll_interval: float = 1.0) -> dict:
    """Run an rsync or rclone transfer command and collect the files it transferred.

    Streams the command's output, reporting progress from rsync's ``to-chk=``
    or rclone's ``Transferred: …, NN%`` lines, and collects files from rsync's
    itemized changes (``-i``) or rclone's per-file log lines (``-v``).

    Args:
        cmd: The command, starting with ``rsync`` or ``rclone`` (or a wrapper
            such as ``sshpass``, followed by one of them).
        file_count: Number of files expected; with ``0`` the command isn't run.
        progress_callback: Called with the percentage (0–100) when it changes.
        should_stop: Polled every *poll_interval* seconds, and for each output
            line; when it returns ``True``, the command is terminated and the
            files so far are returned. It's checked even while the command
            prints nothing, e.g. a copy that has stalled (#711).
        idle_timeout: For rsync to or from another host: seconds the
            command's rsync processes may read nothing and print nothing
            before the command is ended and fails (#711); 0 for none. It
            backs up rsync's ``--timeout``, which doesn't end a pull whose
            other end hangs. It needs ``/proc`` (Linux), and is off without it.
        poll_interval: Seconds between those checks.

    Returns:
        dict: ``new``, ``updated`` and ``deleted`` (lists of paths relative to
        the source/destination) and ``stopped`` (bool).

    Raises:
        TransferCommandError: If the command exits with an error, unless it
            was stopped, or is ended by *idle_timeout*. For rsync, code 24 (source files vanished), and code
            23 when its only errors are listed files that no longer exist,
            aren't errors; for rclone, code 6 when its only errors are files
            that changed while being copied (#668).
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
    changed = {}          # rclone: files that changed while being copied, in order
    deletions_skipped = False

    timed_out = False     # ended for reading nothing for idle_timeout seconds (#711)

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        # The output is read in a thread, so Stop and the idle timeout are
        # checked even while the command prints nothing (#711)
        lines = queue.Queue()

        def _read_output():
            for output_line in proc.stdout:
                lines.put(output_line)
            lines.put(None)

        threading.Thread(target=_read_output, daemon=True).start()
        last_read = _rsync_bytes_read(proc.pid) if idle_timeout else None
        last_active = time.monotonic()

        while True:
            try:
                line = lines.get(timeout=poll_interval)
            except queue.Empty:
                line = ''
            if line is None:
                break

            if should_stop and should_stop():
                logging.info("Stopping")
                proc.terminate()
                result['stopped'] = True
                break

            if idle_timeout and last_read is not None:
                read = _rsync_bytes_read(proc.pid)
                now = time.monotonic()
                if line or (read is not None and read != last_read):
                    last_active = now
                    last_read = read if read is not None else last_read
                elif now - last_active >= idle_timeout:
                    logging.error("%s read nothing for %d s; ending it", tool, idle_timeout)
                    proc.terminate()
                    timed_out = True
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
                match = RCLONE_ERROR_RE.search(line)
                if match:
                    error = match.group(1)
                    changed_file = RCLONE_CHANGED_RE.match(error)
                    if changed_file:
                        changed[changed_file.group(1)] = None
                    elif RCLONE_NOT_DELETING_RE.search(error):
                        deletions_skipped = True
                    elif not RCLONE_FOLLOW_ON_RE.match(error):
                        error_count += 1
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

        try:
            returncode = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait()

    if result['stopped']:
        return result

    if timed_out:
        error = TransferCommandError(
            tool, returncode, '', {key: result[key] for key in ('new', 'updated', 'deleted')},
            message=f"{tool} received nothing for {idle_timeout} s and was ended "
                    "(rsyncTimeouts ioTimeout in openvdm.yaml)")
        logging.error("Transfer failed: %s", error)
        raise error

    ok_codes = RSYNC_OK_CODES if tool == 'rsync' else (0,)
    if tool == 'rsync' and returncode == 23 and vanished_count and not error_count:
        ok_codes = (23,)    # only listed files that have since vanished
    if tool == 'rclone' and returncode == RCLONE_CHANGED_CODE and changed and not error_count:
        ok_codes = (RCLONE_CHANGED_CODE,)    # only files that changed while being copied
    if returncode not in ok_codes:
        detail = (_rsync_failure_detail(errors, error_count, recent) if tool == 'rsync'
                  else error_detail(tool, recent))
        error = TransferCommandError(tool, returncode, detail,
                                     {key: result[key] for key in ('new', 'updated', 'deleted')})
        logging.error("Transfer failed: %s", error)
        raise error
    if returncode == 23:
        logging.warning("rsync exited with code 23: %d listed file%s vanished before the "
                        "transfer; treating as success", vanished_count, 's' if vanished_count > 1 else '')
    elif tool == 'rclone' and returncode == RCLONE_CHANGED_CODE:
        logging.warning("rclone exited with code 6: %s changed while being copied and will be "
                        "copied on a later transfer%s; treating as success",
                        _changed_files(list(changed)),
                        " (rclone skipped this transfer's deletions)" if deletions_skipped else '')
    elif returncode != 0:
        logging.warning("%s exited with code %d (%s); treating as success",
                        tool, returncode, error_detail(tool, recent))

    return result


def rsync_timeouts(config: dict) -> dict:
    """Return the limits on rsync over the network, from ``openvdm.yaml``.

    The ``rsyncTimeouts`` block's ``ioTimeout`` (rsync's ``--timeout``: how
    long a listing or copy may receive nothing, #689, #711) and
    ``listingTimeLimit`` (how long listing a collection system transfer's
    source may take), in seconds; 0 turns a limit off. An unset or invalid
    value uses :data:`RSYNC_TIMEOUT_DEFAULTS`; an invalid one is logged.

    Args:
        config: The ``openvdm.yaml`` settings, e.g. ``OpenVDM.config``.

    Returns:
        dict: ``{'ioTimeout': int, 'listingTimeLimit': int}``.
    """
    block = config.get('rsyncTimeouts')
    if not isinstance(block, dict):
        block = {}
    limits = dict(RSYNC_TIMEOUT_DEFAULTS)
    for key, default in RSYNC_TIMEOUT_DEFAULTS.items():
        value = block.get(key)
        if value in (None, ''):
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            logging.warning("openvdm.yaml: rsyncTimeouts %s must be a whole number of seconds "
                            "(0 for no limit), not %r; using %d", key, value, default)
            continue
        limits[key] = value
    return limits


def run_listing_command(cmd: list, should_stop: Optional[Callable[[], bool]] = None,
                        time_limit: int = 0,
                        poll_interval: float = 1.0) -> tuple[subprocess.CompletedProcess, Optional[str]]:
    """Run a source listing command, ending it on Stop or when it takes too long.

    Like ``subprocess.run(cmd, capture_output=True, text=True)``, but checks
    *should_stop* and the time every *poll_interval* seconds, and ends the
    command (``terminate``, then ``kill`` if it's still running 10 s later)
    when the job is stopped or *time_limit* has passed (#689).

    Args:
        cmd: The listing command, e.g. ``rsync -r ...`` or ``sshpass ... rsync ...``.
        should_stop: Returns ``True`` when the job has been stopped.
        time_limit: Seconds the command may run; 0 for no limit.
        poll_interval: Seconds between checks.

    Returns:
        tuple: The finished command (``CompletedProcess``, with its output so
        far if it was ended), and ``None`` if it ran to the end, ``'stopped'``
        or ``'timed out'``.
    """
    started = time.monotonic()
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=poll_interval)
                return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr), None
            except subprocess.TimeoutExpired:
                pass
            if should_stop and should_stop():
                ended = 'stopped'
            elif time_limit and time.monotonic() - started >= time_limit:
                ended = 'timed out'
            else:
                continue
            logging.info("Ending the listing: %s", ended)
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr), ended
