# Evaluation Protocol

## Episode

1. Reset to the public `failure_snapshot`.
2. Give the agent only the instruction, failure observation, public
   pre-failure trace, and tools.
3. Serialize side-effecting tool calls and enforce `max_actions`.
4. Stop on `finish`, `report_infeasible`, or a budget.
5. Recompute terminal constraints, financial ledgers, scope, and oracle.

Each repetition uses a fresh deep copy. No state is shared across runs.

## Hard goal

A feasible task requires exactly one active commitment per required slot, all
slot/cross-slot constraints, every lifecycle budget, and terminal `finish`.

For an infeasible task, the exhaustive solver must find no valid repair, the
agent must call `report_infeasible`, and the exact public commitment snapshot
and post-failure cash ledger must remain unchanged. Queries and failed writes
are harmless; a successful mutation followed by an infeasibility report is not.

## Auditable ledgers

All values are computed from deterministic transaction records.

```text
financial_delta =
    post-failure charges
  + in-place modification net cash
  - refunds of prior commitments
  - refunds of post-failure commitments

lifecycle_cost = pre-failure spend + financial_delta

cancellation_loss =
  sum(price_paid - refund_received for cancelled prior commitments)

post_failure_waste =
  sum(price_paid - refund_received for post-failure bookings later cancelled)

recovery_loss =
    cancellation_loss
  + post_failure_waste
  + max(0, total modification net cash)
```

`recovery_loss` does not call a useful retained replacement “waste.” A refund
can reduce `lifecycle_cost`, but it cannot manufacture negative recovery loss.
Modification credits offset modification charges through their full net cash
effect; fees are not counted twice.

## Oracle and objective

For each required slot, the solver enumerates keep, available replacement,
allowed in-place modification, and booking into an empty slot. It replays the
Cartesian product in fresh environments and rejects tool errors and hard-goal
violations.

The task declares a lexicographic objective. Pilot v0.2 uses:

```text
(recovery_loss,
 mutated_prior_commitments,
 lifecycle_cost,
 state_changing_actions)
```

This is not a weighted utility score. The evaluator compares the complete
tuple; comparing only the first scalar would incorrectly mark some
over-repairs as optimal. All exact ties are accepted.

## Metrics

Primary:

- **Goal Pass@1**: correct final state and terminal mode;
- **Optimal Repair Rate**: goal pass plus exact oracle objective;
- **Extra Loss**:
  `observed_recovery_loss - minimum_feasible_recovery_loss`;
- **Financial Regret**:
  `observed_lifecycle_cost - minimum_feasible_lifecycle_cost`;
- **Family Success**: every counterfactual variant in a family succeeds.

`extra_loss` and `financial_regret` answer different questions. A valid plan
can preserve an explicit commitment preference and therefore cost more than a
global re-shopping plan; neither number should be silently substituted for the
other.

Scope diagnostics:

- nearest optimal-scope distance;
- over-repair and under-repair;
- cancellation loss and post-failure waste;
- action count and tool errors;
- correct infeasibility rate.

Bootstrap confidence intervals by family, not by treating near-duplicate
variants as independent examples.

## Gold isolation

Public task JSON contains no `expected_oracle`, optimal plan, or optimal scope.
`data/gold/pilot.json` is evaluator-only. `build_user_prompt` uses an explicit
allowlist and never serializes the full task. `repairscope validate` recomputes
the gold from public mechanics and checks the checked-in file for drift.

## Provider fairness

- use an explicit provider and model ID;
- use identical task context, tools, budgets, and terminal rules;
- force sequential tool calls because operations have side effects;
- record every model tool call and tool result;
- report provider failures separately from task failures;
- retain raw per-episode JSONL and aggregate only afterward.

The checked-in provider protocol tests use deterministic mock HTTP responses.
Live provider access is deliberately not part of CI because it requires user
credentials, incurs cost, and would not be deterministic.
