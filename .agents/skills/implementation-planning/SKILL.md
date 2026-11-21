---
name: implementation-planning
description: Plan a feasible one-week Arx implementation or refactor with small, reviewable acceptance-driven steps. Use for plans, milestones and work breakdowns.
---

# Short, delivery-oriented planning

Use when asked for an implementation plan, roadmap, milestone breakdown, or substantial refactoring plan. Apply [minimal-change](../minimal-change/SKILL.md).

## Timebox

Target **one working week** for a plan; two weeks is the exception, not the default. Prefer one coherent PR with a few concrete steps. Do not convert a focused change into ten milestones, hundreds of tasks, or a multi-quarter roadmap.

1. State the goal and observable acceptance criteria in a few sentences.
2. Inspect current code, tests, and available extension points before proposing infrastructure.
3. Define the minimum end-to-end slice; include mandatory cross-package or native boundaries only where affected.
4. List normally **3–7 implementation steps**, with owner areas and one verification step. Do not manufacture phases for ordinary tasks.
5. List genuine risks/blockers briefly. Keep optional enhancements outside the scoped plan.
6. If the smallest correct implementation exceeds two weeks, propose a first independently useful, reviewable slice and note what remains; do not claim partial support is complete.

One milestone may equal an entire PR. Prefer acceptance-oriented milestones rather than microtasks such as "create file", "rename function", or "write docs". Avoid planning documents in the repository unless explicitly requested or needed for an approved architecture decision.

## Completion

The plan should explain *what is necessary*, not catalog everything that might be done. Reassess scope during implementation and stop when acceptance criteria are met. Never automatically introduce benchmarks, new CI jobs, documentation pages, or speculative abstractions.
