# V10 semantic-uncertainty interpretation addendum v3

Addendum identity: `subject-index-evaluation-v10-semantic-uncertainty-addendum-v3`  
Status: approved bounded precision for implementation and coordinated review; not activated  
Parent decision contract SHA-256: `f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9`  
Incorporated v1 SHA-256: `e0f0e91a23274a94e292409b17df53d1b403bd0a52b26e6e7ae84809430c5f76`  
Incorporated v2 SHA-256: `fea2a5b87f9e063d28135895fdb7d3637dfe4d2edd294fb7a50fd3aff7009277`

This precision controls the meaning of an unresolved axis under v1 and v2.
The parent contract, v1, and v2 bytes remain unchanged.

## Non-singleton unresolved-axis rule

After applying every established fact and existing cross-axis invariant, an
axis may be declared unresolved only when at least two legacy-consistent values
remain possible for that axis. If the consistent domain collapses to one value,
the axis is resolved and the native row must record that value. A declaration
of uncertainty cannot replace a fact already entailed by the frozen rubric.

Consequently:

- known `complete_path_fit=material_partial_fit` requires the existing
  `partially_supported` non-keep judgment;
- known `complete_path_fit=no_fit` requires the existing `unsupported`
  non-keep judgment; and
- either fit paired with `judgment=semantic_unresolved` must be rejected.

Do not retain a null keep decision merely because its numerical interval could
be written as zero through zero. If keep/non-keep is forced to non-keep, preserve
`keep_decision=not_kept` and its existing zero rating credit. If a finer
diagnostic or judgment detail remains unresolved, record and block only that
finer premise. If the reviewer genuinely cannot establish non-keep, then a fit
value that would force non-keep was not itself established and fit must remain
the unresolved axis.

`judgment=semantic_unresolved` is therefore permitted only when the jointly
consistent state set contains both kept and non-kept worlds. Its keep-credit
bounds remain zero through one. This is validation of factual consistency, not
a new credit, formula, threshold, cap, or gate.

Add synthetic acceptance tests for both forced-non-keep fits, for a genuinely
unresolved keep domain containing kept and non-kept worlds, and for preserving
known non-keep while another axis remains unresolved. All execution and release
holds from v1 and v2 remain in force.
