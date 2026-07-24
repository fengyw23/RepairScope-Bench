# RepairScope-Bench v1.1 Data Card

## Summary

RepairScope-Bench v1.1 contains 160 fixed post-failure tasks derived from 80
single-fact counterfactual pairs. It evaluates full recovery: an agent must
reach a valid persistent state and avoid an economically dominated repair.

| Dimension | Distribution |
|---|---:|
| Domains | 40 tasks each in travel, after-sales, SaaS, event logistics |
| Reasoning structures | 16 tasks for each of ten structures |
| Structure-domain cells | 40 cells, 4 tasks per cell |
| Splits | 32 dev, 64 test, 64 heldout |
| Difficulty | 16 L1, 64 L2, 64 L3, 16 L4 |
| Multi-point Pareto frontier | 50% |
| Positive irreversible-loss gold | 50% |
| Gold changes a prior commitment | 90% |
| One added option is insufficient | 30% |

The statistical unit for counterfactual analysis is the 80 base scenarios,
not 160 independent observations.

## Reasoning matrix

The primary private labels are reasoning structures rather than fee names:

- sunk versus marginal recovery cost;
- multi-hop economic impact propagation;
- shared commitments;
- non-linear thresholds;
- conditional contracts;
- partial quantities;
- bridge repair;
- joint bundle selection;
- explicit-horizon recurring cost;
- Pareto trade-offs.

Each structure occurs in every domain through two base scenarios and paired
variants. Economic carriers are deliberately reused across structures.

## Public task schema

| Field | Meaning |
|---|---|
| `schema_version` | `1.1` |
| `task_id` | opaque task identifier |
| `domain` | domain tool surface |
| `environment_type` | executable environment adapter |
| `split` | dev, test, or heldout |
| `instruction` | natural customer request |
| `pre_failure_trace` | successful public write calls and results |
| `latest_failure` | actual failed public write call and result |
| `failure_snapshot` | authoritative persistent starting state |
| `snapshot_sha256` | canonical state hash |
| `boundary_commitments` | prior commitments used by the runtime |
| `inventory` | queryable alternatives; not placed in the model prompt |
| `contracts` | queryable clauses; not placed in the model prompt |
| `compatibility_rules` | queryable compatibility facts |
| `hard_goals` | deterministic evaluator constraints; private from the model |
| `construction` | non-answer-revealing provenance assertions |
| `max_turns` | 15 |

The public JSON does not contain pair identity, scenario identity, variant
role, reasoning structure, changed-fact manifest, authored candidate scopes,
or repair macros.

## Private gold

`data/gold/v11.json` contains:

- private pair, scenario, structure, difficulty, and intervention metadata;
- all hard-goal-feasible terminal assignments;
- every Pareto non-dominated outcome;
- an independently replayed public-tool frontier;
- economic vectors, scope dispositions, state hashes, and witness traces;
- per-task validity certificates.

The terminal solver enumerates retained boundary commitments and inventory
combinations directly. The independent solver reaches terminal states by
executing public cancellation and purchase tools. Release validation requires
exact frontier agreement.

If a model outcome strictly dominates stored gold, the evaluator marks an
`oracle_violation`, does not penalize the model, and excludes the task from
aggregate reporting pending audit.

## Construction and counterfactuals

The builder:

1. starts from an empty database;
2. creates prior commitments using public write tools;
3. executes an unavailable option and records the actual failure;
4. saves and hashes the failure boundary;
5. creates a paired task by changing one queryable logical fact;
6. searches all feasible terminal commitments and the economic frontier;
7. verifies the same frontier through public-tool state search;
8. rejects pairs whose accepted repair scopes do not change.

The intervention may change a number, relation, Boolean condition, threshold,
or explicit horizon. File names and model-visible prompts do not identify the
pair or intervention.

## Provenance and limitations

All entities, prices, policies, contracts, and inventories are synthetic.
The four domains have distinct tool names, state attributes, and business
vocabulary over a common deterministic commitment-and-ledger core. This
choice supports exact Oracle comparison but is less externally diverse than
four independently implemented production systems. The older v0.6 release
retains direct STATE-Bench runtime integration for travel and after-sales.

The release does not evaluate pre-failure planning, subjective preference
elicitation, stochastic risk, or production-account safety. The 80 states
come from ten audited generator families; publication claims should be
supported by independent scenario authoring, human audit, paraphrase tests,
and entity/order perturbation experiments.
