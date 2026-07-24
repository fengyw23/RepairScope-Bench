# Research Story: Repair Scope After Real Commitments

## Motivation

A service agent books a flight to Shanghai, a hotel, an airport transfer, and
a conference pass. The final restaurant booking fails. The failed restaurant
must be handled, but the flight still secures the central goal of attending
the conference. Replacing the hotel may or may not make sense: it depends on
the hotel's refund, the transfer change fee, and a package credit.

The same conflict appears in purchasing. A clinic has already bought a
workstation, display, warranty, and imaging licence when the dock purchase
fails. A universal dock repairs the missing component locally. Replacing the
computer may yield a cheaper compatible bundle, but can forfeit the original
warranty refund and invalidate the licence. The hard goal does not identify
the right recovery scope; the economic consequences of already executed
commitments do.

The central observation is:

> Knowing where execution failed does not determine which successful
> commitments should be preserved, replaced, or cancelled.

## Gap

Existing work covers important neighboring abilities:

| Research direction | What it evaluates | Remaining question |
|---|---|---|
| compensation and rollback | whether side effects can be reversed | which successful effects should be reversed |
| failure localization and replanning | where an invalid plan should resume | whether a broader or narrower valid repair wastes money |
| stateful task benchmarks such as STATE-Bench | whether the requested final database state is reached | which of several valid states respects existing economic commitments |
| dynamic adaptation such as STT-Arena | whether an agent notices a changed condition and replans | whether prior paid commitments create avoidable loss |
| planning and cost optimization | which prospective plan is cheap | how sunk commitments, refunds, fees, and clawbacks change recovery |

RepairScope-Bench does not claim that partial rollback is new. Its target is a
missing evaluation question:

> After real tool calls have created persistent commitments and a later
> action fails, can an agent achieve the remaining hard goal without choosing
> a repair that another feasible repair objectively dominates in both
> irreversible loss and net recovery spending?

## Why a fixed failure boundary

v0.6 intentionally controls the pre-failure state. This does not make the
commitments textual fiction: the builder creates them using executable tools,
records the returned identifiers and charges, injects the changed condition,
and performs the failed call. The snapshot is therefore a real reachable
state.

Starting every model from that same state isolates recovery-scope selection.
An end-to-end extension can later measure planning quality, but mixing
different prefixes in the first benchmark would make recovery comparisons
ambiguous: models would face different commitments, policies, and losses.

The paper must state this boundary explicitly rather than calling v0.6 a
complete end-to-end agent benchmark.

## Objective rather than “value”

“Value-aware recovery” invites subjective judgments about comfort or
preference. v0.6 uses a narrower, auditable claim. Hard requirements determine
feasibility. Two ledger-derived economic quantities determine dominance:
irreversible loss and net recovery outlay.

No exchange rate between those objectives is assumed. A solution is wrong for
repair quality only when another feasible solution is no worse on both and
strictly better on at least one. This supports multiple valid answers and
avoids an LLM judge or author-assigned utility.

## Benchmark construction

The benchmark contributes:

1. a STATE-backed construction pipeline that materializes and hashes real
   failure boundaries;
2. 24 recovery tasks across travel and after-sales purchasing, with local and
   cross-commitment alternatives;
3. single-fact counterfactual pairs in which the economically defensible
   repair scope flips;
4. deterministic hard-goal checking and transaction-ledger accounting;
5. a semantic state-search Oracle cross-checked by an independent enumerator;
6. metrics that separate task completion from dominated recovery.

The key experimental pattern is not merely that agents fail. A particularly
informative result is:

```text
high Goal Pass
+ lower Non-Dominated Repair Pass
= agents can execute a valid repair but choose an avoidably costly scope
```

The deterministic baselines already demonstrate that the benchmark can expose
this gap: full rollback completes 24/24 tasks but obtains 0/24
Non-Dominated Repair Pass, while local repair completes 24/24 and obtains
12/24.

## Evidence needed for a conference paper

The repository is an implementable benchmark release, but a strong paper
still needs:

- five-run evaluations of current GPT, Claude, Qwen, and DeepSeek models;
- per-family and per-mechanism error analysis;
- evidence that models actually query distributed facts rather than exploit
  identifiers or templates;
- paraphrase and held-out-template robustness;
- independent human audit of constraints, contract text, and Oracle traces;
- additional independently authored task families if strong models saturate
  the current 24 cases.

Difficulty should come from meaningful economic counterfactuals and
cross-contract dependencies, not malformed tools, hidden termination
protocols, or arbitrary interaction traps.

## Claim boundary and risks

The defensible novelty is the benchmark formulation and executable
measurement, not the general idea of compensating or partially rolling back
work. The release does not cover pre-failure planning or subjective
preference elicitation.

Major risks are limited domain breadth, templated family structure, and
Oracle incompleteness. The countermeasures are held-out mechanisms,
single-fact pair validation, two solvers, `oracle_violation` handling, and
release-time baseline gates. If all goal-completing model traces become
non-dominated, the correct response is to expand economic mechanisms and
families—not to lower scores through interface traps.
