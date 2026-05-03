---
title: "On Writing a Testable Database"
date: 2026-05-03T11:22:54+0800
tags: [rust, testing, databases, property-based-testing]
---

*Follows on from [Verifying a Database Implementation with TLA+](/notes/verifying-db-with-tlaplus/). That note found three bugs in [NodeDB](https://github.com/nodeDB-Lab/nodedb) using TLA+ specs. This note is about why writing automated tests for those bugs is harder than it should be.*

---

## The problem

After finding bugs in NodeDB's transaction layer with TLA+, the natural next step is property-based testing — write a fuzzer or stateful test that generates random transaction histories and checks invariants like "no false aborts." Standard practice.

It doesn't work out of the box. NodeDB's public API requires a live TCP server. The lightweight internal types sit behind `pub(crate)`. There's no path to the interesting code without either:

- Spinning up a full server (WAL, dispatcher, security stores, 120+ fields in `SharedState`)
- Writing tests inside the crate itself

This is the testing gap: the bugs live in the middle of the stack, and both available test entry points are at the wrong layer.

---

## NodeDB's API layers

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

`SessionStore` is the right layer to test. It owns conflict detection (Bug 1), session state, read/write set tracking. It has no network dependency — `SessionStore::new()` takes no arguments. The existing internal unit test uses it directly:

```rust
let store = SessionStore::new();
let addr: SocketAddr = "127.0.0.1:5000".parse().unwrap();
store.begin(&addr, Lsn::new(1)).unwrap();
store.commit(&addr).unwrap();
```

But `pub(crate)` means this is only reachable from inside the `nodedb` crate. An external fuzzer or a crate like `hegel-rust` can't touch it.

---

## Why this happens

Rust's module system makes tight encapsulation the default and easy choice. Teams draw the public boundary at the network interface because that's the natural "product API." Internal types stay `pub(crate)` or private — clean, correct, no accidental coupling.

The cost is that the network boundary and the testability boundary become the same boundary. Anything below the public API is only reachable through the full server stack.

This isn't a Rust-specific failure. It's a general pattern in server-side code: the business logic gets buried under transport, auth, and initialization infrastructure, and the test surface shrinks to either unit tests of leaf functions or end-to-end tests against a real server.

---

## Where bugs hide because of this

The three NodeDB bugs from the TLA+ analysis all sit in the gap:

| Bug | Layer | Reachable from public API | Reachable from SessionStore |
|-----|-------|--------------------------|----------------------------|
| False aborts (conflict detection) | SessionStore::commit() | Only through full server | Yes |
| Cross-coordinator ordering | TransactionCoordinator | No | No |
| Crash recovery | TransactionCoordinator | No | No |

Bug 1 would be caught immediately by a property test on `SessionStore`. Bugs 2 and 3 aren't reachable at all without either the full server or significant refactoring.

---

## How to fix it

**1. `#[cfg(any(test, feature = "testing"))] pub`**

The simplest escape hatch. Make `SessionStore` conditionally public under a `testing` feature flag:

```rust
#[cfg(any(test, feature = "testing"))]
pub use crate::control::server::pgwire::session::store::SessionStore;
```

External test crates add `nodedb = { features = ["testing"] }`. No API stability promise needed — document it as test-only. This costs nothing architecturally and unblocks property-based testing immediately.

**2. Extract a `nodedb-txn` crate**

Pull transaction logic into a separate crate with a proper public API. `SessionStore`, conflict detection, and `TransactionCoordinator` become `pub` in `nodedb-txn`. The main `nodedb` crate depends on it. External test crates depend on `nodedb-txn` directly.

This is more work but the right long-term structure. It also forces a cleaner interface: transaction logic has to be expressed in terms of explicit inputs/outputs rather than leaking internal server state.

**3. Define a trait at the transaction boundary**

Instead of testing `SessionStore` directly, define a trait that captures the transaction operations:

```rust
pub trait TransactionEngine {
    fn begin(&self, session: SessionId, snapshot_lsn: Lsn) -> Result<()>;
    fn record_read(&self, session: SessionId, collection: &str, doc_id: &str, lsn: Lsn);
    fn buffer_write(&self, session: SessionId, task: PhysicalTask);
    fn commit(&self, session: SessionId) -> Result<Vec<PhysicalTask>>;
    fn rollback(&self, session: SessionId) -> Result<()>;
}
```

`SessionStore` implements it. Tests use the trait, not the concrete type. This also makes it possible to swap in a test double that records calls for assertion.

**4. Test-only server constructor**

If the full server is needed, provide a constructor that skips network setup:

```rust
#[cfg(any(test, feature = "testing"))]
impl NodeDb {
    pub fn new_in_memory() -> Self { ... }
}
```

Postgres, SQLite, and most other databases have in-memory or embedded modes for testing. NodeDB doesn't. Adding one is high-value.

---

## The general principle

The network boundary is not the right testability boundary. Transport (TCP, protocol encoding, auth) should be a thin layer over business logic that can be tested independently. When they're the same layer, every test of the business logic pays the cost of the transport.

For a database specifically: transaction isolation, conflict detection, and recovery semantics are the core correctness properties. They should have the cheapest possible test path — not require a server.

The pattern to aim for: property-based tests run against the transaction engine directly. Integration tests run against the server. The property-based tests are fast and run on every commit. The integration tests run less often and catch transport/protocol bugs.

Right now NodeDB only has the second path. Adding the first is what makes ongoing correctness verification practical.
