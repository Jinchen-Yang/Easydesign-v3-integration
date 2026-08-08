"""EasyDesign Local command line for one explicit project and one step."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import easydesign
from easydesign.core import EasyDesignError
from easydesign.orchestration.application import diagnose_runtime
from easydesign.orchestration.local_project import resolve_project_run
from easydesign.orchestration.local_steps import (
    StepCommandResult,
    approve_step,
    drain_step,
    initialize_step_project,
    resume_step,
    run_step,
    stage_template,
    status_step,
    validate_step,
    watch_step,
)
from easydesign.orchestration.runtime_link import link_runtime, verify_runtime_link
from easydesign.reporting import (
    build_stage02_viewer_overlay,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from easydesign.workspace_context import WorkspaceContext


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")


def _add_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", dest="run_id", help="显式 run ID")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easydesign",
        description="EasyDesign Local：在 VS Code 终端逐阶段运行可追溯设计流程",
    )
    parser.add_argument("--version", action="version", version=easydesign.__version__)
    parser.add_argument("--debug", action="store_true", help="失败时显示 traceback")
    commands = parser.add_subparsers(dest="command", required=True)

    runtime = commands.add_parser("runtime", help="链接或验证本机科学环境/模型")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_link = runtime_commands.add_parser("link", help="只读复用已安装 runtime")
    runtime_link.add_argument("source", type=Path)
    _add_json(runtime_link)
    runtime_status = runtime_commands.add_parser("status", help="验证当前 link receipt")
    _add_json(runtime_status)

    doctor = commands.add_parser("doctor", help="检查本地 runtime/backend")
    doctor.add_argument("--full", action="store_true")
    _add_json(doctor)

    step = commands.add_parser("step", help="初始化、验证并顺序运行 Stage 1–7")
    step_commands = step.add_subparsers(dest="step_command", required=True)

    init = step_commands.add_parser("init", help="创建平铺的七份 Stage YAML")
    init.add_argument("project", type=Path)
    source = init.add_mutually_exclusive_group(required=True)
    source.add_argument("--target", type=Path)
    source.add_argument("--target-bundle", type=Path)
    source.add_argument("--pdb-id")
    source.add_argument("--uniprot")
    source.add_argument("--uniprot-query")
    init.add_argument(
        "--source-run-root",
        type=Path,
        help="--target-bundle 对应的只读源 run（当前 local 或 Git APOE example）",
    )
    init.add_argument("--chain")
    init.add_argument("--chain-namespace", choices=("auth", "label"), default="auth")
    init.add_argument("--identity-uniprot")
    init.add_argument("--taxon-id", type=int)
    init.add_argument("--project-id")
    init.add_argument("--target-id")
    init.add_argument("--scope-range", help="例如 25:646")
    init.add_argument(
        "--scope-feature-type",
        choices=("Domain", "Chain", "Topological domain"),
    )
    init.add_argument("--scope-feature-name")
    init.add_argument("--precomputed-msa", type=Path)
    init.add_argument(
        "--msa-cache-mode",
        choices=("online", "prefer-cache", "offline"),
        default="online",
    )
    _add_json(init)

    template = step_commands.add_parser("template", help="定位标准 YAML 或生成人工模板")
    template.add_argument("step", type=int, choices=range(1, 8))
    template.add_argument("project", type=Path)
    template.add_argument("--manual", action="store_true")
    template.add_argument("--output", type=Path)
    _add_json(template)

    validate = step_commands.add_parser("validate", help="只验证当前 Stage 配置")
    validate.add_argument("step", type=int, choices=range(1, 8))
    validate.add_argument("project", type=Path)
    validate.add_argument("--config", type=Path)
    _add_run(validate)
    _add_json(validate)

    run = step_commands.add_parser("run", help="只运行当前 run 的下一 Stage")
    run.add_argument("step", type=int, choices=range(1, 8))
    run.add_argument("project", type=Path)
    run.add_argument("--config", type=Path)
    run.add_argument("--confirm", action="store_true")
    run.add_argument("--detach", action="store_true")
    _add_run(run)
    _add_json(run)

    approve = step_commands.add_parser("approve", help="批准 Stage 01 decision 或 Stage 02 区域")
    approve.add_argument("step", type=int, choices=(1, 2))
    approve.add_argument("project", type=Path)
    approve.add_argument("--input", type=Path, required=True)
    approve.add_argument("--detach", action="store_true")
    _add_run(approve)
    _add_json(approve)

    status = step_commands.add_parser("status", help="读取项目、run 和 worker 状态")
    status.add_argument("project", type=Path)
    _add_run(status)
    _add_json(status)

    watch = step_commands.add_parser("watch", help="观察持久 worker；Ctrl-C 仅脱离")
    watch.add_argument("project", type=Path)
    _add_run(watch)
    _add_json(watch)

    resume = step_commands.add_parser("resume", help="恢复中断的 Stage 04–07")
    resume.add_argument("project", type=Path)
    resume.add_argument("--detach", action="store_true")
    _add_run(resume)
    _add_json(resume)

    drain = step_commands.add_parser("drain", help="在安全检查点停止新分片调度")
    drain.add_argument("project", type=Path)
    drain.add_argument("--job", dest="job_id")
    _add_json(drain)

    view = step_commands.add_parser("view", help="启动只读 Target Viewer")
    view.add_argument("project", type=Path)
    _add_run(view)
    view.add_argument("--port", type=int, default=8000)
    _add_json(view)
    return parser


def _scope_range(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        start, end = (int(item) for item in value.split(":", maxsplit=1))
    except (TypeError, ValueError) as error:
        raise ValueError("--scope-range 必须是 START:END") from error
    return start, end


def _json(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _print_result(result: StepCommandResult, *, as_json: bool) -> None:
    if as_json:
        print(_json(result))
        return
    print(f"状态: {result.status}")
    print(f"项目: {result.project_id}")
    if result.run_id:
        print(f"Run: {result.run_id}")
    if result.job_id:
        print(f"Job: {result.job_id}")
    if result.run_root:
        print(f"Run 目录: {result.run_root}")
    if result.manifest:
        print(f"Manifest: {result.manifest}")
    if result.generated_files:
        print("生成文件:")
        for path in result.generated_files:
            print(f"  - {path}")
    if result.next_actions:
        print("下一步:")
        for action in result.next_actions:
            print(f"  - {action}")


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "runtime":
        if args.runtime_command == "link":
            link_result = link_runtime(args.source)
            print(_json(link_result) if args.json else (
                f"已链接只读 runtime: {link_result.source_runtime}\n"
                f"Profile: {link_result.profile}\nReceipt: {link_result.receipt}\n"
                f"环境 {link_result.environment_count}，资产 {link_result.asset_count}"
            ))
        else:
            receipt = verify_runtime_link()
            print(_json(receipt) if args.json else f"runtime link 有效: {receipt.source_runtime}")
        return 0
    if args.command == "doctor":
        report = diagnose_runtime(full=args.full)
        if args.json:
            print(_json(report))
        else:
            for check in report.checks:
                print(f"{check.status}: {check.name}: {check.message}")
        return 0 if report.ok else 2
    result: StepCommandResult
    if args.step_command == "init":
        result = initialize_step_project(
            project_root=args.project,
            target=args.target,
            target_bundle=args.target_bundle,
            source_run_root=args.source_run_root,
            pdb_id=args.pdb_id,
            uniprot=args.uniprot,
            uniprot_query=args.uniprot_query,
            taxon_id=args.taxon_id,
            chain=args.chain,
            chain_namespace=args.chain_namespace,
            identity_uniprot=args.identity_uniprot,
            project_id=args.project_id,
            target_id=args.target_id,
            scope_range=_scope_range(args.scope_range),
            scope_feature_type=args.scope_feature_type,
            scope_feature_name=args.scope_feature_name,
            precomputed_msa=args.precomputed_msa,
            msa_cache_mode=args.msa_cache_mode,
        )
    elif args.step_command == "template":
        result = stage_template(
            args.step,
            args.project,
            manual=args.manual,
            output=args.output,
        )
    elif args.step_command == "validate":
        result = validate_step(
            args.step,
            args.project,
            config_path=args.config,
            run_id=args.run_id,
        )
    elif args.step_command == "run":
        result = run_step(
            args.step,
            args.project,
            config_path=args.config,
            run_id=args.run_id,
            confirm=args.confirm,
            detach=args.detach,
        )
    elif args.step_command == "approve":
        result = approve_step(
            args.step,
            args.project,
            input_path=args.input,
            run_id=args.run_id,
            detach=args.detach,
        )
    elif args.step_command == "status":
        result = status_step(args.project, run_id=args.run_id)
    elif args.step_command == "watch":
        result = watch_step(args.project, run_id=args.run_id)
    elif args.step_command == "resume":
        result = resume_step(args.project, run_id=args.run_id, detach=args.detach)
    elif args.step_command == "drain":
        result = drain_step(args.project, job_id=args.job_id)
    elif args.step_command == "view":
        summary = resolve_project_run(args.project, run_id=args.run_id, required=True)
        assert summary is not None
        report_root = resolve_target_viewer_argument(summary.path)
        server = create_target_viewer_server(
            report_root,
            port=args.port,
            stage02_overlay=build_stage02_viewer_overlay(summary.path),
        )
        result = StepCommandResult(
            status="serving",
            project_id=summary.project_id,
            run_id=summary.run_id,
            run_root=summary.path,
            manifest=summary.latest_manifest,
            next_actions=(server.url, "Ctrl-C 仅停止只读 Viewer，不影响科学任务。"),
        )
        _print_result(result, as_json=args.json)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
        return 0
    else:
        raise RuntimeError(f"未知 step command: {args.step_command}")
    _print_result(result, as_json=args.json)
    return 2 if result.status.endswith("-failed") else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        os.environ.update(WorkspaceContext.discover().child_environment())
        return _dispatch(args)
    except (EasyDesignError, OSError, ValueError) as error:
        if getattr(args, "debug", False):
            traceback.print_exc()
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
