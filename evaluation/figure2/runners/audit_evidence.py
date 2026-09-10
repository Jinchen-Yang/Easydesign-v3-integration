"""Verify portable raw evidence, all CSV references, and frozen source bytes.

This audit does not certify biological validity or make diagnostics main-eligible.
"""
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "evaluation/figure2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    errors = []
    counts = {"source_files": 0, "episode_receipts": 0, "raw_artifacts": 0, "scientific_artifacts": 0, "retrieval_files": 0}
    frozen = json.loads((EVAL / "provenance/freeze.json").read_text())
    for relative, expected in frozen["source_files"].items():
        if not (ROOT / relative).is_file() or sha(ROOT / relative) != expected:
            errors.append("frozen-source:" + relative)
        counts["source_files"] += 1
    for relative, expected in frozen["config_files"].items():
        if sha(EVAL / relative) != expected:
            errors.append("frozen-config:" + relative)
    for episode_file in sorted((EVAL / "results/raw").glob("*/*/episode.json")):
        episode = json.loads(episode_file.read_text())
        counts["episode_receipts"] += 1
        base = episode_file.parent
        artifact_manifest = base / "artifact-manifest.json"
        if artifact_manifest.exists():
            if sha(artifact_manifest) != episode["output_manifest_sha256"]:
                errors.append("episode-manifest:" + str(episode_file.relative_to(EVAL)))
            for relative, expected in json.loads(artifact_manifest.read_text()).items():
                artifact = base / relative
                if not artifact.is_file() or sha(artifact) != expected:
                    errors.append("raw-artifact:" + str(artifact.relative_to(EVAL)))
                counts["raw_artifacts"] += 1
        projects = base / "project-artifacts.json"
        if projects.exists():
            for relative, expected in json.loads(projects.read_text()).items():
                artifact = EVAL / "provenance/scientific-artifacts" / relative
                if not artifact.is_file() or sha(artifact) != expected:
                    errors.append("scientific-artifact:" + relative)
                counts["scientific_artifacts"] += 1
        if "decision_probe" in episode["method"]:
            for path, expected in [(base / "prompt.txt", episode["prompt_sha256"]),
                                   (EVAL / "configs/decision_cases.json", episode["casefile_sha256"])]:
                if sha(path) != expected:
                    errors.append("agent-input:" + str(path.relative_to(EVAL)))
            if episode.get("skill_sha256") and sha(base / "task/RESEARCH_SKILL.md") != episode["skill_sha256"]:
                errors.append("agent-skill:" + episode["run_id"])
    for receipt in (EVAL / "fixtures/targets").rglob("*.receipt.json"):
        source = receipt.with_name(receipt.name.removesuffix(".receipt.json"))
        expected = json.loads(receipt.read_text())["sha256"]
        if sha(source) != expected:
            errors.append("retrieval:" + str(source.relative_to(EVAL)))
        counts["retrieval_files"] += 1
    for csvpath in EVAL.glob("*.csv"):
        with csvpath.open() as handle:
            reader = csv.DictReader(handle)
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                errors.append("duplicate-csv-columns:" + csvpath.name)
            for row in reader:
                if None in row:
                    errors.append("malformed-csv:" + csvpath.name)
                if row.get("main_figure_eligible", "").lower() == "true":
                    errors.append("diagnostic-main-leak:" + csvpath.name)
    eval_manifest = json.loads((EVAL / "EVAL_MANIFEST.json").read_text())
    for relative, expected in eval_manifest["data_files"].items():
        if sha(EVAL / relative) != expected:
            errors.append("derived-file:" + relative)
    payload = {"audited_at": datetime.now(timezone.utc).isoformat(), "status": "passed" if not errors else "failed", "counts": counts, "errors": errors,
               "scope": "byte integrity and diagnostic/main segregation only; no biological or scientific outcome certification"}
    (EVAL / "provenance/EVIDENCE_INTEGRITY_AUDIT.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
