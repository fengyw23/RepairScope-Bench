# RepairScope-Bench

**A controlled diagnostic benchmark for post-commit agent recovery.**

An agent may successfully book a flight and hotel, fail to book the rental car,
and then need to decide whether to keep, modify, or cancel the commitments that
already exist. The failure location alone does not determine the correct repair
scope.

RepairScope-Bench evaluates that decision from a standardized post-failure
state. Every model receives the same original goal, auditable pre-failure tool
trace, authoritative state snapshot, failure observation, policies, and tools.
The model must act in an executable environment. It is not asked to classify a
snapshot or output a rollback label.

> Status: **research pilot, v0.1**. The current release has 16 counterfactual
> tasks in two domains. It establishes the protocol and tests the oracle; it is
> not yet large enough for a leaderboard claim.

[中文说明](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation protocol](docs/EVALUATION.md) ·
[Research positioning](docs/RESEARCH_STORY.md)

## What is new here?

Existing benchmarks test useful neighboring abilities: executing stateful
tasks, adapting to a changed tool state, retrying a failed call, or re-running
steps affected by an error. RepairScope-Bench isolates a different question:

> After earlier actions have created persistent commitments and a later action
> fails, can an agent preserve useful commitments, revise only what is
> necessary, and avoid objectively measurable extra loss?

The v0.1 protocol has four defining properties:

1. **Fixed failure boundary.** Models begin from the same state, so score
   differences are attributable to recovery rather than different prefixes.
2. **Real state mutations after the boundary.** The agent still queries,
   cancels, books, modifies, and verifies records in an executable environment.
3. **No single gold trajectory.** An exhaustive solver accepts every
   constraint-satisfying plan with minimum repair loss.
4. **Counterfactual families.** Small changes to price, refundability,
   compatibility, or deadlines change the optimal scope. “Always keep,”
   “repair only the failed step,” and “rollback everything” cannot solve the
   full family.

The benchmark makes a deliberately narrow claim: it measures **conditional
post-commit recovery from a standardized failure state**. It does not claim to
measure the quality of planning and execution before that state. An end-to-end
track can later add those stages without changing the conditional track.

## Pilot tasks

The pilot transforms coordination structures inspired by four STATE-Bench
cases. The language, failure states, policies, counterfactuals, and oracle are
newly authored here.

| Family | Source structure | Failure boundary | Counterfactual optimal outcomes |
|---|---|---|---|
| Denver package | STATE-Bench 124 | Flights and hotel confirmed; car booking fails | book only the car; replace the hotel; modify one flight; report infeasible |
| Destination change | STATE-Bench 121 | Flight changed to SFO; requested SFO hotel sells out | replace old hotel; keep old hotel when allowed; choose another SFO hotel; report infeasible |
| Shortened trip | STATE-Bench 122 | Final hotel night removed; car date change fails | keep the extra rental day; replace the car; modify the car; report infeasible |
| Workstation compatibility | STATE-Bench 105 | Laptop and monitor ordered; dock order is voided | add compatible dock; replace laptop and dock; add adapter-dock; report infeasible |

Each family contains four variants. Three are feasible and one is infeasible.
The expected result is **not** manually selected. The checked-in
`expected_oracle` field is a regression assertion; `repairscope validate`
recomputes it from the public state, constraints, policies, and ledger.

## Objective evaluation

### 1. Goal feasibility

A feasible repair must leave exactly one active commitment in each required
slot and satisfy every hard constraint, including date, location,
compatibility, deadline, and total lifecycle budget.

### 2. Repair loss

For a trajectory \(\tau\):

\[
L(\tau)=
\text{unrefunded value of cancelled prior commitments}
+\text{net cost of new purchases}
+\text{explicit modification fees}.
\]

The exhaustive oracle computes:

\[
L^*(s_f)=\min_{\tau:\,\mathrm{GoalPass}(\tau)}L(\tau)
\]

