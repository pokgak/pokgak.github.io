---
title: "Maglev vs Rendezvous: what GCP is changing in internal load balancers"
date: 2026-08-19T12:00:00+0800
tags: [gcp, networking, load-balancing, consistent-hashing]
---

Google sent a notice this week: starting **21 September 2026**, most internal passthrough Network Load Balancers switch their backend-selection algorithm from **Maglev** to **Rendezvous**, completing by 9 October. Connection tracking, session affinity and health checks are unchanged. What changes is the answer to exactly one question — given this flow, which backend?

I wanted to understand the trade properly rather than take the release note's word for it, so I built an interactive comparison. Both algorithms are implemented from their published descriptions — Maglev per Eisenbud et al. (NSDI 2016), Rendezvous per Thaler & Ravishankar (1996) — and both run live in the page over the same 32-bit hash. The churn figures are measured in your browser as you change the backend set, not quoted from a paper.

<div class="not-prose" style="position:relative;left:50%;transform:translateX(-50%);width:min(1180px,calc(100vw - 3rem));margin-top:2.5rem;margin-bottom:2.5rem">
  <iframe id="maglev-embed"
          src="/embeds/maglev-vs-rendezvous/?embed=1"
          title="Maglev vs Rendezvous: interactive comparison"
          style="width:100%;height:2400px;border:0;display:block;border-radius:6px"></iframe>
  <p style="margin:0.75rem 0 0;font-size:0.8rem;text-align:center;opacity:0.65">
    Interactive — <a href="/embeds/maglev-vs-rendezvous/">open it full width in its own page</a>.
  </p>
</div>

<script>
(function () {
  var f = document.getElementById('maglev-embed');
  if (!f) return;
  function fit() {
    try {
      var d = f.contentDocument;
      if (d && d.documentElement) f.style.height = d.documentElement.scrollHeight + 'px';
    } catch (e) { /* cross-origin: keep the fallback height */ }
  }
  f.addEventListener('load', function () {
    fit();
    try { new ResizeObserver(fit).observe(f.contentDocument.body); } catch (e) {}
  });
  window.addEventListener('resize', fit);
})();
</script>

## What the numbers actually say

My first assumption was that Maglev must be causing meaningfully more connection churn, and that this was the reason for the change. The simulation says otherwise.

- **Rendezvous is provably minimal.** Drain a backend and only that backend's flows move. The "needless" column reads exactly zero, every time, at any scale. That is a property of the algorithm, not a tuning result.
- **Maglev at a production table size is already very close.** With M = 65,537 the needless churn is a couple of hundredths of a percent — a handful of flows in twenty thousand.
- **But that closeness is bought with the table.** Shrink M to 127 slots and needless churn climbs past 1.5%. The large table is what makes Maglev nearly minimal, and the large table is exactly what every load balancer has to hold and rebuild.

So the win isn't churn — it's deleting the state. Rendezvous keeps nothing per forwarding rule and rebuilds nothing when a backend appears or disappears. Google's stated reason, "scalability and efficiency", lines up with that far better than any disruption argument.

The cost is real but well-placed: Rendezvous gives up the O(1) table read and pays a hash per backend on every new flow. That only lands on flows that miss the connection-tracking table, which in a busy load balancer is a small minority of packets.

## What to check on your own load balancers

Established connections are not affected — backend selection only runs for a flow with no connection-tracking entry. The one-time remap of *new* flows is where you'd notice something:

- Anything holding per-client state outside the connection — an in-memory session keyed by client IP, a per-tenant cache warmed on the backend — sees clients land somewhere new.
- Long-idle flows that age out of connection tracking re-resolve, and may not come back to the same backend.

There is a carve-out: load balancers stay on Maglev where backend VMs have two or more NICs **and** at least two of those NICs are eligible backends of at least two internal passthrough NLBs.

One caveat on all of the above: Google has not published the details of its own implementation. Treat the measured numbers as properties of the published algorithms, not as predictions about your specific load balancer.
