-- Widget Controller Benchmark — DuckDB Analysis Queries
--
-- Usage:
--   duckdb -c ".read queries.sql"
--
-- Or interactively:
--   duckdb
--   D .read queries.sql
--
-- Set METRICS_DIR to your run directory, e.g.:
--   SET VARIABLE metrics_dir = 'metrics/20260517T123456-N1000';
--
-- Then run individual queries below.
--
-- Quick start — load all four files from a run:
--   CREATE VIEW m AS
--     SELECT * FROM read_csv_auto(['metrics/20260517T123456-N1000/metrics-good.csv',
--                                   'metrics/20260517T123456-N1000/metrics-good-single.csv',
--                                   'metrics/20260517T123456-N1000/metrics-bad-fixed-status.csv',
--                                   'metrics/20260517T123456-N1000/metrics-bad-fixed-single.csv']);

-- ─── 1. Queue depth over time ────────────────────────────────────────────────
-- How fast does the queue build up and does it ever drain?
SELECT
    strftime(timestamp, '%H:%M:%S') AS t,
    controller,
    queue_depth
FROM m
ORDER BY timestamp, controller;

-- ─── 2. Per-second reconcile rate (counter delta) ────────────────────────────
-- Converts cumulative counters to per-second rate using LAG().
SELECT
    strftime(timestamp, '%H:%M:%S') AS t,
    controller,
    reconcile_success_total
        - LAG(reconcile_success_total, 1, reconcile_success_total)
          OVER (PARTITION BY controller ORDER BY timestamp) AS success_per_sec,
    reconcile_error_total
        - LAG(reconcile_error_total, 1, reconcile_error_total)
          OVER (PARTITION BY controller ORDER BY timestamp) AS errors_per_sec,
    queue_adds_total
        - LAG(queue_adds_total, 1, queue_adds_total)
          OVER (PARTITION BY controller ORDER BY timestamp) AS queue_adds_per_sec
FROM m
ORDER BY timestamp, controller;

-- ─── 3. Retry rate — wasted work from annotation conflicts ───────────────────
-- queue_retries_total counts items that came back through the rate limiter.
-- High value on bad controllers = conflicts driving retry storms.
SELECT
    controller,
    MAX(queue_retries_total)    AS total_retries,
    MAX(reconcile_error_total)  AS total_errors,
    MAX(reconcile_success_total) AS total_successes,
    ROUND(
      MAX(queue_retries_total) / NULLIF(MAX(reconcile_success_total) + MAX(reconcile_error_total), 0),
      2
    ) AS retries_per_reconcile
FROM m
GROUP BY controller
ORDER BY total_retries DESC;

-- ─── 4. Useful work ratio ─────────────────────────────────────────────────────
-- What fraction of reconciles produced a success (useful) vs error (wasted)?
SELECT
    controller,
    MAX(reconcile_success_total) AS successes,
    MAX(reconcile_error_total)   AS errors,
    ROUND(
      MAX(reconcile_success_total) /
      NULLIF(MAX(reconcile_success_total) + MAX(reconcile_error_total), 0) * 100,
      1
    ) AS useful_pct
FROM m
GROUP BY controller
ORDER BY useful_pct DESC;

-- ─── 5. Convergence time ─────────────────────────────────────────────────────
-- First timestamp where queue_depth = 0 after t=0.
-- Only meaningful for good controllers — bad ones never converge.
WITH first_row AS (
    SELECT controller, MIN(timestamp) AS t0 FROM m GROUP BY controller
)
SELECT
    m.controller,
    MIN(m.timestamp) AS converged_at,
    DATEDIFF('second',
      (SELECT t0 FROM first_row WHERE controller = m.controller),
      MIN(m.timestamp)
    ) AS seconds_to_converge
FROM m
JOIN first_row USING (controller)
WHERE m.queue_depth = 0
  AND m.timestamp > (SELECT t0 FROM first_row WHERE controller = m.controller)
GROUP BY m.controller
ORDER BY seconds_to_converge;

-- ─── 6. Active worker saturation ─────────────────────────────────────────────
-- Were workers actually maxed out? If active_workers < max_workers for a long
-- time, the queue was empty (good) or something else was the bottleneck.
SELECT
    controller,
    ROUND(AVG(active_workers), 2)  AS avg_active_workers,
    MAX(active_workers)            AS peak_active_workers,
    ROUND(AVG(unfinished_work_s), 3) AS avg_unfinished_work_s
FROM m
GROUP BY controller
ORDER BY avg_active_workers DESC;

-- ─── 7. Reconcile latency (rolling average) ──────────────────────────────────
-- reconcile_latency_sum / reconcile_latency_count gives average latency
-- at that point in time. Delta of both gives the per-interval average.
SELECT
    strftime(timestamp, '%H:%M:%S') AS t,
    controller,
    ROUND(
      (reconcile_latency_sum
         - LAG(reconcile_latency_sum, 1, reconcile_latency_sum)
           OVER (PARTITION BY controller ORDER BY timestamp))
      / NULLIF(
          reconcile_latency_count
            - LAG(reconcile_latency_count, 1, reconcile_latency_count)
              OVER (PARTITION BY controller ORDER BY timestamp),
          0
        ) * 1000,
      1
    ) AS avg_latency_ms
FROM m
ORDER BY timestamp, controller;

-- ─── 8. Queue depth: max and time-at-depth > N ───────────────────────────────
-- For the bad controllers: how backed up did the queue get, and for how long?
SELECT
    controller,
    MAX(queue_depth)                         AS peak_queue_depth,
    COUNT(*) FILTER (WHERE queue_depth > 10) AS seconds_depth_gt_10,
    COUNT(*) FILTER (WHERE queue_depth > 100) AS seconds_depth_gt_100,
    COUNT(*) FILTER (WHERE queue_depth > 0)  AS seconds_queue_nonempty
FROM m
GROUP BY controller
ORDER BY peak_queue_depth DESC;

-- ─── 9. Side-by-side summary ─────────────────────────────────────────────────
-- One-row-per-controller summary for the experiment write-up.
SELECT
    controller,
    MAX(reconcile_success_total)                                AS successes,
    MAX(reconcile_error_total)                                  AS errors,
    MAX(queue_retries_total)                                    AS retries,
    MAX(queue_depth)                                            AS peak_depth,
    ROUND(AVG(active_workers), 1)                              AS avg_workers,
    ROUND(MAX(reconcile_latency_sum)
          / NULLIF(MAX(reconcile_latency_count), 0) * 1000, 1) AS overall_avg_lat_ms
FROM m
GROUP BY controller
ORDER BY controller;
