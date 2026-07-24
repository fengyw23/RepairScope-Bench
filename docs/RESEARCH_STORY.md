# Research Story: Repair Scope After Commitments Exist

## Motivation

A tool agent may already have booked a flight and hotel, purchased equipment,
activated a licence, or contracted a vendor before a later action fails.
Recovery is therefore not only “find another way to complete the missing
step.” It also changes real commitments, refunds, fees, compatibility, and
future payments.

Consider a trip to a Shanghai conference. The flight, hotel, transfer, and
conference admission are active; the restaurant booking fails. Replacing the
restaurant may be enough. A different hotel-and-restaurant combination may
be cheaper after refunds. But cancelling the flight usually destroys a
commitment that still serves the central goal. The failed step identifies
what needs attention; it does not determine how far recovery should roll
back.

## Research question

> From a reachable post-failure state with persistent commitments, can an
> agent investigate distributed facts, satisfy the remaining hard goals, and
> avoid a repair scope that another feasible outcome objectively dominates?

This is narrower and more testable than “value-aware recovery.” Objective
dominance uses two auditable quantities—irreversible loss and net recovery
outlay—and accepts every Pareto non-dominated result. It does not ask
annotators to assign subjective utility weights.

## Gap relative to adjacent benchmarks

Existing work may test whether an agent can undo side effects, recover from a
dynamic event, re-execute affected steps, or reach a prescribed database
state. Those capabilities are necessary, but they do not isolate whether the
agent chose the right set of already-successful commitments to keep, modify,
or cancel.

RepairScope-Bench fixes the failure boundary across models and makes the
prior effects executable and persistent. Unlike text-only replanning, every
decision changes state and a transaction ledger. Unlike a prescribed target
state, all Pareto non-dominated terminal states are accepted.

The novelty claim is benchmark formulation and deterministic measurement,
not the invention of partial rollback.

## Why organize by reasoning structure

Refunds, licences, discounts, and deposits are surface carriers. v1.1 instead
organizes tasks by ten reusable reasoning structures:

- separating sunk from recoverable value;
- propagating economic effects through multiple records;
- protecting commitments shared by several goals;
- computing non-linear thresholds;
- evaluating Boolean contract conditions;
- selecting a partial quantity;
- comparing a bridge repair with upstream replacement;
- choosing a compatible bundle jointly;
- aggregating recurring cost over an explicit horizon;
- recognizing genuine multi-point Pareto trade-offs.

Every structure appears in every domain, and the same carrier appears under
different structures. A single-fact counterfactual pair changes one hidden,
queryable fact and changes the accepted scope. Pair success therefore tests
whether the model adapts its reasoning, rather than repeating “always repair
locally” or “always choose the cheapest listed option.”

## Intended empirical claim

The central result should separate execution success from scope quality:

```text
Goal Pass is materially higher than Non-Dominated Repair Pass
+ Counterfactual Pair Success is lower than per-task success
= agents often complete the task but fail to reason reliably about
  which prior commitments should survive.
```

Error analysis can then attribute failures to missing investigation,
multi-hop propagation, threshold or horizon arithmetic, combination search,
scope choice, or wasteful execution.

## Evidence required for a top-conference claim

The repository provides deterministic data and release gates, but a paper
still needs:

- multi-model, five-run experiments;
- clustered confidence intervals over base scenarios;
- paired counterfactual analysis;
- independent human audit of goals, terms, and naturalness;
- prompt paraphrase and entity/option-order perturbation tests;
- execution controls showing that failures are not primarily API confusion;
- preferably additional scenarios authored outside the generator team.

## Claim boundary

v1.1 evaluates recovery after a fixed failure boundary. It does not measure
the quality of pre-failure planning, subjective preference elicitation,
stochastic risk, or production-account safety.

The four domains expose different operations, attributes, and vocabulary but
share a deterministic commitment-and-ledger core. This improves controlled
comparison and exact Oracle coverage, while limiting claims about external
environment diversity. The older v0.6 release retains direct STATE-Bench
runtime integration as a complementary engineering reference.
