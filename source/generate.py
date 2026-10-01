#!/usr/bin/env python3
"""Generate deterministic relations R(a,b) and S(b,c), using only the stdlib."""

import argparse
import math
from pathlib import Path
import sys


def generate_text(n, m=None, match_rate=1):
    """Return relation definitions with unique row ids and controllable matches.

    S keys share buckets of approximately match_rate rows; R cycles over the
    corresponding keys. The last bucket can be smaller, so the rate is a target,
    not an exact promise for every combination of sizes. Rates below one leave
    unmatched keys. Rate zero uses disjoint keys on the two sides.
    """
    if m is None:
        m = n
    for name, count in (("n", n), ("m", m)):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if (isinstance(match_rate, bool)
            or not isinstance(match_rate, (int, float))
            or not math.isfinite(match_rate) or match_rate < 0):
        raise ValueError("match rate must be a finite nonnegative number")
    if m and match_rate > m:
        raise ValueError("match rate cannot exceed the number of tuples in S")

    buckets = math.ceil(m / match_rate) if match_rate and m else 1
    lines = [
        f"// Deterministic data: n={n}, m={m}, requested match rate={match_rate}",
        "R (a, b) = {",
    ]
    for index in range(n):
        key = index % buckets if match_rate else -1
        lines.append(f"{index}, {key}")
    lines.extend(["}", "", "S (b, c) = {"])
    for index in range(m):
        key = math.floor(index / match_rate) if match_rate else index
        lines.append(f"{key}, {index}")
    lines.extend(["}", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1000, help="number of R rows (default: 1000)")
    parser.add_argument("--m", type=int, help="number of S rows (default: n)")
    parser.add_argument("--match-rate", type=float, default=1, help="approximate S matches per R row (default: 1)")
    parser.add_argument("--out", type=Path, help="output file; omit to print relation definitions")
    args = parser.parse_args(argv)
    try:
        content = generate_text(args.n, args.m, args.match_rate)
        if args.out is None:
            sys.stdout.write(content)
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(content, encoding="utf-8")
            m = args.n if args.m is None else args.m
            print(f"Wrote {args.n} R tuples and {m} S tuples to {args.out.resolve()}")
    except (ValueError, OverflowError, OSError) as error:
        print(f"Generator error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
