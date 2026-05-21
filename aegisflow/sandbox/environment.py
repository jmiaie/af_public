"""AegisFlow Sandbox Layer -- v2."""

import os, shutil, logging, subprocess, uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from aegisflow.core.errors import (
    SandboxPermissionError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)

logger = logging.getLogger(__name__)

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


class LocalSandbox:
    def __init__(self, workspace_path: str = "./sandbox_workspace"):
        self.workspace = os.path.abspath(workspace_path)
        self.isolation_level = "local"
        # Perf §5.1: cache ensured parent dirs so write_file doesn't re-stat
        # the full path on every call.
        self._known_dirs: set = set()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for d in ["workspace", "uploads", "outputs", "logs"]:
            path = os.path.join(self.workspace, d)
            os.makedirs(path, exist_ok=True)
            self._known_dirs.add(path)
        self._known_dirs.add(self.workspace)

    def _resolve_path(self, relative_path: str) -> str:
        target = os.path.abspath(os.path.join(self.workspace, relative_path))
        if not target.startswith(self.workspace):
            raise SandboxPermissionError(f"Path traversal detected: {relative_path}")
        return target

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

    def execute(self, command: str, timeout: int = 30) -> SandboxResult:
        import time
        start = time.time()
        try:
            result = subprocess.run(
                command, shell=True, cwd=self.workspace,
                capture_output=True, text=True, timeout=timeout,
            )
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout, stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=int((time.time() - start) * 1000),
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(success=False, error="Timed out", exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))
        except Exception as e:
            return SandboxResult(success=False, error=str(e), exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))

    def cleanup(self) -> None:
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)
            self._ensure_directories()


class NamespaceSandbox:
    def __init__(self, workspace_path: str = "./namespace_workspace", enable_network: bool = False, timeout: int = 120):
        self.workspace = os.path.abspath(workspace_path)
        self.enable_network = enable_network
        self.timeout = timeout
        self.isolation_level = "namespace"
        self._id = uuid.uuid4().hex[:8]
        try:
            subprocess.run(["unshare", "--help"], capture_output=True, timeout=5, check=True)
            self._unshare_available = True
        except Exception:
            self._unshare_available = False

    def _unshare_cmd(self, command: str) -> List[str]:
        cmd = ["unshare", "--user", "--map-root", "--uid-map=0 1000 1", "--gid-map=0 1000 1",
               "--pid", "--mount", "--fork", "--mount-propagation", "private"]
        if not self.enable_network:
            cmd.append("--net")
        cmd.extend(["bash", "-c", "cd " + self.workspace + " && " + command])
        return cmd

    def _resolve_path(self, relative_path: str) -> str:
        target = os.path.abspath(os.path.join(self.workspace, relative_path))
        if not target.startswith(self.workspace):
            raise SandboxPermissionError(f"Path traversal detected: {relative_path}")
        return target

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

    def execute(self, command: str, timeout: Optional[int] = None) -> SandboxResult:
        import time
        start = time.time()
        timeout = timeout or self.timeout
        os.makedirs(self.workspace, exist_ok=True)
        if not self._unshare_available:
            local = LocalSandbox(self.workspace)
            return local.execute(command, timeout=timeout)
        try:
            result = subprocess.run(self._unshare_cmd(command), capture_output=True, text=True, timeout=timeout)
            return SandboxResult(success=(result.returncode == 0), stdout=result.stdout,
                                   stderr=result.stderr, exit_code=result.returncode,
                                   duration_ms=int((time.time() - start) * 1000))
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-9", "-P", str(os.getpid())], capture_output=True)
            return SandboxResult(success=False, error="Timeout", exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))
        except Exception as e:
            return SandboxResult(success=False, error=str(e), exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))

    def cleanup(self) -> None:
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)


class DockerSandbox:
    def __init__(self, image: str = "python:3.12-slim", workspace_path: str = "./docker_workspace", timeout: int = 120):
        self.image = image
        self.workspace = os.path.abspath(workspace_path)
        self.container_name = "aegisflow-" + uuid.uuid4().hex[:8]
        self.timeout = timeout
        self.isolation_level = "docker"
        try:
            r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            self._docker_available = (r.returncode == 0)
        except Exception:
            self._docker_available = False

    def _resolve_path(self, relative_path: str) -> str:
        target = os.path.abspath(os.path.join(self.workspace, relative_path))
        if not target.startswith(self.workspace):
            raise SandboxPermissionError(f"Path traversal detected: {relative_path}")
        return target

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

    def execute(self, command: str, working_dir: str = "/workspace") -> SandboxResult:
        import time
        start = time.time()
        if not self._docker_available:
            return SandboxResult(success=False, error="Docker not available", exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))
        os.makedirs(self.workspace, exist_ok=True)
        docker_cmd = ["docker", "run", "--rm", "--name", self.container_name,
                     "-v", self.workspace + ":" + working_dir, "-w", working_dir,
                     self.image, "sh", "-c", command]
        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=self.timeout)
            return SandboxResult(success=(result.returncode == 0), stdout=result.stdout,
                                   stderr=result.stderr, exit_code=result.returncode,
                                   duration_ms=int((time.time() - start) * 1000))
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", self.container_name], capture_output=True)
            return SandboxResult(success=False, error="Timeout", exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))
        except Exception as e:
            return SandboxResult(success=False, error=str(e), exit_code=-1,
                                   duration_ms=int((time.time() - start) * 1000))

    def cleanup(self) -> None:
        subprocess.run(["docker", "kill", self.container_name], capture_output=True)


Sandbox = NamespaceSandbox
