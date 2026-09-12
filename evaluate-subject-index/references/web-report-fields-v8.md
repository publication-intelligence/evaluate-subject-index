# Web report fields — V8

New reports use `subject-index-web-report-v9` and point to the current V8 calculation and item-assessment artifacts.

The report exposes:

- evaluation identity and status;
- six full-precision dimension percentages and weighted contributions;
- the overall percentage, rounded only after summing all contributions, and uncertainty where applicable;
- gate outcomes;
- item-level findings and evidence links;
- keep precision, treatment recall, and reliability F1;
- per-locator treatment, fit, diagnostic credit and grade, binary rating credit, and explanation; and
- structure-review quantities and decisions.

Explanation text is display metadata and cannot alter calculation values. Content hashes join report references to their source records; they are not security attestations or checkpoint-resume gates.
