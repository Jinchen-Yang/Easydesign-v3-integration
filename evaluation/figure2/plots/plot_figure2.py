"""Plot only measured diagnostic rows; keep absent primary endpoints visibly empty.

Figure contract: quantitative grid, Python/matplotlib, 180 mm width, editable
PDF/SVG text, >= 6 pt text. The current data establish diagnostic coverage only.
Every main claim remains open. No synthetic numerical outcome enters this plot.
"""
from pathlib import Path
import csv
import json
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "plots"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"], "font.size": 7,
                     "axes.titlesize": 8, "axes.labelsize": 7, "xtick.labelsize": 6, "ytick.labelsize": 6,
                     "legend.fontsize": 6, "svg.fonttype": "none", "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.6,
                     "savefig.facecolor": "white"})
TITLES = {"a": "Time to valid project", "b": "Completion and intervention", "c": "GPCR computational HQ yield",
          "d": "GPCR quality, diversity and biology", "e": "Non-GPCR generalization", "f": "Paired generalization effect",
          "g": "Reliability: contract diagnostics", "h": "Traceability: contract diagnostics"}
REASONS = {"a": "No completed independent end-to-end method episodes. Setup stop times are not turnaround times.",
           "b": "Full / Plain / fixed workflow comparison has not run. Scientific approvals are retained.",
           "c": "No GPCR candidates generated or independently evaluated. Planned: 6 targets, 54 campaigns.",
           "d": "Independent confidence, PAE, geometry and diversity require measured candidate outputs.",
           "e": "Seven standardized target identities selected. No non-GPCR HQ-yield measurements.",
           "f": "No matched scientific campaign pairs. Paired effect and 95% CI are not estimable."}


def data(name):
    with (ROOT / name).open() as handle:
        return list(csv.DictReader(handle))


def panel(ax, letter):
    ax.set_title(f"{letter}  {TITLES[letter]}", loc="left", fontweight="bold", pad=8)
    if letter in REASONS:
        ax.set_axis_off()
        ax.text(0.02, 0.68, "NOT AVAILABLE", color="#686868", fontsize=9, weight="bold", transform=ax.transAxes)
        ax.text(0.02, 0.44, textwrap.fill(REASONS[letter], 48), color="#505050", va="top", linespacing=1.35, transform=ax.transAxes)
        return
    records = [row for row in data("FIGURE2_SUMMARY.csv") if row["panel"] == letter and row["method"] == "easydesign_contract_probe"]
    if not records:
        ax.set_axis_off()
        ax.text(0.05, 0.5, "Contract results unavailable", transform=ax.transAxes)
        return
    values = np.array([[float(row["estimate"])] for row in records])
    ax.imshow(values, cmap=ListedColormap(["#e2a28d", "#bad9dd"]), vmin=0, vmax=1, aspect="auto")
    labels = [row["target_id"].replace("_", " ") for row in records]
    ax.set_yticks(range(len(records)), labels)
    ax.set_xticks([0], ["Frozen code assertions"])
    ax.tick_params(axis="both", length=0)
    for index, row in enumerate(records):
        n = int(row["n_runs"])
        ax.text(0, index, f"{round(float(row['estimate'])*n)}/{n}", ha="center", va="center", fontsize=6)
    ax.set_title(f"{letter}  Contract checks only", loc="left", fontweight="bold", pad=8)
    ax.set_xlabel("Technical replays; Supplementary only", labelpad=7)


def export(fig, stem):
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.svg")
    fig.savefig(OUT / f"{stem}.png", dpi=300)


def main():
    OUT.mkdir(exist_ok=True)
    for letter in "abcdefgh":
        fig, ax = plt.subplots(figsize=(100/25.4, (100 if letter in "gh" else 68)/25.4))
        fig.subplots_adjust(left=0.53 if letter in "gh" else 0.07, right=0.94, top=0.90, bottom=0.16)
        panel(ax, letter)
        export(fig, f"figure2_{letter}")
        plt.close(fig)
    # A planning/contact sheet, explicitly not a finished comparative manuscript figure.
    fig = plt.figure(figsize=(180/25.4, 225/25.4))
    grid = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 1.75], left=0.04, right=0.96, top=0.93, bottom=0.06, wspace=0.18, hspace=0.55)
    for index, letter in enumerate("abcdefgh"):
        ax = fig.add_subplot(grid[index//2, index%2])
        if letter in "gh":
            bounds = ax.get_position()
            ax.set_position([bounds.x0+0.22, bounds.y0, bounds.width-0.22, bounds.height])
        panel(ax, letter)
    fig.text(0.04, 0.984, "EasyDesign Figure 2 | Evidence status, not a completed comparison", fontsize=8, weight="bold", va="top")
    fig.text(0.04, 0.015, "a–f: unmeasured primary endpoints. g–h: deterministic fixture checks, not agent superiority or scientific replay.", fontsize=6)
    export(fig, "figure2_evidence_status")
    plt.close(fig)
    # Real timing evidence, explicitly separated from the main time-to-valid-project endpoint.
    records = [r for r in data("FIGURE2_DATA_LONG.csv") if r["metric_name"] == "setup_probe_wall_time_s" and r["metric_value"] != ""]
    if records:
        names = sorted({r["target_id"] for r in records})
        fig, ax = plt.subplots(figsize=(180/25.4, 70/25.4))
        for index, name in enumerate(names):
            observed = [float(r["metric_value"]) for r in records if r["target_id"] == name]
            offsets = np.linspace(-0.13, 0.13, len(observed))
            ax.scatter(index+offsets, observed, s=13, color="#477f89", edgecolor="white", linewidth=0.3)
        ax.set_xticks(range(len(names)), names, rotation=35, ha="right", rotation_mode="anchor")
        ax.set_ylabel("Setup probe wall time (s)")
        fig.text(0.10, 0.94, "Extended Data | Time until observed stop / review state", fontsize=8, weight="bold")
        fig.text(0.10, 0.885, "Raw technical replays, including immediate input blocks; not time-to-valid-project.", fontsize=6)
        fig.subplots_adjust(left=0.10, right=0.98, bottom=0.25, top=0.78)
        export(fig, "extended_data_setup_timing")
        plt.close(fig)
    (OUT / "plot_manifest.json").write_text(json.dumps({"matplotlib": matplotlib.__version__, "numpy": np.__version__, "main_figure_comparison_complete": False, "missing_value_policy": "label NOT AVAILABLE; no imputation", "uncertainty": "None: technical deterministic replays only; no independent scientific comparison", "source_data": ["FIGURE2_DATA_LONG.csv", "FIGURE2_SUMMARY.csv"]}, indent=2)+"\n")


if __name__ == "__main__":
    main()
