# Changelog

All notable changes to AegisFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-04-26

### Added
- **Protocol contracts** (`core/protocols.py`): Formal `LLMProvider`, `SandboxProvider`, `MemoryProvider`, and `Tool` protocols (runtime-checkable via `typing.Protocol`)
- **Error taxonomy** (`core/errors.py`): Structured exception hierarchy with machine-readable `code` and `retryable` fields — `AegisFlowLLMError`, `AegisFlowSandboxError`, `AegisFlowMemoryError`, `AegisFlowOrchestrationError`
- **CLI entrypoint** (`__main__.py`): `aegisflow doctor`, `aegisflow bench`, `aegisflow run`, `aegisflow version` commands
- **PyPI readiness**: `py.typed` marker, `CHANGELOG.md`, `[project.scripts]` in pyproject.toml
- Structured HTTP error classification in `OpenAICompatibleLLM` — 401→AuthError, 429→RateLimitError, 5xx→ProviderError
- **Institutional Repository Hygiene**: Added standard `LICENSE` (MIT), complete community and governance structures (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.github/CODEOWNERS`, pull request and issue templates)
- **Security Policy & Threat Model** (`SECURITY.md`): Established a clear vulnerability disclosure policy, supported versions, and a robust 1-page Threat Model detailing trust boundaries and isolation scopes
- **Performance Regression Gate** (`benchmarks/regress.py`): Built a standalone regression gate enforcing a ≤20% p95 execution time margin
- **Continuous Integration Workflow** (`.github/workflows/ci.yml`): Formulated multi-OS build and test automation, strict code coverage gating, security checks, and benchmark regression runs
- **Reproducible Lockfile** (`uv.lock`): Sealed package environment via `uv` lockfile to guarantee consistent environment replication

### Changed
- Sandbox path-traversal errors now raise `SandboxPermissionError` (subclass of `AegisFlowSandboxError`) instead of generic `PermissionError`
- `pyproject.toml` URLs updated to correct GitHub repo (`jmiaie/af`)
- Added Python 3.13/3.14 classifiers and `Typing :: Typed` classifier

## [0.2.0] — 2026-04-26

### Added
- **Async sub-agent execution** (`delegate_and_run_async`) — 3-5× speedup on real LLM workloads via `asyncio.gather`
- **LLM provider registry** — `AgenticLLM.register()` / `AgenticLLM.available_backends()` with 6 auto-registered providers (gemini, ollama, nvidia + proxy variants)
- **Fallback-rate counter** on `LeadOrchestrator` — surfaces when LLM decomposition degrades to rule-based
- **Comprehensive test suite** — 6 → 73 tests covering brain, analytics, LLM, sandbox, async orchestration
- Path-traversal protection for `NamespaceSandbox` and `DockerSandbox`

### Fixed
- `REQUIRED_FRONTatter` → `REQUIRED_FRONTMATTER` typo in `doctor.py`
- `MemoryChunk.created_at` timestamp: `%M:%M` → `%M:%S`
- Inline `__import__("re")` → proper module import in `doctor.py`
- Version mismatch: `pyproject.toml` aligned to `0.2.0`
- Whitepaper title: "SandFish" → "AegisFlow"

### Removed
- Empty `cc-lens/` and `gbrain/` directories

## [0.1.0] — 2026-04-15

### Added
- Initial scaffold: core architecture, memory vault, knowledge graph, sandbox layer
- LLM connector layer: OpenAI-compatible, Ollama, Gemini, NVIDIA adapters
- Docker-grade namespace isolation
- GBrain brain layer port: BrainFirstLookup, SignalDetector, BrainDoctor
- CC-Lens analytics port: pricing, tool categories, session analytics, MTB
- Benchmark suite (control-plane + LLM-integrated)
- 3 shipped performance optimizations: `_known_dirs` cache, `store_verbatim` fix, KG dict indices
