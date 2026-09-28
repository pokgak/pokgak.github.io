---
title: "Arrays vs hash tables: what a lookup costs, measured"
date: 2026-09-28T12:00:00+0800
tags: [performance, data-structures, databases, cpu-cache, experiments]
---

A post on X claimed: *"In performance optimization, the data structure I least want to use is a hash (only as a last resort), and the one I most want to use is an array. When a database is full of hashes, there's probably a lot of optimization opportunity hiding in there."* This experiment tests that claim. It runs a `GROUP BY key, SUM(amount)` loop over 20 million rows four ways, from a string-keyed `std::unordered_map` down to a plain array indexed by id, and measures time and memory at different group counts. The widgets on this page model what each structure looks like in memory and how its read pattern interacts with a CPU cache, so you can change the configuration and watch the effect. The benchmark sources are linked in [Setup](#setup).

<style>
.avh{--v:#2a78d6;--k:#eb6834;--p:#1baf7a;--m:#eda100;--hit:#008300;--miss:#e34948;--ink:#111827;--ink2:#4b5563;--rule:rgba(17,24,39,.16);--faint:rgba(17,24,39,.06);--other:rgba(17,24,39,.13);--panel:#fafafa;margin:2rem 0;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.45;color:var(--ink)}
.dark .avh{--v:#3987e5;--k:#d95926;--p:#199e70;--m:#c98500;--hit:#2fa84f;--miss:#e66767;--ink:#f3f4f6;--ink2:#a1a1aa;--rule:rgba(243,244,246,.2);--faint:rgba(243,244,246,.07);--other:rgba(243,244,246,.16);--panel:#18181b}
.avh-panel{border:1px solid var(--rule);border-radius:8px;padding:14px;background:var(--panel)}
.avh-controls{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:flex-end;margin-bottom:10px}
.avh-ctl{display:flex;flex-direction:column;gap:4px}
.avh-ctl>span{font-size:12px;color:var(--ink2);font-weight:600}
.avh-seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--rule);border-radius:6px;overflow:hidden}
.avh-seg button{font:inherit;font-size:13px;padding:4px 10px;background:transparent;color:var(--ink);border:0;border-left:1px solid var(--rule);cursor:pointer}
.avh-seg button:first-child{border-left:0}
.avh-seg button[aria-pressed="true"]{background:var(--ink);color:var(--panel)}
.avh-btn{font:inherit;font-size:13px;padding:4px 12px;border:1px solid var(--rule);border-radius:6px;background:transparent;color:var(--ink);cursor:pointer}
.avh-btn:hover,.avh-seg button:hover{background:var(--faint)}
.avh-seg button[aria-pressed="true"]:hover{background:var(--ink)}
.avh input[type=range]{width:170px;accent-color:var(--v)}
.avh-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:12px}
.avh-stat{border:1px solid var(--rule);border-radius:6px;padding:6px 10px}
.avh-stat b{display:block;font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}
.avh-stat small{color:var(--ink2);font-size:12px}
.avh-legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin:4px 0 8px}
.avh-legend i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.avh-note{font-size:13px;color:var(--ink2);margin-top:8px;min-height:2.9em}
.avh-note b{color:var(--ink)}
.avh svg{display:block;width:100%;height:auto;overflow:visible}
.avh svg text{fill:currentColor}
.avh figcaption{font-size:.8rem;opacity:.7;text-align:center;margin-top:.6rem}
.avh .cell{cursor:pointer}
.avh .ring{fill:none;stroke:var(--ink);stroke-width:2}
.avh .badge circle{fill:var(--ink)}
.avh .badge text{fill:var(--panel);font-size:10px;font-weight:700}
.avh .pop{animation:avh-pop .35s ease-out}

.avh .grow{animation:avh-grow .5s ease-out}
@keyframes avh-grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes avh-pop{from{opacity:0;transform:scale(.6)}to{opacity:1;transform:scale(1)}}
.avh .dict-tok{animation:avh-flow 6s linear infinite}
.avh .dict-q{animation:avh-query 3s ease-in-out infinite}
.avh .dict-glow{animation:avh-glow 6s ease-in-out infinite}
@keyframes avh-flow{0%{transform:translateX(0);opacity:0}8%{opacity:1}45%{transform:translateX(250px);opacity:1}50%,100%{transform:translateX(250px);opacity:0}}
@keyframes avh-query{0%{transform:translateX(0);opacity:0}15%{opacity:1}70%{transform:translateX(120px);opacity:1}85%,100%{transform:translateX(120px);opacity:0}}
@keyframes avh-glow{0%,15%{fill-opacity:.05}30%,40%{fill-opacity:.25}55%,100%{fill-opacity:.05}}
@media (prefers-reduced-motion: reduce){.avh .dict-tok,.avh .dict-q,.avh .dict-glow,.avh .pop,.avh .grow{animation:none}}
</style>

## The Question

How much slower is a hash table than an array for the same job, and why? When does the difference show up, and when is a hash table the right choice?

## Setup

- **Hardware:** Apple M4 Max. Each performance core has a 128 KB L1 data cache, and each cluster of performance cores shares a 16 MB L2 cache.
- **Compiler:** Apple clang with `-O2 -std=c++20 -mcpu=native`. Single-threaded.
- **Workload:** 20M rows of `(id, amount)` with ids drawn uniformly from `[0, G)`. `G` (the number of distinct groups) is set to 100, 10K, 1M, or 10M.
- **Runs:** each configuration ran twice. The runs agreed within 10%. The tables show the first run.
- **Sources:** [`groupby.cpp`](/embeds/arrays-vs-hashes/groupby.cpp), [`order.cpp`](/embeds/arrays-vs-hashes/order.cpp), [`smalln.cpp`](/embeds/arrays-vs-hashes/smalln.cpp), [`mem.cpp`](/embeds/arrays-vs-hashes/mem.cpp).

The four structures compared:

| Name (short) | What it is |
|---|---|
| `unordered_map<string>` (string map) | `std::unordered_map<std::string, int64_t>`. Keys look like `user_1000000123`. This is what you get when ids come out of JSON or a row store as text. |
| `unordered_map<u32>` (u32 map) | The same node-based table with integer keys. |
| flat open-addressing (flat hash) | A hash table stored in flat arrays: linear probing and a power-of-two capacity, sized to twice the number of groups. This is the design behind SwissTable and Go 1.24 maps, simplified. |
| `array[id]` (array) | `std::vector<int64_t> sums(G); sums[id] += amount;`. It works only because the ids are dense, `0..G-1`. |

---

## Background: what one lookup touches

A CPU does not read single bytes from memory. It reads a whole **cache line**, which is 64 bytes on x86 and most ARM cores. Apple Silicon reports 128-byte lines, but the ratios below stay the same. A read that finds its line in L1 costs about a nanosecond. A read that goes to DRAM costs about 100 ns. So the useful cost measure for a data structure is **how many distinct cache lines one lookup touches, and whether those lines are likely to be in cache already.**

The widget below lays out each structure byte by byte in 64-byte lines. It uses libc++'s real node sizes (32 B nodes for `u32` keys and 48 B for string keys, both confirmed with `mem.cpp`). Click any colored cell, or press play, to watch a lookup step through memory.

