#!/usr/bin/env python3
"""Add authoritative SHA-256 fragments to tracked Conda explicit locks."""

from __future__ import annotations

import bz2
import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse


def _identity(url: str) -> tuple[str, str, str, str, str]:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if parsed.netloc == "conda.anaconda.org" and len(parts) >= 3:
        owner = parts[0]
        basename = "/".join(parts[-2:])
    elif parsed.netloc == "repo.anaconda.com" and parts[:2] == ["pkgs", "main"]:
        owner = "anaconda"
        basename = "/".join(parts[-2:])
    else:
        raise RuntimeError(f"unsupported canonical Conda URL: {url}")
    filename = parts[-1]
    stem = filename.removesuffix(".conda").removesuffix(".tar.bz2")
    try:
        package_name, _version, _build = stem.rsplit("-", 2)
    except ValueError as error:
        raise RuntimeError(f"cannot parse Conda filename: {filename}") from error
    repodata_base = url.rsplit("/", 1)[0]
    return owner, package_name, basename, repodata_base, filename


def _package_hashes(key: tuple[str, str]) -> dict[str, str]:
    owner, package_name = key
    url = (
        "https://api.anaconda.org/package/"
        f"{quote(owner, safe='')}/{quote(package_name, safe='')}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "EasyDesign-lock/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    hashes: dict[str, str] = {}
    for item in payload.get("files", []):
        basename = item.get("basename")
        sha256 = item.get("sha256")
        if (
            isinstance(basename, str)
            and isinstance(sha256, str)
            and len(sha256) == 64
        ):
            hashes[basename] = sha256
    return hashes


def _repodata_hashes(base_url: str, filenames: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in ("current_repodata", "repodata"):
        url = f"{base_url}/{name}.json.bz2"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "EasyDesign-lock/0.1"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(bz2.decompress(response.read()))
        for section in ("packages.conda", "packages"):
            records = payload.get(section, {})
            for filename in filenames - found.keys():
                record = records.get(filename)
                if isinstance(record, dict):
                    sha256 = record.get("sha256")
                    if isinstance(sha256, str) and len(sha256) == 64:
                        found[filename] = sha256
        if filenames <= found.keys():
            break
    return found


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock_root = root / "environments" / "locks"
    explicit_paths = tuple(sorted(lock_root.glob("*.conda-lock.txt")))
    identities: dict[str, tuple[str, str, str, str, str]] = {}
    package_keys: set[tuple[str, str]] = set()
    for path in explicit_paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("https://"):
                continue
            canonical_url = line.rsplit("#", 1)[0]
            identity = _identity(canonical_url)
            identities[canonical_url] = identity
            package_keys.add(identity[:2])

    package_files: dict[tuple[str, str], dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(_package_hashes, key): key for key in package_keys}
        for future in as_completed(futures):
            key = futures[future]
            package_files[key] = future.result()

    repodata_missing: dict[str, set[str]] = {}
    for owner, package_name, basename, repodata_base, filename in identities.values():
        if package_files[(owner, package_name)].get(basename) is None:
            repodata_missing.setdefault(repodata_base, set()).add(filename)
    repodata_files = {
        base_url: _repodata_hashes(base_url, filenames)
        for base_url, filenames in sorted(repodata_missing.items())
    }

    missing: list[str] = []
    rendered_by_path: dict[Path, list[str]] = {}
    for path in explicit_paths:
        rendered: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("https://"):
                rendered.append(raw)
                continue
            canonical_url = line.rsplit("#", 1)[0]
            owner, package_name, basename, repodata_base, filename = identities[
                canonical_url
            ]
            sha256 = package_files[(owner, package_name)].get(basename)
            if sha256 is None:
                sha256 = repodata_files.get(repodata_base, {}).get(filename)
            if sha256 is None:
                missing.append(f"{owner}/{package_name}/{basename}")
                rendered.append(raw)
            else:
                rendered.append(f"{canonical_url}#{sha256}")
        rendered_by_path[path] = rendered
    if missing:
        print("missing Conda package hashes:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    for path, rendered in rendered_by_path.items():
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text("\n".join(rendered) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    for descriptor in sorted(lock_root.glob("*.lock.json")):
        payload = json.loads(descriptor.read_text(encoding="utf-8"))
        explicit = root / payload["conda_explicit"]
        payload["conda_explicit_sha256"] = hashlib.sha256(
            explicit.read_bytes()
        ).hexdigest()
        temporary = descriptor.with_suffix(descriptor.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
