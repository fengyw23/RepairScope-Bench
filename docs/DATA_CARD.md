# RepairScope-Bench v3.0 Data Card

## Summary

RepairScope-Bench v3.0 contains 80 fixed post-failure tasks grouped into 40
single-fact counterfactual pairs. It evaluates whether a tool-using agent can
reach all evidenced hard goals and select the unique lowest incremental-cost
repair scope over already executed commitments.

| Dimension | Distribution |
|---|---:|
| Domains | 40 travel, 40 after-sales |
| Splits | 40 development, 40 test |
| Reasoning structures | 10, with 8 tasks each |
| Structure-domain cells | 20, with 4 tasks each |
| Counterfactual pairs | 40 |
| Existing commitments | 4 per task |
| Feasible scopes | at least 3 per task |
| Turns | 15 |

The paired base scenario—not each variant independently—is the statistical
unit for counterfactual analysis.

## Domain provenance

Travel tasks instantiate STATE-Bench's native `TravelEnvironment`; after-sales
tasks instantiate its native `CustomerSupportEnvironment`. The dependency is
pinned to commit `4efcbf2d4fe60df04878859b692d9391f3d5b33a`.

Composition adapters add the benchmark-specific restaurant, transfer,
conference-service, compatibility, licence, warranty, and settlement facts.
They do not replace the native reservation, order, customer, product, or
persistence systems. Every task records its source commit and runtime class.

Prices are synthetic but constrained by frozen domain profiles whose public
references and freeze date are stored in each task. Travel uses GSA travel
price references; after-sales profiles use public Dell workstation and dock
catalogues. Amounts are stored as integer cents and exposed to models as
ordinary two-decimal USD objects.

## Reasoning matrix

The private primary labels describe reasoning structure, not business nouns:

- sunk versus incremental cost;
- multi-hop economic propagation;
- shared commitments;
- non-linear thresholds;
- conditional contracts;
- partial quantity;
- bridge repair;
- joint combinations;
- explicit-horizon recurring cost;
- selective dependency cutting.

Every structure occurs in both domains using different surface carriers. A
pricing threshold may be a travel-package minimum in one domain and a
quantity or delivery threshold in purchasing.

## Public task schema

| Field | Meaning |
|---|---|
| `schema_version` | `3.0` |
| `task_id` | opaque task identifier |
| `domain` | `travel` or `after_sales` |
| `split` | `dev` or `test` |
| `instruction` | natural customer request |
| `pre_failure_trace` | four successful public write calls and real results |
| `latest_failure` | actual failed public write call and result |
| `failure_snapshot` | authoritative persistent starting state |
| `snapshot_sha256` | canonical snapshot hash |
| `boundary_commitments` | four active pre-failure commitments |
| `option_metadata` | runtime inventory facts, only visible through tools |
| `economic_terms` | runtime policies, only visible through tools |
| `compatibility_rules` | deterministic queryable relations |
| `hard_goals` | deterministic evaluator constraints, hidden from model |
| `price_profile` | frozen realism profile and sources |
| `construction` | provenance assertions |
| `max_turns` | `15` |

Pair identity, scenario identity, variant role, reasoning label, evidence
manifest, changed-fact pointer, feasible scopes, and gold are stored in the
private gold file rather than the public task.

## Constraint evidence

Every hard-constraint atom must reference at least one evidence record:

- an exact span in the user instruction;
- a successful prefix result;
- a reproducible query result;
- a documented tool or policy rule.

The builder and release validator reject constraints that use constants
outside this evidence graph. This applies equally to quantity, date,
location, compatibility, budget, and deadline constraints. The v3 release
validates 624 of 624 evidence references. It additionally replays 1,320 of
1,320 scored state atoms, including candidate coverage and price, boundary
records and refunds, complete economic terms, and structured relationship
rules. A tool-description match is not accepted as evidence for a scored
rule. See [Scorer–Agent Observability Audit](OBSERVABILITY_AUDIT.md).

## Construction

For every task, the builder:

1. starts from a clean native-domain database;
2. creates four prior commitments with the model's public write tools;
3. records the resulting transaction ledger;
4. injects a policy, compatibility, or inventory change;
5. executes and records one genuinely failed write;
6. saves and hashes the failure snapshot;
7. creates a paired variant by changing one queryable fact;
8. enumerates all hard-goal-feasible native terminal scopes;
9. computes each scope's minimum incremental recovery cost;
10. replays each candidate through the public tools;
11. rejects non-unique or insufficiently separated optima;
12. verifies that the pair's gold scope changes.

The released gold is unique at the scope level, not the tool-order level.

## Private gold

`data/gold/v3.json` contains:

- pair, scenario, structure, and variant metadata;
- the evidence manifest and changed-fact certificate;
- every feasible replayed terminal scope and cost;
- the unique gold scope and a public-tool witness;
- complexity features and the runner-up margin.

If a model produces a goal-satisfying outcome cheaper than stored gold, the
evaluator marks `oracle_violation`, does not penalize the model, and excludes
the task from aggregation pending audit.

## Quality gates

The release validator requires:

- 80 tasks, 40 pairs, balanced domains, splits, and structures;
- exactly four replayable prior writes and one real failed write per task;
- native STATE-Bench runtime identity;
- at least three feasible scopes per task;
- one unique minimum-cost scope;
- a lead of `max($10, 1% of boundary paid value)` over the runner-up;
- one public fact difference and a gold flip in every pair;
- 100% hard-constraint evidence coverage;
- 100% price-profile validity;
- public money normalization;
- weak heuristic Unique Scope Pass below 65%;
- exact Oracle success on every task.

## Limitations

The prior commitments are standardized rather than freely generated by the
tested model. The benchmark therefore isolates post-failure recovery scope,
not pre-failure planning. The data use two native systems but synthetic
scenario content and ten generator families. They do not cover subjective
preferences, uncertain future costs, adversarial tools, concurrency, or
production safety.

Four v2 pilot quantity tasks without model-visible evidence were invalidated
and are not part of v3.0 results. Their identifiers are documented in
`docs/INVALIDATED_DATA.md`.
