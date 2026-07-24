# Data Card

## Summary

RepairScope-Bench v0.4.0 contains 16 executable post-failure recovery tasks:
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
- an evaluation class (`loss_sensitive` or `infeasible_control`);
- a maximum action budget;
- source inspiration and transformation disclosure.

Public tasks intentionally omit expected feasibility, optimal actions, scopes,
and costs. Evaluator-only solver output is stored in `data/gold/pilot.json`.

## Construction

The four coordination structures were inspired by STATE-Bench travel and
shopping cases. Wording, failure boundaries, prices, refund policies,
counterfactual variants, executable state, and oracle are newly authored.
Provenance appears in every task and `THIRD_PARTY_NOTICES.md`.

The travel adapter preserves the upstream domain partition (flight bookings,
hotel reservations, and car rentals) and the core list/detail/search operation
pattern. It does not vendor the STATE-Bench runtime. Targeted policy previews,
post-failure mutation accounting, and the solver are RepairScope-Bench
extensions required by this benchmark's recovery-loss question.

`scripts/build_pilot.py` deterministically regenerates public tasks, solves
them, and writes evaluator gold. `repairscope validate` independently solves
the public mechanics and detects drift.

## Fields

| Field | Purpose | Model visible directly |
|---|---|---:|
| `instruction` | User goal and stated constraints | yes |
| `failure_observation` | Latest failed operation | yes |
| `pre_failure_trace` | Auditable successful/failed prefix | yes |
| `failure_snapshot` | Initial executable state | one commitment at a time through read tools |
| `catalog` | Options, availability, prices | only available entries through domain search tools |
| `modification_rules` | Allowed in-place changes and cash effects | only for a requested commitment-target quote |
| `constraints` | Executable evaluator checks | no |
| `objective` | Scoring declaration | no |
| `max_actions` | Action budget | enforced by harness |

The prompt is generated from a field allowlist, never by dumping the task JSON.
`failure_observation` contains only the raw failed call and error. It must not
summarize refunds, alternatives, compatibility, the required repair scope, or
whether the task is feasible. Counterfactual variants in one family therefore
share the same failure text even when their hidden environment facts differ.

## Quality checks

The test suite verifies:

- every gold plan executes and the oracle passes all 16 tasks;
- every loss-sensitive task has at least two goal-satisfying repairs and at
  least two distinct recovery-loss values;
- public tasks contain no gold fields;
- failed and terminal calls do not silently mutate state;
- an infeasibility report cannot hide earlier successful damage;
- positive and negative modification cash changes are accounted exactly;
- the complete lexicographic objective is checked;
- the prompt does not narrate counterfactual policies or solutions;
- reservation/order listing does not expose refunds or modification rules;
- unavailable options remain hidden from search;
- compatibility and modification facts require targeted queries;
- OpenAI, Anthropic, Qwen/DeepSeek protocol loops preserve tool-call state;
- a scripted model can complete the full model → tool → model loop.

## Limitations

The v0.4 harness additionally verifies that model-visible tools are
domain-specific, exclude global cost/loss summaries, and run under a 15-turn
budget.

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
