# GPCRdb Integration Contract

## 使用原则

GPCRdb 在这里是可追溯的注释来源，不是受体身份、构建体组成、膜方向或功能因果性的唯一权威。
每个用于决策的响应都要保留 endpoint、获取时间、内容哈希、缓存状态和解释版本；可选 endpoint
失败必须记录为未知，不能伪装成空的生物学结果。身份冲突或热点残基映射歧义时停止主候选发布。

## 目录

- [访问与 endpoint](#access-contract)
- [身份和家族解析](#identity-resolution)
- [generic numbering 与残基映射](#generic-numbering)
- [结构和状态上下文](#structure-and-state-context)
- [失败语义](#failure-semantics)

Use GPCRdb as a curated annotation source, not as the sole authority for receptor identity, construct composition, membrane orientation, or functional causality. Preserve every response used for a decision with its retrieval metadata and content hash.

Official references:

- [GPCRdb web services](https://docs.gpcrdb.org/web_services.html)
- [GPCRdb generic numbering](https://docs.gpcrdb.org/generic_numbering.html)
- [GPCRdb structures](https://docs.gpcrdb.org/structures.html)
- [GPCRdb OpenAPI service description](https://gpcrdb.org/services/?format=openapi)

## Access Contract

Use the core `easydesign.backends.gpcrdb.GpcrdbAdapter` for read-only HTTP GET access. The prepare orchestration owns its `ScientificHttpClient`, cache mode, retry policy and provenance records; do not create a second GPCR-specific transport or cache. Do not send mutations, credentials, unpublished sequences, or project artifacts to GPCRdb.

For every request, retain:

- HTTP method, canonical endpoint and resolved HTTPS URL.
- Retrieval time, status code, response SHA-256 and cache record path.
- Source status: `network`, `cache`, or stale-cache fallback.
- Structured warning/error, including identifier conflicts and optional endpoint failures.
- The OpenAPI retrieval date or schema snapshot used to interpret fields.

Treat a cached response as evidence with an age, not as timeless truth. In offline mode, accept only a hash-valid cache entry; on a cache miss, stop that branch explicitly. Never convert an endpoint failure into an empty successful result.

## Endpoint Surface

Use the smallest necessary set. Confirm the live OpenAPI contract before adding fields or endpoints.

| Purpose | Endpoint | Required fields used by this skill |
| --- | --- | --- |
| Resolve receptor by entry | `/protein/{entry_name}/` | `entry_name`, `name`, `accession`, `family`, `species`, `source`, `residue_numbering_scheme`, `sequence`, `genes` when present |
| Resolve receptor by accession | `/protein/accession/{accession}/` | Same protein fields; recover canonical `entry_name` |
| Resolve family | `/proteinfamily/{slug}/` | `slug`, `name`, `parent` chain when present |
| Basic topology | `/residues/{entry_name}/` | `sequence_number`, `amino_acid`, `protein_segment`, `display_generic_number` |
| Extended topology | `/residues/extended/{entry_name}/` | Basic fields plus `alternative_generic_numbers` when present |
| Resolve one structure | `/structure/{pdb_code}/` | `pdb_code`, `protein`, `class`, `family`, `species`, `preferred_chain`, `resolution`, `publication_date`, `type`, `state`, `distance`, `publication`, `ligands`, `signalling_protein` when present |
| Receptor structures | `/structure/protein/{entry_name}/` | Available receptor structures and their construct/state metadata |
| Representative structures | `/structure/protein/{entry_name}/representative/` | Curated representatives by state when available |
| Small-molecule contacts | `/structure/{pdb_code}/interaction/` | Contact records; optional evidence only |
| Peptide contacts | `/structure/{pdb_code}/peptideinteraction/` | Peptide-receptor contact records; optional evidence only |
| Signalling-complex contacts | `/structure/{pdb_code}/complexinteraction/` | Receptor-transducer contacts; use mainly to identify intracellular avoid surfaces |
| Mutation evidence | `/mutants/{entry_name}/` | Mutation and assay records; preserve assay context |
| Ligand records | `/ligands/{entry_name}/` | Ligand identity/type and available pharmacology context |

Do not assume every field or optional endpoint is populated for every receptor. Keep `null` distinct from an empty biological set.

## Identity Resolution

Resolve identity in this order:

1. If a PDB code is supplied, fetch `/structure/{pdb_code}/` and record `protein` plus `preferred_chain`.
2. Fetch the resulting entry through `/protein/{entry_name}/`.
3. If only an accession is supplied, resolve it through `/protein/accession/{accession}/`, then fetch the canonical entry.
4. Cross-check GPCRdb entry, accession, species, the current prepare Target Bundle sequence, structure polymer sequence and receptor chain.
5. Accept aliases only when they resolve to the same accession and sequence. Do not select the closest receptor by display name.

Stop primary selection when:

- PDB receptor, supplied entry and supplied accession disagree.
- More than one structure chain can satisfy the receptor identity without a deterministic chain-role record.
- The prepare Target Bundle receptor sequence represents an isoform, species or construct that cannot be reconciled with the GPCRdb wild-type sequence.
- A fusion, chimeric receptor, engineered loop or stabilizing construct is mistaken for the native receptor sequence.

Record unresolved conflicts in `warnings` and keep all fetched records. Do not silently choose one identifier.

## Family Resolution

Use the receptor protein's `family` slug and resolve its parent chain. Match the top GPCR family by the first slug component only after confirming the parent hierarchy:

| Top slug | GPCRdb top family |
| --- | --- |
| `001` | Class A (Rhodopsin) |
| `002` | Class B1 (Secretin) |
| `003` | Class B2 (Adhesion) |
| `004` | Class C (Glutamate) |
| `005` | Class D1 (Ste2-like fungal pheromone) |
| `006` | Class F (Frizzled) |
| `007` | Class O1 |
| `008` | Class O2 |
| `009` | Class T2 |
| `010` | Other GPCRs |

Do not treat non-receptor GPCRdb branches such as G-protein families as receptor families. If the parent chain is incomplete or unfamiliar, classify the family as unresolved and use receptor-specific evidence only.

## Generic Numbering

Keep generic numbers as strings, including the GPCRdb `x` separator. Do not parse `3x32` as a decimal or assume the same display scheme across classes. Preserve:

- `display_generic_number` exactly as returned.
- Every `alternative_generic_numbers` entry with its numbering scheme.
- The receptor's `residue_numbering_scheme`.
- The absolute GPCRdb `sequence_number` and one-letter amino acid.
- The GPCRdb `protein_segment`, including N-term, TM1-TM7, ECL/ICL, H8 and C-term labels when present.

Use generic numbers to compare homologous positions only after validating the family-specific scheme and sequence alignment. Never use a generic number alone as a structure residue identifier.

## Deterministic Residue Mapping

Build one auditable mapping table from GPCRdb wild-type sequence to the prepare Target Bundle receptor sequence and then to observed structure residues. Use a structured mmCIF/PDB parser; do not extract residue identities with ad hoc text matching.

For every mapped residue, emit:

| Field | Meaning |
| --- | --- |
| `gpcrdb_sequence_number` | GPCRdb wild-type position |
| `amino_acid` | Expected one-letter amino acid |
| `protein_segment` | GPCRdb topology segment |
| `display_generic_number` | Exact displayed generic number or `null` |
| `alternative_generic_numbers` | Unmodified list from GPCRdb |
| `sequence_index` | prepare Target Bundle receptor-sequence index |
| `label_asym_id`, `label_seq_id` | Stable structure label identifiers |
| `auth_asym_id`, `auth_seq_id`, `insertion_code` | Author-facing identifiers for review |
| `observed` | Whether coordinates exist in the selected model |
| `mapping_status` | `exact`, `conservative_construct_difference`, `missing_coordinates`, or `unresolved` |
| `mapping_note` | Isoform, mutation, insertion, deletion or engineered-construct explanation |

Apply these rules:

1. Anchor the mapping by verified accession/entry and full polymer sequences, not residue numbers alone.
2. Preserve engineered substitutions as construct differences; do not rewrite their amino-acid identity to wild type.
3. Preserve missing coordinates as explicit gaps. Do not shift subsequent author numbers to close them.
4. Keep insertion codes and label/auth namespaces separate.
5. Require amino-acid agreement at every proposed hotspot or a documented construct mutation.
6. Require an unambiguous local mapping spanning the entire candidate and its immediate structural context.
7. Reject primary publication if one residue maps to multiple structure positions or a proposed hotspot lacks coordinates.

Report whole-receptor mapping coverage as context, but do not use a global percentage to excuse ambiguity at the selected site.

## Structure and State Context

Treat GPCRdb state labels as curated evidence, then cross-check the deposited structure:

- Record PDB code, preferred receptor chain, resolution/method, construct type, bound ligand class and signalling protein.
- Record whether the structure is active, inactive, intermediate, predicted or unresolved according to the source.
- Inspect missing loops/domains, stabilizing mutations, fusion partners, truncations, antibodies/nanobodies and crystal contacts.
- Keep a selected state and a counterstate when the mechanism requires state selectivity.
- Do not infer membrane normal from GPCRdb segment labels alone.

Interaction records identify contacts, not causal hotspots. A ligand-contact residue becomes a functional-site candidate only when state, pharmacology, accessibility and independent evidence support the mechanism.

## Failure Semantics

Use these statuses consistently:

- `resolved`: exact identity and required site mapping are available.
- `partial`: identity is resolved but optional annotations or non-site coordinates are missing.
- `stale_cache`: a hash-valid cached record was used after a network failure; record age and warning.
- `offline_cache_miss`: the required response is absent; stop the affected analysis.
- `identifier_conflict`: supplied identifiers disagree; stop primary selection.
- `mapping_conflict`: site residues cannot be mapped uniquely; stop primary selection.
- `schema_change`: required response fields changed or disappeared; preserve raw response and stop interpretation.

Never fabricate topology, generic numbers, state or interaction records to keep the workflow moving.
