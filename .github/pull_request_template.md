## Motivation
<!-- Why this change? Link the issue (Fixes #...). -->

## Summary
<!-- What does this PR do? Architecture diagram or bullet list. -->

## Test plan
- [ ] `ruff check .` clean
- [ ] `mypy aegisflow` clean
- [ ] `pytest -q` green
- [ ] `python benchmarks/bench_core.py` — paste the delta vs baseline if anything in `orchestration/`, `memory/`, `sandbox/`, or `brain/` changed:
  ```
  metric       baseline   this PR   Δ
  ```
- [ ] Added/updated tests for new behaviour or bug-fix

## Risk
<!-- Worst-case impact. Rollback procedure. Are there migrations? -->

## Documentation
- [ ] README updated (if user-visible)
- [ ] `CHANGELOG.md` `[Unreleased]` entry added
- [ ] `ARCHITECTURE.md` / `BENCHMARKS.md` / `SECURITY.md` updated where relevant

## Screenshots / output samples
<!-- Optional but encouraged. -->
