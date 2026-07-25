# Data Card: RepairScope-Bench v2.0 Pilot

## Composition

| Field | Value |
|---|---:|
| Executable tasks | 24 |
| Base scenarios / strict pairs | 12 |
| Domains | 4, with 6 tasks each |
| Reasoning mechanisms | 10, multi-label |
| Construction strata | 14 C2, 10 C3 |
| Multi-point frontiers | 3 |
| Tasks with positive-loss accepted points | 3 |
| Minimum feasible semantic scopes | 4 |
| Gold requiring at least 3 mutations | 13 |
| Model turns | 15 |

All tasks are synthetic dev tasks. Public gold is intentional for the pilot.
Future validation and hidden-test specifications belong under the ignored
`data/private/` path and must not be committed.

## Starting state

Every task starts after four successful public write operations and one
actual failed write. The successful operations create persistent commitments
and an auditable prefix ledger. The same writes reproduce the stored failure
snapshot and its SHA-256 hash.

The model receives only the customer request, successful activity, latest
failure, and domain tools. Inventory, policies, contracts, hard goals,
counterfactual identity, mechanism labels, and gold are not placed in the
model prompt.

## Gold and economics

`data/gold/v2.json` stores:

- pair/scenario identity and variant role;
- reasoning signature and mechanism card;
- exact changed-fact and reveal-tool manifest;
- all feasible terminals and the Pareto frontier;
- public-tool replay witnesses;
- structural complexity profiles;
- validity certificates.

The evaluator loads frozen gold. Dataset validation recomputes the
declarative Oracle, replays feasible claims through public tools, and rejects
any disagreement.

## Known limitations

- This is a development pilot, not the final leaderboard set.
- The four public tool surfaces currently share an auditable commitment and
  ledger substrate, despite having separate domain operations and vocabulary.
- Most tasks still have singleton frontiers; the pilot contains ten C3 and
  three multi-frontier cases.
- Empirical difficulty is absent until a frozen multi-model calibration run
  is available.
- Naturalness and business realism still require independent human audit.

These limitations are explicit scale-up gates. They must not be hidden by
adding tool traps or relabelling the current pilot as a final benchmark.
