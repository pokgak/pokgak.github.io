---
title: "Maglev vs Rendezvous: GCP's Load Balancer Hashing Change"
date: 2026-08-19T12:00:00+0800
tags: [gcp, networking, load-balancing, consistent-hashing]
---

GCP notice: from **21 Sep 2026** (complete by 9 Oct), most internal passthrough NLBs switch backend selection from **Maglev** to **Rendezvous**. Connection tracking, session affinity and health checks are unchanged.

Implemented both from their papers — Maglev (Eisenbud et al., NSDI 2016), Rendezvous/HRW (Thaler & Ravishankar, 1996) — over the same 32-bit MurmurHash3, to check the trade rather than take the release note's word for it. Every number below is measured, not quoted.

## The Two Algorithms

- **Maglev** — precompute a table of `M` slots (prime; 65537 in the paper). Each backend derives an offset and a skip from two hashes, generating its preference list. Backends take turns claiming the first free slot on their list until the table is full. Lookup = 1 hash + 1 array read.
- **Rendezvous** — no table. For each backend, hash `(flow, backend name)`; highest score wins. Lookup = N hashes.
- Both are consistent hashing: no shared state, no coordination, every LB instance independently reaching the same answer for the same flow.

<figure class="not-prose" style="margin:2rem 0">
<svg viewBox="0 0 720 400" role="img" aria-label="One flow resolved two ways. Maglev hashes the 5-tuple to 0x705afa7d, takes it mod 127 to get slot 103, and reads be-0 from the table. Rendezvous scores all four backends and picks be-3, the highest." style="width:100%;height:auto;display:block;overflow:visible">
  <g fill="currentColor" font-family="ui-sans-serif, system-ui, sans-serif">
    <!-- shared flow key -->
    <rect x="130" y="6" width="460" height="34" rx="5" fill="none" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5"/>
    <text x="360" y="27" text-anchor="middle" font-size="13" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">10.240.0.14:51820 -&gt; 10.128.0.9:443 tcp</text>
    <path d="M300 40 L180 68" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5" fill="none"/>
    <path d="M420 40 L556 68" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5" fill="none"/>

    <!-- ── Maglev ── -->
    <text x="180" y="88" text-anchor="middle" font-size="11" letter-spacing="1.6" opacity=".6">MAGLEV</text>
    <rect x="30" y="100" width="300" height="30" rx="4" fill="none" stroke="currentColor" stroke-opacity=".28" stroke-width="1.5"/>
    <text x="180" y="120" text-anchor="middle" font-size="12" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">murmur3 = 0x705afa7d</text>
    <path d="M180 130 L180 150" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5"/>
    <rect x="30" y="150" width="300" height="30" rx="4" fill="none" stroke="currentColor" stroke-opacity=".28" stroke-width="1.5"/>
    <text x="180" y="170" text-anchor="middle" font-size="12" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">0x705afa7d mod 127 = 103</text>
    <path d="M180 180 L180 202" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5"/>

    <!-- real table contents, slots 99..107, with 103 highlighted -->
    <g>
      <rect x="46"  y="206" width="26" height="26" rx="4" fill="#6c71c4" fill-opacity=".5"/>
      <rect x="76"  y="206" width="26" height="26" rx="4" fill="#dc322f" fill-opacity=".5"/>
      <rect x="106" y="206" width="26" height="26" rx="4" fill="#2aa198" fill-opacity=".5"/>
      <rect x="136" y="206" width="26" height="26" rx="4" fill="#dc322f" fill-opacity=".5"/>
      <rect x="166" y="206" width="26" height="26" rx="4" fill="#b58900"/>
      <rect x="164" y="204" width="30" height="30" rx="5" fill="none" stroke="#cb4b16" stroke-width="2.5"/>
      <rect x="200" y="206" width="26" height="26" rx="4" fill="#dc322f" fill-opacity=".5"/>
      <rect x="230" y="206" width="26" height="26" rx="4" fill="#b58900" fill-opacity=".5"/>
      <rect x="260" y="206" width="26" height="26" rx="4" fill="#dc322f" fill-opacity=".5"/>
      <rect x="290" y="206" width="26" height="26" rx="4" fill="#b58900" fill-opacity=".5"/>
      <text x="59"  y="248" text-anchor="middle" font-size="9" opacity=".45">99</text>
      <text x="179" y="248" text-anchor="middle" font-size="9" opacity=".8" font-weight="600">103</text>
      <text x="303" y="248" text-anchor="middle" font-size="9" opacity=".45">107</text>
    </g>
    <text x="180" y="268" text-anchor="middle" font-size="11" opacity=".6">one array read into the 127-slot table</text>
    <path d="M180 274 L180 292" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5"/>
    <rect x="132" y="292" width="96" height="30" rx="5" fill="#b58900"/>
    <text x="180" y="312" text-anchor="middle" font-size="13" font-weight="600" fill="#002b36" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">be-0</text>

    <!-- ── Rendezvous ── -->
    <text x="556" y="88" text-anchor="middle" font-size="11" letter-spacing="1.6" opacity=".6">RENDEZVOUS</text>
    <text x="556" y="112" text-anchor="middle" font-size="11" opacity=".6">score = hash(flow | backend name)</text>

    <g font-size="11" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">
      <text x="396" y="136" opacity=".75">be-0</text>
      <rect x="440" y="126" width="240" height="14" rx="3" fill="currentColor" fill-opacity=".08"/>
      <rect x="440" y="126" width="13.9" height="14" rx="3" fill="#b58900"/>
      <text x="716" y="136" text-anchor="end" opacity=".75">5.8%</text>

      <text x="396" y="164" opacity=".75">be-1</text>
      <rect x="440" y="154" width="240" height="14" rx="3" fill="currentColor" fill-opacity=".08"/>
      <rect x="440" y="154" width="172.8" height="14" rx="3" fill="#dc322f"/>
      <text x="716" y="164" text-anchor="end" opacity=".75">72.0%</text>

      <text x="396" y="192" opacity=".75">be-2</text>
      <rect x="440" y="182" width="240" height="14" rx="3" fill="currentColor" fill-opacity=".08"/>
      <rect x="440" y="182" width="99.1" height="14" rx="3" fill="#6c71c4"/>
      <text x="716" y="192" text-anchor="end" opacity=".75">41.3%</text>

      <text x="396" y="220" font-weight="600">be-3</text>
      <rect x="440" y="210" width="240" height="14" rx="3" fill="currentColor" fill-opacity=".08"/>
      <rect x="440" y="210" width="217.0" height="14" rx="3" fill="#2aa198"/>
      <text x="716" y="220" text-anchor="end" font-weight="600">90.4%</text>
    </g>
    <text x="556" y="250" text-anchor="middle" font-size="11" opacity=".6">no table - highest score wins</text>
    <path d="M556 258 L556 292" stroke="currentColor" stroke-opacity=".35" stroke-width="1.5"/>
    <rect x="508" y="292" width="96" height="30" rx="5" fill="#2aa198"/>
    <text x="556" y="312" text-anchor="middle" font-size="13" font-weight="600" fill="#002b36" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">be-3</text>

    <text x="360" y="358" text-anchor="middle" font-size="12" opacity=".7">Same flow, different backend. Neither is wrong - they are simply different mappings.</text>
  </g>
