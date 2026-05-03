---
title: "Deterministic Simulation Testing in Production"
date: 2026-05-03T13:59:01+0800
tags: [testing, distributed-systems, databases, deterministic-simulation, rust]
---

*Part of a series on database correctness. See also: [Verifying a Database Implementation with TLA+](/notes/verifying-db-with-tlaplus/) and [On Writing a Testable Database](/notes/testing-gap-rust-db-internals/).*

---

## What DST is

Deterministic Simulation Testing runs an entire distributed system — multiple nodes, network, disk, time — inside a single controlled process. All sources of nondeterminism are replaced with seeded, injectable versions. Same seed → identical execution → reproducible bugs.

The goal: find the class of bugs that Jepsen, staging environments, and unit tests systematically miss — rare interleavings under fault injection that only appear once every million operations in production.

---

## Three ways to achieve it

**Application-level (highest throughput, highest investment)**

Write all system code against abstractions for I/O, time, and randomness. A single-threaded event loop drives execution; a seeded PRNG controls all scheduling decisions. The simulator and production code share the same business logic — only the I/O layer swaps out.

Runs thousands of simulated hours per wall-clock hour. But requires designing around it from the start — retrofitting is impractical once async I/O and direct system calls are woven through the codebase.

**Runtime swap (Rust async)**

