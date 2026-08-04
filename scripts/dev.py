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
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "development-policy.json"
AGENTS_PATH = ROOT / "AGENTS.md"
MODE_ORDER = {"inspect": 0, "dev-local": 1, "integration": 2, "release": 3}


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
    if mode == "release":
        selected.add("docs/agent/RELEASE_AND_REMOTE.md")
    if mode == "ops":
        selected.update(
            {
                "docs/agent/RUNTIME_AND_DATA.md",
                "docs/agent/RELEASE_AND_REMOTE.md",
            }
        )
    return tuple(sorted(selected))


def policy_bundle_id(guides: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in ("AGENTS.md", "configs/development-policy.json", *sorted(guides)):
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
    for line in _git(
        "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"
    ).stdout.splitlines():
        name, commit = line.split(maxsplit=1)
        branches.append({"name": name, "commit": commit})
        if name != "main":
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
        safe_legacy = bool(item.get("locked")) and bool(commit) and _is_ancestor(commit)
        message = f"额外 worktree {item.get('worktree')} @ {commit[:12]}"
        (warnings if safe_legacy else blockers).append(message)
    return {
        "branch": _git("branch", "--show-current").stdout.strip(),
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


def _run(command: Sequence[str], *, environment: dict[str, str] | None = None) -> CommandResult:
    print(f"+ {' '.join(command)}", flush=True)
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        check=False,
        env=environment,
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
            "缺少 .venv/bin/python；请先运行 uv sync --frozen --extra ui --extra dev"
        )
    return selected


def _latest_environment_prefix(environment_id: str) -> Path | None:
    record_root = ROOT / "runtime" / "state" / "registries" / "environments"
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
            return ROOT / relative
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
            candidates.append(prefix / "lib" / "node_modules" / "corepack" / "shims" / name)
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
    if any(path.startswith("web/") for path in paths):
        commands.append(["make", "build-ui-staging"])
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
                path.startswith(("src/easydesign/ui/", "src/easydesign/reporting/", "web/"))
                for path in paths
            ):
                commands.append(["make", "test-web-chromium"])
        else:
            commands = [
                ["make", "check"],
                ["make", "test"],
                ["make", "test-web"],
                ["make", "release-build", "RELEASE=1"],
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


def ui_command(arguments: argparse.Namespace) -> int:
    if arguments.port == 18769:
        raise DeveloperWorkflowError("18769 保留给正式 release；开发 UI 必须使用其他端口")
    command = [
        str(_python()),
        "-m",
        "easydesign",
        "ui",
        "serve",
        "--development",
        "--host",
        "127.0.0.1",
        "--port",
        str(arguments.port),
    ]
    if arguments.open:
        command.append("--open")
    os.execv(command[0], command)
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

    tools = commands.add_parser("tool-path", help="解析 workspace 开发工具")
    tools.add_argument("name", choices=("python", "uv", "node", "npm", "pnpm"))
    tools.set_defaults(function=lambda args: print(resolve_tool(args.name)) or 0)

    ui = commands.add_parser("ui", help="在非正式端口启动禁用 Manager 的开发 UI")
    ui.add_argument("--port", type=int, default=18770)
    ui.add_argument("--open", action="store_true")
    ui.set_defaults(function=ui_command)
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
