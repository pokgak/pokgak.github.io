# Experiments Format

Each experiment file follows a scientific structure: hypothesis → method → results → conclusion.

## Frontmatter

```yaml
---
title: "Short descriptive title: what was measured or investigated"
date: 2026-04-07T00:00:00+0800
tags: [relevant, tags]
---
```

## File Structure

Start with a one-paragraph summary of what is being investigated and the setup (hardware, software, context). Link to code if applicable.

Then a `## The Question` section stating the core question being answered.

Then a `## Hardware` / `## Setup` section if relevant.

---

Each experiment is a `## Experiment N: <Title>` section with these subsections:

### **Why this matters**
Why is this experiment necessary? What gap in understanding does it fill? What decision does it inform?

### **Hypothesis**
State a concrete, falsifiable prediction before running the experiment.

### **Method**
Briefly describe what was measured, how, and any controls (warmup, iterations, etc.).

### **Results**
Show data in a markdown table. Raw numbers, not just conclusions.

### **What this tells us**
Interpret the results. Was the hypothesis confirmed or refuted? What new questions does this raise? Link to the next experiment if relevant.

---

## End with a `## Final Summary`

Summarize the answer to the original question. A table of key findings by factor is useful here.

## Example

See `mlx-inference-throughput-gap.md` — a 12-experiment investigation into why MLX inference on M3 Ultra achieves only 62-81% of theoretical bandwidth.
