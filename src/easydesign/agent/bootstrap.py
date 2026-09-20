"""Goal-first interpretation before the existing Stage 01 target source is materialized.

This module resolves only the bounded database-search input needed by the existing
Target preparation implementation.  It does not select identity or structure authority;
those remain native Stage 01 decisions and Gate 1.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .contracts import AgentBoundaryError, ShortText, StrictDTO
from .models import ModelConfig
from .phase34_model import structured_opinion


class GoalTargetIntent(StrictDTO):
    target_label: str = Field(min_length=1, max_length=80)
    uniprot_query: str = Field(
        min_length=1,
        max_length=160,
        description=(
            "A compact target name, gene symbol or official alias suitable for the existing "
            "bounded UniProt search. Do not include organism syntax or database filters."
        ),
    )
    organism: str = Field(min_length=1, max_length=100)
    taxon_id: int = Field(ge=1)
    interpretation: ShortText
    limitations: list[ShortText] = Field(min_length=1, max_length=4)


async def resolve_goal_target(
    *,
    store: Any,
    thread: str,
    goal: str,
    model: Any,
    config: ModelConfig,
) -> GoalTargetIntent:
    """Resolve a replayable search intent without creating scientific authority."""

    previous = [
        event["payload"]
        for event in store.events(thread)
        if event["kind"] == "goal-target-intent"
    ]
    if previous:
        return GoalTargetIntent.model_validate(previous[-1]["intent"])
    execution = store.begin_execution(thread, goal)
    intent = await structured_opinion(
        bridge=type("GoalBootstrapBridge", (), {"store": store, "thread": thread})(),
        model=model,
        config=config,
        execution_id=execution["execution_id"],
        role="target",
        schema=GoalTargetIntent,
        packet={
            "user_goal": goal,
            "scope": "Resolve only a UniProt search query and organism/taxon input.",
            "authority": (
                "This interpretation is a discovery input, not target identity, structure "
                "selection, or scientific approval. Native Stage 01 must verify all sources."
            ),
        },
        prompt=(
            "Extract the biological target and organism needed to start EasyDesign's existing "
            "review-gated Target Intelligence. Return a conservative database-search intent. "
            "Preserve ambiguity in limitations. Never claim that identity is resolved and never "
            "choose a PDB structure. If the organism is implicit, use the strongest conventional "
            "biomedical interpretation and explicitly state that assumption in limitations."
        ),
        resume_across_executions=True,
    )
    if not intent.uniprot_query.strip():
        raise AgentBoundaryError("Goal did not resolve to a bounded UniProt search input")
    store.event(
        thread,
        "goal-target-intent",
        {
            "intent": intent.model_dump(mode="json"),
            "authority": "discovery-input-only",
            "execution_id": execution["execution_id"],
        },
    )
    return intent
