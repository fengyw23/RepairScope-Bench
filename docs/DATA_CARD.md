# RepairScope-Bench v0.6 Data Card

## Summary

RepairScope-Bench v0.6 contains 24 fixed post-failure states across six task
families and two executable STATE-Bench domains. It measures whether an agent
can inspect persisted commitments, finish the user's hard goal, and avoid an
economically dominated recovery.

| Split | Tasks | Families represented |
|---|---:|---:|
| dev | 8 | 6 |
| test | 8 | 6 |
| heldout | 8 | 6 |
| total | 24 | 6 |

There are 12 travel tasks and 12 customer-support tasks. Each family has two
counterfactual pairs:

- `refund-low` versus `refund-full`;
- `penalty-none` versus `penalty-high`.

Within a pair, the executable starting state, inventory, instruction, prefix,
and failure are identical. Only the named economic term differs.

## Unit of evaluation

One JSON file is one independently constructed failure state, not a second
prompt over a shared hidden state. Important public fields are:

| Field | Meaning |
|---|---|
| `schema_version` | `0.6` |
| `task_id`, `family_id`, `variant_id` | task and counterfactual identity |
| `split` | `dev`, `test`, or `heldout` |
| `instruction` | model-visible natural-language request |
| `initial_snapshot` | clean executable state before prefix writes |
| `pre_failure_trace` | actual successful prefix calls and results |
| `prefix_ledger` | transaction record produced by those calls |
| `latest_failure` | actual failed call and returned error |
| `failure_snapshot` | authoritative model starting state |
| `snapshot_sha256` | canonical hash of that state |
| `boundary_commitments` | audit metadata for prior commitments |
| `contracts` | item-level refund, bundle, licence, or service terms |
| `constraints` | evaluator-only deterministic hard-goal DSL |
| `oracle_actions` | evaluator-only semantic actions |
| `candidate_scopes` | independent gold-enumerator inputs |
| `max_turns` | 15 |

The public benchmark files include evaluator fields for reproducibility. The
runner constructs model input explicitly and does not expose constraints,
semantic actions, economic totals, or gold.

## Construction pipeline

For every task, `scripts/build_v06.py`:

1. creates a clean STATE-style database;
2. invokes the same write tools available to models;
3. records successful results and ledger entries;
4. injects an inventory, compatibility, or policy change;
5. invokes the intended failing operation and asserts failure;
6. serializes and hashes the failure state;
7. reloads it and checks exact state and ledger equality;
8. solves it with semantic state search and independent scope enumeration;
9. releases it only if both methods agree.

Travel uses the upstream `TravelEnvironment`. Customer-support tasks use the
upstream `CustomerSupportEnvironment` and real `Order`/`OrderItem` records.
Composition-based extensions supply restaurant or service reservations,
alternative purchases, compatibility relations, and cross-order contracts.
The upstream runtime is imported rather than copied.

## Task requirements

The generator and validator enforce:

- at least three hard-goal-feasible semantic recovery scopes;
- both local and non-local recovery;
- at least one feasible but economically dominated distractor;
- each hard constraint filters at least one real available option;
- two interacting loss mechanisms in difficult variants;
- a scope flip in each single-fact counterfactual pair;
- a reference solution that fits within the 15-turn protocol.

The six families are conference dinner, destination-linked ground plan,
shortened trip, radiology workstation, clinic cold chain, and media
production kit.

## Gold

`data/gold/v06.json` contains all non-dominated terminal states, their
two-dimensional economic vectors, changed commitments, and replayable raw
tool calls. It does not prescribe one trajectory.

The bounded search expands domain-semantic actions. A separate enumerator
replays declared candidate scopes. Tasks are rejected if their feasible
scope sets or Pareto frontiers differ. If a model nevertheless finds a
strictly better feasible point, evaluation emits `oracle_violation` and
excludes the case instead of punishing the model.

## Data quality and reproducibility

`repairscope validate data/v06` checks:

- schema, tool and hash integrity;
- prefix and failed-call replay from the clean snapshot;
- persistence and ledger equality after reload;
- constraint effectiveness;
- pair isomorphism outside the designated fact;
- expected Pareto-scope flips;
- independent Oracle agreement;
- baseline separation.

The checked-in release passes 56 unit and integration tests. Rebuilding is
deterministic under the pinned STATE-Bench revision.

## Intended and out-of-scope uses

Intended uses include evaluation of tool-using agents, repair-policy
ablations, query/action error analysis, and comparison of feasibility with
recovery quality.

The benchmark does not measure pre-failure planning, open-world user
preference elicitation, subjective utility, irreversible real-world harm, or
production safety. Prices and policies are synthetic. Results should not be
interpreted as a claim that the agent can safely operate real accounts.

## Legacy data

The v0.4 pilot and v0.5 challenge set are archived under
`data/legacy/v0.5`. They remain covered by regression tests but are not the
default benchmark.
