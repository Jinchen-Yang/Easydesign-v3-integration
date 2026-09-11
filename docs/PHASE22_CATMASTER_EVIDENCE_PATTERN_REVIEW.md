# Phase 2.2 CatMaster evidence pattern review

Reviewed before EasyDesign implementation on 2026-09-11. Actual reference checkout:
`/data/agent-framework-study/CatMaster`, commit
`5246749f8d20cce144faa12f4535a5c9a4de4427`.
The six requested runtime files were read in full, together with the literature
pipeline in both `litreview_agent` and `research_specialist`, its selection and
review-compilation references, academic-search Skill and evidence attributes,
reader router, models and the scoped find implementation.

| Problem | CatMaster mechanism | Exact source path | ADOPT / ADAPT / REJECT | EasyDesign implementation decision |
| --- | --- | --- | --- | --- |
| Search results become an archive in context | `_format_web_search_content` returns bounded title, URL and snippet while artifact preserves data | `catmaster/runtime/literature/tools.py` | ADAPT | Compact provider/identifier/title/year/access-depth leads; discovery never automatically acquires every hit. Ranking is relevance, not scientific strength. |
| Every discovered paper is read | Auditable selected/deferred/excluded with task-specific reasons; shallow candidate records | `skills/litreview_agent/nature-literature-pipeline/SKILL.md`; `skills/litreview_agent/nature-literature-pipeline/references/selection-policy.md`; `skills/research_specialist/nature-literature-pipeline/SKILL.md` | ADOPT | Thread-scoped selection with a required reason; only selected sources can be acquired deeply. Durable raw evidence remains project-level. |
| Repeated remote retrieval/fulltext consumption | Acquire one selected source, cache locally, verify identity, return a receipt/path rather than PDF text | `catmaster/runtime/literature/acquisition.py` (`acquire_literature_source`, `_validate_pdf`, `_tool_result`) | ADAPT | Reuse existing ScientificHttpClient/raw source ArtifactRefs and PMID/PMCID/accession checks. Acquisition receipt describes availability and local corpus, never injects full response. |
| Corpus needed without new storage platform | Hash-deduplicated local documents and chunks; manifests and scoped path validation | `catmaster/runtime/literature/corpus.py` (`ingest_literature_files`, `_extract`, `_split_text`) | ADAPT | Small derived JSON chunk index over existing source ArtifactRefs, tied to target binding; no second SQLite/ORM/artifact registry. Keep full original bytes even when view is small. |
| Need a passage, not whole paper | FTS ranked partial locator snippets, page/section and query-bound cursor | `catmaster/runtime/literature/corpus.py` (`query_literature_corpus`, `_query_cursor`, `_decode_query_cursor`) | ADAPT | Bounded lexical retrieval within explicitly scoped evidence need/source; stable source + section/chunk location, query/view-bound continuation. Expose partial coverage honestly. |
| Need to continue reading narrowly | Pattern matches plus bounded neighboring text and character positions | `catmaster/runtime/literature/tools.py` (`FindInPageInput`, `find_in_page`); `catmaster/runtime/literature/online_search_adapter.py` (`find_in_page`) | ADAPT | Find/read from already acquired local chunks with on-demand continuation; do not refetch the remote page for every find. |
| Large general tool result | `content_and_artifact`, large field/whole artifact offload, bounded preview and stripped input echoes | `catmaster/runtime/tool_output_adapter.py`; `catmaster/runtime/tool_output_config.py` | ADAPT | Existing SessionStore offload retains full result; tool-owned compact scientific projection plus scoped read replaces raw pretty-JSON paging. Runtime binds hashes/identities. Bound model-visible content explicitly. |
| Entire project copied to each specialist | Role/task context with a small memory index, progressive disclosure | `catmaster/runtime/context_pack.py` (`ContextPackBuilder.build`); `skills/litreview_agent/nature-reader/SKILL.md` | ADAPT | Target/Site/Binder receive role/task projections. Research retrieval views are thread/execution scoped; approved science remains shared. Do not feed the full corpus or all prior retrieval messages into every delegation. |
| Unclear evidence/claim relationship | Claim-relative modality/access/condition/provenance and conflicting interpretations | `skills/litreview_agent/nature-academic-search/SKILL.md`; `skills/litreview_agent/nature-academic-search/references/evidence-attributes.md` | ADAPT | Protein-design EvidenceNeed cards with source locator, relation, claim, status and transfer limits. VERIFIED source identity is not VERIFIED scientific entailment. Judge gets bound support and relevant counterevidence. |
| Generic reference subsystem would expand scope | SQLite FTS, broad provider fallbacks, bibliography, review compilation, publisher browser dependencies | `catmaster/runtime/literature/corpus.py`; `catmaster/runtime/literature/acquisition.py`; `skills/litreview_agent/nature-literature-pipeline/references/review-compilation-workflow.md` | REJECT | Do not transplant platform, browsers, citation scoring, wiki, scheduling or manuscript workflow. Keep existing scientific provider allowlist and bounded research worker. |

Important source limitations: CatMaster's adapter offloads artifact data but leaves
tool-authored `content` essentially intact; `_json_tool_result` and raw page reading
can still be large. Its page snapshot is truncated to a character limit, and
`find_in_page` can fetch again. These are not evidence-retention guarantees to copy.
EasyDesign must retain original full bytes and explicitly budget its working views.
CatMaster's selection is primarily a Skill policy; EasyDesign will enforce the
acquisition selection boundary in runtime, not rely on a prompt alone.

Implementation acceptance remains pending. This review does not assert that the
reference patterns alone resolve EasyDesign's failed live cases. Keep the 60,000
input-character guard and measure every actual model request, retrieval counts,
corpus size, source retention, on-demand continuation and cross-thread isolation.
