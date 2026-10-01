#!/usr/bin/env python3
"""Plot already-measured results. Matplotlib is used only for the report."""
import argparse
import json
import os
from pathlib import Path
import tempfile

# Keep plotting caches separate from the engine and user configuration.
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ra-matplotlib"))
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default=str(PROJECT_ROOT / "measurements/results.json"))
    parser.add_argument("--out", default=str(PROJECT_ROOT / "measurements/performance.png"), help="output PNG file")
    args = parser.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = json.loads(Path(args.input).read_text())
    records = []
    for row in report["records"]:
        if row["experiment"] == "scale" and row["seconds"] > 0:
            records.append(row)
    if not records:
        raise ValueError("the input contains no positive scale measurements")
    fig, ax = plt.subplots(figsize=(10, 6.4))
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.18, top=0.89)
    for operator in ("join", "select", "project"):
        # Tuples sort by the first item, so these points follow increasing size.
        points = []
        for row in records:
            if row["operator"] == operator:
                points.append((row["n"], row["seconds"]))
        points.sort()
        if not points:
            continue
        slope = report.get("slopes", {}).get(operator)
        label = operator
        if slope is not None:
            label += f" (fitted slope {slope:.3f})"
        sizes = [point[0] for point in points]
        seconds = [point[1] for point in points]
        ax.plot(sizes, seconds, marker="o", linewidth=2, label=label)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    sizes = sorted({row["n"] for row in records})
    ax.set_xticks(sizes, labels=[f"{size:,}" for size in sizes])
    ax.set_xlabel("Tuples per input relation (n = m)", labelpad=10)
    ax.set_ylabel("Measured wall time (seconds)", labelpad=10)
    ax.set_title("Python relational algebra operator performance", loc="left", fontsize=16, pad=18)
    ax.grid(True, which="major", color="#dfe4e9", linewidth=0.8)
    ax.legend(loc="upper left", frameon=False)
    fig.text(0.11, 0.035, "One evaluation per point; loading and parsing excluded; result construction included",
             fontsize=8.5, ha="left", va="bottom")
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    print(target)
    plt.close(fig)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Plot error: {error}")
