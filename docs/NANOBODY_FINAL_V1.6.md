# Nanobody Final Filter v1.6

## Scope

Version 1.6 applies the frozen v1.5 final thresholds to
`openfold3-af3-jax` evidence and strengthens multi-seed consensus from two to
three individually passing seeds.

## Sampling

- The Top 400 screen remains seed 101 with one diffusion sample.
- The Top 60 deep panel uses seeds 101, 202, 303, 404 and 505.
- Each deep seed produces five diffusion samples.
- The highest `ranking_score` sample is that seed's representative.
- All 25 raw structures and confidence files remain immutable evidence.
- At least three of five representatives must independently pass the hard
  gates before pairwise RMSD and hotspot-contact Jaccard consensus is applied.

## Frozen thresholds

Pairwise ipTM is at least 0.60, interface PAE is at most 10 Å, binder pTM is at
least 0.60, target CA RMSD is at most 3 Å, hotspot coverage is at least 0.40,
and the existing clash gates remain unchanged. Consensus uses the existing 7 Å
interface PAE, 2.5 Å pose RMSD, 3 Å pair RMSD and 0.50 contact-Jaccard limits.

The metric definition is
`openfold3-p2-af3-jax-complex-confidence-v1`. gPDE is not synthesized.
