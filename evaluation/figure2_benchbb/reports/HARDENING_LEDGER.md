# BenchBB experimental-agent hardening ledger

This ledger records development failures found while using the seven BenchBB targets as an
engineering hardening set. These runs are not formal Figure 2 effectiveness observations. A case
counts as repaired only after the original failure is preserved, a target-independent regression
passes, and a new fresh run from the frozen raw target input succeeds. Resuming the failed thread
may diagnose recovery but cannot prove the repair.

## BB-HARDEN-001 — a review assigned E2 was treated as a fatal Site boundary failure

- Case: PD-L1 / deposited input `4Z18`; direct interface reference `4ZQK`.
- Development run: `formal-pdl1-easydesign-r1-20260920`, subsequently marked non-formal and
  excluded from benchmark estimates.
- Boundary: bounded Site Research finalization before a Gate 2 proposal was persisted.
- Before: Runtime had already acquired a focused `4ZQK` coordinate-contact passage with
  `primary_eligible=true`. The handoff also cited a retrieved Perspective/Review passage with
  `primary_eligible=false` but assigned it `strength=E2`. `EvidenceResearch.validate_questions`
  correctly rejected the promotion, but raised an undifferentiated fatal `AgentBoundaryError`.
  Replaying the unfinished checkpoint reproduced the failure instead of allowing the handoff to be
  corrected. The saved trace also contains schema-only handoff corrections; these shared the same
  two correction slots and could leave no capacity for the later source-role error.
- Cause: source eligibility was already a Runtime fact, but the compact finalization packet exposed
  only `primary_eligible` and did not publish an explicit allowed-strength ceiling. A known
  source-role mismatch used the fatal authority exception instead of the typed scientific
  correction path, and syntax versus source-role corrections shared one budget.
- Repair:
  - each focused evidence card now publishes Runtime-derived `allowed_strengths`;
  - `E1/E2` remain restricted to `primary_eligible=true` passages;
  - a model cannot promote a review, discovery source or other ineligible passage;
  - `EvidenceRoleMismatch` returns the invalid card, its submitted strength and currently available
    primary-eligible focused passage IDs;
  - Site Research receives one separately named, durable evidence-role correction after the normal
    two shape/schema corrections;
  - the correction resubmits only `SiteResearchHandoff`; it does not repeat research, silently
    rewrite the opinion, replace a source or approve a Site.
- Security boundary retained: foreign card IDs, source tampering, identity drift and invented
  passages remain fatal. A repair cannot raise a source above its Runtime-owned ceiling.
- Regression:
  - a retrieved review plus a direct primary passage reproduces the saved PD-L1 role conflict;
  - the diagnostic names both the invalid review and eligible direct passage;
  - finalization succeeds after two pre-existing shape repairs and one evidence-role repair;
  - direct and review cards expose `E1-E4` versus `E3-E4` ceilings respectively.
- Validation: 92 focused Evidence/Site/finalization tests pass; Ruff passes; mypy passes for all
  changed source modules. A fresh PD-L1 run is required before this entry is closed.
- Disposition: implementation validated locally; fresh-run validation pending.
