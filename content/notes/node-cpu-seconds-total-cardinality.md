---
title: "node_cpu_seconds_total: The Infamous Cardinality Killer"
date: 2026-04-03T00:00:00+0800
tags: [prometheus, metrics, cardinality, grafana, observability]
---

## Problem

`node_cpu_seconds_total` cardinality = `nodes x cpu_cores x cpu_modes`

- 8 standard CPU modes: `user`, `system`, `idle`, `iowait`, `nice`, `irq`, `softirq`, `steal`
- 100 nodes x 128 cores x 8 modes = **102,400 series** from a single metric
- Most Prometheus backends charge/resource-plan based on active series count

## Fix: Drop the `cpu` Label

Almost no dashboard uses per-core breakdown — they all `sum by (instance)` anyway. Dropping the `cpu` label collapses to one series per node per mode.

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

### Scoping warning

If you have a shared relabel pipeline processing multiple sources (e.g., cAdvisor, DCGM exporter), scope the `labeldrop` to node_exporter only. cAdvisor uses a `cpu` label on `container_cpu_*` metrics too.

## Impact

| Scenario | Before | After | Reduction |
|---|---|---|---|
| 100 nodes x 64 cores x 8 modes | 51,200 | 800 | 98.4% |
| 100 nodes x 128 cores x 8 modes | 102,400 | 800 | 99.2% |

After: `nodes x cpu_modes` = 100 x 8 = 800 series.

## Dashboard Query Update

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

Safe to update dashboards before rolling out the labeldrop.

## Bonus: Drop Unused CPU Modes

Most dashboards only need `user`, `system`, `idle`, `iowait`. Drop the rest for another ~50% reduction:

```yaml
metric_relabel_configs:
  - source_labels: [__name__, mode]
    regex: 'node_cpu_seconds_total;(steal|nice|softirq|irq)'
    action: drop
```

Takes 800 series down to ~400.
