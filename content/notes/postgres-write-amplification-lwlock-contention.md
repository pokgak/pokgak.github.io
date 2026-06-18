---
title: "When Postgres 'lock contention' isn't locks: write amplification & LWLocks"
date: 2026-06-18T10:00:00+0800
tags: [postgres, databases, performance, concurrency]
---

**"Slow query? Add an index."** It's the reflex, and it's right often enough to become muscle memory. But an index is a *read* optimization whose cost is paid on *every write* — and that cost is invisible to whoever adds it. You see the SELECT get fast immediately; you never see the write tax, which surfaces later, on a different code path, as tail latency nobody connects back to the index.

This is a real case where that reflex compounded into a production fire. Nobody set out to put **~25 indexes** on one table — ~25 people each fixed one slow query, each index locally rational.

Then comes the trap that makes this worth a note. The aggregate turned a high-churn table into a contention disaster — but when someone enabled `log_lock_waits` to find the "lock contention," it logged **nothing**. Conclusion: "not a lock problem." Wrong. It was the most lock-bound table in the fleet — just at a layer the tooling hides. The waits were on **lightweight locks (LWLocks)**: microsecond shared-memory locks on WAL insertion, page buffers, and the lock manager, driven by the write amplification those 25 indexes create. `log_lock_waits` only sees *heavyweight* locks, so the over-indexing damage is invisible to exactly the tool you'd reach for. That invisibility is what makes the reflex dangerous — and it's why the diagnosis below matters as much as the fix.

## The setup

A high-churn lifecycle table on managed Postgres 15. Rows model short-lived compute resources: created → rapidly updated through a state machine (`PENDING → PROVISIONING → RUNNING → … → TERMINATED`) over seconds-to-minutes → then never touched again.

- ~50M live rows, never deleted (terminate = a status UPDATE, not a DELETE) → grows unbounded
- ~5 updates per row over its short life; ~18M updates vs ~4M inserts/day
- **~25 indexes** on the table (many partial, predicated on `status`)
- Recurring "the DB is locking up" reports → someone enabled `log_lock_waits`… which then logged **nothing**. That silence is the whole story.

## Cause 1 — write amplification (the bloat half)

Postgres updates are copy-on-write (MVCC): an UPDATE writes a *new* row version and marks the old one dead. Indexes point at physical tuple locations, so the cost of an update is really *"how many indexes need a new entry for the new tuple?"*

- **HOT update (fast path):** if the update touches no indexed column and the page has room, the new version stays on-page and **no index is touched**.
- **Non-HOT update:** new tuple → new location → **every index gets a fresh entry**, even indexes on columns that didn't change. Old entries linger as dead until VACUUM.

This table ran at **0.3% HOT**. Why? The column mutated on every transition — `status` — is indexed ~15 ways. So *every* lifecycle update is non-HOT and rewrites all ~25 indexes.

→ One short-lived row = ~150 index-entry writes instead of ~25. Multiply by millions → ~450M index insertions/day, each leaving a dead entry. Autovacuum at default `scale_factor=0.2` only fires at ~10M dead tuples (~every 4 days), so the indexes bloated to tens of GB.

**Takeaway:** indexing the column your hot path mutates silently turns every write into the slow path. Check `n_tup_hot_upd / n_tup_upd` (here: 0.3%).

## Cause 2 — the "lock contention" is lightweight locks, not row locks

People assumed heavyweight row-lock contention (classic "hot row" serialization). The data said otherwise. Three lock layers worth distinguishing:

- **Heavyweight locks** — row locks (`FOR UPDATE`, `FOR KEY SHARE`, …) + relation locks. One statement can *wait* on another. **These are what `log_lock_waits` logs.**
- **Lightweight locks (LWLocks)** — microsecond locks protecting shared memory: WAL-insert, relation-extension, buffer pages, lock manager. **Not logged by `log_lock_waits`.**
- **buffer_pin** — waiting on a buffer another backend pinned.

The managed query-stats view splits `lock_time` by `lock_type`. Result on the top queries: **100% lightweight (`lw`), 0% heavyweight (`hw`).** That single number reframed everything:

- It's **why `log_lock_waits` was silent** — there were essentially no heavyweight waits to log.
- The table wasn't row-lock-bound; it was **LWLock/throughput-bound** from the write volume.

### Getting this data without a managed view

No managed dashboard needed — `pg_stat_activity.wait_event_type` already separates the two worlds: `Lock` = heavyweight (what `log_lock_waits` sees), `LWLock` = lightweight (`WALInsert`, `BufferContent`, `LockManager`, …).

```sql
-- pg_stat_activity is a point-in-time snapshot. Poll it repeatedly
-- (e.g. every 100ms for a minute) and aggregate the samples.
SELECT wait_event_type, wait_event, count(*)
FROM pg_stat_activity
WHERE state = 'active' AND wait_event_type IS NOT NULL
GROUP BY 1, 2
ORDER BY 3 DESC;
```

If `LWLock` rows dominate and `Lock` rows are absent, that's the "100% lw, 0% hw" result — contention is lightweight, and `log_lock_waits` stays silent.

