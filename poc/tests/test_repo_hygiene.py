"""Repository hygiene: no machine-specific paths in tracked files."""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCAL_PATH = re.compile(r"/(?:home|Users)/(?!user\b)[A-Za-z0-9_.-]+/")


def test_no_local_account_paths():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    offenders = []
    for name in out.stdout.splitlines():
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            continue
        if LOCAL_PATH.search(data.decode("utf-8", errors="ignore")):
            offenders.append(name)
    assert offenders == []
