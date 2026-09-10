"""Copy only manifest-declared files from this benchmark's fresh projects.

Run on the source host after Tier 1 stops. Original episode receipts are never
changed. The portable copies preserve bytes, including original absolute paths.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "evaluation/figure2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    records = []
    for episode_path in sorted((EVAL / "results/raw/tier1").glob("*/episode.json")):
        episode = json.loads(episode_path.read_text())
        run_id = episode["run_id"]
        if not run_id.startswith("fig2-v010-"):
            raise ValueError("Unexpected project outside this benchmark")
        manifest = episode_path.parent / "project-artifacts.json"
        if not manifest.exists():
            continue
        declared = json.loads(manifest.read_text())
        allowed = [ROOT / "workspace" / scope / run_id for scope in ("projects", "runs")]
        copied = {}
        for relative, expected in declared.items():
            source = ROOT / relative
            if not any(source.resolve().is_relative_to(base.resolve()) for base in allowed):
                raise ValueError(f"Out-of-scope source: {relative}")
            if not source.is_file() or sha(source) != expected:
                raise ValueError(f"Source artifact changed: {relative}")
            destination = EVAL / "provenance/scientific-artifacts" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if sha(destination) != expected:
                    raise ValueError(f"Existing evidence copy differs: {destination}")
            else:
                shutil.copyfile(source, destination)
            copied[relative] = destination
        prep = episode.get("prepare_response", {})
        remote_manifest = prep.get("manifest")
        stage_refs = []
        if remote_manifest:
            relative = str(Path(remote_manifest).relative_to(ROOT))
            if relative in copied:
                run_manifest = json.loads(copied[relative].read_text())
                stage_refs = run_manifest.get("stage_manifest_refs", [])
        evidence = []
        for relative, path in copied.items():
            if "stage-manifest" in path.name or path.name == "source-error.json":
                try:
                    content = json.loads(path.read_text())
                except ValueError:
                    continue
                evidence.append({"path": str(path.relative_to(EVAL)), "sha256": sha(path), "content": content})
        error_text = json.dumps(evidence, ensure_ascii=False)
        observed_status = episode["status"]
        site_response = episode_path.parent / "05-site-sasa/stdout.txt"
        site_payload = json.loads(site_response.read_text()) if site_response.exists() and site_response.read_text().strip() else {}
        if site_payload.get("status"):
            observed_status = site_payload["status"]
        if episode["status"] == "operational-failed":
            cause = "nonempty-construct-sequence-error" if "canonical amino-acid sequence" in error_text else "operational-failure-see-evidence"
        elif site_payload.get("status") == "awaiting-human-approval":
            cause = "scientific-site-approval-required"
        elif episode.get("scientific_approval_pending") or episode["status"] == "awaiting-human-approval":
            cause = "scientific-identity-or-construct-review"
        else:
            cause = "target-prepared-but-strategy-not-valid" if episode["status"] == "succeeded" else episode["status"]
        detail = {"run_id": run_id, "cause": cause, "original_episode": str(episode_path.relative_to(EVAL)),
                  "original_prepare_status": episode["status"], "final_observed_status": observed_status,
                  "site_scan_response": site_payload,
                  "project_artifact_manifest_sha256": sha(manifest), "copied_file_count": len(copied),
                  "run_manifest_stage_refs": stage_refs, "stage_evidence": evidence,
                  "scope": "post-run evidence copy and failure classification; no original receipt mutation"}
        out = EVAL / "provenance/setup-evidence-v2" / f"{run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(detail, ensure_ascii=False, indent=2) + "\n"
        if out.exists() and out.read_text() != encoded:
            raise ValueError(f"Existing classified evidence differs: {out}")
        if not out.exists():
            with out.open("x") as handle:
                handle.write(encoded)
        records.append({"run_id": run_id, "target_id": episode["target_id"], "status": observed_status,
                        "failure_class": cause, "copied_file_count": len(copied), "evidence": str(out.relative_to(EVAL)), "sha256": sha(out)})
    dest = EVAL / "results/derived/SETUP_FAILURE_CLASSIFICATION.csv"
    with dest.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run_id", "target_id", "status", "failure_class", "copied_file_count", "evidence", "sha256"])
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps({"projects_copied": len(records), "files_copied": sum(row["copied_file_count"] for row in records)}))


if __name__ == "__main__":
    main()
