---
title: "When Prometheus Alerts Resolve Themselves and the Problem Hasn't Gone Away"
date: 2026-08-21T00:00:00+0800
tags: [prometheus, grafana, alerting, promql, observability]
---

An alert fires for a hardware fault. Two minutes later Grafana marks it resolved. Nobody touched the machine, and it's still broken. If the alert is wired to a ticketing system or a pager, the "resolved" event goes out too, and closes the incident while someone is still fixing it.

This is usually not a flaky evaluator. It's that the metric doesn't mean what the alert assumes it means.

## State gauges vs event-window metrics

Two different things get exported as "metrics":

| | State gauge | Event-window metric |
|---|---|---|
| Example shape | `thing_status{...} = 1` | `events_count{code="..."}` |
| Meaning | the condition is true right now | an event happened recently |
| Lifetime | series exists as long as the target is scraped | series exists only while an event is inside the exporter's window |
| Resolves when | condition stops being true | window drains, whatever the condition is doing |

Alerting on a state gauge behaves how you'd expect: the value goes back to normal, the alert resolves, and that tells you something.

Event-window metrics are where this goes wrong. Many exporters count "events seen in the last N minutes" and attach a label identifying the event: an error code, a reason, a kind. That label only exists while an event sits inside the window. In steady state you get an unlabelled series at zero, or nothing at all.

So this rule:

```promql
sum by (instance, device, code) (
  max_over_time(some_events_count{code="42"}[5m])
)
```

is not asking "is device X in error state 42?". It's asking "did an event with code 42 arrive in the last 5 minutes?". Those are the same question for 5 minutes and then they aren't.

## Two ways it resolves early

These need different fixes, so it's worth telling them apart.

**Missing series.** The selector matches a series that stops being exported. The alert instance has no data at all: not a false condition, an absent one. Grafana treats a firing instance whose series disappeared as stale and resolves it after `missing_series_evals_to_resolve` evaluations, which defaults to 2. At a 1-minute group interval that's a 2-minute resolve.

**Window drain.** The underlying metric is a persistent counter, so the series never disappears, but a short `increase(...)` or `max_over_time(...)` drops back to zero once the events age out. The condition goes false and the alert resolves normally.

Both look the same in the UI: it was firing, now it isn't, nothing was fixed.

## Working out which one you have

Compare how long the labelled series lives against a plain state metric from the same exporter on the same target:

```promql
# does the alerting series still exist?
count(some_events_count{instance="...", code="42"})

# is the exporter alive and still reporting at all?
count(some_other_gauge{instance="..."})
count(up{instance="..."} == 1)
```

If the last two keep reporting while the first goes to nothing, the exporter is fine and the label just expired. That's worth checking early, because "the exporter died" and "the label expired" look identical from the alert side and have nothing in common as fixes.

Then see whether the resolve time matches `exporter window + (group interval × missing_series_evals_to_resolve)`. If it lines up, that's your answer.

## What each setting actually does

```promql
max_over_time(some_events_count{code="42"}[2h])
```

Widening the range selector is the change that matters. It's the only one that keeps the series existing: as long as one sample falls inside the window, `max_over_time` still returns a value for that label set. The other settings only delay a resolve that's already happening.

With Grafana's managed alert rules, the rule's query time range has to be at least as long as the range selector, or the query quietly sees less data than you asked for. Change both together.

| Setting | What it does | What it doesn't do |
|---|---|---|
| range selector (`[2h]`) | keeps the series alive and the condition true | anything, if the query time range is shorter |
| `keep_firing_for` | holds a firing alert open after the condition goes false | bring back a series that vanished |
| `missing_series_evals_to_resolve` | how many empty evaluations before a stale instance resolves | help when the series is present but zero |
| `for` (pending period) | delays firing, filters noise | change resolve behaviour |

`keep_firing_for` and `missing_series_evals_to_resolve` are worth setting as a backstop, since they cover the exporter dropping out entirely. They aren't the fix on their own. A 30-minute `keep_firing_for` on a 5-minute window still resolves in 35 minutes.

## Pick the window on purpose

Widening the lookback changes what "resolved" means: the alert now clears only after a clean window with no events. So pick it from the failure mode rather than taking a default:

- **Hard failures needing someone to physically intervene** (a device dropping off the bus, uncorrectable memory errors): hours. The condition won't fix itself, and you want the alert to outlive the repair.
- **Transient events that still need a look** (a process getting killed, a retry storm): long enough that the alert is still there when someone triages. If it clears before anyone reads it, it wasn't doing anything.
- **Conditions that really are live** (thermal throttling, saturation): leave the window short. Resolving is correct here, because the condition did stop. Add a small `keep_firing_for` so it doesn't flap on the edge.

The mistake is using one window for all of them. What's right for "device fell off the bus" is wrong for "device is hot right now".

## Alert on state when there is a state signal

Where a state signal exists, alert on that and use the event metric for the detail. Plenty of exporters publish both: a health or status gauge that stays up while the condition is true, alongside the event counter. Alert on the gauge, and pull the error code and history from the events.

An event metric can tell you something happened. It can't tell you it stopped.

## Auto-resolve is a write, not a colour change

If alert notifications feed anything stateful (a ticket tracker, an on-call system, a vendor integration, a bot posting updates) then a resolve is a write. An early one can:

- close a ticket while the repair is still going
- cancel an escalation before anyone acknowledged it
- mark a machine healthy in an automated remediation loop, putting a broken node back into service

That's what turns an alerting config detail into an incident. When reviewing rules built on event metrics, check what consumes the resolve, not just whether the fire was right.

## Checklist

For any alert rule whose selector pins a label naming an event, error code, or reason:

- [ ] Is this a state gauge or an event-window metric? Look for "in the last N" in the exporter docs; that's a window.
- [ ] Does the labelled series exist in steady state, or only during an event?
- [ ] Is the range selector at least as long as the condition realistically lasts?
- [ ] Is the rule's query time range >= the range selector?
- [ ] Is there a `keep_firing_for` / `missing_series_evals_to_resolve` backstop?
- [ ] Is there a state gauge you should be alerting on instead?
- [ ] What acts on the resolve downstream, and is it safe if the resolve is wrong?
