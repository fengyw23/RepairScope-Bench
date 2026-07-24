# Research Positioning

## Core observation

When a tool agent fails halfway through a task, the location of the failed
operation does not determine which earlier successful effects should be
reversed.

For a Shanghai conference trip, a failed dinner booking clearly requires a
new dinner. It may also make a hotel change necessary if no nearby restaurant
remains. It normally should not cancel the flight that is still required to
attend the conference. Which scope is correct depends on hard compatibility,
refunds, package terms, deadlines, and the persistent commitments already
created.

The research question is:

> Given an authoritative post-failure state with persistent commitments, can
> an agent explore the environment and execute a hard-goal-satisfying repair
> with minimum objectively measurable additional loss?

This is narrower and more defensible than “value-aware rollback.” Gold comes
from executable constraints and transaction rules, not a human preference
label.

## Why completion accuracy is insufficient

A full rollback policy can complete all 12 v0.5 challenge tasks, yet it is
optimal on none. A solver that ignores sunk/cancellation loss and searches
only for the cheapest final arrangement completes all tasks but is optimal on
only half.

Therefore:

```text
hard-goal success ≠ correct recovery scope
```

The empirical quantity of interest is the
**Scope-Optimization Gap = Goal Pass − Optimal Pass**.

## Relation to neighboring benchmarks

| Evaluation target | What it asks | Missing question addressed here |
|---|---|---|
| Stateful execution such as STATE-Bench | Did the final database satisfy the user's requested changes? | When several final states satisfy the hard goal, which prior commitments should be preserved? |
| Dynamic adaptation such as STT-Arena | Did the model notice an injected change and find a valid continuation? | What irreversible cost did its repair impose on effects created before the failure? |
| Stream revision benchmarks | Can an output or plan be revised as new textual information arrives? | Do revisions operate on persistent external commitments with refunds and compensation? |
| Failure recovery/rollback | Can affected steps be undone or re-executed? | Is the selected compensation scope objectively dominated by a less destructive feasible scope? |
| Pre-execution optimization | Which complete plan is cheapest before acting? | How should sunk commitments and cancellation policies change the optimum after execution starts? |

The claim is not that partial rollback is new. The contribution is the
controlled, executable evaluation of post-commit scope selection for modern
tool agents.

## Why the fixed failure state is legitimate

Allowing every model to create its own prefix is valuable for an end-to-end
system score, but it confounds the diagnostic question. Different models may
reach different failure states, so their later losses and repair choices are
not comparable.

The controlled main track:

- fixes the causal input state;
- preserves a public trace explaining how each commitment arose;
- requires real post-boundary queries and mutations;
- supports exact matched counterfactuals;
- permits an exhaustive objective Oracle;
- resembles resuming a production workflow from a persisted incident state.

This does not imply that end-to-end evaluation is unimportant. A later
auxiliary track can execute a deterministic prefix, verify that the trigger
and commitments occurred, and then reuse the same recovery evaluator.

## v0.5 benchmark story

### 1. Larger, genuinely competitive repair graphs

Each loss-aware task contains hundreds of candidate repairs, dozens of
goal-satisfying plans in many tasks, multiple scope patterns, and several
loss levels. Validation enforces minimum graph complexity instead of relying
on author intuition.

### 2. Objective non-local consequences

Changing one reservation or order can trigger a charge elsewhere:

- air-hotel package credit;
- workstation rebate;
- cold-chain calibration/service term.

This prevents the benchmark from collapsing into “pick the smallest refund
fee attached to the failed step.”

### 3. Tool-mediated composition

No single tool returns the answer. The model must combine:

- what is already confirmed;
- exact paid amounts and dates;
- live category-filtered inventory;
- cancellation or exchange terms;
- cross-option compatibility;
- linked settlement consequences.

The evaluator computes the global loss, but the model sees only source facts.

### 4. Matched objective-demand pairs

The same physical failure state is prompted once with only the hard goal and
once with a natural anti-waste request. This distinguishes:

- inability to find a feasible repair;
- inability to infer that preserving commitments matters;
- inability to optimize even after the user states that concern.

### 5. Mechanism-level generalization

Development, test, and held-out sets use different causal loss mechanisms.
Splitting by mechanism and family avoids leakage from numerical twins.

## Paper-scale contributions

1. A formal distinction between failure localization, feasible recovery, and
   objective repair-scope selection.
2. An executable fixed-boundary benchmark with persistent pre-failure
   commitments and real post-boundary mutations.
3. An exact Oracle over hard constraints, transaction loss, linked settlement
   effects, and all tied optimal scopes.
4. Matched feasibility/loss-aware prompts and counterfactual scope flips.
5. Metrics that explicitly expose “completed but needlessly destructive”
   behavior.
6. Empirical analysis across current agents, planning baselines, and
   ledger/compatibility ablations.

## What remains for a top-conference paper

The v0.5 release makes the benchmark mechanism credible, but a submission
still needs:

- tens to hundreds of independently authored failure states;
- at least four domains with distinct commitment semantics;
- hidden mechanism-disjoint test data;
- independent solver or certificate verification;
- human checks for linguistic clarity and realism, without human voting on
  the gold;
- broad multi-model results with five runs per task;
- ablations for linked terms, inventory visibility, state visibility, and
  objective-demand prompts;
- an auxiliary end-to-end or no-failure control track.

A convincing paper result would show high Goal Pass but substantially lower
Optimal Pass, plus failure analyses demonstrating over-repair, under-repair,
and loss-blind global replanning. If all strong models remain near Oracle,
the data must be expanded rather than claiming the task is solved.
