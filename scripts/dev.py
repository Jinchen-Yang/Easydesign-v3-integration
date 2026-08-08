"""Fast, deterministic developer context and verification entry point."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "development-policy.json"
AGENTS_PATH = ROOT / "AGENTS.md"
MODE_ORDER = {"inspect": 0, "dev-local": 1, "integration": 2, "release": 3}
LOCAL_BRANCH = "codex/vscode-local"
SHARED_SCIENCE_PATHS = (
    "src/easydesign/core",
    "src/easydesign/stages",
    "src/easydesign/filtering",
    "src/easydesign/backends",
)


class DeveloperWorkflowError(RuntimeError):
    """Raised for an invalid or unsafe developer workflow request."""


def _load_policy() -> dict[str, Any]:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "0.1":
        raise DeveloperWorkflowError("development policy schema 必须为 0.1")
    return cast(dict[str, Any], payload)


def _git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check and completed.returncode != 0:
        raise DeveloperWorkflowError(
            f"Git 命令失败: {' '.join(arguments)}: {completed.stderr.strip()}"
        )
    return completed


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _normalize_paths(paths: Sequence[str]) -> tuple[str, ...]:
    normalized: set[str] = set()
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_absolute():
            try:
                candidate = candidate.resolve().relative_to(ROOT.resolve())
            except ValueError as error:
                raise DeveloperWorkflowError(f"路径不属于仓库: {raw}") from error
        value = candidate.as_posix().removeprefix("./")
        if not value or value.startswith("../"):
            raise DeveloperWorkflowError(f"无效仓库相对路径: {raw}")
        normalized.add(value)
    return tuple(sorted(normalized))


def selected_guides(mode: str, paths: Sequence[str]) -> tuple[str, ...]:
    policy = _load_policy()
    selected: set[str] = set()
    for guide in policy["agent_guides"]:
        if any(_matches(path, guide["patterns"]) for path in paths):
            selected.add(guide["path"])
    if mode == "ops":
        selected.add("docs/agent/RUNTIME_AND_DATA.md")
    return tuple(sorted(selected))


def policy_bundle_id(guides: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in ("AGENTS.md", "config/development-policy.json", *sorted(guides)):
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def guides_for_known_bundle(bundle_id: str | None) -> tuple[str, ...] | None:
    """Resolve a current-policy receipt without persisting task state."""

    if not bundle_id:
        return None
    guide_paths = tuple(
        sorted(item["path"] for item in _load_policy()["agent_guides"])
    )
    for mask in range(1 << len(guide_paths)):
        candidate = tuple(
            path for index, path in enumerate(guide_paths) if mask & (1 << index)
        )
        if policy_bundle_id(candidate) == bundle_id:
            return candidate
    return None


def _is_ancestor(commit: str) -> bool:
    return _git("merge-base", "--is-ancestor", commit, "main", check=False).returncode == 0


def git_topology() -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    branches = []
    current_branch = _git("branch", "--show-current").stdout.strip()
    for line in _git(
        "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"
    ).stdout.splitlines():
        name, commit = line.split(maxsplit=1)
        branches.append({"name": name, "commit": commit})
        if name not in {"main", LOCAL_BRANCH}:
            message = f"历史 branch {name} @ {commit[:12]}"
            (warnings if _is_ancestor(commit) else blockers).append(message)

    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*_git("worktree", "list", "--porcelain").stdout.splitlines(), ""]:
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value or True
    root = str(ROOT.resolve())
    for item in worktrees:
        if item.get("worktree") == root:
            continue
        commit = str(item.get("HEAD", ""))
        is_main_worktree = (
            current_branch == LOCAL_BRANCH
            and item.get("branch") == "refs/heads/main"
        )
        safe_legacy = is_main_worktree or (
            bool(item.get("locked")) and bool(commit) and _is_ancestor(commit)
        )
        message = f"额外 worktree {item.get('worktree')} @ {commit[:12]}"
        (warnings if safe_legacy else blockers).append(message)
    return {
        "branch": current_branch,
        "head": _git("rev-parse", "HEAD").stdout.strip(),
        "status": _git("status", "--short", "--branch").stdout.splitlines(),
        "branches": branches,
        "worktrees": worktrees,
        "warnings": warnings,
        "blockers": blockers,
    }


def context_command(arguments: argparse.Namespace) -> int:
    started = time.monotonic()
    paths = _normalize_paths(arguments.path or ["AGENTS.md"])
    guides = selected_guides(arguments.mode, paths)
    bundle = policy_bundle_id(guides)
    topology = git_topology()
    unchanged = arguments.known_bundle_id == bundle
    previous_guides = guides_for_known_bundle(arguments.known_bundle_id)
    if unchanged:
        required_reading: list[str] = []
    elif previous_guides is not None:
        required_reading = [
            guide for guide in guides if guide not in previous_guides
        ]
    else:
        required_reading = ["AGENTS.md", *guides]
    payload = {
        "schema_version": "0.1",
        "mode": arguments.mode,
        "paths": list(paths),
        "selected_guides": list(guides),
        "policy_bundle_id": bundle,
        "policy_unchanged": unchanged,
        "required_reading": required_reading,
        "verification_profile": (
            "none" if arguments.mode in {"inspect", "ops"} else arguments.mode
        ),
        "git": topology,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 3 if topology["blockers"] else 0


def changed_paths() -> tuple[str, ...]:
    paths: set[str] = set()
    for arguments in (
        ("diff", "--name-only", "HEAD"),
        ("diff", "--name-only", "--cached"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(line for line in _git(*arguments).stdout.splitlines() if line)
    return tuple(sorted(paths))


def minimum_mode(paths: Sequence[str]) -> str:
    patterns = _load_policy()["integration_patterns"]
    return "integration" if any(_matches(path, patterns) for path in paths) else "dev-local"


def routed_tests(paths: Sequence[str]) -> tuple[str, ...]:
    selected: set[str] = set()
    for route in _load_policy()["test_routes"]:
        if any(_matches(path, route["patterns"]) for path in paths):
            selected.update(route["tests"])
    return tuple(sorted(selected))


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float


@dataclass(frozen=True)
class RuntimeTreeStats:
    logical_bytes: int
    file_count: int
    symlink_count: int
    newest_mtime: float


def _runtime_tree_stats(path: Path) -> RuntimeTreeStats:
    """Inventory one path without following symlinks or changing any state."""

    if not path.exists() and not path.is_symlink():
        return RuntimeTreeStats(0, 0, 0, 0.0)
    initial = path.lstat()
    logical_bytes = initial.st_size
    file_count = int(path.is_file() and not path.is_symlink())
    symlink_count = int(path.is_symlink())
    newest_mtime = initial.st_mtime
    if not path.is_dir() or path.is_symlink():
        return RuntimeTreeStats(
            logical_bytes,
            file_count,
            symlink_count,
            newest_mtime,
        )
    for directory, directory_names, filenames in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        for name in (*directory_names, *filenames):
            item = directory_path / name
            item_stat = item.lstat()
            logical_bytes += item_stat.st_size
            newest_mtime = max(newest_mtime, item_stat.st_mtime)
            if item.is_symlink():
                symlink_count += 1
            elif item.is_file():
                file_count += 1
    return RuntimeTreeStats(
        logical_bytes,
        file_count,
        symlink_count,
        newest_mtime,
    )


def cleanup_report_payload(
    *,
    limit: int,
    root: Path = ROOT,
    policy: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Return a read-only retention report; never infer deletion permission."""

    if limit < 1:
        raise DeveloperWorkflowError("cleanup-report --limit 必须大于 0")
    selected_policy = policy or _load_policy()
    retention = selected_policy.get("runtime_retention")
    if not isinstance(retention, dict):
        raise DeveloperWorkflowError("development policy 缺少 runtime_retention")
    if retention.get("automatic_deletion") is not False:
        raise DeveloperWorkflowError("runtime retention 必须显式禁止自动删除")

    selected_root = root.resolve(strict=True)
    generated_at = time.time() if now is None else now
    protected_paths: list[dict[str, object]] = []
    for relative in retention.get("protected_paths", []):
        protected = selected_root / str(relative)
        protected_paths.append(
            {
                "path": str(relative),
                "exists": protected.exists() or protected.is_symlink(),
            }
        )

    apoe_manifest = selected_root / "examples/apoe-ui-demo/bundle-manifest.json"
    apoe_manifest_sha256 = (
        hashlib.sha256(apoe_manifest.read_bytes()).hexdigest()
        if apoe_manifest.is_file()
        else None
    )
    roots: list[dict[str, object]] = []
    for configured in retention.get("inventory_roots", []):
        relative = str(configured["path"])
        inventory_root = selected_root / relative
        resolved = inventory_root.resolve(strict=False)
        if not resolved.is_relative_to(selected_root):
            raise DeveloperWorkflowError(f"retention 路径逃逸仓库: {relative}")
        root_stats = _runtime_tree_stats(inventory_root)
        review_policy = str(configured["review_policy"])
        minimum_age_days = configured.get("minimum_age_days")
        entries: list[dict[str, object]] = []
        if inventory_root.is_dir() and not inventory_root.is_symlink():
            for entry in inventory_root.iterdir():
                stats = _runtime_tree_stats(entry)
                age_days = (
                    max(0.0, (generated_at - stats.newest_mtime) / 86_400)
                    if stats.newest_mtime
                    else 0.0
                )
                if review_policy == "manual":
                    status = "manual-review"
                elif minimum_age_days is not None and age_days >= float(minimum_age_days):
                    status = "retention-review"
                else:
                    status = "retained-young"
                entries.append(
                    {
                        "path": entry.relative_to(selected_root).as_posix(),
                        "status": status,
                        "age_days": round(age_days, 3),
                        "logical_bytes": stats.logical_bytes,
                        "file_count": stats.file_count,
                        "symlink_count": stats.symlink_count,
                        "newest_mtime": (
                            datetime.fromtimestamp(stats.newest_mtime, UTC).isoformat()
                            if stats.newest_mtime
                            else None
                        ),
                    }
                )
        entries.sort(key=lambda item: (-int(item["logical_bytes"]), str(item["path"])))
        budget_bytes = int(configured["budget_bytes"])
        roots.append(
            {
                "path": relative,
                "review_policy": review_policy,
                "minimum_age_days": minimum_age_days,
                "budget_bytes": budget_bytes,
                "over_budget": root_stats.logical_bytes > budget_bytes,
                "logical_bytes": root_stats.logical_bytes,
                "file_count": root_stats.file_count,
                "symlink_count": root_stats.symlink_count,
                "entry_count": len(entries),
                "status_counts": {
                    status: sum(item["status"] == status for item in entries)
                    for status in ("retention-review", "retained-young", "manual-review")
                },
                "largest_entries": entries[:limit],
            }
        )
    return {
        "schema_version": "0.1",
        "generated_at": datetime.fromtimestamp(generated_at, UTC).isoformat(),
        "automatic_deletion": False,
        "safety_notice": (
            "只读报告；retention-review 只表示达到年龄阈值，不表示已获得删除授权。"
            "删除仍需精确路径、引用、活动进程和可再生性证明。"
        ),
        "protected_paths": protected_paths,
        "apoe_bundle_manifest_sha256": apoe_manifest_sha256,
        "roots": roots,
    }


