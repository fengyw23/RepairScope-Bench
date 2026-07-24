# Data Card

## Summary

RepairScope-Bench v0.2 contains 16 executable post-failure recovery tasks:
four counterfactual families, two domains, 12 feasible cases, and four
infeasible cases. It is a protocol pilot rather than a statistically broad
leaderboard dataset.

## Unit of evaluation

Each public task contains:

- original user instruction;
- public pre-failure tool trace;
- authoritative failure snapshot with persistent commitments;
- failure observation;
- available catalog and modification rules;
- required slots and executable hard constraints;
- an unweighted lexicographic objective;
- a maximum action budget;
- source inspiration and transformation disclosure.

Public tasks intentionally omit expected feasibility, optimal actions, scopes,
and costs. Evaluator-only solver output is stored in `data/gold/pilot.json`.

## Construction

The four coordination structures were inspired by STATE-Bench travel and
shopping cases. Wording, failure boundaries, prices, refund policies,
counterfactual variants, executable state, and oracle are newly authored.
Provenance appears in every task and `THIRD_PARTY_NOTICES.md`.

`scripts/build_pilot.py` deterministically regenerates public tasks, solves
them, and writes evaluator gold. `repairscope validate` independently solves
the public mechanics and detects drift.

## Fields

| Field | Purpose | Model visible directly |
|---|---|---:|
| `instruction` | User goal and stated constraints | yes |
| `failure_observation` | Latest failed operation | yes |
| `pre_failure_trace` | Auditable successful/failed prefix | yes |
| `failure_snapshot` | Initial executable state | through `query_state` |
| `catalog` | Options, availability, prices | through `list_options` |
| `modification_rules` | Allowed in-place changes and cash effects | through tools |
| `constraints` | Executable evaluator checks | no |
| `objective` | Scoring declaration | no |
| `max_actions` | Action budget | enforced by harness |

The prompt is generated from a field allowlist, never by dumping the task JSON.

## Quality checks

The test suite verifies:

- every gold plan executes and the oracle passes all 16 tasks;
- public tasks contain no gold fields;
- failed and terminal calls do not silently mutate state;
- an infeasibility report cannot hide earlier successful damage;
- positive and negative modification cash changes are accounted exactly;
- the complete lexicographic objective is checked;
- OpenAI, Anthropic, Qwen/DeepSeek protocol loops preserve tool-call state;
- a scripted model can complete the full model → tool → model loop.

## Limitations

- only 16 cases and two domains;
- finite, enumerated options and at most one active commitment per slot;
- deterministic monetary units, with no taxes or exchange-rate changes;
- no clarification/user-simulation tasks;
- no pre-failure end-to-end execution track;
- source-inspired structures are not evidence of coverage of the source
  benchmark.

The next defensible release should expand independent domain templates,
separate development/test mechanics, add adversarial accounting cases, and
report human verification of scenario clarity without human voting on gold.
