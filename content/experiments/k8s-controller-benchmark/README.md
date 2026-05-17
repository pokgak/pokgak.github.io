# k8s-controller-benchmark

Benchmark code for [Kubernetes Controller Anti-patterns: What Actually Costs You Performance](../k8s-controller-antipatterns-benchmark.md).

Tests four controller best-practice patterns side-by-side on a local Kind cluster, measuring convergence time, per-reconcile latency, and queue depth via Prometheus metrics scraped to CSV.

## Prerequisites

- `kind`
- `kubectl`
- `docker` (or OrbStack)
- `go 1.22+`
- `duckdb` (optional, for CSV analysis)

## Quick start

```bash
# create Kind cluster, build all images, deploy controllers
make setup

# run the 2×2 anti-pattern vs best-practice comparison
make stress N=1000

# analyse results
duckdb -c "CREATE VIEW m AS SELECT * FROM read_csv_auto(['metrics/*/metrics-*.csv']); SELECT controller, MAX(queue_depth), MAX(reconcile_success_total), MAX(queue_retries_total) FROM m GROUP BY controller;"
```

## Controller variants

| Variant | Workers | Predicate | Status method | Annotation loop |
|---|---|---|---|---|
| `good` | 5 | ✓ | `Status().Update()` + RetryOnConflict | ✗ |
| `good-single` | 1 | ✓ | `Status().Update()` + RetryOnConflict | ✗ |
| `good-patch` | 5 | ✓ | `Status().Patch()` | ✗ |
| `good-single-patch` | 1 | ✓ | `Status().Patch()` | ✗ |
| `bad-fixed-status` | 5 | ✗ | `Status().Update()` | ✓ |
| `bad-fixed-single` | 1 | ✗ | `Status().Update()` | ✓ |

## Scripts

| Script | What it runs |
|---|---|
| `stress.sh N [secs]` | 2×2 matrix: all 4 good+bad variants, N=50–5000 |
| `stress-good.sh N [secs]` | Good variants only (good, good-single, good-patch, good-single-patch) |
| `stress-patch.sh N [secs]` | Patch variants only (good-patch, good-single-patch) |
| `stress-good-fg.sh N [secs]` | Good variants on the feature-gate cluster |
| `stress-patch-fg.sh N [secs]` | Patch variants on the feature-gate cluster |

Each run writes metrics to `metrics/<timestamp>-<tag>-N<scale>/metrics-<controller>.csv`.

## Feature gate cluster

```bash
make setup-fg   # creates widget-benchmark-fg with ConcurrentWatchObjectDecode + WatchListClient
bash stress-good-fg.sh 5000 180
make cluster-delete-fg
```

## Analysing with DuckDB

Pre-written queries are in `queries.sql`. Load any run:

```sql
CREATE VIEW m AS SELECT * FROM read_csv_auto(['metrics/20260517T.../metrics-good.csv',
                                               'metrics/20260517T.../metrics-good-single.csv']);
.read queries.sql
```

Key queries: queue depth over time, per-second reconcile rate (via `LAG()`), convergence time, retry rate, worker saturation.
