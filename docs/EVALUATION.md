# Evaluation Protocol

## Controlled starting point

Every run begins from a deep copy of the task's hashed failure snapshot. The
agent receives a normal service-agent system prompt, the customer request, a
compact trace of prior successful writes, the failed call and its result, and
domain tools. It does not receive the hard-constraint DSL, objective vector,
global economic summary, candidate scopes, or Oracle trajectory.

The official limit is 15 model turns. There is no separate mutation budget
and no benchmark-specific `finish()` tool. When the model stops calling tools
or reaches the turn limit, the evaluator reads the persistent terminal state.

## Hard-goal evaluation

The deterministic constraint DSL supports:

- exact active-record counts by semantic slot;
- record status, quantity, time, location, deadline, and budget;
- permitted option attributes;
- flight/hotel/ground-transport consistency;
- product/accessory/software/service compatibility;
- duplicate and conflict prevention;
- database reference and ledger integrity.

Constraints describe what the customer must receive. They must not require
unmentioned records to remain unchanged or otherwise encode an author-chosen
repair trajectory.

`Goal Pass` is true only if every hard constraint and business-policy check
passes.

## Economic vector

For each goal-satisfying terminal state, the evaluator derives two values
solely from executed transaction records and visible contract terms:

```text
L = irreversible_loss
O = net_recovery_outlay
```

`L` includes cancellation/modification fees, non-refundable value, bundle or
licence clawbacks, and recovery purchases that were later wasted. `O` is all
post-boundary payments, fees, and settlements minus refunds and compensation.
Amounts paid before the standardized failure boundary are sunk and are not
silently charged again.

There is no scalar combination of `L` and `O`.

## Pareto acceptance

Feasible outcome A dominates feasible outcome B exactly when:

```text
A.L <= B.L and A.O <= B.O
and at least one inequality is strict
```

`Non-Dominated Repair Pass` requires Goal Pass and membership in the Pareto
frontier. Every non-dominated terminal state is accepted, regardless of which
trajectory produced it.

If a model reaches a feasible vector that strictly dominates all stored
frontier points, the evaluator marks `oracle_violation=true`,
`exclude_from_aggregate=true`, and preserves the trace for adjudication.

## Oracle

The primary Oracle performs bounded graph search over normalized persistent
states. Its actions are domain-semantic operations—keep, change, cancel and
rebook a travel record; keep, return, exchange, cancel or replace a purchased
item; and update linked contracts. Each semantic action expands to public
tool calls. Economically dominated prefixes at an identical normalized state
are pruned.

An independent candidate-scope enumerator replays separately declared tool
sequences. Both solvers must agree on feasible scopes and the Pareto frontier.
Gold stores all accepted terminal states and replay traces.

## Metrics

Official aggregate metrics:

- `Goal Pass@1`: mean success across all runs;
- `Goal Pass^5`: fraction of tasks solved in all five runs;
- `Non-Dominated Repair Pass@1`;
- `Non-Dominated Repair Pass^5`;
- `Dominated Repair Rate`: dominated outcomes among goal completions;
- `Irreversible-Loss Regret`;
- `Net-Outlay Regret`.

Diagnostic fields include changed prior commitments, over-repair,
under-repair, nearest-frontier scope distance, tool errors, model stopping,
turn exhaustion, provider error, and Oracle violation.

Provider failures remain in the denominator as failures. Oracle-violation
cases are excluded as specified above.

## Baselines

The release includes:

| Baseline | Policy |
|---|---|
| no repair | preserve the failed state |
| local repair | change only the failed component |
| dependency repair | repair the declared dependency closure |
| full rollback | choose the broadest replacement scope |
| sticker price | optimize visible final prices |
| refund only | optimize immediate refund |
| Pareto Oracle | execute a non-dominated gold trace |

Run them with:

```bash
repairscope run-baselines data/v06
```

The task release is valid only if the Pareto Oracle passes every case and the
heuristics exhibit both goal completion and scope-quality separation.

## Official model experiment

Run each task independently five times at the provider's documented sampling
settings and report exact model identifiers, date, token limits, reasoning
configuration, and provider endpoint class. Preserve `runs.jsonl` and
`summary.json`. Report Goal Pass and Non-Dominated Repair Pass together;
reporting only the second can hide execution failures, while reporting only
the first hides dominated repair.
