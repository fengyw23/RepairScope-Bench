"""Build the 80-task native-domain RepairScope-Bench v3.0 dataset."""

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

from repairscope_bench.v3_environment import (  # noqa: E402
    NativeRecoveryEnvironmentV3,
    snapshot_hash,
)
from repairscope_bench.v3_oracle import (  # noqa: E402
    clear_v3_oracle_cache,
    solve_task_v3,
)


OUTPUT = ROOT / "data" / "v3"
DEV_OUTPUT = OUTPUT / "dev"
TEST_OUTPUT = OUTPUT / "test"
GOLD_OUTPUT = ROOT / "data" / "gold" / "v3.json"
CARDS_OUTPUT = OUTPUT / "mechanism_cards.json"
COVERAGE_OUTPUT = OUTPUT / "coverage_matrix.json"
STATE_COMMIT = "4efcbf2d4fe60df04878859b692d9391f3d5b33a"


MECHANISMS = [
    "sunk_vs_incremental",
    "multi_hop_propagation",
    "shared_commitment",
    "nonlinear_threshold",
    "conditional_contract",
    "partial_quantity",
    "bridge_vs_replacement",
    "joint_bundle_selection",
    "explicit_horizon",
    "selective_dependency_cut",
]


MECHANISM_CARDS = {
    "sunk_vs_incremental": {
        "name": "Sunk cost versus incremental recovery cost",
        "reasoning": "Ignore payments that cannot be changed now and compare only post-failure cash events.",
        "changed_fact": "supplier refund credit",
    },
    "multi_hop_propagation": {
        "name": "Multi-hop economic propagation",
        "reasoning": "Changing the anchor also forces a support replacement and can trigger a downstream migration charge.",
        "changed_fact": "downstream migration charge",
    },
    "shared_commitment": {
        "name": "Shared commitment protection",
        "reasoning": "The anchor satisfies two live goals, so replacing it needs a continuity component as well as the failed component.",
        "changed_fact": "continuity settlement charge",
    },
    "nonlinear_threshold": {
        "name": "Non-linear threshold",
        "reasoning": "Changing a commitment can push retained paid value below a discontinuous benefit threshold.",
        "changed_fact": "retained-value threshold",
    },
    "conditional_contract": {
        "name": "Conditional contract logic",
        "reasoning": "The same linked contract applies to any changed item in one variant and only when all linked items change in the other.",
        "changed_fact": "Boolean trigger condition",
    },
    "partial_quantity": {
        "name": "Evidence-backed partial quantity repair",
        "reasoning": "An existing quantity remains useful; the agent must compare topping up the shortfall with replacing the whole quantity.",
        "changed_fact": "full-replacement supplier credit",
    },
    "bridge_vs_replacement": {
        "name": "Bridge repair versus upstream replacement",
        "reasoning": "A low-price component requires a separate compatibility bridge whose certification cost can reverse the decision.",
        "changed_fact": "bridge certification charge",
    },
    "joint_bundle_selection": {
        "name": "Joint combination selection",
        "reasoning": "Two required components must be compared as a compatible pair rather than by individual sticker price.",
        "changed_fact": "joint supplier coordination charge",
    },
    "explicit_horizon": {
        "name": "Explicit-horizon recurring cost",
        "reasoning": "A recurring charge must be aggregated over the user-stated 12-month horizon.",
        "changed_fact": "monthly service charge",
    },
    "selective_dependency_cut": {
        "name": "Selective dependency cut",
        "reasoning": "The failed component requires changing one affected support item while preserving independent commitments.",
        "changed_fact": "support migration charge",
    },
}


TRAVEL_STORIES = {
    "sunk_vs_incremental": [
        ("Seattle medical congress", "dining", "conference dinner", "Seattle"),
        ("Boston research symposium", "shuttle", "venue shuttle", "Boston"),
    ],
    "multi_hop_propagation": [
        ("Chicago standards workshop", "workspace", "meeting workspace", "Chicago"),
        ("Austin engineering summit", "dining", "team dinner", "Austin"),
    ],
    "shared_commitment": [
        ("Denver clinical meeting", "dining", "host dinner", "Denver"),
        ("Portland policy forum", "shuttle", "forum shuttle", "Portland"),
    ],
    "nonlinear_threshold": [
        ("Atlanta association meeting", "dining", "delegate dinner", "Atlanta"),
        ("Phoenix training week", "workspace", "training room", "Phoenix"),
    ],
    "conditional_contract": [
        ("San Diego partner event", "shuttle", "partner shuttle", "San Diego"),
        ("Nashville annual meeting", "dining", "speaker dinner", "Nashville"),
    ],
    "partial_quantity": [
        ("Orlando group conference", "dining", "group dinner seats", "Orlando"),
        ("Minneapolis delegation visit", "shuttle", "delegation shuttle seats", "Minneapolis"),
    ],
    "bridge_vs_replacement": [
        ("New York investor forum", "workspace", "secure meeting access", "New York"),
        ("San Francisco developer event", "dining", "accessible dinner service", "San Francisco"),
    ],
    "joint_bundle_selection": [
        ("Las Vegas exhibition", "booth_service", "booth support", "Las Vegas"),
        ("Philadelphia policy conference", "dining", "conference dinner", "Philadelphia"),
    ],
    "explicit_horizon": [
        ("Miami twelve-month field program", "local_service", "local mobility service", "Miami"),
        ("Raleigh year-long research visit", "workspace", "workspace access", "Raleigh"),
    ],
    "selective_dependency_cut": [
        ("Detroit supplier conference", "shuttle", "supplier shuttle", "Detroit"),
        ("Salt Lake City compliance meeting", "workspace", "compliance workspace", "Salt Lake City"),
    ],
}


