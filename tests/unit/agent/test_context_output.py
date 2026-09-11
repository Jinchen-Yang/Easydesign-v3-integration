import json
from typing import Any

import pytest

from easydesign.agent.contracts import AgentBoundaryError
from easydesign.agent.harness import fingerprint, skill_root
from tests.agent_support import scripted_config


def test_large_summary_offloads_without_structure_copy(bridge: Any) -> None:
    value = {"limitations": ["x" * 9000], "evidence_refs": ["existing/target.json#sha256=abc"]}
    output = bridge.store.offload(bridge.thread, value)
    assert len(output.encode()) < 8192
    ref = json.loads(output)["ref"]
    path = bridge.store.root / "agent-work" / bridge.thread / ref[1:]
    assert json.loads(path.read_text()) == value
    with pytest.raises(AgentBoundaryError, match="large"):
        bridge.store.offload(bridge.thread, {"data": "x" * 260000})


def test_config_and_budget_survive_reopen(bridge: Any) -> None:
    from easydesign.agent.session_store import SessionStore

    bridge.store.thread(bridge.thread, fingerprint(scripted_config()), "Prepare chain A")
    execution = bridge.store.begin_execution(bridge.thread, "Prepare chain A")
    bridge.store.reserve_model_call(bridge.thread, "target", 1, execution["execution_id"])
    second = SessionStore(bridge.project)
    try:
        assert second.thread(bridge.thread, fingerprint(scripted_config())) == "Prepare chain A"
        with pytest.raises(AgentBoundaryError, match="budget"):
            second.reserve_model_call(bridge.thread, "judge", 1, execution["execution_id"])
        next_execution = second.begin_execution(bridge.thread, "Explain the remaining limits")
        second.reserve_model_call(bridge.thread, "judge", 1, next_execution["execution_id"])
        assert [
            e["payload"]["lifetime_call"]
            for e in second.events(bridge.thread)
            if e["kind"] == "model-call"
        ] == [1, 2]
        with pytest.raises(AgentBoundaryError, match="Incompatible"):
            second.thread(bridge.thread, "changed-model")
    finally:
        second.close()
    assert (skill_root() / "target-intelligence/SKILL.md").is_file()
    assert (skill_root() / "evidence-judge/SKILL.md").is_file()


def test_reasoning_view_preserves_evidence_and_user_turns_without_mutating_checkpoint() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from easydesign.agent.evidence_output import reasoning_working_view

    user = HumanMessage(content="Find a falsifiable binding hypothesis; no approval.")
    assistant = AIMessage(
        content=[
            {
                "type": "thinking",
                "thinking": "private deliberation " * 1000,
                "signature": "original-signed-block",
            }
        ],
        tool_calls=[
            {
                "id": "read-1",
                "name": "retrieve_evidence",
                "args": {"need": "KNOWN_EPITOPE", "question": "scoped source"},
                "type": "tool_call",
            }
        ],
    )
    evidence = {
        "passage": "Exact source quote with counterevidence.",
        "source_id": "test-source",
        "mapping": [{"label": 9, "canonical": None, "status": "ambiguous"}],
        "limitations": ["unknown efficacy", "state mismatch"],
        "full_result": "/result-aabb.json",
    }
    result = ToolMessage(
        name="retrieve_evidence", tool_call_id="read-1", content=json.dumps(evidence)
    )
    second_user = HumanMessage(content="Retain the state mismatch.")
    messages = [user, assistant, result, second_user]
    original = [m.model_dump() for m in messages]
    view = reasoning_working_view(messages)
    assert [m.model_dump() for m in messages] == original
    assert view[0] is user and view[-1] is second_user
    assert "private deliberation" not in str(view) and "original-signed-block" not in str(view)
    record = json.loads(view[1].content)["runtime_history"]
    assert record[0]["requested_tools"] == assistant.tool_calls
    assert record[1]["content"] == evidence
    assert record[1]["status"] == "success"
    assert len(str(view)) < len(str(messages)) / 4
    assert reasoning_working_view([user, assistant]) == [user, assistant]
    assert reasoning_working_view([user, result]) == [user, result]


