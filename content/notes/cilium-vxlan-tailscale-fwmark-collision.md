---
title: "Why new Kubernetes connections disappeared between two nodes"
date: 2026-09-13T21:15:00+0800
tags: [kubernetes, cilium, tailscale, vxlan, networking, troubleshooting, nixos]
---

**A new connection from one Kubernetes Pod to another node kept timing out, even though older connections between the same nodes still worked.** The bug turned out to be two networking tools accidentally using the same internal label for different purposes.

The short version:

- Cilium wrapped the Pod's packet so it could travel to the other node.
- Cilium attached a numeric label to that wrapped packet.
- Tailscale mistook part of that label for one of its own labels.
- Linux therefore sent the packet toward the normal LAN router instead of through Tailscale.
- A narrow routing rule made Cilium's wrapped packets take the Tailscale path before the conflicting rule could see them.

## A small networking glossary

- **Pod:** a running Kubernetes workload. Each Pod gets its own cluster-internal IP address.
- **Node:** the machine that runs Pods. This cluster had two nodes.
- **Cilium:** the component that gives Pods network connectivity and applies network policy.
- **VXLAN:** a way to carry a Pod packet inside another packet. Think of putting a letter inside a courier envelope. The inner letter is the Pod traffic; the outer envelope is addressed between nodes.
- **Tailscale:** the encrypted private network connecting the two machines.
- **`tailscale0`:** the Linux network interface used to send packets into Tailscale.
- **TCP:** the protocol applications commonly use for reliable connections. A new TCP connection starts with a `SYN` packet.
- **UDP:** a simpler transport used here for the outer VXLAN envelope. Cilium sends these envelopes to UDP port 8472.
- **DNS:** the system that turns a service name into an IP address.
- **ClusterIP Service:** a stable virtual Kubernetes IP that forwards connections to one or more Pods.
- **Route:** Linux's answer to “which interface should carry this packet?”
- **Policy routing:** extra routing rules that can choose a route using more than the destination address.
- **Packet mark:** an internal number attached to a packet while it is inside the Linux kernel. It is metadata, not bytes sent to the remote application. Routing rules can inspect it.
- **MTU:** the largest packet an interface or route can carry without further splitting.

Two more terms appear in networking tools:

- The **overlay** is the virtual Pod network created by Cilium.
- The **underlay** is the real path carrying that virtual network. Here, the underlay was Tailscale.

## How a cross-node Pod packet should travel

Suppose Pod A runs on node 1 and Pod B runs on node 2:

