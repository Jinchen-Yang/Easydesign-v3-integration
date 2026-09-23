"""Bounded Site review: small typed opinion, runtime-owned facts and failure records."""

from __future__ import annotations

from time import perf_counter
from typing import Annotated, Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, ValidationError

from .context_policy import ModelContextCapacityError, context_usage
from .contracts import (
    AgentBoundaryError,
    EvidenceBinding,
    JudgeFactClaim,
    JudgeVerdict,
    OptionRecommendation,
    SiteClaimCorrection,
    StrictDTO,
)
from .models import ModelConfig
from .session_store import compact, identity
from .site_fact_integrity import (
    fact_paths,
    fact_value,
    validate_fact_fields,
    validate_fact_references,
)
from .tools import JUDGE_EVIDENCE

Brief = Annotated[
    str,
    Field(
        min_length=1,
        max_length=300,
        description="Concise scientific interpretation, risk or uncertainty. Ordinary scientific "
        "vocabulary and numbers are allowed. Cite runtime facts in fact_refs; explicit exact "
        "factual assertions belong in fact_claims and are checked against those facts.",
    ),
]


class CompactClaimCorrection(SiteClaimCorrection):
    qualification: Brief


class SiteJudgeVerdict(StrictDTO):
    """A short early-stage review; runtime binds citations and renders hard facts."""

    verdict: Literal["ready-to-ask", "insufficient", "reject"]
    recommendation: Literal["SUPPORTED", "DISCOURAGED"] = Field(
        description="DISCOURAGED requires nonempty warnings and a non-null alternative."
    )
    reasons: list[Brief] = Field(min_length=1, max_length=2)
    uncertainties: list[Brief] = Field(min_length=1, max_length=3)
    warnings: list[Brief] = Field(default_factory=list, max_length=3)
    alternative: Brief | None = Field(
        default=None,
        description="Required when DISCOURAGED. A conditional next step or alternative, "
        "not a certified better site. "
        "Point exposure does not prove whole-binder access. Contact with a disulfide-forming "
        "cysteine is not evidence of disrupting the bond, folding or trafficking; describe "
        "it as a risk to evaluate, never as a demonstrated goal violation.",
    )
    corrections: list[CompactClaimCorrection] = Field(
        default_factory=list,
        max_length=3,
        description="Qualify material overclaims in either the selected or alternative Site. "
        "Claims of whole-binder impossibility from point burial, or direct trafficking "
        "conflict from cysteine contact alone, need qualification rather than repetition. "
        "Disulfide connectivity is not a prohibition on noncovalent antibody contact; "
        "do not endorse subtracting disulfide endpoints from a binding surface.",
    )
    fact_refs: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Optional short supplied references such as candidate:0 or source:2. "
        "Runtime supplies the evidence revision and renders the cited facts.",
    )

    fact_claims: list[JudgeFactClaim] = Field(
        default_factory=list,
        max_length=4,
        description="Optional exact assertions about supplied facts: use a short fact_ref, "
        "one direct field name and its exact JSON value. Prefer fact_refs alone "
        "for interpretation; do not duplicate the fact table.",
    )


class RecoverySiteJudgeVerdict(SiteJudgeVerdict):
    """After truncation, prioritize a minimal submission within the same repair budget."""

    reasons: list[Brief] = Field(min_length=1, max_length=1)
    uncertainties: list[Brief] = Field(min_length=1, max_length=2)
    fact_refs: list[str] = Field(default_factory=list, max_length=1)


