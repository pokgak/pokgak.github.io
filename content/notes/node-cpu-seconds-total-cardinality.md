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

## Follow-up: `labeldrop` Doesn't Reduce Samples — It Breaks DPM Billing

Learned this the hard way. Dropping the `cpu` label reduced series count (cardinality) but **tripled the Grafana Cloud bill**.

**Why:** Grafana Cloud's usage-based tier charges per *samples ingested* (DPM — data points per minute), not per series count. When you `labeldrop` the `cpu` label, 128 samples per scrape that previously had distinct label sets now all share the same label set. They still get scraped and forwarded individually. One "series" now receives 128 samples per scrape interval instead of 1.

- Before: 128 series × 1 sample each per scrape = 128 DPM per (instance, mode)
- After labeldrop: 1 series × 128 samples per scrape = 128 DPM per (instance, mode)

Cardinality goes down, DPM stays the same. If your vendor bills on DPM, you get nothing.

**The actual fix: pre-aggregate with a recording rule before remote_write.**

```yaml
groups:
  - name: node_cpu_agg
    rules:
      - record: node_cpu_seconds_total:by_mode
        expr: sum without (cpu) (node_cpu_seconds_total)
```

Prometheus evaluates this locally and only remote-writes the aggregated series — one sample per `(instance, mode)` per scrape interval. DPM drops proportionally to core count.

**Catch: Grafana Alloy doesn't support recording rules.** If your pipeline is Alloy → Grafana Cloud, you can't pre-aggregate this way. Your options are:

1. **Grafana Cloud Adaptive Metrics** — detects unused label dimensions and aggregates them server-side. But you still pay full ingest cost for the raw samples that already came in; it only reduces the *active series* charge, not ingestion.
2. **Run a self-managed Prometheus** in front of Alloy — let it evaluate recording rules, then remote-write the aggregated output to Grafana Cloud. Adds operational overhead.

**TL;DR:** `labeldrop` is a cardinality fix. For DPM-based billing you need pre-aggregation via recording rules — but if you're on Alloy you can't do that locally, and Grafana Cloud's Adaptive Metrics doesn't help with ingest cost.