<figure class="not-prose" style="margin:2rem 0">
<svg viewBox="40 0 640 680" role="img" aria-labelledby="packet-flow-title packet-flow-desc" style="width:100%;height:auto;display:block;overflow:visible">
  <title id="packet-flow-title">A packet travelling from Pod A to Pod B on another node</title>
  <desc id="packet-flow-desc">An animated packet moves from Pod A through Cilium, Linux routing, the encrypted Tailscale tunnel, and Cilium on the second node before reaching Pod B.</desc>
  <style>
    .pf-stage { fill: currentColor; fill-opacity: .04; stroke: currentColor; stroke-opacity: .28; stroke-width: 1.5; }
    .pf-arrow { stroke: currentColor; stroke-opacity: .28; stroke-width: 2; }
    .pf-packet { animation: pf-travel 8s ease-in-out infinite; transform-origin: center; }
    .pf-pulse { animation: pf-pulse 8s ease-in-out infinite; }
    @keyframes pf-travel {
      0%, 8% { transform: translateY(0); }
      18%, 25% { transform: translateY(110px); }
      35%, 42% { transform: translateY(220px); }
      52%, 59% { transform: translateY(330px); }
      69%, 76% { transform: translateY(440px); }
      88%, 100% { transform: translateY(550px); }
    }
    @keyframes pf-pulse {
      0%, 100% { opacity: .35; }
      45%, 55% { opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
      .pf-packet, .pf-pulse { animation: none; }
    }
  </style>
  <defs>
    <marker id="pf-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L7,3 z" fill="currentColor" opacity=".4"/>
    </marker>
  </defs>
  <g fill="currentColor" font-family="ui-sans-serif, system-ui, sans-serif">
    <g text-anchor="middle">
      <rect class="pf-stage" x="80" y="20" width="450" height="72" rx="8"/>
      <text x="305" y="50" font-size="20" font-weight="650">Pod A</text>
      <text x="305" y="74" font-size="16" opacity=".65">creates a packet for Pod B</text>
      <rect class="pf-stage" x="80" y="130" width="450" height="72" rx="8"/>
      <text x="305" y="160" font-size="20" font-weight="650">Cilium on node 1</text>
      <text x="305" y="184" font-size="16" opacity=".65">wraps it in a VXLAN/UDP envelope</text>
      <rect class="pf-stage" x="80" y="240" width="450" height="72" rx="8"/>
      <text x="305" y="270" font-size="20" font-weight="650">Linux routing</text>
      <text x="305" y="294" font-size="16" opacity=".65">chooses the outgoing interface</text>
      <rect class="pf-stage pf-pulse" x="80" y="350" width="450" height="72" rx="8" stroke="#2aa198"/>
      <text x="305" y="380" font-size="20" font-weight="650">Tailscale encrypted tunnel</text>
      <text x="305" y="404" font-size="16" opacity=".65">carries it securely to node 2</text>
      <rect class="pf-stage" x="80" y="460" width="450" height="72" rx="8"/>
      <text x="305" y="490" font-size="20" font-weight="650">Cilium on node 2</text>
      <text x="305" y="514" font-size="16" opacity=".65">opens the VXLAN envelope</text>
      <rect class="pf-stage" x="80" y="570" width="450" height="72" rx="8"/>
      <text x="305" y="600" font-size="20" font-weight="650">Pod B</text>
      <text x="305" y="624" font-size="16" opacity=".65">receives the original packet</text>
    </g>
    <g class="pf-arrow" marker-end="url(#pf-arrowhead)">
      <line x1="305" y1="94" x2="305" y2="122"/>
      <line x1="305" y1="204" x2="305" y2="232"/>
      <line x1="305" y1="314" x2="305" y2="342"/>
      <line x1="305" y1="424" x2="305" y2="452"/>
      <line x1="305" y1="534" x2="305" y2="562"/>
    </g>
    <line x1="610" y1="57" x2="610" y2="607" stroke="currentColor" stroke-opacity=".12" stroke-width="4" stroke-linecap="round"/>
    <g class="pf-packet">
      <rect x="570" y="37" width="80" height="40" rx="20" fill="#268bd2"/>
      <text x="610" y="62" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">packet</text>
    </g>
    <text x="610" y="662" text-anchor="middle" font-size="15" opacity=".5">repeats</text>
  </g>
</svg>
<figcaption style="font-size:0.8rem;opacity:0.65;text-align:center;margin-top:0.5rem">The application sees one Pod-to-Pod connection. Cilium and Tailscale handle the extra transport layers underneath it.</figcaption>
</figure>

Cilium uses UDP destination port **8472** for the outer VXLAN envelope. The application does not know about VXLAN or Tailscale; it only sees the original inner packet.

### What “wrapping” adds to the packet

Each outer layer supplies information needed by the layer below it. The animation highlights the layers from the original application data outward:

<figure class="not-prose" style="margin:2rem 0">
<svg viewBox="0 0 720 470" role="img" aria-labelledby="encap-title encap-desc" style="width:100%;height:auto;display:block;overflow:visible">
  <title id="encap-title">Layers added around application data for cross-node delivery</title>
  <desc id="encap-desc">Nested boxes show application data inside TCP, the inner Pod IP packet, inner Ethernet, VXLAN, UDP, and the outer node IP packet. The layers highlight from inside to outside.</desc>
  <style>
    .ec-layer { fill-opacity: .08; stroke-width: 1.5; animation: ec-highlight 7s ease-in-out infinite; }
    .ec-1 { animation-delay: 0s; }
    .ec-2 { animation-delay: .6s; }
    .ec-3 { animation-delay: 1.2s; }
    .ec-4 { animation-delay: 1.8s; }
    .ec-5 { animation-delay: 2.4s; }
    .ec-6 { animation-delay: 3s; }
    .ec-7 { animation-delay: 3.6s; }
    @keyframes ec-highlight {
      0%, 9%, 28%, 100% { fill-opacity: .08; stroke-width: 1.5; }
      14%, 22% { fill-opacity: .32; stroke-width: 3; }
    }
    @media (prefers-reduced-motion: reduce) {
      .ec-layer { animation: none; fill-opacity: .14; }
    }
  </style>
  <g font-family="ui-sans-serif, system-ui, sans-serif">
    <rect class="ec-layer ec-7" x="30" y="25" width="660" height="370" rx="14" fill="#6c71c4" stroke="#6c71c4"/>
    <text x="48" y="52" font-size="13" font-weight="700" fill="currentColor">Outer node IP</text>
    <text x="672" y="52" text-anchor="end" font-size="11" fill="currentColor" opacity=".6">which node?</text>
    <rect class="ec-layer ec-6" x="65" y="65" width="590" height="295" rx="12" fill="#268bd2" stroke="#268bd2"/>
    <text x="83" y="91" font-size="13" font-weight="700" fill="currentColor">UDP</text>
    <text x="637" y="91" text-anchor="end" font-size="11" fill="currentColor" opacity=".6">port 8472</text>
    <rect class="ec-layer ec-5" x="100" y="105" width="520" height="220" rx="10" fill="#2aa198" stroke="#2aa198"/>
    <text x="118" y="131" font-size="13" font-weight="700" fill="currentColor">VXLAN</text>
    <text x="602" y="131" text-anchor="end" font-size="11" fill="currentColor" opacity=".6">this carries a virtual network</text>
    <rect class="ec-layer ec-4" x="135" y="145" width="450" height="145" rx="8" fill="#859900" stroke="#859900"/>
    <text x="153" y="171" font-size="13" font-weight="700" fill="currentColor">Inner Ethernet</text>
    <rect class="ec-layer ec-3" x="170" y="185" width="380" height="70" rx="7" fill="#b58900" stroke="#b58900"/>
    <text x="188" y="211" font-size="13" font-weight="700" fill="currentColor">Inner Pod IP</text>
    <rect class="ec-layer ec-2" x="280" y="202" width="255" height="38" rx="6" fill="#cb4b16" stroke="#cb4b16"/>
    <text x="298" y="226" font-size="12" font-weight="700" fill="currentColor">TCP</text>
    <rect class="ec-layer ec-1" x="365" y="210" width="150" height="22" rx="5" fill="#dc322f" stroke="#dc322f"/>
    <text x="440" y="226" text-anchor="middle" font-size="11" font-weight="700" fill="currentColor">application data</text>
    <text x="360" y="430" text-anchor="middle" font-size="12" fill="currentColor" opacity=".65">sender: add layers from inside → outside · receiver: remove them outside → inside</text>
  </g>
</svg>
<figcaption style="font-size:0.8rem;opacity:0.65;text-align:center;margin-top:0.5rem">The original data remains at the center. Cross-node delivery adds addressing and transport information around it.</figcaption>
</figure>

## What actually happened

The journey broke at **Linux routing**, after Cilium had created the outer envelope:

<figure class="not-prose" style="margin:2rem 0">
<svg viewBox="0 0 720 450" role="img" aria-labelledby="route-choice-title route-choice-desc" style="width:100%;height:auto;display:block;overflow:visible">
  <title id="route-choice-title">The wrong route before the fix and the correct route after it</title>
  <desc id="route-choice-desc">A VXLAN packet reaches Linux routing. Before the fix, an orange packet follows the physical LAN route and is lost. After the fix, a green packet follows Tailscale table 52 to tailscale0 and reaches node 2.</desc>
  <style>
    .rc-box { fill: currentColor; fill-opacity: .04; stroke: currentColor; stroke-opacity: .3; stroke-width: 1.5; }
    .rc-path { fill: none; stroke-width: 3; stroke-linecap: round; }
    .rc-moving-before { offset-path: path("M 360 88 L 360 175 L 555 295"); animation: rc-move 6s ease-in-out infinite; }
    .rc-moving-after { offset-path: path("M 360 88 L 360 175 L 165 295"); animation: rc-move 6s 3s ease-in-out infinite; opacity: 0; }
    @keyframes rc-move {
      0% { offset-distance: 0%; opacity: 0; }
      8%, 72% { opacity: 1; }
      80%, 100% { offset-distance: 100%; opacity: 0; }
    }
    @media (prefers-reduced-motion: reduce) {
      .rc-moving-before, .rc-moving-after { animation: none; opacity: 0; }
    }
  </style>
  <defs>
    <marker id="rc-good-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L7,3 z" fill="#2aa198"/>
    </marker>
    <marker id="rc-bad-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L7,3 z" fill="#cb4b16"/>
    </marker>
  </defs>
  <g fill="currentColor" font-family="ui-sans-serif, system-ui, sans-serif">
    <rect class="rc-box" x="215" y="20" width="290" height="68" rx="8"/>
    <text x="360" y="49" text-anchor="middle" font-size="16" font-weight="650">Cilium creates VXLAN packet</text>
    <text x="360" y="72" text-anchor="middle" font-size="12" opacity=".62">packet mark: 0x1d080400</text>
    <line x1="360" y1="88" x2="360" y2="126" stroke="currentColor" stroke-opacity=".3" stroke-width="2"/>
    <rect class="rc-box" x="215" y="126" width="290" height="68" rx="8"/>
    <text x="360" y="155" text-anchor="middle" font-size="16" font-weight="650">Linux policy routing</text>
    <text x="360" y="178" text-anchor="middle" font-size="12" opacity=".62">reads the packet mark</text>
    <path class="rc-path" d="M350 194 C310 225 225 245 165 285" stroke="#2aa198" marker-end="url(#rc-good-arrow)"/>
    <path class="rc-path" d="M370 194 C410 225 495 245 555 285" stroke="#cb4b16" marker-end="url(#rc-bad-arrow)"/>
    <rect x="40" y="292" width="250" height="105" rx="9" fill="#2aa198" fill-opacity=".11" stroke="#2aa198" stroke-width="2"/>
    <text x="165" y="322" text-anchor="middle" font-size="14" font-weight="700" fill="#2aa198">AFTER FIX · CORRECT</text>
    <text x="165" y="350" text-anchor="middle" font-size="14">Tailscale table 52</text>
    <text x="165" y="375" text-anchor="middle" font-size="12" opacity=".65">tailscale0 → node 2</text>
    <rect x="430" y="292" width="250" height="105" rx="9" fill="#cb4b16" fill-opacity=".11" stroke="#cb4b16" stroke-width="2"/>
    <text x="555" y="322" text-anchor="middle" font-size="14" font-weight="700" fill="#cb4b16">BEFORE FIX · WRONG</text>
    <text x="555" y="350" text-anchor="middle" font-size="14">Normal routing table</text>
    <text x="555" y="375" text-anchor="middle" font-size="12" opacity=".65">physical LAN gateway → lost</text>
    <g class="rc-moving-before">
      <circle r="10" fill="#cb4b16"/>
      <circle r="4" fill="#ffffff"/>
    </g>
    <g class="rc-moving-after">
      <circle r="10" fill="#2aa198"/>
      <circle r="4" fill="#ffffff"/>
    </g>
    <g font-size="11" opacity=".58">
      <circle cx="72" cy="427" r="6" fill="#2aa198"/>
      <text x="85" y="431">corrected packet</text>
      <circle cx="480" cy="427" r="6" fill="#cb4b16"/>
      <text x="493" y="431">misrouted packet</text>
    </g>
  </g>
</svg>
<figcaption style="font-size:0.8rem;opacity:0.65;text-align:center;margin-top:0.5rem">The packet contents did not change. The fix changed which routing rule handled the VXLAN envelope first.</figcaption>
</figure>

This explains the confusing evidence: Cilium said it had sent the packet “to overlay,” but no matching packet appeared on `tailscale0`. Cilium had completed its part; Linux chose the wrong exit afterward.

## Why Linux chose the wrong route

Cilium and Tailscale both use packet marks. This is normally fine, but packet marks are one shared 32-bit number. The two tools must avoid assigning conflicting meaning to the same bits.

Cilium put two things in the mark on this VXLAN packet:

- the Pod's Cilium security identity;
- a value meaning “this is overlay traffic.”

The failing Cilium identity was decimal **7432**, or hexadecimal **`0x1d08`**. The final mark was:

```text
Cilium identity:       0x1d08
Outer VXLAN mark:      0x1d080400
```

Tailscale had a policy rule that looked only at part of the mark:

```text
fwmark 0x80000/0xff0000 lookup main
```

Read this as: “If these selected bits equal `0x80000`, use the normal Linux routing table.” The mask after `/` selects which bits matter. Apply that mask to Cilium's mark:

```text
0x1d080400 & 0x00ff0000 = 0x00080000
```

It accidentally matched. Tailscale saw the `08` inside Cilium's identity and treated the packet as traffic that should bypass Tailscale's routing table.

The important point is not the hexadecimal arithmetic. It is this:

> Cilium attached a label for one reason. Tailscale read part of the same label and gave it a different meaning.

Cilium assigns identities dynamically. This was not permanently tied to one application: any endpoint identity whose low byte was `0x08` could hit the same failure.

## Packet size constraints

The three MTU values were intentionally different:

```text
remote Pod route  1180
Cilium links      1230
tailscale0        1280
```

Why leave space? Wrapping the inner Pod packet adds an outer IP header, UDP header, VXLAN header, and Ethernet header. The smaller inner limit leaves room for that envelope. Tailscale's 1280-byte interface limit then accounts for its own encrypted transport.

The routing fix preserved all three values. This mattered because reducing MTU had solved an earlier packet-fragmentation problem, but it could not solve a packet being sent through the wrong interface.

## Symptoms

- The CloudNativePG database controller could not establish a new connection to a PostgreSQL instance on the other node.
- Moving the controller out of the Pod network and onto the node's own network (`hostNetwork`) restored service, but only as a temporary recovery.
- Traffic sent by the node itself, rather than by a Pod, worked across nodes.
- Some already-established Pod connections worked.
- Cilium reported traffic at `to-overlay`.
- No corresponding UDP/8472 packet appeared on `tailscale0`.
- Lowering MTU had previously fixed fragment drops, but did not fix this new-flow failure.

In plain language, that mix of results said:

- the other machine and the Tailscale tunnel were reachable;
- Cilium decided to wrap the packet for cross-node delivery;
- something went wrong between wrapping it and sending it into Tailscale;
- Linux's connection tracking could preserve an older working path, so testing only an existing connection was misleading.

## Reproduce without the affected application

The first useful step was to remove CloudNativePG from the experiment.

Create ordinary Pods pinned to opposite nodes, run a simple TCP listener on one, and start a fresh connection from the other. Delete and recreate the source Pod between attempts so the test does not reuse Cilium endpoint state or Linux's memory of an older connection.

Test all four combinations:

1. core Pod → worker Pod IP;
2. worker Pod → core Pod IP;
3. core Pod → worker-backed ClusterIP Service;
4. worker Pod → core-backed ClusterIP Service.

Also run a control Pod with a different Cilium security identity. In this incident:

- the identity matching the failed application reproduced the failure;
- a fresh control identity succeeded;
- therefore the application and general cross-node MTU were not the discriminating variables.

## Trace from endpoint to wire

The goal was to follow one new TCP connection attempt through each layer. A TCP connection begins with a packet carrying the `SYN` flag, so that first SYN is a useful marker.

Use Cilium's monitor to confirm that the Pod packet reached the overlay path. At the same time, use `tcpdump` to watch for the outer VXLAN envelope:

```bash
# Cilium's logical datapath decision
kubectl -n kube-system exec ds/cilium -c cilium-agent -- \
  cilium-dbg monitor --type trace --type drop

# Expected encrypted underlay emission
sudo tcpdump -ni tailscale0 'udp port 8472'

# Check whether it escaped on the physical interface instead
sudo tcpdump -ni <physical-interface> 'udp port 8472'
```

Seeing `to-overlay` means Cilium decided to wrap the packet. It does **not** mean Linux sent the new outer packet through `tailscale0`.

The final command asks Linux: “Where would you send a UDP/8472 packet to this Tailscale peer if it had the exact mark Cilium produced?”

```bash
ip -4 rule show
ip route show table 52
ip route get <peer-tailscale-ip> \
  ipproto udp dport 8472 mark 0x1d080400
```

Before the fix, the exact marked lookup selected each node's physical LAN default route rather than Tailscale table 52.

## The durable fix

Add a higher-priority rule that is specific to Cilium VXLAN and the exact peer:

```bash
ip -4 rule add priority 5205 \
  to <peer-tailscale-ip>/32 \
  ipproto udp dport 8472 \
  lookup 52
```

Read the rule one line at a time:

- **priority 5205:** check this rule before Tailscale's conflicting rule at 5210. Linux checks lower numbers first.
- **to the peer `/32`:** match only the other node's exact Tailscale IP address. `/32` means one IPv4 address.
- **UDP destination port 8472:** match only Cilium's VXLAN envelopes.
- **lookup 52:** use the routing table Tailscale maintains, which sends the packet through `tailscale0`.

The result is: “Before considering the more general Tailscale mark rule, send Cilium's VXLAN packets for this node through Tailscale.”

The rule is deliberately narrow:

- one peer `/32`, not the whole tailnet;
- UDP only;
- destination port 8472 only;
- no mutation of Cilium or Tailscale marks;
- table 52 remains owned and populated by Tailscale.

Running the `ip rule add` command manually would fix the current machine, but the rule would disappear after rebuilding or replacing the host. The lasting implementation therefore put the same rule in the NixOS host configuration:

```nix
{ peerAddress }:
{ pkgs, ... }:
{
  systemd.services.cilium-tailscale-routing = {
    description = "Route Cilium VXLAN packets through the Tailscale underlay";
    wantedBy = [
      "multi-user.target"
      "tailscaled.service"
    ];
    partOf = [ "tailscaled.service" ];
    after = [ "tailscaled.service" ];
    before = [ "k3s.service" ];
    path = [ pkgs.iproute2 ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      while ip -4 rule del priority 5205 \
        to ${peerAddress}/32 ipproto udp dport 8472 lookup 52 \
        2>/dev/null; do :; done
      ip -4 rule add priority 5205 \
        to ${peerAddress}/32 ipproto udp dport 8472 lookup 52
    '';
    preStop = ''
      while ip -4 rule del priority 5205 \
        to ${peerAddress}/32 ipproto udp dport 8472 lookup 52 \
        2>/dev/null; do :; done
    '';
  };
}
```

You do not need to understand every Nix expression to understand the behavior:

- remove any old copy of this exact rule;
- add one fresh copy;
- start it during normal system activation;
- remove and reinstall it around a Tailscale restart;
- install it before Kubernetes starts.

The delete loop makes repeated activation safe and removes duplicates left by an interrupted attempt. `PartOf=tailscaled.service` plus the `wantedBy` relationship reinstalls the rule when Tailscale restarts.

### A lifecycle bug caught during rollout

The first version said only “start this when Tailscale starts.” During `nixos-rebuild test`, Tailscale was already running, so systemd did not start it again. The new routing service remained inactive and no rule went live.

Adding `multi-user.target` also said “start this as part of the normal running system.” That made configuration activation start the rule immediately, while retaining the Tailscale restart coupling. The automated check now verifies both the rule text and when the service starts.

This is why an automated configuration test should check when a service starts, not just the command it will eventually run.

## Verification

Do not qualify this fix with one `curl`. Check new state, established state, encapsulation, and the applications that exposed the problem.

### Routing and MTU

On both nodes:

```bash
ip -o link show tailscale0      # mtu 1280
ip -o link show cilium_host     # mtu 1230
ip -o link show cilium_vxlan    # mtu 1230
ip route show                   # remote Pod CIDR: mtu 1180
ip rule show                    # priority 5205 present

ip route get <peer-tailscale-ip> \
  ipproto udp dport 8472 mark 0x1d080400
# must resolve through tailscale0 and table 52
```

New Pod `eth0` interfaces also reported MTU 1230.

### Dataplane

- Newly recreated ordinary Pods established direct TCP both ways.
- ClusterIP Services worked both ways in repeated attempts.
- Three-second TCP transfers remained active and transferred about 30–35 MB each way.
- TLS 1.3 handshakes and multiple asymmetric application records passed both ways.
- DNS resolved both test Services from both nodes.
- Large ping packets passed 5/5 both ways. `ping -s 1152` creates an 1180-byte packet after adding the 28 bytes of IPv4 and ICMP headers, so this tested the route's size limit rather than only tiny packets.
- `tcpdump` on both `tailscale0` interfaces showed VXLAN packets moving in both directions, including large inner TCP segments, with zero kernel capture drops.
- Bounded Cilium drop monitoring showed no logical-fragment drops.
- Both Cilium agents reported cluster health **2/2**, including host and endpoint ICMP/HTTP.

### Application recovery

Only after the ordinary-Pod tests passed:

- Flux removed CloudNativePG's temporary settings that bypassed the normal Pod network.
- The controller returned to an ordinary Pod IP on the core node, Ready with zero restarts.
- The PostgreSQL cluster reported healthy and continuous archiving remained healthy.
- `pg_isready`, `pg_is_in_recovery() = false`, and a simple SQL expression passed.

Temporary listeners, capture Pods, identity probes, and the test namespace were removed after qualification.

## Takeaways

- **Internal packet labels are shared.** Two independent networking systems can accidentally assign different meanings to the same bits.
- **Follow the whole packet journey.** `to-overlay` means Cilium decided to wrap a packet; it does not prove Linux sent the wrapper through the intended interface.
- **Ask Linux about the real packet.** A basic route lookup can look correct while the packet's mark triggers another policy rule. Include its destination, protocol, port, and mark in the test lookup.
- **Reproduce with an ordinary Pod.** This separated the infrastructure defect from CloudNativePG immediately.
- **Test fresh and established connections.** Linux's memory of existing connections can make a broken new-connection path look healthy.
- **Keep the exception narrow.** Match the exact peers, protocol, and port instead of overriding Tailscale policy broadly.
- **Preserve declarative ownership.** NixOS owns the host rule; Flux owns removal of the Kubernetes workaround; neither depends on a live-only patch.
- **Test when a systemd service starts.** Correct command text is not enough if the service never runs during configuration activation.
