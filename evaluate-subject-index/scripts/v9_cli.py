#!/usr/bin/env python3
"""Run an explicitly selected V9 workflow without changing the V8 entrypoints.

Usage: v9_cli.py TOOL [arguments...]
Tools: state, policy, page-chunks, prepare-candidate, audit-candidate,
score, grade, study, bundle.
The preserved V8 benchmark/source workflow remains the source-proof authority.
"""
import argparse
import runpy
import sys
from pathlib import Path
import runtime_profile

TOOLS = {
    "state": "state_cli.py", "policy": "policy_cli.py",
    "page-chunks": "page_chunk_cli.py", "bundle": "bundle_cli.py",
    "prepare-candidate": "candidate_preparation_cli.py",
    "audit-candidate": "parallel_candidate_audit_cli.py",
    "score": "dimension_score_v8_cli.py", "grade": "item_grade_v8_cli.py",
    "study": "study_cli.py",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    runtime_profile.select_v9()
    script = Path(__file__).with_name(TOOLS[args.tool])
    sys.argv = [str(script), *args.arguments]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
