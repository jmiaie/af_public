"""AegisFlow execution backends.

Three backends share one interface (``write_file`` / ``read_file`` /
``execute`` / ``cleanup``):

* :class:`LocalSandbox` is a **local executor, not isolated**. It scopes file
  paths to a workspace directory and runs commands as ordinary host processes
  with the caller's privileges. It is NOT a security boundary.
* :class:`NamespaceSandbox` runs commands under Linux ``unshare`` (user, PID,
  mount and, by default, network namespaces). If ``unshare`` is unusable it
  raises :class:`SandboxUnavailableError` instead of falling back to the host.
* :class:`DockerSandbox` runs commands in a throwaway container.

Commands are never passed to a host shell. ``execute`` accepts an argv list
(preferred) or a string, which is tokenised with :func:`shlex.split`; shell
syntax such as pipes, ``&&``, redirects and globs is therefore NOT interpreted.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from aegisflow.core.errors import (
    SandboxPermissionError,
    SandboxUnavailableError,
)

logger = logging.getLogger(__name__)

#: A command is either an argv sequence or a string tokenised with shlex.split.
Command = Union[str, Sequence[str]]


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_files: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:500],
            "stderr": self.stderr[:200],
            "output_files": self.output_files,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ── Shared helpers ───────────────────────────────────────────────────────────


def resolve_within(root: str, relative_path: str) -> str:
    """Resolve ``relative_path`` under ``root`` and refuse anything outside it.

    Both sides go through :func:`os.path.realpath` (so ``..`` segments and
    symlinks are resolved) and containment is checked with
    :func:`os.path.commonpath`, so a sibling such as ``<root>_evil`` is rejected.

    Args:
        root: Workspace root directory.
        relative_path: Caller-supplied path, relative to ``root``.

    Returns:
        The absolute, resolved target path.

    Raises:
        SandboxPermissionError: If the resolved path escapes ``root``.
    """
    root_real = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_real, relative_path))
    try:
        inside = os.path.commonpath([root_real, target]) == root_real
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        raise SandboxPermissionError(f"Path traversal detected: {relative_path}")
    return target


def to_argv(command: Command) -> List[str]:
    """Convert a command to an argv list without involving a shell.

    Args:
        command: An argv sequence, or a string split with :func:`shlex.split`.

    Returns:
        A non-empty list of arguments.

    Raises:
        ValueError: If the command is empty.
        TypeError: If the command is neither a string nor a sequence of strings.
    """
    if isinstance(command, str):
        argv = shlex.split(command)
    elif isinstance(command, (list, tuple)):
        if not all(isinstance(a, str) for a in command):
            raise TypeError("command argv must contain only strings")
        argv = list(command)
    else:
        raise TypeError("command must be a string or a list of strings")
    if not argv:
        raise ValueError("empty command")
    return argv


def _kill_process_group(proc: "subprocess.Popen[str]") -> None:
    """Kill the child's own process group (and nothing else)."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows
            proc.kill()
    except ProcessLookupError:
        pass


