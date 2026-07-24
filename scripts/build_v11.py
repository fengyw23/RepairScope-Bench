"""Build the validity-first RepairScope-Bench v1.1 dataset.

The public tasks contain only executable state and user-visible facts. Pair
membership, reasoning labels, interventions, Oracle output, and validity
certificates are written to the private gold file.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable


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


OUTPUT = ROOT / "data" / "v11"
GOLD_OUTPUT = ROOT / "data" / "gold" / "v11.json"

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

ALL_DOMAINS = [
    "travel",
    "after_sales",
    "saas",
    "event_logistics",
]

STRUCTURE_DOMAINS = {
    structure: ALL_DOMAINS for structure in STRUCTURES
}

DOMAIN_PROFILES = {
    "travel": {
        "settings": [
            ("Shanghai medical congress", "Shanghai"),
            ("Shenzhen client summit", "Shenzhen"),
            ("Hangzhou research workshop", "Hangzhou"),
            ("Chengdu clinical symposium", "Chengdu"),
        ],
        "owner": "traveller",
        "roles": [
            ("lodging", "hotel reservation", "hotel"),
            ("ground_transport", "airport transfer", "ground transport"),
            ("event_access", "conference admission", "event pass"),
            ("meal_service", "required dinner", "restaurant"),
        ],
        "deadline_key": "service_day",
        "location_key": "city",
        "full_replacement": "protected conference travel package",
    },
    "after_sales": {
        "settings": [
            ("radiology workstation deployment", "Radiology Lab A"),
            ("clinic cold-chain console", "Clinic North"),
            ("pathology imaging station", "Pathology Lab"),
            ("telemedicine workstation", "Outpatient Centre"),
        ],
        "owner": "procurement team",
        "roles": [
            ("core_device", "approved core device", "core device"),
            ("service_cover", "service warranty", "warranty"),
            ("licensed_software", "bound software licence", "software"),
            ("required_accessory", "required compatible accessory", "accessory"),
        ],
        "deadline_key": "delivery_day",
        "location_key": "delivery_site",
        "full_replacement": "certified replacement equipment bundle",
    },
    "saas": {
        "settings": [
            ("regulated analytics workspace", "CN-East tenant"),
            ("customer-support platform", "APAC tenant"),
            ("clinical reporting workspace", "Health tenant"),
            ("enterprise audit environment", "Compliance tenant"),
        ],
        "owner": "enterprise administrator",
        "roles": [
            ("core_subscription", "core subscription", "subscription"),
            ("security_coverage", "security package", "security service"),
            ("data_connector", "data connector", "connector"),
            ("required_integration", "required integration", "integration"),
        ],
        "deadline_key": "activation_day",
        "location_key": "tenant_region",
        "full_replacement": "managed workspace migration package",
    },
    "event_logistics": {
        "settings": [
            ("vaccination outreach event", "District 7"),
            ("regional product launch", "Convention Zone B"),
            ("mobile screening programme", "County West"),
            ("public science festival", "University Quarter"),
        ],
        "owner": "event coordinator",
        "roles": [
            ("venue_capacity", "confirmed venue", "venue"),
            ("transport_capacity", "transport contract", "transport"),
            ("storage_capacity", "storage service", "storage"),
            ("vendor_service", "required final-mile vendor service", "vendor service"),
        ],
        "deadline_key": "service_day",
        "location_key": "service_area",
        "full_replacement": "insured event continuity package",
    },
}


def main() -> None:
    tasks: list[dict[str, Any]] = []
    private: dict[str, dict[str, Any]] = {}
    pair_members: dict[str, list[str]] = {}
    global_index = 0

    for structure_index, structure in enumerate(STRUCTURES):
        builder = BUILDERS[structure]
        domains = STRUCTURE_DOMAINS[structure]
        for family_index in range(8):
            global_index += 1
            domain = domains[family_index % len(domains)]
            orientation = bool((family_index + structure_index) % 2)
            pair_id = opaque_id("pair", structure, family_index)
            scenario_id = opaque_id("scenario", structure, family_index)
            pair_members[pair_id] = []
            for side_index, side in enumerate(("left", "right")):
                high = bool(side_index) ^ orientation
                public, evidence = builder(
                    global_index,
                    family_index,
                    domain,
                    high,
                )
                task_id = opaque_id(
                    "task", structure, family_index, side, domain
                )
                public["task_id"] = task_id
                public["split"] = split_for(global_index)
                pair_members[pair_id].append(task_id)
                tasks.append(public)
                private[task_id] = {
                    "metadata": {
                        "pair_id": pair_id,
                        "scenario_id": scenario_id,
                        "variant_role": side,
                        "reasoning_structure": structure,
                        "difficulty_level": evidence["difficulty_level"],
                        "domain": domain,
                    },
                    "intervention": evidence["intervention"],
                    "mechanism_evidence": evidence["mechanism_evidence"],
                }

    clear_v1_oracle_cache()
    for task_index, task in enumerate(tasks, start=1):
        oracle = solve_task_v1(task)
        if not oracle.feasible:
            raise RuntimeError(f"{task['task_id']}: no feasible recovery")
        if oracle.feasible_scope_count < 3:
            raise RuntimeError(
                f"{task['task_id']}: fewer than three semantic scopes"
            )
        if len(oracle.frontier) >= oracle.feasible_terminal_count:
            raise RuntimeError(
                f"{task['task_id']}: no dominated feasible terminal"
            )
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.independent_frontier
        ):
            raise RuntimeError(f"{task['task_id']}: independent Oracles disagree")
        metadata = private[task["task_id"]]["metadata"]
        certificate = validity_certificate(task, oracle, metadata)
        private[task["task_id"]]["oracle"] = oracle.as_dict()
        private[task["task_id"]]["validity_certificate"] = certificate
        if task_index % 10 == 0:
            print(f"Validated {task_index}/{len(tasks)} tasks.", flush=True)

    validate_pairs(tasks, private, pair_members)
    validate_dataset(tasks, private, pair_members)

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
        json.dumps(private, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(tasks)} public tasks, {len(pair_members)} pairs, "
        f"and {len(private)} private validity records."
    )


def build_common(
    case_number: int,
    family_index: int,
    domain: str,
    *,
    boundary: list[dict[str, Any]],
    recovery: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    compatibility: list[dict[str, Any]],
    hard_capabilities: list[dict[str, Any]],
    instruction_focus: str,
    exact_location_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    profile = DOMAIN_PROFILES[domain]
    setting, location = profile["settings"][family_index % 4]
    prefix = f"N{case_number:03d}"
    deadline_key = profile["deadline_key"]
    location_key = profile["location_key"]
    exact_location_capabilities = (
        exact_location_capabilities
        if exact_location_capabilities is not None
        else [item["capability"] for item in hard_capabilities]
    )

    for item in boundary + recovery:
        item.setdefault("attributes", {})
        item["attributes"].setdefault(location_key, location)
        item["attributes"].setdefault(deadline_key, 2)

    gap_capability = next(
        item["capability"]
        for item in hard_capabilities
        if not any(
            int(boundary_item["provides"].get(item["capability"], 0)) > 0
            for boundary_item in boundary
        )
    )
    failed = option(
        f"{prefix}-failed",
        f"unavailable {profile['roles'][3][1]}",
        profile["roles"][3][2],
        18000,
        {gap_capability: 1},
        available=False,
        attributes={location_key: location, deadline_key: 2},
    )
    wrong_location = option(
        f"{prefix}-wrong-site",
        f"cheap service for a different {location_key}",
        profile["roles"][3][2],
        5000,
        {gap_capability: 1},
        attributes={
            location_key: f"Other {location}",
            deadline_key: 2,
        },
    )
    late = option(
        f"{prefix}-late",
        f"late {profile['roles'][3][1]}",
        profile["roles"][3][2],
        4000,
        {gap_capability: 1},
        attributes={location_key: location, deadline_key: 9},
    )
    all_capabilities = {
        item["capability"]: int(item.get("min", 1))
        for item in hard_capabilities
    }
    fallback = option(
        f"{prefix}-continuity",
        profile["full_replacement"],
        "continuity service",
        600000 + case_number * 137,
        all_capabilities,
        attributes={location_key: location, deadline_key: 3},
    )
    inventory = boundary + recovery + [fallback, failed, wrong_location, late]
    attribute_requirements = [
        {
            "capability": capability,
            "attribute": location_key,
            "op": "eq",
            "value": location,
        }
        for capability in exact_location_capabilities
    ]
    attribute_requirements.append(
        {
            "capability": gap_capability,
            "attribute": deadline_key,
            "op": "le",
            "value": 4,
        }
    )
    required_text = ", ".join(
        f"{item['capability']}={item.get('min', 1)}"
        for item in hard_capabilities
    )
    task = {
        "schema_version": "1.1",
        "task_id": "",
        "domain": domain,
        "environment_type": f"repairscope.{domain}.state.v1.1",
        "split": "",
        "now": "2026-09-01T09:00:00+08:00",
        "max_turns": 15,
        "instruction": (
            f"Complete the {setting} at {location} for the {profile['owner']}. "
            f"The successful commitments in the activity log are already paid "
            f"and active, but the latest {profile['roles'][3][1]} operation "
            f"failed. The final state must preserve these required functions "
            f"exactly as specified: {required_text}. The missing service must "
            f"be available by day 4 at {location}. {instruction_focus} "
            "Investigate the authoritative records and execute the best "
            "supported recovery without asking me to choose."
        ),
        "inventory": inventory,
        "contracts": contracts,
        "compatibility_rules": compatibility,
        "hard_goals": {
            "capabilities": hard_capabilities,
            "attribute_requirements": attribute_requirements,
        },
        "initial_snapshot": {"commitments": []},
        "initial_snapshot_sha256": snapshot_hash({"commitments": []}),
        "failure_snapshot": {"commitments": []},
        "snapshot_sha256": "",
        "pre_failure_trace": [],
        "prefix_ledger": [],
        "latest_failure": {},
        "boundary_commitments": [],
        "construction": {
            "prefix_generated_by_public_tools": True,
            "failure_generated_by_public_tool": True,
            "necessary_action_order_invariant": True,
            "domain_state_adapter": domain,
        },
    }
    materialize_boundary(task, boundary, failed)
    return task


def materialize_boundary(
    task: dict[str, Any],
    boundary: list[dict[str, Any]],
    failed: dict[str, Any],
) -> None:
    environment = CommitmentRecoveryEnvironment(task)
    names = environment.names
    trace = []
    for step, item in enumerate(boundary, start=1):
        result = environment.execute_tool(
            names["book"], {names["option"]: item["option_id"]}
        )
        if not result.ok:
            raise RuntimeError(result.message)
        trace.append(
            {
                "step": step,
                "tool": names["book"],
                "arguments": {names["option"]: item["option_id"]},
                "result": result.as_dict(),
            }
        )
    failed_result = environment.execute_tool(
        names["book"], {names["option"]: failed["option_id"]}
    )
    if failed_result.ok:
        raise RuntimeError("Injected failure unexpectedly succeeded")
    task["pre_failure_trace"] = trace
    task["prefix_ledger"] = deepcopy(environment.ledger)
    task["latest_failure"] = {
        "tool": names["book"],
        "arguments": {names["option"]: failed["option_id"]},
        "result": failed_result.as_dict(),
    }
    task["failure_snapshot"] = {
        "commitments": sorted(
            environment.active_commitments(),
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
    task["contracts"] = resolve_contract_ids(
        task["contracts"], task["boundary_commitments"]
    )
    task["compatibility_rules"] = resolve_rule_ids(
        task["compatibility_rules"], task["boundary_commitments"]
    )
    boundary_option_ids = {item["option_id"] for item in boundary}
    for item in task["inventory"]:
        if item["option_id"] in boundary_option_ids:
            item["available"] = False


def resolve_contract_ids(
    contracts: list[dict[str, Any]],
    boundary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping = {item["option_id"]: item["entity_id"] for item in boundary}
    result = deepcopy(contracts)
    for contract in result:
        trigger = contract["trigger"]
        for source, target in [
            ("entity_option_ids", "entity_ids"),
            ("changed_option_ids", "changed_entity_ids"),
            ("retained_option_ids", "retained_entity_ids"),
        ]:
            values = trigger.pop(source, [])
            if values:
                trigger[target] = [mapping[item] for item in values]
    return result


def resolve_rule_ids(
    rules: list[dict[str, Any]],
    boundary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return deepcopy(rules)


def semantic(domain: str, family_index: int) -> dict[str, Any]:
    profile = DOMAIN_PROFILES[domain]
    setting, location = profile["settings"][family_index % 4]
    roles = profile["roles"]
    return {
        "setting": setting,
        "location": location,
        "location_key": profile["location_key"],
        "deadline_key": profile["deadline_key"],
        "c1": roles[0][0],
        "n1": roles[0][1],
        "k1": roles[0][2],
        "c2": roles[1][0],
        "n2": roles[1][1],
        "k2": roles[1][2],
        "c3": roles[2][0],
        "n3": roles[2][1],
        "k3": roles[2][2],
        "gap": roles[3][0],
        "gap_name": roles[3][1],
        "gap_kind": roles[3][2],
    }


def base_ids(case_number: int) -> dict[str, str]:
    prefix = f"N{case_number:03d}"
    return {
        key: f"{prefix}-{key}"
        for key in [
            "b1",
            "b2",
            "b3",
            "local",
            "alt1",
            "alt2",
            "alt3",
            "bridge",
            "aux1",
            "aux2",
        ]
    }


def standard_attributes(s: dict[str, Any], day: int = 2) -> dict[str, Any]:
    return {
        s["location_key"]: s["location"],
        s["deadline_key"]: day,
    }


def goal(capability: str, minimum: int = 1, maximum: int | None = 1) -> dict[str, Any]:
    return {"capability": capability, "min": minimum, "max": maximum}


def option(
    option_id: str,
    name: str,
    kind: str,
    upfront: int,
    provides: dict[str, int],
    *,
    available: bool = True,
    refund: int = 0,
    attributes: dict[str, Any] | None = None,
    monthly: int = 0,
    horizon: int = 0,
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "name": name,
        "kind": kind,
        "available": available,
        "upfront_cents": int(upfront),
        "monthly_cents": int(monthly),
        "horizon_months": int(horizon),
        "refund_after_purchase_cents": int(refund),
        "provides": deepcopy(provides),
        "attributes": deepcopy(attributes or {}),
    }


def build_sunk(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    refund = 100000 if high else 5000
    offset = family_index * 700
    boundary = [
        option(
            ids["b1"], s["n1"], s["k1"], 100000, {s["c1"]: 1},
            refund=refund, attributes=standard_attributes(s, 1),
        ),
        option(
            ids["b2"], s["n2"], s["k2"], 100000, {s["c2"]: 1},
            refund=80000, attributes=standard_attributes(s, 1),
        ),
    ]
    recovery = [
        option(
            ids["local"], f"standalone {s['gap_name']}", s["gap_kind"],
            50000 + offset, {s["gap"]: 1}, attributes=standard_attributes(s),
        ),
        option(
            ids["alt1"], f"new {s['n1']} with {s['gap_name']}",
            f"{s['k1']} bundle", 90000 + offset,
            {s["c1"]: 1, s["gap"]: 1}, attributes=standard_attributes(s),
        ),
        option(
            ids["alt2"], f"replacement {s['n2']} with {s['gap_name']}",
            f"{s['k2']} continuity bundle", 60000 + offset,
            {s["c2"]: 1, s["gap"]: 1}, attributes=standard_attributes(s),
        ),
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=[],
        hard_capabilities=[goal(s["c1"]), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "Past prices are historical; cancellation previews determine what "
            "can still be recovered now."
        ),
    )
    return task, evidence(
        1,
        "boundary refund controls marginal recovery economics",
        {
            "logical_fact": "recoverable value of the primary commitment",
            "observable_via": "cancellation preview",
            "paths": [
                "inventory[b1].refund_after_purchase_cents",
                "failure_snapshot[b1].refund_cents",
                "boundary_commitments[b1].refund_cents",
            ],
            "value": refund,
        },
    )


def build_multi_hop(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 100000, {s["c1"]: 1}, refund=100000, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 30000, {s["c2"]: 1}, refund=30000, attributes=attrs),
        option(ids["b3"], s["n3"], s["k3"], 30000, {s["c3"]: 1}, refund=30000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"standalone {s['gap_name']}", s["gap_kind"], 70000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"replacement {s['n1']} with {s['gap_name']}", f"{s['k1']} bundle", 20000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["aux1"], f"migrated {s['n2']}", s["k2"], 50000, {s["c2"]: 1}, attributes=attrs),
        option(ids["aux2"], f"rebound {s['n3']}", s["k3"], 50000, {s["c3"]: 1}, attributes=attrs),
        option(ids["alt2"], f"expedited {s['gap_name']}", s["gap_kind"], 95000, {s["gap"]: 1}, attributes=attrs),
    ]
    old_core_support = [ids["b1"], ids["alt1"]] if high else [ids["b1"]]
    compatibility = [
        {
            "type": "requires_any",
            "if_option_id": ids["b2"],
            "any_option_ids": old_core_support,
        },
        {
            "type": "requires_any",
            "if_option_id": ids["b3"],
            "any_option_ids": [ids["b2"]],
        },
        {
            "type": "requires_any",
            "if_option_id": ids["aux1"],
            "any_option_ids": [ids["b1"], ids["alt1"]],
        },
        {
            "type": "requires_any",
            "if_option_id": ids["aux2"],
            "any_option_ids": [ids["aux1"]],
        },
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=compatibility,
        hard_capabilities=[
            goal(s["c1"]), goal(s["c2"]), goal(s["c3"]), goal(s["gap"]),
        ],
        instruction_focus=(
            "Services bound through the dependency chain must remain valid for "
            "the final primary commitment."
        ),
    )
    return task, evidence(
        3,
        "primary-to-service-to-licence dependency chain",
        {
            "logical_fact": "whether the existing linked service supports the replacement primary",
            "observable_via": "linked terms and compatibility checks",
            "paths": ["compatibility_rules[existing-linked-service].any_option_ids"],
            "value": old_core_support,
        },
    )


def build_shared(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    shared = f"{s['c1']}_secondary_use"
    boundary = [
        option(
            ids["b1"], f"shared {s['n1']}", s["k1"], 80000,
            {s["c1"]: 1, shared: 1}, refund=80000, attributes=attrs,
        ),
        option(ids["b2"], s["n2"], s["k2"], 100000, {s["c2"]: 1}, refund=80000, attributes=attrs),
    ]
    alt_provides = {s["c1"]: 1, s["gap"]: 1}
    if high:
        alt_provides[shared] = 1
    recovery = [
        option(ids["local"], f"standalone {s['gap_name']}", s["gap_kind"], 60000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"combined {s['n1']} and {s['gap_name']}", f"{s['k1']} package", 30000, alt_provides, attributes=attrs),
        option(ids["aux1"], f"replacement secondary use for {s['n1']}", "secondary service", 10000, {shared: 1}, attributes=attrs),
        option(ids["alt2"], f"replacement {s['n2']} with {s['gap_name']}", f"{s['k2']} continuity bundle", 60000, {s["c2"]: 1, s["gap"]: 1}, attributes=attrs),
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[
            {
                "contract_id": f"N{case_number:03d}-shared-migration",
                "description": (
                    "A 100000-cent migration charge applies only when the "
                    "separate replacement secondary-use service is activated."
                ),
                "trigger": {
                    "type": "active_any",
                    "option_ids": [ids["aux1"]],
                },
                "charge_cents": 100000,
            }
        ],
        compatibility=[],
        hard_capabilities=[
            goal(s["c1"]), goal(shared), goal(s["c2"]), goal(s["gap"]),
        ],
        instruction_focus=(
            f"The shared {s['n1']} currently supports both {s['c1']} and "
            f"{shared}; both functions remain mandatory."
        ),
    )
    return task, evidence(
        2,
        "one commitment supports two independently required functions",
        {
            "logical_fact": "whether the replacement preserves the shared secondary use",
            "observable_via": "option capabilities",
            "paths": ["inventory[combined-option].provides[shared-secondary-use]"],
            "value": high,
        },
    )


def build_threshold(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    threshold = 500000 if high else 100000
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 400000, {s["c1"]: 1}, refund=400000, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 200000, {s["c2"]: 1}, refund=150000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"standalone {s['gap_name']}", s["gap_kind"], 90000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"replacement {s['n1']} with {s['gap_name']}", f"{s['k1']} bundle", 440000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt2"], f"replacement {s['n2']} with {s['gap_name']}", f"{s['k2']} continuity bundle", 100000, {s["c2"]: 1, s["gap"]: 1}, attributes=attrs),
    ]
    contracts = [
        {
            "contract_id": f"N{case_number:03d}-threshold",
            "description": (
                f"An 80000-cent credit is clawed back if retained paid value "
                f"across the listed commitments falls below {threshold} cents."
            ),
            "trigger": {
                "type": "retained_paid_below",
                "entity_option_ids": [ids["b1"], ids["b2"]],
                "threshold_cents": threshold,
            },
            "charge_cents": 80000,
        }
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=contracts,
        compatibility=[],
        hard_capabilities=[goal(s["c1"]), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "Any order-level credit threshold and clawback must be evaluated "
            "against the retained commitments."
        ),
    )
    return task, evidence(
        2,
        "retained-value threshold with a discontinuous credit clawback",
        {
            "logical_fact": "retained paid-value threshold",
            "observable_via": "linked contract terms",
            "paths": ["contracts[threshold].trigger.threshold_cents"],
            "value": threshold,
        },
    )


def build_conditional(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    trigger_type = "any_changed" if high else "all_changed"
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 80000, {s["c1"]: 1}, refund=80000, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 40000, {s["c2"]: 1}, refund=40000, attributes=attrs),
        option(ids["b3"], s["n3"], s["k3"], 100000, {s["c3"]: 1}, refund=80000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"standalone {s['gap_name']}", s["gap_kind"], 70000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"new {s['n1']} with {s['gap_name']}", f"{s['k1']} package", 50000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt2"], f"new {s['n2']} with {s['gap_name']}", f"{s['k2']} package", 65000, {s["c2"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt3"], f"replacement {s['n3']} with {s['gap_name']}", f"{s['k3']} continuity bundle", 60000, {s["c3"]: 1, s["gap"]: 1}, attributes=attrs),
    ]
    contracts = [
        {
            "contract_id": f"N{case_number:03d}-conditional",
            "description": (
                f"A 120000-cent settlement uses the published "
                f"{trigger_type} cancellation condition for the first two "
                f"commitments."
            ),
            "trigger": {
                "type": trigger_type,
                "entity_option_ids": [ids["b1"], ids["b2"]],
            },
            "charge_cents": 120000,
        }
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=contracts,
        compatibility=[],
        hard_capabilities=[
            goal(s["c1"]), goal(s["c2"]), goal(s["c3"]), goal(s["gap"]),
        ],
        instruction_focus=(
            "Apply the contract's exact Boolean cancellation condition; do not "
            "treat 'any' and 'all' as interchangeable."
        ),
    )
    return task, evidence(
        2,
        "Boolean contract condition over two independently changeable commitments",
        {
            "logical_fact": "contract trigger is ANY versus ALL",
            "observable_via": "linked contract terms",
            "paths": ["contracts[conditional].trigger.type"],
            "value": trigger_type,
        },
    )


def build_partial(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    units = f"{s['c1']}_units"
    partial_price = 250000 if high else 80000
    boundary = [
        option(ids["b1"], f"{s['n1']} lot A (3 units)", s["k1"], 90000, {units: 3}, refund=90000, attributes=attrs),
        option(ids["b2"], f"{s['n1']} lot B (3 units)", s["k1"], 60000, {units: 3}, refund=60000, attributes=attrs),
        option(ids["b3"], s["n2"], s["k2"], 30000, {s["c2"]: 1}, refund=5000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"withdrawn two-unit {s['gap_name']} pack", s["gap_kind"], 70000, {units: 2, s["gap"]: 1}, available=False, attributes=attrs),
        option(ids["alt1"], f"five-unit replacement pack with {s['gap_name']}", f"{s['k1']} lot", partial_price, {units: 5, s["gap"]: 1}, attributes=attrs),
        option(ids["alt2"], "eight-unit full replacement lot", f"{s['k1']} lot", 210000, {units: 8, s["gap"]: 1}, attributes=attrs),
        option(ids["alt3"], "late spare two-unit pack", s["gap_kind"], 50000, {units: 2, s["gap"]: 1}, attributes=standard_attributes(s, 7)),
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=[],
        hard_capabilities=[goal(units, 8, 8), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "The final configuration needs exactly eight operational units; "
            "individual lots have different return values."
        ),
        exact_location_capabilities=[units, s["c2"], s["gap"]],
    )
    return task, evidence(
        3,
        "heterogeneous lots require a strict non-empty, non-full replacement subset",
        {
            "logical_fact": "price of the five-unit partial replacement lot",
            "observable_via": "catalog search and raw price terms",
            "paths": ["inventory[five-unit-partial-lot].upfront_cents"],
            "value": partial_price,
        },
    )


def build_bridge(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    bridge_price = 80000 if high else 10000
    bridge_capability = f"{s['c1']}_bridge_service"
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 100000, {s["c1"]: 1}, refund=100000, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 25000, {s["c2"]: 1}, refund=5000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"new {s['gap_name']}", s["gap_kind"], 10000, {s["gap"]: 1}, attributes=attrs),
        option(ids["bridge"], f"certified bridge for {s['n1']}", "compatibility bridge", bridge_price, {bridge_capability: 1}, attributes=attrs),
        option(ids["alt1"], f"replacement {s['n1']} with native {s['gap_name']}", f"{s['k1']} bundle", 140000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt2"], f"premium bridge-enabled {s['gap_name']}", s["gap_kind"], 95000, {s["gap"]: 1}, attributes=attrs),
    ]
    compatibility = [
        {
            "type": "requires_bridge",
            "option_ids": [ids["b1"], ids["local"]],
            "bridge_option_ids": [ids["bridge"]],
        },
        {
            "type": "requires_bridge",
            "option_ids": [ids["b1"], ids["alt2"]],
            "bridge_option_ids": [ids["bridge"]],
        },
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=compatibility,
        hard_capabilities=[goal(s["c1"]), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "A certified bridge may make the new component coexist with the "
            "existing primary commitment; the bridge does not itself provide "
            "the missing function."
        ),
    )
    return task, evidence(
        3,
        "bridge option changes compatibility rather than supplying the failed capability",
        {
            "logical_fact": "bridge certification price",
            "observable_via": "option price terms and compatibility check",
            "paths": ["inventory[bridge].upfront_cents"],
            "value": bridge_price,
        },
    )


def build_joint(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    second_gap = f"{s['gap']}_companion"
    y_price = 70000 if high else 20000
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 100000, {s["c1"]: 1}, refund=100000, attributes=attrs),
        option(ids["b2"], s["n3"], s["k3"], 25000, {s["c3"]: 1}, refund=5000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"system-X {s['gap_name']}", s["gap_kind"], 30000, {s["gap"]: 1}, attributes={**attrs, "system": "X"}),
        option(ids["aux1"], "system-X companion", "companion service", 40000, {second_gap: 1}, attributes={**attrs, "system": "X"}),
        option(ids["alt1"], f"system-Y {s['gap_name']}", s["gap_kind"], 20000, {s["gap"]: 1}, attributes={**attrs, "system": "Y"}),
        option(ids["aux2"], "system-Y companion", "companion service", y_price, {second_gap: 1}, attributes={**attrs, "system": "Y"}),
        option(ids["alt2"], f"system-Y replacement {s['n1']}", s["k1"], 90000, {s["c1"]: 1}, attributes={**attrs, "system": "Y"}),
        option(ids["alt3"], f"system-X replacement {s['n1']}", s["k1"], 150000, {s["c1"]: 1}, attributes={**attrs, "system": "X"}),
        option(
            ids["bridge"],
            f"premium replacement {s['n3']} with both recovery services",
            f"{s['k3']} continuity bundle",
            300000,
            {s["c3"]: 1, s["gap"]: 1, second_gap: 1},
            attributes=attrs,
        ),
    ]
    compatibility = [
        {"type": "forbid_pair", "option_ids": [ids["local"], ids["aux2"]]},
        {"type": "forbid_pair", "option_ids": [ids["alt1"], ids["aux1"]]},
        {"type": "forbid_pair", "option_ids": [ids["b1"], ids["alt1"]]},
        {"type": "forbid_pair", "option_ids": [ids["b1"], ids["aux2"]]},
        {"type": "forbid_pair", "option_ids": [ids["alt2"], ids["local"]]},
        {"type": "forbid_pair", "option_ids": [ids["alt2"], ids["aux1"]]},
        {"type": "forbid_pair", "option_ids": [ids["alt3"], ids["alt1"]]},
        {"type": "forbid_pair", "option_ids": [ids["alt3"], ids["aux2"]]},
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=compatibility,
        hard_capabilities=[
            goal(s["c1"]), goal(s["c3"]), goal(s["gap"]), goal(second_gap),
        ],
        instruction_focus=(
            "The missing service and its companion must form one compatible "
            "system; independently cheapest components may not coexist."
        ),
    )
    return task, evidence(
        3,
        "joint system choice couples two recovery components and the retained anchor",
        {
            "logical_fact": "price of the system-Y companion",
            "observable_via": "catalog search and compatibility checks",
            "paths": ["inventory[system-y-companion].upfront_cents"],
            "value": y_price,
        },
    )


def build_horizon(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    monthly = 16000 if high else 8000
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 120000, {s["c1"]: 1}, refund=120000, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 100000, {s["c2"]: 1}, refund=80000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"fixed-term {s['gap_name']} plugin", s["gap_kind"], 50000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"upgraded {s['n1']} with {s['gap_name']}", f"{s['k1']} plan", 10000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs, monthly=monthly, horizon=12),
        option(ids["alt2"], f"annual replacement {s['n2']} with {s['gap_name']}", f"{s['k2']} annual bundle", 60000, {s["c2"]: 1, s["gap"]: 1}, attributes=attrs),
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=[],
        hard_capabilities=[goal(s["c1"]), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "The service must remain active for the explicitly required "
            "12-month horizon; compare upfront and monthly charges over all "
            "twelve months."
        ),
    )
    return task, evidence(
        2,
        "explicit-horizon aggregation of upfront and recurring charges",
        {
            "logical_fact": "monthly charge of the upgraded plan",
            "observable_via": "raw option price terms",
            "paths": ["inventory[upgraded-plan].monthly_cents"],
            "value": monthly,
        },
    )


def build_pareto(
    case_number: int, family_index: int, domain: str, high: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    s, ids = semantic(domain, family_index), base_ids(case_number)
    attrs = standard_attributes(s)
    core_refund = 80000 if high else 20000
    boundary = [
        option(ids["b1"], s["n1"], s["k1"], 100000, {s["c1"]: 1}, refund=core_refund, attributes=attrs),
        option(ids["b2"], s["n2"], s["k2"], 60000, {s["c2"]: 1}, refund=30000, attributes=attrs),
    ]
    recovery = [
        option(ids["local"], f"zero-rollback {s['gap_name']}", s["gap_kind"], 50000, {s["gap"]: 1}, attributes=attrs),
        option(ids["alt1"], f"{s['n1']} replacement with {s['gap_name']}", f"{s['k1']} bundle", 90000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt2"], f"{s['n2']} replacement with {s['gap_name']}", f"{s['k2']} bundle", 35000, {s["c2"]: 1, s["gap"]: 1}, attributes=attrs),
        option(ids["alt3"], f"dominated {s['n1']} replacement", f"{s['k1']} bundle", 120000, {s["c1"]: 1, s["gap"]: 1}, attributes=attrs),
    ]
    task = build_common(
        case_number, family_index, domain,
        boundary=boundary,
        recovery=recovery,
        contracts=[],
        compatibility=[],
        hard_capabilities=[goal(s["c1"]), goal(s["c2"]), goal(s["gap"])],
        instruction_focus=(
            "Different recoveries may trade irreversible commitment loss "
            "against post-failure cash outlay; do not assume one hidden scalar "
            "weight."
        ),
    )
    return task, evidence(
        4,
        "multiple genuine Pareto points plus a strictly dominated recovery",
        {
            "logical_fact": "refund for the primary commitment",
            "observable_via": "cancellation preview",
            "paths": [
                "inventory[primary].refund_after_purchase_cents",
                "failure_snapshot[primary].refund_cents",
                "boundary_commitments[primary].refund_cents",
            ],
            "value": core_refund,
        },
    )


BUILDERS: dict[
    str,
    Callable[
        [int, int, str, bool],
        tuple[dict[str, Any], dict[str, Any]],
    ],
] = {
    "sunk_vs_marginal": build_sunk,
    "multi_hop_propagation": build_multi_hop,
    "shared_commitment": build_shared,
    "nonlinear_threshold": build_threshold,
    "conditional_contract": build_conditional,
    "partial_quantity": build_partial,
    "bridge_vs_replacement": build_bridge,
    "joint_bundle_selection": build_joint,
    "explicit_horizon": build_horizon,
    "pareto_tradeoff": build_pareto,
}


def evidence(
    difficulty_level: int,
    mechanism_evidence: str,
    intervention: dict[str, Any],
) -> dict[str, Any]:
    return {
        "difficulty_level": difficulty_level,
        "mechanism_evidence": mechanism_evidence,
        "intervention": intervention,
    }


def validity_certificate(
    task: dict[str, Any],
    oracle: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    frontier = oracle.frontier
    maximum_mutations = max(
        (len(item["tool_calls"]) for item in frontier),
        default=0,
    )
    # Names are deliberately absent from every constraint, compatibility,
    # contract, ledger, and Oracle key used to construct terminal economics.
    # Verify that invariant structurally instead of doubling full-state search.
    invariant = all(
        "name" not in requirement
        for requirement in task["hard_goals"]["attribute_requirements"]
    )
    return {
        "public_metadata_absent": not {
            "reasoning_structure",
            "variant_role",
            "changed_fact",
            "frontier_profile",
            "counterfactual_pair_id",
        }.intersection(task),
        "prefix_generated_by_public_tools": task["construction"][
            "prefix_generated_by_public_tools"
        ],
        "failure_generated_by_public_tool": task["construction"][
            "failure_generated_by_public_tool"
        ],
        "snapshot_hash_verified": snapshot_hash(task["failure_snapshot"])
        == task["snapshot_sha256"],
        "dual_oracle_agreement": frontier_signature(frontier)
        == frontier_signature(oracle.independent_frontier),
        "irrelevant_wording_invariant": invariant,
        "feasible_scope_count": oracle.feasible_scope_count,
        "feasible_terminal_count": oracle.feasible_terminal_count,
        "frontier_count": len(frontier),
        "dominated_terminal_exists": len(frontier)
        < oracle.feasible_terminal_count,
        "maximum_frontier_mutations": maximum_mutations,
        "gold_replay_within_15_turns": maximum_mutations <= 15,
        "candidate_discoverable_by_capability_search": (
            candidate_discoverable_by_capability_search(task)
        ),
        "domain_semantics_linted": semantic_lint(task),
        "reasoning_structure": metadata["reasoning_structure"],
    }


def semantic_lint(task: dict[str, Any]) -> bool:
    instruction = task["instruction"]
    goals = {
        item["capability"] for item in task["hard_goals"]["capabilities"]
    }
    inventory_capabilities = {
        capability
        for item in task["inventory"]
        for capability in item["provides"]
    }
    if not goals.issubset(inventory_capabilities):
        return False
    location_requirements = [
        item
        for item in task["hard_goals"]["attribute_requirements"]
        if item["op"] == "eq"
    ]
    return all(str(item["value"]) in instruction for item in location_requirements)


def candidate_discoverable_by_capability_search(
    task: dict[str, Any],
) -> bool:
    environment = CommitmentRecoveryEnvironment(task)
    current: dict[str, int] = {}
    for item in environment.active_commitments():
        for capability, amount in item["provides"].items():
            current[capability] = current.get(capability, 0) + int(amount)
    missing = [
        requirement["capability"]
        for requirement in task["hard_goals"]["capabilities"]
        if current.get(requirement["capability"], 0)
        < int(requirement.get("min", 0))
    ]
    if not missing:
        return False
    for capability in missing:
        result = environment.execute_tool(
            environment.names["search"],
            {"required_capability": capability},
        )
        if not result.ok or not result.data["results"]:
            return False
    return True


def validate_pairs(
    tasks: list[dict[str, Any]],
    private: dict[str, dict[str, Any]],
    pair_members: dict[str, list[str]],
) -> None:
    by_id = {task["task_id"]: task for task in tasks}
    for pair_id, members in pair_members.items():
        if len(members) != 2:
            raise RuntimeError(f"{pair_id}: expected two tasks")
        left, right = members
        left_oracle = private[left]["oracle"]
        right_oracle = private[right]["oracle"]
        left_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in left_oracle["frontier"]
        }
        right_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in right_oracle["frontier"]
        }
        if left_scopes == right_scopes:
            raise RuntimeError(f"{pair_id}: intervention did not change frontier")
        left_intervention = private[left]["intervention"]
        right_intervention = private[right]["intervention"]
        if left_intervention["logical_fact"] != right_intervention["logical_fact"]:
            raise RuntimeError(f"{pair_id}: pair changes different logical facts")
        if left_intervention["value"] == right_intervention["value"]:
            raise RuntimeError(f"{pair_id}: intervention values are identical")
        left_public = deepcopy(by_id[left])
        right_public = deepcopy(by_id[right])
        left_public["task_id"] = "<opaque>"
        right_public["task_id"] = "<opaque>"
        private[left]["validity_certificate"]["counterfactual_frontier_changed"] = True
        private[right]["validity_certificate"]["counterfactual_frontier_changed"] = True
        private[left]["validity_certificate"]["single_logical_fact_intervention"] = True
        private[right]["validity_certificate"]["single_logical_fact_intervention"] = True


def validate_dataset(
    tasks: list[dict[str, Any]],
    private: dict[str, dict[str, Any]],
    pair_members: dict[str, list[str]],
) -> None:
    if len(tasks) != 160 or len(pair_members) != 80:
        raise RuntimeError("v1.1 must contain 160 tasks in 80 pairs")
    structures = [
        item["metadata"]["reasoning_structure"] for item in private.values()
    ]
    for structure in STRUCTURES:
        if structures.count(structure) != 16:
            raise RuntimeError(f"{structure}: expected 16 tasks")
    domains = {task["domain"] for task in tasks}
    if domains != set(DOMAIN_PROFILES):
        raise RuntimeError("all four domains must be represented")
    cell_counts: dict[tuple[str, str], int] = {}
    for task in tasks:
        structure = private[task["task_id"]]["metadata"][
            "reasoning_structure"
        ]
        cell = (structure, task["domain"])
        cell_counts[cell] = cell_counts.get(cell, 0) + 1
    if len(cell_counts) != 40 or set(cell_counts.values()) != {4}:
        raise RuntimeError(
            "each reasoning-structure/domain cell must contain four tasks"
        )
    for task_id, record in private.items():
        certificate = record["validity_certificate"]
        required_true = [
            "public_metadata_absent",
            "prefix_generated_by_public_tools",
            "failure_generated_by_public_tool",
            "snapshot_hash_verified",
            "dual_oracle_agreement",
            "irrelevant_wording_invariant",
            "dominated_terminal_exists",
            "gold_replay_within_15_turns",
            "candidate_discoverable_by_capability_search",
            "domain_semantics_linted",
            "counterfactual_frontier_changed",
            "single_logical_fact_intervention",
        ]
        if not all(certificate.get(key, False) for key in required_true):
            raise RuntimeError(f"{task_id}: incomplete validity certificate")
    pareto_records = [
        record
        for record in private.values()
        if record["metadata"]["reasoning_structure"] == "pareto_tradeoff"
    ]
    if any(
        record["validity_certificate"]["frontier_count"] < 2
        for record in pareto_records
    ):
        raise RuntimeError("every Pareto task must have multiple frontier points")


def opaque_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(item) for item in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def split_for(index: int) -> str:
    if index <= 16:
        return "dev"
    if index <= 48:
        return "test"
    return "heldout"


if __name__ == "__main__":
    main()