from the same failure state \(s_f\). Repair regret is
\(L(\tau)-L^*(s_f)\). Ties are broken by fewer mutated prior commitments and
then fewer state-changing actions. All plans tied after the full lexicographic
objective are accepted.

### 3. Repair scope

Every pre-failure commitment receives one terminal disposition:

- `KEEP`: the original commitment remains active;
- `MODIFY`: the same commitment was changed in place;
- `REPLACE`: it was cancelled and a new commitment fills its slot;
- `CANCEL`: it was cancelled without a replacement.

The evaluator reports distance to the nearest optimal scope, over-repair
(needlessly changing a commitment that every optimal plan keeps), and
under-repair (keeping one that every optimal plan changes).

### 4. Infeasible states

When no valid repair exists, the correct behavior is to call
`report_infeasible` **without first destroying existing commitments**. This
prevents an “act first, explain later” policy from receiving credit.

## Quick start

Python 3.10 or newer is sufficient; the core package has no runtime
dependencies.

```bash
python -m pip install -e .
python scripts/build_pilot.py
repairscope validate data/pilot
python -m unittest discover -s tests -v
```

Inspect a task and its authoritative failure snapshot:

```bash
repairscope inspect data/pilot/travel-package-b-replace-hotel.json
```

Show every oracle-optimal trajectory:

```bash
repairscope oracle data/pilot/travel-package-b-replace-hotel.json
```

Evaluate an action trace:

```bash
repairscope evaluate \
  data/pilot/travel-package-b-replace-hotel.json \
  examples/travel-package-b-actions.json
```

Run the included diagnostic baselines:

```bash
repairscope run-baselines data/pilot
```

Expected v0.1 validation summary:

| Baseline | Success | Optimal repair |
|---|---:|---:|
| No repair | 2 / 16 | 2 / 16 |
| Repair only the missing/failed slot | 4 / 16 | 4 / 16 |
| Repair declared affected slots | 7 / 16 | 5 / 16 |
| Cancel everything, then greedily rebook | 0 / 16 | 0 / 16 |
| Exhaustive oracle | 16 / 16 | 16 / 16 |

These numbers are implementation checks, not claims about language models.

## Agent protocol

The evaluated model receives:

- `instruction`;
- `failure_observation`;
- the public pre-failure tool trace;
- access to the post-failure tools.

The model does **not** receive `expected_oracle`, oracle plans, or hidden solver
output. In an official harness, those evaluator-only fields should be loaded
outside the model context.

Available actions:

```text
query_state()
list_options(slot)
cancel(commitment_id)
book(option_id)
modify(commitment_id, to_option_id)
finish()
report_infeasible(reason)
```

Every run uses a fresh deep copy of the same snapshot. Tool errors are logged
and do not silently mutate state.

## Repository layout

```text
data/pilot/                 16 generated task instances
examples/                   example agent action traces
scripts/build_pilot.py      auditable counterfactual generator
src/repairscope_bench/      environment, solver, evaluator, baselines, CLI
tests/                      oracle replay and dataset invariants
docs/                       data card, metrics, and research positioning
```

## Limitations and next steps

- The pilot is travel-heavy: 12 travel tasks and 4 shopping tasks.
- Prices and policies are controlled simulations, not claims about current
  vendors.
- The exhaustive solver is intended for small structured worlds. A larger
  release should compile the same semantics to CP-SAT/SMT.
- The current tools are a compact transactional simulator rather than a
  browser or production API.
- Fixed failure states improve causal attribution but omit prefix planning,
  failure exposure, and failure detection. Those belong in a separate
  end-to-end track.
- Before reporting model rankings, the dataset needs more independent causal
  templates, paraphrases, domain diversity, held-out template splits, and
  human checks that the public facts are unambiguous.

## Attribution

The pilot was inspired by STATE-Bench cases 105, 121, 122, and 124.
STATE-Bench is MIT licensed. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
and the `source_inspiration` field in every task. No STATE-Bench runtime code is
copied into this repository.

## License

RepairScope-Bench is released under the MIT License. Dataset source
attribution is retained in each task.

