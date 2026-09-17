#!/usr/bin/env python3
"""Record or verify a human release decision against an immutable V10 result.

This separate artifact is never an input to scoring, gates or method readiness.
"""
import argparse
import json
from pathlib import Path
import study_comparison as study
from schema_validation import schema_errors


def machine_facts(result):
    return {key: result[key] for key in ('evaluation_id','candidate','provenance','dimension_calculations','scorecard','overall_percentage','critical_gates','evaluation_validity','gate_assessment','method_readiness','authoritative_evaluation')}


def validate_decision(decision, result, result_file_sha256):
    from runtime_profile import semantic_uncertainty
    profile='v10s' if semantic_uncertainty() else 'v10'
    study.require(not schema_errors(result,'evaluation-result-v14.schema.json',profile=profile), 'Invalid V10 result')
    study.require(not schema_errors(decision,'human-release-decision-v10.schema.json',profile='v10'), 'Invalid V10 human release decision')
    study.require(decision['result_file_sha256'] == result_file_sha256 and decision['machine_facts_sha256'] == study.digest(machine_facts(result)), 'Release decision is bound to different machine outcomes')
    study.require(decision['evaluation_id'] == result['evaluation_id'], 'Release decision evaluation differs')
    study.require(decision['acknowledged_gate_ids'] == result['method_readiness']['triggered_gate_ids'], 'Release decision must acknowledge every confirmed core gate')
    study.require(decision['status'] != 'approved' or result['method_readiness']['status'] == 'ready', 'Blocked method readiness requires an explicit deviation, not ordinary approval')
    from datetime import datetime, timezone
    stamp=datetime.fromisoformat(decision['decided_at'].replace('Z','+00:00'))
    study.require(stamp.utcoffset() is not None and stamp <= datetime.now(timezone.utc), 'Release decision requires a timezone-aware, nonfuture decision date')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result',required=True);parser.add_argument('--decision',required=True)
    parser.add_argument('--output',help='Optional new location for the validated decision; result bytes are never changed.')
    args=parser.parse_args()
    try:
        result=study.read(args.result);decision=study.read(args.decision)
        validate_decision(decision,result,study.file_digest(args.result))
        if args.output:
            output=Path(args.output)
            study.require(not output.exists(),'Release decision output already exists')
            output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(Path(args.decision).read_bytes())
        print(json.dumps({'ok':True,'status':decision['status'],'method_readiness':result['method_readiness'],'machine_outcomes_changed':False},indent=2))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}));raise SystemExit(1)

if __name__=='__main__':main()
