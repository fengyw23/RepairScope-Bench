# Research Story: Reasoning About Repair Scope

## Problem

A tool agent may already have booked travel, purchased equipment, activated a
licence, or signed a vendor service before a later action fails. Completing
the missing step is not enough: the agent must decide which successful
commitments remain useful and which should be reconsidered.

Failure location alone does not determine repair scope. A missing accessory
may be repaired locally, through a bridge component, or by replacing an
upstream device and its linked licence. Each can satisfy the hard goal, but
refunds, threshold clawbacks, shared dependencies, and recurring costs can
make one scope objectively dominated.

## Research gap

Neighboring benchmarks test rollback execution, recovery from dynamic state,
or reaching a prescribed database state. RepairScope-Bench asks a different
question:

> From the same reachable post-failure state, can an agent inspect distributed
> economic facts and avoid a hard-goal-feasible repair scope that another
> feasible outcome strictly dominates?

The novelty claim is benchmark formulation and measurement, not the invention
of partial rollback.

## Why reasoning structures

Fee names are surface forms. v1 organizes tasks by ten reusable reasoning
structures: sunk-cost separation, multi-hop propagation, shared commitments,
thresholds, conditional contracts, partial quantities, bridge repairs, joint
selection, explicit horizons, and Pareto trade-offs.

Each structure appears across four domains and multiple economic carriers.
Single-fact counterfactual pairs test whether the model changes its scope when
one refund or linked term changes. This is stronger evidence than performance
on unrelated one-off stories.

## Expected empirical signature

The central result should report:

```text
high Goal Pass
+ lower Non-Dominated Repair Pass
+ low Counterfactual Pair Success
= agents can execute valid repairs but do not reliably reason about scope
```

Error analysis then identifies whether failures arise from missing policy
queries, multi-hop propagation, threshold arithmetic, combinatorial scope
selection, or wasteful execution.

## Claim boundary

v1 is a controlled recovery-stage benchmark. It does not score pre-failure
planning, subjective comfort, stochastic risk preference, or production
safety. Failure states and prices are synthetic. The common runtime improves
comparability but remains less externally diverse than four independently
developed production systems.

A conference paper still requires multi-model five-run experiments,
clustered uncertainty estimates, independent human audit, prompt
paraphrases, ID permutation tests, and preferably additional scenarios
authored outside the generator team.