def review_prompt(*, recovery: bool = False) -> str:
    return (
        "For a RankedSiteDecision, provide a lightweight second opinion on the supplied order. "
        "SiteDecision alone owns ranking; do not replace its order or choose a new winner. "
        "Flag a material issue that might change ranking in a short reason naming the candidate. "
        "Qualify overclaims and add risks/uncertainty. Weak evidence, low exposure, unknown "
        "whole-binder access or high scientific risk affect rank/confidence, not eligibility. "
        "Runtime alone blocks hard-invalid candidates. Scientist may select any hard-valid "
        "candidate, including B/C, even with a negative or unavailable independent review. "
        "Independently review this pending Site/Hotspot proposal for a Scientist decision. "
        "This is early selection, not proof of binder efficacy. Runtime owns identity, exact "
        "mapping, membership, source provenance and topology. Treat the supplied Site opinion "
        "as unapproved. Return only the offered structured review tool, without a preamble. "
        "Focus on whether the current hypothesis is usable, its major risk, and uncertainty. "
        "Use reject for hard contradiction; insufficient only when a meaningful current-stage "
        "decision is impossible. Unperformed docking, whole-binder access and functional assays "
        "normally remain uncertainty. Qualify material overclaims in the selected or alternative "
        "site using short exact claim excerpts. Point burial does not prove whole-binder "
        "impossibility; cysteine contact does not prove trafficking damage. Disulfide bonds "
        "constrain covalent connectivity, not whether a residue can make noncovalent contacts. "
        "Use measured exposure for exposure claims, not a disulfide-exclusion assumption. "
        "A supplied hotspot list is not the complete footprint of an unbuilt binder. "
        "Keep these distinctions in your own reasons as well as corrections. A discouraged but "
        "reviewable hypothesis can be ready-to-ask, with a warning and an alternative. "
        "Use ordinary scientific language to explain implications and uncertainties. "
        "Use fact_refs by default; runtime renders their precise values separately. "
        "Optional fact_claims assert an exact value of one DIRECT field of a referenced "
        "object, never a nested JSON path. There is no need to restate the supplied facts. "
        "Prose is not a source of "
        "verified facts. Do not recalculate facts, audit every residue or repeat sources. "
        + (
            "The previous response was truncated or did not submit. Use the recovery schema: "
            "exactly one reason, at most two uncertainties, and at most one fact_ref. "
            "When a prior typed opinion is supplied, correct that opinion instead of restarting "
            "the review. Correct the reported structured inconsistency using the supplied "
            "fact value. Keep each prose item to one short sentence under 240 characters. "
            "Complete the "
            "structured submission now. Retain any negative finding; do not change verdict "
            "to satisfy formatting."
            if recovery
            else "One or two short reasons are sufficient; prioritize completing the typed opinion."
        )
    )


def review_input(packet: dict[str, Any]) -> dict[str, Any]:
    """Exact scientific working set; omit transport/navigation instructions, not evidence."""
    keys = (
        "user_objective",
        "objective_requirements",
        "approved_target",
        "runtime_status",
        "residue_facts",
        "residue_constraints",
        "candidate_facts",
        "candidate_evaluation_scope",
        "reference_annotations",
        "receptor_context",
        "prepared_target_context",
        "final_site_decision",
        "decision_evidence",
        "downstream_validation",
        "authority",
        "avoid_design_labels",
        "peptide_reference",
        "peptide_facts",
        "peptide_overlaps",
    )
    return {
        **{key: packet[key] for key in keys if key in packet},
        "reference_collections": packet["fact_references"],
        "available_fact_ids": [key.split(":", 1)[1] for key in fact_paths(packet)],
        "reference_usage": "Use collection_name:zero_based_index in fact_refs and "
        "fact_claims.fact_ref. "
        "Use only supplied IDs, without counting or inventing indices. A claim field is a "
        "direct key of that fact object; null means the whole value. Mapping facts use column "
        "names. An annotation reference is one feature; its fields include location and type. "
        "Source passage is verbatim text, not a nested object: do not address JSON fields "
        "inside a passage string. Use annotation references for structured feature assertions. "
        "Source passages expand source_group through decision_evidence.source_metadata. "
        "Their exact original passages and qualifiers are retained.",
    }


