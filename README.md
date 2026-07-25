# RepairScope-Bench

**Can a tool-using agent recover from a failed operation without needlessly
discarding already executed commitments?**

RepairScope-Bench v3.0 evaluates recovery from a fixed, executable failure
boundary. Flights, hotels, products, licences, and services have already been
created through real write tools and persist in a native STATE-Bench domain.
The agent must investigate orders, policies, inventory, contracts, and
compatibility, then execute the unique lowest-cost valid repair within 15
model turns.

v3.0 uses two native domains:

- travel, backed by STATE-Bench `TravelEnvironment`;
- after-sales purchasing, backed by STATE-Bench
  `CustomerSupportEnvironment`.

There is no LLM judge, answer-revealing cost-summary tool, authored repair
macro, subjective utility weight, or benchmark-specific `finish()` action.

[中文说明](README.zh-CN.md) · [Data Card](docs/DATA_CARD.md) ·
[Evaluation](docs/EVALUATION.md) ·
[Research Story](docs/RESEARCH_STORY.md) ·
[Provider Setup](docs/PROVIDERS.md)

## Dataset

The release contains 80 tasks from 40 single-fact counterfactual pairs:

| Dimension | Coverage |
|---|---:|
| Native domains | travel and after-sales |
| Reasoning structures | 10 |
| Tasks per structure-domain cell | 4 |
| Development split | 40 |
| Test split | 40 |
| Counterfactual pairs | 40 |
| Existing persistent commitments per task | 4 |
| Model-turn limit | 15 |

The ten reasoning structures are:

1. sunk cost versus incremental recovery cost;
2. multi-hop economic impact propagation;
3. shared-commitment protection;
4. non-linear pricing thresholds;
5. conditional contract logic;
6. evidence-backed partial-quantity repair;
7. bridge repair versus upstream replacement;
8. joint compatible-combination selection;
9. explicit-horizon recurring cost;
10. selective dependency cutting.

Every structure appears in both domains through two independently named base
scenarios and their paired variants. A pair has the same request, prefix,
failure snapshot, and inventory; one queryable policy fact changes, and the
unique optimal repair scope must change with it.

## Objective

All amounts are exact integer cents internally and model-visible USD strings.
Historical payments before the failure boundary are not counted again.

```text
Incremental Recovery Cost
  = post-failure payments
  + modification, cancellation, return, migration, and activation fees
  + discount or rebate clawbacks
  - refunds
  - immediately usable credits and compensation
```

The Oracle enumerates all hard-goal-feasible native commitment sets, computes
the minimum reachable cost of each scope, and replays every candidate through
the public domain tools. A task is released only when exactly one scope is
cheapest and its lead over the runner-up is at least:

```text
max($10, 1% of active paid commitments at the failure boundary)
```

Tool-call order is not part of gold. Different legal traces are accepted if
they end in the same scope. Unnecessary intermediate actions remain in the
ledger and can make an otherwise correct scope wasteful.

## What the model sees

The model receives only:

- a normal travel or after-sales system prompt;
- the natural-language customer request;
- four successful pre-failure write calls and their real results;
- the latest failed write call and result;
- eight domain-specific tools.

The model does not receive the hard-goal DSL, pair identity, reasoning label,
changed-fact pointer, candidate scopes, aggregate recovery costs, or gold.
It must query the authoritative environment to discover the decisive fact.

## Metrics

- `Goal Pass`: all evidenced hard requirements and business rules hold;
- `Unique Scope Pass`: Goal Pass and the final native scope equals the unique
  lowest-cost scope;
- `Counterfactual Pair Success`: both variants are solved and the repair
  changes with the queried fact;
- `Incremental Recovery Cost` and `Cost Regret`;
- `Clean Execution`: the scope is correct and no avoidable cost was incurred;
- `Execution Waste`: cost added by unnecessary intermediate actions;
- `Over-Repair` and `Under-Repair`.

The release validator also proves scorer–agent information symmetry: 624/624
hard-constraint evidence references and 1,320/1,320 scored state atoms are
replayable through model-visible instructions or structured public tools. See
[Scorer–Agent Observability Audit](docs/OBSERVABILITY_AUDIT.md).

Scope reasoning and tool execution are deliberately separated. An agent that
buys the wrong option, pays a visible cancellation fee, and then reaches the
correct final scope receives `Unique Scope Pass` but not `Clean Execution`.

## Install, build, and validate

Python 3.12+ and Git are required. STATE-Bench is pinned to commit
`4efcbf2d4fe60df04878859b692d9391f3d5b33a`.

```bash
python -m pip install -e .
python scripts/build_v3.py
repairscope validate data/v3
repairscope run-baselines data/v3
python -m unittest discover -s tests -v
```

The checked-in v3.0 data gives:

| Baseline | Goal Pass | Unique Scope Pass |
|---|---:|---:|
| No repair | 0 / 80 | 0 / 80 |
| Local repair | 80 / 80 | 32 / 80 |
| Dependency repair | 80 / 80 | 36 / 80 |
| Full rollback | 80 / 80 | 4 / 80 |
| Lowest new sticker price | 80 / 80 | 38 / 80 |
| Largest gross refund | 80 / 80 | 0 / 80 |
| Minimum changes | 80 / 80 | 32 / 80 |
| Exact cost Oracle | 80 / 80 | 80 / 80 |

## Run a model

```bash
repairscope run-suite data/v3 \
  --provider openai-compatible \
  --model YOUR_MODEL_ID \
  --base-url https://gateway.example/v1 \
  --repeats 5 \
  --output-dir results/your-model-v3
```

Official reporting uses five independent episodes per task and reports
Pass@1, strict Pass^5, paired success, cost regret, investigation behavior,
scope errors, execution waste, tool errors, and turn exhaustion. Provider
failures remain in the denominator.

## Layout and claim boundary

```text
data/v3/dev/                 40 public development tasks
data/v3/test/                40 public test tasks
data/gold/v3.json            private metadata, terminals, gold, and witnesses
scripts/build_v3.py          deterministic native-domain builder
src/repairscope_bench/v3_*   runtime, constraints, Oracle, and evaluator
tests/test_v3.py             v3 release and regression tests
```

v3.0 evaluates only post-failure recovery from standardized snapshots. The
prior commitments were produced by executable tools, but not freely chosen
by the tested model in the same episode. It does not evaluate pre-failure
planning, subjective preferences, stochastic risk, or production safety.
The novelty claim is not that partial rollback is new; it is deterministic
evaluation of whether an agent selects the correct repair scope over real
persistent commitments and auditable incremental costs.
