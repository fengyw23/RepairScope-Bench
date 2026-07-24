# Data Card

## Releases

| Set | Schema | Tasks | Purpose |
|---|---:|---:|---|
| `data/pilot` | 0.4 | 16 | protocol, accounting, infeasibility, and provider-loop regression |
| `data/challenge` | 0.5 | 12 | paired scope optimization with larger repair graphs and linked losses |

The challenge set contains six unique failure states. Each has a `goal` and
`loss_aware` prompt, producing 12 episodes. There are three counterfactual
families, two domains, and three causal mechanisms.

## Unit of evaluation

Each task contains:

- natural customer instruction;
- successful pre-failure tool trace and failed call;
- authoritative persistent commitments;
- live option catalog and in-place modification rules;
- linked settlement rules;
- live inventory partitioned by public domain categories;
- required slots and executable hard constraints;
- evaluator objective and automatic challenge thresholds;
- pair, mechanism, and split metadata;
- provenance and transformation disclosure.

The prompt exposes only instruction, public trace, failed result, and tools.
Gold and evaluator mechanics are not serialized to the model.

## Challenge families

| Family | Mechanism | Split | A variant | B variant |
|---|---|---|---|---|
| Shanghai conference dinner | package breakage | dev | compatible dinner exists near current hotel | current hotel has no compatible dinner |
| Radiology workstation dock | compatibility cascade | test | universal dock is available | laptop change forces warranty/software changes |
| Clinic cold-chain battery | service-contract cascade | heldout | legacy-compatible battery is available | freezer and service plan must change |

All variants remain feasible. This is intentional: the challenge measures
which feasible repair scope is chosen, not only whether the model recognizes
impossibility.

## Repair-graph statistics

Across the six loss-aware tasks:

| Statistic | Minimum | Maximum |
|---|---:|---:|
| Raw candidate plans | 486 | 729 |
| Goal-satisfying plans | 18 | 235 |
| Feasible scope patterns | 4 | 30 |
| Recovery-loss levels | 4 | 30 |
| Persistent prior commitments | 5 | 5 |
| Required final slots | 6 | 6 |

The paired `goal` task has the same graph as its `loss_aware` twin.

## Important fields

| Field | Meaning | Directly model-visible |
|---|---|---:|
| `instruction` | hard goal and natural objective demand | yes |
| `failure_observation` | raw latest failed call | yes |
| `pre_failure_trace` | public evidence of earlier persistent effects | yes |
| `failure_snapshot` | executable initial state | through record tools |
| `catalog` | live and unavailable options | available matches through search |
| `modification_rules` | possible in-place changes | through targeted quote |
| `linked_loss_rules` | non-local settlement consequences | through targeted linked-term lookup |
| `constraints` | deterministic terminal checks | no |
| `objective` | Oracle ordering | no |
| `pair_id` | matched-pair identity | no |
| `evaluation_track` | goal or loss-aware analysis track | no |
| `mechanism`, `split` | causal grouping | no |

## Construction

`scripts/build_challenge.py` deterministically generates public tasks and
solver-derived evaluator gold. The scenarios are newly authored around
coordination structures inspired by STATE-Bench cases 105, 121, and 122; no
upstream answer or runtime is reused.

The generator creates two counterfactual variants per family and two prompt
tracks per state. It then invokes the same Oracle used by evaluation.
`repairscope validate data/challenge` independently recomputes gold, checks
scope flips, applies challenge thresholds, and replays baseline policies.

## Quality controls

Automated tests verify:

- public files load under the versioned schema;
- every linked loss references real prior commitments and is charged once;
- category searches expose every live option in the requested public category
  and require no hidden phrase;
- model-facing schemas remain domain-native and contain no generic evaluator
  operations;
- every loss-aware graph meets all four minimum thresholds;
- A/B variants change the optimal disposition of prior commitments;
- Oracle replay passes every task;
- full rollback completes every task but is never optimal;
- a final-cost-only solver completes every task but is optimal on only half;
- natural model termination cannot invalidate an otherwise correct final state;
- provider tool loops retain state across OpenAI, Anthropic, Qwen, and
  DeepSeek-compatible protocols.

## Limitations

- Six unique failure states are enough to test mechanisms, not enough for
  leaderboard-scale statistical claims.
- The option space is finite and deterministic.
- Each slot supports at most one active commitment.
- Losses use dollar-like deterministic units; taxes, exchange rates, and
  uncertain future value are excluded.
- There is no simulated clarification user because current tasks are
  deliberately decision-complete.
- The main track starts after the failure boundary and therefore does not
  score pre-failure planning.
- The current Oracle should be cross-checked by an independent solver before
  a paper-scale release.
