# Data Card

## Dataset summary

RepairScope-Bench v0.1 contains 16 executable post-failure recovery tasks:

- 4 independent causal families;
- 4 counterfactual variants per family;
- 12 feasible tasks and 4 infeasible tasks;
- 12 travel tasks and 4 shopping tasks.

Every task starts at a standardized failure boundary. It contains an original
instruction, a public canonical tool trace, an authoritative failure snapshot,
a structured catalog, modification policies, hard constraints, and
evaluator-only oracle regression fields.

## Unit of evaluation

The statistical unit is a **counterfactual family**, not an individual JSON
file. Variants within a family share the same causal skeleton. Future train,
development, and test splits must keep an entire family in one split.

## Construction

The pilot generator is checked in at `scripts/build_pilot.py`. It creates four
families:

1. a trip package whose final car booking fails;
2. a destination change whose replacement hotel sells out;
3. a shortened trip whose car date change fails;
4. a workstation whose dock order is voided by a compatibility check.

Each family changes refundability, availability, price, a hard constraint, or
an explicit modification policy so that the correct scope changes.

The task-level `expected_oracle` is not used to score an agent. It is a public
regression assertion. Dataset validation recomputes feasibility, minimum loss,
and optimal scopes from the executable state.

## Public model context vs evaluator-only fields

Recommended model context:

- `instruction`;
- `failure_observation`;
- `pre_failure_trace`;
- tool schemas and tool responses.

Evaluator only:

- `expected_oracle`;
- enumerated oracle plans;
- aggregate validation results.

The `failure_snapshot` is authoritative environment state. It can be supplied
as a compact initial observation or accessed only through `query_state`,
depending on the experiment; the choice must be reported.

## Field guide

| Field | Meaning |
|---|---|
| `task_id` | Globally unique task identifier |
| `family_id` | Counterfactual grouping key |
| `variant_id` | Variant within a family |
| `source_inspiration` | Source case and transformation disclosure |
| `instruction` | User's persistent goal and hard constraints |
| `failure_observation` | Structured natural-language tool failure |
| `pre_failure_trace` | Canonical externally visible tool calls/results |
| `failure_snapshot.commitments` | Active persistent side effects at the boundary |
| `catalog` | Post-failure options, prices, availability, and attributes |
| `modification_rules` | Allowed in-place changes and explicit costs |
| `required_slots` | Components that the final solution must fill |
| `constraints` | Deterministically checked terminal conditions |
| `objective` | Lexicographic optimization semantics |
| `expected_oracle` | Generator regression assertion |

## Intended use

- diagnose post-commit repair-scope selection;
- compare recovery prompting or planning methods;
- test whether a policy reacts correctly to minimal counterfactual changes;
- develop state, ledger, and solver-based evaluators.

## Out-of-scope use

- claiming end-to-end agent reliability;
- evaluating failure detection before the supplied boundary;
- treating the 16-task pilot as a statistically meaningful leaderboard;
- training on the public pilot and reporting it as held-out evaluation;
- interpreting simulated vendor prices or policies as real-world facts.

## Known limitations

- limited domains and causal templates;
- synthetic, compact transactional APIs;
- no concurrent external actors after the failure boundary;
- no user clarification tasks in v0.1;
- an exhaustive solver that does not yet scale to large catalogs;
- no released model runs or human agreement study.

## Expansion requirements

A paper-scale release should add:

- at least 30–50 independent causal templates;
- procurement, event planning, customer support, and enterprise workflows;
- compatibility, temporal, budget, refund, partial-success, and permission
  mechanisms;
- required clarification and approval cases;
- template-disjoint splits and adversarial paraphrases;
- a second independent oracle implementation;
- human verification that natural-language facts faithfully express the
  structured state;
- end-to-end twins as a separate track.

