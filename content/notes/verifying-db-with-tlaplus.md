---
title: "Verifying a Database Implementation with TLA+"
date: 2026-05-01T01:11:25+0800
tags: [tla+, distributed-systems, databases, formal-methods]
---

*Agent-assisted exploration. I'm not a TLA+ expert — this is me learning by doing, with Claude Code helping write and debug specs. All the TLA+ was written collaboratively in a local Claude Code session.*

---

The context: I've been looking at [NodeDB](https://github.com/nodeDB-Lab/nodedb), a distributed database with a Rust implementation. All analysis is based on a snapshot of the codebase at commit [`44ff3d68`](https://github.com/nodeDB-Lab/nodedb/commit/44ff3d68e86d2994eed7f22be441bdfb33ffa77e) (2026-04-30). The TLA+ specs are on the [`tlaplus/correctness-specs`](https://github.com/pokgak/nodedb/tree/tlaplus/correctness-specs/tlaplus) branch of my fork. Reading the code, I found a few places where the implementation seemed to diverge from what the comments described. Instead of just writing it up as prose bugs, I wanted to try TLA+ to make the case more formally.

This is **not** spec-first design (the AWS/FoundationDB approach where you write TLA+ before writing code). It's closer to a formal post-mortem: read the code, form hypotheses, encode them as specs, and let TLC produce counterexample traces that are harder to argue with than prose.

---

## Why post-hoc instead of spec-first?

Spec-first (AWS, MongoDB, CockroachDB style) writes TLA+ *before* the code. TLC explores the state space and finds design bugs you didn't anticipate. The spec is the source of truth; the code is a translation of it.

Post-hoc confirmation works from the other direction: the code exists, you suspect specific bugs, you want rigorous demonstration. The tradeoff:

- **Spec-first finds unknown bugs.** Post-hoc only confirms what you already suspected.
- **Post-hoc is tractable on existing code.** Retrofitting spec-first to a running system is expensive; you'd need to reverse-engineer the design intent first anyway.
- **Confirmation bias is real.** We only checked invariants we expected to fail. The impl specs might violate other properties we never thought to write.

For a learning exercise on a codebase I didn't design, post-hoc made sense. For new greenfield work, spec-first is the better default.

---

## The three-layer structure

Rather than one monolithic spec, I used three layers per subsystem:

1. **Reference spec** — defines what "correct" looks like. This is where invariants live — derived from first principles (database theory, distributed systems literature), not from reading the code. Both the protocol spec and impl spec are checked against these invariants.
2. **Protocol spec** — models what the code *intends* to do, as described in comments and docs. Verified it satisfies the reference invariants.
3. **Implementation spec** — models what the code *actually* does. One targeted change per spec. Verified TLC finds the expected violation.

**Why three layers instead of two?** If the impl spec violates an invariant, you don't know if the *design* is broken or the *code* just drifted from a sound design. The protocol spec answers that. For all three bugs here, the protocol spec passed — meaning the designs are sound and the violations are pure implementation drift. If the protocol spec had also failed, the bug would be in the design, requiring a different kind of fix.

---

## Bug 1: False aborts in Snapshot Isolation

### The invariant and where it comes from

Snapshot Isolation is a well-defined isolation level from the database literature. Its core guarantee: **a transaction aborts only if there is a genuine write-write conflict** — another committed transaction modified a key that this transaction also read or wrote. Unrelated writes by other transactions must never cause an abort.

This gives us `NoFalseAborts` directly — it's not derived from the code, it's the SI definition stated formally:

```tla
NoFalseAborts ==
    \A t \in TxnIds :
        tx_state[t] = "aborted"
        =>
        \E entry \in tx_read_set[t] :
            doc_lsn[entry.doc] > entry.read_lsn
```

"If a transaction aborted, there must exist a document it read whose LSN actually increased — meaning someone else committed a write to that exact document."

### The violation trace

1. T1 reads `d1` at `doc_lsn["d1"] = 0`, records `read_lsn = 0`
2. T2 writes `d2` only (a different document, no reads), commits — `wal_lsn` advances to 1, `doc_lsn["d2"] = 1`, `doc_lsn["d1"]` stays 0
3. T1 tries to commit — the implementation checks the condition, aborts T1
4. TLC checks `NoFalseAborts` for T1: `tx_state[T1] = "aborted"` is true, so it looks for a document T1 read whose LSN increased. T1 only read `d1`, and `doc_lsn["d1"] = 0 = entry.read_lsn`. **No such document exists — invariant violated.**

T2 having no reads is important: if T2 also read a document, it could have been aborted under this implementation too. Making T2 write-only ensures it commits cleanly and advances `wal_lsn`, which is the exact setup needed to trigger T1's false abort.

### How the implementation produces this trace

The code in `transaction_cmds.rs`:

```rust
for (_collection, _doc_id, read_lsn) in &read_set {
    if current > *read_lsn && current > snapshot_lsn {
        // abort
    }
}
```

