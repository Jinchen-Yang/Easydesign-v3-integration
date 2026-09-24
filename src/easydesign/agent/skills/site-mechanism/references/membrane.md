# Membrane / GPCR interpretation

Use only the supplied topology and the existing geometry tool. The current GPCR kernel
withholds a signed membrane frame unless mapping, helix geometry and direction agree.
An unresolved frame must remain unresolved; do not draw an extracellular plane from intuition.
`declared_topology` is user-supplied annotation mapped onto coordinates, not independently
established topology. TM/ECL/ICL labels, geometry-derived regions and mechanistic hypotheses
are distinct evidence layers.

For a relevant site compare extracellular availability, membrane proximality, loop/helix
context and a plausible VHH approach. Consider whether a framework could collide even when
individual residues have high SASA. Current tools do not perform full VHH docking or compute
binding free energy; accessible trajectory and membrane clearance are hypotheses to test.
For the mandatory extracellular deep-orthosteric GPCR preference, these untested approach
hypotheses remain downstream uncertainties and cannot demote the candidate from A.

State-dependent or ligand-associated exposure requires actual state evidence and a relevant
counterstate before claiming discrimination. With a single supplied state, describe the
mechanism sought and what counterstate/control would falsify it. Functional importance alone
is not proof of accessibility. An intracellular/TM region can be an exploratory proposal with
warnings; map/coordinate failures are the separate hard constraints.

Use the existing kernel definitions in `docs/workflow/02-hotspot-discovery.md`; do not replace
SASA, topology mapping or geometric calculations with model-generated numbers.