def recovery_review_input(
    packet: dict[str, Any],
    *,
    failure: str,
    prior_opinion: dict[str, Any] | None,
    schema_diagnostic: str | None,
) -> dict[str, Any]:
    """Small decision view for typed recovery; the full packet remains validation authority.

    The first review receives the complete evidence packet. A retry exists to finish or repair
    that review, so it must not resend every passage, annotation and mapping namespace. Exact
    candidate facts, the full ranked interpretation and any fact cited by a prior typed opinion
    are retained. The eventual submission is still validated against ``packet``.
    """
    table = packet["residue_facts"]["facts_table"]
    columns = table["mapping_columns"] + table["metric_columns"]
    rows = [dict(zip(columns, values, strict=True)) for values in table["rows"]]
    by_label = {row["label_seq_id"]: row for row in rows}
    residue_fields = (
        "label_seq_id",
        "canonical_position",
        "canonical_residue",
        "amino_acid",
        "mapping_status",
        "rsasa",
        "surface_eligible",
    )
    decision = packet["final_site_decision"]
    interpretations = {
        candidate.get("candidate_id"): candidate
        for candidate in decision.get("interpretation", {}).get("candidates", [])
        if isinstance(candidate, dict)
    }
    candidates = []
    for candidate in packet["candidate_facts"]:
        labels = candidate["design_labels"]
        candidates.append(
            {
                **candidate,
                "residue_summary": [
                    {key: by_label[label].get(key) for key in residue_fields}
                    for label in labels
                    if label in by_label
                ],
                "ranking_interpretation": interpretations.get(candidate["candidate_id"]),
            }
        )

    target = packet["approved_target"]
    hard = target.get("hard_facts", {})
    identity_facts = target.get("identity", {})
    concise_target = {
        "identity": identity_facts,
        "hard_facts": {
            key: hard[key]
            for key in (
                "canonical_accession",
                "canonical_length",
                "selected_chain",
            )
            if key in hard
        },
        "bundle": target.get("bundle"),
    }

    prior_refs: list[str] = []
    if isinstance(prior_opinion, dict):
        refs = prior_opinion.get("fact_refs", [])
        if isinstance(refs, list):
            prior_refs.extend(ref for ref in refs if isinstance(ref, str))
        claims = prior_opinion.get("fact_claims", [])
        if isinstance(claims, list):
            prior_refs.extend(
                claim["fact_ref"]
                for claim in claims
                if isinstance(claim, dict) and isinstance(claim.get("fact_ref"), str)
            )
    full_paths = fact_paths(packet)
    prior_facts = {}
    prior_kinds = set()
    for short in dict.fromkeys(prior_refs):
        bound = bind_fact_ref(short, packet)
        if bound in full_paths:
            prior_facts[short] = fact_value(packet, bound)
            prior_kinds.add(full_paths[bound]["kind"])

    offered_kinds = {"target", "candidate", "topology", "exclusions", *prior_kinds}
    offered = {
        kind: value for kind, value in packet["fact_references"].items() if kind in offered_kinds
    }
    available = [
        key.split(":", 1)[1] for key, ref in full_paths.items() if ref["kind"] in offered_kinds
    ]
    available.extend(short for short in prior_facts if short not in available)
    return {
        "kind": "site-judge-recovery-view-v1",
        "user_objective": packet["user_objective"],
        "objective_requirements": packet.get("objective_requirements", {}),
        "approved_target": concise_target,
        "runtime_status": packet["runtime_status"],
        "candidate_facts": candidates,
        "final_site_decision": decision,
        "candidate_evaluation_scope": packet["candidate_evaluation_scope"],
        "downstream_validation": packet["downstream_validation"],
        "authority": packet["authority"],
        "avoid_design_labels": packet.get("avoid_design_labels", []),
        "reference_collections": offered,
        "available_fact_ids": list(dict.fromkeys(available)),
        "prior_referenced_facts": prior_facts,
        "submission_correction": {
            "failure": failure,
            "prior_unvalidated_submission_to_correct": prior_opinion,
            "schema_diagnostic": schema_diagnostic,
            "instruction": "Correct and submit only the compact typed verdict. The failed "
            "output is not evidence. Preserve substantive negative findings.",
        },
        "recovery_scope": "The immutable full evidence packet remains Runtime authority and "
        "will validate every fact reference and claim. This retry view removes repeated source "
        "passages and mapping metadata after the complete first review; it does not remove or "
        "change candidates, their order, their exact membership or their verified location.",
    }