SUPPORT_STORIES = {
    "sunk_vs_incremental": [
        ("radiology workstation", "dock", "certified dock", "Radiology Lab A"),
        ("media editing station", "storage", "high-speed storage module", "Media Studio 2"),
    ],
    "multi_hop_propagation": [
        ("pathology imaging station", "interface", "camera interface", "Pathology Lab"),
        ("clinical analytics console", "gateway", "secure gateway", "Clinic Analytics"),
    ],
    "shared_commitment": [
        ("cardiology review system", "dock", "diagnostic dock", "Cardiology Room"),
        ("design review workstation", "adapter", "display adapter", "Design Lab"),
    ],
    "nonlinear_threshold": [
        ("molecular testing console", "battery", "backup battery", "Molecular Lab"),
        ("architecture rendering kit", "storage", "archive storage", "Architecture Studio"),
    ],
    "conditional_contract": [
        ("ophthalmology capture system", "interface", "capture interface", "Eye Clinic"),
        ("broadcast production station", "dock", "broadcast dock", "Broadcast Suite"),
    ],
    "partial_quantity": [
        ("clinic cold-chain kit", "sensor", "certified sensors", "Vaccine Clinic"),
        ("warehouse scanning kit", "scanner", "wireless scanners", "Warehouse North"),
    ],
    "bridge_vs_replacement": [
        ("ultrasound review workstation", "dock", "ultrasound dock", "Ultrasound Lab"),
        ("audio mastering workstation", "interface", "audio interface", "Audio Studio"),
    ],
    "joint_bundle_selection": [
        ("surgical video station", "capture", "video capture module", "Surgical Lab"),
        ("geospatial analysis station", "storage", "geospatial storage", "GIS Lab"),
    ],
    "explicit_horizon": [
        ("twelve-month pathology platform", "software_service", "analysis service", "Pathology Center"),
        ("annual newsroom workstation", "support_service", "managed support", "Newsroom"),
    ],
    "selective_dependency_cut": [
        ("oncology planning station", "dock", "planning dock", "Oncology Lab"),
        ("industrial inspection console", "interface", "inspection interface", "Inspection Bay"),
    ],
}


TRAVEL_PRICE_PROFILE = {
    "profile_id": "travel-usd-2026q3",
    "source_date": "2026-07-25",
    "sources": [
        "https://www.gsa.gov/travel/plan-a-trip/per-diem-rates/per-diem-files"
    ],
    "ranges_minor": {
        "flight": [18000, 65000],
        "hotel_total": [30000, 150000],
        "ground_service": [3500, 45000],
        "event_admission": [30000, 120000],
    },
}


SUPPORT_PRICE_PROFILE = {
    "profile_id": "after-sales-usd-2026q3",
    "source_date": "2026-07-25",
    "sources": [
        "https://www.dell.com/en-us/shop/scc/sc/workstations?dtredir=1",
        "https://www.dell.com/en-us/shop/monitor-accessories/ar/5390/docking-stations?appliedRefinements=35071",
    ],
    "ranges_minor": {
        "core_device": [90000, 450000],
        "display": [20000, 250000],
        "accessory": [5000, 90000],
        "software_or_service": [8000, 250000],
    },
}