</svg>
<figcaption style="font-size:0.8rem;opacity:0.65;text-align:center;margin-top:0.5rem">One flow, resolved both ways. Real values from the implementation.</figcaption>
</figure>

## Watching The Table Get Built

The turn-taking is the part Rendezvous has no equivalent for, and it is easier to watch than to describe. Each backend walks its own `(offset + j·skip) mod M` sequence, claiming the first slot nobody has taken.

<div class="not-prose" style="margin:2rem 0">
  <iframe class="embed-frame"
          src="/embeds/maglev-vs-rendezvous/?only=build&amp;embed=1"
          title="Maglev table population, animated"
          style="width:100%;height:760px;border:0;display:block;border-radius:6px"></iframe>
</div>

Turn-taking is what makes the result **exactly balanced** — at M = 127 with 4 backends the slots split 32 / 32 / 32 / 31, no statistics involved. It is also what makes it expensive to change: add or remove a backend and the permutations interleave differently, so the whole table is rebuilt.

## What The Simulation Shows

Drain a backend and watch what moves. 20,000 synthetic flows, both algorithms, before and after:

<div class="not-prose" style="position:relative;left:50%;transform:translateX(-50%);width:min(980px,calc(100vw - 3rem));margin:2rem 0">
  <iframe class="embed-frame"
          src="/embeds/maglev-vs-rendezvous/?only=lab&amp;embed=1"
          title="Backend churn lab: measured flow remapping"
          style="width:100%;height:1500px;border:0;display:block;border-radius:6px"></iframe>
  <p style="margin:0.75rem 0 0;font-size:0.8rem;text-align:center;opacity:0.65">
    <a href="/embeds/maglev-vs-rendezvous/">Open the full interactive page</a> for the mechanism walkthrough and lookup-cost benchmark.
  </p>
