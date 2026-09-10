"""Render and capture figure QA using the installed nature-figure tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

EVAL = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-scripts", type=Path, required=True)
    args = parser.parse_args()
    output = EVAL / "provenance/plot-qa"
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(EVAL / "plots/plot_figure2.py")], check=True)
    source_check = subprocess.run([sys.executable, str(args.skill_scripts / "validate_figure.py"), str(EVAL / "plots/plot_figure2.py"), "--json"], capture_output=True, text=True, check=True)
    (output / "source-validation.json").write_text(source_check.stdout)
    audits = []
    for path in sorted((EVAL / "plots").glob("*.pdf")):
        result = subprocess.run([sys.executable, str(args.skill_scripts / "audit_pdf_text.py"), str(path), "--min-pt", "5", "--json"], capture_output=True, text=True)
        (output / f"{path.stem}.json").write_text(result.stdout)
        audits.append({"plot": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "returncode": result.returncode})
    (output / "summary.json").write_text(json.dumps(audits, indent=2) + "\n")
    print(json.dumps({"audited_pdfs": len(audits), "failed_pdfs": sum(r["returncode"] != 0 for r in audits)}))
    if any(r["returncode"] != 0 for r in audits):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