def test_repeated_field_indexes_fit_without_archiving_science_and_are_reconstructable() -> None:
    from copy import deepcopy

    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from easydesign.agent.evidence_output import fit_site_working_view, reasoning_working_view
    from easydesign.agent.session_store import compact

    fields = ["verified_source_field_" + str(i) for i in range(20)]
    messages: list[Any] = [HumanMessage(content="Preserve contradictory findings.")]
    for i in range(12):
        messages += [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": str(i), "name": "read_evidence_result", "args": {"path": ["state"]}}
                ],
            ),
            ToolMessage(
                name="read_evidence_result",
                tool_call_id=str(i),
                content=compact(
                    {
                        "full_result": "/result-aabb.json",
                        "stored_fields": fields,
                        "counterevidence": [str(i)],
                        "value": {"occupancy": None},
                    }
                ),
            ),
        ]
    original = [m.model_dump() for m in messages]
    view = reasoning_working_view(messages)
    payload = json.loads(view[1].content)
    restored = deepcopy(payload)
    indexes = {}
    originals = {
        m.tool_call_id: json.loads(m.content) for m in messages if isinstance(m, ToolMessage)
    }
    for record in restored["runtime_history"]:
        if record["kind"] != "tool-result":
            continue
        content = record["content"]
        if "stored_fields_from_tool_call" in content:
            content["stored_fields"] = indexes[content.pop("stored_fields_from_tool_call")]
        indexes[record["tool_call_id"]] = content["stored_fields"]
        assert content == originals[record["tool_call_id"]]
    assert [m.model_dump() for m in messages] == original
    compact_chars = sum(len(str(m.content)) for m in view)
    expanded_chars = len(messages[0].content) + len(compact(restored))
    assert expanded_chars - compact_chars > 4000
    system_chars = 60000 - (compact_chars + expanded_chars) // 2
    fitted, archived = fit_site_working_view(
        messages, reasoning=True, system_chars=system_chars, max_chars=60000, suffix=[]
    )
    assert not archived and system_chars + sum(len(str(m.content)) for m in fitted) < 60000
    # A later user turn starts an independent record with its own complete field index.
    following = reasoning_working_view(
        [*messages, HumanMessage(content="New scope"), *messages[1:3]]
    )
    assert (
        json.loads(following[-1].content)["runtime_history"][1]["content"]["stored_fields"]
        == fields
    )


@pytest.mark.parametrize("reasoning", [False, True])
def test_site_context_fit_retains_newest_answer_evaluation_and_originals(reasoning: bool) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from easydesign.agent.evidence_output import fit_site_working_view

    user = HumanMessage(content="Trusted original goal " + "g" * 35000)
    messages = [user]
    for i in range(6):
        name = "evaluate_candidate_site" if i == 2 else "retrieve_evidence"
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"id": str(i), "name": name, "args": {"question": str(i)}}],
                ),
                ToolMessage(
                    name=name,
                    tool_call_id=str(i),
                    content=json.dumps(
                        {
                            "full_result": f"/result-{i + 10:x}.json",
                            "stored_fields": ["matches", "limitations", "target_binding"],
                            "path": ["matches"],
                            "source_id": f"synthetic-{i}",
                            "passage": "e" * 4800,
                            "limitations": ["uncertain", "counterevidence retained"],
                            "mapping": {"canonical": None, "status": "ambiguous"},
                        }
                    ),
                ),
            ]
        )
    original = [m.model_dump() for m in messages]
    suffix = [HumanMessage(content="Runtime phase notice; no scientific approval.")]
    fitted, archived = fit_site_working_view(
        messages, reasoning=reasoning, system_chars=5000, max_chars=60000, suffix=suffix
    )
    assert archived and 5000 + sum(len(str(m.content)) for m in fitted) < 60000
    assert [m.model_dump() for m in messages] == original
    assert fitted[0] is user and fitted[-1] is suffix[0]
    assert not ({a["ref"] for a in archived} & {"/result-c.json", "/result-f.json"})
    if reasoning:
        records = json.loads(fitted[1].content)["runtime_history"]
        results = {r["tool_call_id"]: r["content"] for r in records if r["kind"] == "tool-result"}
    else:
        results = {
            m.tool_call_id: json.loads(m.content) for m in fitted if isinstance(m, ToolMessage)
        }
    for call_id in ["2", "5"]:
        original_tool = next(
            m for m in messages if isinstance(m, ToolMessage) and m.tool_call_id == call_id
        )
        assert results[call_id] == json.loads(original_tool.content)
    for a in archived:
        assert any(v.get("archived_result") == a["ref"] and v["partial"] for v in results.values())
        archived_view = next(v for v in results.values() if v.get("archived_result") == a["ref"])
        assert archived_view["stored_fields"] == ["matches", "limitations", "target_binding"]
        assert archived_view["previous_scope"] == {"path": ["matches"]}
    small = [HumanMessage(content="Small goal")]
    same, archive = fit_site_working_view(
        small, reasoning=reasoning, system_chars=100, max_chars=60000, suffix=[]
    )
    assert same == small and not archive
    # A large immutable human/base context remains oversized for the caller's hard guard.
    huge = [HumanMessage(content="h" * 61000)]
    large, archive = fit_site_working_view(
        huge, reasoning=reasoning, system_chars=100, max_chars=60000, suffix=[]
    )
    assert large == huge and not archive