</div>

- **Rendezvous churn is provably minimal.** Drain a backend, only its flows move. The "needless" column reads exactly 0, every time, at any table size. Property of the algorithm, not a tuning result.
- **Maglev at production table size is already close.** M = 65,537 → ~0.02% needless. A handful of flows in 20,000.
- **That closeness is bought with the table.** Shrink M and it climbs sharply.

<figure class="not-prose" style="margin:2rem 0">
<svg viewBox="0 0 720 300" role="img" aria-label="Bar chart of Maglev needless churn against table size, draining one of four backends: 1.615 percent at M=127, 0.770 at 1021, 0.070 at 16381, 0.020 at 65537, and 0.000 at 655373. Rendezvous is 0.00 percent at every size." style="width:100%;height:auto;display:block;overflow:visible">
  <g font-family="ui-sans-serif, system-ui, sans-serif" fill="currentColor">
    <!-- gridlines -->
    <g stroke="currentColor" stroke-opacity=".15" stroke-width="1">
      <line x1="70" y1="230" x2="690" y2="230"/>
      <line x1="70" y1="167" x2="690" y2="167"/>
      <line x1="70" y1="104" x2="690" y2="104"/>
      <line x1="70" y1="41"  x2="690" y2="41"/>
    </g>
    <g font-size="11" opacity=".6" text-anchor="end">
      <text x="60" y="234">0</text>
      <text x="60" y="171">0.5</text>
      <text x="60" y="108">1.0</text>
      <text x="60" y="45">1.5</text>
    </g>
    <text x="18" y="140" font-size="11" opacity=".6" text-anchor="middle" transform="rotate(-90 18 140)">needless churn (% of flows)</text>

    <!-- Maglev bars -->
    <g fill="#cb4b16">
      <rect x="101" y="26.5"  width="62" height="203.5" rx="3"/>
      <rect x="225" y="132.9" width="62" height="97.1"  rx="3"/>
      <rect x="349" y="221.2" width="62" height="8.8"   rx="3"/>
      <rect x="473" y="227.5" width="62" height="2.5"   rx="3"/>
      <rect x="597" y="228.5" width="62" height="1.5"   rx="3" fill-opacity=".3"/>
    </g>
    <g font-size="12" font-weight="600" text-anchor="middle" fill="#cb4b16">
      <text x="132" y="18">1.615%</text>
      <text x="256" y="124">0.770%</text>
      <text x="380" y="213">0.070%</text>
      <text x="504" y="219">0.020%</text>
      <text x="628" y="220">0.000%</text>
    </g>

    <!-- Rendezvous baseline, keyed in the empty upper right -->
    <line x1="70" y1="230" x2="690" y2="230" stroke="#2aa198" stroke-width="3"/>
    <g font-size="12" font-weight="600">
      <rect x="436" y="26" width="18" height="8" rx="2" fill="#cb4b16"/>
      <text x="462" y="35" fill="#cb4b16">Maglev</text>
      <rect x="436" y="52" width="18" height="8" rx="2" fill="#2aa198"/>
      <text x="462" y="61" fill="#2aa198">Rendezvous - 0.00% at every size</text>
    </g>

    <!-- x axis -->
    <g font-size="11" opacity=".7" text-anchor="middle" font-family="ui-monospace, SFMono-Regular, Menlo, monospace">
      <text x="132" y="272">127</text>
      <text x="256" y="272">1,021</text>
      <text x="380" y="272">16,381</text>
      <text x="504" y="272">65,537</text>
      <text x="628" y="272">655,373</text>
    </g>
    <text x="380" y="294" font-size="11" opacity=".6" text-anchor="middle">Maglev table size M</text>
  </g>