`_collection` and `_doc_id` are ignored. The condition checks: "has the node's WAL LSN advanced past this read?" — a node-local write fence. `self.state.wal.next_lsn()` is the WAL for this specific node, not the whole cluster. In a distributed deployment, writes landing on other nodes don't advance this WAL. The false abort is therefore scoped to **intra-node concurrent transactions**: any two transactions on the same node touching unrelated documents will abort each other. Cross-node writes are dispatched through a separate event-plane path and don't contribute to this WAL position. In the trace above, T2's commit advanced `current` (global `wal_lsn`) from 0 to 1. When T1 evaluates `current (1) > read_lsn (0)`, it fires — even though `d1` was never touched.

The impl spec encodes this faithfully:

```tla
ConflictDetected(t) ==
    \E entry \in tx_read_set[t] :
        wal_lsn > entry.read_lsn /\ wal_lsn > tx_snap[t]
```

`wal_lsn` → `current`, `entry.read_lsn` → `*read_lsn`, `tx_snap[t]` → `snapshot_lsn`. The second conjunct is technically redundant (since `read_lsn >= snapshot_lsn` always, `wal_lsn > read_lsn` implies `wal_lsn > snapshot_lsn`) but kept to mirror the Rust exactly. TLC found the violation in 1,116 states.

---

## Bug 2: Cross-coordinator ordering

> **Caveat discovered after publication:** The `TransactionCoordinator` struct modeled below (`nodedb-cluster/src/cross_shard_txn.rs`) is exported but never instantiated in production code — only in unit tests. No feature flag, no binary entry point, no production call site. Production cross-shard transactions actually flow through `nodedb/src/event/cross_shard/` — a `CrossShardDispatcher`/`CrossShardReceiver` pattern with per-target-node QUIC queues, FIFO-per-source-vshard ordering, and a persistent DLQ — which we did not model. The bug as described is real for the code we verified; whether the live path has analogous ordering issues is an open question. This is a concrete instance of the model-fidelity gap named in the limitations section: the TLA+ only checks what you model, and you can model code that never runs.

### The invariant and where it comes from

Distributed database correctness requires that all replicas agree on the order in which transactions are applied. If two shards apply the same two transactions in different orders, they will diverge. This is the replica agreement principle — a fundamental requirement for any system claiming consistent cross-shard transactions.

```tla
CrossCoordOrderHolds ==
    \A t1, t2 \in Txns :
        /\ t1 # t2
        /\ txn_coord[t1] # txn_coord[t2]   \* different coordinators
        /\ \A s \in Shards : AppliedOn(t1, s) /\ AppliedOn(t2, s)
        =>
        \* All shards agree on the relative order of t1 and t2.
        \/ \A s \in Shards : PosInShardLog(t1, s) < PosInShardLog(t2, s)
        \/ \A s \in Shards : PosInShardLog(t2, s) < PosInShardLog(t1, s)
```

"For any two transactions from different coordinators that both shards applied, all shards must have applied them in the same relative order."

### The violation trace

1. Coordinator `c1` proposes `txn_A`, coordinator `c2` proposes `txn_B` — simultaneously, with no global ordering
2. Shard `s1` receives `txn_A` first, applies `[txn_A, txn_B]`
3. Shard `s2` receives `txn_B` first, applies `[txn_B, txn_A]`
4. `CrossCoordOrderHolds` checks: `PosInShardLog(txn_A, s1) = 1 < PosInShardLog(txn_A, s2) = 2` but `PosInShardLog(txn_B, s1) = 2 > PosInShardLog(txn_B, s2) = 1`. Neither ordering holds globally — **invariant violated.**

### How the implementation produces this trace

The code uses per-node monotonic counters with no global sequencer:

```rust
pub struct TransactionCoordinator {
    next_txn_id: u64,   // per-node — not global
    pending: HashMap<u64, TxnState>,  // in-memory only
    node_id: u64,
}
```

Two coordinators assign IDs from independent sequences. `ForwardEntry` messages arrive at shards in non-deterministic order. Nothing enforces a consistent global order across coordinators — shards apply in arrival order. The impl spec models this: two coordinators each with their own counter, shards with a non-deterministic inbox. TLC found the violation in 814 states.

The code comments claim "Calvin protocol" — real Calvin requires a single global sequencer that imposes a total order before execution. That global sequencer doesn't exist here.

**A gotcha that made the spec pass vacuously**: with `Coordinators = {1,2}` and `Shards = {1,2}`, the process ID sets overlap and shard processes never run. The spec "passed" in 26 states with an empty shard log. Switching to disjoint string IDs (`{"c1","c2"}` and `{"s1","s2"}`) immediately produced the real violation. After any unexpected fast pass: check that the interesting processes actually ran and that key variables have entries.

---

## Bug 3: Coordinator crash recovery

> **Same caveat as Bug 2:** `TransactionCoordinator` is dead code. The live cross-shard path has a persistent DLQ (backed by redb) and a persistent HWM store — a different recovery story than the one modeled here. The crash scenario below applies to the unwired coordinator, not to production behavior.

### The invariant and where it comes from

Crash safety requires that durable state survives process restarts. If a transaction was durably committed to the Raft log, it must eventually be applied on all its target shards — even if the coordinator crashes mid-way through forwarding. This is the standard crash-recovery principle that 2PC was designed to guarantee.

