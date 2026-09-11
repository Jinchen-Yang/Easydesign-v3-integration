import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import Field

from easydesign.agent.cli import run_session
from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.phase2_tools import PHASE2_ALLOWED, phase2_tools
from easydesign.agent.session_store import SessionStore
from easydesign.agent.site_contracts import ScientificTask
from tests.agent_support import ScriptedModel, scripted_config
from tests.unit.agent.test_site_runtime import site_intent


class SiteModel(ScriptedModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        outputs = {"target": "TargetInterpretation", "site": "SiteIntent", "judge": "JudgeVerdict"}
        expected = PHASE2_ALLOWED[self.role] | (
            {outputs[self.role]} if self.role in outputs else set()
        )
        assert {t.name for t in tools} == expected
        return self

    def answer(self, messages: Any) -> AIMessage:
        calls = {c["id"]: c for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
        results = [
            (calls.get(m.tool_call_id, {}), m) for m in messages if isinstance(m, ToolMessage)
        ]
        for _, message in results:
            assert message.status != "error", message.content
        named = [(c.get("name"), c, m) for c, m in results]
        if self.role in {"site", "judge"}:
            human = next(m for m in messages if isinstance(m, HumanMessage))
            task = ScientificTask.model_validate_json(human.text)
            if not results:
                self.tasks.append(task.model_dump())
                skill = "site-mechanism" if self.role == "site" else "evidence-judge"
                return self.call("read_file", file_path=f"/skills/{skill}/SKILL.md")
            if self.role == "site":
                labels = [4, 5, 6] if task.current_revision_instruction else [1, 2, 3]
                if not any(n == "read_site_evidence" for n, _, _ in named):
                    return self.call("read_site_evidence")
                if not any(n == "evaluate_candidate_site" for n, _, _ in named):
                    return self.call("evaluate_candidate_site", label_seq_ids=labels)
                return self.call("SiteIntent", **site_intent(labels).model_dump(mode="json"))
            if not any(n == "read_scientific_evidence" for n, _, _ in named):
                return self.call("read_scientific_evidence")
            return self.call(
                "JudgeVerdict",
                verdict="ready-to-ask",
                reasons=["The mapped structural hypothesis is reviewable."],
                limitations=["Function and binding remain experimentally untested."],
            )
        if self.role == "target":
            return super().answer(messages)
        if not results:
            return self.call("read_scientific_state")
        decisions = [
            json.loads(m.content) for n, _, m in named if n == "request_scientific_decision"
        ]
        if decisions and decisions[-1]["status"] in {"hotspot-approved", "proposal-rejected"}:
            return AIMessage(content="The current scientific decision has been handled.")
        iterations = 1 + sum(d["status"] == "revision-requested" for d in decisions)
        site_results = [
            m for n, c, m in named if n == "task" and c["args"]["subagent_type"] == "site-mechanism"
        ]
        judges = [
            m for n, c, m in named if n == "task" and c["args"]["subagent_type"] == "evidence-judge"
        ]
        if len(site_results) < iterations:
            return self.call(
                "task",
                subagent_type="site-mechanism",
                description=(
                    "Assess the best mapped site for the original goal and current trusted "
                    "revision."
                ),
            )
        if len(judges) < iterations:
            return self.call(
                "task",
                subagent_type="evidence-judge",
                description="Challenge the current Site proposal and its limitations.",
            )
        result = json.loads(judges[-1].content)
        return self.call(
            "request_scientific_decision", assessment_id=result["assessment_id"], option_id="site"
        )


@pytest.mark.asyncio
async def test_site_revision_restart_preserves_target_and_goal(site_bridge: Any) -> None:
    bridge = site_bridge
    models = {r: SiteModel(role=r) for r in PHASE2_ALLOWED}
    goal = (
        "Choose an exposed site for exploratory VHH engagement; no functional "
        "validation is claimed."
    )
    target_before = bridge.target_state()["binding"]
    first = await run_session(bridge, scripted_config(), models, goal)
    assert first["status"] == "awaiting-human-approval"
    assert first["card"]["gate_type"] == "site-hotspot"
    reopened = SessionStore(bridge.project)
    try:
        resumed = Phase2Bridge(bridge.project, bridge.thread, reopened)
        revised = await run_session(
            resumed,
            scripted_config(),
            models,
            goal,
            decision="revise",
            card_id=first["card"]["card_id"],
            user="synthetic-scientist",
            human_instruction=(
                "Keep the target, reassess mapped residues 4–6 and explain the new choice."
            ),
        )
        assert revised["status"] == "awaiting-human-approval"
        assert revised["card"]["parent_card_id"] == first["card"]["card_id"]
        assert resumed.target_state()["binding"] == target_before
        assert resumed.approved_site() is None
        tasks = models["site"].tasks
        assert len(tasks) == 2
        assert all(t["user_goal"] == goal and t["current_user_message"] == goal for t in tasks)
        assert tasks[0]["current_revision_instruction"] is None
        assert "4–6" in tasks[1]["current_revision_instruction"]
        assert tasks[1]["evidence_refs"] == tasks[0]["evidence_refs"]
        done = await run_session(
            resumed,
            scripted_config(),
            models,
            goal,
            decision="approve",
            card_id=revised["card"]["card_id"],
            user="synthetic-scientist",
        )
        assert done["status"] == "finished" and done["scientific_state"] == "hotspot-approved"
        assert resumed.approved_site()["hotspots"]["hotspot_sets"][0]["label_seq_ids"] == [4, 5, 6]
        assert len(resumed._jobs()) == 1
        assert (
            len([j for j in resumed.controller.list(project_id=resumed.project_id) if j.step == 2])
            == 2
        )
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_judge_cannot_read_undelegated_snapshot(site_bridge: Any) -> None:
    tool = phase2_tools(site_bridge, "judge")[0]
    with pytest.raises(AgentBoundaryError):
        await tool.ainvoke({})
    assert all(
        "decision" not in t.name and "prepare" not in t.name
        for t in phase2_tools(site_bridge, "site")
    )


@pytest.mark.asyncio
async def test_site_reject_preserves_the_scientific_project(site_bridge: Any) -> None:
    bridge = site_bridge
    models = {r: SiteModel(role=r) for r in PHASE2_ALLOWED}
    goal = "Review a mapped site without generating candidates."
    pending = await run_session(bridge, scripted_config(), models, goal)
    result = await run_session(
        bridge,
        scripted_config(),
        models,
        goal,
        decision="reject",
        card_id=pending["card"]["card_id"],
        user="synthetic-scientist",
        optional_reason="Need a different scientific approach",
    )
    assert result["status"] == "proposal-rejected"
    assert result["scientific_state"] == "awaiting-human-approval"
    assert bridge.read_evidence()["status"] == "succeeded"
    assert bridge.approved_site() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "point", ["after_response_intent", "after_steering_delivery", "after_site_approval"]
)
async def test_gate2_restart_does_not_duplicate_approval_or_target(
    site_bridge: Any, point: str
) -> None:
    from tests.unit.agent.test_command_recovery import Crash, crash_at

    bridge = site_bridge
    models = {r: SiteModel(role=r) for r in PHASE2_ALLOWED}
    goal = "Review a mapped exploratory site."
    first = await run_session(bridge, scripted_config(), models, goal)
    action = "revise" if point == "after_steering_delivery" else "approve"
    crash_at(bridge, point)
    with pytest.raises(Crash):
        await run_session(
            bridge,
            scripted_config(),
            models,
            goal,
            decision=action,
            card_id=first["card"]["card_id"],
            user="synthetic-scientist",
            human_instruction="Reassess residues 4–6" if action == "revise" else None,
        )
    reopened = SessionStore(bridge.project)
    try:
        resumed = Phase2Bridge(bridge.project, bridge.thread, reopened)
        result = await run_session(resumed, scripted_config(), models, goal)
        if action == "revise":
            assert result["status"] == "awaiting-human-approval"
            assert result["card"]["parent_card_id"] == first["card"]["card_id"]
        else:
            assert result["status"] == "finished"
            assert resumed.approved_site()["outcome"]["human_actor"] == "synthetic-scientist"
        assert len(resumed._jobs()) == 1
        assert len([e for e in reopened.events(bridge.thread) if e["kind"] == "site-approved"]) == (
            0 if action == "revise" else 1
        )
    finally:
        reopened.close()


class CorrectableSiteModel(SiteModel):
    malformed_once: bool = False

    def answer(self, messages: Any) -> AIMessage:
        result = super().answer(messages)
        if (
            self.role == "site"
            and not self.malformed_once
            and result.tool_calls
            and result.tool_calls[0]["name"] == "SiteIntent"
        ):
            self.malformed_once = True
            result.tool_calls[0]["args"]["binder_approach"] = {"rationale": "wrong field type"}
        return result


@pytest.mark.asyncio
async def test_site_structured_output_retries_before_any_scientific_submission(
    site_bridge: Any,
) -> None:
    models = {r: CorrectableSiteModel(role=r) for r in PHASE2_ALLOWED}
    result = await run_session(
        site_bridge, scripted_config(), models, "Assess an exploratory site."
    )
    assert result["status"] == "awaiting-human-approval"
    assert models["site"].malformed_once
    assert (
        len(
            [
                j
                for j in site_bridge.controller.list(project_id=site_bridge.project_id)
                if j.step == 2
            ]
        )
        == 1
    )
    assert (
        len(
            [
                e
                for e in site_bridge.store.events(site_bridge.thread)
                if e["kind"] == "site-proposal"
            ]
        )
        == 1
    )


class InvalidJsonSiteModel(SiteModel):
    malformed_once: bool = False

    def answer(self, messages: Any) -> AIMessage:
        result = super().answer(messages)
        if (
            self.role == "site"
            and not self.malformed_once
            and result.tool_calls
            and result.tool_calls[0]["name"] == "SiteIntent"
        ):
            self.malformed_once = True
            return AIMessage(
                content="",
                invalid_tool_calls=[
                    {
                        "name": "SiteIntent",
                        "args": '{"binder_approach": unquoted}',
                        "id": "bad-site-json",
                        "error": "Invalid JSON",
                    }
                ],
            )
        return result


@pytest.mark.asyncio
async def test_invalid_provider_json_repair_is_budgeted_and_has_no_duplicate_job(
    site_bridge: Any,
) -> None:
    models = {r: InvalidJsonSiteModel(role=r) for r in PHASE2_ALLOWED}
    result = await run_session(
        site_bridge, scripted_config(), models, "Assess an exploratory site."
    )
    assert result["status"] == "awaiting-human-approval"
    assert models["site"].malformed_once
    events = site_bridge.store.events(site_bridge.thread)
    contexts = [e["payload"] for e in events if e["kind"] == "model-context"]
    calls = [e for e in events if e["kind"] == "model-call"]
    assert len(contexts) == len(calls)
    assert any(c["repair_attempt"] == 1 for c in contexts)
    assert all(c["context_chars"] <= c["limit"] for c in contexts)
    assert (
        len([e for e in events if e["kind"] == "model-call" and e["payload"]["role"] == "site"])
        == 5
    )
    assert (
        len(
            [
                j
                for j in site_bridge.controller.list(project_id=site_bridge.project_id)
                if j.step == 2
            ]
        )
        == 1
    )


class ProseJudge(SiteModel):
    sent_prose: bool = False

    def answer(self, messages: Any) -> AIMessage:
        result = super().answer(messages)
        if (
            self.role == "judge"
            and result.tool_calls
            and result.tool_calls[0]["name"] == "JudgeVerdict"
            and not self.sent_prose
        ):
            self.sent_prose = True
            return AIMessage(content="The scientific proposal looks reviewable.")
        return result


@pytest.mark.asyncio
async def test_judge_prose_repaired_within_existing_budget(site_bridge: Any) -> None:
    models = {role: ProseJudge(role=role) for role in PHASE2_ALLOWED}
    result = await run_session(site_bridge, scripted_config(), models, "Review the mapped site.")
    assert result["status"] == "awaiting-human-approval"
    calls = [
        e["payload"]
        for e in site_bridge.store.events(site_bridge.thread)
        if e["kind"] == "model-call"
    ]
    assert sum(c["role"] == "judge" for c in calls) == 4
    assert site_bridge.approved_site() is None
    assert (
        len(
            [
                j
                for j in site_bridge.controller.list(project_id=site_bridge.project_id)
                if j.step == 2
            ]
        )
        == 1
    )