def run_in_own_group(argv: List[str], cwd: str, timeout: float) -> Tuple[int, str, str]:
    """Run ``argv`` in a new session; on timeout kill only that process group.

    Args:
        argv: Command arguments (no shell).
        cwd: Working directory for the child.
        timeout: Seconds before the child's process group is killed.

    Returns:
        ``(returncode, stdout, stderr)``.

    Raises:
        subprocess.TimeoutExpired: After the child's process group was killed.
    """
    proc = subprocess.Popen(  # nosec B603 - argv list, shell=False
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        proc.communicate()
        raise
    return proc.returncode, out, err


def _elapsed_ms(start: float) -> int:
    return int((time.time() - start) * 1000)


# ── LocalSandbox ─────────────────────────────────────────────────────────────


class LocalSandbox:
    """Local executor, not isolated.

    File access is confined to ``workspace_path`` but commands run as normal
    host processes with the caller's privileges, filesystem and network. Use
    :class:`NamespaceSandbox`, :class:`DockerSandbox`, or an external VM or
    container if commands may come from untrusted input (including LLM output).
    """

    def __init__(self, workspace_path: str = "./sandbox_workspace"):
        os.makedirs(workspace_path, exist_ok=True)
        self.workspace = os.path.realpath(workspace_path)
        self.isolation_level = "local"
        # Perf §5.1: cache ensured parent dirs so write_file doesn't re-stat
        # the full path on every call.
        self._known_dirs: set[str] = set()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for d in ["workspace", "uploads", "outputs", "logs"]:
            path = os.path.join(self.workspace, d)
            os.makedirs(path, exist_ok=True)
            self._known_dirs.add(path)
        self._known_dirs.add(self.workspace)

    def _resolve_path(self, relative_path: str) -> str:
        return resolve_within(self.workspace, relative_path)

    def write_file(self, relative_path: str, content: str) -> str:
        safe_path = self._resolve_path(relative_path)
        # Perf §5.1: skip makedirs when we've already materialized the parent.
        parent = os.path.dirname(safe_path)
        if parent not in self._known_dirs:
            os.makedirs(parent, exist_ok=True)
            self._known_dirs.add(parent)
        with open(safe_path, "w") as f:
            f.write(content)
        return safe_path

    def read_file(self, relative_path: str) -> str:
        safe_path = self._resolve_path(relative_path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError("File not found")
        with open(safe_path, "r") as f:
            return f.read()

    def execute(self, command: Command, timeout: int = 30) -> SandboxResult:
        """Run ``command`` on the host (no shell) with the workspace as cwd.

        Args:
            command: argv list, or a string tokenised with ``shlex.split``.
            timeout: Seconds before the command's process group is killed.

        Returns:
            A :class:`SandboxResult`.
        """
        start = time.time()
        try:
            argv = to_argv(command)
            code, out, err = run_in_own_group(argv, self.workspace, timeout)
            return SandboxResult(
                success=(code == 0),
                stdout=out,
                stderr=err,
                exit_code=code,
                duration_ms=_elapsed_ms(start),
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False, error="Timed out", exit_code=-1, duration_ms=_elapsed_ms(start)
            )
        except Exception as e:
            return SandboxResult(
                success=False, error=str(e), exit_code=-1, duration_ms=_elapsed_ms(start)
            )

    def cleanup(self) -> None:
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)
            self._known_dirs.clear()
            self._ensure_directories()


# ── NamespaceSandbox ─────────────────────────────────────────────────────────


class NamespaceSandbox:
    """Run commands under Linux ``unshare`` namespaces.

    Raises :class:`SandboxUnavailableError` from :meth:`execute` when
    ``unshare`` cannot create the namespaces; it never silently runs the
    command on the host instead.
    """

    def __init__(
        self,
        workspace_path: str = "./namespace_workspace",
        enable_network: bool = False,
        timeout: int = 120,
    ):
        os.makedirs(workspace_path, exist_ok=True)
        self.workspace = os.path.realpath(workspace_path)
        self.enable_network = enable_network
        self.timeout = timeout
        self.isolation_level = "namespace"
        self._id = uuid.uuid4().hex[:8]
        self._unshare_available = self._probe_unshare()

    def _unshare_prefix(self) -> List[str]:
        cmd = [
            "unshare",
            "--user",
            "--map-root-user",
            "--pid",
            "--mount",
            "--fork",
            "--kill-child",
            "--propagation",
            "private",
        ]
        if not self.enable_network:
            cmd.append("--net")
        return cmd

    def _probe_unshare(self) -> bool:
        """Check that unshare can actually create the namespaces we need."""
        if shutil.which("unshare") is None or shutil.which("true") is None:
            return False
        try:
            r = subprocess.run(  # nosec B603 - fixed argv
                self._unshare_prefix() + ["true"], capture_output=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    def _unshare_cmd(self, command: Command) -> List[str]:
        return self._unshare_prefix() + to_argv(command)

    def _resolve_path(self, relative_path: str) -> str:
        return resolve_within(self.workspace, relative_path)

    def write_file(self, relative_path: str, content: str) -> str:
        safe_path = self._resolve_path(relative_path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(content)
        return safe_path

    def read_file(self, relative_path: str) -> str:
        safe_path = self._resolve_path(relative_path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError("File not found")
        with open(safe_path, "r") as f:
            return f.read()

    def execute(self, command: Command, timeout: Optional[int] = None) -> SandboxResult:
        """Run ``command`` inside fresh namespaces (no shell).

        Args:
            command: argv list, or a string tokenised with ``shlex.split``.
            timeout: Seconds before the command's process group is killed.

        Returns:
            A :class:`SandboxResult`.

        Raises:
            SandboxUnavailableError: If ``unshare`` namespaces are unavailable.
        """
        start = time.time()
        timeout = timeout or self.timeout
        if not self._unshare_available:
            raise SandboxUnavailableError(
                "NamespaceSandbox requires a working `unshare` with unprivileged user "
                "namespaces; refusing to run the command unisolated. Use DockerSandbox, "
                "or LocalSandbox explicitly if host execution is acceptable."
            )
        os.makedirs(self.workspace, exist_ok=True)
        try:
            argv = self._unshare_cmd(command)
            code, out, err = run_in_own_group(argv, self.workspace, timeout)
            return SandboxResult(
                success=(code == 0),
                stdout=out,
                stderr=err,
                exit_code=code,
                duration_ms=_elapsed_ms(start),
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False, error="Timeout", exit_code=-1, duration_ms=_elapsed_ms(start)
            )
        except Exception as e:
            return SandboxResult(
                success=False, error=str(e), exit_code=-1, duration_ms=_elapsed_ms(start)
            )

    def cleanup(self) -> None:
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)


# ── DockerSandbox ────────────────────────────────────────────────────────────


class DockerSandbox:
    def __init__(
        self,
        image: str = "python:3.12-slim",
        workspace_path: str = "./docker_workspace",
        timeout: int = 120,
    ):
        self.image = image
        os.makedirs(workspace_path, exist_ok=True)
        self.workspace = os.path.realpath(workspace_path)
        self.container_name = "aegisflow-" + uuid.uuid4().hex[:8]
        self.timeout = timeout
        self.isolation_level = "docker"
        try:
            r = subprocess.run(  # nosec B603 B607 - fixed argv
                ["docker", "info"], capture_output=True, timeout=5
            )
            self._docker_available = r.returncode == 0
        except Exception:
            self._docker_available = False

    def _resolve_path(self, relative_path: str) -> str:
        return resolve_within(self.workspace, relative_path)

    def write_file(self, relative_path: str, content: str) -> str:
        safe_path = self._resolve_path(relative_path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(content)
        return safe_path

    def read_file(self, relative_path: str) -> str:
        safe_path = self._resolve_path(relative_path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError("File not found")
        with open(safe_path, "r") as f:
            return f.read()

    def execute(self, command: Command, working_dir: str = "/workspace") -> SandboxResult:
        """Run ``command`` in a throwaway container.

        A string is run with ``sh -c`` *inside the container*; an argv list is
        passed to the container as-is. No host shell is involved either way.
        """
        start = time.time()
        if not self._docker_available:
            return SandboxResult(
                success=False,
                error="Docker not available",
                exit_code=-1,
                duration_ms=_elapsed_ms(start),
            )
        os.makedirs(self.workspace, exist_ok=True)
        inner = ["sh", "-c", command] if isinstance(command, str) else to_argv(command)
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            self.container_name,
            "-v",
            self.workspace + ":" + working_dir,
            "-w",
            working_dir,
            self.image,
        ] + inner
        try:
            result = subprocess.run(  # nosec B603 B607 - argv list
                docker_cmd, capture_output=True, text=True, timeout=self.timeout
            )
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=_elapsed_ms(start),
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", self.container_name], capture_output=True)
            return SandboxResult(
                success=False, error="Timeout", exit_code=-1, duration_ms=_elapsed_ms(start)
            )
        except Exception as e:
            return SandboxResult(
                success=False, error=str(e), exit_code=-1, duration_ms=_elapsed_ms(start)
            )

    def cleanup(self) -> None:
        subprocess.run(["docker", "kill", self.container_name], capture_output=True)


Sandbox = NamespaceSandbox
