"""EasyDesign Developer Preview 的薄命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import easydesign
from easydesign.core import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ConfigurationError,
    EasyDesignError,
    RunManifest,
    SerializationError,
    load_model,
)
from easydesign.orchestration.application import (
    DiagnosticReport,
    PipelineExecution,
    RunPlan,
    continue_pipeline_after_decision,
    diagnose_runtime,
    execute_pipeline,
    list_runs,
    migrate_run_configuration,
    resume_pipeline,
    show_run,
    validate_run_configuration,
)
from easydesign.orchestration.decisions import (
    approve_decision,
    export_decision,
    show_decision,
)
from easydesign.orchestration.hotspots import approve_hotspots, export_hotspot_review
from easydesign.orchestration.profile import (
    default_runtime_profile_path,
    initialize_runtime_profile,
    load_runtime_profile,
)
from easydesign.orchestration.project import initialize_project
from easydesign.orchestration.stage04 import Stage04Execution
from easydesign.orchestration.stage05 import Stage05Execution
from easydesign.orchestration.stage06 import Stage06Execution
from easydesign.reporting import (
    HOST,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from easydesign.stages.s02_hotspot_discovery import RegionMethod


def _json_text(value: BaseModel | tuple[BaseModel, ...] | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        payload: object = value.model_dump(mode="json")
    elif isinstance(value, tuple):
        payload = [item.model_dump(mode="json") for item in value]
    else:
        payload = value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")


def _add_profile(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=Path, help="显式 runtime profile 路径")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easydesign",
        description="EasyDesign 可追溯 binder 设计流程（Developer Preview）",
    )
    parser.add_argument("--version", action="version", version=easydesign.__version__)
    parser.add_argument("--debug", action="store_true", help="失败时显示完整 traceback")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="从真实 target 创建最小用户项目")
    init_parser.add_argument("project_dir", type=Path)
    init_source = init_parser.add_mutually_exclusive_group(required=True)
    init_source.add_argument("--target", type=Path)
    init_source.add_argument("--target-bundle", type=Path)
    init_source.add_argument("--pdb-id")
    init_source.add_argument("--uniprot")
    init_source.add_argument("--uniprot-query")
    init_parser.add_argument("--source-run-root", type=Path)
    init_parser.add_argument("--chain")
    init_parser.add_argument(
        "--chain-namespace",
        choices=("auth", "label"),
        default="auth",
    )
    init_parser.add_argument("--identity-uniprot")
    init_parser.add_argument("--taxon-id", type=int)
    init_parser.add_argument("--project-id")
    init_parser.add_argument("--target-id")
    init_parser.add_argument(
        "--execution-mode",
        choices=("review-gated", "unattended"),
        default="review-gated",
    )
    init_parser.add_argument(
        "--scope-range",
        help="UniProt/reference residue range，例如 25:646",
    )
    init_parser.add_argument(
        "--scope-feature-type",
        choices=("Domain", "Chain", "Topological domain"),
    )
    init_parser.add_argument("--scope-feature-name")
    init_parser.add_argument(
        "--precomputed-msa",
        type=Path,
        help="显式提供与 target query 完全一致的 A3M；不会调用远程 MSA",
    )
    init_parser.add_argument(
        "--msa-cache-mode",
        choices=("online", "prefer-cache", "offline"),
        default="online",
        help="远程 MSA 缓存策略；默认 online 每次刷新",
    )
    init_parser.add_argument(
        "--stop-after",
        type=int,
        choices=(1, 2, 3, 4, 5, 6),
        default=1,
    )
    init_parser.add_argument(
        "--stage02-method",
        choices=("sasa", "scannet", "both"),
        default=None,
        help="Stage 02 自动方法（review-gated 默认 both；unattended 默认 sasa）",
    )
    _add_json(init_parser)

    profile_parser = commands.add_parser("profile", help="管理本机 runtime profile")
    profile_commands = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_init = profile_commands.add_parser("init", help="创建空 backend profile")
    profile_init.add_argument("--path", type=Path)
    profile_init.add_argument("--profile-id", default="local")
    profile_init.add_argument("--runs-root", type=Path)
    profile_show = profile_commands.add_parser("show", help="显示已解析 profile")
    profile_show.add_argument("--path", type=Path)
    _add_json(profile_show)
    profile_validate = profile_commands.add_parser("validate", help="只验证 profile schema")
    profile_validate.add_argument("--path", type=Path)
    _add_json(profile_validate)

    config_parser = commands.add_parser("config", help="检查用户运行配置")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate = config_commands.add_parser("validate", help="验证 YAML，不创建 run")
    config_validate.add_argument("config", type=Path)
    _add_profile(config_validate)
    config_validate.add_argument("--runs-root", type=Path)
    _add_json(config_validate)
    config_migrate = config_commands.add_parser(
        "migrate",
        help="将旧 YAML 显式迁移为 canonical 0.7",
    )
    config_migrate.add_argument("config", type=Path)
    config_migrate.add_argument("--output", type=Path, required=True)

    doctor_parser = commands.add_parser("doctor", help="检查本次运行所需环境")
    doctor_parser.add_argument("--config", type=Path)
    _add_profile(doctor_parser)
    doctor_parser.add_argument("--runs-root", type=Path)
    _add_json(doctor_parser)

    run_parser = commands.add_parser("run", help="执行 YAML 声明的已实现阶段")
    run_parser.add_argument("config", type=Path)
    _add_profile(run_parser)
    run_parser.add_argument("--runs-root", type=Path)
    run_parser.add_argument("--run-id")
    run_parser.add_argument(
        "--from-run",
        type=Path,
        help="从 checksum 验证通过的终态上游 run 建立 continuation",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    _add_json(run_parser)

    hotspots_parser = commands.add_parser(
        "hotspots",
        help="导出或批准 Stage 02 完整候选区域",
    )
    hotspots_commands = hotspots_parser.add_subparsers(
        dest="hotspots_command",
        required=True,
    )
    hotspots_export = hotspots_commands.add_parser(
        "export",
        help="导出人工审批模板，不修改 run",
    )
    hotspots_export.add_argument("run", type=Path)
    hotspots_export.add_argument(
        "--method",
        choices=("sasa", "scannet"),
        help="automatic 双方法时必填；用户提供区域不填写",
    )
    hotspots_export.add_argument("--output", type=Path, required=True)
    hotspots_approve = hotspots_commands.add_parser(
        "approve",
        help="验证审批文件并发布 hotspots.yaml",
    )
    hotspots_approve.add_argument("run", type=Path)
    hotspots_approve.add_argument("--input", type=Path, required=True)

    decisions_parser = commands.add_parser(
        "decisions",
        help="查看、导出或批准任意 Stage 的科学选择门",
    )
    decision_commands = decisions_parser.add_subparsers(
        dest="decisions_command",
        required=True,
    )
    decision_show = decision_commands.add_parser("show", help="显示当前 pending gate")
    decision_show.add_argument("run", type=Path)
    _add_json(decision_show)
    decision_export = decision_commands.add_parser("export", help="导出审批模板")
    decision_export.add_argument("run", type=Path)
    decision_export.add_argument("--output", type=Path, required=True)
    decision_approve = decision_commands.add_parser("approve", help="验证并记录人工决定")
    decision_approve.add_argument("run", type=Path)
    decision_approve.add_argument("--input", type=Path, required=True)
    _add_profile(decision_approve)

    runs_parser = commands.add_parser("runs", help="从 run-index 查看运行")
    runs_commands = runs_parser.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_commands.add_parser("list", help="列出 index 声明的 runs")
    _add_profile(runs_list)
    runs_list.add_argument("--runs-root", type=Path)
    _add_json(runs_list)
    runs_show = runs_commands.add_parser("show", help="验证并显示一个 run")
    runs_show.add_argument("run")
    _add_profile(runs_show)
    runs_show.add_argument("--runs-root", type=Path)
    _add_json(runs_show)
    runs_watch = runs_commands.add_parser(
        "watch",
        help="只读取原子 progress 与事件快照显示当前运行",
    )
    runs_watch.add_argument("run", type=Path)
    runs_watch.add_argument("--interval", type=float, default=5.0)
    runs_watch.add_argument("--once", action="store_true")
    _add_json(runs_watch)
    runs_resume = runs_commands.add_parser(
        "resume",
        help="验证 runtime state 后只恢复未达标任务",
    )
    runs_resume.add_argument("run", type=Path)
    _add_profile(runs_resume)
    _add_json(runs_resume)

    viewer_parser = commands.add_parser("viewer", help="查看自包含结构报告")
    viewer_commands = viewer_parser.add_subparsers(dest="viewer_command", required=True)
    viewer_serve = viewer_commands.add_parser("serve", help="仅在 127.0.0.1 提供已验证报告")
    viewer_serve.add_argument("run", type=Path)
    viewer_serve.add_argument("--port", type=int, default=8000)
    return parser


def _print_plan(plan: RunPlan) -> None:
    print(f"项目：{plan.project_id}")
    print(f"Target：{plan.target_id}（{plan.detected_input_format}）")
    print(f"执行到 Stage {plan.stop_after_stage}")
    print(f"需要 backend：{', '.join(plan.required_backends)}")
    print(f"Runs：{plan.runs_root}")
    print(f"Profile：{plan.profile_id}")


def _print_diagnostics(report: DiagnosticReport) -> None:
    for check in report.checks:
        print(f"[{check.status}] {check.name}: {check.message}")
    print("环境检查通过。" if report.ok else "环境检查失败。")


def _print_execution(execution: PipelineExecution) -> None:
    if execution.status == "dry-run":
        print("Dry run 通过；未创建任何 run。")
        _print_plan(execution.plan)
        return
    print(f"运行状态：{execution.status}")
    print(f"Run：{execution.run_root}")
    print(f"Run manifest：{execution.run_manifest}")
    if execution.status == "awaiting-human-approval" and execution.run_root is not None:
        print("需要人工选择；下一步：")
        current = (
            load_model(execution.run_manifest, RunManifest)
            if execution.run_manifest is not None
            else None
        )
        if (
            current is not None
            and current.workflow_state is not None
            and current.workflow_state.action == "approve-hotspots"
        ):
            print(
                f"  easydesign hotspots export {execution.run_root} --output hotspots-review.yaml"
            )
            print(
                f"  easydesign hotspots approve {execution.run_root} --input hotspots-review.yaml"
            )
        else:
            print(f"  easydesign decisions show {execution.run_root}")
            print(f"  easydesign decisions export {execution.run_root} --output decision.yaml")
            print(f"  easydesign decisions approve {execution.run_root} --input decision.yaml")
    if execution.viewer_status is not None:
        print(f"Stage 01 Viewer：{execution.viewer_status}")


def _runs_root(explicit: Path | None, profile_path: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    selected = profile_path
    if selected is None and not default_runtime_profile_path().is_file():
        return (Path.cwd() / "runs").resolve()
    loaded = load_runtime_profile(selected)
    return (
        loaded.profile.runs_root.resolve()
        if loaded.profile.runs_root is not None
        else (Path.cwd() / "runs").resolve()
    )


def _dispatch(arguments: argparse.Namespace) -> int:
    if arguments.command == "init":
        scope_range: tuple[int, int] | None = None
        if arguments.scope_range is not None:
            try:
                start_text, end_text = arguments.scope_range.split(":", maxsplit=1)
                scope_range = (int(start_text), int(end_text))
            except (TypeError, ValueError) as error:
                raise ConfigurationError("--scope-range 必须使用 START:END") from error
        initialized = initialize_project(
            project_root=arguments.project_dir,
            target=arguments.target,
            target_bundle=arguments.target_bundle,
            source_run_root=arguments.source_run_root,
            pdb_id=arguments.pdb_id,
            chain=arguments.chain,
            chain_namespace=arguments.chain_namespace,
            identity_uniprot=arguments.identity_uniprot,
            uniprot=arguments.uniprot,
            uniprot_query=arguments.uniprot_query,
            taxon_id=arguments.taxon_id,
            project_id=arguments.project_id,
            target_id=arguments.target_id,
            stop_after_stage=arguments.stop_after,
            stage02_method=arguments.stage02_method,
            execution_mode=arguments.execution_mode,
            scope_range=scope_range,
            scope_feature_type=arguments.scope_feature_type,
            scope_feature_name=arguments.scope_feature_name,
            precomputed_msa=arguments.precomputed_msa,
            msa_cache_mode=arguments.msa_cache_mode,
        )
        payload = {
            "project_root": str(initialized.project_root),
            "config": str(initialized.config_path),
            "target": (None if initialized.target_path is None else str(initialized.target_path)),
            "format": str(initialized.detected_format),
            "msa": (None if initialized.msa_path is None else str(initialized.msa_path)),
        }
        if arguments.json:
            print(_json_text(payload))
        else:
            print(f"项目已创建：{initialized.project_root}")
            print(f"下一步：easydesign config validate {initialized.config_path}")
        return 0

    if arguments.command == "profile":
        if arguments.profile_command == "init":
            path = initialize_runtime_profile(
                arguments.path,
                profile_id=arguments.profile_id,
                runs_root=arguments.runs_root,
            )
            print(f"Runtime profile 已创建：{path}")
            print("请显式填写本机 backend 绝对路径，然后运行 easydesign profile validate。")
            return 0
        loaded = load_runtime_profile(arguments.path)
        if arguments.profile_command == "show":
            if arguments.json:
                print(_json_text(loaded.profile))
            else:
                print(f"Profile：{loaded.path}")
                print(_json_text(loaded.profile))
            return 0
        payload = {
            "status": "valid",
            "path": str(loaded.path),
            "profile_id": loaded.profile.profile_id,
            "sha256": loaded.identity.sha256,
        }
        print(_json_text(payload) if arguments.json else f"Profile 校验通过：{loaded.path}")
        return 0

    if arguments.command == "config":
        if arguments.config_command == "migrate":
            migrated = migrate_run_configuration(
                arguments.config,
                arguments.output,
            )
            print(f"配置已迁移：{migrated}")
            return 0
        plan = validate_run_configuration(
            arguments.config,
            profile_path=arguments.profile,
            runs_root=arguments.runs_root,
        )
        if arguments.json:
            print(_json_text(plan))
        else:
            _print_plan(plan)
            print("配置校验通过；未创建 run。")
        return 0

    if arguments.command == "doctor":
        report = diagnose_runtime(
            profile_path=arguments.profile,
            config_path=arguments.config,
            runs_root=arguments.runs_root,
        )
        if arguments.json:
            print(_json_text(report))
        else:
            _print_diagnostics(report)
        return 0 if report.ok else 3

    if arguments.command == "run":
        execution = execute_pipeline(
            arguments.config,
            profile_path=arguments.profile,
            runs_root=arguments.runs_root,
            run_id=arguments.run_id,
            dry_run=arguments.dry_run,
            continue_from_run=arguments.from_run,
        )
        if arguments.json:
            print(_json_text(execution))
        else:
            _print_execution(execution)
        return 0

    if arguments.command == "hotspots":
        if arguments.hotspots_command == "export":
            method = (
                None
                if arguments.method is None
                else (
                    RegionMethod.SASA_SURFACE_DIVERSITY
                    if arguments.method == "sasa"
                    else RegionMethod.SCANNET_EPITOPE_NO_MSA
                )
            )
            output = export_hotspot_review(
                arguments.run,
                method=method,
                output=arguments.output,
            )
            print(f"Hotspot 审批模板已导出：{output}")
            print(
                "请填写 approved_by、每个区域的两类理由；用户提供区域和 "
                "structural-only 证据还需分别确认 acknowledgement。"
            )
            return 0
        hotspots = approve_hotspots(
            arguments.run,
            input_path=arguments.input,
        )
        print(f"Stage 02 已批准：{hotspots}")
        return 0

    if arguments.command == "decisions":
        if arguments.decisions_command == "show":
            request = show_decision(arguments.run)
            if arguments.json:
                print(_json_text(request))
            else:
                print(f"Decision：{request.decision_id}")
                print(f"Gate：{request.stage_id}/{request.gate}")
                print(request.message)
                for option in request.options:
                    state = "eligible" if option.eligible else "ineligible"
                    print(f"- {option.option_id} [{state}] {option.label}")
            return 0
        if arguments.decisions_command == "export":
            output = export_decision(arguments.run, output=arguments.output)
            print(f"Decision 审批模板已导出：{output}")
            return 0
        record = approve_decision(arguments.run, input_path=arguments.input)
        print(f"Decision 已记录：{record}")
        execution = continue_pipeline_after_decision(
            arguments.run,
            decision_record=record,
            profile_path=arguments.profile,
        )
        _print_execution(execution)
        return 0

    if arguments.command == "runs":
        if arguments.runs_command == "watch":
            if arguments.interval <= 0 or arguments.interval > 60:
                raise ConfigurationError("--interval 必须在 0 到 60 秒之间")
            while True:
                from easydesign.orchestration import read_pipeline_progress

                progress = read_pipeline_progress(arguments.run)
                if arguments.json:
                    print(_json_text(progress), flush=True)
                else:
                    print(
                        f"[{progress.updated_at.isoformat()}] "
                        f"{progress.stage_id}"
                        f"{f'/{progress.phase}' if progress.phase else ''} "
                        f"{progress.status}: "
                        f"tasks {progress.succeeded_tasks}/{progress.total_tasks}, "
                        f"running={progress.running_tasks}, failed={progress.failed_tasks}; "
                        f"candidates {progress.collected_candidates}/"
                        f"{progress.planned_candidates}",
                        flush=True,
                    )
                    if progress.per_device:
                        assignments = ", ".join(
                            f"GPU {device}={strategy}"
                            for device, strategy in sorted(progress.per_device.items())
                        )
                        print(f"  {assignments}", flush=True)
                    if progress.estimated_remaining_seconds is not None:
                        print(
                            f"  ETA≈{progress.estimated_remaining_seconds / 60:.1f} min",
                            flush=True,
                        )
                    for message in progress.recent_errors[-3:]:
                        print(f"  ERROR {message}", flush=True)
                if arguments.once or progress.status in {
                    "succeeded",
                    "scientific-stop",
                    "failed",
                    "incomplete",
                }:
                    return 0
                time.sleep(arguments.interval)
        if arguments.runs_command == "resume":
            outcome = resume_pipeline(
                arguments.run,
                profile_path=arguments.profile,
            )
            if arguments.json:
                print(_json_text(outcome))
            else:
                print(f"恢复状态：{outcome.status}")
                if isinstance(outcome, Stage04Execution):
                    print(f"完整候选：{outcome.complete_candidate_count}")
                elif isinstance(outcome, Stage05Execution):
                    print(
                        "胜出策略："
                        f"{outcome.selected_strategy_id or '无（科学停止）'}"
                    )
                elif isinstance(outcome, Stage06Execution):
                    print(f"规模候选：{outcome.complete_candidate_count}")
                print(f"Run：{outcome.run_root}")
            return 4 if outcome.status == "incomplete" else 0
        root = _runs_root(arguments.runs_root, arguments.profile)
        if arguments.runs_command == "list":
            runs = list_runs(root)
            if arguments.json:
                print(_json_text(runs))
            elif not runs:
                print(f"没有 index 声明的 run：{root}")
            else:
                for run in runs:
                    print(
                        f"{run.project_id}/{run.run_id}\t{run.status}\t"
                        f"revision={run.manifest_revision}\t{run.integrity_status}"
                    )
            return 0
        run = show_run(root, arguments.run)
        if arguments.json:
            print(_json_text(run))
        else:
            print(f"Run：{run.project_id}/{run.run_id}")
            print(f"状态：{run.status}")
            print(f"Manifest：{run.latest_manifest}")
            print(f"Stages：{', '.join(run.completed_stages) or '无'}")
        return 0

    if arguments.command == "viewer":
        report_root = resolve_target_viewer_argument(arguments.run)
        server = create_target_viewer_server(report_root, port=arguments.port)
        print(f"Target Viewer report：{server.report_root}")
        print(f"Local URL：{server.url}")
        print(
            "远程服务器请使用 SSH 端口转发："
            f"ssh -N -L {server.server.server_address[1]}:{HOST}:"
            f"{server.server.server_address[1]} <server>"
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nTarget Viewer server 已停止。")
        finally:
            server.close()
        return 0
    raise AssertionError(f"未处理命令: {arguments.command}")


def _exit_code(error: Exception) -> int:
    if isinstance(error, ConfigurationError):
        return 2
    if isinstance(error, (ArtifactIntegrityError, ArtifactNotFoundError, SerializationError)):
        return 5
    return 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        return _dispatch(arguments)
    except (EasyDesignError, OSError, ValueError) as error:
        if arguments.debug:
            traceback.print_exc()
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return _exit_code(error)


if __name__ == "__main__":
    raise SystemExit(main())
