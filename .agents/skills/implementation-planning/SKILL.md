---
name: implementation-planning
description:
  Plan a feasible one-week Arx implementation or refactor with small, reviewable
  acceptance-driven steps. Use for plans, milestones and work breakdowns.
---

# Plan a one-week, reviewable implementation

**Use when the user asks for a plan, milestones, a feature breakdown, or
substantial refactoring.** For a straightforward fix, a formal plan may be
unnecessary. Always apply [minimal-change](../minimal-change/SKILL.md).

## Planning protocol

1. **Goal:** In one or two sentences, state precisely what changes for the
   user/developer.
2. **Current implementation:** Read the relevant existing code, tests, and
   project contracts; identify what can be reused. Don't propose replacements
   before investigating.
3. **Done means:** List 2–5 observable acceptance criteria, including critical
   correctness/safety behavior.
4. **Smallest vertical slice:** Include all necessary compiler stages for the
   supported behavior, but nothing unrequested. Consider affected package
   callers and native ABI dependencies.
5. **Execution:** Provide a short ordered sequence, normally 3–7 implementation
   steps. Group work by meaningful implementation outcome, not by trivial file
   operations.
6. **Verification:** Name the _existing_ tests/checks that prove success and any
   truly missing regression coverage. Do not plan benchmarks, documentation
   files, CI jobs, or new task infrastructure unless necessary.
7. **Risks and omissions:** Identify only immediate blockers and intentionally
   excluded work.

## Timebox and milestone policy

Target **one week**. Two weeks is a maximum default, only for a genuinely
broader requested change. One milestone can represent one complete PR; don't
divide a small PR into 10 milestones with dozens of subtasks.

If the smallest _correct_ solution needs longer than two weeks, find the first
self-contained and useful deliverable (e.g. one supported Arrow kernel through
semantic analysis and compiled execution), clearly mark unsupported cases, and
present subsequent work as optional follow-up—not as tasks silently approved in
the current scope. Never call parser-only or ASTx-only support "feature
complete."

## Output format

```markdown
## Goal

<one sentence>
## Acceptance criteria
- <observable behavior>
## Implementation
1. <concrete code change with ownership>
2. <necessary integration>
3. <verification>
## Risks / out of scope
<only when meaningful>
```

For small tasks, omit headings and use a short paragraph instead. Avoid Gantt
charts, oversized status matrices, new plan files, invented estimates,
exhaustive alternate designs, and reviews of unrelated architecture.

## Example

Request: "Move import type resolution out of Arx codegen."

Good: inspect existing `irx.analysis` semantic plans; move **only** the
remaining resolution to its owning layer; adapt `arx/codegen.py` to consume
metadata; run affected analysis and compiled tests. Likely one PR.

Bad: redesign the whole compiler pipeline, create an adapter framework, add 12
integration suites, benchmark all backends, and rewrite the architecture docs.

## While executing

Reassess whether the result already meets acceptance criteria. Stop rather than
inventing new milestones. State new substantial work as a decision for the user,
not an automatic extension.
