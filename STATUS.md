# Status — af_public (AegisFlow public mirror)

**Updated:** 2026-09-30 (PT)  
**Visibility:** public  
**Maturity:** product / duplicate-public-mirror  
**Role:** public discoverability + release showcase for AegisFlow — **not** the SandFish demo

## Honest positioning

| Repo | Role |
|------|------|
| [`af`](https://github.com/jmiaie/af) | **Canonical private** AegisFlow (deeper work) |
| **this repo (`af_public`)** | Public mirror / PyPI-oriented showcase (`aegisflow` **0.3.0**) |
| [`sandfish`](https://github.com/jmiaie/sandfish) | Public **v1 swarm demo** — separate product line |

See [`docs/POSITIONING.md`](docs/POSITIONING.md).

Offline check (2026-09-30, box): `pytest -q` → **95 passed**.

## Drift note

Private `af` is still on **0.2.0** in tree. Tips are **not** assumed identical. Prefer documenting sync decisions over silent dual-maintenance. Clone URLs for public viewers should use **this** remote (`jmiaie/af_public`), not private `af`.

## What is **not** claimed

- That CI coverage badges are live metrics (several README badges were placeholders)  
- Interchangeability with SandFish  
- Invented production uptime / customer counts

## Next (owner)

1. Keep as portfolio showcase **or** archive if `af` alone is enough  
2. Align with private `af` on a deliberate cadence  
3. Do not port AegisFlow features into sandfish
