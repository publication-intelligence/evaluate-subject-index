#!/usr/bin/env python3
"""Run the canonical V10 subject-index evaluation workflow.

Usage: v10_cli.py TOOL [arguments...]
Tools: state, policy, page-chunks, discover-source, benchmark,
prepare-candidate, audit-candidate, score, grade, study, bundle,
release-decision, access-review.
"""
import argparse
import runpy
import sys
from pathlib import Path
import runtime_profile

TOOLS = {
    "adopt": "v10_execution.py",
    "state": "state_cli.py", "policy": "policy_cli.py",
    "discover-source": "parallel_discovery_cli.py", "benchmark": "benchmark_review_cli.py",
    "access-review": "v10_candidate_access.py", "release-decision": "v10_release.py",
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
    runtime_profile.activate_public_cli()
    script = Path(__file__).with_name(TOOLS[args.tool])
    namespace = runpy.run_path(str(script), run_name=f"_v10_{args.tool.replace('-', '_')}")
    sys.argv = [f"scripts/v10_cli.py {args.tool}", *args.arguments]
    namespace["main"]()


if __name__ == "__main__":
    main()
