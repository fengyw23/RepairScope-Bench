"""Build the strict 12-pair RepairScope-Bench v2.0 pilot."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repairscope_bench.difficulty import (  # noqa: E402
    build_complexity_profile,
    coverage_matrix,
)
from repairscope_bench.audit import (  # noqa: E402
    permutation_invariance_certificate,
    public_role_leakage_hits,
)
from repairscope_bench.v2_environment import (  # noqa: E402
    DOMAIN_INTERFACES,
    DomainRecoveryEnvironmentV2,
    snapshot_hash,
)
from repairscope_bench.v2_oracle import (  # noqa: E402
    clear_v2_oracle_cache,
    frontier_signature,
    solve_task_v2,
)


OUTPUT = ROOT / "data" / "v2" / "pilot"
GOLD_OUTPUT = ROOT / "data" / "gold" / "v2.json"
CARDS_OUTPUT = ROOT / "data" / "v2" / "mechanism_cards.json"
COVERAGE_OUTPUT = ROOT / "data" / "v2" / "coverage_matrix.json"


MECHANISM_CARDS = [
    {
        "card_id": "MC-SUNK",
        "name": "Sunk versus marginal recovery cost",
        "causal_pattern": "A historical payment is fixed; only recoverable value and post-boundary cash flows distinguish repairs.",
        "required_evidence": ["paid amount", "refund policy", "replacement price"],
        "common_failure": "Compare historical total prices instead of marginal recovery consequences.",
    },
    {
        "card_id": "MC-MULTIHOP",
        "name": "Multi-hop economic propagation",
        "causal_pattern": "Changing one commitment changes a dependency, which changes another contract or required purchase.",
        "required_evidence": ["dependency relation", "linked terms", "downstream replacement"],
        "common_failure": "Stop propagation after the first affected record.",
    },
    {
        "card_id": "MC-SHARED",
        "name": "Shared commitment protection",
        "causal_pattern": "One existing commitment supports more than one hard goal.",
        "required_evidence": ["all provided functions", "replacement coverage"],
        "common_failure": "Cancel a commitment after considering only the failed branch.",
    },
    {
        "card_id": "MC-THRESHOLD",
        "name": "Non-linear threshold",
        "causal_pattern": "Crossing a retained-value or quantity threshold triggers a discontinuous charge.",
        "required_evidence": ["threshold", "retained total", "charge"],
        "common_failure": "Add item-level prices without testing the threshold.",
    },
    {
        "card_id": "MC-CONDITION",
        "name": "Conditional contract",
        "causal_pattern": "A Boolean or count condition determines whether a linked charge applies.",
        "required_evidence": ["trigger condition", "linked entities", "charge"],
        "common_failure": "Treat every linked term as always active.",
    },
    {
        "card_id": "MC-QUANTITY",
        "name": "Partial quantity repair",
        "causal_pattern": "The missing requirement has quantity and can be satisfied by different subsets.",
        "required_evidence": ["required quantity", "option quantities", "bundle prices"],
        "common_failure": "Replace the entire set when only a subset is missing.",
    },
    {
        "card_id": "MC-BRIDGE",
        "name": "Bridge versus replacement",
        "causal_pattern": "A bridge component can preserve an upstream commitment but has its own cost.",
        "required_evidence": ["bridge requirement", "bridge price", "replacement path"],
        "common_failure": "Compare the failed component and replacement without the bridge.",
    },
    {
        "card_id": "MC-JOINT",
        "name": "Joint bundle selection",
        "causal_pattern": "Options must be compared as complete compatible combinations.",
        "required_evidence": ["companion requirements", "compatibility", "combined charge"],
        "common_failure": "Choose the cheapest item independently.",
    },
    {
        "card_id": "MC-HORIZON",
        "name": "Explicit-horizon recurring cost",
        "causal_pattern": "Upfront and recurring charges must be aggregated over a stated horizon.",
        "required_evidence": ["upfront charge", "monthly charge", "horizon"],
        "common_failure": "Compare only upfront or first-month price.",
    },
    {
        "card_id": "MC-CUT",
        "name": "Selective dependency cut",
        "causal_pattern": "A dependency change requires replacing a precise subset rather than the full prefix or only the failed step.",
        "required_evidence": ["dependency alternatives", "retained commitments", "replacement closure"],
        "common_failure": "Apply full rollback or one-step local repair.",
    },
]


PROFILES = {
    "travel": {
        "location_key": "city",
        "time_key": "service_day",
        "locations": ["Shanghai", "Shenzhen", "Hangzhou"],
        "settings": [
            "specialist conference trip",
            "regional research workshop",
            "clinical collaboration visit",
        ],
        "owner": "traveller",
        "boundary": [
            ("hotel", "Harbor View Hotel"),
            ("transfer", "MetroLink Transfer"),
            ("event_pass", "Congress Admission"),
            ("workspace", "Riverside Meeting Room"),
        ],
        "gap": ("dining", "Yulan Dining Service"),
        "names": [
            "Yulan Dining Service",
            "Jinhai Hospitality Package",
            "Mingyuan Dining Service",
            "Huating Conference Package",
            "Qinghe Dining Service",
            "Lanting Coordination Service",
        ],
    },
    "after_sales": {
        "location_key": "delivery_site",
        "time_key": "delivery_day",
        "locations": ["Radiology Lab A", "Clinic North", "Pathology Lab"],
        "settings": [
            "radiology workstation deployment",
            "cold-chain console installation",
            "pathology imaging station",
        ],
        "owner": "procurement team",
        "boundary": [
            ("core_device", "Aster Workstation"),
            ("warranty", "Northstar Service Cover"),
            ("software", "Meridian Clinical Licence"),
            ("display", "Helios Reference Display"),
        ],
        "gap": ("accessory", "Orchid Interface Unit"),
        "names": [
            "Orchid Interface Unit",
            "Aster Integration Set",
            "Cedar Interface Unit",
            "Meridian Deployment Set",
            "Pine Interface Unit",
            "Juniper Certification Service",
        ],
    },
    "saas": {
        "location_key": "tenant_region",
        "time_key": "activation_day",
        "locations": ["CN-East", "APAC-1", "Health-CN"],
        "settings": [
            "regulated analytics workspace",
            "customer-support platform",
            "clinical reporting tenant",
        ],
        "owner": "enterprise administrator",
        "boundary": [
            ("subscription", "Atlas Core Subscription"),
            ("security", "Sentinel Security Service"),
            ("connector", "Meridian Data Connector"),
            ("audit", "Beacon Audit Archive"),
        ],
        "gap": ("integration", "Orchid Integration Service"),
        "names": [
            "Orchid Integration Service",
            "Atlas Managed Workspace",
            "Cedar Integration Service",
            "Meridian Migration Service",
            "Pine Integration Service",
            "Juniper Compatibility Service",
        ],
    },
    "event_logistics": {
        "location_key": "service_area",
        "time_key": "service_day",
        "locations": ["District 7", "Convention Zone B", "County West"],
        "settings": [
            "vaccination outreach event",
            "regional product launch",
            "mobile screening programme",
        ],
        "owner": "event coordinator",
        "boundary": [
            ("venue", "Harbor Convention Hall"),
            ("transport", "MetroLink Transport"),
            ("storage", "Northstar Storage Service"),
            ("coverage", "Beacon Event Cover"),
        ],
        "gap": ("vendor", "Orchid Field Service"),
        "names": [
            "Orchid Field Service",
            "Harbor Integrated Package",
            "Cedar Field Service",
            "Meridian Event Package",
            "Pine Field Service",
            "Juniper Coordination Service",
        ],
    },
}


SCENARIOS = [
    ("travel", 0, "refund", ["sunk_vs_marginal", "shared_commitment"], "MC-SUNK", 2),
    ("travel", 1, "threshold", ["nonlinear_threshold", "conditional_contract"], "MC-THRESHOLD", 3),
    ("travel", 2, "bridge", ["bridge_vs_replacement", "joint_bundle_selection"], "MC-BRIDGE", 2),
    ("after_sales", 0, "relation", ["multi_hop_propagation", "selective_dependency_cut"], "MC-MULTIHOP", 3),
    ("after_sales", 1, "partial", ["partial_quantity", "joint_bundle_selection"], "MC-QUANTITY", 2),
    ("after_sales", 2, "shared", ["shared_commitment", "multi_hop_propagation"], "MC-SHARED", 3),
    ("saas", 0, "monthly", ["explicit_horizon", "joint_bundle_selection"], "MC-HORIZON", 2),
    ("saas", 1, "frontier", ["conditional_contract", "sunk_vs_marginal"], "MC-CONDITION", 2),
    ("saas", 2, "relation", ["multi_hop_propagation", "selective_dependency_cut"], "MC-CUT", 3),
    ("event_logistics", 0, "frontier", ["sunk_vs_marginal", "joint_bundle_selection"], "MC-SUNK", 2),
    ("event_logistics", 1, "partial", ["partial_quantity", "joint_bundle_selection"], "MC-QUANTITY", 2),
    ("event_logistics", 2, "frontier", ["conditional_contract", "selective_dependency_cut"], "MC-CONDITION", 3),
]


def main() -> None:
    tasks: list[dict[str, Any]] = []
    gold: dict[str, dict[str, Any]] = {}
    pairs: dict[str, list[str]] = {}
    for index, scenario in enumerate(SCENARIOS, start=1):
        domain, profile_index, mode, mechanisms, card_id, depth = scenario
        scenario_id = opaque("scenario", index, domain, mode)
        pair_id = opaque("pair", index, domain, mode)
        pairs[pair_id] = []
        for variant_role, high in [("left", False), ("right", True)]:
            task, metadata = build_task(
                index,
                domain,
                profile_index,
                mode,
                high,
                mechanisms,
                card_id,
                depth,
            )
            task_id = opaque("task", scenario_id, variant_role)
            task["task_id"] = task_id
            metadata.update(
                {
                    "pair_id": pair_id,
                    "scenario_id": scenario_id,
                    "variant_role": variant_role,
                    "domain": domain,
                }
            )
            pairs[pair_id].append(task_id)
            tasks.append(task)
            gold[task_id] = {"metadata": metadata}

    clear_v2_oracle_cache()
    for task in tasks:
        oracle = solve_task_v2(task)
        record = gold[task["task_id"]]
        if not oracle.feasible:
            raise RuntimeError(f"{task['task_id']}: no feasible recovery")
        if oracle.feasible_scope_count < 4:
            raise RuntimeError(f"{task['task_id']}: fewer than four scopes")
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.replay_frontier
        ):
            raise RuntimeError(f"{task['task_id']}: independent Oracles disagree")
        record["oracle"] = oracle.as_dict()
        profile = build_complexity_profile(task, oracle, record["metadata"])
        record["metadata"]["complexity_profile"] = profile
        record["metadata"]["construction_stratum"] = profile[
            "construction_stratum"
        ]
        record["validity_certificate"] = validity_certificate(task, oracle)
        leakage = public_role_leakage_hits(task)
        if leakage:
            raise RuntimeError(f"{task['task_id']}: role leakage {leakage}")
        permutation = permutation_invariance_certificate(task)
        if not permutation["identifier_permutation_invariant"]:
            raise RuntimeError(
                f"{task['task_id']}: identifier permutation changed Oracle"
            )
        record["validity_certificate"].update(
            {
                "public_role_leakage_hits": 0,
                "identifier_permutation_invariant": True,
            }
        )

    validate_pairs(tasks, gold, pairs)
    validate_pilot(tasks, gold)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
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
    CARDS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CARDS_OUTPUT.write_text(
        json.dumps(MECHANISM_CARDS, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    COVERAGE_OUTPUT.write_text(
        json.dumps(coverage_matrix(gold), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tasks)} tasks in {len(pairs)} strict pairs.")


def build_task(
    index: int,
    domain: str,
    profile_index: int,
    mode: str,
    high: bool,
    mechanisms: list[str],
    card_id: str,
    dependency_depth: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = PROFILES[domain]
    location = profile["locations"][profile_index]
    setting = profile["settings"][profile_index]
    location_key = profile["location_key"]
    time_key = profile["time_key"]
    capabilities = {
        "primary": f"F{index:02d}-primary",
        "support": f"F{index:02d}-support",
        "access": f"F{index:02d}-access",
        "shared": f"F{index:02d}-shared",
        "gap": f"F{index:02d}-gap",
        "secondary": f"F{index:02d}-secondary",
    }
    option_ids = {label: opaque("option", index, label) for label in [
        "primary", "support", "access", "shared", "missing", "candidate_a",
        "candidate_b", "candidate_c", "continuity", "companion",
        "support_new", "site_candidate", "time_candidate",
    ]}
    policy_ids = {label: opaque("policy", index, label) for label in [
        "primary", "support", "access", "shared", "new",
    ]}
    refund_primary = 100000
    if mode == "refund":
        refund_primary = 100000 if high else 5000
    if mode == "frontier":
        refund_primary = 80000
    policies = [
        policy(policy_ids["primary"], refund_primary),
        policy(
            policy_ids["support"],
            40000 if mode == "relation" else 10000,
        ),
        policy(policy_ids["access"], 0),
        policy(policy_ids["shared"], 0),
        policy(policy_ids["new"], 0),
    ]
    boundary = []
    paid = [100000, 40000, 30000, 20000]
    cap_labels = ["primary", "support", "access", "shared"]
    for position, ((kind, name), cap_label) in enumerate(
        zip(profile["boundary"], cap_labels, strict=True)
    ):
        provides = {capabilities[cap_label]: 1}
        if mode == "shared" and position == 0:
            provides[capabilities["secondary"]] = 1
        boundary.append(
            option(
                option_ids[cap_label],
                name,
                kind,
                paid[position],
                provides,
                policy_ids[cap_label],
                location_key,
                location,
                time_key,
                2,
            )
        )

    gap_kind, _gap_name = profile["gap"]
    names = profile["names"]
    gap_min = 2 if mode == "partial" else 1
    local_provides = {capabilities["gap"]: gap_min}
    local_price = 70000
    local_monthly = 0
    local_horizon = 0
    if mode == "partial":
        local_price = 120000 if high else 50000
    if mode == "bridge":
        local_price = 20000
    if mode == "monthly":
        local_price = 10000
        local_monthly = 9000 if high else 1000
        local_horizon = 12
    candidate_a = option(
        option_ids["candidate_a"],
        names[0],
        gap_kind,
        local_price,
        local_provides,
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
        monthly_cents=local_monthly,
        horizon_months=local_horizon,
    )

    bundle_provides = {
        capabilities["primary"]: 1,
        capabilities["gap"]: gap_min,
    }
    if mode == "shared" and not high:
        bundle_provides[capabilities["secondary"]] = 1
    bundle_price = 80000
    if mode in {"contract", "threshold", "shared"}:
        bundle_price = 50000
    if mode == "relation":
        bundle_price = 80000
    if mode == "frontier":
        bundle_price = 120000
    if mode in {"monthly", "bridge", "partial"}:
        bundle_price = 300000
    candidate_b = option(
        option_ids["candidate_b"],
        names[1],
        f"{gap_kind}_package",
        bundle_price,
        bundle_provides,
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
    )

    candidate_c_price = (
        30000
        if mode == "frontier"
        else 60000
        if mode == "monthly"
        else 70000
        if mode == "bridge"
        else 120000
    )
    candidate_c_provides = {capabilities["gap"]: 1}
    if mode == "partial":
        candidate_c_price = 35000
    candidate_c = option(
        option_ids["candidate_c"],
        names[2],
        gap_kind,
        candidate_c_price,
        candidate_c_provides,
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
    )

    companion_price = 35000 if mode == "partial" else (
        100000
        if mode == "bridge" and high
        else 80000
        if mode == "shared"
        else 10000
        if mode == "bridge"
        else 150000
    )
    companion_provides = (
        {capabilities["gap"]: 1}
        if mode == "partial"
        else {f"{capabilities['gap']}-companion": 1}
    )
    companion = option(
        option_ids["companion"],
        names[5],
        "coordination_service",
        companion_price,
        companion_provides,
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
    )
    support_new = option(
        option_ids["support_new"],
        names[4],
        profile["boundary"][1][0],
        100000 if mode == "relation" else 150000,
        {capabilities["support"]: 1},
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
    )
    continuity = option(
        option_ids["continuity"],
        names[3],
        "continuity_package",
        600000,
        {
            capabilities["primary"]: 1,
            capabilities["support"]: 1,
            capabilities["access"]: 1,
            capabilities["shared"]: 1,
            capabilities["gap"]: gap_min,
            **(
                {capabilities["secondary"]: 1}
                if mode == "shared"
                else {}
            ),
        },
        policy_ids["new"],
        location_key,
        location,
        time_key,
        3,
    )
    site_candidate = option(
        option_ids["site_candidate"],
        "Rivermark Service",
        gap_kind,
        4000,
        {capabilities["gap"]: gap_min},
        policy_ids["new"],
        location_key,
        f"Other {location}",
        time_key,
        2,
    )
    time_candidate = option(
        option_ids["time_candidate"],
        "Cypress Service",
        gap_kind,
        3000,
        {capabilities["gap"]: gap_min},
        policy_ids["new"],
        location_key,
        location,
        time_key,
        9,
    )
    missing = option(
        option_ids["missing"],
        profile["gap"][1],
        gap_kind,
        18000,
        {capabilities["gap"]: gap_min},
        policy_ids["new"],
        location_key,
        location,
        time_key,
        2,
        available=False,
    )
    inventory = boundary + [
        candidate_a,
        candidate_b,
        candidate_c,
        continuity,
        companion,
        support_new,
        site_candidate,
        time_candidate,
        missing,
    ]
    for inventory_item in inventory:
        inventory_item["entity_id_on_purchase"] = opaque(
            "entity", domain, inventory_item["option_id"]
        )

    contracts: list[dict[str, Any]] = []
    compatibility: list[dict[str, Any]] = []
    changed_path: str
    changed_value: Any
    logical_fact: str
    reveal_record: str
    reveal_kind = "search"

    if mode == "refund":
        changed_path = "/policies/0/refund_cents"
        changed_value = refund_primary
        logical_fact = "primary commitment refund"
        reveal_record = "PRIMARY_ENTITY"
        reveal_kind = "policy"
    elif mode == "contract":
        charge = 150000 if high else 0
        contracts.append(
            contract(
                opaque("contract", index, "settlement"),
                "A linked settlement applies when the covered primary commitment is changed.",
                {"type": "any_changed", "entity_option_ids": [option_ids["primary"]]},
                charge,
            )
        )
        changed_path = "/contracts/0/charge_cents"
        changed_value = charge
        logical_fact = "linked settlement amount"
        reveal_record = "PRIMARY_ENTITY"
        reveal_kind = "policy"
    elif mode == "frontier":
        charge = 0 if high else 100000
        contracts.append(
            contract(
                opaque("contract", index, "frontier"),
                "A service-specific settlement applies when the linked option is activated.",
                {
                    "type": "active_any",
                    "option_ids": [option_ids["candidate_c"]],
                },
                charge,
            )
        )
        changed_path = "/contracts/0/charge_cents"
        changed_value = charge
        logical_fact = "service-specific activation settlement"
        reveal_record = option_ids["candidate_c"]
        reveal_kind = "policy"
    elif mode == "threshold":
        threshold = 1 if high else 0
        contracts.append(
            contract(
                opaque("contract", index, "threshold"),
                "A retained-value threshold determines whether a package adjustment applies.",
                {
                    "type": "retained_paid_below",
                    "entity_option_ids": [option_ids["primary"]],
                    "threshold_cents": threshold,
                },
                150000,
            )
        )
        changed_path = "/contracts/0/trigger/threshold_cents"
        changed_value = threshold
        logical_fact = "retained-value threshold"
        reveal_record = "PRIMARY_ENTITY"
        reveal_kind = "policy"
    elif mode == "monthly":
        changed_path = "/inventory/4/monthly_cents"
        changed_value = local_monthly
        logical_fact = "recurring monthly charge"
        reveal_record = gap_kind
    elif mode == "bridge":
        compatibility.append(
            {
                "type": "requires_all",
                "if_option_id": option_ids["candidate_a"],
                "all_option_ids": [option_ids["companion"]],
            }
        )
        changed_path = "/inventory/8/upfront_cents"
        changed_value = companion_price
        logical_fact = "certification service charge"
        reveal_record = "coordination_service"
    elif mode == "partial":
        changed_path = "/inventory/4/upfront_cents"
        changed_value = local_price
        logical_fact = "two-unit pack price"
        reveal_record = gap_kind
    elif mode == "relation":
        allowed = (
            [option_ids["support_new"]]
            if high
            else [option_ids["support"]]
        )
        compatibility.append(
            {
                "type": "requires_any",
                "if_option_id": option_ids["candidate_b"],
                "any_option_ids": allowed,
            }
        )
        changed_path = "/compatibility_rules/0/any_option_ids/0"
        changed_value = allowed[0]
        logical_fact = "allowed support dependency"
        reveal_record = option_ids["candidate_b"]
        reveal_kind = "policy"
    elif mode == "shared":
        changed_path = f"/inventory/5/provides/{capabilities['secondary']}"
        changed_value = int(not high)
        logical_fact = "replacement secondary-function coverage"
        reveal_record = f"{gap_kind}_package"
    else:
        raise ValueError(mode)

    if mode in {"refund", "threshold", "frontier", "relation", "shared"}:
        companion["available"] = True
        companion["upfront_cents"] = 10000
        compatibility.append(
            {
                "type": "requires_all",
                "if_option_id": option_ids["candidate_b"],
                "all_option_ids": [option_ids["companion"]],
            }
        )
    if mode == "shared":
        support_new["available"] = True
        support_new["upfront_cents"] = 80000
        support_new["provides"] = {capabilities["secondary"]: 1}
    elif mode == "monthly":
        companion["available"] = True
        companion["upfront_cents"] = 10000
        support_new["available"] = True
        support_new["upfront_cents"] = 10000
        support_new["provides"] = {f"{capabilities['gap']}-auxiliary": 1}
        for selected in ["candidate_a", "candidate_c"]:
            compatibility.append(
                {
                    "type": "requires_all",
                    "if_option_id": option_ids[selected],
                    "all_option_ids": [
                        option_ids["companion"],
                        option_ids["support_new"],
                    ],
                }
            )
    elif mode == "partial":
        support_new["available"] = True
        support_new["upfront_cents"] = 10000
        support_new["provides"] = {f"{capabilities['gap']}-auxiliary": 1}
        compatibility.append(
            {
                "type": "requires_all",
                "if_option_id": option_ids["candidate_c"],
                "all_option_ids": [option_ids["support_new"]],
            }
        )
    elif mode == "bridge":
        support_new["available"] = True
        support_new["upfront_cents"] = 10000
        support_new["provides"] = {f"{capabilities['gap']}-auxiliary": 1}
        compatibility[0]["all_option_ids"].append(option_ids["support_new"])
    elif mode != "relation":
        support_new["available"] = False

    capability_requirements = [
        {"capability": capabilities[label], "min": 1, "max": 1}
        for label in ["primary", "support", "access", "shared"]
    ]
    capability_requirements.append(
        {"capability": capabilities["gap"], "min": gap_min, "max": gap_min}
    )
    if mode == "shared":
        capability_requirements.append(
            {"capability": capabilities["secondary"], "min": 1, "max": 1}
        )

    task = {
        "schema_version": "2.0",
        "task_id": "",
        "domain": domain,
        "environment_type": f"repairscope.{domain}.state.v2",
        "split": "dev",
        "now": "2026-09-01T09:00:00+08:00",
        "max_turns": 15,
        "instruction": (
            f"Complete the {setting} at {location} for the {profile['owner']}. "
            "The activity log contains commitments that are already paid and "
            f"active, but the most recent {profile['gap'][1]} operation failed. "
            "Keep the required primary arrangement, support, access, shared "
            f"service, and {profile['gap'][0]} coverage valid at {location} by "
            "day 4. Investigate the authoritative records and execute the best "
            "supported recovery without asking me to choose."
        ),
        "initial_snapshot": {"commitments": []},
        "initial_snapshot_sha256": snapshot_hash({"commitments": []}),
        "failure_snapshot": {"commitments": []},
        "snapshot_sha256": "",
        "pre_failure_trace": [],
        "prefix_ledger": [],
        "latest_failure": {},
        "boundary_commitments": [],
        "inventory": inventory,
        "policies": policies,
        "contracts": contracts,
        "compatibility_rules": compatibility,
        "hard_goals": {
            "capabilities": capability_requirements,
            "attribute_requirements": [
                {
                    "capability": capabilities["gap"],
                    "attribute": location_key,
                    "op": "eq",
                    "value": location,
                },
                {
                    "capability": capabilities["gap"],
                    "attribute": time_key,
                    "op": "le",
                    "value": 4,
                },
            ],
        },
        "construction": {
            "prefix_generated_by_public_tools": True,
            "failure_generated_by_public_tool": True,
            "normalized_policy_source": True,
            "necessary_action_order_invariant": True,
        },
    }
    entity_map = materialize_boundary(task, boundary, missing)
    resolve_contracts(task, entity_map)
    if reveal_record == "PRIMARY_ENTITY":
        reveal_record = entity_map[option_ids["primary"]]
    interface = DOMAIN_INTERFACES[domain]
    reveal_tool = (
        interface["policy"] if reveal_kind == "policy" else interface["search"]
    )
    metadata = {
        "reasoning_signature": mechanisms,
        "mechanism_card_id": card_id,
        "dependency_depth": dependency_depth,
        "intervention": {
            "json_pointer": changed_path,
            "logical_fact": logical_fact,
            "value": changed_value,
        },
        "key_fact_manifest": {
            "logical_fact": logical_fact,
            "json_pointer": changed_path,
            "reveal_tool": reveal_tool,
            "record_id": reveal_record,
        },
    }
    return task, metadata


def materialize_boundary(
    task: dict[str, Any],
    boundary: list[dict[str, Any]],
    missing: dict[str, Any],
) -> dict[str, str]:
    interface = DOMAIN_INTERFACES[task["domain"]]
    environment = DomainRecoveryEnvironmentV2(task)
    trace = []
    option_to_raw_entity = {}
    for step, item in enumerate(boundary, start=1):
        args = {interface["option"]: item["option_id"]}
        result = environment.execute_tool(interface["book"], args)
        if not result.ok:
            raise RuntimeError(result.message)
        raw_entity = result.data["entity_id"]
        option_to_raw_entity[item["option_id"]] = raw_entity
        trace.append(
            {
                "step": step,
                "tool": interface["book"],
                "arguments": args,
                "result": result.as_dict(),
            }
        )
    failure_args = {interface["option"]: missing["option_id"]}
    failed = environment.execute_tool(interface["book"], failure_args)
    if failed.ok:
        raise RuntimeError("Injected failure unexpectedly succeeded")

    entity_map = {
        raw: opaque("entity", task["domain"], option_id)
        for option_id, raw in option_to_raw_entity.items()
    }
    option_to_entity = {
        option_id: entity_map[raw]
        for option_id, raw in option_to_raw_entity.items()
    }
    for item in trace:
        raw = item["result"]["data"]["entity_id"]
        item["result"]["data"]["entity_id"] = entity_map[raw]
    ledger = deepcopy(environment.ledger)
    for item in ledger:
        if item.get("entity_id") in entity_map:
            item["entity_id"] = entity_map[item["entity_id"]]

    commitments = []
    inventory_by_id = {item["option_id"]: item for item in task["inventory"]}
    for item in environment.active_commitments():
        source = inventory_by_id[item["option_id"]]
        commitments.append(
            {
                "entity_id": entity_map[item["entity_id"]],
                "option_id": item["option_id"],
                "name": item["name"],
                "kind": item["kind"],
                "status": "active",
                "paid_cents": item["paid_cents"],
                "refund_policy_id": source["refund_policy_id"],
                "provides": deepcopy(item["provides"]),
                "attributes": deepcopy(item.get("attributes", {})),
                "created_after_boundary": False,
            }
        )
    commitments.sort(key=lambda item: item["entity_id"])
    task["pre_failure_trace"] = trace
    task["prefix_ledger"] = ledger
    task["latest_failure"] = {
        "tool": interface["book"],
        "arguments": failure_args,
        "result": failed.as_dict(),
    }
    task["failure_snapshot"] = {"commitments": commitments}
    task["snapshot_sha256"] = snapshot_hash(task["failure_snapshot"])
    task["boundary_commitments"] = [
        {
            **deepcopy(item),
            "primary_capability": next(iter(item["provides"])),
        }
        for item in commitments
    ]
    boundary_ids = {item["option_id"] for item in boundary}
    for item in task["inventory"]:
        if item["option_id"] in boundary_ids:
            item["available"] = False
    return option_to_entity


def resolve_contracts(task: dict[str, Any], option_to_entity: dict[str, str]) -> None:
    for item in task["contracts"]:
        trigger = item["trigger"]
        trigger["entity_ids"] = [
            option_to_entity[option_id]
            for option_id in trigger.pop("entity_option_ids", [])
        ]


def validity_certificate(task: dict[str, Any], oracle: Any) -> dict[str, Any]:
    return {
        "snapshot_hash_verified": snapshot_hash(task["failure_snapshot"])
        == task["snapshot_sha256"],
        "dual_oracle_agreement": frontier_signature(oracle.frontier)
        == frontier_signature(oracle.replay_frontier),
        "feasible_scope_count": oracle.feasible_scope_count,
        "feasible_terminal_count": oracle.feasible_terminal_count,
        "dominated_terminal_exists": len(oracle.frontier)
        < oracle.feasible_terminal_count,
        "minimum_frontier_mutations": min(
            len(item["tool_calls"]) for item in oracle.frontier
        ),
        "normalized_policy_source": task["construction"][
            "normalized_policy_source"
        ],
    }


def validate_pairs(
    tasks: list[dict[str, Any]],
    gold: dict[str, dict[str, Any]],
    pairs: dict[str, list[str]],
) -> None:
    by_id = {item["task_id"]: item for item in tasks}
    for pair_id, members in pairs.items():
        if len(members) != 2:
            raise RuntimeError(f"{pair_id}: expected two variants")
        left_id, right_id = members
        left_meta = gold[left_id]["metadata"]
        right_meta = gold[right_id]["metadata"]
        if (
            left_meta["intervention"]["json_pointer"]
            != right_meta["intervention"]["json_pointer"]
        ):
            raise RuntimeError(f"{pair_id}: changed different logical facts")
        differences = public_differences(by_id[left_id], by_id[right_id])
        expected_path = left_meta["intervention"]["json_pointer"]
        if differences != [expected_path]:
            raise RuntimeError(
                f"{pair_id}: expected one public fact difference, got {differences}"
            )
        left_scopes = {
            item["scope_key"] for item in gold[left_id]["oracle"]["frontier"]
        }
        right_scopes = {
            item["scope_key"] for item in gold[right_id]["oracle"]["frontier"]
        }
        if left_scopes & right_scopes:
            raise RuntimeError(f"{pair_id}: accepted scope sets overlap")
        left_evidence = reveal_changed_fact(
            by_id[left_id], left_meta["key_fact_manifest"]
        )
        right_evidence = reveal_changed_fact(
            by_id[right_id], right_meta["key_fact_manifest"]
        )
        if left_evidence == right_evidence:
            raise RuntimeError(
                f"{pair_id}: intervention is not observable through its tool"
            )
        for task_id in members:
            gold[task_id]["validity_certificate"].update(
                {
                    "single_source_fact_intervention": True,
                    "disjoint_counterfactual_scopes": True,
                    "changed_fact_tool_observable": True,
                }
            )


def public_differences(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    result: list[str] = []
    left_copy = deepcopy(left)
    right_copy = deepcopy(right)
    left_copy["task_id"] = right_copy["task_id"] = "<opaque>"
    _diff(left_copy, right_copy, "", result)
    return result


def reveal_changed_fact(
    task: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    environment = DomainRecoveryEnvironmentV2(task)
    interface = DOMAIN_INTERFACES[task["domain"]]
    arguments = (
        {"record_id": manifest["record_id"]}
        if manifest["reveal_tool"] == interface["policy"]
        else {interface["category"]: manifest["record_id"]}
    )
    result = environment.execute_tool(manifest["reveal_tool"], arguments)
    if not result.ok:
        raise RuntimeError(
            f"{task['task_id']}: changed fact query failed: {result.message}"
        )
    return result.as_dict()


def _diff(left: Any, right: Any, path: str, result: list[str]) -> None:
    if type(left) is not type(right):
        result.append(path)
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            next_path = f"{path}/{key}"
            if key not in left or key not in right:
                result.append(next_path)
            else:
                _diff(left[key], right[key], next_path, result)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            result.append(path)
            return
        for index, (left_item, right_item) in enumerate(
            zip(left, right, strict=True)
        ):
            _diff(left_item, right_item, f"{path}/{index}", result)
        return
    if left != right:
        result.append(path)


def validate_pilot(
    tasks: list[dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> None:
    if len(tasks) != 24:
        raise RuntimeError("v2 pilot must contain 24 tasks")
    domains = {item["domain"] for item in tasks}
    if domains != set(PROFILES):
        raise RuntimeError("v2 pilot must cover all four domains")
    cards = {
        card
        for record in gold.values()
        for card in record["metadata"]["reasoning_signature"]
    }
    required = {
        "sunk_vs_marginal",
        "multi_hop_propagation",
        "shared_commitment",
        "nonlinear_threshold",
        "conditional_contract",
        "partial_quantity",
        "bridge_vs_replacement",
        "joint_bundle_selection",
        "explicit_horizon",
        "selective_dependency_cut",
    }
    if cards != required:
        raise RuntimeError(f"reasoning coverage mismatch: {cards ^ required}")


def option(
    option_id: str,
    name: str,
    kind: str,
    upfront_cents: int,
    provides: dict[str, int],
    refund_policy_id: str,
    location_key: str,
    location: str,
    time_key: str,
    service_time: int,
    *,
    monthly_cents: int = 0,
    horizon_months: int = 0,
    available: bool = True,
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "name": name,
        "kind": kind,
        "available": available,
        "upfront_cents": upfront_cents,
        "monthly_cents": monthly_cents,
        "horizon_months": horizon_months,
        "refund_policy_id": refund_policy_id,
        "provides": provides,
        "attributes": {location_key: location, time_key: service_time},
    }


def policy(policy_id: str, refund_cents: int) -> dict[str, Any]:
    return {
        "policy_id": policy_id,
        "type": "refund",
        "description": "The stated refund applies if the linked commitment is changed now.",
        "refund_cents": refund_cents,
    }


def contract(
    contract_id: str,
    description: str,
    trigger: dict[str, Any],
    charge_cents: int,
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "description": description,
        "trigger": trigger,
        "charge_cents": charge_cents,
    }


def opaque(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(item) for item in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix[0].upper()}-{digest}"


if __name__ == "__main__":
    main()
