"""
AegisFlow Sandbox Layer.

Provides containerized and directory-isolated execution for agent operations.

Modes:
- local: directory-bound sandbox (no container, just chroot-like path checking)
- docker: full container isolation via Docker daemon
- podman: full container isolation via Podman (future)
"""

import os
import shutil
import logging
import subprocess
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result of a sandboxed operation."""
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
    """
    Directory-bound sandbox with path traversal protection.
    Suitable for non-privileged execution on any system.
    """

    def __init__(self, workspace_path: str = "./sandbox_workspace"):
        self.workspace = os.path.abspath(workspace_path)
        self.isolation_level = "local"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for d in ["workspace", "uploads", "outputs", "logs"]:
            os.makedirs(os.path.join(self.workspace, d), exist_ok=True)

    def _resolve_path(self, relative_path: str) -> str:
        target = os.path.abspath(os.path.join(self.workspace, relative_path))
        if not target.startswith(self.workspace):
            raise PermissionError(f"Path traversal detected: {relative_path} escapes workspace")
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
            raise FileNotFoundError(f"File not found: {relative_path}")
        with open(safe_path, "r") as f:
            return f.read()

    def list_files(self, subdir: str = "workspace") -> List[str]:
        full_path = os.path.join(self.workspace, subdir)
        if not os.path.exists(full_path):
            return []
        return sorted([
            os.path.relpath(os.path.join(root, f), full_path)
            for root, _, files in os.walk(full_path)
            for f in files
        ])

    def execute(self, command: str, timeout: int = 30) -> SandboxResult:
        """Execute a shell command within the workspace directory."""
        import time
        start = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=int((time.time() - start) * 1000),
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                error=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000),
            )

    def cleanup(self) -> None:
        """Remove all files in the workspace."""
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace)
            self._ensure_directories()
            logger.info(f"Sandbox cleanup complete: {self.workspace}")


class DockerSandbox:
    """
    Docker-based containerized sandbox.
    Requires a running Docker daemon and docker CLI.
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        workspace_path: str = "./sandbox_workspace",
        container_name: Optional[str] = None,
        timeout: int = 120,
    ):
        self.image = image
        self.workspace = os.path.abspath(workspace_path)
        self.container_name = container_name or f"aegisflow-sandbox-{uuid.uuid4().hex[:8]}"
        self.timeout = timeout
        self.isolation_level = "docker"

        # Check if docker is available
        self._docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def write_file(self, relative_path: str, content: str) -> str:
        """Write a file to the host workspace (before container run)."""
        safe_path = os.path.join(self.workspace, relative_path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w") as f:
            f.write(content)
        return safe_path

    def read_file(self, relative_path: str) -> str:
        safe_path = os.path.join(self.workspace, relative_path)
        with open(safe_path, "r") as f:
            return f.read()

    def execute(self, command: str, working_dir: str = "/workspace") -> SandboxResult:
        """Execute a command inside a Docker container."""
        import time
        start = time.time()

        if not self._docker_available:
            return SandboxResult(
                success=False,
                error="Docker daemon not available. Install Docker or use LocalSandbox.",
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000),
            )

        # Ensure workspace exists on host
        os.makedirs(self.workspace, exist_ok=True)

        docker_cmd = [
            "docker", "run",
            "--rm",
            "--name", self.container_name,
            "-v", f"{self.workspace}:{working_dir}",
            "-w", working_dir,
            self.image,
            "sh", "-c", command,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return SandboxResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=int((time.time() - start) * 1000),
            )
        except subprocess.TimeoutExpired:
            # Try to kill the container
            subprocess.run(["docker", "kill", self.container_name], capture_output=True)
            return SandboxResult(
                success=False,
                error=f"Container command timed out after {self.timeout} seconds",
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000),
            )

    def cleanup(self) -> None:
        """Kill any running container with our name."""
        subprocess.run(["docker", "kill", self.container_name], capture_output=True)


Sandbox = LocalSandbox  # Default alias for backward compat