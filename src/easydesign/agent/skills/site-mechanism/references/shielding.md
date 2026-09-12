# Glycan / PTM / missing-region constraints

The existing N-X-S/T detector (X can be any residue except proline) provides sequence-motif
warnings only. Keep canonical sequence and engineered construct sequence distinct. Motif absence does not
prove glycan absence; motif presence does not prove occupancy or a modeled glycan shield.
Separate supplied experimental annotations, observed structural coordinates and inferred risk.
No glycan ensemble or occupancy calculation is available in this slice.

Prepared-chain SASA omits absent glycans, unresolved loops and excluded interaction partners.
Explain how those omissions could change an approach, and prefer a real alternative when its
evidence is stronger. Supplied PTM/glycan feature overlap warrants a warning; it is not alone
a deterministic prohibition. An explicit user exclusion or required region without mapped
coordinates is a hard constraint and cannot be overridden by a model recommendation.

Retain construct artifacts and mapping uncertainty. Conservation or a functional mutation may
support mechanistic relevance while saying little about binder accessibility or selectivity.
State the missing experiment/context rather than inventing shielding radii or binding success.
