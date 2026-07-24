# Evaluation Protocol

## Episode

1. Reset the environment to the task's `failure_snapshot`.
2. Give the agent the original instruction, public pre-failure trace, failure
   observation, and tool interface.
3. Allow up to a declared action budget.
4. Stop on `finish`, `report_infeasible`, or the action limit.
5. Recompute terminal constraints, financial ledgers, prior-commitment
   dispositions, and the task oracle.

Every repetition starts from a fresh deep copy. No state is shared between
models or runs.

## Hard goal

For a feasible task:

- every required slot has exactly one active commitment;
- all slot-level attribute constraints hold;
- all cross-slot compatibility constraints hold;
- total lifecycle cost remains under any declared hard cap;
- the agent terminates with `finish`.

For an infeasible task:

- the exhaustive solver finds no constraint-satisfying plan;
- the agent terminates with `report_infeasible`;
- every pre-failure commitment remains unmodified.

## Ledgers

`lifecycle_cost` is the total amount ultimately retained by providers:

```text
pre-failure spend
+ post-failure charges
+ modification net cash changes
- refunds
```

It is used for hard total-budget constraints.

`repair_loss` measures the cost introduced by recovery:

```text
unrefunded value of cancelled pre-failure commitments
+ post-failure charges
- refunds of post-failure purchases
+ explicit modification fees
```

Refunded principal from an old commitment is not counted as a negative repair
loss. This prevents a free cancellation from appearing to “earn” recovery
credit; replacing a valid commitment still incurs the new purchase cost.

## Oracle

For each required slot the solver enumerates:

- keep the active pre-failure commitment;
- cancel it and book an available replacement;
- apply each available in-place modification;
- book an available option when the slot is empty.

It takes the Cartesian product across slots, replays each plan in a fresh
environment, rejects tool errors and hard-constraint violations, and minimizes:

```text
(repair_loss, mutated_prior_commitments, state_changing_actions)
```

All plans tied on this full tuple are accepted.

## Metrics

### Primary

- **Goal Pass@1**: fraction of tasks with a correct terminal state/mode.
- **Optimal Repair Rate**: fraction that both pass and attain oracle loss.
- **Mean Repair Regret**: mean excess repair loss over successful feasible
  tasks; always report coverage.
- **Family Success**: fraction of counterfactual families for which every
  variant passes.

### Scope diagnostics

Let \(\sigma(c)\) be the terminal disposition of prior commitment \(c\), and
\(\Sigma^*\) the set of oracle-optimal scope maps.

\[
d_{\mathrm{scope}} =
\min_{\sigma^* \in \Sigma^*}
\frac{1}{|C|}
\sum_{c \in C} \mathbf{1}[\sigma(c) \ne \sigma^*(c)].
\]

Also report:

- over-repair count/rate;
- under-repair count/rate;
- unnecessary cancellation value;
- tool error count;
- correct infeasibility rate.

### Counterfactual robustness

- **Family success**: all variants in a family are correct.
- **Flip accuracy**: a decisive changed fact causes the expected scope change.
- **Invariance accuracy**: irrelevant paraphrases leave the scope unchanged
  (not included in v0.1; required for a larger release).

Bootstrap confidence intervals by family, never by treating near-duplicate
variants as independent examples.

## Baselines

The repository includes:

- `no_repair`;
- `local_repair`;
- `dependency_repair`;
- `full_rollback`;
- `oracle`.

A paper evaluation should additionally include a globally re-planning
cost-minimizer, a checkpoint/suffix rollback policy, and frontier tool-using
agents with identical context and action budgets.

