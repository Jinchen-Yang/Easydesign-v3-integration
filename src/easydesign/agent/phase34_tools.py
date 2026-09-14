"""Runtime-only downstream actions through the existing interrupt/response ledger."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from .contracts import AgentBoundaryError, EmptyArguments, Identifier, StrictDTO

NAMES = {"advance_downstream", "observe_downstream", "request_downstream_decision"}


class PresentDownstreamCard(StrictDTO):
    card_id: Identifier


def downstream_tools(bridge: Any) -> list[Any]:
    from langchain_core.tools import StructuredTool
    from langgraph.types import interrupt

    async def advance() -> str:
        return cast(str, bridge.store.offload(bridge.thread, await bridge.advance()))

    async def observe() -> str:
        result = bridge.get_job_status()
        for _ in range(20):
            if result.get("status") not in {"queued", "running"}:
                break
            await asyncio.sleep(0.5)
            result = bridge.get_job_status()
        return cast(str, bridge.store.offload(bridge.thread, result))

    async def present(card_id: str) -> str:
        saved_response = bridge.store.response(bridge.thread, card_id)
        action = bridge.next_downstream_action()
        if saved_response is None and (
            action is None
            or action.tool != "request_downstream_decision"
            or action.arguments != {"card_id": card_id}
        ):
            raise AgentBoundaryError("Requested card is outside current downstream authority")
        card = (
            bridge.store.card(bridge.thread, card_id)
            if saved_response is not None
            else (
                bridge.frozen_pilot_card()
                if action.stage == "pilot-plan-review"
                else bridge.downstream_card()
            )
        )
        if card is None or card.card_id != card_id:
            raise AgentBoundaryError("Current downstream review has changed")
        # Cards retain their original owner thread. A new conversational thread can
        # inspect it, but must not silently transfer an outstanding human approval.
        bridge.store.card(bridge.thread, card_id)
        response = interrupt(card.model_dump(mode="json"))
        intent = bridge.store.response(bridge.thread, card_id)
        if (
            not isinstance(response, dict)
            or set(response) != {"card_id", "decision"}
            or (
                intent is None
                or response["card_id"] != card_id
                or response["decision"] != intent["response"]
            )
        ):
            raise AgentBoundaryError("Resume differs from persisted Scientist steering")
        return cast(str, bridge.store.offload(bridge.thread, bridge.apply_decision(card)))

    return [
        StructuredTool.from_function(
            name=name, coroutine=fn, args_schema=schema, description=description
        )
        for name, fn, schema, description in (
            (
                "advance_downstream",
                advance,
                EmptyArguments,
                "Execute the next exact runtime-authorized downstream step.",
            ),
            (
                "observe_downstream",
                observe,
                EmptyArguments,
                "Observe the current downstream worker without starting work.",
            ),
            (
                "request_downstream_decision",
                present,
                PresentDownstreamCard,
                "Present the exact current Gate 3 Pilot plan or Gate "
                "4/5 card for Scientist steering.",
            ),
        )
    ]
