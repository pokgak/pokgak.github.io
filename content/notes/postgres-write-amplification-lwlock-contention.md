---
title: "When Postgres 'lock contention' isn't locks: write amplification & LWLocks"
date: 2026-06-18T10:00:00+0800
tags: [postgres, databases, performance, concurrency]
---

A high-churn table everyone called "lock-contended" had **zero** heavyweight lock waits. The real pain was lightweight locks (LWLocks) driven by index write amplification — which is exactly why `log_lock_waits` caught nothing.

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

## Fixes (in order of leverage)

1. **Fewer indexes.** The direct lever: fewer index entries per write = less WAL, fewer extension points, less leaf contention. Audit with `pg_stat_user_indexes.idx_scan` (on *every* node — the counter is per-replica) to find genuinely unused ones. We found ~5 indexes with 0 scans on both primary and replica, plus single-column indexes redundant with composites (`(a)` is covered by `(a, b)`'s leading column).
2. **BRIN for append-ordered columns.** A B-tree on `created_at` is huge and hot at the right leaf. A BRIN stores min/max per block range → few MB, near-zero write cost, no per-row leaf insert. Lossy (range scans only), so only where the query is a range scan.
3. **`synchronous_commit = off`** on the high-frequency write path — commit returns before the WAL fsync. Cuts insert tail latency; risk is a sub-second window of lost *acknowledged* txns on crash (no corruption/inconsistency). Scope per-session, not the money ledger.
4. **Autovacuum tuning** per-table (`scale_factor` ~0.02) so bloat doesn't accumulate.
5. **Upgrade to PG 16+** — its bulk relation extension adds many pages at once and hands spares to waiters, so the extension lock is taken far less often. Directly targets cause-2 #2.
6. **App-side write buffering** — the real "batch and flush periodically": hold hot churn in Redis / an append-only ledger and persist only meaningful state. (There's *no* Postgres knob to defer B-tree index updates — synchronous by design. The only built-in batch-and-flush is GIN `fastupdate`, GIN-only.)

## Takeaways

- **Indexing a hot-path-mutated column kills HOT updates** → every write becomes the slow path.
- **`log_lock_waits` silence ≠ no contention.** It only sees heavyweight locks. LWLock / buffer / WAL contention is invisible to it — split `lock_time` by `lock_type`.
- **Heavyweight row-lock theories are seductive and often wrong** — check lock *mode compatibility* (`FOR KEY SHARE` vs `FOR NO KEY UPDATE`) before blaming a "hot row."
- **Contention is a tail phenomenon** — p99, not avg.
- The fix for write-amplification contention is usually **fewer/cheaper indexes + buffering writes**, not a magic GUC.
