# RepairScope-Bench v2.0 strict pilot

## Status

The v2.0 development track contains 24 executable tasks in 12 strict
single-fact counterfactual pairs. It is a quality-gated pilot, not the final
160-task benchmark. v1.1 remains frozen and reproducible.

The pilot makes three changes that are required before scaling:

1. scope quality and trajectory waste are scored separately;
2. declarative gold is checked by public-tool replay;
3. task difficulty is recorded as mechanism, structural complexity, and
   later empirical calibration rather than an author-assigned level.

## Two economic layers

`Scope Non-Dominated Pass` evaluates the canonical economic consequence of
the final persistent scope. It derives the necessary changes between the
fixed failure boundary and the final active commitments. Redundant
intermediate actions are ignored at this layer.

`Realized Non-Dominated Pass` evaluates the complete transaction ledger.
Unnecessary purchases, cancellations, or repeated changes remain in the
ledger even when the final active commitments match a good scope.

The primary diagnostic chain is:

```text
Goal Pass
  -> Scope Non-Dominated Pass
  -> Realized Non-Dominated Pass
```

A run that passes scope but fails realized evaluation selected a defensible
repair but executed it wastefully. Cancelling an existing boundary
commitment and buying it again is still a scope change; only detours that do
not survive in the final scope are isolated as execution waste.

## Two Oracle implementations

Oracle A exhaustively enumerates retained boundary commitments and available
option subsets. It independently evaluates hard constraints, compatibility,
contracts, refund policies, and the economic frontier without calling the
runtime.

Oracle B receives every feasible terminal claim from Oracle A and reaches it
using only the same public cancellation and purchase tools exposed to a
model. Runtime contract settlement and the actual transaction ledger
recompute the economic vector. A task is rejected when a claimed terminal is
unreachable or the two frontier signatures differ.

The second Oracle is a construction-time validity check. Model evaluation
uses the frozen frontier in `data/gold/v2.json`; it does not repeatedly
search the full state space.

## Strict counterfactuals

Every pair:

- changes one normalized source field;
- exposes that fact only through an authoritative query tool;
- keeps the request, failure boundary, inventory, and all other facts fixed;
- has disjoint accepted scope sets across variants.

The private manifest records the exact JSON Pointer, reveal tool, record ID,
and logical fact. Evaluation reports whether the model queried that record
before its first successful mutation.

All identifiers are opaque. A build-time audit rejects role-bearing labels
and verifies that identifier and ordering permutations preserve the Oracle
shape.

## Reusable difficulty knowledge

Difficulty is represented in three layers.

### Reasoning signature

Each task receives one or more mechanism labels, such as
`multi_hop_propagation`, `partial_quantity`, or
`selective_dependency_cut`. The labels describe what must be reasoned about,
not how hard a particular model will find the task.

### Structural complexity profile

The builder records:

- number of boundary commitments and available options;
- number of key facts;
- dependency depth;
- feasible scope count and frontier size;
- minimum gold mutations;
- number of interacting mechanisms.

A deterministic score maps this profile to construction strata `C1`–`C4`.
These are authoring strata, not empirical difficulty claims.

### Empirical difficulty

After a task set is frozen, `calibrate-difficulty` fits a regularized Rasch
model over calibration runs. It stores item difficulty, predicted pass
probability for the median calibration agent, a difficulty band, and anchor
tasks. Future expansions can be calibrated against the anchors.

`data/v2/mechanism_cards.json` stores reusable causal patterns, required
evidence, and common errors. `data/v2/coverage_matrix.json` shows which
mechanism/domain/complexity cells are represented, so expansion fills
missing cells instead of creating more renamed templates.

## Commands

```powershell
python scripts/build_v2_pilot.py
repairscope validate data/v2/pilot
repairscope run-baselines data/v2/pilot
repairscope inspect data/v2/pilot/<task>.json
repairscope run-suite data/v2/pilot <provider arguments> --output-dir results/v2
repairscope calibrate-difficulty results/v2/runs.jsonl --version v2-calibration-1
```

## Current release gates

- 24 tasks, 12 pairs, and four balanced domains;
- ten reasoning mechanisms represented;
- at least four feasible semantic scopes per task;
- exact one-source-fact pair differences;
- disjoint accepted scopes within every pair;
- declarative/replay frontier agreement;
- zero role-token leakage;
- identifier/order permutation invariance;
- a dominated feasible terminal in every task;
- local, full-rollback, sticker-price, refund-only, and minimum-change
  heuristics below 60% Scope Non-Dominated Pass.

The final 160-task set will be authored only after model calibration on this
pilot confirms that failures are primarily investigation and repair-scope
reasoning rather than tool-interface execution.

Exact composition and current limitations are recorded in
[DATA_CARD_V2_PILOT.md](DATA_CARD_V2_PILOT.md).