For continuous accumulation instead of manual polling, `pg_wait_sampling` profiles wait events in the background:

```sql
CREATE EXTENSION pg_wait_sampling;
SELECT event_type, event, count
FROM pg_wait_sampling_profile
ORDER BY count DESC
LIMIT 20;
```

This active-session-sampling approach is exactly what RDS Performance Insights and Cloud SQL Query Insights are built on. While you're in there, confirm the bloat half too:

```sql
-- HOT-update ratio (here: 0.3%) — low means writes are taking the slow path
SELECT relname, n_tup_upd, n_tup_hot_upd,
       round(100.0 * n_tup_hot_upd / nullif(n_tup_upd, 0), 1) AS hot_pct
FROM pg_stat_user_tables
ORDER BY n_tup_upd DESC;
```

What the LWLock contention actually is, for an insert-heavy + 25-index table:

1. **WAL-insert locks** — every write emits WAL for the heap tuple + ~25 index entries; high write volume contends on the WAL insert slots.
2. **Relation-extension lock** — when concurrent inserts need a new page, they serialize on a per-relation lock to extend the file — once for the heap and once *per index* (~25 points).
3. **Index leaf-buffer contention** — monotonic indexes (`created_at`, etc.) funnel every insert to the same right-most leaf page → a buffer-content hotspot.
4. **Lock-manager LWLocks** — taking the relation-level lock on the table + every index, per statement.

**Takeaway:** "lock waits" in a stats dashboard can be lightweight locks. If `log_lock_waits` is silent but the system feels contended, break `lock_time` down by `lock_type` (or sample `pg_stat_activity.wait_event`) before assuming row contention.

## The misdirection

Two plausible-but-wrong theories the evidence killed:

- **"A hot counter row serializes everything via FK locks."** An insert takes `FOR KEY SHARE` on its parent rows; the parent's counter UPDATE takes `FOR NO KEY UPDATE`. Those two row-lock modes are **compatible** → no conflict, no wait. (Confirmed: `hw=0`.)
- **"Reads are blocking on the writes."** A plain SELECT takes no row locks (MVCC snapshot); it only takes a relation-level `AccessShareLock` that conflicts solely with DDL. Reads were also `lw`-bound — contending on buffers being dirtied by the write storm, not waiting on locks.

## The tail-latency tell

Per-query latency: **p50 ≈ 1 ms, p99 ≈ 60+ s** for inserts. The median write is instant; the contention shows up only as a fat tail when concurrency spikes. Averages were dragged 100–1000× above the median. Lesson: **look at p99, not avg** — contention is a tail phenomenon.

## What to do instead of adding index #26

The reflex is to add an index. Here the leverage runs the other way: the question isn't "what index makes this read faster" but "does this query — or this write — need to hit Postgres at all?" Three tiers, cheapest-to-build first.

### Tier 1 — fix the indexes you already have (subtract, don't add)