def bind_fact_ref(short: str, packet: dict[str, Any]) -> str:
    return f"{packet['fact_revision']}:{short}"


def validate_partial_fact_submission(submitted: dict[str, Any], packet: dict[str, Any]) -> None:
    """A malformed prose field cannot hide an independently readable factual conflict."""
    refs = submitted.get("fact_refs", [])
    bound_refs = (
        [bind_fact_ref(r, packet) for r in refs if isinstance(r, str)]
        if isinstance(refs, list)
        else []
    )
    claims = submitted.get("fact_claims", [])
    bound_claims = []
    for raw in claims if isinstance(claims, list) else []:
        if isinstance(raw, dict):
            raw = {k: raw[k] for k in JudgeFactClaim.model_fields if k in raw}
        try:
            claim = JudgeFactClaim.model_validate(raw)
        except ValidationError:
            continue  # Invalid items cannot mask other, readable conflicting assertions.
        bound_claims.append(
            claim.model_copy(update={"fact_ref": bind_fact_ref(claim.fact_ref, packet)})
        )
    validate_fact_fields(bound_refs, bound_claims, packet)


def normalize_opinion(opinion: SiteJudgeVerdict, packet: dict[str, Any]) -> JudgeVerdict:
    errors = []
    recommendation = None
    try:
        recommendation = OptionRecommendation(
            option_id="site",
            status=opinion.recommendation,
            warnings=list(opinion.warnings),
            alternative=opinion.alternative,
        )
    except ValidationError as error:
        errors.append(str(error))
    try:
        validate_partial_fact_submission(opinion.model_dump(mode="json"), packet)
    except AgentBoundaryError as error:
        errors.append(str(error))
    if errors:
        raise AgentBoundaryError("; ".join(errors))
    assert recommendation is not None
    result = JudgeVerdict(
        verdict=opinion.verdict,
        reasons=list(opinion.reasons),
        limitations=list(opinion.uncertainties),
        recommendation=recommendation,
        site_claim_corrections=list(opinion.corrections),
        fact_refs=[bind_fact_ref(short, packet) for short in dict.fromkeys(opinion.fact_refs)],
        fact_claims=[
            c.model_copy(update={"fact_ref": bind_fact_ref(c.fact_ref, packet)})
            for c in opinion.fact_claims
        ],
    )
    validate_fact_references(result, packet)
    return result


class SiteJudgeUnavailable(AgentBoundaryError):
    """Only a classified operational failure, never a scientific verdict."""


class SiteJudgePreflightUnavailable(AgentBoundaryError):
    """The full bound Site review cannot fit before any model call is reserved."""


