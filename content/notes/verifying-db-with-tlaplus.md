---
title: "Verifying a Database Implementation with TLA+"
date: 2026-05-01T01:11:25+0800
tags: [tla+, distributed-systems, databases, formal-methods]
---

*Agent-assisted exploration. I'm not a TLA+ expert — this is me learning by doing, with Claude Code helping write and debug specs. All the TLA+ was written collaboratively in a local Claude Code session.*

---

The context: I've been looking at [NodeDB](https://github.com/nodeDB-Lab/nodedb), a distributed database with a Rust implementation. Reading the code, I found a few places where the implementation seemed to diverge from what the comments described. Instead of just writing it up as prose bugs, I wanted to try TLA+ to make the case more formally.

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

1. **Reference spec** — what does "correct" look like? Define invariants independently of any implementation.
2. **Protocol spec** — what does the code *intend* to do? Model the design as described in comments and docs. Verify it satisfies the reference invariants.
3. **Implementation spec** — what does the code *actually* do? One targeted change per spec. Verify TLC finds the expected violation.

**Why three layers instead of two?** You could skip the protocol spec and go straight from reference to impl. But if the impl spec violates an invariant, you don't know if the *design* is broken or the *code* just drifted from a sound design. The protocol spec answers that. For all three bugs here, the protocol spec passed — meaning the designs are internally sound and the violations are pure implementation drift. That's a more precise diagnosis.

If the protocol spec had *also* violated an invariant, the bug would be in the design itself, not just the code. A different kind of fix is required.

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

`_collection` and `_doc_id` are both ignored (underscore prefix). The check is: "has the global WAL LSN advanced past this read?" That's a global write fence, not per-document conflict detection.

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

The key change: `doc_lsn[entry.doc]` replaced by `wal_lsn`. Both conjuncts mirror the Rust exactly. The second conjunct (`wal_lsn > tx_snap[t]`) is technically redundant — since `read_lsn >= snapshot_lsn` always holds, `wal_lsn > read_lsn` implies `wal_lsn > snapshot_lsn` — but it's in the Rust and keeping it in the spec is a deliberate fidelity choice. If we dropped it, we'd be checking a slightly different predicate than what the code does.

**The invariant** (`NoFalseAborts`):

```tla
NoFalseAborts ==
    \A t \in TxnIds :
        tx_state[t] = "aborted"
        =>
        \E entry \in tx_read_set[t] :
            doc_lsn[entry.doc] > entry.read_lsn
```

"If a transaction aborted, there must exist a document it read that was actually modified by someone else."

TLC found a violation in 1,116 states. The counterexample: T1 reads `d1`, T2 writes `d2` only (no reads, so T2's own `ConflictDetected` won't fire), T2 commits first (advancing `wal_lsn` from 0 to 1), T1 then tries to commit — `wal_lsn (1) > read_lsn (0)` is true, so T1 aborts. But `doc_lsn["d1"]` is still 0 — `d1` was never touched.

The reason T2 having no reads matters: if T2 had also read some document, it could have aborted too under this implementation. Making T2 a write-only transaction ensures it commits cleanly and advances `wal_lsn`, which is exactly the setup needed to trigger T1's false abort.

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

**A gotcha that made the spec pass vacuously**: if `Coordinators = {1,2}` and `Shards = {1,2}`, the process ID sets overlap. TLC builds a unified `ProcSet` and assigns initial `pc` state based on the first matching clause in the `CASE` statement. Since coordinators come first, shard processes also start at the coordinator label and never reach the `Apply` step. The spec "passed" in 26 states with no shard log entries ever written.

**Why this is dangerous**: a spec that passes vacuously looks like a passing spec. The signal was the suspiciously low state count (26 states) and an empty shard log. After switching to disjoint string IDs (`Coordinators = {"c1","c2"}`, `Shards = {"s1","s2"}`), TLC immediately found the `CrossCoordOrderHolds` violation in 814 states.

**Rule of thumb**: after a spec passes faster than expected, check whether the interesting processes actually ran. Look at the state count vs. what you'd expect, and inspect key variables (shard logs, message queues) to confirm they have entries.

---

## Bug 3: Coordinator crash recovery

The `pending` map (in-flight transactions) lives only in process memory. If the coordinator crashes after proposing a transaction to its local Raft log but before forwarding to all target shards, there's no recovery path — `pending` is gone on restart, and no code replays the Raft log.

```rust
// On crash: pending (HashMap) is lost.
// On restart: fresh TransactionCoordinator::new() — pending = {}.
// No Raft log replay path exists.
```

The reference spec (`CoordinatorRecovery.tla`) models correct recovery: on restart, replay the Raft log and re-forward any durably proposed transactions. The impl spec wipes `pending` on restart and does nothing else. TLC violation (`NoOrphanedApply`): shard `s1` applied the transaction, coordinator crashed, shard `s2` never received the forward.

