# RepairScope-Bench v1.0 Data Card

## Summary

RepairScope-Bench v1.0 contains 160 fixed post-failure tasks derived from 80
single-fact counterfactual pairs. It evaluates whether an agent can satisfy
hard goals while avoiding an economically dominated recovery scope.

| Dimension | Distribution |
|---|---|
| Domains | 40 tasks each in travel, after-sales, SaaS, event logistics |
| Reasoning structures | 16 tasks for each of ten structures |
| Splits | 48 dev, 48 test, 64 heldout |
| Difficulty | 32 L1, 56 L2, 48 L3, 24 L4 |
| Pareto structure | 60% multi-point frontiers |
| Positive-loss gold | 60% of tasks |

The statistical unit for counterfactual analysis is the 80 base scenarios,
not 160 independent observations.

## Reasoning matrix

The primary labels are reasoning structures rather than fee names:

- sunk versus marginal cost;
- multi-hop impact propagation;
- shared commitments;
- non-linear thresholds;
- conditional contracts;
- partial quantities;
- bridge repair;
- joint bundle selection;
- explicit-horizon recurring cost;
- Pareto trade-offs.

Each appears in all four domains. Economic carriers are deliberately crossed
with structures to reduce surface-template shortcuts.

## Task schema

Important public fields:

| Field | Meaning |
|---|---|
| `schema_version` | `1.0` |
| `task_id` | opaque task identifier |
| `scenario_id` | shared base-scenario identifier |
| `counterfactual_pair_id` | paired-analysis identifier |
| `variant_role` | opaque alpha/beta role; never shown to the model |
| `domain` | one of four tool domains |
| `reasoning_structure` | evaluator metadata; not shown to the model |
| `instruction` | natural customer request |
| `pre_failure_trace` | successful public write calls |
| `latest_failure` | actual unavailable-option call |
| `failure_snapshot` | authoritative persistent starting state |
| `snapshot_sha256` | canonical state hash |
| `inventory` | tool-queryable alternatives |
| `contracts` | tool-queryable economic clauses |
| `hard_goals` | deterministic evaluator constraints |
| `changed_fact` | pair-audit metadata |

There are no authored `oracle_actions` or `candidate_scopes`.

## Construction

The builder creates commitments with public write tools, records the prefix
ledger, executes the failed call, and hashes the state. Each pair changes one
refund or linked-term amount while preserving the task story and operational
structure.

Necessary changes are order-invariant: contract triggers depend only on the
monotonically growing set of changed boundary commitments. Extra model
mutations remain charged and are diagnosed separately.

## Gold

`data/gold/v1.json` contains:

- all hard-goal-feasible terminal assignments;
- all Pareto non-dominated outcomes;
- an independently replayed frontier;
- economic vectors, scopes, state hashes, and public-tool witness traces.

The primary solver enumerates terminal assignments directly from raw
capabilities and constraints. The independent solver enumerates legal
mutations and executes them through the public runtime. Release validation
requires exact frontier agreement.

## Provenance and limitations

Travel and after-sales adapters follow STATE-Bench-style workflows and tool
semantics. The older v0.6 release remains the direct STATE-Bench runtime
integration. SaaS and event logistics are native synthetic stateful domains.

All prices, contracts, inventory, and people are synthetic. The release does
not demonstrate safety on production accounts, subjective preference
elicitation, failure-prevention planning, or pre-failure autonomy. Although
there are 80 distinct executable states, they are generated from ten
reasoning blueprints; claims about unrestricted real-world diversity require
additional independently authored scenarios and human audit.
