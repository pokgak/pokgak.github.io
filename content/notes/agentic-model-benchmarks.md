---
title: "SOTA Benchmarks for Agentic Models"
date: 2026-04-12T15:19:28+0800
tags: [ai, benchmarks, agents, llm]
---

Evaluating agentic models requires different benchmarks than standard chat/reasoning evals. Each benchmark makes sharp design tradeoffs — what it optimizes for determines what it's blind to.

## BFCL — Berkeley Function Calling Leaderboard

[Paper](https://arxiv.org/abs/2402.15491) | [Repo](https://github.com/ShishirPatil/gorilla)

- ~4,700 test cases across ~21 scoring categories
- Four test groups: single-turn (simple/parallel/multiple), live (user-contributed schemas), multi-turn (dialogue with tool use), and agentic (memory backends, web search)

**How it scores:**
- **AST checker** for single-turn: parses output as function call, checks name + params + types + values against a `possible_answer` list. String values are heavily normalized (lowercase, strip punctuation/spaces)
- **Execution checker** for multi-turn: runs model's tool calls against simulated backends, compares resulting state to ground truth
- **Agentic checker**: only verifies the final answer string appears in the response — does *not* validate intermediate tool-call chains
- All scoring is binary pass/fail per test case

**Optimizes for:** controllability and deterministic evaluation. Synthetic schemas with known correct answers make scoring unambiguous.

**Sacrifices:**
- Realism — synthetic schemas don't capture the messiness of real APIs (ambiguous descriptions, overlapping tools)
- Semantic quality — checks structural correctness of the call, not whether the model's reasoning was sound
- Robustness — scores are [fragile to naturalistic query rephrasing](https://arxiv.org/abs/2504.00914) and toolkit expansion with similar tools
- Format instruction compliance — [IFEval-FC](https://arxiv.org/abs/2509.18420) specifically criticizes BFCL for not testing adherence to format instructions embedded in parameter descriptions
- Small sample sizes in some live categories (15-23 entries) limit statistical significance

**Bottom line:** BFCL answers "can this model produce structurally correct tool calls?" — a necessary but not sufficient condition for agentic work. Good first filter, especially for smaller models where schema hallucination is the primary failure mode.

---

## τ-bench (Tau-bench)

[Paper](https://arxiv.org/abs/2406.12045) | [Repo](https://github.com/sierra-research/tau-bench)

- 165 tasks across 2 domains: retail (115 tasks, 17 tools) and airline (50 tasks, 15 tools)
- Each domain has a policy wiki, constraint rules, mock database, and Python tool implementations

**How it scores:**
- **Database state match**: after conversation ends, replays ground-truth actions on a fresh DB copy and compares hashes to the agent's resulting DB state
- **Output match**: expected strings must appear (case-insensitive substring) in agent responses
- Both must pass — binary 0/1 per task
- Key metric is **pass^k**: run each task k times, estimate probability all k succeed via `C(c,k)/C(n,k)`. This measures *reliability*, not just average accuracy. GPT-4o scored <50% pass^1 and <25% pass^8 on retail

**The user simulation twist:** a separate LLM (default: GPT-4o) plays the customer, following natural conversation instructions. It doesn't dump all info at once — it behaves like a real customer. This adds realism but introduces non-determinism.

**Optimizes for:** end-to-end task completion with realistic multi-turn interaction. The pass^k metric specifically targets reliability — penalizing models that succeed sometimes but fail unpredictably.

**Sacrifices:**
- Determinism — results depend on the user-simulator model
- Credit granularity — binary scoring means a conversation that's 90% correct and one that's 0% correct score the same
- DB hash comparison is fragile: a different but equally valid action sequence (e.g., equivalent payment method) scores 0
- Breadth — only 2 narrow customer service domains, 165 total tasks
- Efficiency measurement — no evaluation of how many turns were needed, only whether the task succeeded

**Bottom line:** τ-bench answers "can this model reliably complete multi-turn tasks?" — the key word being *reliably*. The pass^k metric is the real innovation here: it surfaces the difference between a model that works 80% of the time (unusable in production) and one that works 99% of the time.

---

## SWE-bench

[Paper](https://arxiv.org/abs/2310.06770) | [Repo](https://github.com/princeton-nlp/SWE-bench)

- Full: 2,294 instances from 12 Python repos (Django, scikit-learn, sympy, matplotlib, Flask, etc.)
- Lite: 300 instances filtered for single-file patches with ≤3 hunks, problem statements >40 words, no images/links
- Verified: human-curated subset for quality

**How it scores:**
- Model receives a codebase at a specific commit + GitHub issue text, must produce a `.patch` file
- Eval runs in Docker: applies patch via `git apply`, runs repo's test suite
- **FAIL_TO_PASS**: tests that failed before the gold PR must now pass (all of them)
- **PASS_TO_PASS**: tests that passed before must still pass (no regressions)
- Instance "resolved" only when both hit 100%. No partial credit — fixing 4/5 failing tests scores the same as fixing 0

**Optimizes for:** real-world grounding. These are actual PRs from real repos with real test suites. No synthetic tasks, no simplified environments. Docker isolation makes evaluation reproducible.

**Sacrifices:**
- Speed — Docker-based eval is heavyweight
- Language diversity — Python only in the original benchmark
- Solution leakage — [SWE-bench+](https://arxiv.org/abs/2410.06992) found ~33% of instances where the solution was directly stated in the issue text or comments
- Weak tests — ~31% of "solved" patches were suspicious due to inadequate test cases. After filtering both issues, SWE-Agent+GPT-4 dropped from 12.47% to 3.97%
- Data contamination — 94%+ of issues predate LLM training cutoffs. [SWE-bench-Live](https://arxiv.org/abs/2505.23419) addresses this with post-2024 issues
- Test overfitting — systems that generate their own tests and iterate can pass the benchmark's tests without truly fixing the issue

**Bottom line:** SWE-bench is the hardest and most revealing benchmark here, but also the most gamed. The Lite/Verified/Live splits represent an ongoing arms race between benchmark designers and leaderboard optimizers. When reading SWE-bench scores, always check which split and whether the agent had access to repo tests during generation.

---

## AgentBench

[Paper](https://arxiv.org/abs/2308.03688) | [Repo](https://github.com/THUDM/AgentBench)

- 8 environments: OS interaction (bash), database (SQL), knowledge graph (SPARQL), card game, lateral thinking puzzles, ALFWorld (household tasks), Mind2Web (web browsing), WebShop (product search), Avalon (social deduction)
- Each environment has its own metric, interaction protocol, and Docker container

**How it scores:**
- No unified scoring function — each environment has a bespoke metric:
  - OS: accuracy, DB: category accuracy, KG: custom score, ALFWorld: success rate, Mind2Web: step success rate, WebShop: reward score, Card Game: win rate
- Client-server architecture with max-flow scheduling for concurrent evaluation
- Detailed failure tracking: context limit exceeded, validation failed, invalid action, task limit reached

**Optimizes for:** breadth of environment coverage and standardized multi-model comparison (25+ models). The interactive multi-turn format (not single-shot) is closer to real agent behavior than most benchmarks.

**Sacrifices:**
- Depth — round limits (8 for OS, 15 for DB) artificially cap complex reasoning chains
- Unified comparison — no aggregate score, results are a table of per-environment numbers that resist summarization
- Reproducibility — Docker dependency + external data for some environments (Mind2Web, WebShop) makes setup non-trivial
- Opponent calibration — game environments use naive bots, not strong baselines
- Long-horizon planning — despite finding this as a main failure mode, the short episode format doesn't deeply test it

**Bottom line:** AgentBench is the broadest benchmark but the shallowest per-domain. Useful for a capability radar chart across environments, not for deep evaluation of any single agentic skill. The lack of unified scoring makes it hard to produce a single "agentic capability" number.

---

## Design Tradeoff Matrix

| | BFCL | τ-bench | SWE-bench | AgentBench |
|---|---|---|---|---|
| **What it tests** | Tool call correctness | Task completion via tools | Real-world code patches | Multi-env agent tasks |
| **Realism** | Low (synthetic schemas) | Medium (simulated customer) | High (real repos/issues) | Medium (Docker envs) |
| **Scoring** | Binary, structural match | Binary, state + output match | Binary, test suite pass | Per-env bespoke metrics |
| **Partial credit** | No | No | No | Varies |
| **Multi-turn** | Yes (subset) | Always | Implicit (agent decides) | Always |
| **Determinism** | High | Low (LLM user sim) | High (Docker + tests) | Medium |
| **Setup cost** | Low (Python harness) | Low (pip install) | High (Docker per repo) | High (Docker + external data) |
| **Task count** | ~4,700 | 165 | 300 (Lite) / 2,294 (Full) | ~500+ across envs |
| **Known gaming** | Query rephrasing fragility | User sim dependence | Solution leakage, test overfitting | Naive bot opponents |

## Supporting Dimensions

These aren't agentic-specific but matter when interpreting agent performance:

| Dimension | Benchmark | Why it matters for agents |
|---|---|---|
| Schema adherence | BFCL irrelevance + parallel | Smaller models hallucinate field names, wrong types, nonexistent tools |
| Multi-turn coherence | MT-Bench | Agents that lose context mid-task produce inconsistent tool calls |
| Instruction following | IFEval | Agents must respect constrained output formats — critical for structured pipelines |
| Long context recall | RULER / Needle-in-a-Haystack | MoE models may degrade differently at long context vs dense models |
| Hallucination rate | TruthfulQA / FActScore | Models reasoning about tool results can confidently fabricate; worse in multi-hop chains |

## Companies Publishing Product-Specific Evals

Academic benchmarks test general capabilities. These companies built evals for *their* workload — worth studying as templates.

**[CursorBench](https://cursor.com/blog/cursorbench)** (Cursor) — Tasks sourced from real Cursor sessions via "Cursor Blame" (traces committed code back to the agent request that produced it). Uses LLM graders, not just unit tests, because most dev requests have multiple valid solutions. Plots correctness against token cost to capture the quality/latency tradeoff. Key insight: real developer prompts are short and underspecified — nothing like the verbose issue descriptions in SWE-bench.

**[Cognition-Golden](https://x.com/cognition_labs/status/1834292727464488966)** (Cognition/Devin) — Internal benchmark using "realistic evaluations for economically valuable tasks," sometimes on codebases with millions of lines. Train/test split to prevent overfitting. Production Devin scores 74.2% on the test split. Designed around what paying customers actually need.

**[Stripe Integration Benchmark](https://stripe.com/blog/can-ai-agents-build-real-stripe-integrations)** (Stripe) — 11 environments testing autonomous Stripe integration building (backend-only, full-stack, focused exercises). Grading is deterministic: automated tests exercise the finished software via API calls and UI tests, then validates Stripe API objects were created correctly. Their philosophy: "a mostly correct integration is a failure; payments require 100% accuracy."

**[v0 Evals](https://vercel.com/blog/eval-driven-development-build-better-ai-faster)** + **[next-evals-oss](https://github.com/vercel/next-evals-oss)** (Vercel) — Multi-layered: code-based checks (valid imports, file structure), LLM-based grading for subjective quality, and human feedback. Every PR that affects output requires eval documentation. The open-source Next.js eval has 20 fixture-based tasks with vitest assertions. Notable finding: an 8KB AGENTS.md file achieved 100% pass rate vs 79% for skills-based retrieval.

**[Terminal-Bench](https://www.vals.ai/benchmarks/terminal-bench)** (VALS AI) — Tests the full terminal-based dev workflow: read code, run tests, interpret output, fix issues, commit. Used by OpenAI to benchmark Codex. More operational than SWE-bench — measures agent competence at *using terminal tools*, not just generating patches.

**Common pattern:** every product-specific eval shares the same structure — real task inputs sourced from production (not synthetic), domain-appropriate environments, deterministic outcome verification where possible, and LLM-based grading for subjective quality.

---

## Benchmarks vs Evals

Worth clarifying the distinction:

- **Benchmarks** are standardized, public, and comparative. They answer "how does model A compare to model B on a known task distribution?" BFCL, SWE-bench, τ-bench are benchmarks.
- **Evals** are product-specific, often private, and diagnostic. They answer "does this model/prompt/system work for *our* use case?" CursorBench, Stripe's integration tests are evals.

Benchmarks are useful for model selection. Evals are useful for shipping. You need both — but if you're building a product, evals are the ones that actually prevent regressions.

---

## Designing a Product-Specific Eval

Based on [Anthropic's eval guide](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) and patterns from the companies above:

### Start small, source from real failures

- **20-50 tasks** is enough to start. Early changes have large effect sizes — small samples suffice to detect them.
- Source tasks from **real user failures and production data**, not invented scenarios. Cursor uses "Cursor Blame" to trace agent-generated code back to the original request. Stripe uses real integration patterns.
- If you don't have production data yet, start with your own dogfooding sessions — record the inputs that broke.

### Three types of graders

| Grader type | Speed | Flexibility | When to use |
|---|---|---|---|
| **Code-based** (string match, assertion, API check) | Fast, deterministic | Rigid | Structured outputs, API state, pass/fail outcomes |
| **Model-based** (LLM judges the output) | Slower, needs calibration | Flexible | Subjective quality, multiple valid solutions, natural language outputs |
| **Human** | Slow, expensive | Gold standard | Calibrating model graders, ambiguous cases, initial eval design |

Most product evals use a mix. Stripe leans heavily on code-based (deterministic API checks). Cursor leans on model-based (many valid code solutions). Start with code-based where you can, add model-based for the rest.

### Grade outcomes, not paths

Agents find alternative valid solutions. If you check "did it call tool X with param Y at step 3", you'll get false failures from agents that solved the task differently. τ-bench's DB hash comparison is a cautionary tale — correct behavior via a different action sequence scores 0.

Instead: check the end state. Did the database have the right records? Did the API return the right response? Did the tests pass? Did the user's request get fulfilled?

### Capability evals vs regression evals

Two different purposes, two different design philosophies:

- **Capability evals** measure potential. Start at low pass rates, expect improvement over time. These are your frontier tasks — the hardest things your agent should eventually handle. When pass rate exceeds ~80%, graduate tasks to the regression suite and create harder ones.
- **Regression evals** ensure reliability. Target ~100% pass rate. These are tasks your agent already handles — the eval exists to catch regressions when you change prompts, models, or tools. A failure here is a bug.

### Measure reliability, not just accuracy

Steal τ-bench's pass^k metric. For any customer-facing agent:
- **pass@k** = "did it succeed at least once in k tries" — measures potential, useful during development
- **pass^k** = "did it succeed every time in k tries" — measures reliability, what matters in production

A model with 90% pass@1 sounds great until you realize that's 35% pass^10. Would you ship a product that fails 65% of the time over 10 interactions?

### Keep the eval alive

- **Refresh tasks** regularly — models memorize patterns, and your product evolves
- **Gate PRs on eval results** — Vercel requires eval documentation for every output-affecting PR
- **Feed production failures back** — when users report issues, add them to the eval suite
- **Monitor saturation** — an eval where everything passes is no longer providing signal

### Starter checklist

1. Collect 20-50 real tasks from production/dogfooding failures
2. Define what "success" looks like for each (end-state, not path)
3. Build code-based graders for deterministic checks
4. Add model-based graders for subjective quality
5. Split into capability (hard, low pass rate) and regression (known-good, target 100%)
6. Run each task k times, track pass^k
7. Set up CI to run regression evals on every change
8. Review failures manually — catch grader bugs, not just agent bugs

---

## Picking the Right Benchmark

- Raw tool-calling correctness → **BFCL**
- Multi-turn agent reliability → **τ-bench** (the pass^k metric is uniquely valuable)
- Coding agent / PR automation → **SWE-bench Lite** (check which split)
- Broad capability scan → **AgentBench**
- Diagnosing long-task failures → **RULER + MT-Bench**
- Small model (≤8B) deployment → **BFCL irrelevance detection + IFEval**
- Your specific product workload → **build your own eval** (see above)

## Takeaway

Academic benchmarks tell you which model to pick. Product evals tell you whether to ship. You need both, but they serve different stages:

1. **Model selection** — use BFCL, τ-bench, SWE-bench to narrow your options
2. **Product validation** — build your own eval from real failures, grade outcomes not paths, measure reliability with pass^k
3. **Ongoing quality** — gate deployments on regression evals, feed production failures back into the suite

The meta-lesson: benchmark scores are most useful when you understand what the benchmark *doesn't* test. A model that tops BFCL but bombs τ-bench can call tools perfectly but can't complete tasks. A model that tops SWE-bench Lite but was never tested on SWE-bench+ might just be pattern-matching leaked solutions. Always pair a primary benchmark with supporting dimensions that cover its blind spots — and always supplement with evals that test *your* workload.
