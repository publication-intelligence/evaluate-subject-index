# V10 semantic-uncertainty interpretation addendum v4

Addendum identity: `subject-index-evaluation-v10-semantic-uncertainty-addendum-v4`  
Status: approved bounded precision for implementation and coordinated review; not activated  
Parent decision contract SHA-256: `f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9`  
Incorporated v1 SHA-256: `e0f0e91a23274a94e292409b17df53d1b403bd0a52b26e6e7ae84809430c5f76`  
Incorporated v2 SHA-256: `fea2a5b87f9e063d28135895fdb7d3637dfe4d2edd294fb7a50fd3aff7009277`  
Incorporated v3 SHA-256: `4031abef00cb37508f30c8c89ec5e12592ce89369f144c1473ebc43bf9503a7d`

This precision controls the representation of a known binary non-keep decision
whose finer legacy judgment subtype remains unresolved. All incorporated bytes
remain unchanged.

## Known non-keep with unresolved subtype

The V10 successor schema may add one explicit aggregate semantic branch for the
case where established facts rule out `supported` but do not establish whether
the correct legacy subtype is `partially_supported` or `unsupported`.

Use a clearly named V10-only representation such as:

- `keep_decision=not_kept`;
- `judgment=not_kept_subtype_unresolved`;
- `axis_resolution.keep_decision=known`;
- `axis_resolution.judgment_subtype=unresolved`; and
- the actual unresolved diagnostic axes, including fit when applicable.

The final field names may follow repository conventions, but the semantics must
be exact. Do not select either legacy subtype without evidence and do not use
`judgment=semantic_unresolved`, which remains reserved by v3 for a domain
containing both kept and non-kept worlds.

This aggregate branch is representational, not a new rating category:

- rating credit is the existing exact non-keep value zero, with bounds zero
  through zero;
- it does not enter the semantic-unresolved keep count or widen keep-precision
  bounds;
- known treatment remains factual and receives its existing selectivity
  applicability and credit;
- unresolved fit/subtype receives only the jointly consistent diagnostic bounds;
- the exact assessment blocker names fit/subtype, not keep; and
- quality-gate predicates may use the established non-keep fact but may not use
  an unresolved fit/subtype premise. Independent complete predicates remain
  available under v2.

For example, a known weak treatment can rule out `supported` while unresolved
fit leaves `partially_supported` and `unsupported` as the permitted legacy
worlds. The aggregate branch truthfully records binary non-keep without
fabricating either subtype.

Reject the branch unless all permitted worlds are non-keep and at least two
legacy judgment subtypes remain. If one subtype is forced, v3 requires the exact
legacy judgment. If both kept and non-kept worlds remain, use the ordinary
semantic-unresolved keep branch instead.

Add synthetic tests for all three domains: singleton exact judgment; plural
non-keep-only subtype domain; and plural kept/non-kept domain. Verify identical
rating arithmetic, scoped assessment blockers, known-treatment selectivity,
gate evidence dependency, old-profile rejection, and unchanged final815/V8/V9
behavior. All earlier execution and release holds remain in force.
