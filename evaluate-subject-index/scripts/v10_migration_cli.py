#!/usr/bin/env python3
"""Internal reader for already frozen pre-native V10 migration fixtures.

This module is not a user-facing workflow. New evaluations use v10_cli.py and
start directly in V10.
"""
import argparse
import runpy
import sys
from pathlib import Path
import runtime_profile

TOOLS = {
    "state": "state_cli.py", "access-review": "v10_candidate_access.py",
    "release-decision": "v10_release.py", "page-chunks": "page_chunk_cli.py",
    "bundle": "bundle_cli.py", "prepare-candidate": "candidate_preparation_cli.py",
    "audit-candidate": "parallel_candidate_audit_cli.py",
    "score": "dimension_score_v8_cli.py", "grade": "item_grade_v8_cli.py",
    "study": "study_cli.py",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    runtime_profile.select_v10()
    script = Path(__file__).with_name(TOOLS[args.tool])
    sys.argv = [str(script), *args.arguments]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
