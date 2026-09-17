"""Explicit process-level runtime selection. Existing entrypoints always default to V8.2.

Only explicit versioned CLIs select successor runtimes, before loading any workflow module. No environment-variable
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


def select_v10():
    global ACTIVE
    if any(name in sys.modules for name in ("scoring_core", "state_cli", "policy_cli", "schema_validation")):
        raise RuntimeError("Select V10 before importing workflow modules")
    ACTIVE = "v10"


def is_v10():
    return ACTIVE == "v10"


def percentage_native():
    return ACTIVE in ("v9", "v10")


def versioned_cli():
    return "v10_cli.py" if is_v10() else "v9_cli.py"


def migration_module():
    import importlib
    return importlib.import_module("v10_migration" if is_v10() else "v9_migration")


def identity(value, *, profile=None):
    selected = ACTIVE if profile is None else profile
    if selected not in ("v8", "v9", "v10"):
        raise ValueError("Unknown runtime profile")
    return V10_IDENTITIES.get(value, value) if selected == "v10" else IDENTITIES.get(value, value) if selected == "v9" else value


def schema_name(value, *, profile=None):
    selected = ACTIVE if profile is None else profile
    if selected not in ("v8", "v9", "v10"):
        raise ValueError("Unknown runtime profile")
    return V10_SCHEMAS.get(value, value) if selected == "v10" else SCHEMAS.get(value, value) if selected == "v9" else value

V10_IDENTITIES = {'ohfr-v8-representation-correction-overlay-v1': 'ohfr-v10-representation-correction-overlay-v1',
 'subject-index-standard-policy-v8.2': 'subject-index-standard-policy-v10',
 'subject-index-rubric-v8.2': 'subject-index-rubric-v10',
 'subject-index-dimension-calculation-v7': 'subject-index-dimension-calculation-v9',
 'subject-index-evaluation-policy-v4': 'subject-index-evaluation-policy-v6',
 'subject-index-evaluation-state-v6': 'subject-index-evaluation-state-v8',
 'subject-index-dimension-calculation-input-v2': 'subject-index-dimension-calculation-input-v4',
 'subject-index-dimension-calculations-v6': 'subject-index-dimension-calculations-v8',
 'subject-index-item-assessments-v7': 'subject-index-item-assessments-v9',
 'subject-index-evaluation-result-v12': 'subject-index-evaluation-result-v14',
 'subject-index-web-report-v10': 'subject-index-web-report-v12',
 'subject-index-v8-projection-metadata-v2': 'subject-index-v10-projection-metadata-v1',
 'ohfr-v8-canonical-web-projection-v1': 'ohfr-v10-canonical-web-projection-v1',
 'ohfr-v8-web-collection-v1': 'ohfr-v10-web-collection-v1',
 'ohfr-study-benchmark-lock-v1': 'ohfr-study-benchmark-lock-v3',
 'subject-index-study-benchmark-lock-v1': 'subject-index-study-benchmark-lock-v3'}
V10_SCHEMAS = {'correction-overlay-v1.schema.json': 'correction-overlay-v10.schema.json',
 'retrospective-study-binding.schema.json': 'retrospective-study-binding-v3.schema.json',
 'evaluation-policy-v4.schema.json': 'evaluation-policy-v6.schema.json',
 'evaluation-state.schema.json': 'evaluation-state-v8.schema.json',
 'dimension-calculation-input.schema.json': 'dimension-calculation-input-v4.schema.json',
 'dimension-calculations-v6.schema.json': 'dimension-calculations-v8.schema.json',
 'item-assessments-v7.schema.json': 'item-assessments-v9.schema.json',
 'evaluation-result-v12.schema.json': 'evaluation-result-v14.schema.json',
 'web-report-v10.schema.json': 'web-report-v12.schema.json',
 'v8-projection-metadata-v2.schema.json': 'v10-projection-metadata-v1.schema.json',
 'web-projection-v1.schema.json': 'web-projection-v10.schema.json',
 'web-collection-v1.schema.json': 'web-collection-v10.schema.json',
 'study-benchmark-lock.schema.json': 'study-benchmark-lock-v3.schema.json'}
