from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration import runtime_components
from easydesign.orchestration.git_sources import directory_content_sha256
from easydesign.orchestration.runtime_components import (
    AfoTemplatePipelineComponentReceipt,
    install_openfold3_component,
    load_openfold3_bundle,
    runtime_status,
    verify_afo_template_pipeline_component,
)
from easydesign.workspace_context import WorkspaceContext

REQUIRED_ROLES = (
    "alphafold-wheel",
    "environment-requirements",
    "converted-weight",
    "runner-script",
    "license",
    "notice",
    "model-card",
    "conversion-manifest",
    "checksums",
    "smoke-input",
    "validation-receipt",
)


def test_python312_is_installed_by_pinned_uv_inside_clone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: python312-test",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    managed_python = (
        context.runtime_root
        / "tools/uv-python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
    )
    find_count = 0
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    monkeypatch.delenv("EASYDESIGN_PYTHON312", raising=False)
    monkeypatch.setattr(
        runtime_components.shutil,
        "which",
        lambda name: "/fixture/uv" if name == "uv" else "/global/python3.12",
    )

    def fake_run(
        argv: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal find_count
        environment = kwargs.get("env")
        calls.append(
            (
                tuple(argv),
                environment if isinstance(environment, dict) else None,
            )
        )
        if argv == ["/fixture/uv", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "uv 0.12.3\n", "")
        if argv[:3] == ["/fixture/uv", "python", "find"]:
            find_count += 1
            return subprocess.CompletedProcess(
                argv,
                1 if find_count == 1 else 0,
                "" if find_count == 1 else f"{managed_python}\n",
                "",
            )
        if argv[:3] == ["/fixture/uv", "python", "install"]:
            managed_python.parent.mkdir(parents=True, exist_ok=True)
            managed_python.write_text("fixture", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "installed\n", "")
        if argv[0] == str(managed_python):
            return subprocess.CompletedProcess(argv, 0, "3.12.13\n", "")
        raise AssertionError(argv)

    monkeypatch.setattr(runtime_components.subprocess, "run", fake_run)

    selected = runtime_components._python312(context, context.child_environment())

    assert selected == managed_python.resolve()
    install_call = next(item for item in calls if item[0][1:3] == ("python", "install"))
    assert install_call[0][-1] == "3.12.13"
    assert install_call[1] is not None
    assert install_call[1]["UV_PYTHON_INSTALL_DIR"] == str(
        context.runtime_root / "tools/uv-python"
    )


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    evidence_root = bundle / "metadata/evidence"
    evidence_root.mkdir(parents=True)
    evidence_refs: dict[str, dict[str, object]] = {}
    for name in ("conversion-a", "conversion-b", "converter-tests", "harness", "inventory"):
        path = evidence_root / f"{name}.log"
        path.write_text(f"{name}: verified\n", encoding="utf-8")
        evidence_refs[name] = {
            "relative_path": f"evidence/{name}.log",
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    records: list[dict[str, object]] = []
    for index, role in enumerate(REQUIRED_ROLES):
        if role == "runner-script":
            relative = Path("runner/run_alphafold.py")
        elif role == "alphafold-wheel":
            relative = Path("wheelhouse/alphafold3_open-3.1.4.whl")
        elif role == "environment-requirements":
            relative = Path("environment/requirements.txt")
        elif role == "converted-weight":
            relative = Path("model/of3_ported_weights.bin.zst")
        else:
            relative = Path("metadata") / f"{index:02d}-{role}.txt"
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{role}\n", encoding="utf-8")
        records.append(
            {
                "relative_path": relative.as_posix(),
                "role": role,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    for name in evidence_refs:
        path = evidence_root / f"{name}.log"
        records.append(
            {
                "relative_path": path.relative_to(bundle).as_posix(),
                "role": "validation-evidence",
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    by_role = {str(item["role"]): item for item in records}
    runner_tree_sha256 = directory_content_sha256(bundle / "runner")
    weight = bundle / "model/of3_ported_weights.bin.zst"
    validation_receipt = {
        "schema_version": "0.2",
        "backend_version": "3.1.4",
        "runner_commit": "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997",
        "runner_tree_sha256": runner_tree_sha256,
        "raw_checkpoint_sha256": "a" * 64,
        "conversions": [
            {
                "conversion_id": conversion_id,
                "compressed_size_bytes": weight.stat().st_size,
                "compressed_sha256": sha256_file(weight),
                "uncompressed_size_bytes": 833,
                "uncompressed_sha256": "d" * 64,
                "log": evidence_refs[conversion_id],
            }
            for conversion_id in ("conversion-a", "conversion-b")
        ],
        "converter_tests": {
            "command": ["pytest", "converter"],
            "collected": 43,
            "passed": 43,
            "return_code": 0,
            "log": evidence_refs["converter-tests"],
        },
        "verification_harnesses": [
            {
                "harness_id": "pytorch-jax-parity",
                "command": ["python", "verify.py"],
                "return_code": 0,
                "tolerance": 0.001,
                "maximum_relative_error": 0.0001,
                "log": evidence_refs["harness"],
            }
        ],
        "python_version": "3.12.11",
        "pytorch_version": "2.7.1",
        "environment_inventory": evidence_refs["inventory"],
        "generated_at": "2026-08-11T00:00:00Z",
    }
    receipt_path = bundle / Path(str(by_role["validation-receipt"]["relative_path"]))
    receipt_path.write_text(json.dumps(validation_receipt), encoding="utf-8")
    by_role["validation-receipt"]["size_bytes"] = receipt_path.stat().st_size
    by_role["validation-receipt"]["sha256"] = sha256_file(receipt_path)
    manifest = {
        "schema_version": "0.2",
        "release_id": "afo-3-1-4-of3-p2-155k",
        "component_id": "openfold3-p2-af3-jax",
        "backend_id": "openfold3-af3-jax",
        "backend_version": "3.1.4",
        "model_id": "of3-p2-155k",
        "python_version": "3.12",
        "code_license": "Apache-2.0",
        "template_mode": "disabled",
        "raw_checkpoint_sha256": "a" * 64,
        "converted_weight_sha256": by_role["converted-weight"]["sha256"],
        "wheel_sha256": by_role["alphafold-wheel"]["sha256"],
        "adapter_contract_version": "openfold3-af3-jax-cli-v1",
        "runner_commit": "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997",
        "runner_tree_sha256": runner_tree_sha256,
        "environment_lock_sha256": by_role["environment-requirements"]["sha256"],
        "conversion_receipt_sha256": by_role["validation-receipt"]["sha256"],
        "files": records,
    }
    (bundle / "release-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return bundle


def test_load_bundle_verifies_complete_inventory(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)

    selected, manifest = load_openfold3_bundle(bundle)

    assert selected == bundle
    assert manifest.runner_commit == "bc32b22ff5902e3daffd5d1f7203d7f2ab6cb997"
    assert len(manifest.files) == len(REQUIRED_ROLES) + 5


def test_load_bundle_fails_closed_after_file_corruption(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    (bundle / "model/of3_ported_weights.bin.zst").write_text(
        "corrupted\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="大小不一致|SHA-256"):
        load_openfold3_bundle(bundle)


def test_load_bundle_rejects_missing_required_role(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / "release-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["files"] = [
        item for item in payload["files"] if item["role"] != "license"
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="无法校验"):
        load_openfold3_bundle(bundle)


def test_load_bundle_explicitly_rejects_legacy_schema_01(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    manifest_path = bundle / "release-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "0.1"
    payload["backend_version"] = "3.1.3"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="schema 0.1/3.1.3"):
        load_openfold3_bundle(bundle)


def test_install_preflight_failure_records_quarantine_without_profile_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: runtime-component-test",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))
    bundle = _bundle(tmp_path)
    (bundle / "model/of3_ported_weights.bin.zst").write_text(
        "corrupted\n", encoding="utf-8"
    )

    with pytest.raises(ConfigurationError, match="大小不一致|SHA-256"):
        install_openfold3_component(bundle)

    receipts = tuple((tmp_path / "runtime/quarantine").glob("*.json"))
    assert len(receipts) == 1
    assert not (tmp_path / "runtime/profile.yaml").exists()


def test_runtime_status_is_readable_before_first_component_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: fresh-clone",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYDESIGN_WORKSPACE", str(tmp_path))

    status = runtime_status()

    assert status.openfold3 is None
    assert status.model_dump() == {"openfold3": None, "openfold3_installed": ()}
    assert not (tmp_path / "runtime/profile.yaml").exists()


def test_template_pipeline_component_is_clone_local_and_checksum_pinned(
    tmp_path: Path,
) -> None:
    (tmp_path / "easydesign-workspace.yaml").write_text(
        "\n".join(
            (
                'schema_version: "0.1"',
                "workspace_id: template-component-test",
                "runtime_root: runtime",
                "projects_root: workspace/projects",
                "runs_root: workspace/runs",
                "archives_root: workspace/archives",
                "",
            )
        ),
        encoding="utf-8",
    )
    context = WorkspaceContext.from_root(tmp_path)
    context.ensure_layout()
    component = context.runtime_root / "models/afo-template-pipeline-v1/test"
    tools = component / "tools"
    database = component / "databases/mmcif_files"
    tools.mkdir(parents=True)
    database.mkdir(parents=True)
    binaries: dict[str, Path] = {}
    for name in ("hmmbuild", "hmmsearch", "hmmalign"):
        path = tools / name
        path.write_text(name + "\n", encoding="utf-8")
        binaries[name] = path
    seqres = component / "databases/pdb_seqres_2022_09_28.fasta"
    seqres.write_text(">x\nACD\n", encoding="utf-8")
    disabled_search = tools / "disabled-msa-search"
    disabled_search.write_text("disabled\n", encoding="utf-8")
    unused_database = component / "databases/unused-msa-database.sentinel"
    unused_database.write_text("unused\n", encoding="utf-8")
    cif = database / "x.cif"
    cif.write_text("data_x\n#\n", encoding="utf-8")
    manifest = component / "mmcif-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "database_version": "pdb-2022-09-28",
                "file_count": 1,
                "files": [
                    {
                        "relative_path": "x.cif",
                        "size_bytes": cif.stat().st_size,
                        "sha256": sha256_file(cif),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    receipt = AfoTemplatePipelineComponentReceipt(
        installed_at="2026-09-26T00:00:00Z",
        hmmbuild=binaries["hmmbuild"],
        hmmbuild_sha256=sha256_file(binaries["hmmbuild"]),
        hmmsearch=binaries["hmmsearch"],
        hmmsearch_sha256=sha256_file(binaries["hmmsearch"]),
        hmmalign=binaries["hmmalign"],
        hmmalign_sha256=sha256_file(binaries["hmmalign"]),
        hmmer_version="3.4",
        disabled_msa_search_executable=disabled_search,
        disabled_msa_search_executable_sha256=sha256_file(disabled_search),
        unused_msa_database_sentinel=unused_database,
        unused_msa_database_sentinel_sha256=sha256_file(unused_database),
        seqres_database=seqres,
        seqres_database_sha256=sha256_file(seqres),
        seqres_database_version="pdb-seqres-2022-09-28",
        mmcif_database=database,
        mmcif_manifest=manifest,
        mmcif_manifest_sha256=sha256_file(manifest),
        mmcif_database_version="pdb-2022-09-28",
        mmcif_file_count=1,
        max_template_date="2022-09-28",
        source_urls=("https://example.test/seqres", "https://example.test/mmcif"),
    )
    receipt_path = component / "component.json"
    receipt_path.write_text(receipt.model_dump_json(), encoding="utf-8")

    observed = verify_afo_template_pipeline_component(
        receipt_path,
        context=context,
    )
    assert observed.mmcif_file_count == 1

    seqres.write_text(">x\nAAA\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="identity 已变化"):
        verify_afo_template_pipeline_component(receipt_path, context=context)
