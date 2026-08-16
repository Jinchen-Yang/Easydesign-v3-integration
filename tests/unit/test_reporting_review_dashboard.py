from __future__ import annotations

import http.client
import shutil
import threading
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.core import ArtifactRef, ExecutionStatus, dump_model
from easydesign.reporting import (
    ReviewDashboardManifest,
    ReviewDashboardPresentationOverride,
    ReviewDashboardReport,
    create_review_dashboard_server,
    export_review_dashboard,
    verify_review_dashboard,
)
from easydesign.reporting.review_models import ReviewStructureRoute


def _artifact(
    root: Path,
    relative: str,
    artifact_id: str,
    file_format: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=artifact_id,
        role="review-dashboard-report",
        file_format=file_format,
    )


def _report_fixture(tmp_path: Path) -> tuple[Path, Path]:
    run_root = tmp_path / "run"
    report_root = tmp_path / "report"
    run_root.mkdir(parents=True)
    (run_root / "structures").mkdir()
    structure = run_root / "structures" / "candidate.cif"
    structure.write_text("data_test\n#\n", encoding="utf-8")
    structure_ref = _artifact(
        run_root,
        "structures/candidate.cif",
        "candidate-structure",
        "mmcif",
    )
    (report_root / "assets").mkdir(parents=True)
    static = files("easydesign.reporting").joinpath("static", "review_dashboard")
    for source, destination in (
        ("index.html", "index.html"),
        ("review-dashboard.css", "assets/review-dashboard.css"),
        ("review-dashboard.js", "assets/review-dashboard.js"),
        ("vendor/3dmol/3Dmol-min.js", "assets/3Dmol-min.js"),
        ("vendor/3dmol/LICENSE", "assets/3DMOL_LICENSE.txt"),
    ):
        target = report_root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        with static.joinpath(*Path(source).parts).open("rb") as read, target.open("wb") as write:
            shutil.copyfileobj(read, write)
    report = ReviewDashboardReport(
        report_kind="stage07",
        project_id="project-a",
        run_id="run-a",
        stage_id="07-final-filtering-and-selection",
        generated_at=datetime.now(UTC),
        title="测试报告",
        tabs=("设计路线比较", "全局候选审查", "双模式预测结果"),
        source_run_manifest_sha256="1" * 64,
        source_stage_manifest_sha256="2" * 64,
        source_profile_id="test-profile",
        source_profile_sha256="3" * 64,
        requested_review_cohort_size=200,
        actual_review_cohort_size=0,
        candidates=(),
        strategies=(),
        structure_routes=(
            ReviewStructureRoute(
                token=f"structure-{structure_ref.sha256[:24]}",
                artifact=structure_ref,
                mime_type="chemical/x-mmcif",
            ),
        ),
        source_artifacts=(structure_ref,),
    )
    dump_model(report, report_root / "report.json")
    output = tuple(
        _artifact(report_root, relative, artifact_id, file_format)
        for relative, artifact_id, file_format in (
            ("index.html", "review-dashboard-html", "html"),
            ("report.json", "review-dashboard-data", "json"),
            ("assets/review-dashboard.css", "review-dashboard-css", "css"),
            ("assets/review-dashboard.js", "review-dashboard-js", "javascript"),
            ("assets/3Dmol-min.js", "review-dashboard-3dmol-js", "javascript"),
            ("assets/3DMOL_LICENSE.txt", "review-dashboard-3dmol-license", "text"),
        )
    )
    manifest = ReviewDashboardManifest(
        report_id="stage07-review-dashboard",
        revision=1,
        status=ExecutionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        source_run_manifest_sha256="1" * 64,
        source_stage_manifest_sha256="2" * 64,
        source_identity_sha256="4" * 64,
        output_artifacts=output,
    )
    dump_model(manifest, report_root / "report-manifest.json")
    return run_root, report_root


def test_presentation_override_cannot_contain_scientific_rules() -> None:
    with pytest.raises(ValidationError, match="threshold"):
        ReviewDashboardPresentationOverride.model_validate(
            {"title": "允许", "thresholds": {"score": 0.5}}
        )


def test_server_verifies_routes_ranges_mime_and_host(tmp_path: Path) -> None:
    run_root, report_root = _report_fixture(tmp_path)
    dashboard = create_review_dashboard_server(report_root, run_root=run_root, port=0)
    thread = threading.Thread(target=dashboard.serve_forever, daemon=True)
    thread.start()
    port = dashboard.server.server_address[1]
    token = next(
        iter(
            ReviewDashboardReport.model_validate_json(
                (report_root / "report.json").read_text(encoding="utf-8")
            ).structure_routes
        )
    ).token
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port)
        connection.request("GET", f"/structures/{token}", headers={"Range": "bytes=0-3"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader("Content-Type") == "chemical/x-mmcif"
        assert response.getheader("Content-Range").startswith("bytes 0-3/")
        assert response.read() == b"data"
        connection.close()

        foreign = http.client.HTTPConnection("127.0.0.1", port)
        foreign.request("GET", "/", headers={"Host": "example.com"})
        response = foreign.getresponse()
        assert response.status == 421
        response.read()
        foreign.close()

        traversal = http.client.HTTPConnection("127.0.0.1", port)
        traversal.request("GET", "/%2e%2e/report.json")
        response = traversal.getresponse()
        assert response.status == 404
        response.read()
        traversal.close()

        (run_root / "structures" / "candidate.cif").write_text(
            "tampered", encoding="utf-8"
        )
        tampered = http.client.HTTPConnection("127.0.0.1", port)
        tampered.request("GET", f"/structures/{token}")
        response = tampered.getresponse()
        assert response.status == 409
        response.read()
        tampered.close()
    finally:
        dashboard.server.shutdown()
        dashboard.close()
        thread.join(timeout=2)


def test_report_tamper_and_symlink_are_rejected(tmp_path: Path) -> None:
    run_root, report_root = _report_fixture(tmp_path)
    (report_root / "report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(Exception, match="SHA|大小"):
        verify_review_dashboard(report_root)

    run_root, report_root = _report_fixture(tmp_path / "symlink-case")
    original = run_root / "structures" / "candidate.cif"
    real = run_root / "structures" / "real.cif"
    original.rename(real)
    original.symlink_to(real.name)
    with pytest.raises(Exception, match="symlink"):
        create_review_dashboard_server(report_root, run_root=run_root)


def test_portable_export_copies_verified_structures(tmp_path: Path) -> None:
    run_root, report_root = _report_fixture(tmp_path)
    destination = tmp_path / "portable"
    exported = export_review_dashboard(
        report_root,
        run_root=run_root,
        output=destination,
    )
    assert exported == destination
    assert (destination / "export-manifest.json").is_file()
    report = ReviewDashboardReport.model_validate_json(
        (destination / "report.json").read_text(encoding="utf-8")
    )
    assert report.structure_routes[0].artifact.relative_path.startswith("structures/")
    verify_review_dashboard(destination)
    with pytest.raises(Exception, match="已存在"):
        export_review_dashboard(
            report_root,
            run_root=run_root,
            output=destination,
        )
