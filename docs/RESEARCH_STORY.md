# Research Positioning

## The problem

Tool-using agents create commitments: bookings, purchases, messages, database
updates, reservations, and permissions. When a later action fails, successful
earlier results do not all become wrong. Some remain necessary, some become
incompatible, and some are worth changing only because a hard budget, deadline,
or policy now binds.

The research question is:

> From an authoritative post-failure state containing persistent commitments,
> can an agent choose and execute the minimum-loss repair scope while satisfying
> the original hard goal?

This wording avoids the subjective claim that an agent has generic “value
awareness.” Every scored fact is expressed as a state invariant, policy,
compatibility relation, deadline, refund, price, or explicit fee.

## Distinction from neighboring evaluations

| Evaluation target | Typical question | RepairScope-Bench adds |
|---|---|---|
| Stateful task execution | Did the final database state match the requested state? | A standardized failure boundary and a minimum-loss recovery oracle over existing commitments |
| Dynamic adaptation | Did the agent notice a changed tool state and find a new valid plan? | Persistent pre-failure commitments whose keep/change/cancel scope is itself evaluated |
| Tool-failure robustness | Did the agent detect, retry, verify, or fall back from a failed call? | Objective consequences of disturbing successful earlier actions |
| Dependency rollback | Which steps depend on the error and should be re-run? | Hard goals and compensation costs can make the optimal scope smaller, larger, or non-contiguous relative to error propagation |
| Pre-execution planning | Which complete plan is cheapest or best before acting? | Decisions after money has been spent and cancellation/refund policies apply |

The claim should not be “the first partial rollback.” Partial rollback,
compensation, and recovery scopes predate language agents. A defensible claim is
the controlled, executable, counterfactual evaluation of **post-commit scope
selection under explicit constraints and losses**.

## Why a fixed failure snapshot is a feature

If agents freely execute the entire prefix, they can reach different failure
states. That is valuable for an end-to-end reliability score, but it confounds
the narrower scientific question: did the model select a better repair scope,
or did it merely create a different prefix?

The conditional track:

- holds the causal input state constant;
- makes exact oracle comparison possible;
- supports paired counterfactual tests;
- permits low-variance model comparisons;
- resembles resuming an automation from a persisted incident checkpoint.

The benchmark must nevertheless demonstrate provenance. Every snapshot is
paired with an externally visible canonical tool trace, and a paper-scale
release should publish a deterministic prefix generator plus snapshot hashes.

## Paper-scale contributions

1. **Problem definition.** Separate failure localization, re-execution point
   selection, and commitment repair-scope selection.
2. **Executable benchmark.** Standardized post-failure states with real tool
   mutations and persistent side effects.
3. **Objective oracle.** Enumerate or solve all feasible repairs using public
   constraints and complete financial ledgers; accept all tied optima.
4. **Counterfactual families.** Change one decisive fact so the optimal scope
   flips, while adding irrelevant and paraphrase controls.
5. **Diagnostic evaluation.** Report goal completion, regret, over-repair,
   under-repair, collateral loss, infeasibility handling, and family
   consistency.
6. **Empirical finding.** Test whether current agents complete the task yet
   choose a dominated or unnecessarily destructive recovery scope.

## What would make the idea top-conference ready

The v0.4.0 repository is a protocol demonstration, not the final empirical
contribution. A strong submission needs:

- substantially more independent causal structures rather than numeric
  variants of four templates;
- at least four domains with qualitatively different commitments;
- a clear dataset-generation and quality-control pipeline;
- solver certificates or a second oracle for every test task;
- template-disjoint hidden evaluation;
- human verification of scenario clarity, not human voting on the gold scope;
- strong contemporary agents and recovery baselines;
- ablations separating state representation, explicit ledgers, solver use, and
  model reasoning;
- an end-to-end auxiliary track or no-failure twins to establish external
  relevance without weakening the controlled main track.
