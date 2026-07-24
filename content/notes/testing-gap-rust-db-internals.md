---
title: "On Writing a Testable Database"
date: 2026-05-03T11:22:54+0800
tags: [rust, testing, databases, property-based-testing, deterministic-simulation]
---

*Follows on from [Verifying a Database Implementation with TLA+](/notes/verifying-db-with-tlaplus/). That note found three bugs in [NodeDB](https://github.com/nodeDB-Lab/nodedb) using TLA+ specs. This note is about why writing automated tests for those bugs is harder than it should be — and how to design a database so it isn't.*

---

## The general problem

The network boundary is not the right testability boundary.

Most database servers end up structured like this:

```
Public API (TCP, protocol, auth)    ← what's tested via integration tests
        │
   Business logic                   ← where the interesting bugs are
        │
   Storage / WAL                    ← what's tested via unit tests
```

Transport gets the full integration test harness. Storage gets unit tests. The business logic in the middle — transaction isolation, conflict detection, ordering guarantees, recovery semantics — sits in a gap. It's too deeply embedded to reach cheaply from outside, and too complex to exercise meaningfully from inside.

The result: correctness bugs in the business logic layer are either caught late (during integration tests against a full server) or not at all.

This is not a Rust problem or a NodeDB problem. It's the default outcome when teams draw the encapsulation boundary at the network interface, because that's the natural "product API," and everything below it becomes internal.

---

## NodeDB as a concrete example

After finding bugs in NodeDB's transaction layer with TLA+, the natural next step is property-based testing — generate random transaction histories, check invariants like "no false aborts." It doesn't work out of the box.

NodeDB's public API requires a live TCP server. The lightweight internal types sit behind `pub(crate)`. There's no path to the transaction logic without either spinning up a full server (WAL, dispatcher, security stores, 120+ fields in `SharedState`) or writing tests inside the crate itself.

```
NativeClient / NativeConnection    ← public, requires TCP server
        │
   Protocol dispatch               ← internal
        │
   SessionStore                    ← pub(crate), network-free ✓
        │
   TransactionCoordinator          ← internal
        │
   WAL / data plane executor       ← internal
```

`SessionStore` is the right layer — it owns conflict detection, session state, read/write tracking, and it has no network dependency. But `pub(crate)` means it's only reachable from inside the crate.

The three bugs from the TLA+ analysis all sit in this gap:

| Bug | Layer | Reachable externally |
|-----|-------|----------------------|
| False aborts (conflict detection) | `SessionStore::commit()` | Only through full server |
| Cross-coordinator ordering | `TransactionCoordinator` | No |
| Crash recovery | `TransactionCoordinator` | No |

Bug 1 would be caught immediately by a property test on `SessionStore`. Bugs 2 and 3 aren't reachable at all without full-server or significant refactoring.

---

## Retrofitting testability: three approaches

If you're working with an existing codebase, there are cheap paths forward:

**1. `#[cfg(any(test, feature = "testing"))] pub`** — the simplest escape hatch. Conditionally expose internal types under a `testing` feature flag. External test crates opt in. No API stability promise needed. Costs nothing architecturally and unblocks property-based testing immediately.

**2. Extract a `nodedb-txn` crate** — pull transaction logic into a crate with a proper public API. `SessionStore`, conflict detection, and `TransactionCoordinator` become `pub`. The main crate depends on it; test crates depend on it directly. More work, but forces a cleaner interface: transaction logic has to be expressed in explicit inputs/outputs rather than leaking server state.

**3. Define a trait at the transaction boundary** — rather than exposing the concrete type, define a trait that captures transaction operations:

```rust
pub trait TransactionEngine {
    fn begin(&self, session: SessionId, snapshot_lsn: Lsn) -> Result<()>;
    fn record_read(&self, session: SessionId, collection: &str, doc_id: &str, lsn: Lsn);
    fn commit(&self, session: SessionId) -> Result<Vec<PhysicalTask>>;
    fn rollback(&self, session: SessionId) -> Result<()>;
}
```

Tests use the trait. The real implementation and test doubles both implement it. This also makes it possible to inject time and failures through the trait boundary — leading to the deeper approach below.

---

## Building testability in from the start: state machines + DST

The retrofits above address the visibility problem. They don't address a harder problem: even if you can reach the transaction logic, concurrency bugs only appear under specific thread interleavings, and crash recovery bugs only appear when you crash at exactly the right moment. Property-based tests still run against real time, real scheduling, real I/O — you can't reproduce a rare ordering reliably.

The deeper solution is **Deterministic Simulation Testing (DST)**, and it requires designing the database around it from the start.

[Polar Signals](https://www.polarsignals.com/blog/posts/2025/07/08/dst-rust) rebuilt their profiling database in Rust with DST as a first-class constraint. Every component is a state machine implementing a single trait:

```rust
pub trait StateMachine {
    fn receive(&mut self, m: Message) -> Option<Vec<(Message, Destination)>>;
    fn tick(&mut self, curtime: Instant) -> Option<Vec<(Message, Destination)>>;
}
```

Two rules enforce determinism at compile time:
- **No `async` inside state machines** — prevents runaway futures from escaping the scheduler's control
- **No direct system time access** — time is only available through the `curtime` argument passed to `tick()`

A single-threaded message bus is "the director." It controls which state machine runs next, what time each one sees, and whether messages are delivered, dropped, or delivered out of order. All system interactions — network, disk, timers — are modeled as state machines. The bus handles failure injection once, centrally.

This collapses the four ingredients of distributed system testing into one place:

| Ingredient | How it's handled |
|---|---|
| Concurrency | Single-threaded bus; deterministic scheduling |
| Time | Injected through `tick(curtime)`; advance arbitrarily in tests |
| Randomness | Single PRNG seeded at test start; same seed = identical run |
| Fault injection | Message-level, in the bus; applies to everything |

**What this gives you for testing:**

- Reproduce any bug by replaying the same seed
- Fast-forward time: test "what happens after 10 seconds of clock skew" in milliseconds
- Inject crashes at any message boundary without modifying component code
- Run thousands of randomized scenarios per second, all deterministically

Polar Signals found both data loss and data duplication bugs using this approach — the same class of bugs as NodeDB's Bugs 2 and 3. The difference is they found them in test, with a reproducible seed.

**The tradeoff:** cognitive overhead during implementation is high. Developers under pressure let logic leak into the production drivers (the wrappers around state machines), which escapes DST coverage. It also requires discipline to model every external dependency as a state machine — UUID generation, wall clock, filesystem all need explicit handling.

For an existing system that can't be rewritten, Polar Signals recommend third-party toolkits ([madsim](https://github.com/madsim-rs/madsim) for Rust) rather than a full rewrite. DST-first design is only the right call when starting from scratch with determinism as an explicit goal.

---

## The spectrum

| Approach | Effort | What it catches |
|---|---|---|
| `#[cfg(feature = "testing")]` escape hatch | Hours | Bugs reachable via the exposed type |
| Separate `txn` crate with public API | Days | Same, plus forces cleaner boundaries |
| Trait boundary + test doubles | Days | Same + allows time/failure injection |
| State machine + DST (new build) | Weeks–months | Concurrency, timing, crash recovery — all reproducibly |

NodeDB needs the first three. Any new distributed database being designed today should start with the last.
