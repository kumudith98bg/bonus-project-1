#!/usr/bin/env python3
"""Run real relational-algebra measurements and save progress after each operator."""

import argparse
from datetime import datetime, timezone
import gc
import json
import math
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.language import parse_definitions, parse_query
from source.engine import evaluate
from source.generate import generate_text


DEFAULT_SIZES = [1000, 2000, 4000, 8000, 16000, 32000, 64000]


def now():
    return datetime.now(timezone.utc).isoformat()


def log_log_slope(points):
    """Fit a straight line after converting both axes to logarithms."""
    if len(points) < 2:
        return None
    xs = [math.log(point["n"]) for point in points]
    ys = [math.log(point["seconds"]) for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    return numerator / denominator if denominator else None


def save(report, directory):
    report["updated_at"] = now()
    report["slopes"] = {}
    for operator in ("join", "select", "project"):
        points = []
        for row in report["records"]:
            if row["experiment"] == "scale" and row["operator"] == operator:
                points.append(row)
        report["slopes"][operator] = log_log_slope(points)
    (directory / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_one(experiment, operator, n, m, match_rate, relations, query):
    ast = parse_query(query)
    gc.collect()
    started = perf_counter()
    result = evaluate(ast, relations)
    seconds = perf_counter() - started
    # Each benchmark query runs exactly one operator.
    examined = result["stats"][0]["examined"]
    if operator == "join" and examined != n * m:
        raise ValueError(f"join counter {examined} does not equal {n} * {m}")
    if operator == "select" and examined != n:
        raise ValueError(f"selection counter {examined} does not equal {n}")
    output_rows = len(result["relation"].rows)
    return {
        "experiment": experiment,
        "operator": operator,
        "n": n,
        "m": m,
        "requested_match_rate": match_rate,
        "actual_matches_per_r": output_rows / n if operator == "join" else None,
        "examined": examined,
        "seconds": seconds,
        "output_rows": output_rows,
        "counters": result["stats"],
    }


def run_benchmark(sizes=None, out=None, match_rate=1, match_size=4000, match_rates=None):
    if sizes is None:
        sizes = DEFAULT_SIZES
    if match_rates is None:
        match_rates = [0, 1, 4, 16]
    for n in list(sizes) + [match_size]:
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise ValueError("input sizes must be positive integers")
    for rate in [match_rate] + list(match_rates):
        if not math.isfinite(rate) or rate < 0:
            raise ValueError("match rates must be finite nonnegative numbers")
    if not sizes:
        raise ValueError("at least one measurement size is required")
    if any(match_rate > n for n in sizes) or any(rate > match_size for rate in match_rates):
        raise ValueError("a requested match rate exceeds its input size")
    # Keep default output inside this project, regardless of the shell directory.
    if out is None:
        directory = PROJECT_ROOT / "measurements"
    else:
        directory = Path(out).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "started_at": now(),
        "complete": False,
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "cpu": platform.processor() or "unknown",
            "logical_cpus": os.cpu_count(),
        },
        "runtime": {
            "language": "Python",
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "method": {
            "timings": "One measured evaluation per operator per size, after two small warmups per operator. Generation, parsing, explicit collection and file I/O excluded; output materialization included.",
            "join": "Every pair is evaluated by the nested-loop implementation. The reported count comes from its actual operator counter.",
            "selection": "select[a>=floor(n/2)](R); approximately half the input survives.",
            "projection": "project[b](R); output cardinality depends on repeated generated keys.",
        },
        "options": {
            "sizes": list(sizes),
            "match_rate": match_rate,
            "match_size": match_size,
            "match_rates": list(match_rates),
        },
        "records": [],
    }
    save(report, directory)
    warm = parse_definitions(generate_text(250, 250, 1))
    for query in ("R join[R.b=S.b] S", "select[a>=125](R)", "project[b](R)"):
        ast = parse_query(query)
        evaluate(ast, warm)
        evaluate(ast, warm)
    for n in sizes:
        relations = parse_definitions(generate_text(n, n, match_rate))
        queries = [
            ("join", "R join[R.b=S.b] S"),
            ("select", f"select[a>={n // 2}](R)"),
            ("project", "project[b](R)"),
        ]
        for operator, query in queries:
            print(f"Running {operator}: n={n}, m={n}, match rate={match_rate}", flush=True)
            record = run_one("scale", operator, n, n, match_rate, relations, query)
            report["records"].append(record)
            save(report, directory)
            print(f'  {record["seconds"]:.6f} s; examined={record["examined"]}; output={record["output_rows"]}', flush=True)
    for rate in match_rates:
        relations = parse_definitions(generate_text(match_size, match_size, rate))
        print(f"Running match-rate comparison: n={match_size}, rate={rate}", flush=True)
        record = run_one("match-rate", "join", match_size, match_size, rate, relations, "R join[R.b=S.b] S")
        report["records"].append(record)
        save(report, directory)
        print(f'  {record["seconds"]:.6f} s; examined={record["examined"]}; output={record["output_rows"]}', flush=True)
    report["complete"] = True
    report["finished_at"] = now()
    save(report, directory)
    print(f"Saved actual measurements to {directory}", flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default=",".join(str(n) for n in DEFAULT_SIZES), help="comma-separated input sizes")
    parser.add_argument("--out", default=None, help="results directory (default: python_version/measurements)")
    parser.add_argument("--match-rate", type=float, default=1, help="main experiment match rate")
    parser.add_argument("--match-size", type=int, default=4000, help="match-rate experiment input size")
    parser.add_argument("--match-rates", default="0,1,4,16", help="comma-separated rates to compare")
    args = parser.parse_args(argv)
    try:
        sizes = [int(value) for value in args.sizes.split(",")]
        rates = [float(value) for value in args.match_rates.split(",")]
        run_benchmark(sizes, args.out, args.match_rate, args.match_size, rates)
    except (ValueError, OSError, OverflowError) as error:
        print(f"Benchmark error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
