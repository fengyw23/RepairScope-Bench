# RepairScope-Bench

**Can a tool-using agent repair a failed multi-step task without discarding
valuable commitments or choosing a recovery that another feasible recovery
objectively dominates?**

RepairScope-Bench v1.1 starts every model from the same executable,
post-failure state. Earlier tool calls have already created paid, persistent
commitments. The model must inspect records, alternatives, cancellation
previews, compatibility facts, and contracts, then complete the recovery
through domain tools within 15 turns.

The public leaderboard has one task format: **full recovery**. It reports:

- `Goal Pass`: all hard requirements and business rules hold;
- `Non-Dominated Repair Pass`: Goal Pass, and no feasible recovery is no worse
  in both irreversible loss and net recovery outlay and strictly better in at
  least one.

There is no LLM judge, subjective utility weight, answer-revealing cost tool,
authored repair macro, or benchmark-specific `finish()` action.

[中文说明](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation](docs/EVALUATION.md) · [Research story](docs/RESEARCH_STORY.md) ·
[Provider setup](docs/PROVIDERS.md)

## v1.1 dataset

The release has 160 tasks from 80 single-fact counterfactual pairs:

| Dimension | Coverage |
|---|---:|
| Domains | travel, after-sales, SaaS, event logistics |
| Base scenarios | 80 |
| Counterfactual tasks | 160 |
| Primary reasoning structures | 10 |
| Tasks per structure-domain cell | 4 |
| Model turns | 15 |

The ten structures are:

1. sunk cost versus marginal recovery cost;
2. multi-hop economic impact propagation;
3. shared-commitment preservation;
4. non-linear threshold effects;
5. conditional contract logic;
6. partial-quantity rollback;
7. bridge repair versus upstream replacement;
8. joint compatible-bundle selection;
9. explicit-horizon recurring cost;
10. genuine Pareto trade-offs.

Each structure appears in every domain through two base scenarios and their
paired variants. Refunds, penalties, credits, warranties, licences,
subscriptions, deposits, delivery charges, and adapters are economic
carriers, not capability labels.

## What a task contains

The builder starts from an empty database, creates the prior commitments with
the same public write tools exposed to the model, executes an unavailable
option, and hashes the resulting failure snapshot. Models receive only:

- a normal domain-agent system prompt;
- the customer request;
- a compact successful pre-failure tool trace;
- the latest failed call and result;
- eight domain tools.

The reasoning label, pair identity, changed fact, hard-goal DSL, feasible
terminal set, and Pareto frontier remain private. A model must query the
environment to discover the intervention.

Necessary operations are economically order-invariant. Extra purchases,
cancellations, and repeated changes remain in the ledger and may make an
otherwise correct scope dominated.

## Validity-first construction

`scripts/build_v11.py` rejects a task unless:

- the failure boundary replays exactly from public tools and matches its hash;
- at least three semantic recovery scopes are feasible;
- at least one feasible recovery is economically dominated;
- a terminal-state enumerator and an independent public-tool state search
  produce the same Pareto frontier;
- the paired variant changes one logical fact and changes the accepted scope;
- a gold witness is executable within the 15-turn limit.

Across the release, 50% of tasks have multi-point Pareto frontiers, 50% have
an accepted solution with positive irreversible loss, 90% require changing
at least one prior commitment, and 30% cannot be solved by one added option.

## Install and validate

Python 3.12+ and Git are required.

```bash
python -m pip install -e .
python scripts/build_v11.py
repairscope validate data/v11
repairscope run-baselines data/v11
python -m unittest discover -s tests -v
```

The checked-in v1.1 data gives:

| Baseline | Goal Pass | Non-Dominated Pass |
|---|---:|---:|
| No repair | 0 / 160 | 0 / 160 |
| Local repair | 160 / 160 | 72 / 160 |
| Dependency repair | 160 / 160 | 72 / 160 |
| Full rollback | 160 / 160 | 0 / 160 |
| Lowest new sticker price | 160 / 160 | 96 / 160 |
| Largest gross refund | 160 / 160 | 0 / 160 |
| Minimum changes | 160 / 160 | 72 / 160 |
| Pareto Oracle | 160 / 160 | 160 / 160 |

Exact minimization of either Pareto dimension is an analytical Oracle, not a
realistic weak baseline: a correctly tie-broken global minimum of one
dimension must be non-dominated.

## Run a model

```bash
repairscope run-suite data/v11 \
  --provider openai-compatible \
  --model YOUR_MODEL_ID \
  --base-url https://gateway.example/v1 \
  --repeats 5 \
  --output-dir results/your-model-v11
```

Official reporting uses five independent episodes per task and includes
Goal Pass@1/Pass^5, Non-Dominated Repair Pass@1/Pass^5, dominated-repair
rate, both regret components, counterfactual-pair success, and breakdowns by
domain, reasoning structure, and difficulty.

## Layout and claim boundary

```text
data/v11/                    160 public v1.1 task states
data/gold/v11.json           private metadata, terminals, frontiers, certificates
scripts/build_v11.py         deterministic validity-first builder
src/repairscope_bench/       runtime, solvers, evaluator, providers, CLI
tests/test_v11.py            v1.1 release and regression tests
data/v1/, data/v06/          retained earlier releases
data/legacy/v0.5/            prototypes
```

v1.1 uses four domain-specific tool surfaces over a common audited
commitment-and-ledger core, which enables exact cross-domain comparison.
v0.6 is retained as the earlier direct STATE-Bench-backed implementation.

The novelty claim is not that partial rollback is new. The benchmark measures
whether an agent can reason over already executed commitments and avoid a
hard-goal-feasible repair scope that another feasible outcome strictly
economically dominates. It does not evaluate pre-failure planning,
subjective preference elicitation, or production safety.
