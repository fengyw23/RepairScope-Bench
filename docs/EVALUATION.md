# RepairScope-Bench v3.0 Evaluation Protocol

## Full-recovery track

Every episode begins from a deep copy of the same hashed failure snapshot.
The agent receives a normal domain prompt, natural customer request, compact
successful prefix trace, latest failed call, and eight public tools. It must
investigate and execute a complete recovery within 15 model turns.

The agent does not receive the hard-goal DSL, private evidence graph,
intervention, candidate scopes, aggregate costs, or gold. There is no
`finish()` tool. Scoring begins when the model stops calling tools or reaches
the turn limit.

The official system prompt explicitly asks the agent to satisfy all still
active requirements while minimizing actual net monetary cost from the
failure boundary. A neutral prompt without that sentence may be reported as a
task-understanding ablation, not as the primary leaderboard condition.

## Hard goals

The deterministic evaluator checks:

- exact capability quantities;
- location, delivery site, and deadline attributes;
- product, service, and itinerary compatibility;
- required bridge or companion components;
- absence of duplicate or conflicting active coverage;
- database references and transaction-ledger integrity.

Every checked atom has a model-visible evidence path. No LLM judge is used.

## Incremental Recovery Cost

All calculations use signed integer cents:

```text
Incremental Recovery Cost
  = post-boundary purchases
  + modification, cancellation, return, migration, and activation fees
  + discount, rebate, or package clawbacks
  + explicit-horizon recurring charges
  - actual refunds
  - immediately usable credits and compensation
```

Pre-boundary payments are sunk and are not counted again. A refund is
subtracted once; its unrecovered portion is not separately added as a second
loss. A free migration or inactive licence consequence has zero cost until an
actual monetary event occurs.

Example: cancelling a paid item yields an `$800` refund and its replacement
costs `$900`; the recovery cost is `$100`, not `$100` plus a separately
invented non-refundable-loss term.

## Unique scope gold

The Oracle first enumerates all hard-goal-feasible final commitment sets and
computes the minimum cost reachable for each native scope signature:

- travel: dispositions and additions for flight, hotel, transfer, local
  service, admission, restaurant, and related reservations;
- after-sales: dispositions and additions for order items, products,
  warranties, licences, and services.

It then replays each scope through public tools and recomputes the cost from
the transaction ledger. A task is eligible only if:

1. exactly one scope has minimum cost;
2. no different scope ties it;
3. its margin over the runner-up is at least
   `max($10, 1% of boundary paid value)`;
4. the uniqueness does not depend on irrelevant state;
5. the paired one-fact variant has a different unique scope.

Gold does not prescribe query order or mutation order. Necessary legal
operation orders are constructed to be economically equivalent.

## Primary metrics

### Goal and scope

- `Goal Pass@1`: fraction of individual runs satisfying every hard goal;
- `Goal Pass^5`: fraction of tasks solved in all five independent runs;
- `Unique Scope Pass@1`: fraction satisfying goals and ending in the unique
  gold scope;
- `Unique Scope Pass^5`: fraction obtaining Unique Scope Pass in all five
  runs;
- `Counterfactual Pair Success`: both variants pass in the matched repeat;
- `Over-Repair` and `Under-Repair`: incorrect changes to prior commitments.

### Economic execution

- `Incremental Recovery Cost`: actual ledger cost after the boundary;
- `Cost Regret`: actual cost minus gold minimum cost;
- `Clean Execution`: Unique Scope Pass and zero Cost Regret;
- `Execution Waste`: positive Cost Regret when the final scope is correct.

These metrics separate a range-selection error from a trajectory error. If an
agent buys an unnecessary option, pays its disclosed cancellation fee, and
then reaches the gold scope, it passes `Unique Scope Pass` but fails
`Clean Execution`.

### Diagnostics

Report changed-fact acquisition before first mutation, tool errors, invalid
identifiers, turn exhaustion, final constraint failures, scope distance, and
state-changing action count. Diagnostics do not replace primary metrics.

## Baselines

The release reports:

- no repair;
- local-only repair;
- dependency repair;
- full rollback;
- minimum changed commitments;
- lowest advertised new-purchase price;
- largest gross refund;
- exact incremental-cost Oracle.

Local, dependency, full rollback, minimum changes, sticker price, and
refund-only strategies must each remain below 65% Unique Scope Pass. The
Oracle must obtain 100% Goal, Scope, and Clean Execution.

## Official experiments

Run five independent episodes per task. Record the exact model identifier,
provider or gateway, date, system-prompt condition, reasoning setting, token
limit, turn limit, timeout, and retry policy. Provider errors and timeouts
remain failures in the denominator.

Report aggregate results and breakdowns by domain, reasoning structure,
derived complexity level, and changed-fact acquisition. Cluster uncertainty
over the 40 base scenarios and use matched paired analysis for the two
counterfactual variants; do not treat 80 paired tasks as 80 independent
counterfactual samples.
