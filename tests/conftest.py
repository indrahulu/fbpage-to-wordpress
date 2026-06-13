from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workdir() -> Path:
    root = Path(".test-work")
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
