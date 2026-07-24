# Evaluation Protocol

## One public track: full recovery

v1.1 has no gold-state execution subtrack and no text-only scope-choice
subtrack. Every leaderboard episode requires the model to investigate and
execute a complete recovery from the fixed failure state.

Every run starts from a deep copy of the hashed snapshot. The model receives:

- a normal domain-agent system prompt;
- the natural customer request;
- the successful pre-failure tool trace;
- the latest failed call and result;
- eight domain tools.

It does not receive hard goals, reasoning labels, pair identity, the
intervention, inventory dumps, contract dumps, economic totals, candidate
scopes, or gold. It must query those facts.

The limit is 15 model turns. There is no mutation budget or `finish()` tool.
When the model stops or reaches the limit, the evaluator reads persistent
state. Asking the user to decide is not a valid completion action.

## Hard goals

The deterministic evaluator checks:

- minimum and maximum functional capability quantities;
- deadlines, locations, service regions, and explicit horizons;
- option compatibility, required companions, and bridge requirements;
- no conflicting or duplicate exact capability coverage;
- stated active-value limits and referential integrity.

Only goal-satisfying outcomes enter economic quality evaluation.

## Economic vector

All amounts use integer cents.

```text
irreversible_loss =
    unrecovered value of changed boundary commitments
  + triggered settlement, threshold, licence, warranty, or migration charges
  + unrecovered value of unnecessary post-boundary purchases

net_recovery_outlay =
    post-boundary purchases and explicit-horizon recurring charges
  + post-boundary fees and settlements
  - refunds
```

Outcome A dominates B when A is no worse on both dimensions and strictly
better on at least one. Every non-dominated outcome is accepted. No exchange
rate between the two dimensions is assumed.

## Primary metrics

- Goal Pass@1 and Goal Pass^5;
- Non-Dominated Repair Pass@1 and Pass^5;
- Dominated Repair Rate among goal completions;
- Irreversible-Loss Regret;
- Net-Outlay Regret;
- Counterfactual Pair Success.

Counterfactual Pair Success requires both variants of the same base scenario
to obtain Non-Dominated Repair Pass in the same repeat. Because the variants
differ in one hidden, queryable fact and have different accepted scopes, a
fixed scope policy cannot pass the pair.

The public report may also diagnose over-repair, under-repair, correct scope
with wasteful execution, missing investigation, tool errors, and turn
exhaustion. These are analyses of the same full-recovery episodes, not
separate benchmark tracks.

## Oracle and validity

The first Oracle enumerates all feasible sets of retained commitments and
available options, then applies hard constraints and final-state contract
logic.

The second Oracle independently searches executable public-tool state
transitions and recomputes economics from the resulting transaction ledger.
A task is rejected if the frontiers differ.

Necessary operations are economically order-invariant. Extra actions still
count: a model that buys and discards an unnecessary option can have the
correct final scope but a dominated execution.

## Baselines and release gates

Reported weak strategies:

- no repair;
- local repair;
- dependency repair;
- full rollback;
- minimum changed commitments;
- lowest advertised new-purchase price;
- largest gross refund;
- Pareto Oracle.

Local repair, full rollback, minimum changes, sticker price, and refund-only
must each remain below 65% Non-Dominated Repair Pass. Exact minimization of
irreversible loss or net outlay is reported only as an analytical upper
bound: after correct tie-breaking, a global minimum of either Pareto
dimension is necessarily non-dominated.

Dataset-level release gates also require:

- 160 tasks and 80 pairs;
- ten balanced reasoning structures;
- every structure represented equally in all four domains;
- at least three semantic feasible scopes per task;
- at least one dominated feasible terminal per task;
- at least 40% multi-point frontiers;
- at least 40% positive-loss accepted solutions;
- at least 30% tasks that reject a one-step added option;
- exact boundary replay, snapshot hashes, and dual-Oracle agreement;
- a scope-changing single-fact intervention for every pair.

## Official experiments

Run five independent episodes per task. Report the exact model identifier,
provider or gateway, date, token and turn limits, reasoning settings, and
endpoint class. Provider errors remain failures in the denominator.

Report uncertainty clustered over the 80 base scenarios and paired analysis
for the two variants. Do not treat 160 paired tasks as 160 independent
samples.
