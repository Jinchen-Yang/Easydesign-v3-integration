# BoltzGen Pilot metric definitions

Reference ID: `boltzgen-pilot-metrics-v1`. Verified against BoltzGen 0.3.2,
commit `a3149cf18eeb58648d1abbb27539bd73f746cdda`.
The supplied metric manual is used only for definitions and calculation methods.
Its lulu project configuration, quality bands, hotspot coverage thresholds, secondary
screening policy and project outcomes are excluded. No project heuristic is installed.

## Provenance and masks

Every native observation retains its original column name, raw value, run/task/candidate,
structure and design-mask references. `design_mask` means generated/inserted/changed
residues; `chain_design_mask` means their complete chains. A VHH design mask typically
covers CDR residues, but the actual NPZ mask owns membership. Never infer CDR numbering
from sequence length or equate the design mask to the whole VHH.

Metric absence is unavailable, never numeric zero. Units for coordinates, RMSD and PAE
are angstroms; areas are square angstroms. Confidence scales and aggregation must be
read under their original metric identity. Native values are retained without rescaling.

## Native filters and ordering

The actual task's saved `config/filtering.yaml`, the pinned Filter implementation and
recorded `pass_<feature>_filter` columns define active native hard filters. Preserve each
rule, direction, threshold, observed value and decision, and reconcile aggregate
`pass_filters`. A failed/incomplete collection is distinct from a scientific zero-pass Arm.
Do not import thresholds from this reference or any project manual.

Native quality ordering computes per-metric ranks with number-of-passed-filters priority,
divides ranks by inverse-importance weights, takes their maximum and breaks ties by
`design_to_target_iptm`. This is an engineering ordering, not a biological fitness equation.
Final exported top/budget folders can contain failures when too few pass; only native
`pass_filters=True` defines the primary candidate population. Record native ordering;
the Ranking Specialist may give a different scientific order with explicit tradeoffs.

## Refold and pose

| Native field | Calculation / scope |
| --- | --- |
| `bb_rmsd` | Original versus refold complex backbone coordinates after complex alignment. |
| `bb_rmsd_design` | Design-mask backbone RMSD after alignment of the design subset; not whole-VHH RMSD. |
| `bb_rmsd_target` | Target subset backbone RMSD with target alignment. |
| `bb_rmsd_design_target` | Design-mask RMSD after complex alignment. |
| `bb_target_aligned_rmsd_design` | Design-mask RMSD after alignment on target; assesses retained pose. |

Lower RMSD indicates greater geometric agreement under that specific mask/alignment.
A low design-only RMSD does not establish that the binding pose survives refold.
`filter_rmsd*` are aliases chosen by the active filtering configuration; do not silently
relabel a design-mask value as whole-binder self RMSD or target-aligned whole-binder RMSD.

## Confidence

| Native field | Meaning |
| --- | --- |
| `design_ptm` | Within full designed-chain confidence aggregation; d0 derives from complex token length. |
| `design_to_target_iptm` | Design-mask residues to target interface confidence. |
| `design_iptm` | Whole designed-chain to target interface confidence. |
| `design_iiptm` | Interface-restricted confidence using the source implementation's 8-angstrom neighborhood. |
| `design_ipsae_min` | Minimum of the two directional ipSAE calculations for full binder/target chain pair. |
| `interaction_pae` | Final native value is the bidirectional design-mask/target mean PAE, including distant target residues. |
| `min_design_to_target_pae` | Minimum design-mask to target PAE; one confident pair alone is not an interface. |
| `complex_plddt`, `complex_iplddt` | Native complex / interface confidence aggregates; retain source scale and mask. |

Per-residue confidence should be used only if its array and residue mapping are verified;
absence is not a reason to synthesize per-residue values from an aggregate.

## Geometry, chemistry and design intent

`delta_sasa_refolded` is target-side solvent area occluded by design-mask atoms, comparing
target alone with target plus design atoms. It is not automatically full-VHH interface
BSA. The existing EasyDesign Shrake-Rupley `(SASA(A)+SASA(B)-SASA(AB))/2` is a different
quantity and must keep a separate identity. Neither establishes affinity.

Native `plip_hbonds_refolded` uses the source Hydride/Biotite hydrogen-bond geometry
calculation, despite its historical column name. Native salt-bridge counts are charged
atom pairs, not unique residue pairs. EasyDesign's heavy-atom polar distance proxy is
not the same hydrogen-bond metric and must not replace it under the native name.

Native `bindsite_under_*rmsd` is original-design center/CA proximity, not refold heavy-atom
hotspot contact. Runtime supplementary metrics separately count target hotspot/avoid
residues with a heavy-atom contact to (a) whole binder and (b) actual design-mask residues.
Contact cutoff follows the existing `CONTACT_ANGSTROM` kernel (5 angstroms); clashes use
its existing severe-clash distance definition. These measurements are ranking evidence,
not new hard filters. Keep residue IDs and atom-mask scope with each count/fraction.

CDR interface participation can be reported for the actual design mask. CDR1/2/3-specific
area decomposition requires verified per-CDR masks; do not guess them. Sequence hashes,
scaffold coverage and designed-sequence differences describe sequence diversity, not
binding-mode diversity. Contact patterns provide additional evidence when measured.
