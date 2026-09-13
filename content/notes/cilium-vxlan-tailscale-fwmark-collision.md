---
title: "When a Cilium identity collided with Tailscale policy routing"
date: 2026-09-13T21:15:00+0800
tags: [kubernetes, cilium, tailscale, vxlan, networking, troubleshooting, nixos]
---

**A newly created Kubernetes Pod could not open a connection to a Pod on the other node, but established connections kept working.** The packet reached Cilium's overlay egress and then disappeared before `tailscale0`.

The cause was not CloudNativePG, VXLAN, or MTU. It was a bit-level collision between a Cilium security identity encoded in the packet mark and a Tailscale policy-routing mark.

This is the troubleshooting path and durable fix from [boxcompute/sandbox#435](https://github.com/boxcompute/sandbox/issues/435).

## The topology and constraints

- Two Kubernetes nodes communicate over Tailscale.
- Cilium uses VXLAN, UDP port 8472, between the node Tailscale addresses.
- `tailscale0` MTU is **1280**.
- Cilium endpoint and VXLAN MTU is **1230**.
- Cilium's route to the remote Pod CIDR has MTU **1180**.
- Host state is owned by NixOS; Kubernetes state is owned by Flux. An imperative live patch is not a fix.

The MTU hierarchy was intentional:

```text
remote Pod route  1180
Cilium links      1230
tailscale0        1280
```

The 50-byte steps reserve room for Cilium's outer IPv4, UDP, VXLAN, and inner Ethernet headers. Tailscale's own 1280-byte TUN contract accounts for its transport overhead.

## Symptoms

- The CloudNativePG controller could not establish a new connection to a PostgreSQL instance on the other node.
- Moving the controller to `hostNetwork` restored service, but only as a temporary recovery.
- Host-originated cross-node traffic worked.
- Some already-established Pod connections worked.
- Cilium reported traffic at `to-overlay`.
- No corresponding UDP/8472 packet appeared on `tailscale0`.
- Lowering MTU had previously fixed fragment drops, but did not fix this new-flow failure.

That mix of results matters. It says:

- the destination and underlay are reachable;
- Cilium selected the overlay path;
- the failure is after Cilium's endpoint egress decision but before emission on the expected underlay interface;
- conntrack can hide the bug, so testing only an existing connection is insufficient.

## Reproduce without the affected application

The first useful step was to remove CloudNativePG from the experiment.

Create ordinary Pods pinned to opposite nodes, run a TCP listener on one, and originate a fresh connection from the other. Delete and recreate the source Pod between attempts so the test does not reuse endpoint or conntrack state.

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

Observe the same new SYN at each layer:

```bash
# Cilium's logical datapath decision
kubectl -n kube-system exec ds/cilium -c cilium-agent -- \
  cilium-dbg monitor --type trace --type drop

# Expected encrypted underlay emission
sudo tcpdump -ni tailscale0 'udp port 8472'

# Check whether it escaped on the physical interface instead
sudo tcpdump -ni <physical-interface> 'udp port 8472'
```

Seeing `to-overlay` proves that Cilium selected encapsulation. It does **not** prove that Linux routed the resulting outer packet through `tailscale0`.

The next step is to inspect both the packet mark and policy routing:

```bash
ip -4 rule show
ip route show table 52
ip route get <peer-tailscale-ip> \
  ipproto udp dport 8472 mark 0x1d080400
```

Before the fix, the exact marked lookup selected each node's physical LAN default route rather than Tailscale table 52.

## The mark collision

Cilium's VXLAN path encoded two relevant values in the outer packet mark:

- source security identity in bits 16–31;
- overlay magic `0x0400` in the low bits.

The failing identity was decimal **7432**, or hexadecimal **`0x1d08`**:

```text
Cilium identity:       0x1d08
Outer VXLAN mark:      0x1d080400
```

Tailscale had this policy-routing bypass rule:

```text
fwmark 0x80000/0xff0000 lookup main
```

Apply its mask to Cilium's mark:

```text
0x1d080400 & 0x00ff0000 = 0x00080000
```

It matches.

Tailscale interpreted the low byte of Cilium's identity, `0x08`, as its own bypass mark and looked in the main routing table. The VXLAN packet then followed the physical default route instead of `tailscale0`.

The identity allocation is dynamic. This was not intrinsically a CloudNativePG identity: **any endpoint identity whose low byte is `0x08` could trigger the same failure.**

```text
Pod SYN
  ↓
Cilium endpoint policy
  ↓
VXLAN encapsulation + mark 0x1d080400
  ↓
Linux policy routing
  ├─ expected: Tailscale table 52 → tailscale0
  └─ actual:   mark collision → main table → physical default
```

## The durable fix

Add a higher-priority rule that is specific to Cilium VXLAN and the exact peer:

```bash
ip -4 rule add priority 5205 \
  to <peer-tailscale-ip>/32 \
  ipproto udp dport 8472 \
  lookup 52
```

Priority 5205 runs before Tailscale's bypass rule at 5210. The rule is deliberately narrow:

- one peer `/32`, not the whole tailnet;
- UDP only;
- destination port 8472 only;
- no mutation of Cilium or Tailscale marks;
- table 52 remains owned and populated by Tailscale.

The host configuration is declarative NixOS:

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

The delete loop makes activation idempotent and removes duplicates left by an interrupted attempt. `PartOf=tailscaled.service` plus the `wantedBy` relationship reinstalls the rule when Tailscale restarts.

### A lifecycle bug caught during rollout

The first version was wanted only by `tailscaled.service`. During `nixos-rebuild test`, Tailscale was already running, so its target was not started again and the new oneshot remained inactive. No routing rule went live.

Adding `multi-user.target` made configuration activation start the unit immediately, while retaining the Tailscale restart coupling. The flake regression check now asserts both the exact rules and activation target.

This is why a declarative unit test should check lifecycle wiring, not just generated command text.

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
- ICMP with `ping -s 1152` passed 5/5 both ways: 1152-byte payload + 28-byte IPv4/ICMP headers = the 1180-byte route boundary.
- `tcpdump` on both `tailscale0` interfaces showed bidirectional UDP/8472 VXLAN and inner 1128-byte TCP payload segments, with zero kernel capture drops.
- Bounded Cilium drop monitoring showed no logical-fragment drops.
- Both Cilium agents reported cluster health **2/2**, including host and endpoint ICMP/HTTP.

### Application recovery

Only after the ordinary-Pod tests passed:

- Flux removed CloudNativePG's temporary `hostNetwork` and `ClusterFirstWithHostNet` settings together.
- The controller returned to an ordinary Pod IP on the core node, Ready with zero restarts.
- The PostgreSQL cluster reported healthy and continuous archiving remained healthy.
- `pg_isready`, `pg_is_in_recovery() = false`, and a simple SQL expression passed.
- The Sandbox API was Available and healthy.
- A fresh authenticated, read-only API request returned HTTP 200 without creating a Sandbox.

Temporary listeners, capture Pods, identity probes, and the test namespace were removed after qualification.

## Git history

- [PR #436 — Fix Cilium VXLAN routing over Tailscale](https://github.com/boxcompute/sandbox/pull/436)
- [PR #437 — Start Cilium routing policy during activation](https://github.com/boxcompute/sandbox/pull/437)
- [PR #438 — Restore CNPG Pod networking](https://github.com/boxcompute/sandbox/pull/438)
- [ADR 0044](https://github.com/boxcompute/sandbox/blob/main/docs/adr/0044-separate-core-and-sandbox-cluster-nodes.md)

## Takeaways

- **Packet marks are a shared namespace.** Two independent networking systems can assign meaning to overlapping bits.
- **Trace beyond the CNI.** `to-overlay` means Cilium chose encapsulation; it does not prove Linux emitted the outer packet on the intended interface.
- **Use exact marked route lookups.** An unmarked `ip route get` can look correct while the real packet takes another policy rule.
- **Reproduce with an ordinary Pod.** This separated the infrastructure defect from CloudNativePG immediately.
- **Test fresh and established flows.** Conntrack can make a broken new-flow path look healthy.
- **Keep the exception narrow.** Match the exact peers, protocol, and port instead of overriding Tailscale policy broadly.
- **Preserve declarative ownership.** NixOS owns the host rule; Flux owns removal of the Kubernetes workaround; neither depends on a live-only patch.
- **Test systemd activation semantics.** Correct command text is not enough if the unit does not start during configuration activation.
