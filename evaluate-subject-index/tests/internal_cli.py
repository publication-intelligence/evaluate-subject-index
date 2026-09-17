"""Subprocess helper for exercising implementation modules without exposing them as CLIs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run_internal_cli(
    module: str,
    *arguments: object,
    profile: str = "v8",
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    selector = {"v8": "", "v10": "runtime_profile.select_v10();"}[profile]
    code = (
        "import importlib,sys;"
        "sys.path.insert(0,sys.argv[1]);"
        "import runtime_profile;"
        + selector
        + "tool=importlib.import_module(sys.argv[2]);"
        "sys.argv=[sys.argv[2],*sys.argv[3:]];"
        "tool.main()"
    )
    return subprocess.run(
        [sys.executable, "-c", code, str(SCRIPTS), module, *(str(value) for value in arguments)],
        text=True,
        capture_output=True,
        check=check,
    )
