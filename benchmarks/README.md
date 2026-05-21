# benchmarks/

This is the staging location for the benchmark harness layout under the institutional
upgrade. The live harness already lives at the repo root in `benchmarks/bench_core.py`
and at `aegisflow/benchmarks/run_all.py`. This directory documents *what* should be
measured, *how*, and the planned CI regression gate.

## What to measure

The repo classifies as a **software library / SDK**, so the spec requires:

| Dimension                    | Metric                                                                 | Where today                          |
|------------------------------|------------------------------------------------------------------------|--------------------------------------|
| **Performance** (micro)      | ops/sec, p50/p95/p99, peak memory for each public surface              | `benchmarks/bench_core.py`           |
| **Performance** (e2e w/ LLM) | wall-clock decompose / sub-agents / synthesis                          | `aegisflow/benchmarks/run_all.py`    |
| **Reliability**              | Test coverage %, fuzz hours (Hypothesis on `signal_detector`)          | **TODO** (pytest-cov in CI)          |
| **API stability**            | Public symbols list + diff per release                                 | **TODO** (`scripts/api_surface.py`)  |
| **Build matrix**             | OS × Python                                                            | `.github/workflows/ci.yml`           |
| **Footprint**                | Wheel size, cold-start time, process RSS                               | `benchmarks/bench_core.py` §memory_footprint |

See [`../BENCHMARKS.md`](../BENCHMARKS.md) for current numbers.

## How to run locally

```bash
# Control-plane (deterministic, no network)
python benchmarks/bench_core.py --output benchmarks/latest.json --markdown benchmarks/latest.md --profile

# LLM-integrated (needs Ollama on localhost:11434 with `llama3.2:1b` or similar)
python -m aegisflow.benchmarks.run_all
```

## Regression policy (planned — institutional upgrade item 5)

A `benchmarks/regress.py` script (already drafted inline inside `.github/workflows/ci.yml`)
will fail CI when any `p95_ms` value drifts more than **20 %** worse than
`benchmarks/baseline.json`. The threshold is intentionally generous to absorb
noise on shared CI runners; it can be tightened to 10 % once a dedicated Linux
benchmark runner is provisioned (audit §5.4).

## Starter regression script (drop-in)

```python
# benchmarks/regress.py
"""Fail CI on > 20 % p95 regression vs benchmarks/baseline.json."""
import json
import pathlib
import sys

TOL = 1.20

def walk_p95(b, c, path=""):
    fails = []
    if isinstance(b, dict) and isinstance(c, dict):
        for k in b:
            if k in c:
                fails.extend(walk_p95(b[k], c[k], f"{path}.{k}"))
        return fails
    if path.endswith("p95_ms") and isinstance(b, (int, float)) and isinstance(c, (int, float)) and b > 0:
        if c > b * TOL:
            fails.append((path, b, c, c / b - 1))
    return fails

if __name__ == "__main__":
    here = pathlib.Path(__file__).parent
    baseline = json.loads((here / "baseline.json").read_text())
    current  = json.loads((here / "latest.json").read_text())
    fails = walk_p95(baseline, current)
    for p, b, c, d in fails:
        print(f"REGRESSION  {p}: {b:.3f} -> {c:.3f}  ({d*100:+.1f}%)")
    sys.exit(1 if fails else 0)
```

## Linux reference job (planned)

`.github/workflows/ci.yml` `benchmark-regression` runs on `ubuntu-latest`; this is
the future home of the Linux reference numbers called out in
`docs/PERFORMANCE_AUDIT.md` §5.4. Once stable, the Linux JSON / Markdown will be
committed under `benchmarks/linux-latest.{json,md}` for cross-platform delta visibility.
