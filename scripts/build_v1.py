"""Build RepairScope-Bench v1.0 from executable commitment-graph scenarios."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repairscope_bench.v1_environment import (  # noqa: E402
    CommitmentRecoveryEnvironment,
    snapshot_hash,
)
from repairscope_bench.v1_oracle import (  # noqa: E402
    clear_v1_oracle_cache,
    frontier_signature,
    solve_task_v1,
)


OUTPUT = ROOT / "data" / "v1"
GOLD_OUTPUT = ROOT / "data" / "gold" / "v1.json"


STRUCTURES = [
    "sunk_vs_marginal",
    "multi_hop_propagation",
    "shared_commitment",
    "nonlinear_threshold",
    "conditional_contract",
    "partial_quantity",
    "bridge_vs_replacement",
    "joint_bundle_selection",
    "explicit_horizon",
    "pareto_tradeoff",
]

STRUCTURE_LABELS = {
    "sunk_vs_marginal": "sunk cost versus marginal recovery cost",
    "multi_hop_propagation": "multi-hop economic impact propagation",
    "shared_commitment": "shared-commitment preservation",
    "nonlinear_threshold": "non-linear threshold effect",
    "conditional_contract": "conditional contract logic",
    "partial_quantity": "partial-quantity rollback",
    "bridge_vs_replacement": "bridge repair versus upstream replacement",
    "joint_bundle_selection": "joint compatible-bundle selection",
    "explicit_horizon": "explicit-horizon recurring cost",
    "pareto_tradeoff": "genuine Pareto trade-off",
}

DOMAINS = ["travel", "after_sales", "saas", "event_logistics"]

DOMAIN_PROFILES = {
    "travel": {
        "setting": ["Shanghai medical congress", "Shenzhen client summit"],
        "owner": ["conference traveller", "corporate traveller"],
        "capabilities": [
            "lodging",
            "ground_transport",
            "event_access",
            "arrival_transport",
            "meal_or_venue_service",
        ],
        "boundary_names": [
            "existing hotel",
            "airport transfer",
            "conference pass",
            "arrival flight",
        ],
        "gap_name": "required dinner or venue service",
        "carrier": ["hotel refund", "package settlement"],
    },
    "after_sales": {
        "setting": ["radiology workstation", "clinic cold-chain console"],
        "owner": ["hospital procurement team", "clinic operations team"],
        "capabilities": [
            "core_device",
            "warranty_cover",
            "licensed_software",
            "display_or_sensor",
            "missing_accessory",
        ],
        "boundary_names": [
            "approved core device",
            "service warranty",
            "bound software licence",
            "retained display or sensor",
        ],
        "gap_name": "required compatible accessory",
        "carrier": ["return refund", "licence settlement"],
    },
    "saas": {
        "setting": ["regulated analytics workspace", "customer-support platform"],
        "owner": ["enterprise administrator", "security administrator"],
        "capabilities": [
            "core_subscription",
            "security_coverage",
            "data_connector",
            "support_entitlement",
            "required_integration",
        ],
        "boundary_names": [
            "core annual subscription",
            "security package",
            "data connector",
            "premium support plan",
        ],
        "gap_name": "required integration",
        "carrier": ["subscription termination", "recurring licence charge"],
    },
    "event_logistics": {
        "setting": ["vaccination outreach event", "regional product launch"],
        "owner": ["event coordinator", "logistics coordinator"],
        "capabilities": [
            "venue_capacity",
            "transport_capacity",
            "storage_capacity",
            "insurance_cover",
            "missing_vendor_service",
        ],
        "boundary_names": [
            "confirmed venue",
            "transport contract",
            "storage service",
            "event insurance",
        ],
        "gap_name": "required final-mile vendor service",
        "carrier": ["supplier deposit", "volume discount clawback"],
    },
}


def main() -> None:
    tasks = []
    scenario_number = 0
    for structure_index, structure in enumerate(STRUCTURES):
        for domain_index, domain in enumerate(DOMAINS):
            for instance in range(2):
                scenario_number += 1
                for variant_role in ("alpha", "beta"):
                    tasks.append(
                        build_task(
                            scenario_number,
                            structure_index,
                            structure,
                            domain_index,
                            domain,
                            instance,
                            variant_role,
                        )
                    )

    clear_v1_oracle_cache()
    gold: dict[str, Any] = {}
    for task in tasks:
        oracle = solve_task_v1(task)
        if not oracle.feasible:
            raise RuntimeError(f"{task['task_id']}: no feasible repair")
        if oracle.feasible_scope_count < 3:
            raise RuntimeError(f"{task['task_id']}: fewer than three scopes")
        if len(oracle.frontier) >= oracle.feasible_terminal_count:
            raise RuntimeError(f"{task['task_id']}: no dominated feasible repair")
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.independent_frontier
        ):
            raise RuntimeError(f"{task['task_id']}: Oracles disagree")
        gold[task["task_id"]] = oracle.as_dict()

    _validate_pairs(tasks, gold)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.json"):
        old.unlink()
    for task in tasks:
        (OUTPUT / f"{task['task_id']}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    GOLD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    GOLD_OUTPUT.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tasks)} tasks from {scenario_number} scenarios.")


def build_task(
    scenario_number: int,
    structure_index: int,
    structure: str,
    domain_index: int,
    domain: str,
    instance: int,
    variant_role: str,
) -> dict[str, Any]:
    profile = DOMAIN_PROFILES[domain]
    scenario_id = f"scenario-{scenario_number:04d}"
    task_id = f"rsb-{scenario_number:04d}-{variant_role[0]}"
    pair_id = f"pair-{scenario_number:04d}"
    rank = ((scenario_number - 1) * 37) % 80
    frontier_profile = (
        "multi_two" if rank < 32 else "singleton" if rank < 64 else "multi_three"
    )
    difficulty = _difficulty(structure, domain_index, instance)
    split = "dev" if scenario_number <= 24 else "test" if scenario_number <= 48 else "heldout"
    capabilities = profile["capabilities"]
    c1, c2, c3, c4, gap = capabilities
    prefix = f"{scenario_number:04d}"
    ids = {
        "b1": f"{prefix}-b1",
        "b2": f"{prefix}-b2",
        "b3": f"{prefix}-b3",
        "b4": f"{prefix}-b4",
    }

    boundary_terms = _boundary_terms(frontier_profile, variant_role)
    boundary_options = []
    for key, capability, name, paid, refund in zip(
        ("b1", "b2", "b3", "b4"),
        (c1, c2, c3, c4),
        profile["boundary_names"],
        boundary_terms["paid"],
        boundary_terms["refund"],
        strict=True,
    ):
        provides = {capability: 1}
        if structure == "shared_commitment" and key == "b1":
            provides["shared_secondary_goal"] = 1
        if structure == "partial_quantity" and key == "b3":
            provides["covered_units"] = 6
        boundary_options.append(
            _option(
                ids[key],
                name,
                capability,
                paid,
                provides,
                available=True,
                refund=refund,
                delivery_day=1,
            )
        )

    local_total, route_totals, pair_charge = _economic_targets(
        frontier_profile, variant_role
    )
    fixed_adjustments = _fixed_contract_purchase_adjustments(structure)
    route_totals = {
        route: total - fixed_adjustments.get(route, 0)
        for route, total in route_totals.items()
    }
    local_provides = {gap: 1}
    route_provides = {
        "A": {c1: 1, c3: 1, gap: 1},
        "B": {c1: 1, c2: 1, gap: 1},
        "C": {c1: 1, c4: 1, gap: 1},
        "D": {c1: 1, c2: 1, c3: 1, c4: 1, gap: 1},
    }
    if structure == "shared_commitment":
        for provides in route_provides.values():
            provides["shared_secondary_goal"] = 1
    if structure == "partial_quantity":
        local_provides["covered_units"] = 2
        route_provides["A"]["covered_units"] = 8
        route_provides["B"]["covered_units"] = 2
        route_provides["C"]["covered_units"] = 2
        route_provides["D"]["covered_units"] = 8
    if structure == "bridge_vs_replacement":
        local_provides["bridge_certification"] = 1
        for provides in route_provides.values():
            provides["bridge_certification"] = 1

    route_specs = {
        "L": _route_options(
            prefix, "L", local_total, local_provides, structure, gap, profile
        ),
        **{
            route: _route_options(
                prefix,
                route,
                route_totals.get(route, 300000),
                provides,
                structure,
                gap,
                profile,
            )
            for route, provides in route_provides.items()
        },
    }
    recovery_options = [
        option for options in route_specs.values() for option in options
    ]
    failed_option = _option(
        f"{prefix}-failed",
        f"unavailable {profile['gap_name']}",
        gap,
        18000,
        {gap: 1},
        available=False,
        refund=0,
        delivery_day=2,
    )
    decoy = _option(
        f"{prefix}-decoy",
        f"late {profile['gap_name']}",
        gap,
        5000,
        {gap: 1},
        available=True,
        refund=0,
        delivery_day=9,
    )
    inventory = boundary_options + recovery_options + [failed_option, decoy]
    compatibility = _route_exclusion_rules(
        {**route_specs, "X": [decoy]}
    )

    contracts = _mechanism_contracts(
        structure,
        ids,
        pair_charge,
        frontier_profile,
        variant_role,
        profile,
    )
    hard_capabilities = [
        {"capability": capability, "min": 1, "max": 1}
        for capability in (c1, c2, c3, c4, gap)
    ]
    if structure == "shared_commitment":
        hard_capabilities.append(
            {"capability": "shared_secondary_goal", "min": 1, "max": 1}
        )
    if structure == "partial_quantity":
        hard_capabilities.append(
            {"capability": "covered_units", "min": 8, "max": 8}
        )
    if structure == "bridge_vs_replacement":
        hard_capabilities.append(
            {"capability": "bridge_certification", "min": 1, "max": 1}
        )

    initial_task = {
        "schema_version": "1.0",
        "task_id": task_id,
        "scenario_id": scenario_id,
        "counterfactual_pair_id": pair_id,
        "variant_role": variant_role,
        "domain": domain,
        "environment_type": "repairscope.commitment_graph.v1",
        "reasoning_structure": structure,
        "reasoning_structure_label": STRUCTURE_LABELS[structure],
        "secondary_structures": _secondary_structures(structure),
        "economic_carriers": [
            profile["carrier"][instance],
            "replacement purchase",
        ],
        "difficulty_level": difficulty,
        "frontier_profile": frontier_profile,
        "split": split,
        "now": "2026-09-01T09:00:00+08:00",
        "max_turns": 15,
        "instruction": _instruction(profile, structure, instance),
        "inventory": inventory,
        "contracts": contracts,
        "compatibility_rules": compatibility,
        "hard_goals": {
            "capabilities": hard_capabilities,
            "attribute_requirements": [
                {
                    "capability": gap,
                    "attribute": "delivery_day",
                    "op": "le",
                    "value": 4,
                }
            ],
            "max_active_value_cents": 500000,
        },
        "initial_snapshot": {"commitments": []},
        "initial_snapshot_sha256": snapshot_hash({"commitments": []}),
        "failure_snapshot": {"commitments": []},
        "snapshot_sha256": "",
        "pre_failure_trace": [],
        "prefix_ledger": [],
        "latest_failure": {},
        "boundary_commitments": [],
        "changed_fact": _changed_fact(
            frontier_profile, structure, variant_role, pair_charge
        ),
        "construction": {
            "prefix_generated_by_public_tools": True,
            "failure_generated_by_public_tool": True,
            "necessary_action_order_invariant": True,
            "state_bench_provenance": (
                "travel-domain adapter derived from pinned STATE-Bench travel semantics"
                if domain == "travel"
                else (
                    "after-sales adapter derived from pinned STATE-Bench customer-support semantics"
                    if domain == "after_sales"
                    else "native RepairScope stateful domain"
                )
            ),
        },
    }
    _materialize_boundary(initial_task, boundary_options, failed_option)
    return initial_task


def _materialize_boundary(
    task: dict[str, Any],
    boundary_options: list[dict[str, Any]],
    failed_option: dict[str, Any],
) -> None:
    environment = CommitmentRecoveryEnvironment(task)
    names = environment.names
    for option in boundary_options:
        result = environment.execute_tool(
            names["book"], {names["option"]: option["option_id"]}
        )
        if not result.ok:
            raise RuntimeError(result.message)
    failed = environment.execute_tool(
        names["book"], {names["option"]: failed_option["option_id"]}
    )
    if failed.ok:
        raise RuntimeError("Failure option unexpectedly succeeded")
    prefix_events = environment.event_log[:-1]
    task["pre_failure_trace"] = [
        {
            "step": index,
            "tool": item["tool"],
            "arguments": item["arguments"],
            "result": item["result"],
        }
        for index, item in enumerate(prefix_events, start=1)
    ]
    task["prefix_ledger"] = deepcopy(environment.ledger)
    task["latest_failure"] = {
        "tool": environment.event_log[-1]["tool"],
        "arguments": environment.event_log[-1]["arguments"],
        "result": failed.as_dict(),
    }
    task["failure_snapshot"] = {
        "commitments": sorted(
            environment.commitments.values(),
            key=lambda item: item["entity_id"],
        )
    }
    for item in task["failure_snapshot"]["commitments"]:
        item["created_after_boundary"] = False
    task["snapshot_sha256"] = snapshot_hash(task["failure_snapshot"])
    task["boundary_commitments"] = [
        {
            **deepcopy(item),
            "primary_capability": next(iter(item["provides"])),
        }
        for item in task["failure_snapshot"]["commitments"]
    ]
    task["contracts"] = _resolve_contract_entity_ids(
        task["contracts"], task["boundary_commitments"]
    )
    for option in task["inventory"]:
        if option["option_id"] in {
            item["option_id"] for item in task["boundary_commitments"]
        }:
            option["available"] = False


def _boundary_terms(
    frontier_profile: str, variant_role: str
) -> dict[str, list[int]]:
    if frontier_profile == "singleton":
        return {
            "paid": [100000, 40000, 30000, 50000],
            "refund": [
                10000 if variant_role == "alpha" else 100000,
                10000,
                30000,
                10000,
            ],
        }
    return {
        "paid": [100000, 40000, 30000, 50000],
        "refund": [
            100000,
            40000,
            20000,
            30000 if frontier_profile == "multi_three" else 10000,
        ],
    }


def _economic_targets(
    frontier_profile: str, variant_role: str
) -> tuple[int, dict[str, int], int]:
    if frontier_profile == "singleton":
        return 50000, {"A": 90000, "B": 100000, "C": 120000}, 0
    if frontier_profile == "multi_two":
        return (
            50000,
            {"A": 90000, "B": 140000, "C": 60000},
            80000 if variant_role == "alpha" else 0,
        )
    return (
        50000,
        {"A": 90000, "B": 140000, "C": 80000},
        80000 if variant_role == "alpha" else 0,
    )


def _fixed_contract_purchase_adjustments(structure: str) -> dict[str, int]:
    if structure == "multi_hop_propagation":
        return {"C": 8000}
    if structure == "nonlinear_threshold":
        return {"C": 15000}
    if structure == "conditional_contract":
        return {"C": 12000}
    if structure == "partial_quantity":
        return {"C": 6000}
    return {}


def _route_options(
    prefix: str,
    route: str,
    total: int,
    provides: dict[str, int],
    structure: str,
    gap: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    split = (
        structure in {"multi_hop_propagation", "joint_bundle_selection"}
        or (structure == "bridge_vs_replacement" and route == "L")
    )
    parts = list(provides.items()) if split else [("bundle", 1)]
    if not split:
        parts_provides = [provides]
    else:
        parts_provides = [{capability: amount} for capability, amount in parts]
    totals = _allocate(total, len(parts_provides))
    options = []
    for index, (part_provides, part_total) in enumerate(
        zip(parts_provides, totals, strict=True), start=1
    ):
        if structure == "explicit_horizon":
            monthly = part_total // 12
            upfront = part_total - monthly * 12
            horizon = 12
        else:
            monthly = 0
            upfront = part_total
            horizon = 0
        options.append(
            _option(
                f"{prefix}-r{route.lower()}{index}",
                (
                    f"{profile['setting'][int(prefix) % 2]} "
                    f"{route} recovery component {index}"
                ),
                gap if route == "L" else "recovery_package",
                upfront,
                part_provides,
                available=True,
                refund=0,
                delivery_day=2 + (index % 2),
                monthly=monthly,
                horizon=horizon,
                route_code=route,
            )
        )
    return options


def _mechanism_contracts(
    structure: str,
    ids: dict[str, str],
    pair_charge: int,
    frontier_profile: str,
    variant_role: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts = []
    if frontier_profile != "singleton":
        contracts.append(
            {
                "contract_id": "PAIR-TERM",
                "description": (
                    f"The linked {profile['carrier'][0]} applies when both the "
                    f"first and second original commitments change; charge "
                    f"{pair_charge} cents."
                ),
                "trigger": {
                    "type": "all_changed",
                    "entity_option_ids": [ids["b1"], ids["b2"]],
                },
                "charge_cents": pair_charge,
            }
        )
    if structure == "nonlinear_threshold":
        contracts.append(
            {
                "contract_id": "THRESHOLD-TERM",
                "description": (
                    "A 15000-cent rebate is clawed back when retained paid "
                    "value across the first and fourth original commitments "
                    "falls below 10000 cents."
                ),
                "trigger": {
                    "type": "retained_paid_below",
                    "entity_option_ids": [
                        ids["b1"],
                        ids["b4"],
                    ],
                    "threshold_cents": 10000,
                },
                "charge_cents": 15000,
            }
        )
    if structure == "conditional_contract":
        contracts.append(
            {
                "contract_id": "CONDITIONAL-TERM",
                "description": (
                    "A 12000-cent settlement applies only when both the first "
                    "and fourth original commitments change."
                ),
                "trigger": {
                    "type": "all_changed",
                    "entity_option_ids": [ids["b1"], ids["b4"]],
                },
                "charge_cents": 12000,
            }
        )
    if structure == "multi_hop_propagation":
        contracts.append(
            {
                "contract_id": "LICENCE-HOP",
                "description": (
                    "Changing both the core commitment and its linked service "
                    "causes an 8000-cent migration settlement."
                ),
                "trigger": {
                    "type": "all_changed",
                    "entity_option_ids": [ids["b1"], ids["b4"]],
                },
                "charge_cents": 8000,
            }
        )
    if structure == "partial_quantity":
        contracts.append(
            {
                "contract_id": "VOLUME-TERM",
                "description": (
                    "Changing at least two of the listed original components "
                    "claws back a 6000-cent volume credit."
                ),
                "trigger": {
                    "type": "changed_count_at_least",
                    "entity_option_ids": [
                        ids["b1"],
                        ids["b4"],
                    ],
                    "count": 2,
                },
                "charge_cents": 6000,
            }
        )
    return contracts


def _resolve_contract_entity_ids(
    contracts: list[dict[str, Any]],
    boundary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    option_to_entity = {
        item["option_id"]: item["entity_id"] for item in boundary
    }
    result = deepcopy(contracts)
    for contract in result:
        trigger = contract["trigger"]
        option_ids = trigger.pop("entity_option_ids", [])
        trigger["entity_ids"] = [option_to_entity[item] for item in option_ids]
    return result


def _route_exclusion_rules(
    route_specs: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    rules = []
    for options in route_specs.values():
        if len(options) <= 1:
            continue
        option_ids = [item["option_id"] for item in options]
        rules.extend(
            {
                "type": "requires_all",
                "if_option_id": option_id,
                "all_option_ids": option_ids,
            }
            for option_id in option_ids
        )
    routes = list(route_specs)
    for index, left_route in enumerate(routes):
        for right_route in routes[index + 1 :]:
            for left in route_specs[left_route]:
                for right in route_specs[right_route]:
                    rules.append(
                        {
                            "type": "forbid_pair",
                            "option_ids": [
                                left["option_id"],
                                right["option_id"],
                            ],
                        }
                    )
    return rules


def _option(
    option_id: str,
    name: str,
    kind: str,
    upfront: int,
    provides: dict[str, int],
    *,
    available: bool,
    refund: int,
    delivery_day: int,
    monthly: int = 0,
    horizon: int = 0,
    route_code: str | None = None,
) -> dict[str, Any]:
    attributes = {"delivery_day": delivery_day}
    if route_code is not None:
        attributes["system_code"] = f"system-{route_code.lower()}"
    return {
        "option_id": option_id,
        "name": name,
        "kind": kind,
        "available": available,
        "upfront_cents": upfront,
        "monthly_cents": monthly,
        "horizon_months": horizon,
        "refund_after_purchase_cents": refund,
        "provides": provides,
        "attributes": attributes,
    }


def _allocate(total: int, count: int) -> list[int]:
    quotient, remainder = divmod(total, count)
    return [
        quotient + (1 if index < remainder else 0)
        for index in range(count)
    ]


def _difficulty(structure: str, domain_index: int, instance: int) -> int:
    if structure in {"sunk_vs_marginal", "shared_commitment"}:
        return 1
    if structure in {
        "multi_hop_propagation",
        "nonlinear_threshold",
        "conditional_contract",
    }:
        return 2
    if structure in {
        "partial_quantity",
        "bridge_vs_replacement",
        "joint_bundle_selection",
    }:
        return 3
    if structure == "pareto_tradeoff":
        return 4
    return 4 if (domain_index + instance) % 2 else 2


def _secondary_structures(structure: str) -> list[str]:
    mapping = {
        "multi_hop_propagation": ["joint_bundle_selection"],
        "nonlinear_threshold": ["sunk_vs_marginal"],
        "conditional_contract": ["multi_hop_propagation"],
        "partial_quantity": ["joint_bundle_selection"],
        "bridge_vs_replacement": ["shared_commitment"],
        "joint_bundle_selection": ["multi_hop_propagation"],
        "explicit_horizon": ["sunk_vs_marginal"],
        "pareto_tradeoff": ["joint_bundle_selection"],
    }
    return mapping.get(structure, [])


def _instruction(
    profile: dict[str, Any], structure: str, instance: int
) -> str:
    horizon = (
        " Evaluate charges over the explicitly required 12-month service horizon."
        if structure == "explicit_horizon"
        else ""
    )
    quantity = (
        " The completed configuration must cover exactly eight operational units."
        if structure == "partial_quantity"
        else ""
    )
    return (
        f"Complete the {profile['setting'][instance]} for the "
        f"{profile['owner'][instance]}. Four paid commitments are already "
        f"active, but the {profile['gap_name']} just failed. Preserve every "
        f"required function, use options deliverable by day 4, and make the "
        f"best supported recovery decision without asking me to choose."
        f"{quantity}{horizon}"
    )


def _changed_fact(
    frontier_profile: str,
    structure: str,
    variant_role: str,
    pair_charge: int,
) -> dict[str, Any]:
    if frontier_profile == "singleton":
        return {
            "fact_type": "refund_value",
            "model_access": "cancellation preview",
            "variant_role": variant_role,
            "value_cents": 10000 if variant_role == "alpha" else 100000,
            "changed_path": "boundary_option[0].refund_after_purchase_cents",
        }
    return {
        "fact_type": (
            "licence_or_package_settlement"
            if structure != "explicit_horizon"
            else "explicit_horizon_adjustment"
        ),
        "model_access": "linked contract terms",
        "variant_role": variant_role,
        "value_cents": pair_charge,
        "changed_path": "contracts[PAIR-TERM].charge_cents",
    }


def _validate_pairs(
    tasks: list[dict[str, Any]], gold: dict[str, Any]
) -> None:
    pairs: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        pairs.setdefault(task["counterfactual_pair_id"], []).append(task)
    if len(pairs) != 80:
        raise RuntimeError("Expected 80 counterfactual pairs")
    for pair_id, members in pairs.items():
        if len(members) != 2:
            raise RuntimeError(f"{pair_id}: expected two variants")
        scopes = [
            {
                tuple(sorted(item["scope"].items()))
                for item in gold[task["task_id"]]["frontier"]
            }
            for task in members
        ]
        if scopes[0] == scopes[1]:
            raise RuntimeError(f"{pair_id}: frontier scope did not change")


if __name__ == "__main__":
    main()