class SiteJudgeBoundary(AgentMiddleware[Any, Any, Any]):
    def __init__(self, bridge: Any, config: ModelConfig, execution_id: str):
        self.bridge, self.config, self.execution_id = bridge, config, execution_id
        self.schema_diagnostic: str | None = None

    def schema_error(self, error: Any) -> str:
        from langchain.agents.structured_output import (
            MultipleStructuredOutputsError,
            StructuredOutputValidationError,
        )

        if not isinstance(error, (MultipleStructuredOutputsError, StructuredOutputValidationError)):
            raise error
        self.schema_diagnostic = str(error)[:6000]
        message = error.ai_message
        self.bridge.store.event(
            self.bridge.thread,
            "structured-output-error",
            {
                "role": "judge",
                "execution_id": self.execution_id,
                "diagnostic": self.schema_diagnostic,
                "tool_calls": message.tool_calls,
                "invalid_tool_calls": message.invalid_tool_calls,
                "usage": message.usage_metadata,
                "stop_reason": message.response_metadata.get("stop_reason"),
                "usage_scope": "Counted once in model-response; reasoning text is not stored.",
            },
        )
        return self.schema_diagnostic

    def bound_packet(self) -> dict[str, Any]:
        packet: dict[str, Any] = self.bridge.judge_evidence()
        binding = EvidenceBinding.model_validate(
            {key: packet[key] for key in EvidenceBinding.model_fields}
        )
        if packet.get("gate_type") != "site-hotspot" or JUDGE_EVIDENCE.get() != binding:
            raise AgentBoundaryError("Site Judge lacks a current delegated binding")
        if "fact_references" not in packet:
            raise AgentBoundaryError("Compact Site Judge requires a dossier-backed proposal")
        return packet

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        from .judge_packet import validate_judge_corrections, validate_judge_stage

        packet = self.bound_packet()
        binding = {key: packet[key] for key in EvidenceBinding.model_fields}
        previous = [
            e["payload"]
            for e in self.bridge.store.events(self.bridge.thread)
            if e["kind"] == "rejected-submission"
            and e["payload"].get("execution_id") == self.execution_id
            and e["payload"].get("binding") == binding
        ]
        failures = [p["diagnostic"] for p in previous]
        last_opinion = next(
            (p["submitted_opinion"] for p in reversed(previous) if p.get("submitted_opinion")),
            None,
        )
        unaccepted_review_content = any(
            p.get("unaccepted_review_content") or p.get("substantive_finding")
            for p in previous
        )
        # Restart does not reset attempts. Normal and compact schemas share this contract.
        for attempt in range(len(previous), 3):
            if attempt:
                repairs = self.bridge.store.db.execute(
                    "SELECT COUNT(*) FROM events WHERE thread=? AND kind='contract-repair' "
                    "AND json_extract(payload,'$.execution_id')=? AND "
                    "(json_extract(payload,'$.contract') IS NULL OR "
                    "json_extract(payload,'$.contract')='JudgeVerdict')",
                    (self.bridge.thread, self.execution_id),
                ).fetchone()[0]
                if repairs >= 2:
                    break
                self.bridge.store.reserve_contract_repair(
                    self.bridge.thread,
                    "judge",
                    self.execution_id,
                    failures[-1],
                    contract="JudgeVerdict",
                )
            current = self.bound_packet()
            if identity(current) != identity(packet):
                raise AgentBoundaryError("Site Judge snapshot changed during review")
            recovery = attempt > 0
            schema = RecoverySiteJudgeVerdict if recovery else SiteJudgeVerdict
            diagnostic = self.schema_diagnostic or next(
                (
                    p.get("schema_diagnostic")
                    for p in reversed(previous)
                    if p.get("schema_diagnostic")
                ),
                None,
            )
            working = (
                recovery_review_input(
                    packet,
                    failure=failures[-1],
                    prior_opinion=last_opinion,
                    schema_diagnostic=diagnostic,
                )
                if recovery
                else review_input(packet)
            )
            messages = [HumanMessage(content=compact(working))]
            system = SystemMessage(content=review_prompt(recovery=recovery))
            schema_chars = len(compact([convert_to_openai_tool(schema)]))
            try:
                usage = context_usage(
                    request.model, self.config, "judge", [system, *messages], schema_chars
                )
            except ModelContextCapacityError as error:
                # Capacity is an operational Reviewer failure, not a Site verdict. Preserve
                # the first-call proof separately; a failed recovery is recorded against the
                # already-reserved repair so the Scientist Gate can still open.
                if attempt != 0 or previous:
                    diagnostic = "MODEL_CONTEXT_CAPACITY_EXCEEDED"
                    failures.append(diagnostic)
                    self.bridge.store.event(
                        self.bridge.thread,
                        "rejected-submission",
                        {
                            "role": "judge",
                            "execution_id": self.execution_id,
                            "binding": binding,
                            "diagnostic": diagnostic,
                            "diagnostic_code": diagnostic,
                            "schema_diagnostic": self.schema_diagnostic,
                            "submitted_opinion": last_opinion,
                            "schema_valid": False,
                            "substantive_finding": False,
                            "unaccepted_review_content": unaccepted_review_content,
                            "usage": error.usage,
                        },
                    )
                    raise SiteJudgeUnavailable("; ".join(failures)) from error
                self.bridge.store.event(
                    self.bridge.thread,
                    "site-judge-context-preflight-failed",
                    {
                        "role": "judge",
                        "execution_id": self.execution_id,
                        "binding": binding,
                        "diagnostic": "MODEL_CONTEXT_CAPACITY_EXCEEDED",
                        "source_role": "verified-runtime",
                        "usage": error.usage,
                    },
                )
                raise SiteJudgePreflightUnavailable(str(error)) from error
            self.bridge.store.reserve_model_call(
                self.bridge.thread, "judge", self.config.max_model_calls, self.execution_id
            )
            self.bridge.store.event(
                self.bridge.thread,
                "model-context",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "binding": binding,
                    **usage,
                    "context_chars": usage["input_chars_with_schemas"] - schema_chars,
                    "estimated_input_chars_with_schemas": usage["input_chars_with_schemas"],
                    "context_metric": "system and message content; tool schemas separately",
                    "limit": self.config.hard_input_chars,
                    "tool_schema_chars": schema_chars,
                    "repair_attempt": attempt,
                    "tool_mode": "site-judge-recovery" if recovery else "site-judge",
                    "structured_output_tool": schema.__name__,
                    "offered_action_tools": [],
                    **(
                        {
                            "full_review_input_chars": len(compact(review_input(packet))),
                            "recovery_review_input_chars": len(compact(working)),
                        }
                        if recovery
                        else {}
                    ),
                },
            )
            call = request.override(
                system_message=system,
                messages=messages,
                tools=[],
                response_format=ToolStrategy(schema, handle_errors=self.schema_error),
            )
            self.schema_diagnostic = None
            started = perf_counter()
            from anthropic import APIConnectionError as AnthropicConnectionError
            from anthropic import APITimeoutError as AnthropicTimeout
            from anthropic import InternalServerError as AnthropicServerError
            from anthropic import RateLimitError as AnthropicRateLimit
            from openai import APIConnectionError as OpenAIConnectionError
            from openai import APITimeoutError as OpenAITimeout
            from openai import InternalServerError as OpenAIServerError
            from openai import RateLimitError as OpenAIRateLimit

            transport_failure = None
            try:
                response = await handler(call)
            except (AnthropicTimeout, OpenAITimeout):
                response = None
                transport_failure = "PROVIDER_TIMEOUT"
            except (
                AnthropicConnectionError,
                AnthropicServerError,
                AnthropicRateLimit,
                OpenAIConnectionError,
                OpenAIServerError,
                OpenAIRateLimit,
            ):
                response = None
                transport_failure = "PROVIDER_UNAVAILABLE"
            raw = [m for m in response.result if isinstance(m, AIMessage)] if response else []
            records = [
                {
                    "stop_reason": m.response_metadata.get("stop_reason")
                    or m.response_metadata.get("finish_reason"),
                    "usage": m.usage_metadata,
                    "tool_names": [c["name"] for c in m.tool_calls],
                    "invalid_tool_names": [c.get("name") for c in m.invalid_tool_calls],
                }
                for m in raw
            ]
            self.bridge.store.event(
                self.bridge.thread,
                "model-response",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "latency_seconds": perf_counter() - started,
                    "responses": records,
                    "transport_failure": transport_failure,
                },
            )
            opinion = response.structured_response if response else None
            submitted = (
                opinion.model_dump(mode="json")
                if isinstance(opinion, SiteJudgeVerdict)
                else next(
                    (
                        c["args"]
                        for m in raw
                        for c in m.tool_calls
                        if c["name"] in {"SiteJudgeVerdict", "RecoverySiteJudgeVerdict"}
                        and isinstance(c.get("args"), dict)
                    ),
                    None,
                )
            )
            fact_error = None
            if submitted is not None:
                last_opinion = submitted
                if not isinstance(opinion, SiteJudgeVerdict):
                    try:
                        validate_partial_fact_submission(submitted, packet)
                    except AgentBoundaryError as error:
                        fact_error = type(error).__name__ + ": " + str(error)
            if isinstance(opinion, SiteJudgeVerdict):
                try:
                    normalized = normalize_opinion(opinion, packet)
                    validate_judge_stage(normalized, packet)
                    validate_judge_corrections(normalized, packet)
                except (AgentBoundaryError, ValueError) as error:
                    diagnostic = type(error).__name__ + ": " + str(error)
                    diagnostic_code = "INVALID_REVIEW_SUBMISSION"
                    unaccepted_review_content = True
                else:
                    self.bridge.store.event(
                        self.bridge.thread,
                        "submission-preflight-passed",
                        {
                            "role": "judge",
                            "execution_id": self.execution_id,
                            "review_contract": schema.__name__,
                            "binding": binding,
                        },
                    )
                    return response
            else:
                unaccepted_review_content |= any(
                    isinstance(c.get("args"), dict)
                    and c["args"].get("verdict") in {"reject", "insufficient"}
                    for m in raw
                    for c in m.tool_calls
                )
                if fact_error:
                    diagnostic_code = "INVALID_REVIEW_SUBMISSION"
                    unaccepted_review_content = True
                elif transport_failure:
                    diagnostic_code = transport_failure
                elif any(r["stop_reason"] in {"max_tokens", "length"} for r in records):
                    diagnostic_code = "OUTPUT_TRUNCATED"
                else:
                    diagnostic_code = "MISSING_OR_INVALID_TYPED_SUBMISSION"
                diagnostic = fact_error or diagnostic_code
            failures.append(diagnostic)
            self.bridge.store.event(
                self.bridge.thread,
                "rejected-submission",
                {
                    "role": "judge",
                    "execution_id": self.execution_id,
                    "binding": binding,
                    "diagnostic": diagnostic,
                    "diagnostic_code": diagnostic_code,
                    "schema_diagnostic": self.schema_diagnostic,
                    "submitted_opinion": submitted,
                    "schema_valid": isinstance(opinion, SiteJudgeVerdict),
                    "substantive_finding": False,
                    "unaccepted_review_content": unaccepted_review_content,
                },
            )
        raise SiteJudgeUnavailable("; ".join(failures))

    async def aafter_agent(self, state: Any, runtime: Any) -> Any:
        opinion = state.get("structured_response")
        if not isinstance(opinion, SiteJudgeVerdict):
            raise AgentBoundaryError("Site Judge did not finish with a valid typed opinion")
        packet = self.bound_packet()
        assessment = self.bridge.register_judge(normalize_opinion(opinion, packet))
        self.bridge.store.event(
            self.bridge.thread,
            "site-judge-submission",
            {
                "execution_id": self.execution_id,
                "assessment_id": assessment.assessment_id,
                "raw_opinion": opinion.model_dump(mode="json"),
                "fact_revision": packet["fact_revision"],
            },
        )
        return {
            "messages": [
                AIMessage(
                    content=compact(
                        {
                            "assessment_id": assessment.assessment_id,
                            "verdict": assessment.verdict,
                        }
                    )
                )
            ]
        }


