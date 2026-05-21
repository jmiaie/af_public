#!/usr/bin/env python3
"""
AegisFlow Performance Regression Gate
Compares microbenchmarks against baseline.json to prevent performance regressions.
"""

import argparse
import json
import sys
from pathlib import Path


def walk_and_compare(baseline_data, candidate_data, path="", tolerance=1.20):
    """
    Recursively compares baseline and candidate measurements.
    Returns a list of tuples: (metric_path, baseline_val, candidate_val, percentage_diff)
    """
    fails = []

    if isinstance(baseline_data, dict) and isinstance(candidate_data, dict):
        for key in baseline_data:
            if key in candidate_data:
                fails.extend(
                    walk_and_compare(
                        baseline_data[key],
                        candidate_data[key],
                        f"{path}.{key}" if path else key,
                        tolerance,
                    )
                )
        return fails

    # We gate on p95_ms values
    if path.endswith("p95_ms") and isinstance(baseline_data, (int, float)) and isinstance(candidate_data, (int, float)):
        if baseline_data > 0 and candidate_data > baseline_data * tolerance:
            diff = (candidate_data / baseline_data) - 1.0
            fails.append((path, baseline_data, candidate_data, diff))

    return fails


def main():
    parser = argparse.ArgumentParser(description="AegisFlow Benchmark Regression Gate")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("benchmarks/baseline.json"),
        help="Path to baseline benchmark JSON file",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=Path("benchmarks/latest.json"),
        help="Path to candidate benchmark JSON file to check",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=20.0,
        help="Percentage regression tolerated (e.g., 20.0 for 20%)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("        AEGISFLOW PERFORMANCE REGRESSION GATE        ")
    print("=" * 60)
    print(f"Baseline file  : {args.baseline}")
    print(f"Candidate file : {args.candidate}")
    print(f"Tolerance      : +{args.tolerance:.1f}%")
    print("-" * 60)

    if not args.baseline.exists():
        print(f"ERROR: Baseline file '{args.baseline}' does not exist.")
        sys.exit(1)

    if not args.candidate.exists():
        print(f"ERROR: Candidate file '{args.candidate}' does not exist.")
        sys.exit(1)

    try:
        baseline_data = json.loads(args.baseline.read_text())
        candidate_data = json.loads(args.candidate.read_text())
    except Exception as e:
        print(f"ERROR: Failed to parse benchmark JSON files: {e}")
        sys.exit(1)

    multiplier = 1.0 + (args.tolerance / 100.0)
    regressions = walk_and_compare(baseline_data, candidate_data, tolerance=multiplier)

    if regressions:
        print("[ REGRESSION DETECTED ]")
        print("-" * 60)
        for path, b_val, c_val, diff in regressions:
            print(f"Metric: {path}")
            print(f"  - Baseline  : {b_val:.3f} ms")
            print(f"  - Candidate : {c_val:.3f} ms")
            print(f"  - Delta     : {diff * 100:+.1f}%")
            print()
        print("-" * 60)
        print("Result: FAILED (one or more metrics exceeded performance tolerance)")
        sys.exit(1)
    else:
        print("[ SUCCESS ] All p95 metrics are within tolerance limits.")
        print("-" * 60)
        print("Result: PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
