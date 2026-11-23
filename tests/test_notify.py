"""Email when a run finishes (notify.py): the email's content, the address check, and
handing it to sendmail. sendmail itself is replaced with a stand-in; no email is sent."""

import subprocess
from types import SimpleNamespace

import pytest

from validate import notify


def _body(message):
    return message.get_content()


def test_successEmail():
    message = notify.runEmail("me@example.org", "Segment", True, None, 4325, "/data/analysis_X",
                              "analysis.yaml", "/data/analysis_X/_autoseg_logs/error_log_1.txt")

    assert message["To"] == "me@example.org"
    assert message["Subject"] == "validate: Segment run finished - success"
    assert _body(message) == (
        "Status: success\n"
        "Run time: 1 h 12 min 5 s\n"
        "\n"
        "Settings: analysis.yaml\n"
        "Folder:   /data/analysis_X\n"
        "The outputs and the task log (task_log.yaml) are in the same folder.\n"
        "The input data folder is listed in analysis.yaml under input: data_dir.\n")


def test_errorEmailGivesReasonAndErrorLog():
    message = notify.runEmail("me@example.org", "Segment", False, "2 of 20 patients failed", 42,
                              "/data/analysis_X", "analysis.yaml", "/data/analysis_X/_autoseg_logs/error_log_1.txt")

    assert message["Subject"] == "validate: Segment run finished - error"
    assert _body(message).startswith("Status: error (2 of 20 patients failed)\nRun time: 42 s\n")
    assert _body(message).endswith("\nError log: /data/analysis_X/_autoseg_logs/error_log_1.txt\n")


@pytest.mark.parametrize("address, valid", [
    ("name@example.org", True),
    ("first.last+tag@sub.example.org", True),
    ("", False),
    ("name@example", False),
    ("name example@example.org", False),
    ("a@example.org, b@example.org", False),
    ("a@example.org\nBcc: b@example.org", False),
], ids=["plain", "dots and plus", "empty", "no domain suffix", "space", "two addresses", "extra header"])
def test_isValidAddress(address, valid):
    assert notify.isValidAddress(address) is valid


@pytest.mark.parametrize("seconds, text", [(42, "42 s"), (200, "3 min 20 s"), (3600, "1 h 0 min 0 s")])
def test_formatDuration(seconds, text):
    assert notify.formatDuration(seconds) == text


@pytest.fixture
def sendmail(monkeypatch):
    """A stand-in sendmail: records the command and message, and exits with returncode."""
    calls = SimpleNamespace(cmd=None, input=None, returncode=0)

    def run(cmd, input=None, capture_output=False, timeout=None):
        calls.cmd, calls.input = cmd, input
        return SimpleNamespace(returncode=calls.returncode, stderr=b"queue full")

    monkeypatch.setattr(notify, "findSendmail", lambda: "/usr/sbin/sendmail")
    monkeypatch.setattr(notify.subprocess, "run", run)
    return calls


def test_emailHandedToSendmail(sendmail):
    notify.sendEmail(notify.runEmail("me@example.org", "Segment", True, None, 1, "/a", "analysis.yaml"))

    assert sendmail.cmd == ["/usr/sbin/sendmail", "-t", "-oi"]      # recipients from the To: header
    assert b"To: me@example.org" in sendmail.input


def test_sendmailFailureRaises(sendmail):
    sendmail.returncode = 75
    with pytest.raises(RuntimeError, match="sendmail failed \\(exit code 75\\): queue full"):
        notify.sendEmail(notify.runEmail("me@example.org", "Segment", True, None, 1, "/a", "analysis.yaml"))


def test_noSendmailRaises(monkeypatch):
    monkeypatch.setattr(notify, "findSendmail", lambda: None)
    with pytest.raises(RuntimeError, match="No sendmail on this machine"):
        notify.sendEmail(notify.runEmail("me@example.org", "Segment", True, None, 1, "/a", "analysis.yaml"))
