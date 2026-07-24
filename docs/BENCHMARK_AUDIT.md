# Benchmark Mechanism Audit

This note records a code-level comparison performed against the public
STT-Arena and STATE-Bench repositories on 2026-07-24. It separates what the
papers intend from what their released evaluators actually enforce.

## STT-Arena does not lock the model to a prescribed trajectory

STT-Arena tasks contain executable Python environments with hidden trigger
flags. A typical generated task uses an observation call to arm a trigger and
a later operation to fire it. The user goal and system prompt encourage the
model to follow this natural workflow, but the harness does not replay or
require a reference action sequence.

The final evaluator runs task-specific check functions over the terminal
environment state. In the released 227-task dataset, the check functions do
not directly require the internal conflict flag to have fired. Consequently:

- a model that follows the intended workflow encounters the injected change
  and must adapt;
- a model that deviates and misses the required final state fails;
- a model that bypasses the trigger yet reaches the checked final state can
  pass.

This last case is not merely theoretical. In released `task_001`, calling
`get_vehicle_status(VH001)` arms the trigger and a later
`record_cooling_unit_reset(RST1001, ...)` fires it. However, the five terminal
checks only inspect delivery location, goods/shipment delivery status,
arrival time, and clinic receipt. A single direct
`register_goods_receipt(SHP1001, CLN01, 06:30)` call satisfies all five checks
while both conflict flags remain false.

Design implication for RepairScope-Bench: if an end-to-end dynamic track is
added later, the evaluator must verify the causal event and ledger, not just a
terminal state that a shortcut can manufacture. The fixed-failure-state track
avoids this trajectory-control problem by beginning after the disruption.

Sources:

- <https://arxiv.org/abs/2605.18548>
- <https://github.com/Miaow-Lab/STT-Arena>
- <https://huggingface.co/datasets/Miaow-Lab/STT-Arena>

## STATE-Bench is not difficult because every task has a huge database

The released STATE-Bench environments are task-local sandboxes. Useful
empirical state-size proxies are below; “fields” is the sum of top-level
fields across all records in the task's initial database.

| Environment | Records | Fields | Domain tools |
|---|---:|---:|---:|
| Travel Case 121 | 10 | 102 | 17 |
| Travel Case 122 | 8 | 75 | 17 |
| Travel Case 124 | 11 | 95 | 17 |
| Shopping Case 105 | 5 | 73 | 18 |
| All 150 travel tasks, median | 9 | 86.5 | 17 |
| All 150 shopping tasks, median | 24 | 415 | 18 |
| RepairScope pilot, mean | 7.25 commitment/catalog records | 59.2 | 12 |

Five of the records in each selected travel case are user-account rows, most
of which are irrelevant distractors. Raw record count therefore does not
explain the large performance gap.

STATE-Bench is harder in aggregate because it combines:

- 450 heterogeneous tasks across travel, shopping, and customer support;
- natural opening messages rather than an explicit evaluator objective;
- a simulated user that withholds some information until asked;
- domain-specific search, detail, policy, preview, and write operations;
- exact mutation requirements, including preservation of booking preferences
  and argument values;
- LLM-judged conversational/procedural requirements conjoined with
  deterministic state requirements;
- a 15-turn domain budget;
- five official runs, with both average Pass@1 and strict Pass^5.

Cases 121 and 122 are not optimization tasks. Their expected replacement is
fixed by the authored task requirements and sandbox inventory. They provide
useful coordination structures, but importing only their story does not
import the difficulty of the full benchmark.

Sources:

- <https://github.com/microsoft/STATE-Bench>
- <https://github.com/microsoft/STATE-Bench/blob/main/docs/RUN_BENCHMARK.md>
- <https://github.com/microsoft/STATE-Bench/blob/main/state_bench/domains/travel/tasks/121-change_flight_cascade_replace_hotel.json>
- <https://github.com/microsoft/STATE-Bench/blob/main/state_bench/domains/travel/tasks/122-shortened_trip_cancel_hotel_replace_car_dates.json>

## Tool-return comparison

STATE-Bench's responses are fairly clean structured API results. For example,
the hotel cancellation preview directly returns `cancellation_fee`,
`refund_amount`, and a policy reason. Search results expose prices and booking
details expose preferences. Therefore, “structured and readable output” is
not itself a defect.

STT-Arena has task-specific generated tools. Results are often larger nested
objects containing connected entities. Some failure messages are also highly
directive; for example, `task_001` explicitly tells the model to queue or
retry when maintenance bays are occupied.

RepairScope-Bench currently compresses the world more aggressively:

- one generic `search_options(slot)` operation serves every domain;
- one generic compatibility operation returns the decisive Boolean;
- `get_cancellation_quote` returns the derived `irrecoverable_loss`, rather
  than only the source price/refund facts;
- `get_cost_summary` exposes an objective-aligned aggregate;
- most tasks have only one feasible repair, so exploration is shallow.

The correction is not to add noisy prose. It is to expose realistic source
facts through domain operations and require the agent to join them:

1. reservation/product detail;
2. policy lookup or cancellation preview;
3. filtered inventory search;
4. compatibility/schedule checks;
5. transaction execution and final verification.

The evaluator may compute global recovery loss, but the agent should not
receive that evaluator-side aggregate directly.

## Extra-loss coverage in pilot v0.3.2

The current 12 feasible tasks have feasible-plan counts:

```text
1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 1, 2
```

Only two tasks contain feasible repairs with different recovery losses:

- `short-trip-c-modify-car`: 30 versus 210;
- `workstation-c`: 0 versus 1200.

`destination-hotel-b` has two feasible repairs, but both have zero recovery
loss; lifecycle cost breaks the tie. Nine feasible tasks admit only one
feasible plan. The pilot therefore mostly tests discovery of the only valid
continuation, not loss-sensitive repair-scope selection.

A loss-sensitive task must contain at least two goal-satisfying repairs whose
recovery-loss values differ. The facts producing the difference must be
discoverable through tools, and the final score must be recomputed from the
transaction ledger. Suitable mechanisms include:

- modify in place for a fee versus cancel/rebook with a larger non-refundable
  loss;
- retain a valid prior commitment and add a compatible bridge versus replace
  the commitment and pay a restocking/cancellation charge;
- cancel one of several coupled reservations, where only one has a penalty;
- reserve a replacement before releasing the old resource versus cancel
  first and lose an expiring discount or availability guarantee;
- repair a downstream item versus replace an upstream bundle, with objective
  disposal/restocking/shipping losses attached to the latter.

Each mechanism should be emitted as a matched counterfactual family that
changes one policy or compatibility fact and flips the oracle-optimal scope.

## Official scoring protocol

Starting in v0.3.2, `run-suite` defaults to five independent runs per task and
reports:

- Goal Pass@1 and Goal Pass^5;
- Optimal Pass@1 and Optimal Pass^5;
- extra loss and financial regret;
- provider errors, which count as failed episodes in the pass denominators.

One-run results are smoke tests and must not be presented as headline model
performance.

## v0.4.0 corrective implementation

The v0.4.0 release implements the audit recommendations:

- plain travel/shopping customer-service prompts replace the explicit
  evaluator-objective instruction;
- models receive domain-specific STATE-style operations and at most 15 turns;
- global cost summaries and model-visible `irrecoverable_loss` are removed;
- cancellation/return previews expose only paid amount, refund, and fee;
- all 12 feasible cases have at least two goal-satisfying repairs with
  different recovery-loss values;
- dataset validation rejects any future `loss_sensitive` task that fails that
  competition requirement.
