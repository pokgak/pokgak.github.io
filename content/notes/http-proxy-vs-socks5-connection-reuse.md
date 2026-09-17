---
title: "HTTP Proxy vs SOCKS5: Who Owns the TCP Connection"
date: 2026-09-17T18:00:00+0800
tags: [networking, tailscale, http, kubernetes, performance]
---

A latency regression that looked like a proxy being slow, but was really about which process owned the TCP connection — and therefore which connection pool got to reuse it.

## The setup

A Python service (httpx, async) forwards requests to backends that live on another network, reachable only over a [Tailscale](https://tailscale.com) tailnet. The backends sit behind a reverse proxy roughly 150 ms away.

**Before:** every service pod ran a Tailscale sidecar container in kernel mode. Tailnet routes landed in the pod's own network namespace, so the app dialled the backend directly. The client's own connection pool held those connections and reused them — dozens of requests per connection.

**The problem with that:** each sidecar registers its own tailnet device. With autoscaling, device count tracked pod count, and the tailnet has a device cap. Scale up enough times and you hit it.

**After:** one shared gateway Deployment with a fixed replica count runs `tailscaled` instead. Pods reach the tailnet through it via `HTTP_PROXY`. Device count now tracks replicas, not pods. Problem solved.

Latency went up by about a second.

## Two things have to be true at once

The regression needs both of these, and neither is obvious on its own.

**1. httpx does not use `CONNECT` for `http://` URLs.**

With a proxy configured, the shape of the connection depends entirely on the scheme:

```python
import httpx, httpcore

c = httpx.AsyncClient(base_url="http://10.0.0.5:8000")   # HTTP_PROXY set
pool = c._transport_for_url(httpx.URL("http://10.0.0.5:8000/v1/x"))._pool

pool.create_connection(httpcore.Origin(b"http",  b"10.0.0.5",    8000))
# -> AsyncForwardHTTPConnection

pool.create_connection(httpcore.Origin(b"https", b"example.com", 443))
# -> AsyncTunnelHTTPConnection
```

- `https://` gets a **tunnel**: one `CONNECT`, then an opaque byte pipe. The client's connection reaches the origin end to end.
- `http://` gets **forward proxying**: the client sends `POST http://host:port/path HTTP/1.1` with an absolute URI, and the proxy *terminates* that request and re-originates it.

Forward proxying means one request becomes two TCP connections with two different owners. The client pool only ever sees the near one.

This is easy to get backwards, because testing a proxy with `curl -p` exercises the `CONNECT` path — which does reuse connections perfectly well. It just isn't the path a plaintext `http://` client takes.

**2. `tailscaled`'s forward proxy pools two connections per host.**

The relevant code in `cmd/tailscaled/proxy.go` is short enough to quote:

```go
rp := &httputil.ReverseProxy{
	Director: func(r *http.Request) {}, // no change
	Transport: &http.Transport{
		DialContext: dialer,
	},
}
```

A `http.Transport` constructed as a struct literal takes Go's defaults for everything unset. The one that matters:

```go
const DefaultMaxIdleConnsPerHost = 2
```

So each gateway replica keeps **two** idle upstream connections per destination host. A third concurrent request dials a new one, and when it finishes it is closed rather than pooled.

At any real concurrency, that means nearly every request opens a fresh TCP connection across the 150 ms link, paying a handshake and TCP slow start it should not have paid.

## The difference, drawn

<div class="not-prose cr-fig"><svg viewBox="0 0 880 452" role="img" aria-label="Three network paths: a sidecar dialling the backend over one TCP stream; an HTTP proxy splitting each request into two legs with the far leg capped at two idle connections; and SOCKS5 relaying one stream end to end."><defs><marker id="cr-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker><marker id="cr-ar-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#bf3326"/></marker></defs><text x="98" y="26" text-anchor="middle" font-size="11" fill="currentColor" opacity=".55">app pod</text><text x="440" y="26" text-anchor="middle" font-size="11" fill="currentColor" opacity=".55">gateway replica</text><text x="782" y="26" text-anchor="middle" font-size="11" fill="currentColor" opacity=".55">backend</text><text x="10" y="62" font-size="13" font-weight="600" fill="currentColor">BEFORE — per-pod sidecar</text><rect x="22" y="76" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="98" y="99" text-anchor="middle" font-size="11.5" fill="currentColor">client pool</text><text x="98" y="115" text-anchor="middle" font-size="10.5" fill="currentColor" opacity=".6">+ tailscaled TUN</text><rect x="706" y="76" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="782" y="107" text-anchor="middle" font-size="11.5" fill="currentColor">:8000</text><line x1="174" y1="102" x2="700" y2="102" stroke="#12707f" stroke-width="2.4" marker-end="url(#cr-ar)" color="#12707f"/><text x="437" y="93" text-anchor="middle" font-size="11" fill="#12707f">one TCP stream — the client pool reuses it</text><text x="437" y="119" text-anchor="middle" font-size="11" fill="#12707f" opacity=".75">many requests per connection</text><text x="10" y="196" font-size="13" font-weight="600" fill="currentColor">HTTP PROXY — forward mode</text><rect x="22" y="210" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="98" y="233" text-anchor="middle" font-size="11.5" fill="currentColor">client pool</text><text x="98" y="249" text-anchor="middle" font-size="10.5" fill="currentColor" opacity=".6">keepalive N</text><rect x="364" y="210" width="152" height="52" rx="3" fill="none" stroke="#bf3326" stroke-width="1.4"/><text x="440" y="231" text-anchor="middle" font-size="11" fill="#bf3326">ReverseProxy</text><text x="440" y="247" text-anchor="middle" font-size="10.5" fill="#bf3326">MaxIdleConnsPerHost 2</text><rect x="706" y="210" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="782" y="241" text-anchor="middle" font-size="11.5" fill="currentColor">:8000</text><line x1="174" y1="236" x2="358" y2="236" stroke="#12707f" stroke-width="2.4" marker-end="url(#cr-ar)" color="#12707f"/><text x="266" y="227" text-anchor="middle" font-size="10.5" fill="#12707f">leg A — local</text><text x="266" y="254" text-anchor="middle" font-size="10.5" fill="#12707f" opacity=".75">~4 ms cold</text><line x1="516" y1="236" x2="700" y2="236" stroke="#bf3326" stroke-width="2.4" marker-end="url(#cr-ar-hot)"/><text x="608" y="227" text-anchor="middle" font-size="10.5" fill="#bf3326">leg B — remote</text><text x="608" y="254" text-anchor="middle" font-size="10.5" fill="#bf3326">150 ms + slow start</text><line x1="440" y1="270" x2="440" y2="288" stroke="currentColor" stroke-width="1" opacity=".35"/><text x="440" y="301" text-anchor="middle" font-size="10.5" fill="currentColor" opacity=".6">HTTP terminated and re-originated here</text><text x="10" y="356" font-size="13" font-weight="600" fill="currentColor">SOCKS5 — relay</text><rect x="22" y="370" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="98" y="393" text-anchor="middle" font-size="11.5" fill="currentColor">client pool</text><text x="98" y="409" text-anchor="middle" font-size="10.5" fill="currentColor" opacity=".6">keepalive N</text><rect x="364" y="370" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2" stroke-dasharray="4 3" opacity=".65"/><text x="440" y="391" text-anchor="middle" font-size="11" fill="currentColor" opacity=".7">socks5.Server</text><text x="440" y="407" text-anchor="middle" font-size="10.5" fill="currentColor" opacity=".7">relays 1:1</text><rect x="706" y="370" width="152" height="52" rx="3" fill="none" stroke="currentColor" stroke-width="1.2"/><text x="782" y="401" text-anchor="middle" font-size="11.5" fill="currentColor">:8000</text><line x1="174" y1="396" x2="700" y2="396" stroke="#12707f" stroke-width="2.4" marker-end="url(#cr-ar)" color="#12707f"/><text x="437" y="437" text-anchor="middle" font-size="11" fill="#12707f">one TCP stream again — the client pool governs reuse</text></svg><p class="cr-cap">The gateway is not the problem; the termination is. Under SOCKS5 the gateway still carries every byte, but it relays the client's stream instead of ending it and dialling its own.</p></div>

## Watch it happen

Both lanes get the same request stream. The only difference is who owns the connection crossing the slow link. Push concurrency past two and the HTTP proxy lane stops reusing anything.

<div class="not-prose cr-sim"><div class="cr-head"><div class="cr-ctl"><label>Concurrent<input type="range" id="crConc" min="1" max="10" step="1" value="6"><output id="crConcOut">6 in flight</output></label><button id="crPlay">Pause</button><button class="cr-ghost" id="crReset">Reset</button></div></div><div class="cr-lanes"><div class="cr-lane"><div class="cr-name">HTTP proxy <span class="cr-tag cr-bad">forward mode</span></div><p class="cr-sub">Gateway owns the far leg and pools two idle connections per host.</p><div class="cr-tracks" id="crTracksA"><div class="cr-band"></div><div class="cr-bandlab">remote leg</div></div><div class="cr-read"><div><b id="crReqA">0</b><span>requests</span></div><div><b id="crDialA">0</b><span>dials</span></div><div><b id="crRatioA" class="cr-hotv">—</b><span>req / conn</span></div></div></div><div class="cr-lane"><div class="cr-name">SOCKS5 <span class="cr-tag cr-good">relay</span></div><p class="cr-sub">Client owns the stream end to end; its own pool does the reuse.</p><div class="cr-tracks" id="crTracksB"><div class="cr-band"></div><div class="cr-bandlab">remote leg</div></div><div class="cr-read"><div><b id="crReqB">0</b><span>requests</span></div><div><b id="crDialB">0</b><span>dials</span></div><div><b id="crRatioB" class="cr-coolv">—</b><span>req / conn</span></div></div></div></div></div>

Red is the handshake and slow start on a freshly dialled connection. The ratio on the left converges on ~1.0 — which is exactly the symptom that showed up in the backend proxy's `downstream_rq_total / downstream_cx_total`.

Measured on a real link: the same large POST took **~1000 ms** on a fresh connection against **~200 ms** on a reused one. Around 800 ms of that is TCP slow start. Slow start is per-connection, so it only becomes visible when connections stop being reused.

## Why SOCKS5 fixes it

SOCKS5 is not a smarter HTTP proxy. It is not an HTTP proxy at all — it negotiates a destination, then relays bytes:

```go
ss := &socks5.Server{
	Logf:   logger.WithPrefix(logf, "socks5: "),
	Dialer: dialer.UserDial,
}
```

One client TCP stream maps 1:1 onto one backend TCP stream. The proxy never parses or terminates HTTP, so keep-alive is negotiated between the client and the backend, and the client's pool is the only pool in the path.

In httpx that means:

```python
pool = client._transport_for_url(url)._pool   # AsyncSOCKSProxy
pool.create_connection(origin)                # AsyncSocks5Connection
```

`AsyncSOCKSProxy` keys its pool on the *target* origin, not the proxy, so `max_keepalive_connections` and `keepalive_expiry` apply per destination, as you would want.

Two practical notes:

- It needs an extra dependency (`httpx[socks]`, which pulls `socksio`). httpx raises `ImportError` at *client construction* against a `socks5://` proxy without it — so the dependency has to ship before the config flips.
- Setting `HTTP_PROXY=socks5://…` as an ambient env var affects every library in the process. `requests` needs PySocks for SOCKS and will raise `InvalidSchema` without it. Passing `proxy=` explicitly to the one client that needs it is safer than overloading the environment.

## The second-order bug: `keepalive_expiry`

Once the client owns the connection again, a setting that was previously irrelevant starts to matter.

httpx defaults `keepalive_expiry` to **5 seconds**. Passing an explicit `httpx.Limits(...)` without naming it inherits that default silently:

```python
# 5s expiry, whether you meant it or not
limits = httpx.Limits(max_connections=2000, max_keepalive_connections=70)

# what you probably want for a low-rate, high-RTT upstream
limits = httpx.Limits(max_connections=2000, max_keepalive_connections=70,
                      keepalive_expiry=300.0)
```

Whether 5 s is enough depends on the gap between requests **per client instance, per destination** — not on aggregate throughput. A service handling thousands of requests per second can still have each individual pod sitting idle for a minute at a time, if it is scaled wide enough.

For roughly Poisson arrivals, the share of requests landing on a cold connection is `exp(-T / gap)`:

<div class="not-prose cr-calc"><div class="cr-head"><div class="cr-ctl"><label>keepalive_expiry<input type="range" id="crExp" min="5" max="900" step="5" value="300"><output id="crExpOut">300 s</output></label><button class="cr-ghost" id="crP1">httpx default</button><button class="cr-ghost" id="crP2">300 s</button></div></div><div class="cr-calcbody" id="crCalcBody"></div><p class="cr-legend"><span><i class="cr-sw cr-sw-hot"></i>cold — redial, handshake, slow start</span><span><i class="cr-sw cr-sw-cool"></i>warm — reused</span></p></div>

Note what the third row shows: past a certain sparsity, no timeout saves you. A client seeing one request every ~9 minutes for a destination will be cold essentially always. That is a capacity-shape problem — too many instances for the traffic — not a timeout problem.

## Takeaways

- **`http://` through an HTTP proxy is not tunnelled.** The proxy terminates and re-originates. Your client's pool stops at the proxy, and whatever pooling happens past it is the proxy's business, not yours.
- **Test the path your client actually takes.** A `curl -p` test exercises `CONNECT` and will look healthy while the real traffic churns connections.
- **Go's `http.Transport` defaults are conservative.** `DefaultMaxIdleConnsPerHost = 2` is fine for a browser-shaped workload and badly wrong for a shared egress proxy. Any struct literal that omits it inherits it.
- **SOCKS5 is the right tool when you want the client to keep owning its connection.** It is lower-level than an HTTP proxy, and here that is precisely the advantage.
- **`keepalive_expiry` is sized by the per-instance idle gap**, not by request duration or aggregate rate.
- **Connection reuse is invisible until it stops.** Handshake and slow-start costs are per-connection; a change that quietly ends reuse reads as "the network got slower".

<style>
.cr-fig, .cr-sim, .cr-calc { --cr-hot:#bf3326; --cr-cool:#12707f; --cr-warn:#9a6510; --cr-line:#d8dede; --cr-bg:#fafbfb; --cr-sub:#64757a; margin:2rem 0; }
.dark .cr-fig, .dark .cr-sim, .dark .cr-calc { --cr-hot:#ff7a68; --cr-cool:#48c4d4; --cr-warn:#d9a441; --cr-line:#2a373b; --cr-bg:#111819; --cr-sub:#8b9ca0; }
.cr-fig { overflow-x:auto; }
.cr-fig svg { max-width:100%; height:auto; display:block; min-width:660px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.cr-cap { font-size:.82rem; color:var(--cr-sub); margin:.9rem 0 0; padding-left:.8rem; border-left:2px solid var(--cr-line); }
.cr-sim, .cr-calc { border:1px solid var(--cr-line); border-radius:.5rem; overflow:hidden; background:var(--cr-bg); }
.cr-head { padding:.85rem 1rem; border-bottom:1px solid var(--cr-line); }
.cr-ctl { display:flex; flex-wrap:wrap; gap:1rem; align-items:center; }
.cr-ctl label { display:flex; flex-direction:column; gap:.3rem; font-size:.68rem; letter-spacing:.08em; text-transform:uppercase; color:var(--cr-sub); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.cr-ctl output { font-size:.85rem; color:inherit; text-transform:none; letter-spacing:0; font-variant-numeric:tabular-nums; }
.cr-ctl input[type=range] { width:9rem; accent-color:var(--cr-cool); }
.cr-sim button, .cr-calc button { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; padding:.5rem .85rem; border-radius:.25rem; border:1px solid transparent; background:#1f2937; color:#f9fafb; cursor:pointer; }
.dark .cr-sim button, .dark .cr-calc button { background:#e5e7eb; color:#111827; }
.cr-sim button.cr-ghost, .cr-calc button.cr-ghost { background:transparent; color:inherit; border-color:var(--cr-line); }
.cr-lanes { display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--cr-line); }
@media (max-width:700px){ .cr-lanes { grid-template-columns:1fr; } }
.cr-lane { background:var(--cr-bg); padding:1rem; }
.cr-name { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; display:flex; gap:.5rem; align-items:baseline; flex-wrap:wrap; }
.cr-tag { font-size:.6rem; letter-spacing:.08em; text-transform:uppercase; padding:.12rem .4rem; border-radius:.2rem; }
.cr-bad { background:rgba(191,51,38,.12); color:var(--cr-hot); }
.cr-good { background:rgba(18,112,127,.12); color:var(--cr-cool); }
.cr-sub { font-size:.76rem; color:var(--cr-sub); margin:.5rem 0 .9rem; min-height:2.4em; }
.cr-tracks { position:relative; height:176px; border:1px solid var(--cr-line); border-radius:.25rem; overflow:hidden; }
.cr-line { position:absolute; left:0; right:0; height:1px; background:var(--cr-line); }
.cr-bar { position:absolute; height:9px; border-radius:1px; left:6px; background:var(--cr-cool); opacity:.9; }
.cr-bar i { position:absolute; left:0; top:0; bottom:0; background:var(--cr-hot); border-radius:1px 0 0 1px; }
.cr-band { position:absolute; top:0; bottom:0; right:0; width:38%; background:rgba(191,51,38,.07); border-left:1px dashed var(--cr-line); }
.cr-bandlab { position:absolute; top:4px; right:8px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.6rem; letter-spacing:.06em; color:var(--cr-sub); }
.cr-read { display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; margin-top:.9rem; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.cr-read b { display:block; font-size:1.25rem; font-weight:500; font-variant-numeric:tabular-nums; }
.cr-read span { font-size:.6rem; letter-spacing:.07em; text-transform:uppercase; color:var(--cr-sub); }
.cr-hotv { color:var(--cr-hot); } .cr-coolv { color:var(--cr-cool); }
.cr-calcbody { padding:1rem; }
.cr-dest { display:grid; grid-template-columns:11rem 1fr 6rem; gap:.9rem; align-items:center; margin-bottom:.9rem; }
@media (max-width:560px){ .cr-dest { grid-template-columns:1fr; gap:.25rem; } }
.cr-dname { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.8rem; }
.cr-dname small { display:block; color:var(--cr-sub); font-size:.68rem; }
.cr-meter { position:relative; height:22px; background:rgba(18,112,127,.12); border-radius:.15rem; overflow:hidden; }
.cr-meter i { position:absolute; inset:0 auto 0 0; background:var(--cr-hot); opacity:.85; transition:width .18s ease-out; }
.cr-dval { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem; text-align:right; font-variant-numeric:tabular-nums; }
.cr-legend { display:flex; gap:1.2rem; flex-wrap:wrap; font-size:.72rem; color:var(--cr-sub); padding:0 1rem 1rem; margin:0; }
.cr-sw { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:.35rem; }
.cr-sw-hot { background:var(--cr-hot); } .cr-sw-cool { background:var(--cr-cool); opacity:.35; }
@media (prefers-reduced-motion:reduce){ .cr-bar { transition:none !important; } }
</style>

<script>
(function(){
  "use strict";
  var TRACKS=10, ROW=17, TOP=6, DUR=1500, COLD=0.46, TICK=330;
  function Lane(id, maxIdle){
    this.el=document.getElementById(id); this.maxIdle=maxIdle;
    this.idle=0; this.busy=0; this.requests=0; this.dials=0; this.free=[];
    for(var i=0;i<TRACKS;i++){ var l=document.createElement("div"); l.className="cr-line";
      l.style.top=(TOP+i*ROW+ROW-1)+"px"; this.el.appendChild(l); this.free.push(i); }
  }
  Lane.prototype.send=function(animate){
    var reused=this.idle>0; if(reused){this.idle--;} else {this.dials++;}
    this.busy++; this.requests++;
    var self=this;
    var done=function(){ self.busy--; if(self.idle<self.maxIdle) self.idle++; };
    if(!animate){ done(); return; }
    var track=this.free.length?this.free.shift():Math.floor(Math.random()*TRACKS);
    var bar=document.createElement("div"); bar.className="cr-bar";
    bar.style.top=(TOP+track*ROW+3)+"px"; bar.style.width="0%";
    if(!reused){ var c=document.createElement("i"); c.style.width=(COLD*100)+"%"; bar.appendChild(c); }
    this.el.appendChild(bar);
    requestAnimationFrame(function(){ bar.style.transition="width "+DUR+"ms linear"; bar.style.width="calc(100% - 12px)"; });
    setTimeout(function(){
      bar.style.transition="opacity 220ms ease-out"; bar.style.opacity="0";
      setTimeout(function(){ if(bar.parentNode) bar.parentNode.removeChild(bar); self.free.push(track); },220);
      done();
    }, DUR);
  };
  Lane.prototype.render=function(r,d,x){
    r.textContent=this.requests; d.textContent=this.dials;
    x.textContent=this.dials?(this.requests/this.dials).toFixed(2):"—";
  };
  var conc=document.getElementById("crConc"), concOut=document.getElementById("crConcOut"),
      play=document.getElementById("crPlay"), reset=document.getElementById("crReset"),
      reqA=document.getElementById("crReqA"), dialA=document.getElementById("crDialA"), ratA=document.getElementById("crRatioA"),
      reqB=document.getElementById("crReqB"), dialB=document.getElementById("crDialB"), ratB=document.getElementById("crRatioB");
  if(!conc) return;
  var A,B,timer=null,running=true;
  function clear(){ ["crTracksA","crTracksB"].forEach(function(id){
    var el=document.getElementById(id);
    Array.prototype.slice.call(el.querySelectorAll(".cr-bar,.cr-line")).forEach(function(n){ n.remove(); }); }); }
  function build(){ clear(); A=new Lane("crTracksA",2); B=new Lane("crTracksB",70); }
  function warm(n){ for(var i=0;i<n;i++){ var k=parseInt(conc.value,10);
    for(var j=0;j<k;j++){ A.send(false); B.send(false); }
    A.idle=Math.min(A.idle,2); B.idle=Math.min(B.idle,70); } }
  function tick(){ var f=parseInt(conc.value,10);
    if(A.busy<f) A.send(true); if(B.busy<f) B.send(true);
    A.render(reqA,dialA,ratA); B.render(reqB,dialB,ratB); }
  function start(){ if(timer) clearInterval(timer); timer=setInterval(tick,TICK); }
  function stop(){ if(timer){ clearInterval(timer); timer=null; } }
  conc.addEventListener("input",function(){ concOut.textContent=conc.value+" in flight"; });
  play.addEventListener("click",function(){ running=!running; play.textContent=running?"Pause":"Play"; if(running) start(); else stop(); });
  reset.addEventListener("click",function(){ stop(); build(); warm(4); A.render(reqA,dialA,ratA); B.render(reqB,dialB,ratB); if(running) start(); });
  build(); warm(4); A.render(reqA,dialA,ratA); B.render(reqB,dialB,ratB);
  var reduce=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if(reduce){ running=false; play.textContent="Play"; } else { start(); }

  var DESTS=[{n:"busy destination",g:14,s:"~1 request every 14 s per instance"},
             {n:"quiet destination",g:53,s:"~1 request every 53 s per instance"},
             {n:"very sparse",g:526,s:"~1 request every 9 min per instance"}];
  var body=document.getElementById("crCalcBody"), exp=document.getElementById("crExp"), expOut=document.getElementById("crExpOut");
  if(!body) return;
  DESTS.forEach(function(d){
    var row=document.createElement("div"); row.className="cr-dest";
    row.innerHTML='<div class="cr-dname">'+d.n+'<small>'+d.s+'</small></div>'+
                  '<div class="cr-meter"><i></i></div><div class="cr-dval"></div>';
    body.appendChild(row); d.bar=row.querySelector(".cr-meter i"); d.val=row.querySelector(".cr-dval");
  });
  function calc(){
    var T=parseInt(exp.value,10); expOut.textContent=T+" s";
    DESTS.forEach(function(d){
      var cold=Math.exp(-T/d.g), pct=cold*100;
      d.bar.style.width=pct.toFixed(1)+"%";
      d.val.textContent=(pct<0.1?pct.toFixed(2):pct.toFixed(1))+"% cold";
      d.val.style.color=pct>40?"var(--cr-hot)":(pct>5?"var(--cr-warn)":"var(--cr-cool)");
    });
  }
  exp.addEventListener("input",calc);
  document.getElementById("crP1").addEventListener("click",function(){ exp.value=5; calc(); });
  document.getElementById("crP2").addEventListener("click",function(){ exp.value=300; calc(); });
  calc();
})();
</script>
