# AegisFlow Control-Plane Benchmark Report

**Generated:** 2026-04-16 04:02:58  
**Python:** 3.14.4  
**Platform:** Windows-11-10.0.26100-SP0  
**Hardware:** 16 vCPU (8 physical), 31.7GB RAM  

## Executive Summary

| KPI | Value |
|-----|-------|
| Startup (mean) | 2.77 ms |
| Startup (p95) | 24.40 ms |
| Vault writes | 5,376 ops/sec (p95 0.276 ms) |
| KG add_triple | 1,198,265 ops/sec (p95 0.0016 ms) |
| KG query_entity | mean 0.011 ms / p95 0.021 ms |
| Sandbox I/O | 678 cycles/sec (p95 2.468 ms) |
| Orchestration (mock LLM) | 2.07 ms/task, 3.0 agents/task |
| Memory per vault | 17.06 KB (tracemalloc) |
| Process RSS (end of suite) | 39.7 MB |

## Raw JSON

```json
{
  "_meta": {
    "generated_at": "2026-04-16 04:02:58",
    "system": {
      "python": "3.14.4",
      "platform": "Windows-11-10.0.26100-SP0",
      "machine": "AMD64",
      "cpu_logical": 16,
      "cpu_physical": 8,
      "ram_total_gb": 31.7,
      "ram_avail_gb": 12.9
    },
    "suite": "aegisflow.benchmarks.bench_core"
  },
  "startup": {
    "samples": 20,
    "mean_ms": 2.7733,
    "median_ms": 1.5557,
    "p95_ms": 24.3966,
    "p99_ms": 24.3966,
    "min_ms": 1.3752,
    "max_ms": 24.3966,
    "stdev_ms": 4.9696
  },
  "vault_writes": {
    "operations": 2000,
    "total_seconds": 0.372,
    "ops_per_sec": 5376.0,
    "samples": 2000,
    "mean_ms": 0.186,
    "median_ms": 0.1688,
    "p95_ms": 0.2757,
    "p99_ms": 0.3745,
    "min_ms": 0.1377,
    "max_ms": 1.5808,
    "stdev_ms": 0.0642
  },
  "knowledge_graph": {
    "add": {
      "operations": 10000,
      "total_seconds": 0.008,
      "ops_per_sec": 1198265.0,
      "samples": 10000,
      "mean_ms": 0.0008,
      "median_ms": 0.0007,
      "p95_ms": 0.0016,
      "p99_ms": 0.0026,
      "min_ms": 0.0005,
      "max_ms": 0.2551,
      "stdev_ms": 0.0031
    },
    "query": {
      "operations": 500,
      "entities_in_graph": 200,
      "triples_in_graph": 10000,
      "samples": 500,
      "mean_ms": 0.0106,
      "median_ms": 0.0079,
      "p95_ms": 0.0206,
      "p99_ms": 0.0315,
      "min_ms": 0.0067,
      "max_ms": 0.0556,
      "stdev_ms": 0.0058
    }
  },
  "sandbox_io": {
    "cycles": 1000,
    "total_seconds": 1.475,
    "cycles_per_sec": 678.0,
    "samples": 1000,
    "mean_ms": 1.4747,
    "median_ms": 1.362,
    "p95_ms": 2.4682,
    "p99_ms": 3.0031,
    "min_ms": 0.866,
    "max_ms": 3.7354,
    "stdev_ms": 0.465
  },
  "orchestration": {
    "tasks": 50,
    "total_sub_agents": 150,
    "avg_sub_agents_per_task": 3.0,
    "samples": 50,
    "mean_ms": 2.0731,
    "median_ms": 1.843,
    "p95_ms": 3.8375,
    "p99_ms": 5.2091,
    "min_ms": 1.1182,
    "max_ms": 5.2091,
    "stdev_ms": 0.8426
  },
  "memory_footprint": {
    "vaults_constructed": 100,
    "kg_triples": 5000,
    "sandboxes_constructed": 100,
    "tracemalloc_total_mb": 1.666,
    "tracemalloc_per_vault_kb": 17.06,
    "process_rss_mb": 39.7
  }
}
```