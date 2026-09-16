#!/usr/bin/env python3
"""Open the local commercial workspace on a healthy, available port."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "commercial_crm.db"


def tracker_health(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("ok") is True
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def select_port(host: str, preferred: int, attempts: int = 10) -> tuple[int, bool]:
    if tracker_health(host, preferred):
        return preferred, False
    for port in range(preferred, preferred + attempts):
        if port_available(host, port):
            return port, True
    raise RuntimeError(
        f"No available workspace port between {preferred} and {preferred + attempts - 1}."
    )


def wait_until_ready(host: str, port: int, process: subprocess.Popen, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tracker_health(host, port):
            return
        if process.poll() is not None:
            raise RuntimeError(f"The workspace server stopped with exit code {process.returncode}.")
        time.sleep(0.15)
    raise RuntimeError("The workspace server did not become ready in time.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    port, should_start = select_port(args.host, args.port)
    workspace_url = f"http://{args.host}:{port}/projects"

    if not should_start:
        print(f"Health Infrastructure Tracker is already running at {workspace_url}")
        if not args.no_browser:
            webbrowser.open(workspace_url)
        return 0

    if port != args.port:
        print(f"Port {args.port} is occupied by another application; using port {port}.")

    command = [
        sys.executable,
        str(ROOT / "commercial_crm_server.py"),
        "--host",
        args.host,
        "--port",
        str(port),
        "--db",
        str(args.db.resolve()),
    ]
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        wait_until_ready(args.host, port, process)
        print(f"Health Infrastructure Tracker is ready at {workspace_url}")
        if not args.no_browser:
            webbrowser.open(workspace_url)
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return process.wait(timeout=5)
    except Exception:
        process.terminate()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
