"""Bounded real-source acceptance inputs. No model inference, approval or GPU work.

Run with the locked Agent environment from the active engineering workspace. Every run
creates new source/project directories; input/deposition bytes and retrieval receipts remain.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from easydesign.agent.evidence_research import EvidenceResearch, ResearchQuery
from easydesign.agent.phase2 import Phase2Bridge
from easydesign.agent.session_store import SessionStore
from easydesign.backends.target_sources.remote import ScientificHttpClient, rcsb_mmcif
from easydesign.orchestration.research import initialize_research_project
from easydesign.workspace_context import WorkspaceContext


def main() -> None:
    context = WorkspaceContext.discover()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory = context.runtime_root / "tmp" / f"phase21-real-sources-{stamp}"
    directory.mkdir(exist_ok=False)
    report = {"evidence_type": "REAL SOURCE RETRIEVAL", "gpu_jobs": 0, "cases": []}
    cases = [
        ("soluble", "1MEL", "P00698", "8784355", "lysozyme camel antibody inhibition", None),
        (
            "gpcr",
            "3P0G",
            "P07550",
            "21228869",
            "beta2 adrenoceptor nanobody active state",
            "adrb2_human",
        ),
    ]
    for name, pdb, accession, pmid, terms, gpcr in cases:
        evidence_dir = directory / name
        evidence_dir.mkdir()
        with ScientificHttpClient(
            evidence_dir=evidence_dir, max_attempts=1, connect_timeout=10, read_timeout=30
        ) as client:
            structure = rcsb_mmcif(client, pdb)
            (evidence_dir / "structure-retrieval.json").write_text(
                structure.record.model_dump_json(indent=2)
            )
        project = context.projects_root / f"phase21-{name}-{stamp}"
        initialize_research_project(project_root=project, target=structure.artifact_path)
        store = SessionStore(project)
        bridge = Phase2Bridge(project, f"sources-{name}", store)
        store.begin_execution(bridge.thread, f"Audit the real {name} evidence for {pdb}")
        worker = EvidenceResearch(bridge)
        queries = [
            ResearchQuery(
                topic="identity",
                question="Which canonical sequence and features are reported?",
                operation="uniprot-record",
                identifier=accession,
            ),
            ResearchQuery(
                topic="structure-complex",
                question="What construct and partners are deposited?",
                operation="structure-record",
                identifier=pdb,
            ),
            ResearchQuery(
                topic="function",
                question="What does the deposition's primary paper establish?",
                operation="primary-record",
                identifier=pmid,
            ),
            ResearchQuery(
                topic="epitope",
                question="What other primary evidence or competing mechanism exists?",
                operation="literature-search",
                query=terms,
            ),
        ]
        if gpcr:
            queries.append(
                ResearchQuery(
                    topic="state",
                    question="What state, topology and ligand evidence exists?",
                    operation="gpcrdb-context",
                    identifier=gpcr,
                )
            )
        outcomes = []
        for query in queries:
            result = worker.acquire(query, role="target")
            outcomes.append(
                {
                    "operation": query.operation,
                    "status": result["status"],
                    "cards": len(result["cards"]),
                    "errors": result["errors"],
                }
            )
            print(name, query.operation, outcomes[-1], flush=True)
        snapshot = worker.snapshot()
        (evidence_dir / "research-snapshot.json").write_text(json.dumps(snapshot, indent=2))
        report["cases"].append(
            {
                "case": name,
                "project": str(project),
                "source_pdb": pdb,
                "queries": outcomes,
                "snapshot": str(evidence_dir / "research-snapshot.json"),
            }
        )
        store.close()
        (directory / "report.json").write_text(json.dumps(report, indent=2))
    print(directory / "report.json", flush=True)


if __name__ == "__main__":
    main()
