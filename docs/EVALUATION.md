# Evaluation Protocol

## Model input

Every run starts from a deep copy of the hashed failure snapshot. The model
receives:

- a normal domain-agent system prompt;
- the natural customer request;
- the successful prefix tool trace;
- the latest failed call and result;
- eight domain-specific tools.

It does not receive hard goals, reasoning labels, the changed-fact manifest,
economic totals, candidate scopes, or gold.

The limit is 15 model turns. There is no mutation budget or `finish()` tool.
When the model stops or exhausts the budget, the evaluator reads state.

## Hard goals

The deterministic evaluator checks:

- minimum and maximum functional capability quantities;
- delivery deadlines and explicit service horizons;
- option compatibility and required component sets;
- no conflicting or duplicate active capability coverage;
- active-value limits.

Only goal-satisfying outcomes enter economic quality evaluation.

## Economic vector

All amounts use integer cents.

```text
irreversible_loss =
    unrecovered value of changed boundary commitments
  + triggered cancellation, threshold, licence, warranty, or settlement charges
  + unrecovered value from unnecessary post-boundary purchases

net_recovery_outlay =
    post-boundary purchases and recurring charges over the stated horizon
  + post-boundary fees and settlements
  - refunds
```

Outcome A dominates B when A is no worse on both dimensions and strictly
better on at least one. Every non-dominated outcome is accepted.

An exact optimizer for either dimension is an Oracle upper bound: after
proper tie-breaking, a global minimum of one Pareto dimension is necessarily
non-dominated. Such controls do not represent simple agent heuristics.

## Metrics

Primary:

- Goal Pass@1 and Goal Pass^5;
- Non-Dominated Repair Pass@1 and Pass^5;
- Dominated Repair Rate among goal completions;
- irreversible-loss and net-outlay regret;
- Counterfactual Pair Success.

Diagnostics:

- over-repair and under-repair;
- correct scope but wasteful execution;
- tool errors and turn exhaustion;
- breakdowns by domain, reasoning structure, and difficulty.

Counterfactual Pair Success requires both alpha and beta variants to obtain
Non-Dominated Repair Pass in the same repeat. Because pair frontiers differ,
this rules out a fixed scope policy.

## Oracle

The terminal solver enumerates all subsets of retained boundary commitments
and compatible inventory options, then applies hard constraints and
order-invariant contract clauses.

The independent solver constructs the same choices separately and replays
actual cancellation and purchase calls through the public environment.
Tasks are rejected if their feasible frontiers differ. A model outcome that
strictly dominates stored gold is marked `oracle_violation` and excluded.

## Baselines

Official baselines:

- no repair;
- local repair;
- dependency repair;
- full rollback;
- minimum changed commitments;
- final sticker price;
- gross refund only;
- exact irreversible-loss Oracle;
- exact net-outlay Oracle;
- Pareto Oracle.

Release gates require local, full rollback, minimum changes, sticker price,
and refund-only strategies to remain below 65% Non-Dominated Pass. Exact
single-objective Oracles are reported as analytical upper bounds and are not
subject to that gate.

## Official experiments

Run five independent episodes per task and report exact model identifiers,
provider, date, token limits, reasoning settings, and endpoint class.
Provider errors remain failures in denominators. Report clustered confidence
intervals over the 80 base scenarios and use paired analysis for alpha/beta
variants.
