# RepairScope-Bench

**Can a tool-using agent recover from a fixed post-failure state without
choosing a repair scope that another feasible repair objectively dominates?**

RepairScope-Bench v1.0 evaluates recovery after prior tool calls have created
persistent commitments. Every model starts from the same hashed failure
snapshot, inspects records, alternatives, refund previews, compatibility
facts, and linked terms, and then changes the state through domain tools.

The benchmark separates:

- `Goal Pass`: all hard requirements are satisfied;
- `Non-Dominated Repair Pass`: Goal Pass and no feasible repair is no worse
  in both irreversible loss and net recovery outlay.

No LLM judge, subjective utility weights, answer-revealing cost tool, or
benchmark-specific `finish()` action is used.

[Chinese README](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation](docs/EVALUATION.md) · [Research story](docs/RESEARCH_STORY.md) ·
[Provider setup](docs/PROVIDERS.md)

## v1.0 dataset

The default release contains 160 tasks from 80 counterfactual pairs:

| Dimension | Coverage |
|---|---:|
| Domains | travel, after-sales, SaaS, event logistics |
| Independent failure scenarios | 80 |
| Single-fact counterfactual tasks | 160 |
| Primary reasoning structures | 10 |
| Model turns | 15 |

Each reasoning structure appears 16 times and each domain 40 times. The ten
structures are:

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

The generator crosses these structures with refunds, settlements, licences,
warranties, subscriptions, deposits, volume credits, and replacement
purchases. Economic carrier names are not used as capability labels.

Travel and after-sales adapters follow STATE-Bench's domain workflow and tool
semantics; v0.6, retained for reproducibility, contains the earlier direct
STATE-Bench runtime integration. SaaS and event logistics use the v1
persistent commitment runtime.

## Construction and gold

For every task, `scripts/build_v1.py`:

1. starts from an empty persistent state;
2. creates four paid commitments using the same public write tool exposed to
   models;
3. executes an unavailable option and records the real failed result;
4. hashes the resulting failure snapshot;
5. builds a paired task that changes exactly one queryable economic fact;
6. computes the complete feasible terminal set without author-specified
   repair macros;
7. cross-checks the frontier using a second solver that replays public tools.

Necessary repair operations are order-invariant by construction. Unnecessary
model actions still remain in the transaction ledger and can make an
otherwise correct scope economically dominated.

## Install and validate

Python 3.12+ and Git are required.

```bash
python -m pip install -e .
python scripts/build_v1.py
repairscope validate data/v1
repairscope run-baselines data/v1
python -m unittest discover -s tests -v
```

The checked-in deterministic validation yields:

| Baseline | Goal Pass | Non-Dominated Pass |
|---|---:|---:|
| No repair | 0 / 160 | 0 / 160 |
| Local repair | 160 / 160 | 80 / 160 |
| Dependency repair | 160 / 160 | 80 / 160 |
| Full rollback | 160 / 160 | 0 / 160 |
| Final sticker price | 160 / 160 | 96 / 160 |
| Gross refund only | 160 / 160 | 0 / 160 |
| Pareto Oracle | 160 / 160 | 160 / 160 |

Sixty percent of tasks have multi-point Pareto frontiers, and sixty percent
have at least one accepted solution with positive irreversible loss.

An exhaustive optimizer for either exact Pareto dimension is an Oracle
upper bound: mathematically, an exact minimum of one dimension is always
non-dominated after proper tie-breaking. Such controls measure search
tractability and must not be described as realistic heuristics.

## Run models

```bash
repairscope run-suite data/v1 --provider openai \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/openai-v1

repairscope run-suite data/v1 --provider anthropic \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/anthropic-v1

repairscope run-suite data/v1 --provider qwen \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/qwen-v1

repairscope run-suite data/v1 --provider deepseek \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/deepseek-v1
```

The summary reports Goal Pass, Non-Dominated Repair Pass, dominated-repair
rate, both regret components, counterfactual-pair success, and breakdowns by
domain, reasoning structure, and difficulty.

## Layout

```text
data/v1/                     160 public v1 task states
data/gold/v1.json            feasible terminals and two Oracle frontiers
data/v06/                    previous direct STATE-backed release
data/legacy/v0.5/            older prototypes
scripts/build_v1.py          deterministic v1 builder
src/repairscope_bench/       runtime, solvers, evaluator, providers, CLI
tests/test_v1.py             v1 unit, integration, and release gates
```

The novelty claim is not that partial rollback is new. The benchmark targets
whether an agent can reason over already executed commitments and avoid a
repair scope that another feasible outcome strictly economically dominates.
