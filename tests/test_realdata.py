"""Opt-in smoke test over the user's own simulation folders.

QE_STUDIO_REAL_DATA=/runs/a:/runs/b uv run pytest -m realdata
"""

import os
from pathlib import Path

import pytest

from qe_studio.core.detection import detect_folder

pytestmark = pytest.mark.realdata


def real_folders():
    roots = [Path(p) for p in os.environ.get("QE_STUDIO_REAL_DATA", "").split(os.pathsep) if p]
    for root in roots:
        for folder, dirs, _files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {"tmp", "plots"} and not d.endswith(".save")]
            yield Path(folder)


def test_detection_never_crashes():
    folders = list(real_folders())
    if not folders:
        pytest.skip("QE_STUDIO_REAL_DATA not set")
    for folder in folders:
        detect_folder(folder)
