# Contributing to AegisFlow

Thanks for your interest. This document is the contract between you and the maintainers.

## Quick path

```bash
git clone https://github.com/jmiaie/af.git aegisflow
cd aegisflow
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# before pushing
ruff check .
mypy aegisflow
pytest -q
python benchmarks/bench_core.py  # ensures no perf regression locally
```

## Workflow

1. **Open an issue first** for anything bigger than a typo or a one-line bugfix. State the problem, the proposed approach, and the trade-offs.
2. **Branch from `main`** with a descriptive name (`feat/...`, `fix/...`, `perf/...`).
3. **Commit messages** follow Conventional Commits (`feat:`, `fix:`, `perf:`, `docs:`, `test:`, `chore:`). The body explains *why*, not *what*.
4. **PR template** must be filled in (motivation, summary, test plan, screenshots if relevant, risk).
5. **CI must be green** — lint, type-check, tests, benchmark regression gate.
6. **CHANGELOG.md** — add an entry under `[Unreleased]` for anything user-visible.

## Code style

- `ruff` config in `pyproject.toml` is the source of truth; line length 100.
- `mypy` strict on the public surface (`disallow_untyped_defs = true`).
- Public functions need a docstring with a one-line summary, args, and returns.
- Avoid new top-level dependencies unless justified in the PR description.

## Tests

- New behaviour must come with a test. Bug fixes start with a failing test that the fix makes pass.
- Place tests in `tests/test_<module>.py`. Async tests use `pytest-asyncio` (`asyncio_mode = "auto"`).
- Property-based tests with Hypothesis are welcome for the brain extractors.

## Benchmarks

If you change anything in `orchestration/`, `memory/`, `sandbox/`, or `brain/`, run
`benchmarks/bench_core.py` before and after and paste the relevant deltas into your PR
description. Regressions over 20 % on any p95 must be justified.

## Releasing (maintainers)

1. Bump version in `pyproject.toml`.
2. Move `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md`.
3. Tag `vX.Y.Z` and push tags.
4. CI release workflow builds the wheel + Docker image.

## Code of Conduct

By participating you agree to [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
