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


# ── Security regressions ─────────────────────────────────────────────────────

import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

from aegisflow.core.errors import SandboxUnavailableError  # noqa: E402
from aegisflow.sandbox.environment import resolve_within, to_argv  # noqa: E402

SANDBOX_CLASSES = [LocalSandbox, NamespaceSandbox, DockerSandbox]


class TestPathContainment:
    @pytest.mark.parametrize("cls", SANDBOX_CLASSES)
    def test_sibling_prefix_dir_rejected(self, tmp_path, cls):
        """`<ws>_evil` shares a string prefix with `<ws>` but is outside it."""
        ws = tmp_path / "sandbox_workspace"
        sb = cls(workspace_path=str(ws))
        (tmp_path / "sandbox_workspace_evil").mkdir()
        with pytest.raises(SandboxPermissionError):
            sb.write_file("../sandbox_workspace_evil/x", "pwn")
        assert not (tmp_path / "sandbox_workspace_evil" / "x").exists()

    @pytest.mark.parametrize("cls", SANDBOX_CLASSES)
    def test_absolute_path_rejected(self, tmp_path, cls):
        sb = cls(workspace_path=str(tmp_path / "ws"))
        with pytest.raises(SandboxPermissionError):
            sb.read_file(str(tmp_path / "outside.txt"))

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
    def test_symlink_escape_rejected(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path / "ws"))
        outside = tmp_path / "outside"
        outside.mkdir()
        os.symlink(outside, tmp_path / "ws" / "link")
        with pytest.raises(SandboxPermissionError):
            sb.write_file("link/escape.txt", "pwn")
        assert not (outside / "escape.txt").exists()

    def test_inner_dotdot_allowed(self, tmp_path):
        p = resolve_within(str(tmp_path), "a/../b.txt")
        assert p == os.path.join(os.path.realpath(tmp_path), "b.txt")


class TestNoShell:
    def test_to_argv_splits_string(self):
        assert to_argv("echo 'a b' c") == ["echo", "a b", "c"]

    def test_to_argv_rejects_empty_and_bad_types(self):
        with pytest.raises(ValueError):
            to_argv("   ")
        with pytest.raises(TypeError):
            to_argv(["echo", 1])  # type: ignore[list-item]

    def test_shell_metacharacters_not_interpreted(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        marker = tmp_path / "pwned"
        r = sb.execute(f"echo hi; touch {marker}")
        assert r.success
        # `;` and `touch` are passed to echo as literal arguments.
        assert "touch" in r.stdout
        assert not marker.exists()

    def test_argv_list(self, tmp_path):
        sb = LocalSandbox(workspace_path=str(tmp_path))
        r = sb.execute([sys.executable, "-c", "print('ok $HOME')"])
        assert r.success and r.stdout.strip() == "ok $HOME"

    def test_subprocess_never_uses_shell(self, tmp_path, monkeypatch):
        seen = {}
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            seen.update(kwargs)
            seen["argv"] = args[0]
            return real_popen(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", spy)
        LocalSandbox(workspace_path=str(tmp_path)).execute("echo hi")
        assert not seen.get("shell", False)
        assert seen["argv"] == ["echo", "hi"]


class TestNamespaceFailsLoudly:
    def test_unavailable_raises_instead_of_host_fallback(self, tmp_path, monkeypatch):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        sb._unshare_available = False
        marker = tmp_path / "ran_on_host"

        def boom(*a, **k):  # any host execution is a failure
            raise AssertionError("must not execute on host")

        monkeypatch.setattr(subprocess, "Popen", boom)
        monkeypatch.setattr(subprocess, "run", boom)
        with pytest.raises(SandboxUnavailableError):
            sb.execute(["touch", str(marker)])
        assert not marker.exists()

    def test_unshare_cmd_has_no_shell(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        cmd = sb._unshare_cmd("echo 'a b'")
        assert cmd[0] == "unshare"
        assert "bash" not in cmd and "-c" not in cmd
        assert cmd[-2:] == ["echo", "a b"]
        assert "--net" in cmd

    def test_real_unshare_if_available(self, tmp_path):
        sb = NamespaceSandbox(workspace_path=str(tmp_path))
        if not sb._unshare_available:
            pytest.skip("unprivileged user namespaces unavailable")
        r = sb.execute(["true"])
        assert r.success, r.stderr


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
class TestTimeoutKillsOnlyOwnGroup:
    def test_timeout_kills_grandchild_but_not_bystander(self, tmp_path):
        # A process we own that is NOT part of the sandboxed command.
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            sb = LocalSandbox(workspace_path=str(tmp_path))
            pidfile = tmp_path / "workspace" / "gc.pid"
            script = (
                "import subprocess, sys, time\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n"
                "time.sleep(30)\n"
            )
            r = sb.execute([sys.executable, "-c", script], timeout=2)
            assert r.success is False and r.error == "Timed out"
            gc_pid = int(pidfile.read_text())
            deadline = time.time() + 5
            while time.time() < deadline and _alive(gc_pid):
                time.sleep(0.05)
            assert not _alive(gc_pid), "grandchild in the command's group survived"
            assert bystander.poll() is None, "unrelated child of the caller was killed"
        finally:
            bystander.kill()
            bystander.wait()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Zombies count as dead. Linux exposes the state in /proc; macOS and the
    # BSDs have no /proc, so ask `ps` instead of assuming the pid is alive.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except OSError:
        pass
    try:
        out = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True
    return bool(out) and not out.startswith("Z")
