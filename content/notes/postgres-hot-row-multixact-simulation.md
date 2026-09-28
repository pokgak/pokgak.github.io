---
title: "Simulating a Postgres hot-row convoy and MultiXact collapse"
date: 2026-09-28T22:00:00+0800
tags: [postgres, databases, concurrency, incidents, simulation]
description: "An interactive model of how a hot row, foreign key locks and a long-running transaction turn into MultiXact LWLock contention and connection exhaustion."
---

<style>
.phr{--a:#2a78d6;--fk:#8b5cf6;--wait:#eb6834;--hold:#1baf7a;--api:#0ea5b7;--bad:#e34948;--warn:#c2410c;--ink:#111827;--ink2:#4b5563;--rule:rgba(17,24,39,.16);--faint:rgba(17,24,39,.07);--panel:#fafafa;margin:2rem 0;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.45;color:var(--ink)}
.dark .phr{--a:#3987e5;--fk:#a78bfa;--wait:#f07b45;--hold:#2fbf88;--api:#22b8cc;--bad:#ef6b6b;--warn:#fb923c;--ink:#f3f4f6;--ink2:#a1a1aa;--rule:rgba(243,244,246,.2);--faint:rgba(243,244,246,.08);--panel:#18181b}
.phr-panel{border:1px solid var(--rule);border-radius:8px;padding:14px;background:var(--panel)}
.phr-controls{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:flex-end;margin-bottom:10px}
.phr-knobs{margin:14px 0 0;padding-top:12px;border-top:1px solid var(--rule)}
.phr-ctl{display:flex;flex-direction:column;gap:4px}
.phr-ctl>span{font-size:12px;color:var(--ink2);font-weight:600}
.phr-ctl output{font-weight:650;color:var(--ink);font-variant-numeric:tabular-nums}
.phr input[type=range]{width:170px;accent-color:var(--a)}
.phr-seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--rule);border-radius:6px;overflow:hidden}
.phr-seg button{font:inherit;font-size:13px;padding:4px 10px;background:transparent;color:var(--ink);border:0;border-left:1px solid var(--rule);cursor:pointer}
.phr-seg button:first-child{border-left:0}
.phr-seg button[aria-pressed="true"]{background:var(--ink);color:var(--panel)}
.phr-seg button:hover{background:var(--faint)}
.phr-seg button[aria-pressed="true"]:hover{background:var(--ink)}
.phr-actions{display:flex;flex-wrap:wrap;gap:6px}
.phr-btn{font:inherit;font-size:13px;padding:4px 12px;border:1px solid var(--rule);border-radius:6px;background:transparent;color:var(--ink);cursor:pointer}
.phr-btn:hover{background:var(--faint)}
.phr svg{display:block;width:100%;height:auto;overflow:visible;margin-top:6px}
.phr svg text{fill:var(--ink);font-size:11px}
.phr .phr-t-strong{font-weight:650;font-size:11.5px}
.phr .phr-t-dim{fill:var(--ink2);font-size:10.5px}
.phr .phr-t-tiny{fill:var(--ink2);font-size:9px}
.phr .phr-t-big{font-size:17px;font-weight:650;font-variant-numeric:tabular-nums}
.phr .phr-t-warn{fill:var(--warn);font-weight:650;font-size:10.5px}
.phr-box{fill:none;stroke:var(--rule)}
.phr-track{fill:var(--faint)}
.phr-chart-bg{fill:var(--faint)}
.phr-arrow{fill:none;stroke:var(--ink2);stroke-width:1.2}
.phr-arrowhead{fill:var(--ink2)}
.phr-slot{transition:fill .15s}
.phr-s-off{fill:none;stroke:var(--faint)}
.phr-s-idle{fill:var(--faint)}
.phr-s-cold,.phr-sw-cold{fill:var(--a);background:var(--a)}
.phr-s-fk,.phr-sw-fk{fill:var(--fk);background:var(--fk)}
.phr-s-rowwait,.phr-sw-rowwait{fill:var(--wait);background:var(--wait)}
.phr-s-hold,.phr-sw-hold{fill:var(--hold);background:var(--hold)}
.phr-s-backoff,.phr-sw-backoff{fill:var(--ink2);background:var(--ink2)}
.phr-s-noconn,.phr-sw-noconn{fill:var(--bad);background:var(--bad)}
.phr-sw-idle{background:var(--faint);border:1px solid var(--rule)}
.phr-fill-rowwait{fill:var(--wait)}
.phr-fill-fk{fill:var(--fk)}
.phr-fill-hold{fill:var(--hold)}
.phr-fill-api{fill:var(--api)}
.phr-fill-ws{fill:var(--a)}
.phr-fill-noconn{fill:var(--bad)}
.phr-cache-mark{stroke:var(--ink);stroke-width:1.2;stroke-dasharray:3 2}
.phr-lock{fill:var(--faint);stroke:var(--ink2)}
.phr-lock-held{fill:var(--hold);stroke:var(--hold)}
.phr-lwdot{fill:var(--faint)}
.phr-lwdot-on{fill:var(--bad)}
.phr-line{fill:none;stroke-width:1.8;stroke-linejoin:round}
.phr-line-hold{stroke:var(--hold)}
.phr-line-ws{stroke:var(--a)}
.phr-line-fk{stroke:var(--fk)}
.phr-line-api{stroke:var(--api)}
.phr-line-rowwait{stroke:var(--wait)}
.phr-line-noconn{stroke:var(--bad)}
.phr-event{stroke:var(--warn);stroke-dasharray:3 2}
.phr-event-restart{stroke:var(--hold);stroke-dasharray:3 2}
.phr-cell-new{fill:var(--wait)}
.phr-cell-copy{fill:var(--fk)}
.phr-cell-old{fill:var(--fk);fill-opacity:.25}
.phr-legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin:8px 0 4px}
.phr-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.phr-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:10px}
.phr-stat{border:1px solid var(--rule);border-radius:6px;padding:6px 10px}
.phr-stat b{display:block;font-size:17px;font-weight:650;font-variant-numeric:tabular-nums}
.phr-stat small{color:var(--ink2);font-size:12px}
.phr-note,.phr-status{font-size:13px;color:var(--ink2);margin:10px 0 0;min-height:2.9em}
.phr-note b,.phr-status b{color:var(--ink)}
.phr figcaption{font-size:.8rem;opacity:.7;text-align:center;margin-top:.6rem}
@media (prefers-reduced-motion: reduce){.phr-slot{transition:none}}
</style>