From the reference spec (`CoordinatorRecovery.tla`):

```tla
NoOrphanedApply ==
    \A t \in TxnIds :
        DurablelyProposed(t) /\ txn_state[t] = "committed"
        =>
        \A s \in raft_log[entry].shards : t \in shard_applied[s]
```

"Every durably proposed, committed transaction must be applied on all its target shards."

### The violation trace

1. Coordinator proposes transaction `t1` to its local Raft log — durably committed
2. Coordinator forwards `ForwardEntry` to shard `s1` — `s1` applies `t1`
3. Coordinator crashes before forwarding to `s2` — `pending` (in-memory HashMap) is wiped
4. Coordinator restarts with empty `pending` — no replay path, `t2` is forgotten
5. `NoOrphanedApply` checks: `t1` is durably in the Raft log and `s1` applied it, but `s2` never received the forward. **Invariant violated.**

### How the implementation produces this trace

```rust
pub struct TransactionCoordinator {
    next_txn_id: u64,
    pending: HashMap<u64, TxnState>,  // in-memory only — lost on crash
    node_id: u64,
}
```

`pending` is not persisted. On restart, `TransactionCoordinator::new()` starts with empty `pending`. No code replays the Raft log to reconstruct in-flight transactions. The impl spec models this: `Crash()` wipes `pending`, `Restart()` starts with `pending = {}`. TLC found the violation in 588 states.

**A subtle invariant design problem**: `PendingFor(t) = {}` is true in two situations — before proposal (the transaction doesn't exist yet) and after crash+restart (it was wiped). The invariant needs a guard to fire only in the crash case:

```tla
NoOrphanedApply ==
    \A t \in TxnIds :
        DurablelyProposed(t) /\
        (\E s \in TargetShards(t) : t \in shard_applied[s]) /\
        coord_alive /\
        PendingFor(t) = {}
        => FullyApplied(t)
```

In normal operation, even after all shards are forwarded, the coordinator keeps the entry in `pending` with an empty `waiting` set — so `PendingFor(t) = {}` is false. Only after crash+restart is `pending` wiped entirely. This asymmetry is deliberate: it makes the invariant fire precisely in the bug case and nowhere else. Sketch the three cases when designing any safety invariant — before the operation, during normal completion, and after the bug scenario — and verify the trigger is false for the first two.

---

## Gap 4: HLC not applied to data transactions (skipped)

There's a fourth gap: NodeDB's Hybrid Logical Clock is applied to metadata operations (DDL, descriptor leases) but not to regular data transactions. Data transactions use WAL LSN, which is local per-node — cross-node data reads can observe different orderings depending on which node serves the read.

No impl spec was written for this. It's an architectural choice spread across multiple files, lower-priority, and would require modelling the full distributed read path. The tradeoff: this is the one gap with no formal counterexample — the claim rests on prose analysis only.

---

## What I learned about TLA+ itself

**Invariants are checked on every reachable state**, not just at the moment you care about. The first attempt at `ConsistentSnapshot` violated this: after T1 committed cleanly, T2 wrote to the same document, and TLC flagged T1 as having seen an inconsistent snapshot — even though T1 was already done. The fix: save the relevant state in an auxiliary variable (`tx_doc_lsn_at_commit`) at the exact moment of commit, and check against that, not against mutable global state.

**Bound every loop.** An unbounded `goto` loop produces a state space TLC can never finish. Two transactions, two documents, two shards is enough to reproduce all three bugs — adding a third only multiplies the state space without finding new violation paths.

**Why 2 of each?** One of anything can't exhibit concurrency bugs by definition. Two is the minimum for interleaving. More than two grows the state space exponentially without contributing new counterexample shapes.

**PlusCal reserved labels**: `Done` and `Error` can't be used as step labels. Rename to `Finish`, `CoordDone`, etc.

**`pcal.trans` overwrites the cfg file** on every run, stripping all invariants. Always restore the cfg before running TLC.

**Mixed process ID types cause fingerprint errors.** All process IDs across all process sets must be the same type — all strings or all integers.

**`CONSTANT` declarations belong in the TLA+ header**, outside the `(*--algorithm ... *)` block.

**`if ... goto ... end if` followed by more statements** requires a new label — the translator can't determine the atomic boundary when control flow can either jump or fall through.

---

## Honest limitations

**Post-hoc confirmation, not discovery.** TLC only checks invariants we wrote, derived from gaps we already suspected. It can't find bugs we didn't think to look for.

**Model fidelity is unchecked.** The impl specs are our reading of the Rust code. If we misread, we either invented bugs that don't exist or missed real ones. Production TLA+ usage does *trace replay*: take TLC's counterexample, encode it as an integration test, run it against the real code, confirm behavior matches.

**One-shot, not iterative.** A refactor next week could fix or worsen these gaps and the specs wouldn't notice. Production teams run TLC in CI and gate merges on it.

What the exercise provides: counterexample traces that are harder to dismiss than prose, and a precise diagnosis of whether the gap is implementation drift (code diverged from sound design) or a design flaw (the design itself violates the invariant).
