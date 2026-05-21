"""
Tests for aegisflow.sandbox — LocalSandbox, NamespaceSandbox, DockerSandbox.
"""
from __future__ import annotations

import os

import pytest

from aegisflow.core.errors import SandboxPermissionError
from aegisflow.sandbox.environment import (
    DockerSandbox,
    LocalSandbox,
    NamespaceSandbox,
    SandboxResult,
)


class TestSandboxResult:
    def test_to_dict(self):
        r = SandboxResult(success=True, stdout="ok", exit_code=0)
        assert r.to_dict()["success"] is True

class TestLocalSandbox:
    def test_dirs(self, tmp_path):
        LocalSandbox(workspace_path=str(tmp_path))
        for d in ["workspace", "uploads", "outputs", "logs"]:
            assert os.path.isdir(tmp_path / d)

    def test_write_read(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        sb.write_file("workspace/t.txt", "hi")
        assert sb.read_file("workspace/t.txt") == "hi"

    def test_traversal_read(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.read_file("../../../../etc/passwd")

    def test_traversal_write(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.write_file("../../../../tmp/evil.txt", "bad")

    def test_execute(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        r = sb.execute("echo hello")
        assert r.success and "hello" in r.stdout

    def test_cleanup(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        sb.write_file("workspace/x.txt", "data")
        sb.cleanup()
        assert os.path.isdir(tmp_path / "workspace")
        assert not os.path.exists(tmp_path / "workspace" / "x.txt")

class TestNamespaceSandbox:
    def test_traversal(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.read_file("../../../../etc/passwd")

    def test_write_read(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        sb.write_file("test.txt", "hello")
        assert sb.read_file("test.txt") == "hello"

class TestDockerSandbox:
    def test_traversal(self, tmp_path):
        sb = DockerSandbox(workspace_path=str(tmp_path))
        with pytest.raises(SandboxPermissionError):
            sb.read_file("../../../../etc/passwd")

    def test_write_read(self, tmp_path):
        sb = DockerSandbox(workspace_path=str(tmp_path))
        sb.write_file("test.txt", "hello")
        assert sb.read_file("test.txt") == "hello"

    def test_docker_unavailable(self, tmp_path):
        sb = DockerSandbox(workspace_path=str(tmp_path))
        sb._docker_available = False
        r = sb.execute("echo hello")
        assert r.success is False
