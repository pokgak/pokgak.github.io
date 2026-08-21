---
title: "When Prometheus Alerts Resolve Themselves and the Problem Hasn't Gone Away"
date: 2026-08-21T00:00:00+0800
tags: [prometheus, grafana, alerting, promql, observability]
---

An alert fires for a hardware fault. Two minutes later Grafana marks it resolved. Nobody touched the machine — it's still broken. If the alert is wired to a ticketing system or a pager, the "resolved" event propagates too, and closes the incident out from under whoever was fixing it.

The cause is almost never a flaky evaluator. It's a mismatch between what the metric represents and what the alert assumes it represents.

## State gauges vs event-window metrics

Two very different things get exported as "metrics":

| | State gauge | Event-window metric |
|---|---|---|
| Example shape | `thing_status{...} = 1` | `events_count{code="..."}` |
| Meaning | the condition is true *right now* | an event happened *recently* |
| Lifetime | series exists as long as the target is scraped | series exists only while an event is inside the exporter's window |
| Resolves when | condition stops being true | window drains — regardless of the condition |

Alerting on a state gauge is straightforward: the value goes back to normal, the alert resolves, and that means something.

Event-window metrics are the trap. Many exporters count "events seen in the last N minutes" and attach a label identifying the event — an error code, a reason, a kind. That label **only exists while an event sits inside the window**. In steady state you get an unlabelled series at zero, or nothing at all.

So a rule like this:

```promql
sum by (instance, device, code) (
  max_over_time(some_events_count{code="42"}[5m])
)
```

is not asking "is device X in error state 42?" It's asking "did an event with code 42 arrive in the last 5 minutes?" Those are only the same question for the first 5 minutes.

## Two distinct resolve mechanisms

Worth separating, because they need different fixes.

**1. Missing series.** The label selector matches a series that stops being exported. The alert instance has no data at all — not a false condition, an *absent* one. Grafana treats a firing instance whose series disappeared as stale and resolves it after `missing_series_evals_to_resolve` evaluations (default 2). At a 1-minute group interval that's a 2-minute resolve.

**2. Window drain.** The underlying metric is a persistent counter, so the series never disappears, but a short `increase(...)` or `max_over_time(...)` falls back to zero once the events age out. The condition evaluates false and the alert resolves normally.

Both look identical in the UI: the alert was firing, now it isn't, nothing was fixed.

## Telling which one you have

Compare the lifetime of the labelled series against a plain state metric from the same exporter on the same target:

```promql
# does the alerting series still exist?
count(some_events_count{instance="...", code="42"})

# is the exporter alive and still reporting at all?
count(some_other_gauge{instance="..."})
count(up{instance="..."} == 1)
```

If the second and third keep reporting while the first goes to nothing, the exporter is healthy and you're looking at a window artefact — not a scrape outage, not an agent crash. That distinction matters, because "the exporter died" and "the label expired" have completely different fixes and you'll waste an afternoon on the wrong one.

Then check whether the resolve timing lines up suspiciously well with `exporter window + (group interval × missing_series_evals_to_resolve)`. If it does, that's your answer.

## The knobs, and what each actually does

```promql
max_over_time(some_events_count{code="42"}[2h])
```

Widening the range selector is the **load-bearing** change. It's the only one that keeps the series *existing*: as long as one sample falls inside the window, `max_over_time` still produces a value for that label set. Everything else merely delays a resolve that's already happening.

If you're using Grafana's managed alert rules, the rule's query time range must be at least as long as the range selector — otherwise the query silently sees less data than you asked for. Bump both together.

| Setting | What it does | What it does *not* do |
|---|---|---|
| range selector (`[2h]`) | keeps the series alive and the condition true | nothing, if the time range is shorter |
| `keep_firing_for` | holds a firing alert open after the condition goes false | resurrect a series that vanished mid-window |
| `missing_series_evals_to_resolve` | how many empty evaluations before a stale instance resolves | help at all when the series is present but zero |
| `for` (pending period) | delays *firing*, filters noise | affect resolve behaviour |

Reach for `keep_firing_for` and `missing_series_evals_to_resolve` as defence in depth — they cover the case where the exporter itself drops out — but don't treat them as the fix. A 30-minute `keep_firing_for` on a 5-minute window still resolves in 35 minutes.

## Pick the window deliberately

Widening the lookback redefines what "resolved" means: the alert now clears only after a clean window with no events. So choose it from the failure mode, not from a default:

- **Hard failures needing physical intervention** (a device dropping off the bus, uncorrectable memory errors) — hours. The condition doesn't self-heal, and you want the alert outliving the repair.
- **Transient-but-worth-knowing events** (a process getting killed, a retry storm) — long enough that the alert survives until someone triages it. An alert that vanishes before a human reads it is a metric, not an alert.
- **Genuinely live conditions** (thermal throttling, saturation) — leave the window short. Resolving *is* correct here, because the condition really did stop. Add a modest `keep_firing_for` so it doesn't flap on the edge.

The trap is applying the same window everywhere. A window that's right for "GPU fell off the bus" is badly wrong for "GPU is hot right now."

## Prefer state, where a state signal exists

The deeper fix is to alert on a state signal when one is available, and treat the event metric as forensic detail. Plenty of exporters publish both: a health/status gauge that persists while the condition is true, alongside the event counter. Alert on the gauge; use the event stream to attach the error code and history.

An event metric can tell you something happened. It can never tell you the thing stopped mattering. Don't ask it to.

## Downstream: auto-resolve is not a free action

If alert notifications feed anything stateful — a ticket tracker, an on-call system, a vendor integration, a chatbot posting updates — then a resolve is a *write*, not just a UI colour change. A premature resolve can:

- close a ticket while the repair is still in progress
- cancel an escalation before anyone acknowledged it
- mark a machine healthy in an automated remediation loop, putting a broken node straight back into service

This is the part that turns an alerting-config detail into an incident. When auditing rules built on event metrics, check what consumes the resolve event, not just whether the fire was correct.

## Checklist

For any alert rule whose selector pins a label naming an event, error code, or reason:

- [ ] Is this a state gauge or an event-window metric? Check the exporter docs for the phrase "in the last N" — that's a window.
- [ ] Does the labelled series exist in steady state, or only during an event?
- [ ] Is the range selector at least as long as the condition realistically persists?
- [ ] Is the rule's query time range >= the range selector?
- [ ] Is there dwell (`keep_firing_for`, `missing_series_evals_to_resolve`) as a backstop?
- [ ] Is there a state gauge you should be alerting on instead?
- [ ] What downstream system acts on the resolve, and is it safe if the resolve is wrong?
