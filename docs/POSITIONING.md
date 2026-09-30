# Positioning: `af_public` vs `af` vs SandFish

Public-facing note for portfolio viewers.

## One-line roles

| Repo | Visibility | Role |
|------|------------|------|
| [`jmiaie/af`](https://github.com/jmiaie/af) | private | **AegisFlow canonical** — where deeper harness work belongs (collaborators only). |
| [`jmiaie/af_public`](https://github.com/jmiaie/af_public) | public | **This repo** — AegisFlow public mirror / release showcase. |
| [`jmiaie/sandfish`](https://github.com/jmiaie/sandfish) | public | **v1 swarm demo** — OMPA-backed simulation + FastAPI. Not AegisFlow. |

There is **no** `github.com/jmiaie/aegisflow` repository.

## Lineage

```
SandFish (v1)  ──►  jmiaie/sandfish (demo)
        │
        └──► AegisFlow (v2) ──► jmiaie/af (canonical, private)
                              └─► jmiaie/af_public (this public mirror)
```

## What belongs where

| Change type | Land in |
|-------------|---------|
| New AegisFlow features | Prefer **af**, then mirror here |
| Public docs / PyPI / community files for AegisFlow | **af_public** |
| SandFish demo hygiene | **sandfish** only |

## Explicit non-goals

- Do not treat this repo and SandFish as the same product.  
- Do not invent live trading / agent-ROI metrics in README copy.
