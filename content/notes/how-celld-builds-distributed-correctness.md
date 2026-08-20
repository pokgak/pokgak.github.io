---
title: "How celld Builds Distributed Correctness Without Consensus"
date: 2026-08-21T00:41:16+0800
tags: [distributed-systems, databases, sqlite, durability, testing]
---

I went through [Deno's celld](https://github.com/denoland/celld), looking specifically for the mechanisms that protect correctness when nodes race, pause, crash, lose replies, or restore stale state.

The snapshot is [`89e4ffc` (v0.3.0)](https://github.com/denoland/celld/commit/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9), 20 August 2026. "Correctness" here means the guarantees celld actually targets, not every property a general distributed database might offer.

## The Scope Reduction Is the First Correctness Mechanism

- Every Durable Object is an independent **cell** with its own SQLite database.
- A cell has one authoritative writer at a time.
- There are no cross-cell transactions, global serial order, or consensus group spanning the fleet.
- Nodes are replaceable. Coordination and long-term recovery state live in an object-storage bucket.

That changes the problem from "make every node agree on one database" to "make every cell have one writer and never lose an acknowledged write."

The bucket is celld's synchronization substrate. It must provide conditional create, conditional overwrite, and read-after-write consistency. This is a hard dependency, not a performance preference. A store that silently ignores preconditions can create split brain. celld [probes that contract](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/celld/bucket.rs#L723-L790) at startup.

```text
                         conditional writes
                    ┌────────────────────────┐
                    │ object-storage bucket  │
                    │ ownership, leases, LTX │
                    └───────┬────────┬───────┘
                            │        │
                    ┌───────▼──┐  ┌──▼───────┐
                    │  node A  │  │  node B  │
                    └────┬─────┘  └────┬─────┘
                         │             │
                    cell x/SQLite  cell y/SQLite
                    one writer     one writer
```

This is not "consensus without consensus." The design avoids needing general consensus by sharding authority down to a single conditional-write record per cell.

## 1. Ownership Is a Compare-and-Swap Record

Each cell has an ownership object containing an owner session and monotonically increasing epoch.

- Acquisition is conditional create when no record exists, otherwise compare-and-swap against the version just read.
- Racing nodes cannot both successfully install themselves as owner.
- Release is also read-then-CAS. A delayed release from an old owner cannot erase a successor's record.
- An ambiguous CAS result is **read back and reconciled**, not blindly repeated. Reconciliation is bounded so a broken store cannot hold resources forever.

The implementation is in [`BucketOwnership`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/celld/ownership_store.rs#L321-L362); the fencing argument is written down in [`docs/fencing.md`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/docs/fencing.md#L15-L41).

## 2. Epochs Fence Data, Not Just Metadata

Winning an ownership record is insufficient if an old process is paused and later resumes. celld carries the ownership epoch into the data path:

```text
cells/<cell>/ltx/e<epoch>/
```

- Every activation advances the epoch, including a local wake.
- A stale writer might continue uploading, but only into its obsolete epoch prefix.
- Restore chooses the newest epoch with data and applies a contiguous transaction chain.
- Ownership records, local database paths, gated writes, and peer-log entries all carry the epoch.

The epoch turns split-brain writes from "two writers corrupt one history" into "a stale writer can only append to a lineage that future owners will not select."

## 3. Node Leases Fence Whole Processes

Cell epochs fence individual lineages; node leases fence a process session.

- A lease has a process generation and bucket-published expiry.
- It renews at one-third of its lifetime; the default TTL is 10 seconds.
- A node self-fences if the lease expires, disappears, or is replaced by another generation.
- Fencing stops cells, fails incomplete requests, and terminates the process with status 3. A potentially stale process is never "unfenced" in place.
- The local deadline is anchored to when expiry was calculated, not when a slow bucket request returns. Network delay therefore cannot accidentally extend authority.
- Each request also checks the published expiry, narrowing the window before process-wide fencing runs.

Takeover authority comes from the bucket lease, not peer suspicion. Peer probes are diagnostic only; celld deliberately has no separate gossip membership or failure-detector protocol.

## 4. A Response Waits Behind an Output Gate

The central durability rule is: **do not acknowledge a write until there is proof it can survive loss of the owner.**

For bucket durability:

1. SQLite commits locally.
2. celld captures the change as an LTX segment.
3. The segment reaches the bucket.
4. celld rereads ownership.
5. It releases the response only if the record still names the same node and epoch.

This final check uses authority state rather than elapsed time, so a long process pause or clock skew cannot make an obsolete writer appear current.

Read-only requests are coupled to this rule too. If a read observes state from a write whose proof is still pending, its response becomes a follower of that gated write. It cannot expose unproved state independently. The gate tracks these dependencies explicitly in [`GatedWrite`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/logic/lib.rs#L205-L234).

The output gate is enabled by default. [`CELLD_OUTPUT_GATE=0`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/docs/README.md#L377-L385) is an explicit acceptance of possible acknowledged-write loss, not an innocent tuning flag.

## 5. Peer Replication Accelerates Proof, but the Bucket Remains Authority

v0.3 adds a replicated write-behind node log. A captured LTX segment is sent to a follower ensemble and can be acknowledged after **every** ensemble member has fsynced the contiguous fragment. Bucket upload continues behind it.

- This is write-all/ack-all, not quorum acknowledgment.
- If one follower fails, celld falls back to bucket proof until it can recruit a healthy ensemble.
- Reconfiguration is allowed only after the old fragment is bucket-covered through the transition point.
- Sequence offsets must be contiguous. Epoch changes reset sequence numbers and watermarks.
- A follower persists a seal mark before replying and rejects the wrong fragment epoch, noncontiguous appends, or writes at/below the seal.
- A per-leader mutex covers follower fragment read-modify-write, preventing one append from overwriting another append's persisted seal.

This trades peer-tier availability for a simple recovery proof: because acknowledgment required every follower, any correctly sealed matching follower contains every acknowledged frame.

The policy is small enough to inspect directly in [`log_tier.rs`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/logic/log_tier.rs#L66-L165).

## 6. Recovery Must Finish Before Takeover

Before the first peer-only acknowledgment, the leader publishes an open node-log record in its lease. That record is the recovery interlock:

- **No record**: this session never acknowledged beyond bucket state.
- **Open/recovering**: peer data must be recovered before restoring the cell.
- **Sealed**: recovery is complete.

A recovering node CASes `Open → Recovering`, seals matching followers, gathers retained fragments, uploads missing per-cell LTX objects to the bucket, then CASes the record to `Sealed`. Only after this can ownership move forward and restore begin.

Recovery may preserve an unacknowledged tail. This is intentional: "the client saw an error" does not mean "the transaction definitely did not commit." The safety promise is that acknowledged writes are not lost, not that failed requests are rolled back.

Restore itself has several guards:

- It reads the full contiguous LTX chain from transaction zero in the newest usable epoch.
- Missing middle segments, invalid headers, bad versions, impossible WAL geometry, and checksum failures are rejected.
- Reconstruction happens in a temporary file, which is fsynced and atomically renamed into place.
- Existing output is not overwritten.
- If local history falls behind the remote replica, celld seeds a new local baseline rather than silently continuing from a lower transaction ID.

LTX validation and atomic publication live in [`ltx.rs`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/ltx/src/ltx.rs#L200-L313) and [`replica.rs`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/ltx/src/replica.rs#L377-L475).

## 7. Ambiguity Is Preserved Instead of Guessed Away

Distributed failures often leave "did it happen?" unanswered. celld treats that as a state to reconcile, not an excuse to retry everything.

- Conditional writes have transport retries disabled. A 409/412 is a definite rejection; another error is ambiguous and must be read back.
- Forwarded application requests retry once after a definite `NotOwner` or if no connection was made.
- Once a request may have gone on the wire, it is not automatically retried. That preserves at-most-once intent and surfaces ambiguity instead of risking duplicate execution.
- LTX uploads and recovery PUTs use deterministic keys, making those infrastructure operations idempotent within a fenced epoch.
- Deletes treat absence as success.
- Peer authentication rejects nonce replay within the signature window, but this is transport replay protection, not durable application-level deduplication.

Applications needing exactly-once business operations still need persisted idempotency keys.

## 8. Local Concurrency Is Explicitly Serialized

The distributed protocol cannot help if two turns mutate one in-process object concurrently.

- Each cell runs through one isolate lock; its SQLite maps are isolate-owned.
- `blockConcurrencyWhile` uses an input gate that prevents another event from entering JavaScript while the holder runs.
- Nested holds are counted, non-holders cannot release the gate, and a cancelled holder is abandoned so it cannot wedge the cell forever.
- Alarms and ordinary requests carry ownership in the state machine, preventing overlapping delivery.
- Exposed application SQL cannot issue raw transaction/savepoint control, attach databases, access reserved runtime tables, or use unsafe pragmas. SQLite transaction boundaries remain under the runtime's control.

The input gate is a compact example of turning concurrency rules into checked state rather than convention: [`gate.rs`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/logic/gate.rs#L3-L144).

## 9. Ordering Is Checked at Every Layer

- LTX segments advance one transaction ID at a time.
- Restore accepts only a contiguous chain and applies it in plan order, even when downloads overlap.
- Peer fragments accept only `end + 1`.
- Shipping credits advance only over a covered prefix; a later completed batch cannot skip a gap.
- Ensemble reconfiguration waits until all shipped data through the transition is bucket-covered.
- Events blocked by the input gate stay on the original ordered channel instead of being copied into a second queue.

There is no global ordering across cells. Ordering is deliberately scoped to the one lineage where it is required.

## 10. Durability Boundaries Are Chosen Deliberately

Local SQLite uses WAL mode with `synchronous=NORMAL`. That protects normal process crashes, but recent local commits may be lost on power/OS failure. celld does not pretend this local setting is its distributed durability boundary; LTX replication plus the output gate is.

The same discipline appears around eviction and shutdown:

- Pressure eviction must prove an epoch recoverable remotely before removing the last local copy.
- Graceful shutdown becomes unhealthy, rejects new work, drains current requests, and releases cells with bounded concurrency.
- A node log can be gracefully sealed only when no captured batch is between stages and all shipped frames exist in per-cell bucket storage, not merely an optimization bundle.
- Refusing to seal is safe; a future session recovers the open record.

Resource accounting also fails conservatively. The preserved-snapshot cache rescans filesystem truth, retains failed deletions in byte totals, and treats undercounting as unsafe. Resource correctness matters when a mistaken eviction can become data loss.

## 11. Protocol and Input Validation Prevent Silent Divergence

- Peer requests bind method, path/query, body hash, source and target sessions, timestamp, nonce, and protocol version under HMAC-SHA-256.
- The replay cache fails closed at its capacity.
- Peer protocol versions must match exactly; incompatible peers receive 426.
- LTX and node-log formats have magic bytes, explicit versions, bounded decoding, and trailing-byte rejection.
- Deployment manifests carry schema versions and required feature gates. A node rejects features it cannot implement instead of partially loading them.
- Cell identifiers are one bounded path component; traversal, separators, controls, `.` and `..` are rejected.
- Configuration rejects unknown or contradictory credential modes rather than choosing an interpretation.

These checks are not the ownership protocol, but they stop malformed, stale, or partially understood input from entering it.

## 12. Correctness Logic Is Separated From I/O

The coordination core is a pure event/decision state machine: adapters deliver an event, [`on_event`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/logic/lib.rs#L1-L7) advances state and returns effects, and adapters execute those effects. Production and simulation use the same transition logic.

That structure enables a broad [`State::validate`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/crates/logic/lib.rs#L900-L995) pass after events. It checks, among other things:

- occupancy never crosses the hard ceiling;
- requests, alarms, transports, and gated writes refer to resident cells;
- read followers remain attached to the write that made their state visible;
- operation completions still match the state that issued them;
- operation IDs do not overflow.

Assertions also guard narrower contracts: storage access outside an installed turn, invalid gate release, and impossible log transitions fail loudly rather than silently corrupting state.

## 13. Testing Attacks Both the Model and the Implementation

celld's test strategy is layered:

- **Differential conformance** runs the same Worker programs on workerd and celld and compares results.
- **TLA+ model checking** targets one writer per epoch and no acknowledged write loss. The project reports that it found four bugs and one split-brain, including an eight-state dormant-resume/release race.
- **Deterministic simulation** drives the production logic core through seeded schedules with latency, CAS races, lost replies, clock drift, crashes at await points, nonterminating handlers, and truncated streams.
- **Mutation of the protocol** deliberately breaks safeguards and checks that the simulator catches the resulting violations. This tests the checker, not only the happy implementation.
- **Live fleet fault injection** uses `SIGKILL`, frozen owners, bucket partitions, sustained 429s, host shutdown, and deletion of local databases.
- **LTX fault tests** cover truncation, corruption, missing middle frames, missing snapshots, and recovery to an earlier valid transaction.
- **Property tests** generate random inserts, updates, deletes, DDL, bulk transactions, and checkpoints, then compare fully restored database contents.
- **Fuzz-style parser tests** feed adversarial and mutated bytes to LTX, WAL, and bundle decoders and assert clean rejection rather than panic.

The testing design is documented in [`docs/testing.md`](https://github.com/denoland/celld/blob/89e4ffc53a14ecb496d2ca5014ff9d19b0061ad9/docs/testing.md). Important caveats: the TLA+ model is hand-synchronized and not in CI; it assumes a linearizable store and perfect shared clocks. The parser tests are bounded deterministic fuzz-style tests, not continuous coverage-guided fuzzing. Some property tests skip without the external `sqlite3` oracle.

## 14. Operations Are Part of the Correctness Story

- Startup probes the bucket's compare-and-swap semantics, distinguishing definite contract violation from transient ambiguity.
- `/state` and `celld diagnose` expose ownership/restoration phases, expired records, malformed peers, unreachable nodes, authentication/version mismatch, pressure, and shedding.
- `restoring` is an operational rollout signal: wait for cold recovery to settle before removing more capacity.
- Self-fencing emits a distinctive `SELF-FENCE:` reason and exit status.
- Telemetry correlates requests, cells, isolates, queue waits, outbound calls, and known durability facts.
- Telemetry is shed before application work under pressure, and the drop count is retained.

There are currently logs, traces, and state endpoints, but no metrics. Observability does not prove safety; it makes violated assumptions and stuck recovery visible before operators improvise around the protocol.

## What celld Does Not Guarantee

- **No Byzantine tolerance.** Bucket credentials and the private peer network are trusted. A compromised credential is fleet-admin authority.
- **No cross-cell transaction or global ordering.** Each cell is an independent consistency domain.
- **No exactly-once request result.** An ambiguous on-wire operation stays ambiguous.
- **No guarantee that an unacknowledged write is absent.** Recovery may retain it.
- **No safety on an object store with broken conditional-write semantics.** The startup probe is useful evidence, not a proof of provider behavior under every load or failure.
- **No peer-tier quorum availability.** Write-all makes the proof simple; one failed follower sends acknowledgment back to the bucket path.
- **No clock-free system.** Ownership revalidation avoids clock-based write acknowledgment, but lease expiry and peer signature windows still depend on clocks.
- **No hostile multi-tenancy boundary yet.** The project describes itself as alpha; its internal operator API and network must be protected externally.

## The Reusable Pattern

celld's strongest idea is not any single algorithm. It is the repeated conversion of uncertainty into explicit, inspectable state:

| Uncertainty | Explicit state |
|---|---|
| Who may write? | ownership CAS + epoch |
| Is this process still authoritative? | generation-bound node lease |
| Can this response leave? | gated write + durability proof |
| Did a conditional write happen? | read-back reconciliation |
| Did peers preserve the tail? | contiguous fragment + durable seal |
| Can takeover restore safely? | open → recovering → sealed log record |
| Is replica data complete? | contiguous TXIDs + checksums |
| Could a request have executed? | no retry after ambiguous on-wire failure |

The general lesson: make stale authority unable to touch the current lineage, make acknowledgment wait for a named proof, and preserve ambiguity whenever the system cannot safely resolve it. Then put the same transition logic under model checking, deterministic simulation, corruption tests, and live failure injection.

That is how celld gets a strong, narrow distributed guarantee without turning every cell into a consensus group.