A model of a production incident I helped debug: a background task pipeline took down the main Postgres database, and DB CPU stayed low the whole time. The widgets below rebuild the failure from its parts so you can change the inputs and watch it happen.

The chain, in one line: **many transactions on one hot row → foreign key locks turn the parent row's lock into a big MultiXact → a long-running transaction keeps old MultiXacts in play → MultiXact lookups miss a tiny cache and queue on one LWLock → everything holds its connection longer → connections run out.**

## What's a MultiXact, and why does it grow so fast?

- A Postgres row header has one `xmax` slot for the transaction that locked or deleted it.
- `INSERT` into a child table checks the foreign key with `SELECT ... FOR KEY SHARE` on the parent row. So every insert puts a shared lock on its parent until commit.
- When two or more transactions hold a lock on the same row, Postgres writes a **MultiXact**: a list of member transaction IDs stored in `pg_multixact/`, with its ID in `xmax`.
- A MultiXact can't be changed after it's written. Adding a locker means writing a new one that copies all the current members and adds the new one.

<figure class="phr not-prose" id="phr-multixact">
<noscript><p>This interactive diagram needs JavaScript.</p></noscript>
<figcaption>Drag the slider or press Play. Each new locker writes a new MultiXact that copies all the current members.</figcaption>
</figure>

- N concurrent lockers write about N²/2 members. Doubling the lockers roughly quadruples the member writes.
- Reading a row whose `xmax` is a MultiXact means looking up its members to see if any are still running. That includes a plain `SELECT` doing a visibility check.
- Members are read through an SLRU cache in shared memory. On PG15 it's a fixed 16 pages (about 26k members). PG17 makes the size configurable (`multixact_member_buffers`).
- Postgres can skip the lookup for a MultiXact older than every running transaction. **One long-running transaction turns that shortcut off** for everything created after it started.

## The simulation

Two task queues dispatch background work. Most tasks update the same hot row, a per-day counter. Each of those tasks also inserts a child row that references a parent row, and an API reads that parent row on every request. Everything shares one connection budget.

<figure class="phr not-prose" id="phr-sim">
<noscript><p>This simulation needs JavaScript.</p></noscript>
<figcaption>A discrete-event model running in your browser. Change the controls while it runs.</figcaption>
</figure>

<script src="/embeds/pg-hot-row/sim.js"></script>
<script src="/embeds/pg-hot-row/ui.js"></script>

### How the model works

