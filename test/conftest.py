"""
pytest fixtures: boot the baseline image and our image as siblings, with the
same custom.conf mounted into both, expose them on different host ports, wait
for readiness, and tear them down at end-of-session.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

BASELINE_IMAGE = os.environ.get("BASELINE_IMAGE", "nginx:1.25-bookworm")
OURS_IMAGE     = os.environ.get("OURS_IMAGE",     "echo/nginx:1.25-bookworm")
BASELINE_PORT  = int(os.environ.get("BASELINE_PORT", "18080"))
OURS_PORT      = int(os.environ.get("OURS_PORT",     "18081"))

CUSTOM_CONF = (Path(__file__).parent / "custom.conf").resolve()


def _docker(*args):
    return subprocess.run(
        ["docker", *args],
        check=False, capture_output=True, text=True,
    )


def _start(image, port, name):
    _docker("rm", "-f", name)
    res = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "--name", name,
            "-p", f"{port}:80",
            "-p", f"{port + 1000}:8081",
            "-v", f"{CUSTOM_CONF}:/etc/nginx/conf.d/custom.conf:ro",
            image,
        ],
        check=True, capture_output=True, text=True,
    )
    return res.stdout.strip()


def _wait_ready(url, timeout=20):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            requests.get(url, timeout=1)
            return
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError(f"timeout waiting for {url}: {last}")


@pytest.fixture(scope="session")
def baseline_url():
    name = "compat-baseline"
    _start(BASELINE_IMAGE, BASELINE_PORT, name)
    url = f"http://127.0.0.1:{BASELINE_PORT}"
    _wait_ready(url)
    yield url
    _docker("rm", "-f", name)


@pytest.fixture(scope="session")
def ours_url():
    name = "compat-ours"
    _start(OURS_IMAGE, OURS_PORT, name)
    url = f"http://127.0.0.1:{OURS_PORT}"
    _wait_ready(url)
    yield url
    _docker("rm", "-f", name)


@pytest.fixture(scope="session")
def baseline_custom_url():
    """Same baseline container, but addressed via the custom.conf listen :8081."""
    return f"http://127.0.0.1:{BASELINE_PORT + 1000}"


@pytest.fixture(scope="session")
def ours_custom_url():
    return f"http://127.0.0.1:{OURS_PORT + 1000}"
