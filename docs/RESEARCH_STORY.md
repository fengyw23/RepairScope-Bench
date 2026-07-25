# RepairScope-Bench v3.0 Research Story

## Problem

Tool-using agents do not merely produce text. They book, pay, cancel, return,
and create persistent external commitments. When a later step fails, restoring
technical consistency is not enough: some successful commitments still serve
the user's goal, while changing them can trigger refunds, fees, contract
effects, and replacement purchases.

Consider a conference trip. The flight, hotel, transfer, and admission are
already confirmed when dinner booking fails. Booking another restaurant may
be cheapest. If a refundable hotel package plus a different dinner and
transfer costs less, a wider repair can instead be correct. Cancelling the
arrival flight is usually harmful because it still serves the conference
goal. The failure location does not determine the repair boundary.

The same structure appears after a workstation purchase. A missing dock may
be repaired locally, bridged with a certified adapter, or handled by replacing
the computer and affected warranty or licence. The display may remain useful
under every valid repair.

## Gap

Existing benchmarks primarily test whether an agent:

- reaches a valid final state;
- notices a dynamic change and replans;
- rolls back side effects safely;
- edits an existing order according to an explicit user request.

Those capabilities are necessary, but they do not isolate the decision studied
here: among several valid post-failure repairs, which already executed
commitments should be kept, changed, or cancelled after all observable
incremental monetary consequences are combined?

The contribution is not the general idea of partial rollback. Classical
planning and workflow research already considered partial recovery. The gap
is deterministic, tool-executable evaluation of repair-scope selection for
modern language-model agents over persistent commitments.

## Benchmark question

> When real travel reservations or product orders are already active and a
> later operation fails, can an agent infer and execute the unique
> lowest-incremental-cost repair scope from observable records, policies,
> contracts, inventory, and compatibility?

The benchmark fixes the failure boundary to control state while preserving
real side effects: every prior commitment was created by a public write tool
in the same native environment. v3.0 does not claim to evaluate the model's
pre-failure planning.

## Design

The dataset crosses ten reusable reasoning structures with two native domains.
Economic mechanisms are carriers, not labels. A threshold may be a travel
package minimum or a purchasing quantity discount; a bridge may be a transfer
service or a certified adapter.

Each base scenario has two versions that differ in one tool-queryable fact.
The unique optimal scope must flip. This paired design tests whether a model
uses the decisive fact rather than applying a fixed “repair locally” or
“rollback everything” rule.

The benchmark uses one scalar objective—post-boundary Incremental Recovery
Cost—because every included consequence is a deterministic cash event.
Subjective convenience, risk attitude, or unpriced preference is excluded
from gold.

## Contributions

1. A formalization of recovery-scope selection over persistent commitments
   with deterministic hard constraints and auditable incremental cost.
2. A two-domain executable benchmark built on native STATE-Bench travel and
   customer-support state rather than a shared generic slot ledger.
3. Ten cross-domain reasoning structures, including multi-hop effects,
   thresholds, Boolean contracts, partial quantities, bridges, combinations,
   recurring cost, and selective dependency cutting.
4. Forty single-fact counterfactual pairs whose unique gold scope changes.
5. Evidence-complete hard goals: every evaluated atom has a reproducible
   model-visible source.
6. Separate measurement of final scope reasoning and execution waste without
   an LLM judge.

## Evidence sought

The main empirical claim should not be merely that models fail. Experiments
should show:

- Goal Pass is substantially higher than Unique Scope Pass, demonstrating
  that completion and repair quality differ;
- fixed heuristics remain below 65%;
- models often fail matched counterfactual pairs despite solving one variant;
- errors decompose into missing investigation, economic reasoning, scope
  selection, and tool execution;
- providing the gold scope produces much higher execution success, isolating
  reasoning from interface difficulty;
- entity renaming, option permutation, and request paraphrases do not change
  Oracle outcomes and do not dominate model results.

## Claim boundary and risks

The current release has 80 tasks from ten generator families and two native
domains. A top-conference paper still requires broad multi-model experiments,
independent human review of scenario realism, prompt and identifier
robustness, hidden-test discipline, and statistical analysis at the paired
scenario level.

The benchmark should not claim to cover all agent recovery, subjective value,
uncertain future outcomes, or end-to-end planning. Its narrow claim is
stronger and testable: agents can complete a task yet choose an objectively
more expensive repair scope over already executed commitments.