[madsim](https://github.com/madsim-rs/madsim) is a drop-in replacement for Tokio: same API, but single-threaded and seeded. Swap the runtime, keep the application code. [turmoil](https://github.com/tokio-rs/turmoil) takes a narrower approach — simulates just the network layer while letting real code run around it.

Key gotcha (from S2's experience): libc symbol overrides for `clock_gettime`, `getrandom`, and `getentropy` are required for true reproducibility. Without them, failures on Linux don't reproduce on Mac because the standard library pulls entropy from libc directly, bypassing the runtime's control.

**Hypervisor-level (zero code changes)**

[Antithesis](https://antithesis.com) runs unmodified Docker containers inside a modified hypervisor that intercepts all syscalls — network, disk, clock, thread scheduling, RNG. No application changes needed. Coverage-guided fuzzing explores the state space and snapshots interesting states for branch exploration.

Tradeoff: lower simulation throughput (closer to wall-clock), proprietary platform.

---

## Production case studies

**FoundationDB** — the canonical reference. The simulation framework was built *before* the database. All code is written in Flow, a C++ extension with actor-based async that the simulator can schedule deterministically. Apple reports near-zero customer-reported correctness bugs over the product's lifetime. The SIGMOD 2021 paper describes running the equivalent of roughly a trillion CPU-hours of simulation across FDB's history.

**TigerBeetle** — financial transactions database written in Zig. VOPR (their simulator) runs a full cluster of replicas and clients in a single process. Runs a 1,000-core simulation cluster 24×7 — 3.3 seconds of VOPR equals 39 minutes of real time. Found both data loss and data duplication bugs. Built from the start around Zig's single-threaded async model.

**RisingWave** — cloud-native streaming SQL database in Rust. Adopted madsim early and runs end-to-end simulation on every PR. External dependencies (object storage, metadata store) replaced with in-memory emulators behind the simulated network.

**S2** — durable stream storage in Rust. Built [mad-turmoil](https://github.com/s2-streamstore/mad-turmoil), a crate that combines turmoil's network simulation with madsim's libc-level overrides. Runs DST on every PR and in thousands of nightly trials. Found 17 notable bugs spanning concurrency deadlocks, ACID violations, and protocol edge cases. Their [blog post](https://s2.dev/blog/dst) is the most detailed practical guide for Rust async DST.

**CockroachDB** (via Antithesis) — a one-in-a-million race condition first filed in Sentry in 2021. Staging never reproduced it. Antithesis found the precise correlated state transitions causing it.

**etcd** (via Antithesis) — added DST after the v3.5 release had correctness regressions. 830 wall-clock hours of Antithesis simulation found new bugs in the main development branch that years of production load hadn't triggered.

**WarpStream** (via Antithesis) — diskless Kafka-compatible platform. Simulated 280 logical hours in 6 real-world hours. Found a bug that triggered roughly once per wall-clock hour in staging but had zero occurrences in normal operation.

**Aiven Inkless** (via Antithesis) — found KAFKA-19880 in upstream Apache Kafka: under an idempotent producer, the first record batch can be delivered out of order. A real correctness violation in vanilla Kafka, undetected for years.

---

## How S2 implemented DST (deep dive)

**What does "deterministic" actually require?**

Four variables must be fully controlled: execution order (single-threaded), entropy (all RNGs seeded), time (no physical clocks), and I/O (no external dependencies — replaced with in-memory emulators over the simulated network).

**Why turmoil alone wasn't enough**

S2's initial attempt kept producing CI failures that couldn't be reproduced locally (or across Linux vs Mac). The culprits:
- Rust's `HashMap` uses random seeds by default (DOS prevention) — iteration order varies per run
- Timestamps embedded in HTTP headers created non-determinism at the packet level
- Third-party dependencies called `getrandom`, `getentropy`, or `clock_gettime` directly via libc, bypassing the runtime

**The libc override solution**

Rather than patch every dependency, S2 overrides at the symbol level:
- `getrandom` and `getentropy` → route through a statically-initialized seeded RNG via `set_rng()`
- `CCRandomGenerateBytes` on Mac — same treatment
- `clock_gettime` → reads from turmoil's simulated clock, scoped with `SimClocksGuard` to prevent teardown races

This catches entropy leaks from any crate in the dependency tree, without needing to know which ones.

**Test structure**

- Networking services use a compile-time feature flag to swap real `TcpListener`/`TcpStream` for turmoil's simulated versions
- External dependencies (metadata store, object storage) are replaced with in-memory emulators running as separate hosts on the simulated network
- Assertions live in mainline code, not just tests — Rust keeps `assert!` in release builds by default, so invariants are checked in production too

**Verifying reproducibility**

Each test run takes a single seed. CI runs a "meta-test": execute the same seed twice and compare the full `TRACE`-level logs byte-for-byte. Any divergence means an uncontrolled entropy source is still leaking through.

---

## What bugs DST actually finds

The consistent finding across all systems: rare interleavings under fault injection — a scenario that requires a specific sequence of concurrent state transitions, often involving crashes or network partitions, that normal testing never constructs.

- Data loss: a write acknowledged to the client that doesn't survive a crash
- Data duplication: a write applied more than once after recovery
- Ordering violations: reads observing commits in the wrong order under concurrent coordinators
- Invariant violations: internal consistency checks that hold under normal scheduling but fail under adversarial scheduling

These are exactly the classes of bugs in NodeDB's distributed transaction path (Bugs 2 and 3 from the TLA+ analysis).

---

## Applying this to NodeDB

NodeDB is Rust and uses Tokio for async I/O. The practical path:

**Option A: madsim** — swap Tokio for madsim. The entire server, including multi-coordinator scenarios and the WAL, runs deterministically in a single process. Requires abstracting external dependencies (disk, network connections) so madsim can intercept them. Any coordinator crash can be simulated at any message boundary.

**Option B: turmoil + libc overrides (S2's path)** — narrower scope. Simulate just the network between coordinators and shards; let the rest of the code run normally. Add libc overrides for `clock_gettime`, `getrandom`, `getentropy` (and `CCRandomGenerateBytes` on Mac) to lock down time and entropy across the entire dependency tree. Use compile-time feature flags to swap real TCP for turmoil's simulated versions. Replace external dependencies with in-memory emulators running as separate hosts on the simulated network. Less coverage than madsim (disk I/O isn't simulated) but lower integration cost. Add a meta-test that reruns any failing seed and compares TRACE logs byte-for-byte to verify full reproducibility.

Either path would directly target the gap the TLA+ analysis identified: Bug 2 (cross-coordinator ordering) and Bug 3 (coordinator crash recovery) require concurrent multi-node scenarios under fault injection to reproduce — exactly what DST is built for. The TLA+ specs would serve as the property oracle: encode the `CrossCoordOrderHolds` and `NoOrphanedApply` invariants as runtime assertions checked after each simulated step.

---

## The broader pattern

The teams that built DST in from the start (FoundationDB, TigerBeetle, S2) get the highest simulation throughput and the most thorough coverage. But Antithesis has made DST accessible to existing systems without code changes — WarpStream, etcd, and CockroachDB all retrofitted it successfully.

For a new system being designed today: the state machine architecture (all components implement `receive` + `tick`, no async inside, time injected through `tick`) gives DST at the application level for free. The Polar Signals [blog post](https://www.polarsignals.com/blog/posts/2025/07/08/dst-rust) describes this approach in Rust. For existing Rust async code: madsim or turmoil + libc overrides is the path of least resistance.
