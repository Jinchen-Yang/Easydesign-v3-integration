#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

BASELINE = "c8545570b30d279fa05b1fbb56a64e86e7c59291"
PREFIX = "evaluation/figure2_benchbb/"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--baseline", default=BASELINE)
    p.add_argument("--require-clean", action="store_true")
    a = p.parse_args()
    repo = a.repo.resolve()
    git(repo, "cat-file", "-e", f"{a.baseline}^{{commit}}")
    changed = set(filter(None, git(repo, "diff", "--name-only", a.baseline, "--").splitlines()))
    status = git(repo, "status", "--porcelain", "--untracked-files=all")
    for line in status.splitlines():
        changed.add(line[3:].split(" -> ")[-1])
    bad = sorted(x for x in changed if not x.startswith(PREFIX))
    if bad:
        raise SystemExit("Agent baseline violation:\n" + "\n".join(bad))
    if a.require_clean and status:
        raise SystemExit("Working tree is not clean:\n" + status)
    print(f"PASS agent baseline {a.baseline}; evaluation-only changes={len(changed)}")


if __name__ == "__main__":
    main()
