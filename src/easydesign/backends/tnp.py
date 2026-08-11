"""Therapeutic Nanobody Profiler (TNP) file-protocol adapter.

The core environment never imports ANARCI, ImmuneBuilder, DSSP, or TNP.  This
adapter probes one explicitly configured Python 3.10 environment, executes the
upstream batch command without a shell, and strictly converts its files into
EasyDesign contracts.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import BackendContractError, ManifestStateError, sha256_file
from easydesign.filtering.nanobody_final_v1_5 import classify_tnp_risk
from easydesign.orchestration.git_sources import verify_git_source_identity
from easydesign.stages.s07_final_filtering_and_selection import (
    SequenceLiability,
    TnpCandidateRecord,
)
from easydesign.workspace_context import INHERITED_INTERPRETER_ENVIRONMENT

TNP_COMMIT = "29dcac72f1380e8538e8870f45a699d3c6156162"
TNP_LICENSE = "BSD-3-Clause"
TNP_LICENSE_SHA256 = "a4f40e49f79300e759b09e6805c46d5e60fa1bad9d27b0ddfbb9a144e2b01de6"
TNP_EXECUTABLE_SOURCE_SHA256 = "87085d798cd69b519ca9d3f5aa02b6da8edd3fd3dc5624067e72d7cb0fc303c0"
TNP_SOURCE = "https://github.com/oxpig/TNP.git"
TNP_EXPECTED_DEPENDENCIES = {
    # Bioconda ANARCI 2024.05.21 exposes Python distribution metadata 1.3.
    "anarci": "1.3",
    "biopython": "1.77",
    "ImmuneBuilder": "1.2",
    "torch": "2.13.0",
    "scipy": "1.15.3",
    "scikit-learn": "1.7.2",
    "einops": "0.8.2",
    "requests": "2.34.2",
    "theraprofnano": "0.0.1",
    "pdbfixer": "1.9.0",
    "OpenMM": "8.5.2",
    "setuptools": "80.9.0",
}
TNP_EXPECTED_CONDA_PACKAGES = {
    "anarci": "2024.05.21",
    "dssp": "4.6.1",
}
_RESULT_NAME = "TNP_Results_Multientry.json"
_FLAG_KEYS = frozenset({"L", "L3", "C", "PSH", "PPC", "PNC"})
_LIABILITY_NAMES = {
    "Met oxidation (M)": "met-oxidation",
    "Trp oxidation (W)": "trp-oxidation",
    "Asn deamidation (NG NS NT)": "asn-deamidation",
    "Asp isomerisation (DG DS DT DD DH)": "asp-isomerisation",
    "Lysine Glycation (KE KD EK ED)": "lysine-glycation",
    "Fragmentation (DP)": "fragmentation",
}


def _verified_tnp_source_snapshot(repository_root: Path) -> str:
    """Verify the installer-owned source identity without parent Git discovery."""

    try:
        result = verify_git_source_identity(
            repository_root,
            source=TNP_SOURCE,
            revision=TNP_COMMIT,
        )
    except Exception as error:
        raise BackendContractError(
            f"TNP source snapshot identity 不匹配: {error}"
        ) from error
    return result.revision


@dataclass(frozen=True, slots=True)
class TnpBatchRequest:
    sequences: tuple[tuple[str, str], ...]
    output_directory: Path
    input_fasta: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True, slots=True)
class TnpBatchResult:
    started_at: datetime
    ended_at: datetime
    return_code: int
    result_path: Path | None
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True, slots=True)
class TnpAdapter:
    python: Path
    executable: Path
    repository_root: Path
    timeout_seconds: float = 86_400.0
    ncores: int = 4

    def __post_init__(self) -> None:
        for name, path in (
            ("python", self.python),
            ("executable", self.executable),
            ("repository_root", self.repository_root),
        ):
            if not path.is_absolute():
                raise BackendContractError(f"TNP {name} 必须为绝对路径")
        if self.timeout_seconds <= 0 or self.ncores < 1:
            raise BackendContractError("TNP timeout/ncores 必须为正数")

    def _probe_command(
        self,
        code: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [str(self.python), "-c", code],
                cwd=self.repository_root,
                env=self._runtime_environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=min(self.timeout_seconds, 120.0),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"TNP runtime probe 无法执行: {error}") from error

    def _runtime_environment(self) -> dict[str, str]:
        """Activate only the explicitly configured prefix for native libraries."""

        prefix = self.python.parent.parent
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in INHERITED_INTERPRETER_ENVIRONMENT
        }
        environment["PATH"] = os.pathsep.join(
            part for part in (str(prefix / "bin"), environment.get("PATH", "")) if part
        )
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            part for part in (str(prefix / "lib"), environment.get("LD_LIBRARY_PATH", "")) if part
        )
        environment["CONDA_PREFIX"] = str(prefix)
        environment["PYTHONNOUSERSITE"] = "1"
        # TNP is a CPU evidence backend; it must not contend with BoltzGen or
        # Protenix GPU tasks merely because a CUDA-enabled Torch wheel is present.
        environment["CUDA_VISIBLE_DEVICES"] = ""
        return environment

    def _conda_package_version(self, package: str) -> str:
        metadata_directory = self.python.parent.parent / "conda-meta"
        matches = sorted(metadata_directory.glob(f"{package}-*.json"))
        if len(matches) != 1:
            raise BackendContractError(
                f"TNP Conda package identity 不唯一: package={package}, "
                f"matches={[path.name for path in matches]}"
            )
        try:
            payload = json.loads(matches[0].read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackendContractError(
                f"TNP Conda package metadata 无法解析: {matches[0]}"
            ) from error
        version = payload.get("version")
        if not isinstance(version, str) or not version:
            raise BackendContractError(f"TNP Conda package metadata 缺少版本: {matches[0]}")
        return version

    def probe(self) -> dict[str, str]:
        """Require the audited source and all imports needed by the real backend."""

        if not self.python.is_file() or not os.access(self.python, os.X_OK):
            raise BackendContractError(f"TNP Python 不可执行: {self.python}")
        if not self.executable.is_file():
            raise BackendContractError(f"TNP executable 不存在: {self.executable}")
        if not self.repository_root.is_dir():
            raise BackendContractError(f"TNP repository 不存在: {self.repository_root}")
        source_commit = _verified_tnp_source_snapshot(self.repository_root)
        license_path = self.repository_root / "LICENCE"
        source_executable = self.repository_root / "bin" / "TNP"
        if not license_path.is_file() or sha256_file(license_path) != TNP_LICENSE_SHA256:
            raise BackendContractError("TNP BSD-3-Clause license identity 不匹配")
        if (
            not source_executable.is_file()
            or sha256_file(source_executable) != TNP_EXECUTABLE_SOURCE_SHA256
        ):
            raise BackendContractError("TNP upstream executable source identity 不匹配")
        probe = self._probe_command(
            "import importlib.metadata as m,json,sys;"
            "import anarci,Bio,ImmuneBuilder,openmm,pdbfixer,torch,theraprofnano;"
            "print(json.dumps({"
            "'python':'.'.join(map(str,sys.version_info[:3])),"
            "'anarci':m.version('anarci'),"
            "'biopython':Bio.__version__,"
            "'ImmuneBuilder':m.version('ImmuneBuilder'),"
            "'torch':m.version('torch'),"
            "'scipy':m.version('scipy'),"
            "'scikit-learn':m.version('scikit-learn'),"
            "'einops':m.version('einops'),"
            "'requests':m.version('requests'),"
            "'theraprofnano':m.version('theraprofnano'),"
            "'pdbfixer':m.version('pdbfixer'),"
            "'OpenMM':m.version('OpenMM'),"
            "'setuptools':m.version('setuptools')"
            "},sort_keys=True))"
        )
        if probe.returncode != 0:
            raise BackendContractError(f"TNP dependency probe 失败: {probe.stderr.strip()[-2048:]}")
        try:
            versions = json.loads(probe.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise BackendContractError("TNP dependency probe 未返回版本 JSON") from error
        if not isinstance(versions, dict) or not str(versions.get("python", "")).startswith(
            "3.10."
        ):
            raise BackendContractError(
                f"TNP 必须使用 Python 3.10，实际={versions.get('python', 'unknown')}"
            )
        observed_dependencies = {
            key: str(versions.get(key, "unknown")) for key in TNP_EXPECTED_DEPENDENCIES
        }
        if observed_dependencies != TNP_EXPECTED_DEPENDENCIES:
            raise BackendContractError(
                "TNP dependency identity 不匹配: "
                f"expected={TNP_EXPECTED_DEPENDENCIES}, actual={observed_dependencies}"
            )
        conda_packages = {
            package: self._conda_package_version(package) for package in TNP_EXPECTED_CONDA_PACKAGES
        }
        if conda_packages != TNP_EXPECTED_CONDA_PACKAGES:
            raise BackendContractError(
                "TNP Conda package identity 不匹配: "
                f"expected={TNP_EXPECTED_CONDA_PACKAGES}, actual={conda_packages}"
            )
        dssp = self.python.parent / "mkdssp"
        if not dssp.is_file() or not os.access(dssp, os.X_OK):
            raise BackendContractError(f"TNP mkdssp 不可执行: {dssp}")
        dssp_probe = subprocess.run(
            [str(dssp), "--version"],
            env=self._runtime_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        dssp_version = (dssp_probe.stdout + dssp_probe.stderr).strip()
        if dssp_probe.returncode != 0 or "4.6.1" not in dssp_version:
            raise BackendContractError(f"TNP DSSP identity 不匹配: {dssp_version or 'unknown'}")
        help_result = subprocess.run(
            [str(self.python), str(self.executable), "--help"],
            cwd=self.repository_root,
            env=self._runtime_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=min(self.timeout_seconds, 120.0),
        )
        if help_result.returncode != 0 or "--file" not in help_result.stdout:
            raise BackendContractError("TNP CLI help probe 失败或不支持 batch FASTA")
        return {
            "backend": "tnp",
            "commit": source_commit,
            "license": TNP_LICENSE,
            "license_sha256": TNP_LICENSE_SHA256,
            "source_executable_sha256": TNP_EXECUTABLE_SOURCE_SHA256,
            "python_version": str(versions["python"]),
            "biopython_version": str(versions["biopython"]),
            "anarci_version": str(versions["anarci"]),
            "anarci_conda_version": conda_packages["anarci"],
            "immunebuilder_version": str(versions["ImmuneBuilder"]),
            "torch_version": str(versions["torch"]),
            "openmm_version": str(versions["OpenMM"]),
            "pdbfixer_version": str(versions["pdbfixer"]),
            "setuptools_version": str(versions["setuptools"]),
            "dssp_version": conda_packages["dssp"],
        }

    def write_input(self, request: TnpBatchRequest) -> None:
        if not request.sequences:
            raise BackendContractError("TNP batch 至少需要一个候选")
        ids = [candidate_id for candidate_id, _ in request.sequences]
        if len(ids) != len(set(ids)):
            raise BackendContractError("TNP candidate ID 不能重复")
        request.input_fasta.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            f">{candidate_id}\n{sequence}\n" for candidate_id, sequence in request.sequences
        )
        try:
            request.input_fasta.write_text(
                body,
                encoding="ascii",
                errors="strict",
            )
        except OSError as error:
            raise BackendContractError(f"TNP FASTA 无法写入: {error}") from error

    def execute(self, request: TnpBatchRequest) -> TnpBatchResult:
        self.probe()
        if request.output_directory.exists():
            raise BackendContractError(f"TNP output 禁止覆盖: {request.output_directory}")
        self.write_input(request)
        request.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        request.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.python),
            str(self.executable),
            "--name",
            "easydesign-stage07",
            "--output",
            str(request.output_directory),
            "--file",
            str(request.input_fasta),
            "--ncores",
            str(self.ncores),
        ]
        started = datetime.now(UTC)
        try:
            with (
                request.stdout_path.open("x", encoding="utf-8") as stdout,
                request.stderr_path.open("x", encoding="utf-8") as stderr,
            ):
                completed = subprocess.run(
                    command,
                    cwd=self.repository_root,
                    env=self._runtime_environment(),
                    check=False,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            return_code = completed.returncode
        except subprocess.TimeoutExpired:
            return_code = 124
            with request.stderr_path.open("a", encoding="utf-8") as stderr:
                stderr.write(
                    f"\nEasyDesign operational timeout after {self.timeout_seconds} seconds.\n"
                )
        ended = datetime.now(UTC)
        result_path = request.output_directory / _RESULT_NAME
        return TnpBatchResult(
            started_at=started,
            ended_at=ended,
            return_code=return_code,
            result_path=result_path if result_path.is_file() else None,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
        )

    def collect(
        self,
        request: TnpBatchRequest,
        result: TnpBatchResult,
    ) -> tuple[TnpCandidateRecord, ...]:
        if result.return_code != 0 or result.result_path is None:
            raise ManifestStateError(f"TNP batch 失败: returncode={result.return_code}")
        try:
            raw = json.loads(result.result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ManifestStateError(f"TNP result JSON 无法解析: {error}") from error
        if not isinstance(raw, dict):
            raise ManifestStateError("TNP result 顶层必须是 candidate mapping")
        expected = {candidate_id for candidate_id, _ in request.sequences}
        if set(raw) != expected:
            raise ManifestStateError(
                "TNP result candidate identity 不完整: "
                f"missing={sorted(expected - set(raw))}, "
                f"unexpected={sorted(set(raw) - expected)}"
            )
        records: list[TnpCandidateRecord] = []
        for candidate_id in sorted(expected):
            value = raw[candidate_id]
            if not isinstance(value, dict) or not value:
                raise ManifestStateError(f"TNP candidate={candidate_id} 结果为空")
            flags = value.get("Flags")
            if not isinstance(flags, dict) or set(flags) != _FLAG_KEYS:
                raise ManifestStateError(f"TNP candidate={candidate_id} flags 不完整")
            total_cdr_length = value.get("Total CDR Length")
            cdr3_length = value.get("CDR3 Length")
            cdr3_compactness = value.get("CDR3 Compactness")
            psh = value.get("PSH")
            ppc = value.get("PPC")
            pnc = value.get("PNC")
            if (
                isinstance(total_cdr_length, bool)
                or not isinstance(total_cdr_length, int)
                or isinstance(cdr3_length, bool)
                or not isinstance(cdr3_length, int)
            ):
                raise ManifestStateError(f"TNP candidate={candidate_id} CDR length 不是整数")
            numeric_values = (cdr3_compactness, psh, ppc, pnc)
            if any(
                isinstance(metric, bool)
                or not isinstance(metric, (int, float))
                or not math.isfinite(float(metric))
                for metric in numeric_values
            ):
                raise ManifestStateError(f"TNP candidate={candidate_id} 包含缺失/非有限 metric")
            assert isinstance(cdr3_compactness, (int, float))
            assert isinstance(psh, (int, float))
            assert isinstance(ppc, (int, float))
            assert isinstance(pnc, (int, float))
            liabilities = self._read_liabilities(
                request.output_directory
                / "Final_Models"
                / f"{candidate_id}_NanoBodyBuilder2_Sequence_Liabilities.json"
            )
            records.append(
                classify_tnp_risk(
                    candidate_id=candidate_id,
                    total_cdr_length=total_cdr_length,
                    cdr3_length=cdr3_length,
                    cdr3_compactness=float(cdr3_compactness),
                    psh=float(psh),
                    ppc=float(ppc),
                    pnc=float(pnc),
                    flags={str(key): str(flag) for key, flag in flags.items()},
                    liabilities=liabilities,
                )
            )
        return tuple(records)

    @staticmethod
    def _read_liabilities(path: Path) -> tuple[SequenceLiability, ...]:
        if not path.is_file():
            raise ManifestStateError(f"TNP liability file 缺失: {path}")
        results: list[SequenceLiability] = []
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = csv.DictReader(handle)
                if rows.fieldnames != ["chain", "position", "aa", "liability"]:
                    raise ManifestStateError("TNP liability CSV header 不符合固定格式")
                for row in rows:
                    name = row["liability"]
                    if name not in _LIABILITY_NAMES:
                        continue
                    position_text = row["position"].strip()
                    numeric = "".join(
                        character for character in position_text if character.isdigit()
                    )
                    if not numeric:
                        raise ManifestStateError(f"TNP IMGT position 无法解析: {position_text}")
                    position = int(numeric)
                    results.append(
                        SequenceLiability(
                            liability_id=_LIABILITY_NAMES[name],
                            name=name,
                            sequence_start=position,
                            sequence_end=position,
                            matched_sequence=row["aa"],
                            evidence_scope="tnp-cdr-or-vernier",
                            numbering="imgt",
                            chain=row["chain"],
                            numbering_label=position_text,
                        )
                    )
        except (OSError, UnicodeDecodeError, csv.Error) as error:
            raise ManifestStateError(f"TNP liability CSV 无法解析: {error}") from error
        return tuple(
            sorted(
                results,
                key=lambda item: (
                    item.chain or "",
                    item.sequence_start,
                    item.liability_id,
                ),
            )
        )
