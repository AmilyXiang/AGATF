"""Vendor-neutral SSH command tool.

Runs shell commands on a device over SSH, for OEM products controlled by a CLI
instead of HTTP. Mirrors ``http_client``: the actual transport is injectable
(a ``runner`` callable) so command mappings can be tested without a live host.

The default runner uses paramiko, imported lazily so this module stays
import-safe without the dependency; install paramiko for real connections or
inject a runner (e.g. subprocess/OpenSSH) for other environments. Credentials
follow the same rule as the HTTP tool: an inline password takes precedence,
otherwise the secret reference is resolved from the environment.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class SshResult:
    """Outcome of one remote command."""

    ok: bool
    exit_status: int
    stdout: str = ""
    stderr: str = ""


# Runner contract: (command) -> SshResult. Encapsulates the actual transport.
Runner = Callable[[str], SshResult]


class SshClient:
    """Executes shell commands on a device over SSH."""

    def __init__(
        self,
        host: str | None = None,
        *,
        username: str = "admin",
        port: int = 22,
        secret_ref: str | None = None,
        password: str | None = None,
        key_file: str | None = None,
        timeout: int = 10,
        strict_host_key: bool = False,
        runner: Runner | None = None,
    ) -> None:
        self.host = host
        self.username = username
        self.port = port
        self.secret_ref = secret_ref
        # Inline password (internal repos) takes precedence over secret_ref.
        self.password = password
        self.key_file = key_file
        self.timeout = timeout
        # Reject unknown host keys instead of auto-accepting (safer, opt-in).
        self.strict_host_key = strict_host_key
        self._runner = runner

    def resolve_password(self) -> str:
        return self.password or (os.environ.get(self.secret_ref, "") if self.secret_ref else "")

    def run(self, command: str) -> SshResult:
        runner = self._runner or self._paramiko_runner
        result = runner(command)
        logger.debug("[ssh %s] %s -> exit=%s ok=%s", self.host, command, result.exit_status, result.ok)
        return result

    def _paramiko_runner(self, command: str) -> SshResult:
        try:
            import paramiko  # lazy: only needed for real connections
        except ImportError as exc:
            raise RuntimeError(
                "paramiko is required for live SSH; run 'pip install paramiko' or inject a runner"
            ) from exc

        client = paramiko.SSHClient()
        policy = paramiko.RejectPolicy() if self.strict_host_key else paramiko.AutoAddPolicy()
        client.set_missing_host_key_policy(policy)
        try:
            client.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.resolve_password() or None,
                key_filename=self.key_file,
                timeout=self.timeout,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=self.timeout)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            return SshResult(ok=exit_status == 0, exit_status=exit_status, stdout=out, stderr=err)
        except Exception as exc:  # surface transport failures as a failed result
            logger.warning("[ssh %s] command failed: %s", self.host, exc)
            return SshResult(ok=False, exit_status=-1, stderr=str(exc))
        finally:
            client.close()
