# Research memory: oversized completed tool batches

The frozen `b9f34494` GPCR attempt stopped during Research, before Site synthesis or
Site Judge. The unchanged hard guard rejected a 109,677-character request after a
framework summary. This is a failed exam, not Phase 2 acceptance.

The saved checkpoint explains the overrun: the framework's safe cutoff moved backward
to preserve the last complete tool transaction. That retained 77,715 characters,
including 53,370 characters of assistant reasoning/content, despite a 3,750-token
retention target. The retained batch alone counted approximately 24,425 tokens.
Summarizing earlier messages therefore did not create enough room for the next request.

The narrow correction retains the native DeepAgents summary, history offload, shared
call accounting and checkpoint event. When the native cutoff leaves one oversized tool
batch whose calls have all returned exactly once, that entire batch joins the summary.
It is never split into orphan calls/results. An incomplete/duplicate/orphan transaction
or a new user message does not qualify for this additional cutoff adjustment.

The summary input reuses the existing completed-tool transcript projection. It preserves
public assistant text, tool arguments, results and source limitations without replaying
private reasoning as evidence. The native offload and original checkpoint still retain
the original messages. This also prevents a long signed-thinking block from crowding all
source context out of the framework's bounded summary input and yielding a placeholder.

Original signed messages and exact source/tool artifacts remain available. The summary
is fallible working memory; it does not become a scientific fact, a Site proposal or an
approval. The final evidence dossier continues to hydrate independently from verified
artifacts. The model, reasoning level, output limit, 64-call budget, 100k hard guard,
scientific kernel and Golden acceptance standard are unchanged.

Validation separates the saved-checkpoint compaction replay from a new frozen fresh
exam. Regression covers the actual oversized-batch shape, source/counterevidence history
retention, incomplete transaction protection, shared call accounting and restart. A
successful summary or continued model call alone is not scientific acceptance.

The subsequent `e2c0e39` fresh exam exposed a separate integration defect: the new
subclass inherited its own class name, while DeepAgents substitutes middleware by
name. The default and custom summary layers both remained active and applied the
same persisted cutoff twice. Fresh tool results disappeared from model requests;
the provider eventually rejected an orphan tool result. This attempt also failed;
its original evidence and frozen source remain preserved.

The subclass now preserves the framework's `SummarizationMiddleware` name so that
exactly one summary layer owns the checkpoint event. An assembled DeepAgents graph
regression exercises an oversized complete batch, a new tool call after summary,
and checkpoint continuation with the same source result still visible. Direct
summary tests alone did not cover this factory substitution boundary.
