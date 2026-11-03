---
title: "Can an AI Agent Run a Profitable Restaurant?"
date: 2026-11-03T12:00:00+0800
tags: [llm, agents, benchmarks, simulation, cloudflare, workers-ai]
---

I built a deterministic restaurant-management game to test whether an AI agent can make good decisions over time, not merely produce valid tool calls. The shape is inspired by [OpenTTD-bench](https://openttd-bench.pages.dev/): give an agent a stateful world, expose a control interface, and score the economic outcome.

The agent controls pricing, inventory, staffing, marketing, investment, borrowing, maintenance, repairs, training, and delivery expediting. Every action, observation, model response, validation result, simulator receipt, and final export is archived to private R2 for later analysis.

The first batch tested three models across five matched seeds. A fourth model, DeepSeek V4 Pro, failed to complete any episode because its inference streams repeatedly stalled. The result was clear: **all three completed models lost money, while the heuristic opponent was profitable in every run**.

## The Question

Can a general-purpose reasoning model maximize cumulative operating profit over an 84-day restaurant simulation without going bankrupt? If not, what decisions cause it to fail?

## Setup

Each episode contains two restaurants in one market:

- one restaurant controlled by the model;
- one controlled by a fixed heuristic policy;
- 84 daily ticks, with a decision every 3 ticks;
- at most 5 actions per decision;
- five seeds: `4101001` through `4101005`;
- weather, local events, market demand, ingredient prices, staff events, supply disruptions, and equipment failures;
- profit as the primary score, with bankruptcy as an irreversible failure state.

The restaurants compete on relative price and marketing. The heuristic is therefore a fixed policy, not a fixed score: its profit changes in response to the model's behavior. Exogenous randomness and each restaurant's private random streams remain seed-controlled.

Every model received the exact same system prompt, action schema, observations, and neutral feedback contract. The frozen configuration was:

| Setting | Value |
|---|---|
| Prompt SHA-256 | `e3a773f0…d6f8d6b61` |
| Reasoning effort | High |
| Temperature | 0.2 |
| Response format | JSON object |
| Explicit output-token cap | None |
| Correction attempts | One, only after a blocking validation error |

Full prompt digest:

```text
e3a773f000f0d5bb8e4b1357459cd9434e63298875779ade779d2e7d6f8d6b61
```

Preflight feedback reported only schema and immediate feasibility errors. Outcome feedback reported observed deltas, action receipts, events, and pending commitments. It did not recommend a strategy or claim that an action caused an outcome.

The heuristic used the same three-tick cadence and five-action limit. Unlike the model harness, it explicitly targeted a $200 cash reserve, changed staffing by at most one worker at a time, and bounded inventory and credit use.

---

## Experiment 1: Profitability and Consistency

### **Why this matters**

A restaurant agent can look competent while setting prices, ordering stock, and fixing equipment, yet still destroy cash over a long horizon. The final economic state is the test.

### **Hypothesis**

The full GLM model will outperform the flash models because it should reason more carefully about delayed costs and cash commitments. At least one model should beat the heuristic on some seeds.

### **Method**

Run each model on all five seeds. Count only episodes that reached tick 84 and whose complete trace archive was verified in R2. Compare model profit with the heuristic operating in the same market. DeepSeek V4 Pro is reported separately because it completed zero episodes.

Two original attempts needed replacements: GLM 5.3 seed `4101001` failed before completion, and DeepSeek V4.1 Flash seed `4101005` completed after its first archive attempt failed. Both replacements used the frozen configuration above, and only their completed, R2-verified traces are included.

### **Results**

All values below are US dollars converted from simulator cents.

On narrow screens, scroll the tables horizontally to see all columns.

| Model | Completed | Mean profit | Median | Best to worst | Mean gap vs paired heuristic | Bankruptcies |
|---|---:|---:|---:|---:|---:|---:|
| GLM 5.3 | 5/5 | **-$1,338.12** | -$1,318.75 | -$1,017.15 to -$1,722.73 | **-$2,876.07** | 4/5 |
| GLM 5.3 Flash | 5/5 | -$2,645.73 | -$2,450.19 | -$1,671.31 to -$4,053.01 | -$3,910.95 | 5/5 |
| DeepSeek V4.1 Flash | 5/5 | -$3,824.27 | -$3,749.32 | -$2,095.19 to -$6,303.31 | -$5,841.44 | 3/5 |
| DeepSeek V4 Pro | 0/5 | Failed | — | — | — | — |

Per-seed model profit shows that the ranking was consistent. A dagger means the restaurant went bankrupt during the episode.

| Seed | GLM 5.3 | GLM 5.3 Flash | DeepSeek V4.1 Flash |
|---:|---:|---:|---:|
| 4101001 | **-$1,017.15†** | -$1,744.90† | -$3,159.16 |
| 4101002 | **-$1,354.28** | -$2,450.19† | -$2,095.19† |
| 4101003 | **-$1,277.71†** | -$1,671.31† | -$3,749.32† |
| 4101004 | **-$1,722.73†** | -$4,053.01† | -$6,303.31† |
| 4101005 | **-$1,318.75†** | -$3,309.24† | -$3,814.38 |

The paired heuristic was profitable and solvent in all 15 completed episodes. Its mean profit ranged from $1,265.22 to $2,017.17 across the three model matchups.

### **What this tells us**

The first half of the hypothesis was correct: GLM 5.3 won every matched seed. The second half was wrong: no model beat the heuristic, and no model produced a profitable restaurant.

Solvency and profitability were not the same. DeepSeek V4.1 Flash survived two runs by borrowing heavily, but it still produced the largest losses. GLM 5.3 lost less money while going bankrupt in four runs because it kept much smaller cash and debt buffers. A benchmark that reports only bankruptcy rate would rank these policies incorrectly.

The five-seed result is also more useful than a single run. The absolute outcome moved with market and operational shocks, but the model ranking held on every seed.

---

## Experiment 2: What Decisions Produced the Losses?

### **Why this matters**

Final profit identifies the winner but does not explain the policy. Complete traces let us connect the score to expansion, inventory, labor, and financing decisions without grading one preferred action sequence.

### **Hypothesis**

The weaker models will over-expand and use debt to protect short-term cash. The strongest model will make fewer irreversible commitments and waste less inventory.

### **Method**

Aggregate actions and final accounting across each model's five completed episodes. Compare revenue, costs, inventory waste, investment, training, and financing. Because bankruptcy shortens the active policy, action totals are shown together with the number of decision checkpoints.

### **Results**

| Model | Revenue | Costs | Units sold | Waste share¹ | Costs / revenue |
|---|---:|---:|---:|---:|---:|
| GLM 5.3 | $30,321.80 | **$37,012.42** | 1,767 | **35.2%** | **1.22×** |
| GLM 5.3 Flash | $23,832.78 | $37,061.43 | 1,520 | 40.4% | 1.55× |
| DeepSeek V4.1 Flash | **$44,993.00** | $64,114.36 | **2,713** | 43.0% | 1.43× |

¹ Waste units divided by units sold plus waste units. Ending and pending inventory are excluded.

| Model | Decisions | Actions / decision | Units ordered | Investments | Training | Borrowed | Repaid | Final debt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GLM 5.3 | 82 | 3.63 | 2,774 | **16** | **24** | **$2,350** | **$1,300** | **$1,050** |
| GLM 5.3 Flash | 73 | 3.27 | 2,758 | 20 | 3 | $9,200 | $950 | $8,250 |
| DeepSeek V4.1 Flash | 104 | **4.27** | **4,784** | **28** | 13 | **$14,820** | **$0** | **$14,820** |

The most common actions reinforce the same pattern:

| Action | GLM 5.3 | GLM 5.3 Flash | DeepSeek V4.1 Flash |
|---|---:|---:|---:|
| Change staffing target | 65 | 48 | **139** |
| Change menu price | 44 | 35 | **76** |
| Purchase inventory | 71 | 56 | **73** |
| Change marketing | 22 | 22 | **45** |
| Invest in capacity or quality | 16 | 20 | **28** |
| Borrow | 10 | 21 | **25** |
| Repay debt | **12** | 5 | **0** |

### **What this tells us**

DeepSeek V4.1 Flash optimized throughput instead of profit. It sold the most units and earned the most revenue, but bought more capacity, labor, inventory, and marketing than the margin could support. It borrowed $14,820 and never repaid any of it. High sales hid a policy that spent $1.43 for every $1 of revenue.

GLM 5.3 Flash was less active, partly because all five restaurants failed early. It still combined expansion with $9,200 of borrowing and almost no training. Its costs were nearly the same as full GLM despite earning $6,489 less revenue.

Full GLM was the least bad policy. It invested less, trained more, borrowed one quarter as much as GLM Flash, repaid more often than it borrowed, and produced the lowest waste share. This confirmed the hypothesis. However, it did not maintain enough cash for shocks and settlement costs: its four bankruptcies occurred at ticks 12, 20, 40, and 82.

The shared mistake was inventory. Even the best model discarded 959 units while selling 1,767. The agents reacted to stockouts and demand forecasts but underweighted six-day shelf life and the downside of prepaid orders.

---

## Experiment 3: Valid Actions Are Not Good Decisions

### **Why this matters**

Tool-use benchmarks often stop at parse rate or action validity. This environment can separate interface competence from policy competence.

### **Hypothesis**

The structured harness will make almost every final action valid. Economic performance will still differ because validation can reject impossible actions but cannot choose a profitable strategy without leading the model.

### **Method**

For every decision, record JSON parsing, envelope validation, schema validation, immediate feasibility, one correction attempt, and the simulator's final acceptance result.

### **Results**

| Model | Inference attempts | Final decisions | Corrections | Simulator-accepted actions | Reported tokens | List cost² |
|---|---:|---:|---:|---:|---:|---:|
| GLM 5.3 | 84 | 82 | 2/2 succeeded | **298/298** | 991,373 | $2.26 |
| GLM 5.3 Flash | 73 | 73 | None needed | **239/239** | 812,249 | **$0.20** |
| DeepSeek V4.1 Flash | 108 | 104 | 4/4 succeeded | **444/444** | 2,236,035 | $1.81 |

² Provider list-price estimate from terminal usage records for the 15 comparable completed episodes, not an invoice.

### **What this tells us**

The hypothesis was correct. Every submitted action was accepted by the simulator. GLM 5.3 Flash produced a valid, feasible decision on all 73 first attempts. Yet it went bankrupt five times.

Syntax and schema adherence are solved at this level. The remaining failure is policy: valuing delayed costs, holding a cash reserve, allowing staffing changes to settle, and separating a profitable experiment from simultaneous changes to price, marketing, labor, and capacity.

More reasoning tokens did not buy better decisions. DeepSeek V4.1 Flash used more than twice as many tokens as either GLM model and produced the worst profit. GLM 5.3 Flash was the cheapest model by an order of magnitude, but full GLM's higher inference cost bought a meaningful improvement in economic behavior.

Early bankruptcy shortened several GLM Flash episodes, so total tokens and cost are not pure measures of reasoning efficiency. They are the resources consumed by the scored episodes.

---

## Experiment 4: DeepSeek V4 Pro Failed at the Transport Boundary

### **Why this matters**

An autonomous benchmark needs to distinguish a bad game policy from a model that cannot reliably complete turns. Partial episodes are not comparable with 84-tick results.

### **Hypothesis**

DeepSeek V4 Pro, with high reasoning and no explicit output cap, will complete the same five episodes and improve on its flash sibling.

### **Method**

Run the same prompt, seeds, and inference settings through a streaming Workers AI relay. Preserve failed checkpoints and retry transport failures conservatively. Mark the model failed unless all five episodes complete and archive successfully.

### **Results**

DeepSeek V4 Pro completed **0 of 5** episodes. The canonical final attempts all ended in read timeouts after about 63 minutes. Four never submitted their tick-0 decision; the fifth submitted five actions at tick 0 and failed before tick 3.

Across the canonical and diagnostic retries, where one episode can make up to 28 inference calls:

- 81 individual inference streams reached a terminal `finish_reason`;
- 6 streams closed after 32,668 to 55,790 reasoning chunks without a terminal marker or JSON answer;
- 18 requests emitted data and then went silent until the 900-second socket-idle timeout;
- the incomplete reasoning streams contained 112,000 to 200,000 characters and showed heavy repetition;
- Cloudflare recorded HTTP 200 responses followed by client cancellation, with no Worker exception and only a few milliseconds of relay CPU time.

This matches a [reported DeepSeek SSE failure mode](https://github.com/deepseek-ai/DeepSeek-V3/issues/1608): reasoning deltas stop without `finish_reason`, `[DONE]`, an error event, or a closed connection. The relay was a pass-through; the strongest evidence points to the upstream model-serving stream rather than a crash in the Worker.

The harness also exposed an observability flaw. It buffered the full SSE body, so a timeout discarded the partial response instead of preserving each chunk and its arrival time. The failed episode summaries and errors reached R2, but the partial bytes from timed-out requests did not.

### **What this tells us**

The hypothesis was wrong. DeepSeek V4 Pro is a reliability failure for this configuration, not a low-scoring restaurant policy. I excluded its partial game states from the leaderboard.

The next harness version should parse and persist SSE incrementally, require a terminal event, classify clean-close and idle-stall failures separately, and use an inter-chunk watchdog based on observed healthy gaps. These changes do not require changing the prompt or adding an output-token cap.

The 15 completed episodes reported $4.27 in list-price usage. Across the entire batch, including exploratory and failed calls, the tracker had $19.17 of terminal usage records. Requests that timed out lacked terminal usage, so the budget tracker reserved $5 per uncertain request and stopped at **$149.17 of conservative exposure against a $150 ceiling**. That exposure is deliberately pessimistic and is not the Cloudflare bill.

---

## Trace and Reproducibility Contract

Each run archive contains:

- the exact prompt and SHA-256;
- inference settings, raw requests, responses, reasoning, usage, and errors;
- observations and neutral outcome feedback at each checkpoint;
- proposed actions, validation issues, corrections, submitted actions, and simulator receipts;
- environment events, actor logs, final game export, summary, and content digests.

The raw archives remain private because they contain full model reasoning and operational metadata. Aggregate results and the frozen contract are sufficient to interpret this write-up without publishing chain-of-thought.

## Limitations

- Five seeds are enough to expose a consistent ranking, but not enough for narrow confidence intervals.
- This tests one prompt, one action cadence, one heuristic opponent, and one restaurant economy. It is a product eval, not a general model ranking.
- The simulator is deterministic for the same seed and actions; model sampling at temperature 0.2 is not deterministic.
- The two restaurants share a competitive market, so the heuristic's score responds to model pricing and marketing. The paired gap is meaningful, but the heuristic is not a constant reference score.
- The baseline was written for this environment and explicitly holds a cash reserve. The models had the same information but had to discover that policy through reasoning.
- Costs are list-price calculations from reported usage. Failed streams without terminal usage prevent exact cost attribution.

## Final Summary

| Finding | Evidence |
|---|---|
| No tested model ran a profitable restaurant | 15/15 completed model episodes had negative operating profit |
| GLM 5.3 was consistently best | Lowest loss on all five matched seeds |
| Valid tool use did not imply good management | 981/981 submitted actions were accepted; every model still lost |
| DeepSeek Flash chased growth over profit | Highest sales and revenue, but $64,114 of costs and $14,820 of unrepaid debt |
| Inventory discipline was a shared weakness | 35% to 43% of sold-plus-wasted inventory was discarded |
| DeepSeek Pro was not scoreable | 0/5 complete episodes due to unterminated or stalled inference streams |

The main lesson is that long-horizon economic control is different from tool calling. These models understood the interface. They could repair equipment, react to stockouts, borrow cash, and produce valid JSON. They still failed to compound decisions into a profitable policy.

The useful feedback loop is therefore not more schema correction. It is neutral accounting feedback: future cash commitments, inventory aging, delayed staffing effects, and a profit-versus-cash bridge. The harness should expose those facts without recommending a particular strategy, then let the model prove whether it can learn from them.