</svg>
<figcaption style="font-size:0.8rem;opacity:0.65;text-align:center;margin-top:0.5rem">Draining 1 of 4 backends across 20,000 flows. Maglev's needless churn is a function of table size; Rendezvous has none to trade.</figcaption>
</figure>

## Why The Switch, Then

- Not churn — Maglev was already within a fraction of a percent at production table sizes.
- It's the **state**: `M` entries per forwarding rule, replicated to every LB instance, rebuilt from scratch on every backend-set change.
- Rendezvous holds nothing and rebuilds nothing. Matches Google's stated reason ("scalability and efficiency") far better than any disruption argument.
- Cost: O(N) per lookup instead of O(1). Only paid by flows that miss the connection-tracking table.
- Bonus: weights are exact and closed-form in Rendezvous (`-w / ln(u)`), vs approximated in Maglev by giving backends extra turns.

| | Maglev | Rendezvous |
|---|---|---|
| State per rule | table of `M` entries, on every instance | none |
| Work per new flow | 1 hash + 1 array read | N hashes + N comparisons |
| Work per backend change | rebuild the whole table | none |
| Load balance | exact by construction | even in expectation |
| Churn on backend loss | near-minimal, because `M` is large | exactly minimal, at any size |
| Weights | approximated via extra turns | exact, `-w / ln(u)` |

## What To Check

- Established connections are unaffected — selection only runs on a connection-tracking miss.
- The same 5-tuple can resolve to a *different* backend after the switch. One-time remap of new flows, not ongoing instability.
- Watch anything holding per-client state outside the connection: in-memory sessions keyed by client IP, per-tenant caches warmed on the backend.
- Long-idle flows that age out of connection tracking re-resolve, and may not return to the same backend.
- **Carve-out**: stays on Maglev where backend VMs have 2+ NICs *and* at least two of those NICs are eligible backends of at least two internal passthrough NLBs.

Caveat: Google hasn't published its own implementation details. These are properties of the published algorithms, not predictions about a specific load balancer.

<script>
(function () {
  document.querySelectorAll('iframe.embed-frame').forEach(function (f) {
    // Measure the root element's own box, not scrollHeight: once the frame is
    // taller than its content, scrollHeight returns the frame height and the
    // iframe can only ever grow.
    function fit() {
      try {
        var d = f.contentDocument;
        if (!d || !d.documentElement) return;
        var h = Math.ceil(d.documentElement.getBoundingClientRect().height);
        if (h > 0 && Math.abs(parseFloat(f.style.height) - h) > 2) f.style.height = h + 'px';
      } catch (e) { /* keep the fallback height */ }
    }
    f.addEventListener('load', function () {
      fit();
      try { new ResizeObserver(fit).observe(f.contentDocument.body); } catch (e) {}
    });
    window.addEventListener('resize', fit);
  });
})();
</script>