<figure class="avh not-prose" id="avh-layout">
<div class="avh-panel">
  <div class="avh-controls">
    <div class="avh-ctl"><span>Structure</span><div class="avh-seg" data-k="struct"><button data-v="array" aria-pressed="true">array[id]</button><button data-v="flat" aria-pressed="false">flat hash</button><button data-v="chain" aria-pressed="false">chained hash</button></div></div>
    <div class="avh-ctl"><span>Key type</span><div class="avh-seg" data-k="key"><button data-v="u32" aria-pressed="true">u32</button><button data-v="str" aria-pressed="false">string</button></div></div>
    <div class="avh-ctl"><span>Entries: <output>16</output></span><input type="range" min="4" max="64" step="4" value="16" data-k="n" aria-label="Number of entries"></div>
    <div class="avh-ctl"><button class="avh-btn" data-act="play">▶ Play lookups</button></div>
  </div>
  <div class="avh-legend"><span><i style="background:var(--v)"></i>value</span><span><i style="background:var(--k)"></i>key</span><span><i style="background:var(--p)"></i>pointer</span><span><i style="background:var(--m)"></i>hash / control byte</span><span><i style="background:transparent;border:1px solid var(--rule)"></i>empty slot / padding</span><span><i style="background:var(--other)"></i>other program data</span></div>
  <svg role="img" aria-label="Memory layout of the selected data structure, drawn as 64-byte cache lines"></svg>
  <div class="avh-note" aria-live="polite"></div>
  <div class="avh-stats"></div>
</div>
<figcaption>Each strip is one 64-byte cache line, split into sixteen 4-byte cells. Numbered rings show which lines a lookup reads, in order.</figcaption>
</figure>

Things to try:

- **Array with 16 entries:** 128 bytes, two lines, and every byte is a value. A lookup is `base + id × 8`: one line, with no hashing and no key comparison.
- **Flat hash, same 16 entries:** a lookup reads a control byte, then the slot. That is two lines instead of one. Half the slots are empty by design, because a 50% load factor keeps probe sequences short.
- **Chained hash:** a lookup reads the bucket array, then follows a pointer to a node allocated somewhere on the heap. The nodes sit wherever `malloc` put them, mixed in with other allocations. Each node also carries a `next` pointer and a cached hash.
- **Switch the key type to string** and watch the node grow to 48 bytes, most of it key. The strings here are 15 characters, so they fit inside libc++'s 24-byte small-string buffer. A key longer than 22 characters adds one more pointer hop to a separate heap buffer.

---

## Experiment 1: GROUP BY with four structures

### **Why this matters**

Grouped aggregation is the inner loop of most analytic queries, and it is where a database most often reaches for a hash table. If arrays win anywhere, they win here.

### **Hypothesis**

With a small number of groups everything fits in cache, so the structures differ only by instruction count: hashing and key comparison versus address arithmetic. Expect a 5–10× gap. Once the table outgrows cache, the gap should widen, because hashing scatters accesses and the node-based table adds a pointer hop to every lookup.

### **Method**

`groupby.cpp` runs each structure over the same 20M-row input for each `G`. The string keys are built before timing starts, so the timed loop measures only hashing and lookup. A checksum over the finished table confirms that every method produced the same total. Memory was measured separately in `mem.cpp` with `malloc_zone_statistics`, one structure at a time. The first attempt measured memory inside the timed benchmark and picked up leftovers from the previous structure, which added about 25 MB to the array at 10M groups.

### **Results**

<figure class="avh not-prose" id="avh-results">
<div class="avh-panel">
  <div class="avh-controls">
    <div class="avh-ctl"><span>Distinct groups (G)</span><div class="avh-seg" data-k="g"><button data-v="0" aria-pressed="false">100</button><button data-v="1" aria-pressed="false">10K</button><button data-v="2" aria-pressed="false">1M</button><button data-v="3" aria-pressed="true">10M</button></div></div>
  </div>
  <svg role="img" aria-label="Bar charts of time per row and memory for each structure"></svg>
</div>
<figcaption>Measured on an M4 Max, 20M rows. Both axes are log scale. The dashed lines on the memory chart mark the L1 (128 KB) and L2 (16 MB) cache sizes.</figcaption>
</figure>

Time per row, in ns:

| Groups | string map | u32 map | flat hash | array |
|---|---|---|---|---|
| 100 | 12.80 | 2.29 | 2.69 | **0.35** |
| 10K | 19.32 | 2.80 | 3.03 | **0.34** |
| 1M | 83.57 | 20.84 | 6.44 | **0.90** |
| 10M | 165.28 | 80.39 | 13.91 | **2.59** |

Memory for the finished table, in MB:

| Groups | string map | u32 map | flat hash | array |
|---|---|---|---|---|
| 1M | 61.2 | 45.2 | 27.3 | **8.0** |
| 10M | 585.4 | 425.4 | 436.2 | **80.0** |

### **What this tells us**

- **The hypothesis was too low when everything fits in cache.** At 100 groups the array is 6.5× faster than the best hash table, and 36× faster than string keys. The array loop costs about 1.5 cycles per row. The string version spends its time hashing 15 bytes and comparing them again on every row.
- **The node-based table falls behind as soon as it leaves cache.** From 10K to 1M groups, `unordered_map<u32>` slows down 7.4× while the flat table slows down only 2.1×. The extra pointer hop per lookup is a second likely cache miss.
- **A good hash table narrows the gap but does not close it.** At 10M groups the flat table is 5.8× faster than `unordered_map<u32>`, and still 5.4× slower than the array.
- **Density decides what fits in cache.** At 1M groups the array is 8 MB and fits in L2. Every hash table is 27–61 MB and does not. The array uses 8 bytes per group. The flat table uses 27 bytes per group at the same count, because it stores keys, keeps half its slots empty, and needs control bytes. The node-based tables use 45–61 bytes per group.
- **The flat table's advantage is smallest when everything fits in cache.** At 100 groups it is slightly slower than `unordered_map<u32>`, because its hash function costs more than libc++'s identity hash for integers. Layout only starts to matter once memory is the bottleneck.

---

## Experiment 2: Read patterns and the cache

### **Why this matters**

Experiment 1 shows that cost jumps once the table outgrows cache. This experiment isolates why: it is the access pattern, not just the size. A hash function is designed to scatter keys, and scattered keys make scattered reads.

### **Hypothesis**

For the same array at 10M groups, processing rows in id order should be several times faster than processing them in random order. In id order, consecutive rows hit the same or neighbouring cache lines, and the hardware prefetcher can see the pattern.

### **Method**

The toy simulator below runs the `GROUP BY` loop against a small, fully associative LRU cache. Each square is one 64-byte line of the table. Blue squares are in cache. Green flashes are hits and red flashes are misses. Its timing is a model: 1 ns per hit and 80 ns per miss, with no prefetcher, so it shows *why* the pattern matters rather than predicting real numbers. The real measurement comes from `order.cpp`: the same `sums[id] += amount` loop over 20M rows and 10M groups, run once with random ids and once with the ids sorted.

<figure class="avh not-prose" id="avh-cache">
<div class="avh-panel">
  <div class="avh-controls">
    <div class="avh-ctl"><span>Structure</span><div class="avh-seg" data-k="struct"><button data-v="array" aria-pressed="true">array[id]</button><button data-v="flat" aria-pressed="false">flat hash</button><button data-v="chain" aria-pressed="false">chained hash</button></div></div>
    <div class="avh-ctl"><span>Groups</span><div class="avh-seg" data-k="g"><button data-v="16" aria-pressed="false">16</button><button data-v="128" aria-pressed="false">128</button><button data-v="512" aria-pressed="true">512</button><button data-v="2048" aria-pressed="false">2048</button></div></div>
    <div class="avh-ctl"><span>Row order</span><div class="avh-seg" data-k="order"><button data-v="random" aria-pressed="true">random</button><button data-v="sorted" aria-pressed="false">sorted by id</button></div></div>
    <div class="avh-ctl"><span>Cache</span><div class="avh-seg" data-k="cache"><button data-v="32" aria-pressed="false">2 KB</button><button data-v="128" aria-pressed="true">8 KB</button><button data-v="512" aria-pressed="false">32 KB</button></div></div>
    <div class="avh-ctl"><span>Speed</span><div class="avh-seg" data-k="speed"><button data-v="slow" aria-pressed="false">step</button><button data-v="fast" aria-pressed="true">fast</button><button data-v="max" aria-pressed="false">instant</button></div></div>
    <div class="avh-ctl"><button class="avh-btn" data-act="run">▶ Run</button></div>
  </div>
  <div class="avh-legend"><span><i style="background:var(--faint);border:1px solid var(--rule)"></i>line not in cache</span><span><i style="background:var(--v);opacity:.6"></i>line in cache</span><span><i style="background:var(--hit)"></i>hit</span><span><i style="background:var(--miss)"></i>miss</span></div>
  <svg role="img" aria-label="Grid of cache lines showing hits and misses as rows are aggregated"></svg>
  <div class="avh-note" aria-live="polite"></div>
  <div class="avh-stats"></div>
