"""Email the user when a run finishes, through the machine's own mail system (sendmail).

The email carries only the run's status and duration and where to find its files: the
settings file (analysis.yaml), the folder holding it and the run's outputs, and the error
log when there were errors. No patient data or results. The address isn't saved.
"""

import re
import shutil
import subprocess
from email.message import EmailMessage
from pathlib import Path

# Where sendmail usually is when it isn't on the PATH (e.g. launched from a desktop)
SENDMAIL_PATHS = ("/usr/sbin/sendmail", "/usr/lib/sendmail")
# One address, no spaces, separators or line breaks (which could add recipients or headers)
_ADDRESS = re.compile(r"[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+")


def isValidAddress(address):
    """True if address is a single plain email address (e.g. name@example.org)."""
    return bool(_ADDRESS.fullmatch(address or ""))


def findSendmail():
    """Path to sendmail, or None if this machine has none."""
    found = shutil.which("sendmail")
    if found:
        return found
    return next((path for path in SENDMAIL_PATHS if Path(path).is_file()), None)


def formatDuration(seconds):
    """e.g. "1 h 12 min 5 s", "3 min 20 s", "42 s"."""
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [f"{hours} h"] * bool(hours) + [f"{minutes} min"] * bool(hours or minutes) + [f"{secs} s"]
    return " ".join(parts)


def runEmail(address, tab, succeeded, reason, seconds, analysisDir, settingsFile, errorLogPath=None):
    """The notification email for a finished run.

    Args:
        address (str): recipient.
        tab (str): the run's tab, e.g. "Segment".
        succeeded (bool): True if the run finished with no errors.
        reason (str or None): why the status is error (e.g. "2 of 20 patients failed").
        seconds (float): run time.
        analysisDir (str): the analysis folder.
        settingsFile (str): file name of the settings in analysisDir (analysis.yaml).
        errorLogPath (str or None): the run's error log, listed when the status is error.

    Returns:
        email.message.EmailMessage
    """
    status = "success" if succeeded else "error"
    lines = [f"Status: {status}" + (f" ({reason})" if reason else ""),
             f"Run time: {formatDuration(seconds)}",
             "",
             f"Settings: {settingsFile}",
             f"Folder:   {analysisDir}",
             "The outputs and the task log (task_log.yaml) are in the same folder.",
             f"The input data folder is listed in {settingsFile} under input: data_dir."]
    if not succeeded and errorLogPath:
        lines += ["", f"Error log: {errorLogPath}"]
    message = EmailMessage()
    message["To"] = address
    message["Subject"] = f"validate: {tab} run finished - {status}"
    message.set_content("\n".join(lines) + "\n")
    return message


def sendEmail(message, timeout=30):
    """Hand message to the machine's mail system (sendmail).

    Delivery depends on the machine's mail set-up: sendmail accepting the message doesn't
    mean it was delivered.

    Raises:
        RuntimeError: there's no sendmail, or it refused the message.
    """
    sendmail = findSendmail()
    if sendmail is None:
        raise RuntimeError("No sendmail on this machine; its mail system isn't set up.")
    try:
        result = subprocess.run([sendmail, "-t", "-oi"], input=message.as_bytes(),
                                capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"sendmail didn't respond within {timeout} s.") from None
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"sendmail failed (exit code {result.returncode}){': ' + detail if detail else ''}")
