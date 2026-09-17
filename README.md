# Evaluate Subject Index

Evaluate Subject Index runs source-grounded **V10** evaluations of finished
subject indexes. The only public command entry point is
`evaluate-subject-index/scripts/v10_cli.py`.

Historical V8 and V9 artifacts remain readable only as frozen evidence during a
typed V10 migration. They are not runnable methodologies, and low-level modules
reject direct execution.

The framework separates four questions:

1. What subjects and reader tasks does the source require?
2. Are the candidate's paths and locators supported by the cited pages?
3. Can readers reach every required subject?
4. Does the whole index form a coherent navigation system?

Validated ledgers feed deterministic V10 scoring and report projection.

## Setup

```bash
python -m pip install -r requirements.txt
```

## Canonical workflow

One `evaluation-state.json` controls the run:

```text
initialize → page map → chunks → policy
  → benchmark discovery/confirmation → synthesis/review/freeze
  → candidate normalization → locator packets
  → locator audit → missing-access audit → structure audit
  → V10 scoring → report and public projection
```

Run every operation through the V10 dispatcher:

```bash
python evaluate-subject-index/scripts/v10_cli.py --help
python evaluate-subject-index/scripts/v10_cli.py state --help
python evaluate-subject-index/scripts/v10_cli.py benchmark --help
python evaluate-subject-index/scripts/v10_cli.py score --help
python evaluate-subject-index/scripts/v10_cli.py study --help
```

The dispatcher exposes state, policy, page/chunk, source discovery, benchmark,
candidate preparation/audit, access review, scoring, grading, study, checkpoint,
and release-decision tools under the selected V10 runtime. The underlying files
are implementation modules even when an old version remains in a filename.

The final transitions are typed and atomic:

```bash
python evaluate-subject-index/scripts/v10_cli.py score register-structure \
  --state /path/to/evaluation/evaluation-state.json \
  --input /path/to/evaluation/structure-audit.json
python evaluate-subject-index/scripts/v10_cli.py score score \
  --state /path/to/evaluation/evaluation-state.json
python evaluate-subject-index/scripts/v10_cli.py score build-report \
  --state /path/to/evaluation/evaluation-state.json
```

See [the skill contract](evaluate-subject-index/SKILL.md) and
[workflow](evaluate-subject-index/references/workflow.md).

## Optional input converter

The skill accepts the format-neutral
[`candidate-layout-extraction-v1`](evaluate-subject-index/references/schemas/candidate-layout-extraction.schema.json)
contract. [`subject_index_converter.py`](utilities/subject_index_converter.py) is
a separate convenience utility for supported PDF, Markdown, text, and HTML
inputs:

```bash
python utilities/subject_index_converter.py \
  --candidate-id example \
  --input /path/to/index.pdf \
  --output /path/to/candidate-layout-extraction.v1.json
```

The converter performs mechanical extraction only. Evaluation and editorial
judgment remain in the V10 skill.

## Checkpoints

Checkpoints are recovery snapshots rather than evaluation stages:

```bash
python evaluate-subject-index/scripts/v10_cli.py bundle checkpoint \
  --state /path/to/evaluation/evaluation-state.json \
  --output /path/to/checkpoint.zip

python evaluate-subject-index/scripts/v10_cli.py bundle import-bundle \
  --input /path/to/checkpoint.zip \
  --output-dir /path/to/resumed-evaluation
```

## Test

```bash
python -m unittest discover -s evaluate-subject-index/tests -p 'test_*.py' -v
python -m unittest discover -s utilities/tests -p 'test_*.py' -v
```

## License

Copyright (c) 2026 John Camden.

This project is licensed under the GNU Affero General Public License, version 3
only (`AGPL-3.0-only`). See [LICENSE](LICENSE). Third-party components remain
subject to their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

PyMuPDF and MuPDF are available under the GNU AGPL v3 or a separate commercial
license from Artifex. This repository uses them under the GNU AGPL v3 and does
not grant an Artifex commercial license.
