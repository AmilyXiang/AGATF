"""Tests for the vendor-neutral SSH transport tool (tools/ssh_client.py)."""
from tools.ssh_client import SshClient, SshResult


class _RecordingRunner:
    """Fake SSH runner capturing commands and returning a canned result."""

    def __init__(self, result: SshResult):
        self.result = result
        self.commands: list[str] = []

    def __call__(self, command: str) -> SshResult:
        self.commands.append(command)
        return self.result


def test_run_uses_injected_runner_and_returns_result():
    runner = _RecordingRunner(SshResult(ok=True, exit_status=0, stdout="online"))
    client = SshClient("10.0.0.5", runner=runner)

    result = client.run("show status")

    assert result.ok is True
    assert result.stdout == "online"
    assert runner.commands == ["show status"]


def test_run_reports_nonzero_exit_as_not_ok():
    runner = _RecordingRunner(SshResult(ok=False, exit_status=2, stderr="denied"))
    client = SshClient("10.0.0.5", runner=runner)

    result = client.run("reboot")

    assert result.ok is False
    assert result.exit_status == 2
    assert result.stderr == "denied"


def test_inline_password_takes_precedence_over_secret_ref(monkeypatch):
    monkeypatch.setenv("DEVICE_SSH_PW", "from-env")
    client = SshClient("10.0.0.5", secret_ref="DEVICE_SSH_PW", password="inline")

    assert client.resolve_password() == "inline"


def test_secret_ref_resolves_from_environment(monkeypatch):
    monkeypatch.setenv("DEVICE_SSH_PW", "from-env")
    client = SshClient("10.0.0.5", secret_ref="DEVICE_SSH_PW")

    assert client.resolve_password() == "from-env"


def test_resolve_password_empty_when_unset():
    client = SshClient("10.0.0.5")

    assert client.resolve_password() == ""
