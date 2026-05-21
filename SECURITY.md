# Security Policy — AegisFlow

## Supported versions

| Version    | Status      | Patches |
|------------|-------------|---------|
| `0.3.x`    | Current     | Yes     |
| `0.2.x`    | Best-effort | Critical only |
| `< 0.2`    | Unsupported | No      |

## Reporting a vulnerability

Please **do not** open public GitHub issues for security findings.

- Preferred: open a private security advisory at <https://github.com/jmiaie/af/security/advisories/new>
- Backup: email the maintainers (`jarv@micap.ai`) with the subject `[AegisFlow security]`.

Response targets:

| Phase                          | Target           |
|--------------------------------|------------------|
| Acknowledgement                | within 3 days    |
| Triage + severity decision     | within 7 days    |
| Patch for High/Critical        | within 30 days   |
| Public advisory                | after coordinated release |

## Scope

In scope:
- `aegisflow.*` Python modules
- `Dockerfile` / `docker-compose.yml`
- The bundled `.skill` archives in this repo

Out of scope:
- Vulnerabilities in upstream dependencies (`ompa`, `fastapi`, `uvicorn`, `pydantic`) — please report those upstream. We will pull patched versions promptly.
- Denial-of-service against `LocalSandbox` from a trusted local caller (use a process supervisor / cgroups for that).

## Dependency scanning posture

- `bandit` and `safety` are declared in the `dev` extras and **will be wired into CI** as part of the institutional upgrade (`upgrade_plan.md` item 3).
- Dependabot / Renovate is recommended but not yet enabled.

## 1-page threat model

### Assets

- **Vault contents** (markdown notes, KG triples): may contain PII, business plans, model outputs.
- **Sandbox workspace**: holds intermediate artefacts that may be sensitive.
- **LLM credentials** (`OPENAI_API_KEY` etc.): high-impact if leaked.

### Trust boundaries

```
[ user prompt / IM channel ]  ──►  LeadOrchestrator
                                    │
       (untrusted text)             ▼
                              [ LLM provider ]   ◄── credentials
                                    │
                              (LLM-generated commands & content)
                                    ▼
                              SubAgent.execute
                                    │
                                    ▼
                              LocalSandbox.write_file   ──►  filesystem (scoped path)
                                    │
                                    ▼
                              MemoryVault.store_verbatim ──►  markdown vault
```

### Threats and mitigations

| # | Threat                                                                                  | Mitigation today                                          | Gap                                              |
|--:|-----------------------------------------------------------------------------------------|-----------------------------------------------------------|--------------------------------------------------|
| 1 | Prompt injection causes the LLM to emit a path-escaping `write_file("..\\..\\etc\\…")`. | `LocalSandbox` joins paths under `workspace_path`.        | No explicit `pathlib.Path.resolve()`-vs-`workspace_path` containment check; symlink escape unverified. |
| 2 | Credential exfiltration through synthesised content.                                    | Credentials are read from env only; never echoed.         | No outbound-content scanning. Consider a guardrail middleware. |
| 3 | Sub-agent ignores task scope and triggers a follow-up LLM call costing money.            | `max_agents` cap; `max_tokens=2048` per call.             | No global $-cap; budget per session not enforced. |
| 4 | Vault contents accessed by a process on the same host.                                  | OS-level filesystem permissions only.                     | Encryption-at-rest is out of scope at v0.3.       |
| 5 | Memory-graph poisoning via `add_triple` from a malicious sub-agent.                     | KG is in-memory and rebuilt from vault on start.          | Vault writes by sub-agents are not signed or attributed; provenance is implicit. |
| 6 | Dependency-chain compromise (e.g., typosquatted `ompa`).                                | Pinned name and version range.                            | No SLSA provenance or signed wheels yet.          |
| 7 | Logged prompts leak PII to disk / observability tooling.                                | Logger is opt-in; `INFO` truncates to 80 chars in `SubAgent.execute`. | No structured PII redaction; consider a redactor. |

### Out-of-the-box hardening recommendations for operators

1. Run AegisFlow inside a container; treat `LocalSandbox` only as a path scope.
2. Set a hard `max_agents` and a wall-clock timeout per session.
3. Keep `OPENAI_API_KEY` in a secrets manager — never check it into the vault.
4. If integrating IM channels (like DeerFlow does), bind to 127.0.0.1 unless an authentication gateway is in front.
