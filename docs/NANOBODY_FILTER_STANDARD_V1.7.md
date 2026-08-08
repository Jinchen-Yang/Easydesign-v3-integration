# Nanobody Filter Standard v1.7

## Scope

Version 1.7 is the OpenFold3/AFO metric-definition revision of the frozen v1.6
pilot policy. It keeps the v1.6 sequence, geometry, promotion, diagnostic and
Stage 06 allocation rules unchanged.

## Prediction identity

- Backend: `openfold3-af3-jax`.
- Model: OpenFold3 preview2, `of3-p2-155k`.
- Metric definition: `openfold3-p2-af3-jax-complex-confidence-v1`.
- Templates are disabled.
- Target is chain A and binder is chain B.
- Target MSA is required; binder MSA is query-only.
- Pilot prediction uses seed 101 and one diffusion sample.
- gPDE is not available and must be reported as `N/A`.

## Normalized confidence

`pairwise_iptm` is `chain_pair_iptm[A][B]`, `binder_ptm` is chain B
`chain_ptm`, and minimum interface PAE is recomputed from both A→B and B→A
entries of the full token PAE matrix. Native summary and full-confidence files
remain immutable evidence.

## Gates and promotion

All numeric gates, score weights, Tier A promotion, diagnostic expansion and
50,000-candidate Stage 06 allocation are exactly those in v1.6. This revision
changes backend identity and metric provenance, not threshold values.
