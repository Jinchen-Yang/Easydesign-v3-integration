# SiteDecision saved-evidence replay — engineering checkpoint, not Golden acceptance

The authoritative scope is PHASE2_FINAL_ASSIGNMENT_20260912.md: finish Phase2 and stop.
Accepted Cases1/3/4/5 and their immutable snapshots remain preserved. Case2 is not yet PASS.

## Boundary

Research remains agentic and uses native DeepAgents memory. The immutable Site Dossier retains
source provenance, exact runtime candidate membership/mapping, original research questions and
fallible opinions. The synthesis projection uses candidate facts, decision-critical passages,
evidence interpretations and explicit unresolved questions. Preliminary candidate preferences,
duplicate impact summaries and stopping narrative do not enter synthesis; they remain durable
and available to the independent Judge. No primary opposing passage is removed by sentiment.
Synthesis has only the small SiteDecision output tool. Runtime hydrates exact SiteIntent facts.
No model, reasoning level, shared call budget or context guard changed.

## Replays

Source: approved104 GPCR project, live177 threadlive-site-20260912t065218389484z.
Original dossier SHA49a5f5d24478abf5e983f125a37f2defadff62b9c6386c1fdd084c623c2e42f9.
Source project SQLite was opened read-only; no new research or original checkpoint mutation.
Reports are under runtime/tmp/autonomous-v3-20260912/.

- decision178-model-replay-20260912T163702Z on ec110399: a typed decision omitted alternative
  IDs. Runtime rejected it. Schema/Skill now clarify that compared IDs include rejected/avoid
  alternatives, without implying recommendation. Original failed log remains.
- decision178-model-replay-20260912T164034Z on15869819: two typed decisions hydrated correctly;
  independent Judge submitted an empty object. The validation reader had disabled normal
  native schema feedback. No stop reason was retained for that failure; output exhaustion is
  not established. Detailed partial audit:replay178b-audit.json.
- decision178-model-replay-20260912T164759Z on29d0647b: completed A/B/C contract replay below.
  Native structured feedback is enabled with a three-step graph bound; this successful replay
  needed one provider call per decision and one for Judge. Outcome telemetry excludes private
  reasoning; output token totals include provider reasoning.

| Check | Result | Evidence |
| --- | --- | --- |
| A: small structured synthesis | Two valid first-call decisions, both ECL2 with two compared IDs | decision-1/2.json;3,168/3,498public chars |
| B: runtime nonidentity hydration | PASS:canonical286 -> design414; conditional ambiguity retained | nonidentity-mapping.json; actual approved mapping |
| C: independent Judge contract | Typed ready-to-ask/DISCOURAGED critique completed; scientific review below is NOT PASS | judge.json; one provider call |
| D: restart after dossier | PASS: native checkpoint reuses the same durable dossier, no repeated research | checks178f.log and checks179b.log; native restart test |

Working projection29,183characters versus original dossier78,376. Each synthesis call received
10,034provider input tokens. Calls used11,325/3,848output tokens and138.71/43.33seconds. Judge used
15,646input/3,862output tokens and48.25seconds. Recommendation varied SUPPORTED/DISCOURAGED on
the same evidence, so this is contract stability, not scientific reproducibility or a model-policy
comparison. No product model default is inferred from this debugging configuration.

## Independent scientific audit of the old evidence

The old177 handoff has insufficient forbidden-effect research and unaccepted faulty opinions.
The new small output does not cure those facts. Both synthesis and Judge still adopted parts
of the fallible notes:canonical192 is D in the runtime mapping, not an unresolved cysteine;
scan-derived candidates include TM segments and are not all intracellular loops; kernel
candidate names do not establish a GPCRdb-endorsed winner. The original conjunction-heavy
literature query and failed full-text access did not adequately investigate adverse-effect
counterevidence. Judge corrected the stale Gate1 note but overlooked other issues and accepted
that search as sufficient. Its ready-to-ask verdict is therefore not scientific acceptance.
The validation reader never registered a proposal/Judge/Gate or rewrote an accepted snapshot.

Next: fresh GPCR research with current decision-sufficiency/query policy, small isolated decision,
runtime hydration and the actual independent Judge/Gate path. Apply the unchanged hard oracle
and independent source-content review. Ordinary failure remains diagnose/patch/test/retry.
Only after Case2 scientific PASS revalidate Cases1/3/4/5, run latest full regression, finish parity
and protected-kernel audit, freeze Phase2 and stop for human review. No Phase3 work.

## Targeted verification

checks178f:47PASS; checks178g:2PASS; checks179a:9PASS; checks179b:17PASS. These overlap and must
not be summed as unique coverage. Latest Ruff and mypy23 pass. Coverage includes runtime facts,
forbidden model fields, nonidentity mapping, candidate comparison, source/contradiction retention,
native restart and shared Site/Judge/Binder steering.385protected files and the Golden oracle
were unchanged at the engineering checkpoint; protected verification is repeated before freeze.
