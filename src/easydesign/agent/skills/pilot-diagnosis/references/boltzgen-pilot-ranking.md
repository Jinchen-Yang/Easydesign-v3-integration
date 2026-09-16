# BoltzGen Pilot metric definitions

`boltzgen-pilot-metrics-v1`: verified against BoltzGen 0.3.2 commit
`a3149cf18eeb58648d1abbb27539bd73f746cdda`. The supplied manual contributes calculations
only: exclude lulu configuration, quality bands, coverage cutoffs, screening policy/outcomes.

Runtime retains raw columns/values, run/task/candidate, structure and NPZ mask references.
`design_mask` = generated/inserted/changed residues; `chain_design_mask` = their full chains.
A VHH mask usually covers CDRs, but actual NPZ membership is authoritative. Never infer CDR
numbering from length or equate design mask with whole VHH. Missing is unknown, not zero.
Coordinates/RMSD/PAE use angstroms; areas use square angstroms. Preserve native confidence
scales, identities and aggregation. Per-residue values require verified arrays/mapping.

Saved task `config/filtering.yaml`, pinned Filter code and `pass_<feature>_filter` columns
own rules, directions, thresholds and decisions; reconcile `pass_filters`. Only
`pass_filters=True` defines PASS; top/budget export folders can contain failures. Failed or
incomplete collection is distinct from scientific zero-pass. Do not import manual thresholds.
Native ordering ranks metrics with number-of-passed-filters priority, divides by inverse
importance weights, takes their maximum, ties by design_to_target_iptm. Retain this ordering;
Specialist may rank differently with explicit tradeoffs. Neither is biological fitness.

| Field | Calculation / scope |
| --- | --- |
| bb_rmsd | Original/refold complex backbone RMSD, complex alignment. |
| bb_rmsd_design | Design-mask backbone RMSD, design-subset alignment. |
| bb_rmsd_target | Target backbone RMSD, target alignment. |
| bb_rmsd_design_target | Design-mask RMSD, complex alignment. |
| bb_target_aligned_rmsd_design | Design-mask RMSD, target alignment: retained pose. |
| design_ptm | Full designed-chain confidence; d0 uses complex token length. |
| design_to_target_iptm | Design-mask to target interface confidence. |
| design_iptm | Whole designed-chain to target interface confidence. |
| design_iiptm | Interface-restricted confidence, source 8-angstrom neighborhood. |
| design_ipsae_min | Minimum directional ipSAE for full binder/target chain pair. |
| interaction_pae | Bidirectional design-mask/target mean PAE, includes distant target. |
| min_design_to_target_pae | Minimum design-mask/target PAE: one pair is not an interface. |
| complex_plddt / complex_iplddt | Native complex/interface confidence aggregates. |

Lower RMSD means geometric agreement under that exact alignment/mask; design-only agreement
does not prove retained pose. `filter_rmsd*` aliases follow active config, never relabel them
as whole-binder or target-aligned whole-binder RMSD. Higher iPTM/confidence is favorable;
lower PAE is favorable. Do not infer missing per-residue values from aggregates.

`delta_sasa_refolded`: target-side area occluded by design-mask atoms, target alone minus
target with design atoms. Not necessarily full-VHH BSA; distinct from EasyDesign
Shrake-Rupley `(SASA(A)+SASA(B)-SASA(AB))/2`. Neither measures affinity.
`plip_hbonds_refolded` actually uses Hydride/Biotite hydrogen-bond geometry. Salt bridges count
charged atom pairs, not unique residue pairs. EasyDesign heavy-atom polar-distance proxy
must not replace the native H-bond metric under its name.
`bindsite_under_*rmsd`: original-design center/CA proximity, not refold heavy-atom hotspot
contact. Runtime counts hotspot/avoid target residues contacting whole binder and actual
design mask separately, using CONTACT_ANGSTROM=5 and the existing severe-clash definition.
Keep residue IDs/mask scope with counts/fractions; these are ranking evidence, not new filters.
CDR participation may describe verified design-mask membership; CDR1/2/3 area decomposition
requires verified per-CDR masks. Sequence hashes/scaffolds/sequence differences describe
sequence diversity, not binding modes; measured contact patterns add complementary evidence.