def opaque(*parts: Any) -> str:
    payload = "|".join(str(item) for item in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    tasks: list[dict[str, Any]] = []
    gold: dict[str, dict[str, Any]] = {}
    for domain in ("travel", "after_sales"):
        for mechanism in MECHANISMS:
            for base_index in range(2):
                pair_id = f"P-{opaque('v3-pair', domain, mechanism, base_index)}"
                for variant_index in range(2):
                    task, metadata = build_task(
                        domain,
                        mechanism,
                        base_index,
                        variant_index,
                        pair_id,
                    )
                    tasks.append(task)
                    gold[task["task_id"]] = {"metadata": metadata}

    clear_v3_oracle_cache()
    for index, task in enumerate(tasks, start=1):
        oracle = solve_task_v3(task)
        if not oracle.feasible:
            raise RuntimeError(f"{task['task_id']}: no feasible recovery")
        if oracle.feasible_scope_count < 3:
            raise RuntimeError(
                f"{task['task_id']}: fewer than three feasible scopes"
            )
        if not oracle.unique:
            costs = [
                (item["incremental_cost_minor"], item["scope_key"])
                for item in oracle.feasible_terminals[:6]
            ]
            raise RuntimeError(
                f"{task['task_id']}: no materially unique gold: {costs}"
            )
        gold[task["task_id"]]["oracle"] = oracle.as_dict()
        gold[task["task_id"]]["metadata"]["complexity_profile"] = (
            complexity_profile(
                task,
                oracle,
                gold[task["task_id"]]["metadata"]["reasoning_structure"],
                len(
                    gold[task["task_id"]]["metadata"][
                        "evidence_manifest"
                    ]
                ),
            )
        )
        if index % 10 == 0:
            print(f"Solved {index}/{len(tasks)} tasks")

    validate_pairs(tasks, gold)
    validate_coverage(tasks, gold)
    write_dataset(tasks, gold)


def build_task(
    domain: str,
    mechanism: str,
    base_index: int,
    variant_index: int,
    pair_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    scenario_id = f"S-{opaque('v3-scenario', domain, mechanism, base_index)}"
    task_id = f"T-{opaque('v3-task', scenario_id, variant_index)}"
    story = (
        TRAVEL_STORIES[mechanism][base_index]
        if domain == "travel"
        else SUPPORT_STORIES[mechanism][base_index]
    )
    setting, gap_category, gap_label, location = story
    actor_id = "traveler_001" if domain == "travel" else "customer_001"
    task: dict[str, Any] = {
        "schema_version": "3.0",
        "task_id": task_id,
        "domain": domain,
        "environment_type": (
            "state_bench.travel+native_recovery_v3"
            if domain == "travel"
            else "state_bench.customer_support+native_recovery_v3"
        ),
        "split": "dev" if base_index == 0 else "test",
        "now": "2026-08-01T10:00:00",
        "actor_id": actor_id,
        "max_turns": 15,
        "source": {
            "benchmark": "STATE-Bench",
            "repository": "https://github.com/microsoft/STATE-Bench",
            "commit": STATE_COMMIT,
            "reuse": "Native domain schemas, persistent state, and write semantics.",
        },
        "price_profile": deepcopy(
            TRAVEL_PRICE_PROFILE
            if domain == "travel"
            else SUPPORT_PRICE_PROFILE
        ),
        "option_metadata": {},
        "boundary_commitments": [],
        "compatibility_rules": [],
        "economic_terms": [],
        "hard_goals": {"capabilities": [], "attributes": []},
        "construction": {
            "prefix_generated_by_public_tools": True,
            "failure_generated_by_public_tool": True,
            "necessary_action_order_invariant": True,
            "currency": "USD",
            "internal_money_unit": "minor",
        },
    }
    identifiers = {
        key: f"{domain[:2].upper()}-{opaque(scenario_id, key)}"
        for key in [
            "anchor",
            "support",
            "access",
            "safeguard",
            "failed",
            "local",
            "alternative",
            "bundle",
            "comprehensive",
            "support_new",
            "continuity",
            "bridge",
            "companion",
            "one_a",
            "one_b",
            "decoy",
        ]
    }
    recipe = build_recipe(
        domain,
        mechanism,
        base_index,
        variant_index,
        identifiers,
        gap_category,
        gap_label,
        location,
    )
    task["option_metadata"] = recipe["option_metadata"]
    task["compatibility_rules"] = recipe["compatibility_rules"]
    task["hard_goals"] = recipe["hard_goals"]
    task["instruction"] = instruction_for(
        domain,
        setting,
        gap_category,
        gap_label,
        location,
        recipe,
    )
    clean_snapshot = (
        travel_snapshot(task, identifiers, location)
        if domain == "travel"
        else support_snapshot(task, identifiers)
    )
    task["initial_snapshot"] = deepcopy(clean_snapshot)
    task["initial_snapshot_sha256"] = snapshot_hash(clean_snapshot)
    task["failure_snapshot"] = deepcopy(clean_snapshot)
    task["snapshot_sha256"] = snapshot_hash(clean_snapshot)

    environment = NativeRecoveryEnvironmentV3(task)
    prefix_calls = (
        travel_prefix_calls(identifiers, actor_id)
        if domain == "travel"
        else support_prefix_calls(identifiers, actor_id)
    )
    prefix_trace = []
    for step, call in enumerate(prefix_calls, start=1):
        result = environment.execute_tool(call["name"], call["arguments"])
        if not result.ok:
            raise RuntimeError(
                f"{task_id}: prefix call failed: {call} {result.message}"
            )
        prefix_trace.append(
            {
                "step": step,
                "tool": call["name"],
                "arguments": call["arguments"],
                "result": result.as_dict(),
            }
        )
    failure_call = (
        {
            "name": "book_travel_option",
            "arguments": {
                "option_id": identifiers["failed"],
                "user_id": actor_id,
            },
        }
        if domain == "travel"
        else {
            "name": "purchase_product_option",
            "arguments": {
                "product_id": identifiers["failed"],
                "customer_id": actor_id,
            },
        }
    )
    failure_result = environment.execute_tool(
        failure_call["name"], failure_call["arguments"]
    )
    if failure_result.ok:
        raise RuntimeError(f"{task_id}: failure call unexpectedly succeeded")
    task["pre_failure_trace"] = prefix_trace
    task["prefix_ledger"] = environment.economic_events()
    task["latest_failure"] = {
        "tool": failure_call["name"],
        "arguments": failure_call["arguments"],
        "result": failure_result.as_dict(),
    }
    task["failure_snapshot"] = environment.normalized_state()
    task["snapshot_sha256"] = snapshot_hash(task["failure_snapshot"])

    task["boundary_commitments"] = boundary_from_environment(
        environment, identifiers
    )
    probe = NativeRecoveryEnvironmentV3(task)
    for item in task["boundary_commitments"]:
        item["refund_minor"] = preview_refund_minor(
            task, probe, item["entity_id"]
        )

    term, changed_field = build_economic_term(
        task,
        mechanism,
        variant_index,
        identifiers,
        recipe,
    )
    task["economic_terms"] = [term]
    evidence_manifest = build_evidence_manifest(
        task, mechanism, changed_field, term
    )
    metadata = {
        "pair_id": pair_id,
        "scenario_id": scenario_id,
        "variant_role": "left" if variant_index == 0 else "right",
        "reasoning_structure": mechanism,
        "mechanism_name": MECHANISM_CARDS[mechanism]["name"],
        "evidence_manifest": evidence_manifest,
        "changed_fact": {
            "logical_fact": MECHANISM_CARDS[mechanism]["changed_fact"],
            "json_pointer": f"/economic_terms/0/{changed_field}",
            "reveal_tool": (
                "get_travel_terms"
                if domain == "travel"
                else "get_product_terms"
            ),
            "record_id": term["linked_entity_ids"][0]
            if term.get("linked_entity_ids")
            else term["linked_option_ids"][0],
        },
    }
    return task, metadata


def build_recipe(
    domain: str,
    mechanism: str,
    base_index: int,
    variant_index: int,
    ids: dict[str, str],
    gap_category: str,
    gap_label: str,
    location: str,
) -> dict[str, Any]:
    if domain == "travel":
        caps = {
            "anchor": "hotel_stay",
            "support": "ground_transfer",
            "access": "event_admission",
            "safeguard": "arrival_flight",
            "shared": "meeting_location_continuity",
            "companion": "on_site_coordination",
            "gap": f"{gap_category}_capacity",
        }
        prices = {
            "anchor": 60000 + base_index * 6000,
            "support": 12000 + base_index * 2000,
            "access": 45000 + base_index * 5000,
            "safeguard": 42000 + base_index * 3000,
            "local": 30000 + base_index * 3000,
            "alternative": 39000 + base_index * 3000,
            "bundle": 95000 + base_index * 6000,
            "comprehensive": 128000 + base_index * 8000,
            "support_new": 20000 + base_index * 2000,
            "continuity": 10000 + base_index * 1000,
            "bridge": 10000 + base_index * 1000,
            "companion": 12000 + base_index * 1000,
            "one": 20000 + base_index * 1000,
        }
        attributes = {"location": location, "ready_day": 2}
        wrong_attributes = {"location": "Different City", "ready_day": 7}
    else:
        caps = {
            "anchor": "core_device",
            "support": "service_coverage",
            "access": "licensed_software",
            "safeguard": "reference_display",
            "shared": "validated_workflow_continuity",
            "companion": "certification_service",
            "gap": f"{gap_category}_capacity",
        }
        prices = {
            "anchor": 180000 + base_index * 20000,
            "support": 30000 + base_index * 4000,
            "access": 60000 + base_index * 5000,
            "safeguard": 75000 + base_index * 8000,
            "local": 40000 + base_index * 4000,
            "alternative": 52000 + base_index * 4000,
            "bundle": 225000 + base_index * 22000,
            "comprehensive": 292000 + base_index * 25000,
            "support_new": 45000 + base_index * 4000,
            "continuity": 20000 + base_index * 2000,
            "bridge": 18000 + base_index * 2000,
            "companion": 18000 + base_index * 2000,
            "one": 25000 + base_index * 2000,
        }
        attributes = {"delivery_site": location, "ready_day": 3, "approved": True}
        wrong_attributes = {
            "delivery_site": "Different Facility",
            "ready_day": 9,
            "approved": False,
        }

    quantity_required = 6 if mechanism == "partial_quantity" else 1
    anchor_provides = {caps["anchor"]: 1}
    if mechanism == "shared_commitment":
        anchor_provides[caps["shared"]] = 1
    if mechanism == "partial_quantity":
        anchor_provides[caps["gap"]] = 4

    metadata: dict[str, dict[str, Any]] = {}

    def add(
        key: str,
        name: str,
        slot: str,
        price_minor: int,
        provides: dict[str, int],
        *,
        candidate: bool = False,
        available: bool = True,
        native_kind: str | None = None,
        attrs: dict[str, Any] | None = None,
        upfront_minor: int | None = None,
    ) -> None:
        selected_native_kind = native_kind or (
            "local_service" if domain == "travel" else "product"
        )
        metadata[ids[key]] = {
            "name": name,
            "slot": slot,
            "native_kind": selected_native_kind,
            "available": available,
            "candidate": candidate,
            "upfront_minor": (
                price_minor if upfront_minor is None else upfront_minor
            ),
            "monthly_minor": 0,
            "horizon_months": 0,
            "total_charge_minor": price_minor,
            "post_purchase_cancel_fee_minor": (
                min(
                    1000 if domain == "travel" else 2500,
                    price_minor // 10,
                )
            )
            if candidate
            else 0,
            "provides": deepcopy(provides),
            "attributes": deepcopy(attrs or attributes),
        }
        if not available:
            metadata[ids[key]]["failure_message"] = (
                f"No inventory remains for the requested {gap_label}."
            )

    add(
        "anchor",
        "Harbor Conference Hotel" if domain == "travel" else "Aster Professional Workstation",
        "hotel" if domain == "travel" else "core_device",
        prices["anchor"],
        anchor_provides,
        native_kind="hotel" if domain == "travel" else "product",
    )
    add(
        "support",
        "MetroLink Ground Transfer" if domain == "travel" else "Northstar Service Coverage",
        "transfer" if domain == "travel" else "warranty",
        prices["support"],
        {caps["support"]: 1},
    )
    add(
        "access",
        "Professional Event Admission" if domain == "travel" else "Meridian Workflow Licence",
        "admission" if domain == "travel" else "software",
        prices["access"],
        {caps["access"]: 1},
    )
    add(
        "safeguard",
        "Confirmed Arrival Flight" if domain == "travel" else "Helios Reference Display",
        "flight" if domain == "travel" else "display",
        prices["safeguard"],
        {caps["safeguard"]: 1},
        native_kind="flight" if domain == "travel" else "product",
    )
    add(
        "failed",
        f"Original {gap_label}",
        gap_category,
        18000 if domain == "travel" else 28000,
        {caps["gap"]: 2 if mechanism == "partial_quantity" else 1},
        available=False,
    )

    local_provides = {
        caps["gap"]: 2 if mechanism == "partial_quantity" else 1
    }
    local_upfront = prices["local"]
    if mechanism == "bridge_vs_replacement":
        local_upfront = 8000 if domain == "travel" else 15000
    elif mechanism == "joint_bundle_selection":
        local_upfront = 10000 if domain == "travel" else 20000
    elif mechanism == "selective_dependency_cut":
        local_upfront = 10000 if domain == "travel" else 25000
    if mechanism == "explicit_horizon":
        local_upfront = 5000 if domain == "travel" else 10000
    add(
        "local",
        f"Independent {gap_label}",
        gap_category,
        local_upfront,
        local_provides,
        candidate=True,
        upfront_minor=local_upfront,
    )
    add(
        "alternative",
        f"Premium independent {gap_label}",
        gap_category,
        prices["alternative"],
        local_provides,
        candidate=True,
    )

    bundle_price = prices["bundle"]
    if mechanism == "sunk_vs_incremental" and domain == "after_sales":
        bundle_price += 15000
    if mechanism == "shared_commitment":
        bundle_price = prices["anchor"] + 10000
    if mechanism in {"multi_hop_propagation", "nonlinear_threshold", "conditional_contract"}:
        bundle_price = (
            prices["anchor"] + 20000
            if domain == "travel"
            else prices["anchor"] + (
                20000
                if mechanism == "multi_hop_propagation"
                else 30000
            )
        )
    if mechanism == "partial_quantity":
        bundle_price = (
            prices["anchor"] + 40000
            if domain == "travel"
            else prices["anchor"] + 50000
        )
    if mechanism in {"bridge_vs_replacement", "joint_bundle_selection", "explicit_horizon", "selective_dependency_cut"}:
        bundle_price = (
            prices["anchor"] + 25000
            if domain == "travel"
            else prices["anchor"] + 45000
        )
    add(
        "bundle",
        f"Integrated {gap_label} lodging package"
        if domain == "travel"
        else f"Integrated {gap_label} device bundle",
        gap_category,
        bundle_price,
        {
            caps["anchor"]: 1,
            caps["gap"]: quantity_required,
            **(
                {caps["companion"]: 1}
                if mechanism == "joint_bundle_selection"
                else {}
            ),
        },
        candidate=True,
        native_kind="hotel" if domain == "travel" else "product",
    )
    add(
        "comprehensive",
        f"Comprehensive {gap_label} travel package"
        if domain == "travel"
        else f"Comprehensive {gap_label} workstation package",
        gap_category,
        prices["comprehensive"],
        {
            caps["anchor"]: 1,
            caps["support"]: 1,
            caps["gap"]: quantity_required,
            **(
                {caps["shared"]: 1}
                if mechanism == "shared_commitment"
                else {}
            ),
            **(
                {caps["companion"]: 1}
                if mechanism == "joint_bundle_selection"
                else {}
            ),
        },
        candidate=True,
        native_kind="hotel" if domain == "travel" else "product",
    )

    compatibility: list[dict[str, Any]] = []
    if mechanism == "multi_hop_propagation":
        add(
            "support_new",
            "Replacement transfer agreement" if domain == "travel" else "Replacement service coverage",
            gap_category,
            prices["support_new"],
            {caps["support"]: 1},
            candidate=True,
        )
        compatibility.extend(
            [
                rule_forbid(ids["bundle"], ids["support"], mechanism),
                rule_require(ids["bundle"], [ids["support_new"]], mechanism),
            ]
        )
    elif mechanism == "shared_commitment":
        add(
            "continuity",
            "Meeting-location continuity service" if domain == "travel" else "Workflow continuity validation",
            gap_category,
            prices["continuity"],
            {caps["shared"]: 1},
            candidate=True,
        )
    elif mechanism == "partial_quantity":
        # The local option is a two-unit top-up. Two independent one-unit
        # options create a second partial path without hidden quantity fields.
        add(
            "one_a",
            f"One-unit {gap_label} option A",
            gap_category,
            prices["one"],
            {caps["gap"]: 1},
            candidate=True,
        )
        add(
            "one_b",
            f"One-unit {gap_label} option B",
            gap_category,
            prices["one"] + 1000,
            {caps["gap"]: 1},
            candidate=True,
        )
    elif mechanism == "bridge_vs_replacement":
        add(
            "bridge",
            "Certified access bridge" if domain == "travel" else "Certified compatibility adapter",
            gap_category,
            prices["bridge"],
            {},
            candidate=True,
        )
        compatibility.append(
            rule_require(ids["local"], [ids["bridge"]], mechanism)
        )
    elif mechanism == "joint_bundle_selection":
        add(
            "companion",
            "On-site coordination service" if domain == "travel" else "Required certification service",
            gap_category,
            prices["companion"],
            {caps["companion"]: 1},
            candidate=True,
        )
        compatibility.append(
            rule_require(ids["local"], [ids["companion"]], mechanism)
        )
    elif mechanism == "selective_dependency_cut":
        add(
            "support_new",
            "Compatible replacement transfer" if domain == "travel" else "Compatible replacement service cover",
            gap_category,
            prices["support_new"],
            {caps["support"]: 1},
            candidate=True,
        )
        compatibility.extend(
            [
                rule_forbid(ids["local"], ids["support"], mechanism),
                rule_require(ids["local"], [ids["support_new"]], mechanism),
            ]
        )

    add(
        "decoy",
        f"Unavailable-location {gap_label}",
        gap_category,
        4000 if domain == "travel" else 7000,
        {caps["gap"]: quantity_required},
        candidate=True,
        attrs=wrong_attributes,
    )

    capability_labels = {
        caps["anchor"]: "hotel stay" if domain == "travel" else "core device",
        caps["support"]: "ground transfer" if domain == "travel" else "service coverage",
        caps["access"]: "event admission" if domain == "travel" else "licensed software",
        caps["safeguard"]: "arrival flight" if domain == "travel" else "reference display",
        caps["gap"]: gap_label,
        caps["shared"]: "meeting-location continuity"
        if domain == "travel"
        else "validated workflow continuity",
        caps["companion"]: "on-site coordination"
        if domain == "travel"
        else "certification service",
    }
    required_caps = [
        caps["anchor"],
        caps["support"],
        caps["access"],
        caps["safeguard"],
        caps["gap"],
    ]
    if mechanism == "shared_commitment":
        required_caps.append(caps["shared"])
    if mechanism == "joint_bundle_selection":
        required_caps.append(caps["companion"])
    hard_capabilities = []
    for capability in required_caps:
        required = quantity_required if capability == caps["gap"] else 1
        constraint_id = f"HC-{opaque(domain, mechanism, base_index, capability)}"
        hard_capabilities.append(
            {
                "constraint_id": constraint_id,
                "capability": capability,
                "label": capability_labels[capability],
                "min": required,
                "max": required,
                "evidence_refs": [f"E-{constraint_id}"],
            }
        )
    location_key = "location" if domain == "travel" else "delivery_site"
    location_constraint_id = f"HA-{opaque(domain, mechanism, base_index, 'location')}"
    ready_constraint_id = f"HA-{opaque(domain, mechanism, base_index, 'ready')}"
    hard_goals = {
        "capabilities": hard_capabilities,
        "attributes": [
            {
                "constraint_id": location_constraint_id,
                "capability": caps["gap"],
                "attribute": location_key,
                "op": "eq",
                "value": location,
                "evidence_refs": [f"E-{location_constraint_id}"],
            },
            {
                "constraint_id": ready_constraint_id,
                "capability": caps["gap"],
                "attribute": "ready_day",
                "op": "le",
                "value": 4,
                "evidence_refs": [f"E-{ready_constraint_id}"],
            },
        ],
    }
    return {
        "caps": caps,
        "prices": prices,
        "quantity_required": quantity_required,
        "option_metadata": metadata,
        "compatibility_rules": compatibility,
        "hard_goals": hard_goals,
        "location": location,
        "location_key": location_key,
        "gap_label": gap_label,
        "gap_category": gap_category,
    }


def build_economic_term(
    task: dict[str, Any],
    mechanism: str,
    variant_index: int,
    ids: dict[str, str],
    recipe: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    by_option = {
        item["option_id"]: item for item in task["boundary_commitments"]
    }
    anchor = by_option[ids["anchor"]]["entity_id"]
    support = by_option[ids["support"]]["entity_id"]
    linked_entities = [anchor]
    linked_options: list[str] = []
    trigger: dict[str, Any] = {
        "type": "any_changed",
        "entity_ids": [anchor],
    }
    term: dict[str, Any] = {
        "term_id": f"TERM-{opaque(mechanism, anchor, support)}",
        "description": MECHANISM_CARDS[mechanism]["reasoning"],
        "linked_entity_ids": linked_entities,
        "linked_option_ids": linked_options,
        "trigger": trigger,
        "charge_minor": 0,
        "credit_minor": 0,
    }
    scale = 1 if task["domain"] == "travel" else 2
    changed_field = "charge_minor"

    if mechanism == "sunk_vs_incremental":
        term["credit_minor"] = 0 if variant_index == 0 else 15000 * scale
        changed_field = "credit_minor"
    elif mechanism == "multi_hop_propagation":
        term["linked_entity_ids"] = [anchor, support]
        term["trigger"] = {
            "type": "all_changed",
            "entity_ids": [anchor, support],
        }
        term["charge_minor"] = 0 if variant_index == 0 else 18000 * scale
    elif mechanism == "shared_commitment":
        term["linked_option_ids"] = [ids["continuity"]]
        term["trigger"] = {
            "type": "active_any",
            "option_ids": [ids["continuity"]],
        }
        term["charge_minor"] = 0 if variant_index == 0 else 15000 * scale
    elif mechanism == "nonlinear_threshold":
        term["linked_entity_ids"] = [
            item["entity_id"] for item in task["boundary_commitments"]
        ]
        retained_without_anchor = sum(
            int(item["paid_minor"])
            for item in task["boundary_commitments"]
            if item["entity_id"] != anchor
        )
        term["trigger"] = {
            "type": "retained_paid_below",
            "entity_ids": term["linked_entity_ids"],
            "threshold_minor": retained_without_anchor
            - 1000
            if variant_index == 0
            else retained_without_anchor + 1000,
        }
        term["charge_minor"] = 25000 * scale
        changed_field = "trigger/threshold_minor"
    elif mechanism == "conditional_contract":
        term["linked_entity_ids"] = [anchor, support]
        term["trigger"] = {
            "type": "any_changed" if variant_index == 0 else "all_changed",
            "entity_ids": [anchor, support],
        }
        term["charge_minor"] = 25000 * scale
        changed_field = "trigger/type"
    elif mechanism == "partial_quantity":
        term["linked_option_ids"] = [ids["bundle"]]
        term["trigger"] = {
            "type": "active_any",
            "option_ids": [ids["bundle"]],
        }
        term["credit_minor"] = 0 if variant_index == 0 else 15000 * scale
        changed_field = "credit_minor"
    elif mechanism == "bridge_vs_replacement":
        term["linked_option_ids"] = [ids["local"], ids["bridge"]]
        term["trigger"] = {
            "type": "active_all",
            "option_ids": [ids["local"], ids["bridge"]],
        }
        term["charge_minor"] = 0 if variant_index == 0 else 20000 * scale
    elif mechanism == "joint_bundle_selection":
        term["linked_option_ids"] = [ids["local"], ids["companion"]]
        term["trigger"] = {
            "type": "active_all",
            "option_ids": [ids["local"], ids["companion"]],
        }
        term["charge_minor"] = 0 if variant_index == 0 else 10000 * scale
    elif mechanism == "explicit_horizon":
        term["linked_option_ids"] = [ids["local"]]
        term["trigger"] = {
            "type": "active_any",
            "option_ids": [ids["local"]],
        }
        term["monthly_minor"] = (
            1000 if task["domain"] == "travel" else 2000
        ) if variant_index == 0 else (
            2000 if task["domain"] == "travel" else 3500
        )
        term["horizon_months"] = 12
        changed_field = "monthly_minor"
    elif mechanism == "selective_dependency_cut":
        term["linked_entity_ids"] = [support]
        term["trigger"] = {
            "type": "any_changed",
            "entity_ids": [support],
        }
        term["charge_minor"] = 0 if variant_index == 0 else 20000 * scale
    else:
        raise ValueError(mechanism)
    return term, changed_field


def instruction_for(
    domain: str,
    setting: str,
    gap_category: str,
    gap_label: str,
    location: str,
    recipe: dict[str, Any],
) -> str:
    phrases = []
    for requirement in recipe["hard_goals"]["capabilities"]:
        quantity = int(requirement["min"])
        if quantity == 1:
            phrases.append(f"exactly one {requirement['label']}")
        else:
            phrases.append(
                f"exactly {quantity} units of {requirement['label']}"
            )
    location_phrase = (
        f"Every option covering {gap_label} must be in {location}"
        if domain == "travel"
        else f"Every option covering {gap_label} must be delivered to {location}"
    )
    return (
        f"Continue the partially completed {setting}. The earlier orders and "
        f"reservations shown below are already active, but the attempted "
        f"{gap_label} ({gap_category}) has just failed. The final state must "
        f"contain {', '.join(phrases)}. {location_phrase} and be ready by day "
        "4. Do not retain combinations that supplier records mark as "
        "incompatible. Complete the remaining goal with the lowest actual net "
        "monetary cost from this failure point."
    )


def travel_snapshot(
    task: dict[str, Any], ids: dict[str, str], location: str
) -> dict[str, Any]:
    metadata = task["option_metadata"]
    flights = [
        _flight(
            ids["safeguard"],
            "ORD",
            "SEA",
            "2026-09-14T08:00:00",
            "2026-09-14T10:30:00",
            metadata[ids["safeguard"]]["total_charge_minor"] // 100,
        )
    ]
    hotels = [
        _hotel(
            option_id,
            item["name"],
            location,
            item["total_charge_minor"] // 200,
            item["total_charge_minor"] // 100,
        )
        for option_id, item in metadata.items()
        if item["native_kind"] == "hotel"
    ]
    services = [
        _service_option(
            option_id,
            item["slot"],
            item["total_charge_minor"] // 100,
            item["available"],
            item.get("failure_message"),
            **item["attributes"],
        )
        for option_id, item in metadata.items()
        if item["native_kind"] == "local_service"
    ]
    return {
        "state_bench": {
            "flights": flights,
            "bookings": [],
            "users": [
                {
                    "user_id": task["actor_id"],
                    "name": "Repair Scope Traveler",
                    "email": "traveler@example.com",
                    "loyalty_tier": "basic",
                    "loyalty_points": 0,
                    "budget": 10000,
                    "preferences": {
                        "meal_preference": "standard",
                        "seat_type": "aisle",
                        "add_wifi": False,
                        "add_extra_legroom": False,
                        "add_insurance": False,
                    },
                }
            ],
            "hotel_inventory": hotels,
            "hotels": [],
            "car_inventory": [],
            "car_rentals": [],
        },
        "extensions": {
            "services": [],
            "service_inventory": services,
        },
    }


def support_snapshot(
    task: dict[str, Any], ids: dict[str, str]
) -> dict[str, Any]:
    products = [
        _product(
            option_id,
            item["name"],
            item["slot"],
            item["total_charge_minor"] // 100,
            item["available"],
        )
        for option_id, item in task["option_metadata"].items()
    ]
    return {
        "state_bench": {
            "products": products,
            "orders": [],
            "order_items": [],
            "customers": [
                {
                    "customer_id": task["actor_id"],
                    "name": "Repair Scope Customer",
                    "email": "customer@example.com",
                    "membership_tier": "standard",
                    "account_created": "2025-01-01",
                    "total_orders": 0,
                    "preferred_refund_method": "original_payment",
                    "store_credit_balance": 0,
                    "has_prime_shipping": False,
                }
            ],
            "warranties": [],
        },
        "extensions": {"services": [], "service_inventory": []},
    }


def travel_prefix_calls(
    ids: dict[str, str], actor_id: str
) -> list[dict[str, Any]]:
    return [
        {
            "name": "book_travel_option",
            "arguments": {"option_id": ids["safeguard"], "user_id": actor_id},
        },
        {
            "name": "book_travel_option",
            "arguments": {"option_id": ids["anchor"], "user_id": actor_id},
        },
        {
            "name": "book_travel_option",
            "arguments": {"option_id": ids["support"], "user_id": actor_id},
        },
        {
            "name": "book_travel_option",
            "arguments": {"option_id": ids["access"], "user_id": actor_id},
        },
    ]


def support_prefix_calls(
    ids: dict[str, str], actor_id: str
) -> list[dict[str, Any]]:
    return [
        {
            "name": "purchase_product_option",
            "arguments": {"product_id": ids[key], "customer_id": actor_id},
        }
        for key in ["anchor", "support", "access", "safeguard"]
    ]


def boundary_from_environment(
    environment: NativeRecoveryEnvironmentV3,
    ids: dict[str, str],
) -> list[dict[str, Any]]:
    prefix_options = {
        ids[key] for key in ["anchor", "support", "access", "safeguard"]
    }
    result = []
    for record in environment.active_records():
        if record["option_id"] not in prefix_options:
            continue
        metadata = environment.option_metadata[record["option_id"]]
        result.append(
            {
                "entity_id": record["entity_id"],
                "option_id": record["option_id"],
                "slot": metadata["slot"],
                "paid_minor": metadata["total_charge_minor"],
                "refund_minor": 0,
                "quantity": max(metadata.get("provides", {}).values(), default=1),
                "provides": deepcopy(metadata["provides"]),
                "attributes": deepcopy(metadata["attributes"]),
            }
        )
    return sorted(result, key=lambda item: item["entity_id"])


def preview_refund_minor(
    task: dict[str, Any],
    environment: NativeRecoveryEnvironmentV3,
    entity_id: str,
) -> int:
    if task["domain"] == "travel":
        result = environment.execute_tool(
            "preview_travel_cancellation",
            {"reservation_id": entity_id},
        )
    else:
        environment.execute_tool(
            "get_product_terms", {"record_id": entity_id}
        )
        result = environment.execute_tool(
            "preview_product_return", {"item_id": entity_id}
        )
    if not result.ok:
        raise RuntimeError(f"Cannot preview {entity_id}: {result.message}")
    data = result.data or {}
    raw = data.get("refund_amount", data.get("base_refund"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Missing normalized refund for {entity_id}: {data}")
    amount = str(raw["amount"])
    sign = -1 if amount.startswith("-") else 1
    amount = amount.lstrip("-")
    dollars, cents = amount.split(".")
    return sign * (int(dollars) * 100 + int(cents))


def build_evidence_manifest(
    task: dict[str, Any],
    mechanism: str,
    changed_field: str,
    term: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest = []
    for requirement in task["hard_goals"]["capabilities"]:
        phrase = (
            f"exactly one {requirement['label']}"
            if int(requirement["min"]) == 1
            else f"exactly {requirement['min']} units of {requirement['label']}"
        )
        manifest.append(
            {
                "evidence_id": requirement["evidence_refs"][0],
                "constraint_id": requirement["constraint_id"],
                "source_type": "instruction_span",
                "text": phrase,
            }
        )
    location, ready = task["hard_goals"]["attributes"]
    manifest.extend(
        [
            {
                "evidence_id": location["evidence_refs"][0],
                "constraint_id": location["constraint_id"],
                "source_type": "instruction_span",
                "text": str(location["value"]),
            },
            {
                "evidence_id": ready["evidence_refs"][0],
                "constraint_id": ready["constraint_id"],
                "source_type": "instruction_span",
                "text": "ready by day 4",
            },
        ]
    )
    for rule in task["compatibility_rules"]:
        evidence_id = f"E-{rule['constraint_id']}"
        rule["evidence_refs"] = [evidence_id]
        manifest.append(
            {
                "evidence_id": evidence_id,
                "constraint_id": rule["constraint_id"],
                "source_type": "tool_rule",
                "tool": (
                    "check_travel_compatibility"
                    if task["domain"] == "travel"
                    else "check_product_compatibility"
                ),
                "description_fragment": "Check whether",
            }
        )
    record_id = (
        term["linked_entity_ids"][0]
        if term.get("linked_entity_ids")
        else term["linked_option_ids"][0]
    )
    manifest.append(
        {
            "evidence_id": f"E-FACT-{task['task_id']}",
            "constraint_id": None,
            "source_type": "query_result",
            "tool": (
                "get_travel_terms"
                if task["domain"] == "travel"
                else "get_product_terms"
            ),
            "arguments": {"record_id": record_id},
            "match": {
                "term_id": term["term_id"],
                "field": changed_field,
                "expected": _get_nested(term, changed_field),
            },
        }
    )
    return manifest


def complexity_profile(
    task: dict[str, Any],
    oracle: Any,
    mechanism: str,
    evidence_count: int,
) -> dict[str, Any]:
    dependency_depth = {
        "sunk_vs_incremental": 1,
        "multi_hop_propagation": 3,
        "shared_commitment": 2,
        "nonlinear_threshold": 2,
        "conditional_contract": 2,
        "partial_quantity": 2,
        "bridge_vs_replacement": 2,
        "joint_bundle_selection": 2,
        "explicit_horizon": 2,
        "selective_dependency_cut": 3,
    }.get(mechanism, 2)
    profile = {
        "existing_commitment_count": len(task["boundary_commitments"]),
        "feasible_scope_count": oracle.feasible_scope_count,
        "evidence_source_count": evidence_count,
        "minimum_required_queries": 1,
        "dependency_depth": dependency_depth,
        "contract_boolean_depth": 2
        if mechanism in {"conditional_contract", "nonlinear_threshold"}
        else 1,
        "interacting_mechanism_count": 2
        if mechanism
        in {
            "multi_hop_propagation",
            "joint_bundle_selection",
            "selective_dependency_cut",
        }
        else 1,
        "quantity_decision_count": 1
        if mechanism == "partial_quantity"
        else 0,
        "minimum_mutation_count": oracle.gold["minimum_mutations"],
        "oracle_expanded_states": oracle.assignment_count,
        "cost_margin_to_second_best_minor": oracle.cost_margin_minor,
    }
    score = (
        profile["dependency_depth"]
        + profile["interacting_mechanism_count"]
        + (2 if profile["feasible_scope_count"] >= 8 else 1)
        + profile["quantity_decision_count"]
    )
    profile["derived_level"] = (
        1 if score <= 4 else 2 if score <= 6 else 3 if score <= 8 else 4
    )
    profile["difficulty_rule_version"] = "v3.0-structural-1"
    return profile


def validate_pairs(
    tasks: list[dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> None:
    pairs: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        pair_id = gold[task["task_id"]]["metadata"]["pair_id"]
        pairs.setdefault(pair_id, []).append(task)
    for pair_id, members in pairs.items():
        if len(members) != 2:
            raise RuntimeError(f"{pair_id}: expected two variants")
        left, right = sorted(
            members,
            key=lambda item: gold[item["task_id"]]["metadata"]["variant_role"],
        )
        if left["failure_snapshot"] != right["failure_snapshot"]:
            raise RuntimeError(f"{pair_id}: failure snapshots differ")
        if left["instruction"] != right["instruction"]:
            raise RuntimeError(f"{pair_id}: instructions differ")
        left_scope = gold[left["task_id"]]["oracle"]["gold"]["scope_signature"]
        right_scope = gold[right["task_id"]]["oracle"]["gold"]["scope_signature"]
        if left_scope == right_scope:
            raise RuntimeError(f"{pair_id}: unique gold scope did not flip")
        left_pointer = gold[left["task_id"]]["metadata"]["changed_fact"][
            "json_pointer"
        ]
        right_pointer = gold[right["task_id"]]["metadata"]["changed_fact"][
            "json_pointer"
        ]
        if left_pointer != right_pointer:
            raise RuntimeError(f"{pair_id}: changed fact pointer differs")
        normalized_left = deepcopy(left)
        normalized_right = deepcopy(right)
        normalized_left["task_id"] = normalized_right["task_id"] = "<opaque>"
        differences: list[str] = []
        _diff(normalized_left, normalized_right, "", differences)
        if differences != [left_pointer]:
            raise RuntimeError(
                f"{pair_id}: expected one public fact difference, got {differences}"
            )


def validate_coverage(
    tasks: list[dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> None:
    if len(tasks) != 80:
        raise RuntimeError(f"Expected 80 tasks, found {len(tasks)}")
    cells: dict[tuple[str, str], int] = {}
    splits: dict[str, int] = {}
    for task in tasks:
        metadata = gold[task["task_id"]]["metadata"]
        cell = (task["domain"], metadata["reasoning_structure"])
        cells[cell] = cells.get(cell, 0) + 1
        splits[task["split"]] = splits.get(task["split"], 0) + 1
    expected_cells = {
        (domain, mechanism)
        for domain in ("travel", "after_sales")
        for mechanism in MECHANISMS
    }
    if set(cells) != expected_cells or set(cells.values()) != {4}:
        raise RuntimeError(f"Unbalanced mechanism-domain coverage: {cells}")
    if splits != {"dev": 40, "test": 40}:
        raise RuntimeError(f"Unbalanced split: {splits}")


def write_dataset(
    tasks: list[dict[str, Any]], gold: dict[str, dict[str, Any]]
) -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    DEV_OUTPUT.mkdir(parents=True)
    TEST_OUTPUT.mkdir(parents=True)
    for task in tasks:
        destination = DEV_OUTPUT if task["split"] == "dev" else TEST_OUTPUT
        (destination / f"{task['task_id']}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    GOLD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    GOLD_OUTPUT.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    CARDS_OUTPUT.write_text(
        json.dumps(MECHANISM_CARDS, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    matrix: dict[str, dict[str, int]] = {}
    for domain in ("travel", "after_sales"):
        matrix[domain] = {}
        for mechanism in MECHANISMS:
            matrix[domain][mechanism] = sum(
                task["domain"] == domain
                and gold[task["task_id"]]["metadata"][
                    "reasoning_structure"
                ]
                == mechanism
                for task in tasks
            )
    COVERAGE_OUTPUT.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote 80 v3 tasks to {OUTPUT}")
    print(f"Wrote v3 gold to {GOLD_OUTPUT}")


def rule_forbid(left: str, right: str, mechanism: str) -> dict[str, Any]:
    return {
        "constraint_id": f"CR-{opaque(mechanism, 'forbid', left, right)}",
        "type": "forbid_pair",
        "option_ids": [left, right],
    }


def rule_require(
    option_id: str, required: list[str], mechanism: str
) -> dict[str, Any]:
    return {
        "constraint_id": f"CR-{opaque(mechanism, 'require', option_id, *required)}",
        "type": "requires_any",
        "if_option_id": option_id,
        "any_option_ids": required,
    }


def _get_nested(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("/"):
        current = current[part]
    return deepcopy(current)


def _diff(left: Any, right: Any, path: str, output: list[str]) -> None:
    if type(left) is not type(right):
        output.append(path)
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            next_path = f"{path}/{key}"
            if key not in left or key not in right:
                output.append(next_path)
            else:
                _diff(left[key], right[key], next_path, output)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            output.append(path)
            return
        for index, (left_item, right_item) in enumerate(
            zip(left, right, strict=True)
        ):
            _diff(left_item, right_item, f"{path}/{index}", output)
        return
    if left != right:
        output.append(path)


def _flight(
    flight_id: str,
    origin: str,
    destination: str,
    departure: str,
    arrival: str,
    price: int,
) -> dict[str, Any]:
    return {
        "flight_id": flight_id,
        "airline_code": "UA",
        "origin": origin,
        "destination": destination,
        "departure_time": departure,
        "arrival_time": arrival,
        "duration_minutes": 150,
        "stops": 0,
        "cabin_prices": {"economy": price},
        "status": "scheduled",
        "delay_minutes": 0,
        "route_type": "domestic",
    }


def _hotel(
    hotel_id: str,
    name: str,
    city: str,
    nightly_rate: int,
    total_price: int,
) -> dict[str, Any]:
    return {
        "hotel_id": hotel_id,
        "hotel_name": name,
        "city": city,
        "check_in": "2026-09-14",
        "check_out": "2026-09-16",
        "room_type": "standard",
        "nightly_rate": nightly_rate,
        "total_price": total_price,
    }


def _service_option(
    option_id: str,
    slot: str,
    price: int,
    available: bool,
    failure_message: str | None,
    **attributes: Any,
) -> dict[str, Any]:
    result = {
        "option_id": option_id,
        "slot": slot,
        "price": price,
        "available": available,
        "attributes": attributes,
    }
    if failure_message:
        result["failure_message"] = failure_message
    return result


def _product(
    product_id: str,
    name: str,
    subcategory: str,
    price: int,
    in_stock: bool,
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "name": name,
        "category": "electronics",
        "subcategory": subcategory,
        "price": price,
        "warranty_months": 12,
        "return_window_days": 30,
        "restocking_fee_pct": 0,
        "weight_lbs": 2.0,
        "is_fragile": False,
        "in_stock": in_stock,
        "current_price": None,
    }


if __name__ == "__main__":
    main()