def cleanup_report_command(arguments: argparse.Namespace) -> int:
    print(
        json.dumps(
            cleanup_report_payload(limit=arguments.limit),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _developer_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPYCACHEPREFIX"] = str(ROOT / "runtime/cache/dev/pycache")
    environment["RUFF_CACHE_DIR"] = str(ROOT / "runtime/cache/dev/ruff")
    return environment


def _run(command: Sequence[str], *, environment: dict[str, str] | None = None) -> CommandResult:
    print(f"+ {' '.join(command)}", flush=True)
    started = time.monotonic()
    selected_environment = _developer_environment()
    if environment is not None:
        selected_environment.update(environment)
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        check=False,
        env=selected_environment,
    )
    result = CommandResult(
        command=tuple(command),
        returncode=completed.returncode,
        duration_seconds=round(time.monotonic() - started, 3),
    )
    print(
        f"  -> rc={result.returncode} duration={result.duration_seconds:.3f}s",
        flush=True,
    )
    if result.returncode != 0:
        raise DeveloperWorkflowError(f"验证失败: {' '.join(command)}")
    return result


def _python() -> Path:
    selected = ROOT / ".venv" / "bin" / "python"
    if not selected.is_file():
        raise DeveloperWorkflowError(
            "缺少 .venv/bin/python；请先运行 uv sync --frozen --extra dev"
        )
    return selected


def _latest_environment_prefix(environment_id: str) -> Path | None:
    receipt = ROOT / "runtime/state/runtime-link.json"
    source_root: Path | None = None
    if receipt.is_file():
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            source_root = Path(payload["source_runtime"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            source_root = None
    record_root = (
        ROOT / "runtime/state/registries/environments"
        if source_root is None
        else source_root / "state/registries/environments"
    )
    for record_path in sorted(record_root.glob("revision-*.json"), reverse=True):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("environment_id") != environment_id:
            continue
        if record.get("status") != "available":
            return None
        relative = record.get("relative_prefix")
        if isinstance(relative, str):
            base = ROOT if source_root is None else source_root.parent
            return base / relative
        return None
    return None


def resolve_tool(name: str) -> Path:
    if name == "python":
        return _python()
    if name == "uv":
        candidates = sorted(
            (ROOT / "runtime" / "tools").glob("uv-*/bin/uv"),
            reverse=True,
        )
        discovered_uv = shutil.which("uv")
        if discovered_uv:
            candidates.append(Path(discovered_uv))
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        raise DeveloperWorkflowError("找不到 workspace uv；请先完成 uv onboarding")
    prefix = _latest_environment_prefix("reporting-web")
    candidates: list[Path] = []
    if prefix is not None:
        if name == "node":
            candidates.append(prefix / "bin" / "node")
        else:
            candidates.extend(
                (
                    prefix / "bin" / name,
                    prefix / "lib" / "node_modules" / "corepack" / "shims" / name,
                )
            )
    discovered = shutil.which(name)
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise DeveloperWorkflowError(f"找不到开发工具 {name}；请先发布 reporting-web 环境")


def _dev_local_commands(paths: Sequence[str]) -> list[list[str]]:
    python = str(_python())
    commands: list[list[str]] = [
        ["git", "diff", "--check"],
        [python, "scripts/check_repository.py"],
    ]
    python_files = [
        path for path in paths if path.endswith(".py") and (ROOT / path).is_file()
    ]
    if python_files:
        commands.extend(
            [
                [python, "-m", "compileall", "-q", *python_files],
                [python, "-m", "ruff", "check", *python_files],
                [python, "-m", "mypy"],
            ]
        )
    tests = routed_tests(paths)
    if tests:
        commands.append([python, "-m", "pytest", *tests])
    if any(path.startswith(("web/target-viewer/", "src/easydesign/reporting/")) for path in paths):
        commands.append(["make", "test-web"])
    return commands


def verify_command(arguments: argparse.Namespace) -> int:
    paths = changed_paths()
    if not paths:
        print(json.dumps({"mode": arguments.mode, "changed_paths": [], "status": "nothing-to-do"}))
        return 0
    required = minimum_mode(paths)
    if MODE_ORDER[arguments.mode] < MODE_ORDER[required]:
        print(
            json.dumps(
                {
                    "status": "mode-too-low",
                    "requested_mode": arguments.mode,
                    "required_mode": required,
                    "changed_paths": list(paths),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    started = time.monotonic()
    results: list[CommandResult] = []
    try:
        if arguments.mode == "dev-local":
            commands = _dev_local_commands(paths)
        elif arguments.mode == "integration":
            commands = [["make", "check"], ["make", "test"]]
            if any(
                path.startswith(("src/easydesign/reporting/", "web/target-viewer/"))
                for path in paths
            ):
                commands.append(["make", "test-web"])
        else:
            commands = [
                ["make", "check"],
                ["make", "test"],
                ["make", "test-web"],
                ["make", "build-wheel-staging"],
            ]
        for command in commands:
            results.append(_run(command))
    except DeveloperWorkflowError as error:
        print(str(error), file=sys.stderr)
        return 1
    payload = {
        "status": "passed",
        "mode": arguments.mode,
        "changed_paths": list(paths),
        "duration_seconds": round(time.monotonic() - started, 3),
        "commands": [
            {
                "command": list(item.command),
                "returncode": item.returncode,
                "duration_seconds": item.duration_seconds,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def core_sync_report_command(arguments: argparse.Namespace) -> int:
    against = arguments.against
    committed = _git(
        "diff", "--name-status", f"{against}...HEAD", "--", *SHARED_SCIENCE_PATHS,
        check=False,
    )
    if committed.returncode != 0:
        raise DeveloperWorkflowError(
            f"无法比较 shared science paths: {committed.stderr.strip()}"
        )
    dirty = _git(
        "diff", "--name-status", "HEAD", "--", *SHARED_SCIENCE_PATHS,
        check=False,
    )
    if dirty.returncode != 0:
        raise DeveloperWorkflowError(
            f"无法读取 shared science 工作树差异: {dirty.stderr.strip()}"
        )
    rows_by_path: dict[str, dict[str, str]] = {}
    for source, output in (("committed", committed.stdout), ("working-tree", dirty.stdout)):
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            status, path = fields[0], fields[-1]
            row = {"status": status, "path": path, "source": source}
            if len(fields) == 3:
                row["previous_path"] = fields[1]
            rows_by_path[path] = row
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", *SHARED_SCIENCE_PATHS
    )
    for path in untracked.stdout.splitlines():
        rows_by_path[path] = {
            "status": "A",
            "path": path,
            "source": "working-tree",
        }
    rows = [rows_by_path[path] for path in sorted(rows_by_path)]
    commits = _git(
        "log",
        "--format=%H%x09%s",
        f"{against}..HEAD",
        "--",
        *SHARED_SCIENCE_PATHS,
    ).stdout.splitlines()
    payload = {
        "schema_version": "0.1",
        "against": against,
        "head": _git("rev-parse", "HEAD").stdout.strip(),
        "working_tree_included": True,
        "shared_paths": list(SHARED_SCIENCE_PATHS),
        "differences": rows,
        "core_commits": [
            {"commit": line.split("\t", 1)[0], "subject": line.split("\t", 1)[1]}
            for line in commits
            if "\t" in line
        ],
        "notice": "只读报告；禁止整体 merge local 分支，只能逐个评审 core: commit。",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    context = commands.add_parser("context", help="输出本逻辑任务的最小 Agent 上下文")
    context.add_argument("--mode", choices=(*MODE_ORDER, "ops"), default="dev-local")
    context.add_argument("--path", action="append", default=[])
    context.add_argument("--known-bundle-id")
    context.set_defaults(function=context_command)

    verify = commands.add_parser("verify", help="按风险模式执行验证")
    verify.add_argument("--mode", choices=("dev-local", "integration", "release"), required=True)
    verify.set_defaults(function=verify_command)

    cleanup = commands.add_parser(
        "cleanup-report",
        help="只读盘点 runtime/dist 预算与 retention 复核候选",
    )
    cleanup.add_argument("--limit", type=int, default=50)
    cleanup.set_defaults(function=cleanup_report_command)

    tools = commands.add_parser("tool-path", help="解析 workspace 开发工具")
    tools.add_argument("name", choices=("python", "uv", "node", "npm", "pnpm"))
    tools.set_defaults(function=lambda args: print(resolve_tool(args.name)) or 0)

    sync = commands.add_parser(
        "core-sync-report",
        help="只读列出 local 与 UI main 的共享科学路径差异",
    )
    sync.add_argument("--against", default="main")
    sync.set_defaults(function=core_sync_report_command)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        return int(arguments.function(arguments))
    except DeveloperWorkflowError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
