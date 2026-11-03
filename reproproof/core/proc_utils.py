"""Process management, port allocation, and environment isolation utilities."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Dict, Optional


def find_free_port() -> int:
    """Finds an available ephemeral port allocated by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        return port


def get_sanitized_runner_env(port: int, base_url: Optional[str] = None) -> Dict[str, str]:
    """Constructs a minimal, sanitized environment for running tests and servers.

    Security Invariant:
    MODEL_API_KEY, credentials, and parent auth tokens are NEVER inherited.
    Sets NODE_PATH so temp execution workspaces resolve @playwright/test cleanly.
    Allows runner processes to run tests in runs/ via PLAYWRIGHT_ALLOW_RUNS=1.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    node_modules_dir = str(repo_root / "node_modules")
    existing_node_path = os.environ.get("NODE_PATH", "")
    node_path_val = f"{node_modules_dir};{existing_node_path}" if existing_node_path else node_modules_dir

    safe_env: Dict[str, str] = {
        "PORT": str(port),
        "BASE_URL": base_url or f"http://127.0.0.1:{port}",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "NODE_PATH": node_path_val,
        "PLAYWRIGHT_ALLOW_RUNS": "1",
    }

    # Scrub any secret or sensitive tokens
    forbidden_tokens = ["MODEL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "META_API_BASE_URL", "TOKEN", "SECRET"]
    for k in list(safe_env.keys()):
        for f in forbidden_tokens:
            if f in k.upper():
                safe_env.pop(k, None)

    return safe_env


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Forcefully terminates a subprocess and its entire child process tree."""
    if proc.poll() is not None:
        return

    pid = proc.pid
    if sys.platform == "win32":
        try:
            # Use taskkill to terminate entire process tree on Windows
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            pass

    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def force_rmtree(path: str) -> None:
    """rmtree that also removes read-only files (git objects are read-only on Windows)."""
    import shutil
    import stat

    def _retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    try:
        shutil.rmtree(path, onexc=_retry)
    except OSError:
        pass  # still locked by a dying process; never mask the caller's result
