# Item grading — V8

Item grades explain the current dimension calculation; they do not create a second scoring system.

For a locator, the displayed grade is:

\[
G_j=100\min(T_j,F_j)
\]

where `T` is page-treatment diagnostic credit and `F` is complete-path-fit diagnostic credit. The item row records both axes, `diagnostic_credit`, the diagnostic grade, structured rule IDs, evidence IDs, and a concise explanation. Explanation prose cannot alter the category or arithmetic.

`dimension_reliability_credit` is separate and binary: it is 1 for `supported` (keep unchanged), 0 for `partially_supported` or `unsupported`, and null for `uninspectable` or `not_measured`. A supported mixed locator therefore displays grade 70 while contributing rating credit 1.

Structure, cross-reference, missing-access, and source-subject rows project the corresponding current audit records. Multi-defect arrays use stable defect-ID ordering so repeated output is deterministic.

Aggregate dimension scores must be read from the calculation artifact, not reconstructed by averaging displayed item grades.