</div>
<figcaption>A toy model with a fully associative LRU cache and no prefetcher. It runs 4,000 rows. Modeled time assumes 1 ns per hit and 80 ns per miss.</figcaption>
</figure>

Things to try:

- **512 groups with an 8 KB cache.** The array is 4 KB and fits, so after the first pass nearly every access hits. The flat hash table for the same 512 groups needs 16 KB of slots plus control bytes, so it thrashes. The chained table does worse.
- **2048 groups, random order.** Now nothing fits. Switch the order to **sorted by id** and the array's misses drop to about one per line, because eight consecutive ids share a line. The hash tables gain much less from sorting, because sorting by id does not sort by hash.
- **The 2 KB cache** shows the same effect at smaller sizes.

### **Results**

Measured (`order.cpp`, `array[id]`, 20M rows, 10M groups):

| Row order | ms | ns/row |
|---|---|---|
| random | 51.0 | 2.55 |
| sorted by id | 14.4 | 0.72 |

### **What this tells us**

- **Confirmed: the same array is 3.5× faster when reads follow memory order.** The data structure is identical. Only the read pattern changed.
- **A hash table cannot use this trick directly.** Its slot order is the hash order, and the hash is designed to have no relation to key order. That is why databases partition data before hashing it. A radix-partitioned hash join first splits both inputs into chunks whose hash tables fit in cache, then joins chunk by chunk ([Balkesen et al. 2013](https://doi.org/10.1109/ICDE.2013.6544839)).
- **An array wins twice over.** Its small footprint means more of it stays in cache, and its layout follows key order, so ordered input becomes sequential reads.

---

## Experiment 3: The cost of getting dense ids

### **Why this matters**

`array[id]` only works when the keys are dense integers. Real keys are strings, UUIDs, or sparse 64-bit ids. Turning them into `0..G-1` needs a dictionary, and a dictionary is a hash table. Does that hash table cancel the benefit?

### **Hypothesis**

Building the dictionary costs about as much as one hash-table aggregation, because it is the same work: hash each key, probe, compare. It pays off only when the encoded column is read more than once.

### **Method**

`groupby.cpp` also times building a dictionary (`unordered_map<string, u32>`) and encoding all 20M rows into a `u32` column.

<figure class="avh not-prose">
<div class="avh-panel">
<svg viewBox="0 0 680 250" role="img" aria-labelledby="avh-dict-t avh-dict-d">
  <title id="avh-dict-t">Dictionary encoding: hash once at ingest, index arrays on every query</title>
  <desc id="avh-dict-d">String keys flow through a dictionary once and become dense integer ids. Later queries use the ids as array indexes and never hash again.</desc>
  <g font-family="ui-sans-serif, system-ui, sans-serif" font-size="12">
    <text x="20" y="22" font-weight="650">ingest (once)</text>
    <text x="470" y="22" font-weight="650">every query</text>
    <line x1="455" y1="10" x2="455" y2="240" stroke="currentColor" stroke-opacity=".2" stroke-dasharray="4 4"/>
    <g font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="11">
      <rect x="20" y="40" width="120" height="180" rx="6" fill="currentColor" fill-opacity=".04" stroke="currentColor" stroke-opacity=".25"/>
      <text x="80" y="58" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" opacity=".7">raw rows</text>
      <text x="30" y="82">user_…0042</text><text x="30" y="104">user_…0917</text><text x="30" y="126">user_…0042</text><text x="30" y="148">user_…0003</text><text x="30" y="170">user_…0917</text><text x="30" y="192">user_…0042</text>
      <rect class="dict-glow" x="175" y="70" width="130" height="110" rx="8" fill="var(--k)" fill-opacity=".05" stroke="var(--k)" stroke-width="1.5"/>
      <text x="240" y="98" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" font-weight="650">dictionary</text>
      <text x="240" y="116" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" opacity=".75">hash each key once</text>
      <text x="240" y="140" text-anchor="middle">…0042 → 0</text><text x="240" y="156" text-anchor="middle">…0917 → 1</text><text x="240" y="172" text-anchor="middle">…0003 → 2</text>
      <rect x="340" y="40" width="80" height="180" rx="6" fill="currentColor" fill-opacity=".04" stroke="currentColor" stroke-opacity=".25"/>
      <text x="380" y="58" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" opacity=".7">ids (u32)</text>
      <text x="380" y="82" text-anchor="middle">0</text><text x="380" y="104" text-anchor="middle">1</text><text x="380" y="126" text-anchor="middle">0</text><text x="380" y="148" text-anchor="middle">2</text><text x="380" y="170" text-anchor="middle">1</text><text x="380" y="192" text-anchor="middle">0</text>
      <g class="dict-tok"><rect x="32" y="200" width="90" height="16" rx="4" fill="var(--k)" fill-opacity=".85"/><text x="77" y="212" text-anchor="middle" fill="#fff" style="fill:#fff">"user_…"</text></g>
      <rect x="560" y="60" width="100" height="120" rx="6" fill="currentColor" fill-opacity=".04" stroke="currentColor" stroke-opacity=".25"/>
      <text x="610" y="78" text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif" opacity=".7">sums[]</text>
      <rect x="575" y="88" width="70" height="22" rx="3" fill="var(--v)" fill-opacity=".8"/><text x="610" y="103" text-anchor="middle" style="fill:#fff">[0]</text>
      <rect x="575" y="114" width="70" height="22" rx="3" fill="var(--v)" fill-opacity=".8"/><text x="610" y="129" text-anchor="middle" style="fill:#fff">[1]</text>
      <rect x="575" y="140" width="70" height="22" rx="3" fill="var(--v)" fill-opacity=".8"/><text x="610" y="155" text-anchor="middle" style="fill:#fff">[2]</text>
      <g class="dict-q"><rect x="440" y="92" width="40" height="16" rx="4" fill="var(--v)"/><text x="460" y="104" text-anchor="middle" style="fill:#fff">q1</text></g>
      <g class="dict-q" style="animation-delay:1s"><rect x="440" y="118" width="40" height="16" rx="4" fill="var(--v)"/><text x="460" y="130" text-anchor="middle" style="fill:#fff">q2</text></g>
      <g class="dict-q" style="animation-delay:2s"><rect x="440" y="144" width="40" height="16" rx="4" fill="var(--v)"/><text x="460" y="156" text-anchor="middle" style="fill:#fff">q3</text></g>
    </g>
    <text x="470" y="215" opacity=".75">sums[id] += amount</text>
    <text x="470" y="232" opacity=".75">no hash, no key compare</text>
  </g>
</svg>
</div>
<figcaption>Hash at the boundary, index everywhere after it. Columnar databases do this with dictionary-encoded columns.</figcaption>
</figure>

### **Results**

| Groups | encode | string map | array | break-even |
|---|---|---|---|---|
| 100 | 11.03 | 12.80 | 0.35 | 0.89 |
| 10K | 17.34 | 19.32 | 0.34 | 0.91 |
| 1M | 80.55 | 83.57 | 0.90 | 0.97 |
| 10M | 161.12 | 165.28 | 2.59 | 0.99 |

All times are ns/row. Break-even is the number of queries after which encoding has paid for itself: `encode / (string map − array)`.

### **What this tells us**

- **Confirmed: encoding costs almost exactly one string-hash aggregation.** It is the same loop, storing an id instead of adding to a sum.
- **It pays off from the second read of the column onward.** Every later query, filter, join, or sort on the encoded column runs at array speed. The 4-byte ids are also 4× smaller than the 15-byte strings they replace.
- **This is the bet a columnar database makes: write once, read many times.** Dictionary encoding ([Abadi et al. 2006](http://www.cs.umd.edu/~abadi/papers/abadisigmod06.pdf)) and ClickHouse's [`LowCardinality`](https://clickhouse.com/docs/reference/data-types/lowcardinality) type pay the hashing cost at insert time so that queries never pay it. For a one-off pass over data you will never read again, just hash it.

---

## Experiment 4: Small maps and linear scans

### **Why this matters**

Redis stores small hashes as a flat `listpack` and scans it linearly, switching to a real hash table only past `hash-max-listpack-entries` ([Redis docs](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/)). A common claim is that a linear scan of a small array beats a hash lookup. If that holds, "prefer arrays" would extend to searching arrays too.

### **Hypothesis**

A linear scan beats `unordered_map` up to roughly 32–64 entries, where the scan's cost overtakes the hash's fixed overhead.

### **Method**

`smalln.cpp` does 20M random point lookups for n = 4 to 1024. It compares scanning a `vector<pair<key, value>>` with `unordered_map::find`, for both `u32` and string keys.

<figure class="avh not-prose" id="avh-smalln">
<div class="avh-panel">
  <div class="avh-controls">
    <div class="avh-ctl"><span>Key type</span><div class="avh-seg" data-k="key"><button data-v="u32" aria-pressed="true">u32</button><button data-v="str" aria-pressed="false">string</button></div></div>
  </div>
  <svg role="img" aria-label="Line chart of lookup time versus map size for linear scan and hash lookup"></svg>
</div>
<figcaption>Measured, ns per lookup. Both axes are log scale. Hover over the markers for exact values.</figcaption>
</figure>

### **Results**

| n | u32 scan | u32 hash | string scan | string hash |
|---|---|---|---|---|
| 4 | 5.42 | 5.08 | 9.88 | 9.90 |
| 8 | 6.54 | 7.49 | 13.74 | 15.15 |
| 16 | 7.88 | 1.89 | 19.22 | 11.56 |
| 64 | 14.42 | 2.83 | 57.85 | 13.20 |
| 256 | 40.76 | 0.91 | 156.18 | 13.92 |
| 1024 | 137.50 | 0.90 | 857.41 | 11.24 |

### **What this tells us**

- **Refuted.** The scan only ties or narrowly wins up to 8 entries. By 64 entries it is 5× slower for `u32` keys and 4× slower for strings. With random queries the loop's exit branch is unpredictable, and a scan does n/2 comparisons on average.
- **Redis uses listpacks to save memory, not to make lookups faster.** A 20-field hash as a listpack is one small allocation. As a hash table it is a table plus 20 nodes, each with pointers.
- **The "array" in the original claim means direct indexing, not searching.** `array[id]` is fast because the key *is* the address. An array you have to search is a different data structure, and it loses to a hash table once n is more than a handful.

---

## Where real systems already replace hashes with arrays

- **DuckDB** uses a *perfect hash aggregate* when column statistics show a small integer range. It allocates `2^bits` slots and indexes each group by `value − min`, with no hash function ([aggregation blog](https://duckdb.org/2022/03/07/aggregate-hashtable), [operator source](https://github.com/duckdb/duckdb/blob/main/src/execution/perfect_aggregate_hashtable.cpp)). Since late 2024 it makes the same switch for joins, using the min/max it computes while building the join table ([PR #14971](https://github.com/duckdb/duckdb/pull/14971)).
- **ClickHouse** aggregates `UInt8`/`UInt16` keys with `FixedHashMap`, which is a lookup array with "no conflict chain … no key comparison" ([source](https://github.com/ClickHouse/ClickHouse/blob/master/src/Common/HashTable/FixedHashTable.h), [hash tables in ClickHouse](https://clickhouse.com/blog/hash-tables-in-clickhouse-and-zero-cost-abstractions)).
- **V8** stores JavaScript object properties in slot arrays described by hidden classes, and falls back to hash-based "dictionary mode" only when an object's shape keeps changing ([Fast properties in V8](https://v8.dev/blog/fast-properties)).
- **CPython 3.6+** stores dict entries in a dense array with a small sparse index on top ([Hettinger's 2012 proposal](https://mail.python.org/pipermail/python-dev/2012-December/123028.html)). The hash part is only a way to find a position in the array.
- **Game engines and compilers** replace pointers and hash-map lookups with indices into arrays: generational handles ([floooh](https://floooh.github.io/2018/06/17/handles-vs-pointers.html)), ECS component storage ([Catherine West, RustConf 2018](https://kyren.github.io/2018/09/14/rustconf-talk.html)), and the Zig compiler's data-oriented rewrite ([Andrew Kelley](https://www.youtube.com/watch?v=IroPQ150F6c)).

## When to use which

**Use an array** when the keys are dense integers, or can be made dense:

- Dictionary-encode strings at ingest, then use the integer ids everywhere after that.
- Hand out handles or indices instead of pointers or string ids.
- For a small or known key range, index by `value − min`.
- For sets of integers, use a bitset, or a Roaring bitmap when the set is sparse.
- For read-mostly lookups, sort once and binary-search. A sorted array, in Eytzinger layout if lookups dominate, beats `std::set`.
- Sort or partition the input by key before the hot loop, so the reads become sequential.

**Use a hash table** when the keys are sparse or unbounded and you will read the data only once, or when inserts and lookups are interleaved with no point where you could encode. When you need one, choose a flat open-addressing table such as `absl::flat_hash_map`, Rust's `HashMap`, or Go 1.24+ maps. At 10M groups the flat table was 5.8× faster than the node-based `std::unordered_map`.

**How to find opportunities:** look for string- or UUID-keyed maps inside hot loops, maps whose keys are already sequential ids, and maps with fewer than about 64K distinct keys, since those keys fit in a `u16` index.

## Final Summary

| Factor | Finding |
|---|---|
| Instruction cost, when everything fits in cache | Array is 6.5× faster than the best hash table, and 36× faster than string keys |
| Cache footprint | 8 B per group for the array vs 27–61 B for hash tables. At 1M groups only the array fits in L2 |
| Pointer chasing | Node-based `unordered_map` is 5.8× slower than a flat hash table at 10M groups |
| Read order | The same array is 3.5× faster with rows sorted by id |
| Cost of dense ids | Encoding costs about one hash aggregation. It pays off from the second query |
| Linear scan on small n | Wins only up to about 8 entries, then loses badly. "Array" means indexing, not searching |

The claim holds, with one condition. A hash table converts a key into a location, and that conversion costs instructions, memory, and locality. Where the key can already be the location, as with dense ids, handles, or dictionary codes, that cost disappears. Where it cannot, a flat hash table is the best option, and the node-based `std::unordered_map` is the most expensive one tested here.

## Further reading

**Hardware**
- Ulrich Drepper, [*What Every Programmer Should Know About Memory*](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) (2007)
- Chandler Carruth, [*Efficiency with Algorithms, Performance with Data Structures*](https://www.youtube.com/watch?v=fHNmRkzxHWs), CppCon 2014
- Bjarne Stroustrup, [GoingNative 2012 keynote](https://www.youtube.com/watch?v=SfkMiGFVhZo) (vector vs list) and the follow-up [*Are lists evil?*](https://isocpp.org/blog/2014/06/stroustrup-lists)
- Matt Austern, [*Why you shouldn't use set (and what you should use instead)*](https://lafstern.org/matt/col1.pdf) (2000)

**Data-oriented design**
- Mike Acton, [*Data-Oriented Design and C++*](https://www.youtube.com/watch?v=rX0ItVEVjHc), CppCon 2014
- Andrew Kelley, [*Practical Data Oriented Design*](https://www.youtube.com/watch?v=IroPQ150F6c), Handmade Seattle 2021
- Andre Weissflog, [*Handles are the better pointers*](https://floooh.github.io/2018/06/17/handles-vs-pointers.html) (2018)
- Richard Fabian, [*Data-Oriented Design*](https://www.dataorienteddesign.com/dodbook/) (book)

**Databases**
- Boncz, Zukowski, Nes, [*MonetDB/X100: Hyper-Pipelining Query Execution*](https://cidrdb.org/cidr2005/papers/P19.pdf), CIDR 2005
- Abadi, Madden, Ferreira, [*Integrating Compression and Execution in Column-Oriented Database Systems*](http://www.cs.umd.edu/~abadi/papers/abadisigmod06.pdf), SIGMOD 2006
- Richter, Alvarez, Dittrich, [*A Seven-Dimensional Analysis of Hashing Methods*](https://www.vldb.org/pvldb/vol9/p96-richter.pdf), VLDB 2015
- Balkesen et al., [*Main-Memory Hash Joins on Multi-Core CPUs*](https://doi.org/10.1109/ICDE.2013.6544839), ICDE 2013
- Kersten et al., [*Everything You Always Wanted to Know About Compiled and Vectorized Queries*](https://www.vldb.org/pvldb/vol11/p2209-kersten.pdf), VLDB 2018
- Kraska et al., [*The Case for Learned Index Structures*](https://doi.org/10.1145/3183713.3196909), SIGMOD 2018
- ClickHouse, [*Parallelizing aggregation merge for fixed hash map*](https://clickhouse.com/blog/parallelizing-fixed-hashmap-aggregation-merge-in-clickhouse) (2025)

**When you must hash, keep it flat**
- Matt Kulukundis, [*Designing a Fast, Efficient, Cache-friendly Hash Table*](https://www.youtube.com/watch?v=ncHmEUmJZf4), CppCon 2017
- Malte Skarupke, [*I Wrote The Fastest Hashtable*](https://probablydance.com/2017/02/26/i-wrote-the-fastest-hashtable/) (2017)
- Michael Pratt, [*Faster Go maps with Swiss Tables*](https://go.dev/blog/swisstable) (2025)

**Sets and search**
- Chambi, Lemire, Kaser, Godin, [*Better bitmap performance with Roaring bitmaps*](https://arxiv.org/abs/1402.6407) (2016)
- Daniel Lemire, [*Fast sets of integers*](https://lemire.me/blog/2012/11/13/fast-sets-of-integers/) and [*sorted arrays vs. hash sets*](https://lemire.me/blog/2017/05/23/counting-exactly-the-number-of-distinct-elements-sorted-arrays-vs-hash-sets/)
- Khuong and Morin, [*Array Layouts for Comparison-Based Searching*](https://arxiv.org/abs/1509.05053) (2017), and Sergey Slotin's [Eytzinger binary search](https://en.algorithmica.org/hpc/data-structures/binary-search/)

<script>
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  function S(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function T(parent, x, y, str, attrs) {
    const t = S('text', Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }
  function mix32(x) {
    x = Math.imul(x ^ (x >>> 16), 0x7feb352d);
    x = Math.imul(x ^ (x >>> 15), 0x846ca68b);
    return (x ^ (x >>> 16)) >>> 0;
  }
  function rng(seed) {
    return function () {
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function pow2(n) { let c = 1; while (c < n) c <<= 1; return c; }
  function nextPrime(n) {
    for (let p = Math.max(2, n); ; p++) {
      let ok = true;
      for (let d = 2; d * d <= p; d++) if (p % d === 0) { ok = false; break; }
      if (ok) return p;
    }
  }
  function segState(root) {
    const st = {};
    root.querySelectorAll('.avh-seg').forEach(seg => {
      const on = seg.querySelector('[aria-pressed="true"]');
      st[seg.dataset.k] = on ? on.dataset.v : null;
    });
    root.querySelectorAll('input[type=range]').forEach(r => { st[r.dataset.k] = +r.value; });
    return st;
  }
  function wireSegs(root, onChange) {
    root.querySelectorAll('.avh-seg').forEach(seg => {
      seg.addEventListener('click', ev => {
        const b = ev.target.closest('button');
        if (!b) return;
        seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
        onChange();
      });
    });
    root.querySelectorAll('input[type=range]').forEach(r => {
      r.addEventListener('input', () => {
        const o = r.parentElement.querySelector('output');
        if (o) o.textContent = r.value;
        onChange();
      });
    });
  }
  function stats(el, items) {
    el.innerHTML = items.map(([v, l]) => `<div class="avh-stat"><b>${v}</b><small>${l}</small></div>`).join('');
  }
  const KIND_FILL = { val: 'var(--v)', key: 'var(--k)', ptr: 'var(--p)', meta: 'var(--m)', other: 'var(--other)' };
  const KIND_NAME = { val: 'value', key: 'key', ptr: 'pointer', meta: 'hash / control byte', empty: 'empty', pad: 'padding', other: 'other program data' };

  // ---------- Widget A: memory layout ----------
  function buildLayout(struct, key, n) {
    const lines = [], regions = [];
    function region(name, bytes) {
      const start = lines.length, L = Math.max(1, Math.ceil(bytes / 64));
      for (let i = 0; i < L; i++) lines.push(Array.from({ length: 16 }, () => ({ kind: 'empty', e: -1 })));
      regions.push({ name, start, count: L });
      return start * 16;
    }
    function put(cell, count, kind, e) {
      for (let i = 0; i < count; i++) { const c = cell + i; lines[c >> 4][c & 15] = { kind, e }; }
    }
    const hashOf = e => mix32((e + 1) * 2654435761 + (key === 'str' ? 0x9e37 : 0));
    const look = [];
    let allocBytes = 0;
    if (struct === 'array') {
      const base = region(`values[] · ${n} × 8 B`, n * 8);
      allocBytes = n * 8;
      for (let e = 0; e < n; e++) {
        put(base + e * 2, 2, 'val', e);
        look[e] = { steps: [{ cell: base + e * 2, what: `read values[${e}]` }], pre: `address = base + ${e} × 8` };
      }
    } else if (struct === 'flat') {
      const cap = pow2(n * 2), sc = key === 'str' ? 8 : 4;
      const ctrl = region(`control bytes · ${cap} slots × 1 B`, cap);
      const slots = region(`slots · ${cap} × ${sc * 4} B (${key === 'str' ? '24 B string + 8 B value' : '4 B key + 4 B pad + 8 B value'})`, cap * sc * 4);
      allocBytes = Math.ceil(cap / 64) * 64 + cap * sc * 4;
      put(ctrl, Math.ceil(cap / 4), 'meta', -1);
      const at = new Array(cap).fill(-1);
      for (let e = 0; e < n; e++) {
        const h = hashOf(e);
        let s = h & (cap - 1);
        const probe = [];
        while (at[s] !== -1) { probe.push(s); s = (s + 1) & (cap - 1); }
        probe.push(s);
        at[s] = e;
        if (key === 'str') { put(slots + s * 8, 6, 'key', e); put(slots + s * 8 + 6, 2, 'val', e); }
        else { put(slots + s * 4, 1, 'key', e); put(slots + s * 4 + 1, 1, 'pad', e); put(slots + s * 4 + 2, 2, 'val', e); }
        const steps = [];
        const seenCtrl = new Set();
        probe.forEach(p => { const c = ctrl + (p >> 2); if (!seenCtrl.has(c >> 4)) { seenCtrl.add(c >> 4); steps.push({ cell: c, what: `scan control bytes (slot ${p})` }); } });
        steps.push({ cell: slots + s * sc, what: `read slot ${s}: compare key, add to value` });
        look[e] = { steps, pre: `hash(${key === 'str' ? `"user_…${String(e).padStart(3, '0')}"` : 'key ' + e}) → slot ${h & (cap - 1)}${probe.length > 1 ? `, probed ${probe.length} slots` : ''}` };
      }
    } else {
      const P = nextPrime(n), nc = key === 'str' ? 12 : 8;
      const bk = region(`bucket array · ${P} × 8 B pointers`, P * 8);
      const heapLines = Math.ceil((n * nc * 4 / 64) * 2.2);
      const heap = region(`heap · ${n} nodes × ${nc * 4} B, placed by malloc among other allocations`, heapLines * 64);
      allocBytes = P * 8 + n * nc * 4;
      put(heap, heapLines * 16, 'other', -1);
      const used = new Uint8Array(heapLines * 16);
      const r = rng(n * 97 + nc);
      const nodeAt = [];
      for (let e = 0; e < n; e++) {
        let c;
        do { c = Math.floor(r() * (heapLines * 16 - nc) / 4) * 4; } while (Array.from({ length: nc }, (_, i) => used[c + i]).some(Boolean));
        for (let i = 0; i < nc; i++) used[c + i] = 1;
        nodeAt[e] = heap + c;
        put(heap + c, 2, 'ptr', e); put(heap + c + 2, 2, 'meta', e);
        if (key === 'str') { put(heap + c + 4, 6, 'key', e); put(heap + c + 10, 2, 'val', e); }
        else { put(heap + c + 4, 1, 'key', e); put(heap + c + 5, 1, 'pad', e); put(heap + c + 6, 2, 'val', e); }
      }
      const chains = Array.from({ length: P }, () => []);
      for (let e = 0; e < n; e++) chains[hashOf(e) % P].unshift(e);
      for (let b = 0; b < P; b++) if (chains[b].length) put(bk + b * 2, 2, 'ptr', -1);
      for (let e = 0; e < n; e++) {
        const b = hashOf(e) % P;
        const steps = [{ cell: bk + b * 2, what: `load bucket ${b} pointer` }];
        for (const x of chains[b]) {
          steps.push({ cell: nodeAt[x], what: x === e ? 'follow pointer to node: compare key' : 'follow pointer: wrong key, take next' });
          if (x === e) {
            const v = nodeAt[x] + nc - 2;
            if ((v >> 4) !== (nodeAt[x] >> 4)) steps.push({ cell: v, what: 'node straddles two lines: read value' });
            else steps[steps.length - 1].what += ', add to value';
            break;
          }
        }
        look[e] = { steps, pre: `hash(${key === 'str' ? `"user_…${String(e).padStart(3, '0')}"` : 'key ' + e}) % ${P} → bucket ${b}` };
      }
    }
    return { lines, regions, look, allocBytes };
  }

  function initLayout(root) {
    const svg = root.querySelector('svg'), note = root.querySelector('.avh-note'), st = root.querySelector('.avh-stats');
    const playBtn = root.querySelector('[data-act=play]');
    let model, lineBox = [], overlay, timers = [], playing = null, conf;
    const CW = 9, CH = 12, LW = 16 * CW, GAP = 10, PER = 4, RP = 17, W = PER * LW + (PER - 1) * GAP;

    function clearTimers() { timers.forEach(clearTimeout); timers = []; }
    function render() {
      clearTimers();
      conf = segState(root);
      model = buildLayout(conf.struct, conf.key, conf.n);
      svg.innerHTML = '';
      lineBox = [];
      let y = 0;
      const g = S('g', { 'font-size': 11, 'font-family': 'ui-sans-serif, system-ui, sans-serif' }, svg);
      model.regions.forEach(rg => {
        y += 14;
        T(g, 0, y - 2, rg.name, { opacity: .75 });
        y += 4;
        for (let i = 0; i < rg.count; i++) {
          const li = rg.start + i, col = i % PER, row = Math.floor(i / PER);
          const x0 = col * (LW + GAP), y0 = y + row * RP;
          lineBox[li] = { x: x0, y: y0 };
          model.lines[li].forEach((c, k) => {
            const fill = KIND_FILL[c.kind];
            const a = { x: x0 + k * CW, y: y0, width: CW - 1, height: CH, rx: 1.5 };
            if (fill) a.fill = fill; else { a.fill = 'none'; a.stroke = 'var(--rule)'; }
            if (c.e >= 0) { a.class = 'cell'; a['data-e'] = c.e; }
            const r = S('rect', a, g);
            const tt = S('title', {}, r);
            tt.textContent = `line ${li} · byte ${k * 4}: ${KIND_NAME[c.kind]}${c.e >= 0 ? ' (entry ' + c.e + ')' : ''}`;
          });
        }
        y += Math.ceil(rg.count / PER) * RP + 4;
      });
      overlay = S('g', {}, svg);
      svg.setAttribute('viewBox', `-4 -4 ${W + 8} ${y + 8}`);
      const lookLines = model.look.map(l => new Set(l.steps.map(s => s.cell >> 4)).size);
      const avg = lookLines.reduce((a, b) => a + b, 0) / lookLines.length;
      stats(st, [
        [fmtBytes(model.allocBytes), 'allocated by the structure'],
        [Math.round(conf.n * 8 / model.allocBytes * 100) + '%', 'of those bytes are your values'],
        [avg.toFixed(2), 'cache lines per lookup (avg)'],
        [Math.max(...lookLines), 'cache lines per lookup (worst)'],
      ]);
      note.innerHTML = conf.struct === 'array' && conf.key === 'str'
        ? 'String keys were mapped to dense ids <b>once, at ingest</b> (Experiment 3). The array stores no keys: the id is the address. Click a value.'
        : 'Click a colored cell to look up that entry.';
    }
    function fmtBytes(b) { return b >= 1024 ? (b / 1024).toFixed(1) + ' KB' : b + ' B'; }
    function lookup(e) {
      clearTimers();
      overlay.innerHTML = '';
      const L = model.look[e];
      const seen = new Map();
      const parts = [`<b>${L.pre}</b>`];
      L.steps.forEach((s, i) => {
        timers.push(setTimeout(() => {
          const li = s.cell >> 4, bx = lineBox[li];
          const isNew = !seen.has(li);
          if (isNew) {
            seen.set(li, seen.size + 1);
            S('rect', { class: 'ring pop', x: bx.x - 2, y: bx.y - 2, width: LW + 3, height: CH + 4, rx: 3, style: 'transform-origin:' + (bx.x + LW / 2) + 'px ' + (bx.y + CH / 2) + 'px' }, overlay);
            const bd = S('g', { class: 'badge pop' }, overlay);
            S('circle', { cx: bx.x + LW + 1, cy: bx.y - 1, r: 6.5 }, bd);
            T(bd, bx.x + LW + 1, bx.y + 2.5, String(seen.size), { 'text-anchor': 'middle' });
          }
          const cellK = s.cell & 15;
          S('rect', { class: 'pop', x: bx.x + cellK * CW - 1, y: bx.y - 1, width: CW + 1, height: CH + 2, fill: 'none', stroke: 'var(--miss)', 'stroke-width': 2, rx: 2 }, overlay);
          parts.push(`${i + 1}. ${s.what} (line ${li}${isNew ? '' : ', already loaded'})`);
          note.innerHTML = parts.join(' → ') + (i === L.steps.length - 1 ? ` · <b>${seen.size} cache line${seen.size > 1 ? 's' : ''}</b>` : '');
        }, i * 550));
      });
      if (!L.steps.length) note.innerHTML = parts[0];
    }
    svg.addEventListener('click', ev => {
      const c = ev.target.closest('.cell');
      if (c) { stop(); lookup(+c.dataset.e); }
    });
    function stop() { if (playing) { clearInterval(playing); playing = null; playBtn.textContent = '▶ Play lookups'; } }
    playBtn.addEventListener('click', () => {
      if (playing) return stop();
      const r = rng(Date.now() & 0xffff);
      const go = () => lookup(Math.floor(r() * conf.n));
      go();
      playing = setInterval(go, 2600);
      playBtn.textContent = '⏸ Pause';
    });
    wireSegs(root, () => { const was = !!playing; stop(); render(); if (was) playBtn.click(); });
    render();
  }

  // ---------- Widget B: cache simulator ----------
  function buildAccess(struct, G) {
    const regions = [];
    let total = 0;
    function region(name, lines) { regions.push({ name, start: total, count: lines }); total += lines; return regions[regions.length - 1].start; }
    const access = new Array(G);
    const hashOf = e => mix32((e + 1) * 2654435761);
    if (struct === 'array') {
      const b = region(`values[] · ${G} × 8 B = ${kb(G * 8)}`, Math.ceil(G / 8));
      for (let e = 0; e < G; e++) access[e] = [b + (e >> 3)];
    } else if (struct === 'flat') {
      const cap = pow2(G * 2);
      const c = region(`control bytes · ${kb(cap)}`, Math.ceil(cap / 64));
      const s = region(`slots · ${cap} × 16 B = ${kb(cap * 16)}`, cap / 4);
      const at = new Int32Array(cap).fill(-1);
      for (let e = 0; e < G; e++) {
        let p = hashOf(e) & (cap - 1);
        const seq = [];
        while (at[p] !== -1) { seq.push(p); p = (p + 1) & (cap - 1); }
        seq.push(p); at[p] = e;
        const ls = [];
        seq.forEach(q => { const l = c + (q >> 6); if (!ls.includes(l)) ls.push(l); });
        ls.push(s + (p >> 2));
        access[e] = ls;
      }
    } else {
      const P = nextPrime(G);
      const b = region(`bucket array · ${P} × 8 B = ${kb(P * 8)}`, Math.ceil(P / 8));
      const H = G;
      const h = region(`heap · ${G} nodes × 32 B, scattered (${kb(G * 32)} of nodes in ${kb(H * 64)})`, H);
      const r = rng(G + 5);
      const halves = Array.from({ length: H * 2 }, (_, i) => i);
      for (let i = halves.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [halves[i], halves[j]] = [halves[j], halves[i]]; }
      const node = e => h + (halves[e] >> 1);
      const chains = Array.from({ length: P }, () => []);
      for (let e = 0; e < G; e++) chains[hashOf(e) % P].unshift(e);
      for (let e = 0; e < G; e++) {
        const bk = hashOf(e) % P;
        const ls = [b + (bk >> 3)];
        for (const x of chains[bk]) { ls.push(node(x)); if (x === e) break; }
        access[e] = ls;
      }
    }
    return { regions, total, access };
  }
  function kb(b) { return b >= 1024 ? (b / 1024).toFixed(b >= 10240 ? 0 : 1) + ' KB' : b + ' B'; }

  function initCache(root) {
    const svg = root.querySelector('svg'), note = root.querySelector('.avh-note'), st = root.querySelector('.avh-stats');
    const runBtn = root.querySelector('[data-act=run]');
    const ROWS = 4000, COLS = 64, SQ = 9.4;
    let conf, model, rects, rows, pos, cache, hits, misses, raf = null, stepTimer = null;
    function setup() {
      stopRun();
      conf = segState(root);
      const G = +conf.g;
      model = buildAccess(conf.struct, G);
      const r = rng(1234 + G);
      rows = Array.from({ length: ROWS }, () => Math.floor(r() * G));
      if (conf.order === 'sorted') rows.sort((a, b) => a - b);
      pos = 0; hits = 0; misses = 0; cache = new Map();
      svg.innerHTML = '';
      rects = [];
      let y = 0;
      const g = S('g', { 'font-size': 11, 'font-family': 'ui-sans-serif, system-ui, sans-serif' }, svg);
      model.regions.forEach(rg => {
        y += 14;
        T(g, 0, y - 3, rg.name, { opacity: .75 });
        for (let i = 0; i < rg.count; i++) {
          rects[rg.start + i] = S('rect', { x: (i % COLS) * SQ, y: y + Math.floor(i / COLS) * SQ, width: SQ - 1.4, height: SQ - 1.4, rx: 1.2, fill: 'var(--faint)', stroke: 'var(--rule)', 'stroke-width': .5 }, g);
        }
        y += Math.ceil(rg.count / COLS) * SQ + 6;
      });
      svg.setAttribute('viewBox', `-2 -2 ${COLS * SQ + 4} ${y + 4}`);
      const ws = model.total * 64, cb = +conf.cache * 64;
      note.innerHTML = `Table touches up to <b>${kb(ws)}</b> of memory. Cache holds <b>${kb(cb)}</b>. ${ws <= cb ? 'Everything fits: expect misses only on first touch.' : `The table is ${(ws / cb).toFixed(1)}× the cache.`}`;
      updateStats();
    }
    function touch(line, flash) {
      const r = rects[line];
      let hit;
      if (cache.has(line)) { cache.delete(line); cache.set(line, 1); hits++; hit = true; }
      else {
        misses++; hit = false;
        cache.set(line, 1);
        if (cache.size > +conf.cache) {
          const old = cache.keys().next().value;
          cache.delete(old);
          rects[old].setAttribute('fill', 'var(--faint)');
          rects[old].removeAttribute('fill-opacity');
        }
      }
      if (flash) {
        r.setAttribute('fill', hit ? 'var(--hit)' : 'var(--miss)');
        r.setAttribute('fill-opacity', 1);
        setTimeout(() => { if (cache.has(line)) { r.setAttribute('fill', 'var(--v)'); r.setAttribute('fill-opacity', .6); } }, 260);
      } else {
        r.setAttribute('fill', 'var(--v)');
        r.setAttribute('fill-opacity', .6);
      }
      return hit;
    }
    function stepRows(k, flash) {
      let last = null;
      for (let i = 0; i < k && pos < rows.length; i++, pos++) {
        const id = rows[pos];
        const res = model.access[id].map(l => [l, touch(l, flash)]);
        last = { id, res };
      }
      return last;
    }
    function updateStats() {
      const acc = hits + misses;
      const ns = pos ? (hits * 1 + misses * 80) / pos : 0;
      stats(st, [
        [`${pos} / ${ROWS}`, 'rows processed'],
        [acc ? (hits / acc * 100).toFixed(1) + '%' : '–', 'cache hit rate'],
        [pos ? (misses / pos).toFixed(2) : '–', 'misses per row'],
        [pos ? ns.toFixed(1) + ' ns' : '–', 'modeled time per row'],
      ]);
    }
    function stopRun() {
      if (raf) cancelAnimationFrame(raf); raf = null;
      if (stepTimer) clearInterval(stepTimer); stepTimer = null;
      runBtn.textContent = pos >= (rows ? rows.length : 1) ? '↺ Restart' : '▶ Run';
    }
    function run() {
      if (raf || stepTimer) { stopRun(); return; }
      if (pos >= rows.length) setup();
      runBtn.textContent = '⏸ Pause';
      if (conf.speed === 'max') {
        stepRows(rows.length, false); updateStats(); stopRun(); return;
      }
      if (conf.speed === 'slow') {
        stepTimer = setInterval(() => {
          const last = stepRows(1, true);
          updateStats();
          if (last) note.innerHTML = `row ${pos}: id <b>${last.id}</b> → ` + last.res.map(([l, h]) => `line ${l} <b style="color:var(${h ? '--hit' : '--miss'})">${h ? 'hit' : 'miss'}</b>`).join(' → ');
          if (pos >= rows.length) stopRun();
        }, 420);
        return;
      }
      const tick = () => {
        stepRows(12, true);
        updateStats();
        if (pos >= rows.length) { raf = null; stopRun(); return; }
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }
    runBtn.addEventListener('click', run);
    wireSegs(root, setup);
    setup();
  }

  // ---------- Widget C: measured results ----------
  const METHODS = ['unordered_map<string>', 'unordered_map<u32>', 'flat open-addressing', 'array[id]'];
  const TIME = [[12.80, 2.29, 2.69, 0.35], [19.32, 2.80, 3.03, 0.34], [83.57, 20.84, 6.44, 0.90], [165.28, 80.39, 13.91, 2.59]];
  const MEM = [[0.012, 0.006, 0.003, 0.0008], [0.61, 0.45, 0.43, 0.08], [61.2, 45.2, 27.3, 8.0], [585.4, 425.4, 436.2, 80.0]];
  const GL = ['100', '10K', '1M', '10M'];
  function logScale(lo, hi, x0, x1) { const a = Math.log10(lo), b = Math.log10(hi); return v => x0 + (Math.log10(v) - a) / (b - a) * (x1 - x0); }
  function initResults(root) {
    const svg = root.querySelector('svg');
    function render() {
      const gi = +segState(root).g;
      svg.innerHTML = '';
      svg.setAttribute('viewBox', '0 0 640 330');
      const g = S('g', { 'font-size': 12, 'font-family': 'ui-sans-serif, system-ui, sans-serif' }, svg);
      panel(g, 0, 'Time per row (ns, log scale)', TIME[gi], 0.1, 300, [0.1, 1, 10, 100], v => v.toFixed(2) + ' ns', true, []);
      panel(g, 170, 'Table memory (MB, log scale)', MEM[gi], 0.0005, 1000, [0.001, 0.1, 10, 1000], v => v >= 1 ? v.toFixed(1) + ' MB' : (v * 1024).toFixed(v < 0.01 ? 1 : 0) + ' KB', false, [[0.128, 'L1 128 KB'], [16, 'L2 16 MB']]);
    }
    function panel(g, top, title, vals, lo, hi, ticks, fmt, showRatio, refs) {
      const X0 = 170, X1 = 560, sx = logScale(lo, hi, X0, X1);
      T(g, 0, top + 14, title, { 'font-weight': 650 });
      ticks.forEach(t => {
        S('line', { x1: sx(t), x2: sx(t), y1: top + 24, y2: top + 150, stroke: 'currentColor', 'stroke-opacity': .1 }, g);
        T(g, sx(t), top + 164, String(t), { 'text-anchor': 'middle', opacity: .6, 'font-size': 10 });
      });
      refs.forEach(([v, l]) => {
        S('line', { x1: sx(v), x2: sx(v), y1: top + 24, y2: top + 150, stroke: 'currentColor', 'stroke-opacity': .5, 'stroke-dasharray': '3 3' }, g);
        T(g, sx(v) + 3, top + 32, l, { opacity: .7, 'font-size': 10 });
      });
      vals.forEach((v, i) => {
        const y = top + 34 + i * 29, isArr = i === 3;
        T(g, X0 - 8, y + 12, METHODS[i], { 'text-anchor': 'end', 'font-family': 'ui-monospace, SFMono-Regular, Menlo, monospace', 'font-size': 11 });
        const w = Math.max(2, sx(v) - X0);
        const bar = S('rect', { class: 'grow', x: X0, y, width: w, height: 17, rx: 3, fill: isArr ? 'var(--v)' : 'currentColor', 'fill-opacity': isArr ? 1 : .35, style: `transform-origin:${X0}px 0` }, g);
        S('title', {}, bar).textContent = `${METHODS[i]}: ${fmt(v)}`;
        const ratio = showRatio && !isArr ? ` · ${(v / vals[3]).toFixed(1)}× array` : '';
        T(g, X0 + w + 6, y + 12.5, fmt(v) + ratio, { 'font-size': 11, 'font-variant-numeric': 'tabular-nums' });
      });
    }
    wireSegs(root, render);
    render();
  }

  // ---------- Widget E: small-n ----------
  const NS_N = [4, 8, 16, 32, 64, 128, 256, 1024];
  const SMALL = {
    u32: { scan: [5.42, 6.54, 7.88, 10.30, 14.42, 22.56, 40.76, 137.50], hash: [5.08, 7.49, 1.89, 4.21, 2.83, 2.06, 0.91, 0.90] },
    str: { scan: [9.88, 13.74, 19.22, 30.15, 57.85, 118.67, 156.18, 857.41], hash: [9.90, 15.15, 11.56, 13.63, 13.20, 12.89, 13.92, 11.24] },
  };
  function initSmall(root) {
    const svg = root.querySelector('svg');
    function render() {
      const k = segState(root).key, d = SMALL[k];
      svg.innerHTML = '';
      svg.setAttribute('viewBox', '0 0 640 300');
      const g = S('g', { 'font-size': 11, 'font-family': 'ui-sans-serif, system-ui, sans-serif' }, svg);
      const X0 = 50, X1 = 520, Y0 = 260, Y1 = 20;
      const sx = v => X0 + (Math.log2(v) - 2) / 8 * (X1 - X0);
      const sy = v => Y0 - (Math.log10(v) - Math.log10(0.5)) / (Math.log10(1000) - Math.log10(0.5)) * (Y0 - Y1);
      [1, 10, 100, 1000].forEach(t => {
        S('line', { x1: X0, x2: X1, y1: sy(t), y2: sy(t), stroke: 'currentColor', 'stroke-opacity': .1 }, g);
        T(g, X0 - 6, sy(t) + 4, t + ' ns', { 'text-anchor': 'end', opacity: .6, 'font-size': 10 });
      });
      NS_N.forEach(n => T(g, sx(n), Y0 + 16, String(n), { 'text-anchor': 'middle', opacity: .6, 'font-size': 10 }));
      T(g, (X0 + X1) / 2, Y0 + 32, 'entries in the map (n)', { 'text-anchor': 'middle', opacity: .7 });
      [['scan', 'linear scan of array', 'var(--k)'], ['hash', 'unordered_map::find', 'var(--v)']].forEach(([key, label, col]) => {
        const pts = d[key].map((v, i) => [sx(NS_N[i]), sy(v)]);
        const path = S('path', { d: 'M' + pts.map(p => p.join(',')).join(' L'), fill: 'none', stroke: col, 'stroke-width': 2, 'stroke-linejoin': 'round' }, g);
        const len = path.getTotalLength ? path.getTotalLength() : 0;
        if (len) { path.style.strokeDasharray = len; path.style.strokeDashoffset = len; requestAnimationFrame(() => { path.style.transition = 'stroke-dashoffset .8s ease-out'; path.style.strokeDashoffset = 0; }); }
        pts.forEach((p, i) => {
          const c = S('circle', { cx: p[0], cy: p[1], r: 4.5, fill: col, stroke: 'var(--panel)', 'stroke-width': 2 }, g);
          S('title', {}, c).textContent = `${label}, n=${NS_N[i]}: ${d[key][i]} ns`;
        });
        const last = pts[pts.length - 1];
        T(g, last[0] + 10, last[1] + 4, label, { 'font-size': 11 });
      });
    }
    wireSegs(root, render);
    render();
  }

  function boot() {
    const a = document.getElementById('avh-layout'); if (a) initLayout(a);
    const b = document.getElementById('avh-cache'); if (b) initCache(b);
    const c = document.getElementById('avh-results'); if (c) initResults(c);
    const e = document.getElementById('avh-smalln'); if (e) initSmall(e);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
</script>
