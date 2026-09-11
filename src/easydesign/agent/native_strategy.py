"""Trusted expert inputs; original native YAML bytes pass unchanged to the old compiler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import ArtifactRef, sha256_file
from easydesign.orchestration.research import _artifact, load_strategy
from easydesign.stages.s03_boltzgen_configuration.compiler import EXPECTED_ASSET_SHA256

from .contracts import AgentBoundaryError
from .session_store import confined, identity


def labels(value: Any) -> set[int]:
    if not isinstance(value, str):
        raise AgentBoundaryError("Native residue selection requires explicit numeric labels")
    result: set[int] = set()
    try:
        for piece in value.split(","):
            ends = [int(v) for v in piece.split("..")]
            if len(ends) > 2 or ends[0] < 1 or ends[-1] < ends[0] or ends[-1] > 10000:
                raise ValueError
            result.update(range(ends[0], ends[-1] + 1))
    except ValueError as exc:
        raise AgentBoundaryError("Native residue selection is invalid") from exc
    return result


def validate_native(bridge: Any, path: Path) -> tuple[Any, dict[str, Any]]:
    strategy = load_strategy(bridge.project, confined(bridge.project, path))
    if not all(v.native_boltzgen_yaml is not None for v in strategy.variants):
        raise AgentBoundaryError(
            "Expert import requires native variants; standard arms use the standard path"
        )
    site = bridge.approved_site()
    if site is None:
        raise AgentBoundaryError("Native proposal requires an approved Gate 2 hotspot")
    if strategy.foundation not in {"current", site["run_id"]}:
        raise AgentBoundaryError("Native strategy cites a different scientific foundation")
    _, target = _artifact(Path(site["foundation_root"]), "target-structure")
    target_sha = sha256_file(target)
    allowed = set(n for h in site["hotspots"]["hotspot_sets"] for n in h["label_seq_ids"])
    _, facts, _ = bridge.site_facts()
    mapped = {r["label_seq_id"] for r in facts["observed_facts"]["mapping"]}
    input_refs, summaries = [], []
    for variant in strategy.variants:
        source = variant.native_boltzgen_yaml
        assert source is not None
        source = confined(
            bridge.project, source if source.is_absolute() else bridge.project / source
        )
        input_refs.append(bridge._project_ref(source, "expert-native"))
        payload = yaml.safe_load(source.read_text())
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("entities"), list)
            or len(payload["entities"]) != 2
        ):
            raise AgentBoundaryError(
                "Native VHH requires exactly one frozen target and one scaffold entity"
            )
        target_file, scaffold_file = (e.get("file") for e in payload["entities"])
        if not isinstance(target_file, dict) or not isinstance(scaffold_file, dict):
            raise AgentBoundaryError("Native target and scaffold must use file entities")
        if set(target_file) - {"path", "include", "binding_types", "structure_groups"}:
            raise AgentBoundaryError(
                "Native target mutation/exclusion or unknown target directives are blocked"
            )
        target_path = str(target_file.get("path", ""))
        if target_path != "../../assets/target.cif":
            candidate = (
                confined(bridge.project, Path(target_path))
                if Path(target_path).is_absolute()
                else confined(bridge.project, source.parent / target_path)
            )
            if not Path(target_path).is_absolute():
                raise AgentBoundaryError(
                    "Native local inputs must use stable absolute project paths or compil"
                    "er asset references"
                )
            if sha256_file(candidate) != target_sha:
                raise AgentBoundaryError("Native target differs from the approved Target Bundle")
            input_refs.append(bridge._project_ref(candidate, "native-target"))
        include = target_file.get("include")
        if (
            not isinstance(include, list)
            or len(include) != 1
            or include[0].get("chain", {}).get("id") != "A"
        ):
            raise AgentBoundaryError("Native target must bind the prepared design-scope chain A")
        crop = include[0]["chain"].get("res_index")
        crop_labels = labels(crop) if crop else mapped
        if not crop_labels.issubset(mapped):
            raise AgentBoundaryError("Native crop leaves the approved mapping")
        bindings = target_file.get("binding_types", [])
        if len(bindings) != 1 or bindings[0].get("chain", {}).get("id") != "A":
            raise AgentBoundaryError("Native conditioning must explicitly bind approved chain A")
        constraint = bindings[0]["chain"]
        binding = labels(constraint.get("binding"))
        avoid = labels(constraint["not_binding"]) if constraint.get("not_binding") else set()
        if (
            not binding
            or not binding.issubset(allowed)
            or binding & avoid
            or not (binding | avoid).issubset(crop_labels)
        ):
            raise AgentBoundaryError("Native binding/avoid/crop conflicts with approved hotspots")
        scaffold = variant.scaffold_ids[0]
        scaffold_path = str(scaffold_file.get("path", ""))
        if set(scaffold_file) != {"path"}:
            raise AgentBoundaryError(
                "Scaffold modifications must be explicit in the expert scaffold input"
            )
        if scaffold_path != f"../../assets/scaffolds/{scaffold}.yaml":
            candidate = confined(bridge.project, Path(scaffold_path))
            if not Path(scaffold_path).is_absolute() or candidate.suffix != ".yaml":
                raise AgentBoundaryError(
                    "Native scaffold path must be a project YAML or official compiler asset"
                )
            spec = yaml.safe_load(candidate.read_text())
            structure = confined(bridge.project, candidate.parent / spec["path"])
            if sha256_file(structure) != EXPECTED_ASSET_SHA256[f"{scaffold}.cif"]:
                raise AgentBoundaryError(
                    "Native scaffold structure is not the declared official VHH"
                )
            from importlib import resources

            from easydesign.stages.s03_boltzgen_configuration.compiler import ASSET_PACKAGE

            official = yaml.safe_load(
                resources.files(ASSET_PACKAGE).joinpath(f"{scaffold}.yaml").read_text()
            )
            if set(spec) - set(official):
                raise AgentBoundaryError("Unsupported native scaffold directives")
            if spec.get("include") != official["include"]:
                raise AgentBoundaryError(
                    "Native scaffold chain/modality differs from the official VHH"
                )
            design = spec.get("design", [])
            official_loops = labels(official["design"][0]["chain"]["res_index"])
            if not design or any(
                d["chain"].get("id") != "B"
                or not labels(d["chain"].get("res_index")).issubset(official_loops)
                for d in design
            ):
                raise AgentBoundaryError("Native design cannot rewrite the VHH framework")
            for excluded in spec.get("exclude", []):
                chain = excluded.get("chain", {})
                if chain.get("id") != "B" or not labels(chain.get("res_index")).issubset(
                    official_loops
                ):
                    raise AgentBoundaryError("Native exclusion cannot remove the VHH framework")
            for inserted in spec.get("design_insertions", []):
                insertion = inserted.get("insertion", {})
                if (
                    insertion.get("id") != "B"
                    or insertion.get("res_index") not in official_loops
                    or not labels(str(insertion.get("num_residues"))).issubset(set(range(1, 33)))
                ):
                    raise AgentBoundaryError(
                        "Native insertion violates the bounded VHH loop contract"
                    )
            if spec.get("reset_res_index") != official.get("reset_res_index"):
                raise AgentBoundaryError("Native scaffold must preserve official chain indexing")
            input_refs.extend(
                [
                    bridge._project_ref(candidate, "native-scaffold"),
                    bridge._project_ref(structure, "native-scaffold-structure"),
                ]
            )
        summaries.append(
            {
                "variant": variant.id,
                "condition": variant.hypothesis_id,
                "scaffold": scaffold,
                "binding": sorted(binding),
                "avoid": sorted(avoid),
                "crop": crop,
                "hypothesis": variant.hypothesis_statement,
                "rationale": variant.rationale,
                "changed_factors": list(variant.changed_factors),
                "held_constant": list(variant.held_constant),
                "candidates": variant.candidates,
            }
        )
    return strategy, {
        "variants": summaries,
        "input_refs": input_refs,
        "hotspots_sha256": site["hotspots_sha256"],
        "target_sha256": target_sha,
        "planned_candidates": sum(v.candidates for v in strategy.variants),
        "generation_started": False,
        "source_bytes": "preserved unchanged",
    }


def import_native(bridge: Any, path: Path) -> None:
    path = confined(bridge.project, path)
    _, summary = validate_native(bridge, path)
    ref = bridge._project_ref(path, "native-strategy")
    previous = bridge.thread_latest("native-strategy-input")
    if previous and previous["strategy_ref"] == ref:
        return
    if previous:
        outcomes = [e for e in bridge.store.events(bridge.thread) if e["kind"] == "human-response"]
        if not outcomes or outcomes[-1]["payload"]["response"] != "revise":
            raise AgentBoundaryError("Replacing expert input requires an explicit scientist REVISE")
    bridge.store.event(
        bridge.thread,
        "native-strategy-input",
        {
            "strategy_ref": ref,
            "summary": summary,
            "input_id": identity({"ref": ref, "summary": summary}),
        },
    )


def native_input(bridge: Any) -> dict[str, Any] | None:
    event = bridge.thread_latest("native-strategy-input")
    if event is None:
        return None
    path = ArtifactRef.model_validate(event["strategy_ref"]).verify(bridge.project)
    _, summary = validate_native(bridge, path)
    if summary != event["summary"]:
        raise AgentBoundaryError("Native input or approved science changed after import")
    return dict(event)
