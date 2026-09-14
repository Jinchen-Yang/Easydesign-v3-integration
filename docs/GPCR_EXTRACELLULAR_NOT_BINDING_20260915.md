# Extracellular GPCR VHH: executable default exclusions

This Gate 3 delta implements the scientist's required default: every standard arm inherits
verified intracellular and transducer-facing receptor residues in actual YAML `not_binding`.
It does not change Site ranking, the approved hotspot, seven-scaffold coverage, CDR semantics,
arm-specific binding subsets, or Gate authority.

## Source and projection contract

`agent/design_exclusions.py` reads the approved Site proposal's immutable research snapshot,
not the new Binder thread's initially empty research history. The existing official annotation
reader verifies accession, canonical sequence hash and source ArtifactRefs. Exact cytoplasmic
ranges are joined to approved canonical-to-design mapping. Declared ICL/C-terminal topology
and explicit exclusions are retained. Coordinate-missing rows are recorded but not emitted
as executable residue labels.

Saved GPCR kernel analyses must match current Target binding, accession, source chain and
source structure SHA. A reliable signed membrane frame can supply intracellular geometry.
G-protein/arrestin interfaces use saved heavy-atom contacts with explicit partner roles;
recognized deposited mmCIF entity names can supply a role missing from the kernel's chain
graph. Chain letters, arbitrary partner contact, all TM residues and unselected Sites do not
establish exclusions. Contact residues are joined by source auth chain/residue, insertion code
and coordinate model, then emitted in design numbering. No network call or new geometry is
required. Unknown partners and absent annotations are not invented or certified safe.

Provenance and limitations are exposed as `gpcr_exclusions` in Binder/Judge evidence and the
Scientist card. This is a source-verified policy projection, not proof of physiological
occupancy, membrane clearance or inhibitory efficacy.

## Runtime behavior

- Applies when `target_kind=gpcr` and `required_site_compartment=extracellular`; the supported
  Binder modality is VHH. Non-GPCR and explicitly intracellular designs retain their defaults.
- Effective avoid = GPCR defaults ∪ approved Site exclusions ∪ each arm's explicit avoid.
  Switching scaffold templates cannot remove these target constraints.
- Both model preflight and final compilation use the same resolver. Binding overlap and
  crops losing exclusions remain blocking constraints. Lists can exceed forty residues and
  survive saved intent/Judge/card reconstruction; the bounded maximum is 3000.
- Native expert YAML is never rewritten. Its actual validated YAML `avoid` summary, rather
  than the empty standard-strategy field, must contain required exclusions. Missing exclusions
  produce a blocked specification for revision.
- Policy identity and source references enter the Design input binding. Old pending cards
  cannot approve a specification that predates the new exclusions. Historical inputs,
  proposals, cards and approvals are not overwritten.

## Verification

The targeted regression set covers canonical/design numbering differences, missing coordinates,
foreign/ambiguous source rejection, explicit partner roles and model-specific contact mapping,
signed geometry, all 21 standard YAMLs, template independence, binding/crop conflicts, stale
cards, idempotence and native input preservation. Existing GPCR template and Design runtime
tests retain their coverage. No Gate 1 or literature rerun is required for this delta.

The NK2R case uses saved P21452/9W2H evidence and the already approved B hotspot. Saved-design
replay and any subsequent independent review are separate validation records; this document
does not claim a new full fresh acceptance run, Gate 3 approval or candidate generation.
