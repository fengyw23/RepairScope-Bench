# Scorer–Agent Observability Audit

RepairScope-Bench rejects a task when the deterministic scorer uses a fact
that an agent cannot recover through the public instruction, prefix trace, or
structured tool results. A natural-language hint or a tool description is not
enough evidence for a scored rule.

## Threat model

The audit is designed to catch four benchmark-construction failures:

1. **Scorer-only rules:** the evaluator enforces a dependency that no public
   query returns.
2. **Ambiguous rule encoding:** prose says that one option requires another,
   while the structured response only describes a fee that applies when both
   are active.
3. **Single-path diagnostics:** the same fact is available through several
   linked records, but fact-acquisition scoring recognizes only one record ID.
4. **Incomplete scope diagnostics:** the agent omits or adds a new option, but
   over-repair or under-repair only compares pre-existing commitments.

## Release invariants

The v3 validator now enforces the following invariants for every task:

- Every hard-goal atom has a replayable evidence record.
- A compatibility or dependency rule cannot use `tool_rule` evidence that
  merely matches words in a tool description.
- `forbid_pair`, `requires_any`, and `requires_all` rules are returned as
  structured `relationship_rules` with stable option IDs and explicit
  semantics.
- Pairwise `compatible=true` or `coexistence_allowed=true` does not hide a
  required companion. Compatibility queries return all relationship rules
  involving either queried option.
- Every economic trigger is returned both in its compact form and as an
  explicit `applies_when` predicate. The latter states the predicate,
  aggregation, records or options, comparison operator, and threshold.
- Every linked record advertised as a route to an economic term must return
  the same complete term.
- Every available candidate's coverage, quantity, attributes, and total price
  must be reproducible through search.
- Every boundary commitment's coverage, attributes, paid amount, and refund
  must be reproducible through record and preview tools.
- Changed-fact acquisition accepts every equivalent query path that returns
  the exact term ID, field, and value before the first successful mutation.
- Scope diagnostics compare both boundary dispositions and newly added
  options.

## Current v3 audit result

The checked-in 80-task release passes:

| Audit target | Replayed |
|---|---:|
| Hard-constraint evidence references | 624 / 624 |
| Scored public state atoms | 1,320 / 1,320 |
| `requires_any` rules | 32 / 32 |
| `forbid_pair` rules | 16 / 16 |
| Unique, replayable gold scopes | 80 / 80 |

Run the gate with:

```bash
repairscope validate data/v3
python -m pytest tests/test_v3.py -q
```

A generated task must not be published when either
`validated_evidence_count != evidence_reference_count` or
`observable_state_atom_count != observable_state_atom_total`.

## Regression case

The ultrasound-dock counterfactual pair originally exposed a companion
dependency only as prose inside an economic term. The evaluator nevertheless
enforced a private `requires_any` rule. DeepSeek-V4-Pro consequently bought the
standalone dock and failed both variants.

After the public tools began returning the exact structured dependency, the
same model and snapshots selected:

- `$150` dock + `$180` required adapter in the zero-certification-fee variant;
- return the `$1,800` core device and buy the `$2,250` integrated bundle in the
  `$400` certification-fee variant.

Both runs reached the unique gold at `$330` and `$450`, respectively. This
regression demonstrates why scorer correctness alone is insufficient:
benchmark validity also requires scorer–agent information symmetry.
