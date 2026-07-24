# Evaluation Protocol

## Episode

1. Reset an executable environment to the public failure snapshot.
2. Give the model only the customer request, public pre-failure trace, latest
   failed tool result, and domain tools.
3. Require the model to investigate, decide, execute, verify, and call
   `finish`; `report_infeasible` is valid only when no hard-goal repair exists.
4. Serialize mutations and stop after at most 15 model turns.
5. Recompute terminal constraints, transaction ledgers, scope, and exact
   Oracle objective.

Every repetition receives a fresh deep copy. Read-only calls do not consume a
separate action budget. A task may set a high mutation safety cap, but
`finish()` is never blocked merely because the model performed many queries.

The official protocol runs each task five independent times. Provider errors
count as failed episodes in pass rates and are also reported separately.

## Hard-goal pass

A feasible task passes only when:

- exactly one active commitment exists in every required slot;
- every slot, cross-slot, deadline, compatibility, and lifecycle-budget
  constraint holds;
- the model called `finish`;
- no protocol budget was exceeded.

For an objectively infeasible task, the exact failure-boundary state and cash
ledger must remain pristine and the model must call `report_infeasible`.

## Auditable accounting

```text
financial_delta =
    post-failure charges
  + in-place modification net cash
  + triggered linked settlement charges
  - refunds of prior commitments
  - refunds of post-failure commitments

lifecycle_cost = pre-failure spend + financial_delta

cancellation_loss =
  sum(price_paid - refund_received for cancelled prior commitments)

post_failure_waste =
  sum(price_paid - refund_received for recovery purchases later cancelled)

recovery_loss =
    cancellation_loss
  + post_failure_waste
  + max(0, total modification net cash)
  + linked settlement loss
```

Linked settlement rules model objective non-local effects such as forfeiting
an air-hotel credit when either reservation changes, losing a workstation
bundle rebate when the laptop is returned, or invalidating a prepaid
calibration credit. Each rule names its triggering prior commitments and
fixed settlement amount. The model can inspect the term through a targeted
domain tool; the evaluator recomputes it from final dispositions.

## Exact Oracle

For each required slot, the Oracle enumerates:

- keep the active commitment;
- cancel and book each currently available replacement;
- apply each allowed in-place modification;
- book each available option when the slot is empty.

It executes the Cartesian product in fresh environments and rejects tool
errors and hard-goal violations. Feasible plans are compared by:

```text
(recovery_loss,
 lifecycle_cost,
 mutated_prior_commitments,
 state_changing_actions)
```

This is an unweighted lexicographic rule. All plans tied on the complete tuple
are accepted. Commitment preservation is a tie-breaker after objective money,
not a subjective preference that can override it.

The Oracle result records raw candidate count, feasible-plan count,
feasible-scope count, all loss levels, every optimal plan, and every optimal
scope. Results are cached during a process so validation and baselines do not
repeat identical exhaustive searches.

## Challenge quality gates

Every v0.5 `loss_aware` task must have at least:

- 100 raw candidate repairs;
- 8 goal-satisfying repairs;
- 4 feasible repair-scope patterns;
- 3 recovery-loss levels.

The checked-in tasks have 486–729 raw candidates, 18–235 feasible plans,
4–30 feasible scopes, and 4–30 loss levels.

## Metrics

Primary:

- **Goal Pass@1** and **Goal Pass^5**;
- **Optimal Pass@1** and **Optimal Pass^5**;
- **Scope-Optimization Gap** = Goal Pass − Optimal Pass;
- **Extra Loss** = observed recovery loss − minimum feasible recovery loss;
- **Financial Regret** = observed lifecycle cost − minimum feasible lifecycle
  cost.

Diagnostics:

- nearest optimal-scope distance;
- over-repair and under-repair;
- cancellation, recovery-waste, and linked-loss components;
- action count and tool errors;
- correct infeasibility.

Bootstrap confidence intervals by family, not by treating paired prompts or
counterfactual twins as independent examples.

## Paired tasks and mechanism splits

Each v0.5 failure state appears twice:

- `goal`: asks only for the complete hard goal;
- `loss_aware`: naturally asks to avoid non-refundable or linked losses.

The environment and Oracle are identical within a pair. Report tracks
separately to determine whether models preserve commitments spontaneously or
only when the user requests it.

Splits are causal-mechanism based:

- `dev`: travel package breakage;
- `test`: product compatibility cascade;
- `heldout`: service-contract cascade.

Never place one member of a counterfactual family in training and its twin in
test.

## Gold isolation and fairness

Public task JSON contains no expected feasibility, optimal scope, optimal
plan, or objective result. `data/gold/*.json` is evaluator-only.
`build_user_prompt` serializes an explicit allowlist rather than the task.

The agent must join facts from record details, parameterized inventory
searches, cancellation/exchange previews, compatibility checks, and linked
terms. No tool returns the evaluator's global recovery loss or solution.

Use identical prompts, tools, 15-turn budgets, explicit model IDs, and
provider settings. Retain raw per-episode JSONL. One run is a smoke test; the
official result uses five independent runs.
