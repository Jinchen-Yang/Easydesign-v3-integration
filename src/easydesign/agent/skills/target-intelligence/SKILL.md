---
name: target-intelligence
description: Prepare and assess a bound local PDB/mmCIF target using existing scientific tools.
---

Read the runtime-injected TargetTask. It contains the researcher's actual goal.
Call prepare_target once. Use get_job_status to attach and observe, then read_target_evidence.
Only stop-after-target, review-gated local structures are supported. Do not fetch remote identities,
predict structures, invent residue mappings, select a chain silently, or enter site/binder design.
If the old worker is still active after bounded observation, report its job ID and stop observing.

A pending chain-selection gate is a real scientific question. There is no successful bundle yet:
compare the frozen source, chain inventory and eligible options. Keep the user's preferred chain
separate from confirmed biological identity. Do not claim that the first or largest chain is correct.
Single-chain inputs may finish directly; do not invent an approval gate.

Return TargetAssessment JSON with observed_facts, unresolved_identity, selectable_options,
evidence_refs, limitations and recommended_action. Cite the exact refs from read_target_evidence.
Never return raw PDB/mmCIF coordinates, full sequences, logs, or invented scientific artifacts.

Required limitations: canonical biological identity is unconfirmed; reference completeness is unknown;
chain choice does not establish species, isoform or native construct. Structural quality and successful
preparation are not affinity or function evidence. Errors, awaiting approval, and success are distinct.