**A subtle invariant design problem**: `PendingFor(t) = {}` is true in two distinct situations — (1) before the transaction is proposed (it doesn't exist yet), and (2) after crash+restart (it was wiped). If the invariant just checks `PendingFor(t) = {}`, it fires on every initial state, which is wrong.

The fix is an asymmetric trigger:

```tla
NoOrphanedApply ==
    \A t \in TxnIds :
        DurablelyProposed(t) /\
        (\E s \in TargetShards(t) : t \in shard_applied[s]) /\
        coord_alive /\
        PendingFor(t) = {}
        => FullyApplied(t)
```

This fires only when `t` is durably in the Raft log AND some shard applied `t` AND the coordinator is alive but has no pending entry. That combination is impossible in normal operation — in the normal path, even after all shards are forwarded, the coordinator keeps the entry in `pending` with an empty `waiting` set. `PendingFor(t) = {}` only becomes true after crash+restart wiped the map entirely. The asymmetry is deliberate and is what makes the invariant precise.

**The design lesson**: when writing a safety invariant for "a state that should never be stable," sketch all three cases: (1) before the operation, (2) during normal completion, (3) after the bug scenario. The trigger condition must be false for (1) and (2) but true only for (3).

---

## Gap 4: HLC not applied to data transactions (skipped)

There's a fourth gap identified in the analysis: NodeDB's Hybrid Logical Clock (HLC) is applied to metadata operations (DDL, descriptor leases) but not to regular data transactions. Data transactions use WAL LSN, which is local per-node — meaning cross-node data reads can observe different orderings depending on which node serves the read.

**Why no impl spec for this one**: it's an architectural choice spread across multiple files rather than a single code path, and it was flagged as lower-priority. Writing a meaningful spec would require modelling the full distributed read path, not just one targeted change. The tradeoff of omitting it: this is the one gap with no formal counterexample. The claim rests on prose analysis only.

---

## What I learned about TLA+ itself

Things that tripped me up:

**Invariants are checked on every reachable state**, not just at the moment you care about. If you want "at commit time, T saw a consistent snapshot," you need to save the relevant state in an auxiliary variable at commit time — not compare against mutable global state later. The first attempt at `ConsistentSnapshot` violated this: after T1 committed cleanly, T2 wrote to the same document, and TLC flagged T1 as having seen an inconsistent snapshot. T1 was already done; T2's write was correct. The fix was adding `tx_doc_lsn_at_commit` — a snapshot of `doc_lsn` saved at the exact moment each transaction commits, before its own writes are applied.

**Bound every loop.** An unbounded `goto` loop produces a state space TLC can never finish. At one point, TLC ran for 15+ minutes generating 300M+ states with no end. The fix: replace `goto` loops with a fixed sequence of labeled steps (one read, one write, one commit per transaction). Two transactions, two documents, two shards is enough to reproduce all three bugs — adding a third only multiplies the state space without finding anything new.

**Why 2 of each?** Any single-entity model (one transaction, one shard) can't exhibit concurrency bugs by definition. Two is the minimum that allows interleaving. More than two grows the state space exponentially and usually doesn't add new violation paths for these kinds of bugs.

**PlusCal reserved labels**: `Done` and `Error` can't be used as step labels in processes — the translator rejects them. Rename to `Finish`, `CoordDone`, etc.

**`pcal.trans` overwrites the cfg file** on every run, stripping all invariants and leaving only the `SPECIFICATION Spec` line. Always restore the cfg immediately after translation before running TLC.

**Mixed process ID types cause fingerprint errors.** All process IDs across all process sets must be the same type. If you have `process Clock = "clock"` (string) and `process Committer \in Groups` where `Groups = {1}` (integer), TLC errors when building `ProcSet`. Keep everything strings or everything integers.

**`CONSTANT` declarations belong in the TLA+ header**, outside the `(*--algorithm ... *)` block. Putting them inside causes `pcal.trans` to reject with "Expected 'begin' but found 'CONSTANT'."

**`if ... goto ... end if` followed by more statements** requires a new label. An `if` with an internal `goto` must end a labeled block — the translator can't determine the atomic boundary when control flow can either jump away or fall through. Split it into two labeled blocks.

---

## Honest limitations

**Post-hoc confirmation, not discovery.** TLC only checks invariants we wrote, derived from gaps we already suspected. We cannot find bugs we didn't think to look for.

**Model fidelity is unchecked.** The impl specs are our reading of the Rust code. If we misread, we either invented bugs that don't exist or missed real ones. Production TLA+ usage does *trace replay*: take TLC's counterexample, encode it as an integration test, run it against the real code, confirm behavior matches. That validates the model and produces a regression test simultaneously. We didn't do that here.

**One-shot, not iterative.** Real spec-first work cycles spec ↔ code many times. A refactor next week could fix or worsen these gaps and the specs wouldn't notice. Production teams run TLC in CI and gate merges on it.

What the exercise provides: counterexample traces that are harder to dismiss than prose descriptions, and a precise diagnosis of *where* the gap is (implementation drift vs. design flaw). That's a narrower claim than production-grade verification, but it's the right tool for the problem: existing code, suspected bugs, need for rigorous demonstration.