def create_site_judge(bridge: Any, model: Any, config: ModelConfig, execution_id: str) -> Any:
    boundary = SiteJudgeBoundary(bridge, config, execution_id)
    return create_agent(
        model=model,
        system_prompt=review_prompt(),
        tools=[],
        middleware=[boundary],
        response_format=ToolStrategy(
            SiteJudgeVerdict | RecoverySiteJudgeVerdict, handle_errors=boundary.schema_error
        ),
        name="site-independent-judge",
    )


def create_site_aware_judge(
    bridge: Any, model: Any, config: ModelConfig, execution_id: str | None, legacy: Any
) -> Any:
    """Use the compact contract only for dossier-backed Gate 2; other Gates retain theirs."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class State(TypedDict):
        messages: list[Any]
        structured_response: Any

    async def route(state: Any) -> str:
        packet = bridge.judge_evidence()
        return (
            "site"
            if packet.get("gate_type") == "site-hotspot" and "fact_references" in packet
            else "legacy"
        )

    async def site(state: Any, config: RunnableConfig) -> Any:
        if execution_id is None:
            raise AgentBoundaryError("Site Judge requires a persisted execution")
        try:
            return await create_site_judge(bridge, model, model_config, execution_id).ainvoke(
                {"messages": [HumanMessage(content="Review the current delegated Site proposal.")]},
                config,
            )
        except SiteJudgePreflightUnavailable:
            from .site_review_availability import record_preflight_unavailable

            failure = record_preflight_unavailable(bridge, execution_id)
        except SiteJudgeUnavailable:
            from .site_review_availability import record_unavailable

            failure = record_unavailable(bridge, execution_id)
        return {
            "messages": [
                AIMessage(
                    content=compact(
                        {
                            "review_availability": "unavailable",
                            "review_failure_id": failure["record_id"],
                            "next": "Scientist review required; assessment unavailable",
                        }
                    )
                )
            ],
            "structured_response": None,
        }

    async def legacy_with_fallback(state: Any, config: RunnableConfig) -> Any:
        packet = bridge.judge_evidence()
        if packet.get("gate_type") != "design-specification":
            return await legacy.ainvoke(state, config)
        from anthropic import APIConnectionError as AnthropicConnectionError
        from anthropic import APITimeoutError as AnthropicTimeout
        from anthropic import InternalServerError as AnthropicServerError
        from anthropic import RateLimitError as AnthropicRateLimit
        from openai import APIConnectionError as OpenAIConnectionError
        from openai import APITimeoutError as OpenAITimeout
        from openai import InternalServerError as OpenAIServerError
        from openai import RateLimitError as OpenAIRateLimit

        from .review_availability import ReviewUnavailable, record_design_unavailable

        try:
            return await legacy.ainvoke(state, config)
        except ReviewUnavailable as error:
            failure_code, diagnostic = error.code, error.detail
        except ModelContextCapacityError as error:
            failure_code, diagnostic = "MODEL_CONTEXT_CAPACITY_EXCEEDED", str(error)
        except (AnthropicTimeout, OpenAITimeout) as error:
            failure_code, diagnostic = "PROVIDER_TIMEOUT", str(error)
        except (
            AnthropicConnectionError,
            AnthropicServerError,
            AnthropicRateLimit,
            OpenAIConnectionError,
            OpenAIServerError,
            OpenAIRateLimit,
        ) as error:
            failure_code, diagnostic = "PROVIDER_UNAVAILABLE", str(error)
        if execution_id is None:
            raise AgentBoundaryError("Design Judge fallback requires a persisted execution")
        failure = record_design_unavailable(
            bridge,
            execution_id,
            failure_code=failure_code,
            diagnostic=diagnostic,
        )
        return {
            "messages": [
                AIMessage(
                    content=compact(
                        {
                            "review_availability": "unavailable",
                            "review_failure_id": failure["record_id"],
                            "next": "Scientist Gate 3 review; advisory assessment unavailable",
                        }
                    )
                )
            ],
            "structured_response": None,
        }

    model_config = config
    graph = StateGraph(State)
    graph.add_node("site", site)
    graph.add_node("legacy", legacy_with_fallback)
    graph.add_conditional_edges(START, route, {"site": "site", "legacy": "legacy"})
    graph.add_edge("site", END)
    graph.add_edge("legacy", END)
    return graph.compile(name="independent-judge-boundary")
