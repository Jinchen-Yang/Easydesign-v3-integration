"""Immutable, human-gated comparison evidence for the OpenFold3 gray rollout."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ConfigurationError, sha256_file
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN
from easydesign.workspace_context import WorkspaceContext

ValidationBackend = Literal[
    "openfold3-af3-jax",
    "protenix-v2",
]
ValidationPanelId = Literal[
    "afo-release-comparison-v2",
    "afo-stable-sanity-mini-v1",
]


class ValidationPanelCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=ID_PATTERN)
    case_class: Literal["technical", "positive-control", "boundary-negative"]
    source_uri: str
    assembly_id: str | None = None
    chain_annotations: dict[str, str] = Field(default_factory=dict)
    required_backends: tuple[ValidationBackend, ...]

    @model_validator(mode="after")
    def validate_backends(self) -> Self:
        if not self.required_backends or len(self.required_backends) != len(
            set(self.required_backends)
        ):
            raise ValueError("validation case required_backends 必须非空且唯一")
        return self


class OpenFold3ValidationPanel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    panel_id: ValidationPanelId
    cases: tuple[ValidationPanelCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> Self:
        identities = [item.case_id for item in self.cases]
        if len(identities) != len(set(identities)):
            raise ValueError("validation panel case identity 不能重复")
        return self


class ValidationEvidenceFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: Path
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    def verify(self) -> Path:
        selected = self.path.expanduser().resolve(strict=True)
        if not selected.is_file() or selected.stat().st_size != self.size_bytes:
            raise ConfigurationError(f"validation evidence 大小不一致: {selected}")
        if sha256_file(selected) != self.sha256:
            raise ConfigurationError(f"validation evidence SHA-256 不一致: {selected}")
        return selected


class BackendValidationObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=ID_PATTERN)
    backend: ValidationBackend
    backend_identity: str
    model_identity: str
    structure: ValidationEvidenceFile
    summary_confidence: ValidationEvidenceFile | None = None
    full_confidence: ValidationEvidenceFile | None = None
    chain_ids: tuple[str, ...] = Field(min_length=1)
    chain_complete: bool
    mean_plddt: float | None = None
    pairwise_iptm: float | None = None
    ptm: float | None = None
    binder_ptm: float | None = None
    minimum_interface_pae_angstrom: float | None = Field(default=None, ge=0)
    target_ca_rmsd_angstrom: float | None = Field(default=None, ge=0)
    binder_pose_rmsd_angstrom: float | None = Field(default=None, ge=0)
    has_clash: bool | None = None
    gpde: float | None = None
    native_metrics: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    @property
    def threshold_pass(self) -> bool | None:
        required = (
            self.pairwise_iptm,
            self.minimum_interface_pae_angstrom,
            self.binder_ptm,
            self.target_ca_rmsd_angstrom,
        )
        if any(value is None for value in required) or self.has_clash is None:
            return None
        assert self.pairwise_iptm is not None
        assert self.minimum_interface_pae_angstrom is not None
        assert self.binder_ptm is not None
        assert self.target_ca_rmsd_angstrom is not None
        return (
            self.chain_complete
            and self.pairwise_iptm >= 0.60
            and self.minimum_interface_pae_angstrom <= 10.0
            and self.binder_ptm >= 0.60
            and self.target_ca_rmsd_angstrom <= 3.0
            and not self.has_clash
        )


class AfoValidationReleaseIdentity(BaseModel):
    """Exact AFO supply-chain identity to which panel evidence is bound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    backend_id: Literal["openfold3-af3-jax"] = "openfold3-af3-jax"
    backend_version: str = Field(
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
    )
    model_id: Literal["of3-p2-155k"] = "of3-p2-155k"
    adapter_contract_version: Literal["openfold3-af3-jax-cli-v1"] = (
        "openfold3-af3-jax-cli-v1"
    )
    release_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    conversion_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    converted_weight_sha256: str = Field(pattern=SHA256_PATTERN)
    wheel_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    runner_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runner_tree_sha256: str = Field(pattern=SHA256_PATTERN)

    def native_metrics(self) -> dict[str, str]:
        return self.model_dump(mode="json")


