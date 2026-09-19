# NK2R Site latency repair ledger — 2026-09-19

## Scope

This ledger records fresh human-NK2R Gate 2 attempts used to validate the Site
latency hardening branch. Every accepted attempt must start from Gate 1 in a new
project and thread. Earlier NK2R dossiers, candidate residues, rankings and
decisions are not supplied to the scientific Agent.

- Repository: `/data/easydesign-worktrees/figure2-ab-20260918`
- Branch: `codex/site-intelligence-latency-20260919`
- R5–R10 baseline: `8efc930c218c96d5ea1eb31a36975c8dc891cd00`
- Initial latency commit: `58a389d01a8d1665cd7a2484183f141e739cfb65`
- Provider/profile: `deepseek / deepseek-v4-pro`
- Target: fresh RCSB 9W2H mmCIF, SHA-256
  `33ff56e619b30fbb1edeba2d58726aaf78006ad1b2480416b97bb4892e488e51`

## R10 read-only equivalence replay

The saved R10 authoritative dossier was opened read-only. The compact v2 decision
working set preserved all three candidate IDs, every exact hotspot design label,
and all three research findings.

- Full immutable dossier: 98,999 compact characters.
- Decision working set: 26,420 compact characters.
- Reduction: 73.3%.
- Source project mutation: none.

## Attempt R11 — invalidated

- Project: `figure2-nk2r-site-fast-r11`
- Thread: `thread-335f7e94d6ae45c1b1b4e0d391866302`
- Start commit: `58a389d01a8d1665cd7a2484183f141e739cfb65`
- Gate 1: independently resolved human NK2R P21452 and auth chain R / label chain B.
- Gate 1 wall time: 147.55 seconds.
- Status: stopped during Gate 2 Site synthesis; retained as defect evidence.
- Manual scientific answer injection: none. Gate 1 chain R approval used the
  standing Scientist authorization.

### SITE-LATENCY-001 — synthesis did not enter compact structured submission

Trigger:

- Site synthesis received a 32,700-character input including its schema.
- The first response ran for 167.82 seconds, consumed 16,384 output tokens, and
  returned no `RankedSiteDecision` tool call.
- The second identical repair call was stopped once the generic cause was proven.

Before:

- Compact/non-thinking submission was enabled for Site Research finalization and
  Judge truncation recovery.
- Normal Site synthesis was marked submission-only but retained the role's high
  reasoning model.
- The Anthropic-compatible SDK dropped forced tool choice when thinking remained
  enabled.

Root cause:

- `compact_site_submission` omitted `site_stage == synthesis`.

Repair:

- Every Site synthesis call now uses the same model/provider with thinking
  disabled from its first call.
- The only offered output remains `RankedSiteDecision`; all existing hydration,
  citation, hard-fact and contract validation remains unchanged.

After:

- Wire-level tests verify high-reasoning DeepSeek configuration is converted to
  `thinking=disabled`, removes `output_config`, and retains forced structured
  tool choice for Site synthesis.

### SITE-LATENCY-002 — atomic GPCR kernel existed but was not deliverable

Trigger:

- GPCRdb acquisition correctly produced one
  `research-receptor-analysis` artifact.
- The Harness then hid `analyze_receptor_context` merely because that artifact
  existed.
- The Agent received only an `analysis_ref`, could not read the compact kernel,
  paged raw GPCRdb source content, and reached the Research call boundary without
  usable topology/candidate context.

Before:

- Atomic kernel computation avoided one duplicate analysis but also removed the
  model-facing compact read.

Root cause:

- Kernel computation and kernel delivery were treated as the same operation.

Repair:

- GPCRdb acquisition still computes the deterministic kernel once.
- The Harness offers one scoped `analyze_receptor_context` call after acquisition.
- `EvidenceResearch.analyze_receptor` verifies current Target binding and auth
  chain, then reuses the stored analysis without calling `analyze_structure`.
- After the successful compact delivery, the Harness removes the tool for the
  remainder of the execution.

After:

- Regression tests prove the second model-facing call returns the identical
  artifact/card and the structure analysis call count remains one.
- The Site model receives the compact topology, membrane, chain graph, candidate
  and approved design-mapping projection.

## Validation

- Initial latency patch affected suite: 144 passed.
- R11 repair focused suite: 107 passed.
- Ruff: passed.
- Mypy before R11 repair: 213 source files passed.
- R11 is invalidated because product code changed after it started.
- The next accepted validation must use a new project and thread from Gate 1.

