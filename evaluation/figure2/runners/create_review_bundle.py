"""Build and verify a collaborator ZIP without runtime, secrets or old studies."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "evaluation/figure2"


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Never overwrite a delivered review bundle")
    frozen = json.loads((EVAL / "provenance/freeze.json").read_text())
    required = ["EVAL_MANIFEST.json", "TARGET_MANIFEST.csv", "RUN_MANIFEST.csv", "METRIC_DICTIONARY.csv", "FIGURE2_DATA_LONG.csv", "FIGURE2_SUMMARY.csv", "FAILURE_EVENTS.csv", "PROVENANCE_MANIFEST.csv", "reports/EVAL_PREFLIGHT.md", "reports/FIGURE2_RESULTS_REPORT.md", "reports/FIGURE2_STATISTICAL_REPORT.md", "reports/FIGURE2_MISSING_DATA.md", "reports/FIGURE2_FINAL_AUDIT.md"]
    for relative in required:
        if not (EVAL / relative).is_file():
            raise FileNotFoundError(relative)
    if json.loads((EVAL / "provenance/EVIDENCE_INTEGRITY_AUDIT.json").read_text())["status"] != "passed":
        raise RuntimeError("Evidence integrity did not pass")
    files = {}
    for relative, expected in frozen["source_files"].items():
        data = (ROOT / relative).read_bytes()
        if sha_bytes(data) != expected:
            raise ValueError("Frozen source mismatch: " + relative)
        files[relative] = ROOT / relative
    # Additional repository metadata is identified as captured-at-package-time,
    # not retroactively claimed to be part of the original source freeze.
    extra = [".gitattributes", ".gitignore", ".python-version", "DEVELOPMENT.md", "setup.cfg"]
    for relative in extra:
        if (ROOT / relative).is_file():
            files[relative] = ROOT / relative
    for base in [ROOT / ".github", EVAL]:
        for path in sorted(base.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files[str(path.relative_to(ROOT))] = path
    # Exclude pytest's directory symlink aliases; the referenced real files and
    # all manifest-declared bytes are included by their normal relative paths.
    secret = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-[A-Za-z0-9_-]{25,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")
    suspect = [relative for relative, path in files.items() if secret.search(path.read_bytes())]
    if suspect:
        raise ValueError("Potential credential-like content; review filenames before packaging: " + repr(suspect))
    hashes = {relative: sha_bytes(path.read_bytes()) for relative, path in sorted(files.items())}
    root_name = "EasyDesign-Figure2-audit-results-20260906"
    readme = (EVAL / "reports/READ_ME_FIRST_合作者.md").read_bytes()
    info = {"format": "source-and-evaluation-review-bundle-v1", "frozen_source_sha256": frozen["source_tree_sha256"],
            "frozen_source_files": len(frozen["source_files"]), "additional_repository_metadata": extra + [".github/"],
            "excluded": [".git history", "model weights", "complete runtime databases", "old scientific results", "credentials", "pytest temporary directory aliases"],
            "scientific_main_comparison_complete": False, "gpu_runs": 0, "file_count_before_package_metadata": len(files),
            "credential_scan": "No matches for private-key, OpenAI-key and GitHub-token patterns; not a comprehensive privacy certification"}
    metadata = json.dumps(info, indent=2).encode() + b"\n"
    hashes["READ_ME_FIRST_合作者.md"] = sha_bytes(readme)
    hashes["BUNDLE_MANIFEST.json"] = sha_bytes(metadata)
    sums = "".join(f"{value}  {relative}\n" for relative, value in sorted(hashes.items())).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for relative, path in sorted(files.items()):
            archive.write(path, root_name + "/" + relative)
        archive.writestr(root_name + "/READ_ME_FIRST_合作者.md", readme)
        archive.writestr(root_name + "/BUNDLE_MANIFEST.json", metadata)
        archive.writestr(root_name + "/SHA256SUMS", sums)
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC verification failed")
        for relative, expected in hashes.items():
            if sha_bytes(archive.read(root_name + "/" + relative)) != expected:
                raise ValueError("Archived bytes differ: " + relative)
    receipt = {"archive": args.output.name, "bytes": args.output.stat().st_size, "sha256": sha_bytes(args.output.read_bytes()),
               "verified_payload_files": len(hashes), "zip_crc_checked": True, "all_payload_sha256_checked": True}
    sidecar = args.output.with_suffix(args.output.suffix + ".sha256")
    with sidecar.open("x") as handle:
        handle.write(receipt["sha256"] + "  " + args.output.name + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