@pytest.mark.parametrize("reasoning", [False, True])
@pytest.mark.parametrize("newest_reference", [False, True])
def test_optional_skill_pages_fit_without_hiding_current_answer_or_main_instructions(
    reasoning: bool, newest_reference: bool
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from easydesign.agent.evidence_output import fit_site_working_view

    messages: list[Any] = [HumanMessage(content="Original research goal " + "g" * 3000)]

    def exchange(name: str, args: dict[str, Any], content: str) -> None:
        call_id = str(len(messages))
        messages.extend(
            [
                AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": args}]),
                ToolMessage(name=name, tool_call_id=call_id, content=content),
            ]
        )

    for path, chars in [
        ("/skills/site-mechanism/SKILL.md", 9000),
        ("/skills/site-mechanism/references/research.md", 5500),
        ("/skills/site-mechanism/references/membrane.md", 1500),
        ("/skills/site-mechanism/references/shielding.md", 1200),
        ("/inputs/references/research.md", 600),
    ]:
        exchange("read_file", {"file_path": path, "limit": 120}, path + "x" * chars)
    exchange(
        "analyze_receptor_context",
        {},
        json.dumps(
            {
                "full_result": "/result-abcd.json",
                "candidate_overview": "c" * 25000,
                "mapping_status": "ambiguous",
                "glycan_occupancy": None,
            }
        ),
    )
    if newest_reference:
        exchange(
            "read_file",
            {
                "file_path": "/skills/site-mechanism/references/research.md",
                "offset": 0,
                "limit": 120,
            },
            "Freshly requested exact reference " + "r" * 900,
        )
    else:
        exchange("compare_reference_identity", {}, '{"mapping_status":"ambiguous"}')
    originals = [m.model_dump() for m in messages]
    suffix = [HumanMessage(content="No approval; unresolved evidence stays unresolved.")]
    fitted, archived = fit_site_working_view(
        messages,
        reasoning=reasoning,
        system_chars=17000,
        max_chars=60000,
        suffix=suffix,
    )
    assert archived and 17000 + sum(len(str(m.content)) for m in fitted) < 60000
    assert [m.model_dump() for m in messages] == originals
    assert fitted[0] is messages[0] and fitted[-1] is suffix[0]
    if reasoning:
        records = json.loads(fitted[1].content)["runtime_history"]
        results = {r["tool_call_id"]: r["content"] for r in records if r["kind"] == "tool-result"}
    else:
        results = {m.tool_call_id: m.content for m in fitted if isinstance(m, ToolMessage)}
    protected = [messages[2], messages[10], messages[12], messages[-1]]
    for message in protected:
        content = message.content
        if reasoning:
            try:
                content = json.loads(content)
            except ValueError:
                pass
        assert results[message.tool_call_id] == content
    assert all(a["tool"] == "read_file" for a in archived)
    for a in archived:
        assert a["ref"] in {
            "/skills/site-mechanism/references/research.md",
            "/skills/site-mechanism/references/membrane.md",
            "/skills/site-mechanism/references/shielding.md",
        }
    text = str([m.content for m in fitted])
    assert "instructions_remain_applicable" in text
    assert "archived_skill_reference" in text
