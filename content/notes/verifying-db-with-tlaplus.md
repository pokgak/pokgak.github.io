---
title: "Verifying a Database Implementation with TLA+"
date: 2026-05-01T01:11:25+0800
tags: [tla+, distributed-systems, databases, formal-methods]
---

*Agent-assisted exploration. I'm not a TLA+ expert — this is me learning by doing, with Claude Code helping write and debug specs. All the TLA+ was written collaboratively in a local Claude Code session.*

---

The context: I've been looking at NodeDB, a distributed database with a Rust implementation. Reading the code, I found a few places where the implementation seemed to diverge from what the comments described. Instead of just writing it up as prose bugs, I wanted to try TLA+ to make the case more formally.

This is **not** spec-first design (the AWS/FoundationDB approach where you write TLA+ before writing code). It's closer to a formal post-mortem: read the code, form hypotheses, encode them as specs, and let TLC produce counterexample traces that are harder to argue with than prose.

---

## What's the approach?

Three-layer structure:

1. **Reference spec** — what does "correct" look like? Define invariants independently of any implementation.
2. **Protocol spec** — what does the code *intend* to do? Model the design as described in comments and docs. Verify it satisfies the reference invariants.
3. **Implementation spec** — what does the code *actually* do? One targeted change per spec. Verify TLC finds the expected violation.

If the protocol spec passes and the impl spec fails, the bug is implementation drift — not a design flaw.

---

## Bug 1: False aborts in Snapshot Isolation

**The hypothesis**: The conflict detection ignores which document was modified. It aborts any transaction if *any* write happened globally since the snapshot — even writes to unrelated documents by different tenants.

The code in `transaction_cmds.rs`:

```rust
for (_collection, _doc_id, read_lsn) in &read_set {
    if current > *read_lsn && current > snapshot_lsn {
        // abort
    }
}
```

`_collection` and `_doc_id` are both ignored. The check is: "has the global WAL LSN advanced past this read?" That's a global write fence, not per-document conflict detection.

**Encoding the intended protocol** (`SIProtocol.tla`):

```tla
ConflictDetected(t) ==
    \E entry \in tx_read_set[t] :
        doc_lsn[entry.doc] > entry.read_lsn
```

Abort only when the specific document a transaction read has a newer LSN — meaning someone else committed a write to that exact document.

**Encoding the actual implementation** (`SIProtocol_Impl.tla`):

```tla
ConflictDetected(t) ==
    \E entry \in tx_read_set[t] :
        wal_lsn > entry.read_lsn /\ wal_lsn > tx_snap[t]
```

One line changed. Now the check uses global `wal_lsn` instead of per-document `doc_lsn[entry.doc]`.

**The invariant** (`NoFalseAborts`):

```tla
NoFalseAborts ==
    \A t \in TxnIds :
        tx_state[t] = "aborted"
        =>
        \E entry \in tx_read_set[t] :
            doc_lsn[entry.doc] > entry.read_lsn
```

"If a transaction aborted, there must exist a document it read that was actually modified." TLC found a violation in 1,116 states: T1 reads `d1`, T2 writes `d2` (disjoint), T2 commits first (advancing `wal_lsn`), T1 then aborts — even though nothing touched `d1`.

---

## Bug 2: Cross-coordinator ordering

The code uses per-node monotonic counters for transaction IDs. Two coordinators assign IDs from independent sequences. Shards receive `ForwardEntry` messages and apply them, but there's no global sequencer to agree on a total order across coordinators.

```rust
pub struct TransactionCoordinator {
    next_txn_id: u64,   // per-node — not global
    pending: HashMap<u64, TxnState>,  // in-memory only
    node_id: u64,
}
```

The protocol spec models the *intended* behavior (global order), passes TLC. The impl spec models two independent coordinators with no ordering mechanism. TLC found a violation in 814 states: shard `s1` applies `[txn_A, txn_B]` while shard `s2` applies `[txn_B, txn_A]`.

One gotcha during spec writing: if `Coordinators = {1,2}` and `Shards = {1,2}`, the process sets overlap and TLC assigns wrong initial state to shard processes — they start at the coordinator label and never run. The spec "passed" in 26 states with no shard log entries written at all. Switched to `Coordinators = {"c1","c2"}`, `Shards = {"s1","s2"}` and immediately got the real violation.

---

## Bug 3: Coordinator crash recovery

The `pending` map (in-flight transactions) lives only in process memory. If the coordinator crashes after proposing a transaction to its local Raft log but before forwarding to all target shards, there's no recovery path — `pending` is gone, and no code replays the Raft log on restart.

```rust
// On crash: pending (HashMap) is lost.
// On restart: fresh TransactionCoordinator::new() — pending = {}.
// No Raft log replay path exists.
```

The reference spec (`CoordinatorRecovery.tla`) models correct recovery: on restart, replay the Raft log and re-forward any durably proposed transactions. The impl spec wipes `pending` on restart and does nothing else. TLC violation (`NoOrphanedApply`): shard `s1` applied the transaction, coordinator crashed, shard `s2` never received the forward.

One subtle invariant design issue: `PendingFor(t) = {}` is true both before a transaction is proposed *and* after crash+restart. The invariant needs a guard:

```tla
NoOrphanedApply ==
    \A t \in TxnIds :
        DurablelyProposed(t) /\
        (\E s \in TargetShards(t) : t \in shard_applied[s]) /\
        coord_alive /\
        PendingFor(t) = {}
        => FullyApplied(t)
```

Only fires when `t` is durably in the Raft log AND some shard applied it AND the coordinator is alive but has no pending entry. Without `DurablelyProposed`, the invariant fires on every initial state.

---

## What I learned about TLA+ itself

A few things that tripped me up (all fixed via agent debugging):

- **Invariants are checked on every reachable state**, not just at the moment you care about. If you want "at commit time, T saw a consistent snapshot," you need to save the relevant state in an auxiliary variable at commit time — not compare against mutable global state later.

- **Bound every loop.** An unbounded `goto` loop produces a state space TLC can never finish exploring. Two transactions, two documents, two shards is enough to reproduce all three bugs.

- **PlusCal reserved labels**: `Done` and `Error` can't be used as step labels in processes.

- **`pcal.trans` overwrites the cfg file** on every run, stripping all invariants. Always restore the cfg before running TLC.

- **CONSTANT declarations** go in the TLA+ header, outside the `(*--algorithm ... *)` block.

---

## Honest limitations

This is **post-hoc confirmation**, not discovery. TLC only checks invariants we wrote, derived from gaps we already suspected. It can't find bugs we didn't think to look for.

Model fidelity is also unchecked — the impl specs are our reading of the Rust code. If we misread, we either invented bugs that don't exist or missed real ones. Production TLA+ usage does *trace replay*: take TLC's counterexample trace, encode it as an integration test, run it against the real code.

What the exercise does provide: counterexample traces that are harder to dismiss than prose descriptions, and a cleaner diagnosis of *where* the gap is (implementation drift vs. design flaw).