class OpenFold3ValidationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    afo_release: AfoValidationReleaseIdentity
    observations: tuple[BackendValidationObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identities(self) -> Self:
        identities = [(item.case_id, item.backend) for item in self.observations]
        if len(identities) != len(set(identities)):
            raise ValueError("每个 case/backend 只能有一个冻结 observation")
        expected = self.afo_release.native_metrics()
        for item in self.observations:
            if item.backend != "openfold3-af3-jax":
                continue
            if item.model_identity != self.afo_release.model_id:
                raise ValueError("AFO observation model identity 与 release 不一致")
            for key, value in expected.items():
                if item.native_metrics.get(key) != value:
                    raise ValueError(f"AFO observation 缺少或错配 release identity: {key}")
        return self


class MetricDrift(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    first_backend: ValidationBackend
    second_backend: ValidationBackend
    pairwise_iptm_delta: float | None
    ptm_delta: float | None
    binder_ptm_delta: float | None
    minimum_interface_pae_delta_angstrom: float | None
    target_ca_rmsd_delta_angstrom: float | None
    threshold_decision_changed: bool | None


class OpenFold3ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.2"] = "0.2"
    report_id: str = Field(pattern=ID_PATTERN)
    generated_at: datetime
    panel_id: ValidationPanelId
    panel_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    afo_release: AfoValidationReleaseIdentity
    observations: tuple[BackendValidationObservation, ...]
    metric_drift: tuple[MetricDrift, ...]
    status: Literal["awaiting-researcher-approval"] = "awaiting-researcher-approval"
    automatic_acceptance_threshold: None = None
    default_backend_changed: Literal[False] = False


class OpenFold3ApprovalReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["0.3"] = "0.3"
    report_sha256: str = Field(pattern=SHA256_PATTERN)
    afo_release: AfoValidationReleaseIdentity
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: datetime
    decision: Literal["approve-stable-promotion", "reject-stable-promotion"]
    notes: str = Field(default="", max_length=4096)
    default_backend_changed: Literal[False] = False


def _load_panel(path: Path) -> OpenFold3ValidationPanel:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return OpenFold3ValidationPanel.model_validate(payload)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as error:
        raise ConfigurationError(f"OpenFold3 validation panel 无法校验: {path}") from error


def _delta(first: float | None, second: float | None) -> float | None:
    return None if first is None or second is None else second - first


def generate_openfold3_validation_report(
    *,
    panel_path: Path,
    evidence_path: Path,
) -> Path:
    """Verify a complete fixed panel and publish an immutable comparison report."""

    panel_file = panel_path.expanduser().resolve(strict=True)
    evidence_file = evidence_path.expanduser().resolve(strict=True)
    panel = _load_panel(panel_file)
    try:
        evidence = OpenFold3ValidationEvidence.model_validate_json(
            evidence_file.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ConfigurationError(
            f"OpenFold3 validation evidence 无法校验: {evidence_file}"
        ) from error
    panel_by_id = {item.case_id: item for item in panel.cases}
    observed = {(item.case_id, item.backend) for item in evidence.observations}
    expected = {
        (case.case_id, backend)
        for case in panel.cases
        for backend in case.required_backends
    }
    unknown = {identity for identity in observed if identity[0] not in panel_by_id}
    missing = expected - observed
    if unknown or missing:
        raise ConfigurationError(
            f"validation panel 不完整: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    for item in evidence.observations:
        item.structure.verify()
        if item.summary_confidence is not None:
            item.summary_confidence.verify()
        if item.full_confidence is not None:
            item.full_confidence.verify()
    by_case: dict[str, list[BackendValidationObservation]] = {}
    for item in evidence.observations:
        by_case.setdefault(item.case_id, []).append(item)
    drift: list[MetricDrift] = []
    for case_id, observations in sorted(by_case.items()):
        for first, second in combinations(
            sorted(observations, key=lambda item: item.backend), 2
        ):
            first_pass = first.threshold_pass
            second_pass = second.threshold_pass
            drift.append(
                MetricDrift(
                    case_id=case_id,
                    first_backend=first.backend,
                    second_backend=second.backend,
                    pairwise_iptm_delta=_delta(first.pairwise_iptm, second.pairwise_iptm),
                    ptm_delta=_delta(first.ptm, second.ptm),
                    binder_ptm_delta=_delta(first.binder_ptm, second.binder_ptm),
                    minimum_interface_pae_delta_angstrom=_delta(
                        first.minimum_interface_pae_angstrom,
                        second.minimum_interface_pae_angstrom,
                    ),
                    target_ca_rmsd_delta_angstrom=_delta(
                        first.target_ca_rmsd_angstrom,
                        second.target_ca_rmsd_angstrom,
                    ),
                    threshold_decision_changed=(
                        None
                        if first_pass is None or second_pass is None
                        else first_pass != second_pass
                    ),
                )
            )
    panel_sha = sha256_file(panel_file)
    evidence_sha = sha256_file(evidence_file)
    report = OpenFold3ValidationReport(
        report_id=f"openfold3-gray-{evidence_sha[:16]}",
        generated_at=datetime.now(UTC),
        panel_id=panel.panel_id,
        panel_sha256=panel_sha,
        evidence_sha256=evidence_sha,
        afo_release=evidence.afo_release,
        observations=tuple(
            sorted(evidence.observations, key=lambda item: (item.case_id, item.backend))
        ),
        metric_drift=tuple(drift),
    )
    context = WorkspaceContext.discover()
    destination = (
        context.runtime_root
        / "validation/openfold3"
        / f"{report.report_id}-{panel_sha[:12]}"
        / "report.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=False)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(report.model_dump_json(indent=2))
        handle.write("\n")
    return destination


def approve_openfold3_validation_report(
    *,
    report_path: Path,
    reviewer: str,
    decision: Literal["approve-stable-promotion", "reject-stable-promotion"],
    notes: str = "",
    confirm: bool,
) -> Path:
    """Record a human decision without changing the configured default backend."""

    if not confirm:
        raise ConfigurationError("OpenFold3 validation approval 需要 --confirm")
    selected = report_path.expanduser().resolve(strict=True)
    try:
        report = OpenFold3ValidationReport.model_validate_json(
            selected.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ConfigurationError(f"OpenFold3 validation report 无法校验: {selected}") from error
    if report.status != "awaiting-researcher-approval":
        raise ConfigurationError("OpenFold3 validation report 状态不允许批准")
    report_sha = sha256_file(selected)
    receipt = OpenFold3ApprovalReceipt(
        report_sha256=report_sha,
        afo_release=report.afo_release,
        reviewer=reviewer.strip(),
        reviewed_at=datetime.now(UTC),
        decision=decision,
        notes=notes,
    )
    context = WorkspaceContext.discover()
    destination = (
        context.runtime_root
        / "state/components/openfold3-p2-af3-jax/releases"
        / report.afo_release.release_id
        / "approvals"
        / f"{report_sha}-{decision}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(receipt.model_dump_json(indent=2))
        handle.write("\n")
    return destination


__all__ = [
    "BackendValidationObservation",
    "AfoValidationReleaseIdentity",
    "OpenFold3ApprovalReceipt",
    "OpenFold3ValidationEvidence",
    "OpenFold3ValidationPanel",
    "OpenFold3ValidationReport",
    "approve_openfold3_validation_report",
    "generate_openfold3_validation_report",
]