- **Remove dead and redundant indexes.** Audit with `pg_stat_user_indexes.idx_scan` (check *every* node — the counter is per-replica). We found ~5 indexes with 0 scans on both primary and replica, plus single-column indexes redundant with composites (`(a)` is covered by `(a, b)`'s leading column). Each one deleted is index entries removed from *every* write.
- **When you do need an index, pick a cheaper one.** This isn't "don't index" — it's "don't reach for a default B-tree." A **partial index** (`WHERE status = 'RUNNING'`) covers only the rows the query wants and stays out of the write path for the rest. A **BRIN** on an append-ordered column (`created_at`) stores min/max per block range → few MB, near-zero write cost, no per-row leaf insert (lossy, range scans only). One well-chosen composite often replaces three single-column indexes.

### Tier 2 — speed up the read without taxing writes

When a read genuinely needs to be fast and no cheap index fits, move the cost off the write path entirely:

- **Cache the read in Redis.** The hot lookup never reaches Postgres. Best when the read is far more frequent than the underlying change, or slight staleness is acceptable.
- **Materialized view / rollup table** for expensive aggregations — compute once, read many times. You trade freshness for read speed and pay a refresh cost, not a per-write cost.
- **Denormalize at write time.** Maintain the answer (a counter, a flattened field) as part of the write you already do, so the read becomes a trivial point lookup instead of a scan that begs for an index.
- **Project hot reads into a read model (CQRS-lite).** Serve quota, dashboards, and billing from a Redis counter, cache, or the read replica — *then delete the read-serving indexes those queries needed*. The relief isn't fewer writes; it's that each remaining write fans out to fewer indexes. This one has a catch worth its own section — see "One write ≠ one write" below.
- **Read replica** for read scaling — but note this *adds* write amplification (every index is rebuilt on the replica too); it scales read throughput, not write cost.

### Tier 3 — eliminate the writes (the real lever here)

The deepest fix questions the schema, not the query. A short-lived resource churning through a state machine doesn't need a durable, heavily-indexed RDBMS row for *every* intermediate transition:

- **Buffer / batch the churn.** Hold the hot state in Redis and flush only meaningful (often terminal) state to Postgres. The ~5 intermediate updates per row collapse to 1–2 persisted writes → most of the 450M daily index insertions never happen. (There's *no* Postgres knob to defer B-tree index updates — they're synchronous by design; the only built-in batch-and-flush is GIN `fastupdate`, GIN-only. So this has to happen in the app.)
- **Move the ephemeral state machine out of Postgres.** Let the durable store hold only the final record; Postgres becomes the archive, not the hot mutable store. This is the headline architectural answer — it deletes the write storm rather than tuning it.
- **Event-sourcing / append-only ledger.** Inserts only, no in-place updates → no MVCC dead tuples, no per-update index churn. Project current state into a cache for reads.

### One write ≠ one write

The offload techniques above — cache, denormalize, project — invite an obvious objection: *isn't that just moving the writes? The table still gets its updates, and now I write the projection too — more writes, not fewer.* Half true, and resolving it is the actual insight.

- **Projections don't reduce writes to the source table.** The lifecycle still does its 1 insert + ~5 updates, and the projection *adds* writes (the counter `HINCRBY`, the cache set).
- **The win isn't offloading writes — it's that projections let you delete the read-serving *indexes*.** Same write count, but each write fans out to ~15 indexes instead of ~25. The reduction is in *amplification per write*, not write count — real work eliminated on the hot table, not shuffled elsewhere. This is the same "subtract, don't add" lever as Tier 1, reached from the read side.
- **A write isn't a write — cost depends on where it lands.** A Postgres write does a pile of work `HINCRBY` simply doesn't:

| | Postgres row UPDATE | Redis `HINCRBY` |
|---|---|---|
| **Storage** | locate + pin a heap page (`shared_buffers`, sometimes disk) | in-memory field write |
| **Indexes** | a new entry into *every* index on the row (the fan-out) | none — hashes have no secondary indexes |
| **MVCC** | new tuple + dead old tuple → bloat + later VACUUM | mutates value in place, no versions |
| **Locking** | row lock + buffer-content LWLocks + lock-manager | single-threaded → "it's my turn," no lock machinery |
| **Durability** | WAL record per change + fsync on commit | optional AOF (sequential append, fsync ~every 1s) or none |
| **Complexity** | the thing it replaces (quota scan) is O(M) over the active set | O(1) |
| **Per-call overhead** | parse + plan + execute SQL | a simple protocol command |

So the quota counter doesn't offload a Postgres write — it *replaces a Postgres read* (the O(M) aggregate scan) with cheap Redis ops, cheap precisely because Redis isn't a B-tree/WAL/MVCC store.

- **The trap:** if the projection is *another indexed Postgres table updated per event*, you've just duplicated the amplification → net loss. Projections only help when they live in a cheap store (Redis/cache), are batched/async, or carry far fewer indexes.
- **The caveat that makes or breaks it:** the win only materializes if you *actually drop* the indexes the projection replaced. Projection without the index-drop is pure added cost — exactly the "more writes, no benefit" outcome. Projection and index-drop are one package.

Mental model: **projections don't reduce writes; they make read-serving indexes *deletable*, and that reduces per-write fan-out. Their own writes are only worth it when they're cheaper than a B-tree (Redis/cache) or batched.**

### Postgres knobs (mitigation, not cure)

Worth doing, but they tune the symptom rather than remove the write:

- **`synchronous_commit = off`** on the high-frequency write path — commit returns before the WAL fsync. Cuts insert tail latency; risk is a sub-second window of lost *acknowledged* txns on crash (no corruption/inconsistency). Scope per-session, never the money ledger.
- **Autovacuum tuning** per-table (`scale_factor` ~0.02) so bloat doesn't accumulate.
- **Upgrade to PG 16+** — bulk relation extension adds many pages at once and hands spares to waiters, so the extension lock is taken far less often. Directly targets cause-2 #2.

> Note: **don't reach for partitioning here.** Partitioning by `status` looks tempting, but `status` is the churn key — every transition would move the row across partitions (a delete + insert), which is *worse* than the non-HOT update you already have. Partition only on an immutable column (e.g. `created_at`), and only if a query actually prunes on it.

## Takeaways

- **The "add an index" reflex optimizes reads and silently taxes every write.** On a high-churn table, each locally-rational index compounds into a write-amplification fire nobody attributes to indexing.
- **Before adding an index, ask if the query (or the write) should exist at all** — cache it, denormalize it, or buffer the churn out of the database.
- **Indexing a hot-path-mutated column kills HOT updates** → every write becomes the slow path. Check `n_tup_hot_upd / n_tup_upd`.
- **`log_lock_waits` silence ≠ no contention.** It only sees heavyweight locks. LWLock / buffer / WAL contention is invisible to it — split `lock_time` by `lock_type` (or sample `pg_stat_activity.wait_event`).
- **Heavyweight row-lock theories are seductive and often wrong** — check lock *mode compatibility* (`FOR KEY SHARE` vs `FOR NO KEY UPDATE`) before blaming a "hot row."
- **Contention is a tail phenomenon** — p99, not avg.
- **Projections extend "subtract, don't add" to the read side** — they don't reduce writes, they make read-serving indexes deletable (and a write to Redis ≠ a write to a B-tree). The relief comes from the index drop they unlock, not the offload.