- **Tasks.** Each queue slot takes a task and a connection. 75% of tasks (adjustable) are for the hot row. The rest touch other rows for 40 ms and leave.
- **Hot task.** It inserts a child row first, which takes `KEY SHARE` on the parent row and joins its MultiXact (a new MultiXact of size N+1). Then it queues for the hot row lock, does 2 ms of work plus 3 MultiXact lookups while holding it, and commits.
- **MultiXact working set.** The members written since the oldest running transaction started. A lookup misses the cache with probability `1 − cache / working set`.
- **SLRU LWLock.** One FIFO server. A hit costs 0.01 ms and a miss 1 ms. Each waiter adds 0.4% overhead, standing in for LWLock wakeup and retry costs.
- **API.** Poisson arrivals. Each request takes a connection and does 4 MultiXact lookups (the tuple versions it checks on the parent row). Clients time out after 10 s and retry twice, and **the server keeps running the abandoned query** and holding its connection.
- **lock_timeout** aborts a transaction that waits too long for the hot row lock, and the task retries after 1 s. It doesn't cover LWLock waits, just like the real setting.
- **Long transaction.** A session with an old snapshot. It holds the horizon still, so the working set only grows.

## Things to try

**1. One queue at 100.** Start from *One queue*.
- About 95 transactions are queued on the hot row at any time, and throughput is about 490 commits/s.
- The working set is about 9k members, well under the 26k cache. It's a convoy, but a stable one.

**2. Add a second queue.** Pick *Two queues*, or move Queue B to 100.
- Throughput *drops* to about 260/s. Doubling the concurrency made the system slower.
- The working set grows to about 40k, past the cache. About a third of lookups miss.
- **Why:** the working set is roughly M², where M is the number of queued lockers. Queue wait is M ÷ throughput, and MultiXacts get written at throughput × M per second, so the throughput cancels out. With a 26k cache, the tipping point is about √26k ≈ 160 lockers.

**3. Drop to 10 concurrent.** Move Queue A to 10 and Queue B to 0.
- Throughput stays close to 490/s. The hot row is the bottleneck, so extra concurrency only adds waiters.

**4. Open a long transaction.** Pick *Two queues + long txn*, or press *Open long txn*.
- The working set climbs without limit. Misses go to about 90%, and the LWLock queue jumps from about 10 to hundreds within 20 s.
- Connections fill up, and API p95 hits the 10 s client timeout. Retries push API attempts to about 3× normal.
- **DB CPU falls to about 0%.** The database is waiting, not working.

**5. End the long transaction.** Press *End long txn* once it has collapsed.
- The working set drops back, but the system **stays down**. The LWLock queue and connections stay full, because abandoned API queries and retries keep refilling them. This is a metastable failure: the trigger is gone, but the load it caused keeps it down.
- Press *Pause queues*, then *Restart DB*. It recovers within seconds.

**6. Try the fixes on the two-queue setup.**
- **`lock_timeout` 100 ms:** M stays around 50, the working set drops to about 4k, and throughput goes back to about 490/s with 200 slots. Now open a long transaction: it still collapses. `lock_timeout` limits heavyweight lock waits, not LWLock waits.
- **1024 member buffers (PG17):** the long transaction takes about 20 s longer to cause trouble, then it degrades anyway. More cache buys time.
- **Fewer hot tasks:** move *Tasks hitting the hot row* to 10% (for example, skipping writes for events that change nothing). The hot row still runs at full speed, but only about 20 lockers queue on it, and the working set drops under 1k.
- None of these survive a long transaction for long, because the working set keeps growing for as long as it stays open. What actually works is ending it early: `idle_in_transaction_session_timeout` and `statement_timeout`, plus an alert on the age of the oldest transaction.

## Signs of this in a real system

- DB CPU is low while latency climbs and write throughput (commits/s, XIDs per minute) falls.
- `pg_stat_activity.wait_event` is dominated by `LWLock: MultiXactMemberSLRU` / `MultiXactMemberBuffer` / `MultiXactOffsetSLRU`, with `Lock: transactionid` and `Lock: tuple` next.
- `log_lock_waits` shows `still waiting for ShareLock on transaction N`, and the `CONTEXT` lines point at the same one or two tuples.
- `pg_stat_slru` shows `blks_read` climbing for the MultiXact caches.
- `now() - xact_start` for the oldest transaction is minutes or hours.
- Primary-key lookups on the parent table take seconds.
- Connections climb until every service sits at its cap, while the task backlog grows.
- `pg_terminate_backend` doesn't end sessions stuck in these LWLock waits. A restart does.

## What the model leaves out

- The numbers are picked to show the shape of the failure, not measured from a real database. The collapse in the real incident took tens of minutes, not seconds.
- A cache miss here is a coin flip based on working set vs cache size. Real SLRU behaviour depends on which pages each lookup touches, on dirty page writeback, and on MultiXact offsets as well as members.
- There's one hot row and one parent row. Real systems have several parents per insert (user, team, account), each with its own MultiXact.
- Transaction and connection handling is simplified: no pool queues, no per-instance connection caps, no autovacuum.
