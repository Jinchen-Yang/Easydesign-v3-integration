# GPCR Analysis, Handoff, and Review Contract

## 使用原则

GPCR dossier 是 prepare 阶段的只读研究证据，不是审批结果。结构分析、候选生成、Pydantic
校验和 HTML 投影必须共享同一份 canonical analysis；报告只负责展示，不得形成第二套科学数据源。
任何未解决的身份、膜方向、状态对比、残基映射或完整 scaffold 接近性都要显式保留，不能用空值或
页面交互掩盖。

## 目录

- [canonical projection](#canonical-projection-boundary)
- [typed analysis 与 candidate contract](#gpcr-hotspot-analysisjson)
- [decision context 与批量输入](#selection-and-decision-context)
- [离线 HTML revision](#offline-html-revision)
- [完整性与人工审阅边界](#review-manifest-and-integrity)

Use one scientific analysis schema as the source for both the unapproved handoff and the read-only HTML report. Keep presentation logic from becoming a second scientific authority.

## Canonical Projection Boundary

Treat outputs from the core structure-context and candidate-generation modules as typed components, not as the final dossier schema. Compose and validate `easydesign.stages.s02_hotspot_discovery.gpcr.GpcrSiteAnalysis`; preserve component schema versions and input hashes under provenance.

Apply this deterministic projection:

1. Set final `schema_version` to `1.0`; retain `gpcr-structure-analysis-v1` and `gpcr-hotspot-candidates-v1` as component schema identifiers.
2. Copy the verified receptor chain into both `structure.receptor_chain` and `identity.receptor_chain`.
3. Add resolved `entry_name`, accession, family slug/name, receptor class and species to `identity`; do not overwrite conflicts.
4. Convert `candidates.<mode>.<classification>[]` into a flat `candidates.<mode>[]`. Copy the group key into each row's `classification`, map `mechanism` to `role`, retain label/rationale/limitations, and add reviewed approach, state, risk, confidence, falsifier and assay fields.
5. Keep the detailed grouped generator output under `provenance.candidate_generation` only when useful for audit; do not maintain two editable candidate authorities.
6. Wrap component provenance lists under a top-level provenance object, for example `provenance.inputs`, `provenance.gpcrdb`, `provenance.project_context` and `provenance.generator`.
7. Copy state and membrane values only after reconciling GPCRdb annotations with structure-derived warnings. An unreliable signed frame must remain unresolved and cannot yield a primary candidate.
8. Validate the resulting object with `GpcrSiteAnalysis.model_validate()` before writing anything.

Never infer missing approach geometry, functional direction or approval status during projection. Downgrade incomplete generated hypotheses to `unresolved` until they satisfy the review contract.

## Analysis Bundle

Write each structure analysis into a new directory with exactly these core files:

```text
analysis-bundle/
  gpcr-hotspot-analysis.json
  gpcr_hotspot_handoff.yaml
  analysis-manifest.json
```

Publish through EasyDesign's normal artifact writer and manifest/checksum boundary; do not reintroduce a Skill-local bundle writer. Refuse a non-empty immutable revision directory. Until a GPCR dossier is admitted to the official prepare artifact manifest, label it a read-only research dossier rather than a completed prepare artifact. Any handoff must always contain:

```yaml
approval_status: awaiting_human_review
ready_for_strategize: false
```

Do not create or overwrite native EasyDesign `hotspots.yaml`, site approval state or strategy state.

## `gpcr-hotspot-analysis.json`

Use UTF-8 JSON and `schema_version: "1.0"`. Required top-level fields are:

| Field | Type | Contract |
| --- | --- | --- |
| `schema_version` | string | Exactly `1.0` |
| `analysis_id` | string | Stable unique identifier for this immutable analysis |
| `generated_at` | string | UTC ISO-8601 timestamp |
| `mode` | string | `inhibit`, `activate`, or `both` |
| `structure` | object | Input identity, path, hash, format and receptor chain |
| `identity` | object | GPCR entry/accession, family/receptor class and resolution evidence |
| `topology` | object | Mapping status plus residue mapping entries |
| `state` | object | Assignment, target/counterstate and evidence |
| `membrane` | object | Orientation status, normal, boundaries, source and confidence |
| `chain_graph` | object | Every chain/ligand/partner and biological role |
| `candidates` | object | Separate `inhibit` and `activate` arrays as required by `mode` |
| `avoid` | array | Explicit excluded regions/residues and reasons |
| `evidence` | array | Typed, source-addressable evidence records |
| `warnings` | array | Unresolved scientific or integrity issues |
| `provenance` | object | Tool version, project/Target Bundle identifiers, endpoint hashes and input hashes |

Recommended stable shape:

```json
{
  "schema_version": "1.0",
  "analysis_id": "adrb2-structureA-both-r1",
  "generated_at": "2026-08-16T00:00:00Z",
  "mode": "both",
  "structure": {
    "id": "structureA",
    "path": "structure/receptor.cif",
    "sha256": "<64 lowercase hex>",
    "format": "mmcif",
    "receptor_chain": "A",
    "assembly": "biological assembly 1"
  },
  "identity": {
    "entry_name": "adrb2_human",
    "accession": "P07550",
    "family_slug": "001_001_003_008",
    "family": "Beta-2 adrenergic receptor",
    "receptor_class": "Class A (Rhodopsin)",
    "species": "Homo sapiens",
    "status": "resolved"
  },
  "topology": {
    "mapping_status": "resolved",
    "mapping_coverage": 1.0,
    "residues": []
  },
  "state": {
    "assignment": "inactive",
    "target": "inactive",
    "counterstate": "active",
    "confidence": "high",
    "evidence_ids": []
  },
  "membrane": {
    "status": "resolved",
    "normal_extracellular_to_intracellular": [0.0, 0.0, -1.0],
    "bilayer_midplane": [0.0, 0.0, 0.0],
    "headgroup_boundaries": [-15.0, 15.0],
    "source": "<method or source>",
    "confidence": "high"
  },
  "chain_graph": {"chains": [], "edges": []},
  "candidates": {"inhibit": [], "activate": []},
  "avoid": [],
  "evidence": [],
  "warnings": [],
  "provenance": {}
}
```

Do not use the example values as defaults. In particular, do not invent resolved membrane coordinates or mapping coverage.

## Residue Mapping Object

Represent every hotspot, avoid residue and topology row with both label and author namespaces:

```json
{
  "label_asym_id": "A",
  "label_seq_id": 113,
  "auth_asym_id": "A",
  "auth_seq_id": 113,
  "insertion_code": null,
  "amino_acid": "D",
  "sequence_index": 112,
  "gpcrdb_sequence_number": 113,
  "generic_number": "3x32",
  "alternative_generic_numbers": [],
  "segment": "TM3",
  "observed": true,
  "mapping_status": "exact",
  "mapping_note": null,
  "membrane_facing": "pocket_facing",
  "functional_role": "orthosteric_anchor",
  "evidence_ids": ["evidence-001"]
}
```

Keep `auth_seq_id` as the deposited identifier even when it is non-contiguous. Preserve an insertion code separately. Never identify a residue only by an integer when more than one chain is present.

## Candidate Object

Each item in `candidates.inhibit` or `candidates.activate` must include:

| Field | Contract |
| --- | --- |
| `id` | Unique within the mechanism array |
| `classification` | `primary`, `backup`, `avoid`, or `unresolved` |
| `role` | Mechanism-specific role, such as `extracellular-rim-blockade` |
| `hypothesis` | Testable causal statement |
| `functional_site` | Broader contextual region; not automatically exported as hotspots |
| `residues` | Small conditioning-hotspot residue array with dual numbering |
| `target_state`, `counterstate` | Explicit state claim |
| `approach_direction` | Three-vector or structured cone in membrane coordinates |
| `approach_checks` | CDR access, framework/membrane/ECD/glycan/protomer collision outcomes |
| `evidence_tier` | `T1`, `T2`, `T3`, `T4`, or `UNRESOLVED`; retain a separate evidence subtype |
| `evidence_ids` | References into the top-level evidence list |
| `hard_gates` | Named gate results and reasons |
| `risks` | Explicit soft-risk list |
| `confidence` | `high`, `medium`, `low`, or `unresolved`; never a disguised score |
| `falsifier` | Observation that rejects the mechanism |
| `assays` | Primary functional assay and orthogonal controls |

Never add `fused_score` or `winner`; the validator rejects both. Do not rank an unresolved-membrane candidate as `primary`.

## Avoid Records

Use explicit records instead of relying on unmarked residues:

```json
{
  "id": "avoid-intracellular-transducer",
  "classification": "avoid",
  "scope": "region",
  "role": "intracellular-transducer-interface",
  "residues": [],
  "reason": "Default extracellular binder must not target the G-protein face",
  "source_ids": ["evidence-004"]
}
```

The current EasyDesign compiler does not require a native `not_binding` emission for this review artifact. Keep the avoid mask in the dossier and let unselected residues remain neutral in any later, separately approved site proposal.

## Evidence Records

Each evidence record should contain:

- `id`, `tier`, `type` and a concise claim.
- Receptor, construct, state, ligand and assay match/mismatch.
- Stable source identifier: DOI, PMID, PDB code, GPCRdb endpoint or project artifact ID.
- URL when public and permissible.
- Retrieval time and SHA-256 for downloaded/API material.
- Exact residue mapping or domain mapping used by the claim.
- Contradictions, limitations and whether the evidence is direct or inferred.

Do not store a citation without the claim it supports.

## Selection and Decision Context

An optional selection file may constrain residues, but a `primary` classification additionally requires explicit decision context. Use this shape:

```yaml
include: []
exclude: []
review_context:
  binder_format: vhh
  access_side: extracellular
  modes:
    inhibit:
      target_state: active
      counterstate: inactive
      assays:
        - state-matched signaling inhibition
        - orthogonal occupancy or competition
      falsifier: Verified occupancy does not change the state-matched functional response.
      approach_clearance: pass
      allow_deep_cavity: false
    activate:
      target_state: active
      counterstate: inactive
      assays:
        - basal and agonist-stimulated signaling with expression controls
      falsifier: Verified occupancy does not increase signaling over matched controls.
      approach_clearance: pass
      allow_deep_cavity: false
```

`approach_clearance: pass` is a reviewed geometric claim covering CDR access and full-framework collision with membrane, ECD/glycan and partner/protomer context. The software never infers it from a residue centroid alone. For an extracellular antibody/VHH/protein binder, a deep 7TM core remains failed unless `allow_deep_cavity: true` is explicitly justified and clearance is passed; this flag records the review decision and does not require or prescribe a long CDR3. Missing decision context still permits a dossier, but all automatic primaries become `unresolved` and the missing fields are reported.

## Batch Review Input

`easydesign.reporting.gpcr_site_review.generate_review_report()` accepts a directory containing zero or more `gpcr-hotspot-analysis.json` files, one analysis JSON, a sequence of `ReviewInput`, or a JSON/YAML batch manifest. It uses packaged templates and the pinned local Mol* assets, so it must work without a source checkout. Use this portable manifest shape when explicit pairing is needed:

```yaml
structures:
  - structure_id: receptor-state-01
    analysis_path: analyses/receptor-state-01/gpcr-hotspot-analysis.json
    structure_path: structures/receptor-state-01.cif
    receptor_chain: A
```

Resolve relative paths against the batch manifest. Require unique structure IDs/slugs. Accept only PDB/ENT or mmCIF/CIF source structures.

To analyze raw structures and immediately publish a review revision through `batch-review`, use this fixed manifest shape:

```yaml
structures:
  - structure_id: receptor-state-01
    path: structures/receptor-state-01.cif
    gpcr_entry: receptor_human       # use accession instead when entry is unavailable
    accession: null
    receptor_chain: A
    state: active
    mode: both
    membrane_orientation: annotations/receptor-state-01-membrane.json  # optional
    selection: annotations/receptor-state-01-selection.yaml             # optional
```

Each raw entry must contain `structure_id`, `path`, `receptor_chain`, `state` and `mode`, plus exactly one resolvable GPCR identity (`gpcr_entry` or `accession`). Optional orientation and selection paths are still integrity-checked and resolved relative to the manifest. Omit an optional field instead of using a guessed value. An empty `structures` list is valid and produces a zero-structure review index; duplicate IDs, ambiguous chains or unresolved identities fail before report publication.

## Offline HTML Revision

Generate a new revision under a dedicated report base:

```text
review-output/
  LATEST
  report-0001/
    index.html
    review-manifest.json
    assets/
      molstar.js
      molstar.css
      MOLSTAR_LICENSE.txt
      report.css
      index.js
      structure.js
    structures/
      <structure-slug>.html
    data/
      <structure-slug>/
        structure.cif
        gpcr-hotspot-analysis.json
        review-data.js
```

`LATEST` points to `report-NNNN/review-manifest.json`. Never rewrite an older `report-NNNN`. The index must support scanning and filtering by receptor/family/state and show inhibit/activate candidate counts plus warnings. Each structure page must show:

- Local Mol* structure view without CDN or network dependency.
- Receptor and chain context, non-receptor partners and membrane status.
- Selectable primary, backup, avoid and unresolved candidates.
- Hotspot residues with label/auth/GPCRdb numbering.
- Functional hypothesis, approach direction, evidence tier, risks and falsifier.
- Provenance and input hashes.

Keep the report read-only. Browser actions may change visibility, camera, representation and selected candidate, but must not mutate analysis JSON, approve a site or write project state.

## Review Manifest and Integrity

The review manifest must include:

- Schema, generator and immutable revision identifiers.
- UTC creation time and requested mode.
- Mol* version and expected asset hashes.
- Structure count and one entry per analysis/structure pair.
- SHA-256 for every copied analysis and structure.
- A complete allowlist of report files with relative POSIX path, role, size and SHA-256.

The allowlist covers every report payload except `review-manifest.json` itself. Self-exclusion is required because embedding the manifest's own SHA-256 would be recursively undefined; the `LATEST` pointer resolves the manifest and validation hashes every declared payload before use.

Run `easydesign.reporting.gpcr_site_review.validate_review_report()` before handing off. Fail when:

- `LATEST` is missing or points outside the report base.
- A declared file is missing, modified, a symlink or has the wrong size/hash.
- An undeclared file appears in the revision.
- Any page uses an HTTP(S) CDN, `file:` URI or absolute filesystem path.
- Mol* assets do not match the pinned local version/hashes.
- Structure IDs collide or structure/analysis paths cannot be resolved.

Opening `index.html` must work offline. When a local server is needed for browser restrictions, bind loopback only and serve the immutable report directory; do not add write endpoints.

## Human Review and EasyDesign Handoff

Present at most three design hypotheses as A/B/C, each with a distinct mechanism or approach geometry. Keep any number of avoid/unresolved records for audit. During review, require the human to check:

1. Correct receptor chain, construct and GPCRdb identity.
2. Correct extracellular/intracellular orientation and membrane-facing labels.
3. Correct target state and counterstate.
4. Plausible full-scaffold approach, not only local residue exposure.
5. Family-specific domain, cleavage, glycan, dimer and autoinhibition context.
6. Residue mapping in both label and author numbering.
7. Evidence, risks, falsifier and assay compatibility.

After review, the user may explicitly choose a hypothesis for the existing EasyDesign `site propose` flow. The report itself remains read-only: it must never change `approval_status`, set `ready_for_strategize: true`, or imply that HTML inspection constitutes approval. When the user has not asked to continue, finish by reporting the dossier/report location and unresolved scientific gates instead of issuing a mandatory confirmation prompt.
