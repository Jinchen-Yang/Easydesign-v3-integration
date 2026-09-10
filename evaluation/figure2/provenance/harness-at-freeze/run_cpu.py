"""Append-only Figure 2 CPU evaluation; never launches a generation backend."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "evaluation/figure2"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def put(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
    return path


def rows(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def run_cmd(argv, output, timeout=180, env=None):
    started = now()
    tick = time.monotonic()
    extra = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="2")
    if env:
        extra.update(env)
    try:
        result = subprocess.run(argv, cwd=ROOT, env=extra, capture_output=True, text=True, timeout=timeout)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
        stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
        code = 124
    except OSError as exc:
        stdout, stderr, code = "", str(exc), 127
    put(output / "stdout.txt", stdout)
    put(output / "stderr.txt", stderr)
    receipt = {"command": argv, "started_at": started, "ended_at": now(), "wall_time_s": time.monotonic() - tick,
               "returncode": code, "stdout_sha256": sha(output / "stdout.txt"), "stderr_sha256": sha(output / "stderr.txt"),
               "cuda_visible_devices": "", "cpu_threads_limit": 2, "timeout_seconds": timeout}
    put(output / "command.json", receipt)
    return receipt, stdout


def source_inventory():
    names = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    scopes = ("src/", "tests/", ".agents/", "scripts/", "config/", "environments/", "docs/", "web/")
    root_names = {"pyproject.toml", "uv.lock", "AGENTS.md", "README.md", "Makefile", "DATA_SAFETY.md", "easydesign-workspace.yaml"}
    return {name: sha(ROOT / name) for name in sorted(set(names)) if name and (name.startswith(scopes) or name in root_names) and (ROOT / name).is_file()}


def freeze():
    for name in ("configs", "manifests", "runners", "metrics", "fixtures", "results/raw", "results/derived", "reports", "plots", "provenance"):
        (EVAL / name).mkdir(parents=True, exist_ok=True)
    code = source_inventory()
    frozen = {"benchmark_version": "0.1.0", "frozen_at": now(), "repository_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "dirty_status": subprocess.check_output(["git", "status", "--short", "--branch"], cwd=ROOT, text=True),
              "source_files": code, "source_tree_sha256": digest(code), "config_files": {str(p.relative_to(EVAL)): sha(p) for p in sorted((EVAL / "configs").glob("*")) if p.is_file()},
              "harness_files": {str(p.relative_to(EVAL)): sha(p) for p in sorted((EVAL / "runners").glob("*.py"))},
              "architecture_mutation_allowed": False, "gpu_execution_authorized": False}
    put(EVAL / "provenance/freeze.json", frozen)
    hardware = {"recorded_at": now(), "platform": platform.platform(), "python": sys.version, "cpu_count": os.cpu_count(), "disk": dict(zip(("total_bytes", "used_bytes", "free_bytes"), shutil.disk_usage(ROOT))), "gpu": []}
    rc, out = run_cmd(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,driver_version", "--format=csv"], EVAL / "provenance/hardware-command", timeout=15)
    hardware["gpu"] = out.strip().splitlines()
    put(EVAL / "provenance/hardware.json", hardware)
    registry = {}
    for category in ("environments", "assets"):
        registry[category] = [{"path": str(p.relative_to(ROOT)), "sha256": sha(p), "receipt": json.loads(p.read_text())} for p in sorted((ROOT / "runtime/state/registries" / category).glob("*.json"))]
    put(EVAL / "provenance/runtime-registry-snapshot.json", registry)
    print(json.dumps({"freeze": frozen["source_tree_sha256"], "n_source_files": len(code)}), flush=True)


def verify_freeze():
    frozen = json.loads((EVAL / "provenance/freeze.json").read_text())
    if source_inventory() != frozen["source_files"]:
        raise RuntimeError("Frozen production source changed; new benchmark version required")
    for relative, expected in frozen["config_files"].items():
        if sha(EVAL / relative) != expected:
            raise RuntimeError(f"Frozen protocol changed: {relative}")
    return frozen


def tier0():
    frozen = verify_freeze()
    cases = json.loads((EVAL / "configs/fault_cases.json").read_text())
    order = [(rep, case) for rep in range(1, 4) for case in cases]
    random.Random(20260906).shuffle(order)
    for rep, case in order:
        episode = f"t0-{case['id']}-r{rep}"
        destination = EVAL / "results/raw/tier0" / episode
        if (destination / "episode.json").exists():
            continue
        destination.mkdir(parents=True, exist_ok=False)
        xml_path = destination / "pytest.xml"
        command = [sys.executable, "-m", "pytest", "-q", case["node"], "--tb=short", "-o", "addopts=", "-o", "cache_dir=runtime/cache/figure2/pytest", "--basetemp", str(destination / "fixture-work"), "--junitxml", str(xml_path)]
        rc, _ = run_cmd(command, destination / "process", timeout=90)
        testcases = []
        if xml_path.exists():
            for item in ET.parse(xml_path).iter("testcase"):
                testcases.append({"name": item.attrib.get("name"), "time": item.attrib.get("time"), "outcome": "failed" if item.find("failure") is not None or item.find("error") is not None else "skipped" if item.find("skipped") is not None else "passed"})
        artifact_files = {str(p.relative_to(destination)): sha(p) for p in sorted(destination.rglob("*")) if p.is_file()}
        outcome = "passed" if rc["returncode"] == 0 and testcases and all(t["outcome"] == "passed" for t in testcases) else "failed"
        put(destination / "artifact-manifest.json", artifact_files)
        payload = {"run_id": episode, "tier": 0, "method": "easydesign_contract_probe", "comparator_status": "not-an-agent-comparison", "case_id": case["id"], "panel": case["panel"], "replicate_id": rep, "replication_kind": "technical-replay", "node": case["node"], "testcases": testcases, "status": outcome, "data_origin": "real_fixture_fault_test", "source_tree_sha256": frozen["source_tree_sha256"], "prompt_sha256": digest(case), "plan_sha256": digest({"case": case, "replicate": rep}), "output_manifest_sha256": sha(destination / "artifact-manifest.json"), **rc}
        put(destination / "episode.json", payload)
        print(f"{episode}: {outcome}", flush=True)


def retrieve(url, path):
    if path.exists():
        return path.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": "EasyDesign-Figure2/0.1 (public structural benchmark)"})
    started = now()
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = response.read()
        receipt = {"requested_url": url, "resolved_url": response.url, "http_status": response.status, "retrieved_at": now(), "started_at": started, "content_type": response.headers.get("Content-Type"), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    put(path.with_suffix(path.suffix + ".receipt.json"), receipt)
    return payload


def acquire():
    verify_freeze()
    from easydesign.backends.target_sources.structure import inventory_structure
    for target in rows(EVAL / "configs/target_selection.csv"):
        root = EVAL / "fixtures/targets" / target["target_id"]
        if (root / "target-receipt.json").exists():
            continue
        root.mkdir(parents=True, exist_ok=True)
        record = {**target, "retrieval_started_at": now(), "status": "unresolved", "selected_chain": None}
        try:
            pdb = target["pdb_id"]
            retrieve(f"https://files.rcsb.org/download/{pdb}.cif", root / "source.cif")
            entry = json.loads(retrieve(f"https://data.rcsb.org/rest/v1/core/entry/{pdb}", root / "entry.json"))
            matching = []
            entities = []
            for entity_id in entry["rcsb_entry_container_identifiers"]["polymer_entity_ids"]:
                entity = json.loads(retrieve(f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb}/{entity_id}", root / f"entity-{entity_id}.json"))
                ids = entity.get("rcsb_polymer_entity_container_identifiers", {})
                refs = ids.get("reference_sequence_identifiers", [])
                uniprots = [r.get("database_accession") for r in refs if r.get("database_name") == "UniProt"]
                if target["uniprot"] and target["uniprot"] in uniprots:
                    matching.extend(ids.get("auth_asym_ids", []))
                if entity.get("entity_poly", {}).get("type") == "polypeptide(L)":
                    entities.append(ids.get("auth_asym_ids", []))
            # A synthetic target without an accession is selected only when there is one protein entity.
            if not target["uniprot"] and len(entities) == 1:
                matching = entities[0]
            if not matching:
                raise RuntimeError("RCSB entity/accession identity is unresolved; no closest-match fallback")
            chain = sorted(matching)[0]
            inventory = inventory_structure(root / "source.cif")
            info = next(c for c in inventory.chains if c.author_chain_id == chain)
            record.update(selected_chain=chain, equivalent_entity_chains=sorted(matching), observed_sequence_sha256=hashlib.sha256(info.sequence.encode()).hexdigest(), residue_count=info.residue_count,
                          structure_sha256=sha(root / "source.cif"), entry_title=entry.get("struct", {}).get("title"), coordinate_model_ids=inventory.model_ids,
                          chain_selection_policy="lexicographically first auth chain of exact RCSB accession-matched polymer entity; construct/assembly review still required", status="acquired-identity-bound")
            if target["uniprot"]:
                retrieve(f"https://rest.uniprot.org/uniprotkb/{target['uniprot']}.fasta", root / "canonical.fasta")
                record["canonical_fasta_sha256"] = sha(root / "canonical.fasta")
        except Exception as exc:
            record.update(status="acquisition-failed", failure_reason=f"{type(exc).__name__}: {exc}")
        record["retrieval_ended_at"] = now()
        put(root / "target-receipt.json", record)
        print(f"acquire {target['target_id']}: {record['status']}", flush=True)


def tier1(limit=None):
    frozen = verify_freeze()
    targets = rows(EVAL / "configs/target_selection.csv")
    order = [(rep, target) for rep in range(1, 4) for target in targets]
    random.Random(20260907).shuffle(order)
    if limit:
        order = order[:limit]
    for rep, target in order:
        run_id = f"fig2-v010-{target['target_id']}-r{rep}"
        dest = EVAL / "results/raw/tier1" / run_id
        if (dest / "episode.json").exists():
            continue
        target_receipt = json.loads((EVAL / "fixtures/targets" / target["target_id"] / "target-receipt.json").read_text())
        dest.mkdir(parents=True, exist_ok=False)
        payload = {"run_id": run_id, "target_id": target["target_id"], "target_family": target["target_family"], "tier": 1, "method": "easydesign_deterministic_setup_probe", "benchmark_mode": "controlled-setup-only", "replicate_id": rep,
                   "replication_kind": "technical-replay", "data_origin": "real_run", "source_tree_sha256": frozen["source_tree_sha256"], "start_time": now(), "target_input_sha256": target_receipt.get("structure_sha256"), "executable_project": False, "backend_validated_strategy": False,
                   "operational_intervention_count": 0, "scientific_approval_count": 0, "candidate_count": 0, "gpu_hours": 0}
        tick = time.monotonic()
        commands = []
        if target_receipt["status"] != "acquired-identity-bound":
            payload.update(status="blocked-input", failure_reason=target_receipt.get("failure_reason"))
        else:
            project = ROOT / "workspace/projects" / run_id
            target_path = EVAL / "fixtures/targets" / target["target_id"] / "source.cif"
            cli = str(ROOT / ".venv/bin/easydesign")
            init = [cli, "project", "init", str(project), "--target", str(target_path), "--chain", target_receipt["selected_chain"], "--target-id", target["target_id"], "--json"]
            if target["uniprot"]:
                init += ["--identity-uniprot", target["uniprot"]]
            rc, _ = run_cmd(init, dest / "01-init", timeout=120)
            commands.append(rc)
            if rc["returncode"] == 0:
                rc, status_before = run_cmd([cli, "project", "status", str(project), "--json"], dest / "02-status", timeout=120)
                commands.append(rc)
                # No prediction backend is selected: the production CLI must stop if prediction is required.
                rc, prepared = run_cmd([cli, "target", "prepare", str(project), "--json"], dest / "03-prepare", timeout=240)
                commands.append(rc)
                payload["prepare_returncode"] = rc["returncode"]
                try:
                    prepared_json = json.loads(prepared)
                    payload["prepare_response"] = prepared_json
                    payload["status"] = prepared_json.get("status", "unknown")
                except ValueError:
                    payload["status"] = "operational-failure"
                rc, state = run_cmd([cli, "project", "status", str(project), "--json"], dest / "04-status", timeout=120)
                commands.append(rc)
                try:
                    state_json = json.loads(state)
                    payload["final_project_status"] = state_json
                    payload["scientific_approval_pending"] = any(a.get("approval_required") for a in state_json.get("next_actions", []))
                except ValueError:
                    pass
                # Attempt the supplied product draft through the actual validator; no synthetic approval.
                rc, validated = run_cmd([cli, "strategy", "validate", str(project), "--config", "strategy-draft.yaml", "--json"], dest / "05-validate-initial-draft", timeout=90)
                commands.append(rc)
                payload["initial_strategy_validation_returncode"] = rc["returncode"]
                payload["initial_strategy_validation"] = validated
                if rc["returncode"] == 0:
                    try:
                        validated_json = json.loads(validated)
                        payload["backend_validated_strategy"] = validated_json.get("status") == "validated"
                        payload["executable_project"] = payload["backend_validated_strategy"]
                    except ValueError:
                        pass
                payload["failure_reason"] = "Executable-plan endpoint not reached: identity/site review and researcher-approved foundation are required before a real strategy can validate. See individual command receipts."
                # Snapshot only artifacts from this benchmark's new project, never old study results.
                project_manifest = {str(p.relative_to(ROOT)): sha(p) for p in sorted(project.rglob("*")) if p.is_file()}
                runs_root = ROOT / "workspace/runs" / run_id
                if runs_root.exists():
                    project_manifest.update({str(p.relative_to(ROOT)): sha(p) for p in sorted(runs_root.rglob("*")) if p.is_file()})
                put(dest / "project-artifacts.json", project_manifest)
            else:
                payload.update(status="init-failed", failure_reason="Actual project init command failed; see stderr")
        payload.update(end_time=now(), wall_time_s=time.monotonic() - tick, commands=commands, prompt_sha256=digest(target), plan_sha256=digest({"target": target, "replicate": rep, "sequence": ["init", "status", "prepare", "status", "validate-initial-draft"]}))
        manifest = {str(p.relative_to(dest)): sha(p) for p in sorted(dest.rglob("*")) if p.is_file()}
        put(dest / "artifact-manifest.json", manifest)
        payload["output_manifest_sha256"] = sha(dest / "artifact-manifest.json")
        put(dest / "episode.json", payload)
        print(f"tier1 {run_id}: {payload['status']}; executable={payload['executable_project']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["freeze", "verify", "tier0", "acquire", "tier1"])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.phase == "freeze":
        freeze()
    elif args.phase == "verify":
        print(json.dumps({"source_unchanged": True, "freeze": verify_freeze()["source_tree_sha256"]}))
    elif args.phase == "tier0":
        tier0()
    elif args.phase == "acquire":
        acquire()
    else:
        tier1(args.limit)
