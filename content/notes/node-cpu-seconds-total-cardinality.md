---
title: "node_cpu_seconds_total: The Infamous Cardinality Killer"
date: 2026-04-03T00:00:00+0800
tags: [prometheus, metrics, cardinality, grafana, observability]
---

## The Problem

`node_cpu_seconds_total` is one of the most well-known high-cardinality metrics in Prometheus. Its cardinality is:

```
nodes × cpu_cores × cpu_modes
```

The standard CPU modes are: `user`, `system`, `idle`, `iowait`, `nice`, `irq`, `softirq`, `steal` — that's 8 modes.

Some concrete examples:

- 50 nodes × 64 cores × 8 modes = **25,600 series**
- 100 nodes × 64 cores × 8 modes = **51,200 series**
- 100 nodes × 128 cores × 8 modes = **102,400 series**
- 500 nodes × 128 cores × 8 modes = **512,000 series**

That's a single metric name generating 100k+ active series on a moderately sized cluster.

## Why It Matters

Most Prometheus-compatible backends (Grafana Cloud Mimir, Thanos, Cortex, VictoriaMetrics) charge or resource-plan based on active series count. When one metric accounts for a significant chunk of your total series, it dominates your storage, memory, and potentially your bill.

## The Fix: Drop the `cpu` Label

The `cpu` label carries the per-core number (`cpu0`, `cpu1`, ..., `cpu127`). Almost no dashboard or alert actually uses per-core breakdown — they all `sum by (instance)` or `avg by (instance)` anyway.

Dropping this label collapses all per-core series into one series per node per mode.

### Prometheus scrape_configs

```yaml
scrape_configs:
  - job_name: node-exporter
    metric_relabel_configs:
      - action: labeldrop
        regex: 'cpu'
```

### Grafana Alloy

```alloy
prometheus.relabel "node_exporter" {
  forward_to = [prometheus.remote_write.default.receiver]

  rule {
    action = "labeldrop"
    regex  = "cpu"
  }
}
```

### Scoping Warning

If you have a shared relabel pipeline that processes metrics from multiple sources (e.g., cAdvisor, DCGM exporter), make sure to scope the `labeldrop` to only node_exporter metrics. cAdvisor uses a `cpu` label on `container_cpu_*` metrics too, and dropping it there would break container-level CPU queries.

## Impact

| Scenario | Before | After | Reduction |
|---|---|---|---|
| 100 nodes × 64 cores × 8 modes | 51,200 | 800 | 98.4% |
| 100 nodes × 128 cores × 8 modes | 102,400 | 800 | 99.2% |

After dropping the `cpu` label, the formula becomes `nodes × cpu_modes` — so 100 nodes × 8 modes = 800 series.

## Dashboard Query Update

The common CPU utilization query needs updating since it relied on the `cpu` label to count cores.

**Before** (relies on `cpu` label to count cores):

```promql
sum by (instance) (irate(node_cpu_seconds_total{mode!="idle"}[$__rate_interval]))
/ scalar(count(count(node_cpu_seconds_total) by (cpu)))
```

**After** (works without `cpu` label):

```promql
1 - (
  sum by (instance) (irate(node_cpu_seconds_total{mode="idle"}[$__rate_interval]))
  /
  sum by (instance) (irate(node_cpu_seconds_total[$__rate_interval]))
)
```

The new query calculates CPU utilization as `1 - idle_ratio`, which works regardless of whether the `cpu` label exists. You can safely update dashboards before rolling out the labeldrop.

## Bonus: Drop Unused CPU Modes

Most dashboards and alerts only care about `user`, `system`, `idle`, and maybe `iowait`. You can drop rarely-queried modes (`steal`, `nice`, `softirq`, `irq`) for another ~50% reduction on top of the label drop.

```yaml
metric_relabel_configs:
  - source_labels: [__name__, mode]
    regex: 'node_cpu_seconds_total;(steal|nice|softirq|irq)'
    action: drop
```

This takes your 800 series (from the earlier example) down to ~400.
