"""Explicit process-level runtime selection. Existing entrypoints always default to V8.2.

Only v9_cli selects V9, before loading any workflow module. No environment-variable
switches, source-artifact rewriting, or inference from display labels is allowed.
"""
import sys

ACTIVE = "v8"
IDENTITIES = {'ohfr-v8-representation-correction-overlay-v1': 'ohfr-v9-representation-correction-overlay-v1',
 'subject-index-standard-policy-v8.2': 'subject-index-standard-policy-v9',
 'subject-index-rubric-v8.2': 'subject-index-rubric-v9',
 'subject-index-dimension-calculation-v7': 'subject-index-dimension-calculation-v8',
 'subject-index-evaluation-policy-v4': 'subject-index-evaluation-policy-v5',
 'subject-index-evaluation-state-v6': 'subject-index-evaluation-state-v7',
 'subject-index-dimension-calculation-input-v2': 'subject-index-dimension-calculation-input-v3',
 'subject-index-dimension-calculations-v6': 'subject-index-dimension-calculations-v7',
 'subject-index-item-assessments-v7': 'subject-index-item-assessments-v8',
 'subject-index-evaluation-result-v12': 'subject-index-evaluation-result-v13',
 'subject-index-web-report-v10': 'subject-index-web-report-v11',
 'subject-index-v8-projection-metadata-v2': 'subject-index-v9-projection-metadata-v1',
 'ohfr-v8-canonical-web-projection-v1': 'ohfr-v9-canonical-web-projection-v1',
 'ohfr-v8-web-collection-v1': 'ohfr-v9-web-collection-v1',
 'ohfr-study-benchmark-lock-v1': 'ohfr-study-benchmark-lock-v2',
 'subject-index-study-benchmark-lock-v1': 'subject-index-study-benchmark-lock-v2'}
SCHEMAS = {'correction-overlay-v1.schema.json': 'correction-overlay-v9.schema.json',
 'retrospective-study-binding.schema.json': 'retrospective-study-binding-v2.schema.json',
 'evaluation-policy-v4.schema.json': 'evaluation-policy-v5.schema.json',
 'evaluation-state.schema.json': 'evaluation-state-v7.schema.json',
 'dimension-calculation-input.schema.json': 'dimension-calculation-input-v3.schema.json',
 'dimension-calculations-v6.schema.json': 'dimension-calculations-v7.schema.json',
 'item-assessments-v7.schema.json': 'item-assessments-v8.schema.json',
 'evaluation-result-v12.schema.json': 'evaluation-result-v13.schema.json',
 'web-report-v10.schema.json': 'web-report-v11.schema.json',
 'v8-projection-metadata-v2.schema.json': 'v9-projection-metadata-v1.schema.json',
 'web-projection-v1.schema.json': 'web-projection-v9.schema.json',
 'web-collection-v1.schema.json': 'web-collection-v9.schema.json',
 'study-benchmark-lock.schema.json': 'study-benchmark-lock-v2.schema.json'}


def select_v9():
    global ACTIVE
    if any(name in sys.modules for name in ("scoring_core", "state_cli", "policy_cli", "schema_validation")):
        raise RuntimeError("Select V9 before importing workflow modules")
    ACTIVE = "v9"


def is_v9():
    return ACTIVE == "v9"


def identity(value, *, profile=None):
    selected = ACTIVE if profile is None else profile
    if selected not in ("v8", "v9"):
        raise ValueError("Unknown runtime profile")
    return IDENTITIES.get(value, value) if selected == "v9" else value


def schema_name(value, *, profile=None):
    selected = ACTIVE if profile is None else profile
    if selected not in ("v8", "v9"):
        raise ValueError("Unknown runtime profile")
    return SCHEMAS.get(value, value) if selected == "v9" else value
