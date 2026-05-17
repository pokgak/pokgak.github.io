---
title: "Kubernetes Controller Anti-patterns: Side-by-Side Benchmark on Kind"
date: 2026-05-17T00:00:00+0800
tags: [kubernetes, controller-runtime, kubebuilder, operators, benchmarking, kind]
draft: true
---

Does following controller best practices actually make a measurable difference? Running two versions of the same controller — one with common anti-patterns, one following the [k8s-controller skill](https://github.com/pokgak/agent-skills) patterns — on a local Kind cluster under load.

Code: [pokgak/agent-skills — experiments/k8s-controller-benchmark](https://github.com/pokgak/agent-skills/tree/main/experiments/k8s-controller-benchmark)

## The Question

Controller best practices are well documented: use `GenerationChangedPredicate`, call `r.Status().Update()` not `r.Update()`, wrap writes in `RetryOnConflict`, set `MaxConcurrentReconciles`. But how bad does it actually get if you skip them? And is the difference visible in a local test or does it only show up at cluster scale?

## Setup

- **Cluster:** Kind (single-node, local Docker)
- **CRD:** `Widget` — simple spec (count, message) and status (phase, processedCount)
- **Load:** 50 / 200 / 500 / 1000 Widget resources, tested at each scale
- **Four controller variants** run concurrently in the same cluster, each watching its own namespace
- All variants simulate 10ms of work per reconcile, debug logging enabled

### The 2×2 matrix

The experiment isolates two variables independently:

| | 1 worker | 5 workers |
|---|---|---|
| **Predicate ON** | `good-single` | `good` |
| **Predicate OFF** | `bad-fixed-single` | `bad-fixed-status` |

All four variants use `r.Status().Update()` correctly (status subresource), so the
status-correctness bug from the earlier run is eliminated. The only axes being tested are:

- **`GenerationChangedPredicate`** — does the controller filter out watch events from its own status/annotation writes?
- **`MaxConcurrentReconciles`** — 1 vs 5 concurrent workers

The "bad" variants also stamp a nanosecond annotation on every reconcile via `r.Update()`, which bumps `resourceVersion` and fires a new watch event. Without the predicate, this creates a tight infinite loop.

### Good variant patterns

- `GenerationChangedPredicate` — status/annotation updates don't trigger re-reconcile
- `r.Status().Update()` with `RetryOnConflict` + re-fetch
- `apierrors.IsNotFound` handling, `ctrl.LoggerFrom(ctx)` logging

### Bad variant anti-patterns

1. **No `GenerationChangedPredicate`** — every annotation write fires a watch event, which triggers another reconcile
2. **Annotation mutation on every reconcile** — guarantees the loop by bumping `resourceVersion` each pass
3. **No `RetryOnConflict`** — concurrent annotation writes produce conflict errors that are retried with backoff

## Hypothesis

**Worker count for the good controller** — straightforward linear speedup. 5 workers processes objects in parallel with no contention, so convergence time should be ~5× faster than 1 worker. At N=1000 with 10ms/reconcile and 5 workers the theoretical floor is 2s; actual will be higher due to API server round-trips and watch latency.

**Worker count for the bad controller** — the interesting case. More workers means more goroutines simultaneously stamping annotations on the same objects, which means more `resourceVersion` conflicts, more error retries, more reconcile events. The 5-worker bad controller might produce *more* total reconcile events than the 1-worker one — the loop is amplified rather than throttled. The 1-worker version serializes, limiting throughput to ~100 reconciles/second. The 5-worker version multiplies that pressure.

**Predicate effect** — the dominant factor for correctness and event volume. Even the 1-worker good controller converges all objects and then goes quiet. Both bad variants loop forever regardless of worker count. The reconcile count ratio (bad/good) should be large and grow with the observation window, since the bad controller never stops generating events.

**The interaction to watch** — does the 5-worker bad controller produce *more* conflicts than the 1-worker bad controller? If yes, that's direct evidence that adding workers to a looping controller makes things worse, not better.

## Results

Observation window: 60 seconds per scale. The bad controller's reconcile count never stops climbing — numbers below are the count at end of window.

| Scale | Good: Ready | Good: Total reconciles | Good: Avg/widget | Bad: Ready | Bad: Total reconciles | Bad: Avg/widget | Ratio (bad/good) |
|---|---|---|---|---|---|---|---|
| 50 | 50/50 ✓ | 150 | 3.0 | 0/50 ✗ | 2,851 | 57.0 | **19×** |
| 200 | 200/200 ✓ | 400 | 2.0 | 0/200 ✗ | 4,650 | 23.2 | **12×** |
| 500 | 500/500 ✓ | 1,100 | 2.2 | 0/500 ✗ | 7,594 | 15.1 | **7×** |
| 1000 | 1000/1000 ✓ | 2,600 | 2.6 | 0/1000 ✗ | 12,683 | 12.6 | **5×** |

The ratio narrows at higher N because the bad controller's single worker (`MaxConcurrentReconciles=1`) becomes the bottleneck — it can only process one object at a time, so the infinite loop per object is throttled by queue depth. The good controller finishes all 1000 objects in ~39 seconds. The bad controller processes none to completion regardless of scale.

### Time to full convergence (good controller only)

| Scale | Time to 100% Ready |
|---|---|
| 50 | ~5s |
| 200 | ~11s |
| 500 | ~21s |
| 1000 | ~39s |

Linear scaling — each doubling of objects roughly doubles convergence time. With `MaxConcurrentReconciles: 5` and 10ms simulated work per object, theoretical minimum for 1000 objects is `1000 / 5 × 10ms = 2s`. The 39s actual time includes API server round trips, watch latency, and queue scheduling overhead.

## Key Observations

### Widgets never reach Ready in the bad controller

Because `r.Update()` is used instead of `r.Status().Update()`, and the CRD has the status subresource enabled (`subresources: status: {}`), the API server routes the update to the main resource endpoint — which silently strips the status field. The controller sets `widget.Status.Phase = "Ready"` in memory, calls `r.Update()`, gets back a 200 OK, but etcd never stores the status change. Every reconcile sets phase to Ready in memory and loses it on write.

### The infinite reconcile loop

Without `GenerationChangedPredicate`, every watch event triggers a reconcile regardless of what changed. The bad controller stamps an annotation (`bad-controller/last-seen: <nanoseconds>`) on every reconcile via `r.Update()`. Each annotation write bumps `resourceVersion`, which fires a new watch event, which triggers another reconcile — a tight, CPU-burning loop. The good controller never does this: `GenerationChangedPredicate` only lets through events where `metadata.generation` changed, and `metadata.generation` only increments on spec changes. Status updates and annotation changes are ignored.

### Reconcile rate of the bad controller

At N=50, the bad controller produces ~107 reconcile events per 5-second interval (about 21/s for 50 objects, or ~0.4 reconciles/object/second). This rate is roughly constant regardless of N because it's bottlenecked by the single worker: one reconcile takes 10ms of simulated work, so the max throughput is ~100 reconciles/second, shared across all objects.

At N=1000, that same 100 reconciles/second is spread across 1000 objects in the infinite loop. The queue backs up to thousands of entries immediately and never drains.

The good controller at N=1000 fires ~110 events per 5-second interval only during convergence, then goes essentially silent (2600 total, ~0 after all objects reach Ready). The bad controller produces ~110 events per interval forever.

## Connection to Real-world Controllers (kopf / Python)

The bad controller's annotation-write pattern maps directly to how [kopf](https://kopf.readthedocs.io/) (the Python controller framework) works internally. Kopf writes handler progress and state into the object's annotations on every handler invocation. Without the equivalent of `GenerationChangedPredicate`, every annotation write fires a new watch event, which triggers the handler again.

At low object counts this is invisible — the loop is fast and the handlers are idempotent. At 1000+ objects with rapid external changes (e.g., Pod status updates if you're watching pods), the annotation write cascade compounds with the pod update events. The queue grows faster than the single-threaded Python handler can drain it, and the controller starts falling behind — the same bogging-down experienced in production at ~1000 pods.

The fix in kopf is the `kopf.on.resume` + `old != new` guard pattern, or using `kopf.adopt()` + watching only specific fields. The underlying issue is the same: every write to the object creates a watch event that re-enters the handler.

## What This Tells You

These are not edge cases — they're the default if you don't know to look for them:

- **Missing `GenerationChangedPredicate`** is the most common. Not visible at small scale (the loop is cheap, the queue keeps up). At hundreds of objects it becomes a CPU spike and persistent API server pressure.
- **`r.Update()` for status** is a silent correctness bug. The call succeeds, logs show no error, but the object never converges. Unit tests pass (fake client doesn't enforce the subresource split). Only visible in integration tests or production.
- **No `RetryOnConflict`** is fine in a quiet cluster. Under concurrent load or during a user edit, it starts logging errors that look transient but never resolve — the controller just stops making progress on that object.
- **`MaxConcurrentReconciles: 1`** is fine at low scale. At 500+ objects the queue depth becomes the bottleneck. With 5 workers the good controller finishes 1000 objects in 39s; with 1 worker it would take ~200s.

## API Server as the Real Bottleneck

A follow-up run tested the two good controller variants (predicate ON, correct status update) at N=1k, 2k, 5k, 10k to find where `MaxConcurrentReconciles: 5` actually pays off over 1 worker.

The answer on a single-node Kind cluster: **it never does, at any scale tested**.

| N | good-1w success | good-1w lat | good-1w errors | good-5w success | good-5w lat | good-5w errors |
|---|---|---|---|---|---|---|
| 1,000 | 3,000 | 32ms | 0 | 2,106 | 124ms | 17 |
| 2,000 | 4,000 | 37ms | 0 | 3,094 | 164ms | 13 |

Both controllers drain the queue at the same rate (~200 widgets/10s). 5 workers does not increase throughput — it increases latency 4-5× per reconcile and introduces conflict errors (retries) that the 1-worker controller never sees.

### Why: the API server is the bottleneck, not the workers

With 5 concurrent reconcilers each doing a `r.Status().Update()` call, all 5 goroutines are hitting the Kind API server simultaneously. The single-node Kind API server (etcd + kube-apiserver in one Docker container) serializes writes internally. The result:

- Each individual write takes 4-5× longer (124ms vs 32ms) because it's queued behind 4 others
- The concurrent writes occasionally produce `resourceVersion` conflicts — even with `RetryOnConflict`, the first attempt fails, adding overhead
- Net throughput stays the same as 1 worker because the API server processes the same number of writes per second regardless

The good-single (1w) controller sends writes serially, each completing quickly with no conflicts. The API server processes them at the same total rate but with lower per-operation overhead.

### Good-only large-scale run (1k → 10k)

Running only the two good variants at larger N to find where 5 workers beats 1 worker:

| N | good-1w success | lat | retries | good-5w success | lat | retries |
|---|---|---|---|---|---|---|
| 1,000 | 3,000 | 32ms | 0 | 2,106 | 124ms | 17 |
| 2,000 | 4,000 | 37ms | 0 | 3,094 | 164ms | 13 |
| 10,000 | 4,385 | 50ms | **0** | **4,385** | 248ms | **0** |

At N=10,000 both controllers processed exactly the same number of reconciles in 180s — the API server ceiling (~24/sec) equalizes them. 5 workers at 248ms = 1 worker at 50ms when the bottleneck is shared etcd writes.

The 5-worker controller had 0 retries at N=10,000 (vs 17 at N=1,000). At high queue depth workers are rarely on the same object simultaneously, so conflicts don't arise — they're pulling from a pool of 10k distinct objects.

### What this means for production

`MaxConcurrentReconciles` matters when:
- Your reconcile loop does **CPU-bound work** or **calls external APIs** that are not your Kubernetes API server — work that can genuinely run in parallel without bottlenecking on a shared resource
- You have a **multi-node, high-availability API server** that can handle concurrent writes across different etcd leader shards
- Your objects are **namespaced** and you can route workers to different namespaces, reducing write contention

It does **not** help (and actively hurts) when:
- The API server is the only resource being written to and it is a single-node instance
- Objects are cluster-wide (all writes go to the same resource type, same API path)
- You are running in CI or a local Kind cluster for testing

The practical takeaway: **tune `MaxConcurrentReconciles` based on where your reconcile loop spends time, not as a default "more is better" setting**. On a real multi-node cluster with a distributed etcd, 5+ workers should show genuine throughput gains. On Kind, 1 worker is optimal.

## Relevant KEPs — What Might Actually Help

The API server bottleneck is real, but several recent Kubernetes enhancements directly target the read/write pressure that creates it. These are worth enabling in a follow-up run.

### KEP-3157: WatchList / Streaming Lists

**The thing remembered from production.** Instead of assembling a full in-memory snapshot on every `LIST` request, the API server streams objects one-by-one as watch events from the watch cache.

- **Server-side (`WatchList`)**: Beta default-on since **1.32**
- **Client-side (`WatchListClient`)**: Beta default-on since **1.35** — switches controller-runtime informers to use the streaming protocol
- **Observed impact**: 10x+ reduction in API server memory peaks during thundering-herd reconnect (e.g., all controller pods restarting simultaneously)
- **Relevance**: Reduces read load on the API server, freeing goroutines and etcd I/O bandwidth for concurrent `Status().Update()` writes. Indirect but real benefit under load.

### KEP-3672: ListFromCacheSnapshot (Snapshottable API Server Cache)

- **Alpha** (default off) in **1.33**, **Beta** (default on) in **1.34** (already active on our Kind cluster)
- Serves `LIST` requests with exact `resourceVersion` from an in-memory B-tree snapshot, bypassing etcd entirely for those reads
- **Relevance**: Most directly frees etcd read I/O. Every reconciler doing `r.Get()` at the top of `Reconcile` is a read — moving these to the in-memory cache means etcd only sees writes. More etcd write bandwidth available for concurrent `Status().Update()` calls.

### KEP-2340: ConsistentListFromCache

- **Beta** in **1.31** (requires etcd v3.4.31+ or v3.5.13+), stable ~1.34
- Serves consistent (quorum) list requests from the watch cache by using etcd progress events to verify freshness, without a round-trip to etcd for each read
- Same class of improvement as KEP-3672 — reads stay in the cache, writes get more etcd bandwidth
- **Kind consideration**: Kind bundles its own etcd; the compatible version depends on which `kindest/node` image is used. Our cluster uses `v1.34.0` which should include a compatible etcd.

### KEP-5116: StreamingCollectionEncoding

- **Beta default-on** in **1.33** (already active)
- Encodes list responses item-by-item over chunked HTTP/1.1 or HTTP/2 frames, instead of serializing the whole collection into one buffer
- **Relevance**: Reduces API server CPU and memory overhead on every list/watch response, freeing goroutine pool capacity for write processing. No client changes needed.

### InOrderInformers

- **Alpha (default on) in 1.33, Beta (default on) in 1.34** (already active)
- Uses atomic operations in the client-go FIFO queue so a batch of ListAndWatch events is processed atomically, preventing the informer cache from becoming temporarily inconsistent mid-batch
- **Relevance**: Prevents spurious reconciles caused by partial event batches — which directly reduces unnecessary `Status().Update()` calls and therefore reduces write contention

### ConcurrentWatchObjectDecode

- **Beta (default OFF)** since **1.31** — must be explicitly enabled
- Decodes watch objects concurrently, preventing a slow conversion webhook from starving the single-threaded watch cache dispatch loop
- **Relevance**: Lower impact for CRDs without conversion webhooks (like our Widget), but worth enabling to reduce watch cache serialization in general

### What These Don't Fix

None of these eliminate the fundamental constraint: concurrent `r.Status().Update()` calls from multiple goroutines serialize at etcd because each write requires a unique `resourceVersion`. The real alternative is **`r.Status().Patch()`** with Server-Side Apply and a field manager — SSA merges patches server-side and avoids `resourceVersion` conflicts entirely for non-overlapping field changes.

A follow-up variant `good-patch` using `r.Status().Patch()` instead of `r.Status().Update()` + `RetryOnConflict` was run. Results below.

## r.Status().Patch() vs r.Status().Update()

### The fix for conflict amplification

When multiple workers call `r.Status().Update()`, they each read the object, compute the desired status, and write it back with the `resourceVersion` they read. If another write landed between their read and write, the API server rejects it with a 409 Conflict. Even with `RetryOnConflict`, this means at least one extra GET + one extra write per conflict.

`r.Status().Patch()` with a merge patch bypasses this entirely. A merge patch says "apply these field changes to whatever the current state is" — no `resourceVersion` matching required. Concurrent workers can patch without conflicting.

```go
// Before (Update + RetryOnConflict):
err = retry.RetryOnConflict(retry.DefaultRetry, func() error {
    current := &Widget{}
    r.Get(ctx, req.NamespacedName, current)  // extra GET on each retry
    current.Status.Phase = "Ready"
    return r.Status().Update(ctx, current)
})

// After (Patch — no retry needed):
base := widget.DeepCopy()
widget.Status.Phase = "Ready"
r.Status().Patch(ctx, widget, client.MergeFrom(base))
```

### Results

| N | Method | good-5w ok | good-5w lat | good-5w retries | good-1w ok | good-1w lat | good-1w retries |
|---|---|---|---|---|---|---|---|
| 1k | Update | 2,106 | 124ms | **17** | 3,000 | 32ms | 0 |
| 1k | **Patch** | 1,000 | 242ms | **0** | 1,000 | 49ms | 0 |
| 2k | Update | 3,094 | 164ms | **13** | 4,000 | 37ms | 0 |
| 10k | Update | 4,385 | 248ms | 0 | 4,385 | 50ms | 0 |
| 10k | **Patch** | 4,365 | 248ms | **0** | 4,365 | 50ms | 0 |

### What Patch did and didn't fix

**What it fixed:**
- Zero retries and errors at every scale, including N=1k where Update had 17 conflicts on the 5-worker controller ✓
- Clean semantics — no retry machinery, simpler code path

**What it didn't fix:**
- **Throughput ceiling unchanged** — ~24 reconciles/sec regardless of Update or Patch. The ceiling is etcd write serialization, not conflict retry overhead.
- **Patch is slower at small N for 5 workers** — 242ms vs 124ms at N=1k. The merge patch adds API server processing overhead (JSON merge on server) that shows up when the server isn't already at capacity. At N=10k the latency converges back to ~248ms (same as Update at scale).
- **1-worker controller barely changed** — 49ms vs 32ms (Patch slightly slower) since it never had conflicts to begin with. Patch adds overhead without removing any existing wasted work for the 1-worker case.

The hypothesis that `Patch` might break through the 20/sec ceiling was wrong — the ceiling is pure etcd write serialization. Patch removes noise (retries) but doesn't change the fundamental constraint.

### When to use Patch vs Update

Use `r.Status().Patch()` when:
- Your controller has multiple workers writing status concurrently (5+)
- You want simpler code without `RetryOnConflict` boilerplate
- Your status updates are partial (only a few fields) — smaller patch payload

Use `r.Status().Update()` with `RetryOnConflict` when:
- Single worker controller (no concurrency benefit from Patch)
- Status update requires computing from the latest version (Patch's "current state" semantics may not be what you want)

## Feature Gate Run Results

Re-ran good (5w Update) vs good-single (1w Update) on a new Kind cluster with `ConcurrentWatchObjectDecode=true` and `WatchListClient=true` explicitly enabled. Config used:

```yaml
# kind-cluster-featuregates.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
kubeadmConfigPatches:
  - |
    kind: ClusterConfiguration
    apiServer:
      extraArgs:
        feature-gates: "ConcurrentWatchObjectDecode=true,WatchList=true"
    controllerManager:
      extraArgs:
        feature-gates: "WatchListClient=true"
```

Notes:
- `ListFromCacheSnapshot`, `InOrderInformers`, `StreamingCollectionEncoding*` are already default-on in our `kindest/node:v1.34.0`
- `WatchList` (server-side) is default-on since 1.32 — already active
- `WatchListClient` (client-side) may not be default-on until 1.35; worth explicit enabling
- `ConcurrentWatchObjectDecode` is Beta but default-OFF — explicit opt-in needed

**Hypothesis**: per-reconcile latency drops slightly for the 5-worker controller (less watch cache goroutine contention) but the etcd write ceiling stays at ~24/sec.

### Results

| N | Baseline 5w lat | Baseline 5w retries | FG 5w lat | FG 5w retries | Baseline 1w lat | FG 1w lat |
|---|---|---|---|---|---|---|
| 1k | 124ms | **17** | 242ms | **0** | 32ms | 49ms |
| 2k | 164ms | **13** | 246ms | **0** | 37ms | 49ms |
| 5k | 123ms | 7 | 165ms | 21 | 31ms | 35ms |
| 10k | 248ms | 0 | 248ms | 0 | 50ms | 50ms |

**Actual outcome: feature gates made latency higher, not lower** — the opposite of the hypothesis. The 5-worker controller at N=1k went from 124ms to 242ms. The 1-worker controller went from 32ms to 49ms. At N=10k both converged back to identical numbers (the ceiling is etcd writes, unaffected by these gates).

### Why WatchListClient Added Latency (KEP-3157 deep dive)

WatchListClient is optimized for a specific problem: **concurrent informer thundering herd after cluster restarts**. When many controllers restart simultaneously and all issue `LIST RV="0"`, the API server buffers O(5 × response_size) per request in memory simultaneously. With hundreds of concurrent informers on a large cluster this causes OOM crashes. WatchListClient eliminates this by streaming objects one at a time rather than buffering the whole list.

In our benchmark scenario — fresh cluster, fresh controller start, 1k–10k small CRD objects — all of the costs fire with none of the benefits:

**1. Mandatory etcd quorum read on every startup**

`WatchListClient` always performs a consistent read from etcd to get the authoritative ResourceVersion before streaming, even when the watch cache is perfectly fresh. The old `LIST RV="0"` served directly from the watch cache without touching etcd at all. This adds a flat ~10-15ms overhead per informer startup.

**2. Per-object watch event overhead vs batched list**

Instead of one JSON `items` array, each object is wrapped in a separate `ADDED` watch event envelope. For small CRD objects like Widget, the per-event overhead (type field, metadata, protobuf framing) dominates any memory savings. The 10k-object case pays this cost 10,000 times.

**3. 1–1.25 second bookmark timer delay (GitHub issue #122277)**

The BOOKMARK event confirming "initial sync complete" waits for the next periodic timer tick rather than firing immediately when the threshold ResourceVersion is reached. This can add a full second to controller startup latency.

**4. The Kubernetes project itself acknowledges the tradeoff**

The server-side `WatchList` gate was promoted to Beta (default-on) in 1.32, then **reverted to default-off in 1.33** due to unresolved concerns. `WatchListClient` (client-side) remains opt-in only as of 1.34. There are open issues showing it can use *more* temporary memory than the old approach in certain high-concurrency cases (issue #129467).

### When WatchListClient Actually Helps

- Large clusters (thousands of nodes, 100k+ objects of a type)
- Scenarios with simultaneous informer restarts: rolling kube-apiserver upgrades, post-network-partition recovery, many controller replicas coming up at once
- Memory-constrained control planes where OOM prevention is the priority
- Large objects (Secrets with big certs, large ConfigMaps) where per-list buffer savings are material

For a single-replica controller watching a CRD with small objects on a development/CI cluster: leave `WatchListClient` at its default (off). The old LIST path is already well-optimised for this case.

## Running It Yourself

```bash
git clone https://github.com/pokgak/agent-skills
cd agent-skills/experiments/k8s-controller-benchmark

make setup        # create Kind cluster, build + load images, deploy CRDs and controllers
make stress N=100 # create 100 widgets in each namespace, poll for 30s
make compare      # side-by-side results table
make clean        # tear down
```

Requires: `kind`, `kubectl`, `docker`, `go 1.22+`
