"""Generate the v0.5 paired, loss-sensitive fixed-failure challenge set."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "challenge"
GOLD_OUTPUT = ROOT / "data" / "gold" / "challenge.json"
OBJECTIVE = [
    "recovery_loss",
    "financial_cost",
    "mutated_prior_commitments",
    "state_changing_actions",
]
REQUIREMENTS = {
    "min_raw_plans": 100,
    "min_feasible_plans": 8,
    "min_feasible_scopes": 4,
    "min_loss_levels": 3,
}


def commitment(
    commitment_id: str,
    slot: str,
    option_id: str,
    price: int,
    refund: int,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "commitment_id": commitment_id,
        "slot": slot,
        "option_id": option_id,
        "status": "confirmed",
        "price_paid": price,
        "refund_if_cancelled": refund,
        "attributes": attributes,
    }


def option(
    option_id: str,
    slot: str,
    price: int,
    available: bool = True,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "slot": slot,
        "price": price,
        "available": available,
        "refund_if_cancelled_after_booking": 0,
        "attributes": attributes,
    }


def _catalog_with_existing(
    commitments: list[dict[str, Any]], catalog: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = deepcopy(catalog)
    known = {item["option_id"] for item in result}
    for item in commitments:
        if item["option_id"] in known:
            continue
        result.append(
            {
                "option_id": item["option_id"],
                "slot": item["slot"],
                "price": item["price_paid"],
                "available": True,
                "refund_if_cancelled_after_booking": 0,
                "attributes": deepcopy(item["attributes"]),
                "provenance": "existing_record",
            }
        )
    return result


def paired_tasks(
    *,
    base_id: str,
    family_id: str,
    variant: str,
    domain: str,
    mechanism: str,
    split: str,
    instruction: str,
    loss_clause: str,
    failure_observation: str,
    commitments: list[dict[str, Any]],
    failed_option_id: str,
    failed_slot: str,
    catalog: list[dict[str, Any]],
    required_slots: list[str],
    constraints: list[dict[str, Any]],
    search_contexts: dict[str, dict[str, str]],
    linked_loss_rules: list[dict[str, Any]],
    modification_rules: list[dict[str, Any]] | None = None,
    source_case: str,
) -> list[dict[str, Any]]:
    trace = []
    action_name = "book_travel_option" if domain == "travel" else "purchase_product"
    identifier_name = "reservation_id" if domain == "travel" else "order_id"
    for step, item in enumerate(commitments, start=1):
        trace.append(
            {
                "step": step,
                "tool": action_name,
                "arguments": {
                    "option_id" if domain == "travel" else "product_id": item[
                        "option_id"
                    ]
                },
                "result": {
                    "status": "confirmed",
                    identifier_name: item["commitment_id"],
                },
            }
        )
    trace.append(
        {
            "step": len(trace) + 1,
            "tool": action_name,
            "arguments": {
                "option_id" if domain == "travel" else "product_id": failed_option_id
            },
            "result": {"status": "failed", "error": "inventory_changed"},
        }
    )
    common = {
        "schema_version": "0.5",
        "family_id": family_id,
        "domain": domain,
        "source_inspiration": {
            "benchmark": "STATE-Bench",
            "case_id": source_case,
            "url": "https://github.com/microsoft/STATE-Bench",
            "transformation": (
                "New fixed post-commit failure state, enlarged inventory, "
                "paired objective demand, linked settlement terms, and "
                "solver-derived repair gold; no upstream answer is reused."
            ),
        },
        "failure_observation": failure_observation,
        "pre_failure_trace": trace,
        "failure_snapshot": {
            "commitments": deepcopy(commitments),
            "note": "Authoritative persistent state immediately after the failed call.",
        },
        "failure": {
            "affected_slots": [failed_slot],
            "side_effect_on_failed_call": "none",
        },
        "catalog": _catalog_with_existing(commitments, catalog),
        "modification_rules": deepcopy(modification_rules or []),
        "linked_loss_rules": deepcopy(linked_loss_rules),
        "required_slots": required_slots,
        "constraints": constraints,
        "search_contexts": search_contexts,
        "objective": {"mode": "lexicographic", "terms": OBJECTIVE},
        "mechanism": mechanism,
        "split": split,
        "challenge_requirements": REQUIREMENTS,
        "max_mutations": 14,
    }
    result = []
    for track, suffix in [("goal", ""), ("loss_aware", loss_clause)]:
        item = deepcopy(common)
        item["task_id"] = f"{base_id}-{track.replace('_', '-')}"
        item["variant_id"] = f"{variant}-{track}"
        item["pair_id"] = base_id
        item["evaluation_track"] = track
        item["evaluation_class"] = (
            "feasibility" if track == "goal" else "loss_sensitive"
        )
        item["instruction"] = instruction + suffix
        result.append(item)
    return result


def conference_family() -> list[dict[str, Any]]:
    slots = [
        "outbound",
        "return",
        "hotel",
        "airport_transfer",
        "conference_pass",
        "dinner",
    ]
    context = {
        slot: {
            "city": "Shanghai",
            "start_date": "2026-09-14",
            "end_date": "2026-09-16",
        }
        for slot in slots
    }

    def make(variant: str, dinner_at_original: bool, hotel_refund: int) -> list[dict[str, Any]]:
        commitments = [
            commitment(
                "TR-OUT", "outbound", "OUT-SHA-ORIG", 520, 100,
                city="Shanghai", date="2026-09-14", arrives_by="12:00"
            ),
            commitment(
                "TR-RET", "return", "RET-SHA-ORIG", 480, 80,
                city="Shanghai", date="2026-09-16", departs_after="18:00"
            ),
            commitment(
                "TR-HOTEL", "hotel", "HOTEL-BUND-ORIG", 900, hotel_refund,
                city="Shanghai", check_in="2026-09-14", check_out="2026-09-16",
                area="Huangpu"
            ),
            commitment(
                "TR-XFER", "airport_transfer", "XFER-ORIG", 160, 0,
                city="Shanghai", date="2026-09-14", area="Huangpu"
            ),
            commitment(
                "TR-PASS", "conference_pass", "PASS-ORIG", 300, 0,
                city="Shanghai", valid_through="2026-09-16"
            ),
        ]
        catalog = [
            option("OUT-SHA-EARLY", "outbound", 490, city="Shanghai", date="2026-09-14", arrives_by="10:30"),
            option("OUT-SHA-FLEX", "outbound", 560, city="Shanghai", date="2026-09-14", arrives_by="11:00"),
            option("RET-SHA-VALUE", "return", 450, city="Shanghai", date="2026-09-16", departs_after="19:00"),
            option("RET-SHA-FLEX", "return", 530, city="Shanghai", date="2026-09-16", departs_after="20:00"),
            option("HOTEL-RIVER", "hotel", 750, city="Shanghai", check_in="2026-09-14", check_out="2026-09-16", area="Lujiazui"),
            option("HOTEL-BUDGET", "hotel", 620, city="Shanghai", check_in="2026-09-14", check_out="2026-09-16", area="JingAn"),
            option("XFER-METRO", "airport_transfer", 120, city="Shanghai", date="2026-09-14", area="any"),
            option("XFER-FLEX", "airport_transfer", 200, city="Shanghai", date="2026-09-14", area="any"),
            option("PASS-DIGITAL", "conference_pass", 280, city="Shanghai", valid_through="2026-09-16"),
            option("PASS-FLEX", "conference_pass", 350, city="Shanghai", valid_through="2026-09-16"),
            option("DINNER-HUANGPU", "dinner", 320, dinner_at_original, city="Shanghai", date="2026-09-14", area="Huangpu"),
            option("DINNER-RIVER", "dinner", 160, city="Shanghai", date="2026-09-14", area="Lujiazui"),
            option("DINNER-JINGAN", "dinner", 100, city="Shanghai", date="2026-09-14", area="JingAn"),
        ]
        hotel_pairs = [
            ["HOTEL-RIVER", "DINNER-RIVER"],
            ["HOTEL-RIVER", "DINNER-JINGAN"],
            ["HOTEL-BUDGET", "DINNER-JINGAN"],
        ]
        if dinner_at_original:
            hotel_pairs.append(["HOTEL-BUND-ORIG", "DINNER-HUANGPU"])
        constraints = [
            *[
                {
                    "type": "slot_attribute",
                    "slot": slot,
                    "attribute": "city",
                    "op": "eq",
                    "value": "Shanghai",
                }
                for slot in slots
            ],
            {
                "type": "allowed_pairs",
                "left_slot": "hotel",
                "right_slot": "dinner",
                "pairs": hotel_pairs,
            },
            {"type": "max_lifecycle_cost", "value": 3800},
        ]
        return paired_tasks(
            base_id=f"conference-dinner-{variant.lower()}",
            family_id="conference-dinner-failure",
            variant=variant,
            domain="travel",
            mechanism="package_breakage",
            split="dev",
            instruction=(
                "Complete my Shanghai conference trip for September 14-16. I "
                "need the flights, hotel, airport transfer, conference pass, "
                "and a dinner reservation in the same area as the hotel; keep "
                "the final trip within $3,800."
            ),
            loss_clause=(
                " Resolve it without wasting non-refundable payments or "
                "needlessly breaking package terms."
            ),
            failure_observation=(
                "book_travel_option(DINNER-ORIGINAL) failed: the restaurant "
                "no longer has inventory."
            ),
            commitments=commitments,
            failed_option_id="DINNER-ORIGINAL",
            failed_slot="dinner",
            catalog=catalog,
            required_slots=slots,
            constraints=constraints,
            search_contexts=context,
            linked_loss_rules=[
                {
                    "rule_id": "AIR-HOTEL-PACKAGE",
                    "description": (
                        "Changing or cancelling either the original outbound "
                        "flight or hotel forfeits a prepaid package credit."
                    ),
                    "trigger": "any_changed",
                    "commitment_ids": ["TR-OUT", "TR-HOTEL"],
                    "amount": 180,
                }
            ],
            source_case="121/122",
        )

    return make("A", True, 700) + make("B", False, 900)


def workstation_family() -> list[dict[str, Any]]:
    slots = ["laptop", "monitor", "dock", "security_key", "warranty", "software"]
    context = {slot: {"use_case": "radiology-workstation"} for slot in slots}

    def make(variant: str, universal_available: bool) -> list[dict[str, Any]]:
        commitments = [
            commitment("WS-LAP", "laptop", "LAP-CREATOR", 1400, 950, arrival_day=2, approved=True),
            commitment("WS-MON", "monitor", "MON-4K", 520, 390, arrival_day=2, approved=True),
            commitment("WS-KEY", "security_key", "KEY-FIPS", 90, 20, arrival_day=1, approved=True),
            commitment("WS-WAR", "warranty", "WAR-CREATOR", 180, 0, arrival_day=1, approved=True),
            commitment("WS-SOFT", "software", "SOFT-CREATOR", 260, 60, arrival_day=1, approved=True),
        ]
        catalog = [
            option("LAP-PRO", "laptop", 700, arrival_day=3, approved=True),
            option("LAP-MED", "laptop", 1250, arrival_day=2, approved=True),
            option("MON-4K-B", "monitor", 470, arrival_day=3, approved=True),
            option("MON-4K-C", "monitor", 560, arrival_day=1, approved=True),
            option("DOCK-UNIVERSAL", "dock", 260, universal_available, arrival_day=2, approved=True),
            option("DOCK-PRO", "dock", 130, arrival_day=2, approved=True),
            option("DOCK-MED", "dock", 170, arrival_day=1, approved=True),
            option("KEY-FIPS-B", "security_key", 75, arrival_day=2, approved=True),
            option("KEY-FIPS-C", "security_key", 110, arrival_day=1, approved=True),
            option("WAR-PRO", "warranty", 50, arrival_day=1, approved=True),
            option("WAR-MED", "warranty", 160, arrival_day=1, approved=True),
            option("SOFT-PRO", "software", 80, arrival_day=1, approved=True),
            option("SOFT-MED", "software", 230, arrival_day=1, approved=True),
        ]
        constraints = [
            *[
                {
                    "type": "slot_attribute",
                    "slot": slot,
                    "attribute": "arrival_day",
                    "op": "le",
                    "value": 3,
                }
                for slot in slots
            ],
            *[
                {
                    "type": "slot_attribute",
                    "slot": slot,
                    "attribute": "approved",
                    "op": "eq",
                    "value": True,
                }
                for slot in slots
            ],
            {
                "type": "allowed_pairs",
                "left_slot": "laptop",
                "right_slot": "dock",
                "pairs": [
                    ["LAP-CREATOR", "DOCK-UNIVERSAL"],
                    ["LAP-PRO", "DOCK-PRO"],
                    ["LAP-PRO", "DOCK-UNIVERSAL"],
                    ["LAP-MED", "DOCK-MED"],
                    ["LAP-MED", "DOCK-UNIVERSAL"],
                ],
            },
            {
                "type": "allowed_pairs",
                "left_slot": "laptop",
                "right_slot": "warranty",
                "pairs": [
                    ["LAP-CREATOR", "WAR-CREATOR"],
                    ["LAP-PRO", "WAR-PRO"],
                    ["LAP-MED", "WAR-MED"],
                ],
            },
            {
                "type": "allowed_pairs",
                "left_slot": "laptop",
                "right_slot": "software",
                "pairs": [
                    ["LAP-CREATOR", "SOFT-CREATOR"],
                    ["LAP-PRO", "SOFT-PRO"],
                    ["LAP-MED", "SOFT-MED"],
                ],
            },
            {"type": "max_lifecycle_cost", "value": 3900},
        ]
        return paired_tasks(
            base_id=f"radiology-dock-{variant.lower()}",
            family_id="radiology-dock-failure",
            variant=variant,
            domain="shopping",
            mechanism="compatibility_cascade",
            split="test",
            instruction=(
                "Complete the approved radiology workstation by day 3 with "
                "one laptop, 4K monitor, compatible dock, FIPS security key, "
                "matching warranty, and matching software. Keep total retained "
                "spending within $3,900."
            ),
            loss_clause=(
                " Avoid unnecessary returns, forfeited licenses, and bundle "
                "charges while completing it."
            ),
            failure_observation=(
                "purchase_product(DOCK-ORIGINAL) failed after the compatibility "
                "service rejected the item."
            ),
            commitments=commitments,
            failed_option_id="DOCK-ORIGINAL",
            failed_slot="dock",
            catalog=catalog,
            required_slots=slots,
            constraints=constraints,
            search_contexts=context,
            linked_loss_rules=[
                {
                    "rule_id": "WORKSTATION-REBATE",
                    "description": (
                        "Changing or returning the original laptop or monitor "
                        "reverses a $140 workstation bundle rebate."
                    ),
                    "trigger": "any_changed",
                    "commitment_ids": ["WS-LAP", "WS-MON"],
                    "amount": 140,
                }
            ],
            source_case="105",
        )

    return make("A", True) + make("B", False)


def cold_chain_family() -> list[dict[str, Any]]:
    slots = [
        "freezer",
        "sensor",
        "battery",
        "gateway",
        "service_plan",
        "installation",
    ]
    context = {slot: {"use_case": "clinic-cold-chain"} for slot in slots}

    def make(variant: str, legacy_battery_available: bool) -> list[dict[str, Any]]:
        commitments = [
            commitment("CC-FRZ", "freezer", "FRZ-LEGACY", 2400, 1700, arrival_day=3, certified=True),
            commitment("CC-SEN", "sensor", "SEN-LORA", 260, 180, arrival_day=2, certified=True),
            commitment("CC-GATE", "gateway", "GATE-LORA", 430, 210, arrival_day=2, certified=True),
            commitment("CC-SVC", "service_plan", "SVC-LEGACY", 360, 0, arrival_day=1, certified=True),
            commitment("CC-INST", "installation", "INST-STANDARD", 500, 100, arrival_day=4, certified=True),
        ]
        catalog = [
            option("FRZ-MODERN", "freezer", 1200, arrival_day=4, certified=True),
            option("FRZ-PREMIUM", "freezer", 2700, arrival_day=2, certified=True),
            option("SEN-LORA-B", "sensor", 220, arrival_day=3, certified=True),
            option("SEN-CELL", "sensor", 310, arrival_day=2, certified=True),
            option("BAT-LEGACY", "battery", 280, legacy_battery_available, arrival_day=2, certified=True),
            option("BAT-MODERN", "battery", 190, arrival_day=3, certified=True),
            option("BAT-PREMIUM", "battery", 240, arrival_day=1, certified=True),
            option("GATE-LORA-B", "gateway", 390, arrival_day=3, certified=True),
            option("GATE-CELL", "gateway", 470, arrival_day=2, certified=True),
            option("SVC-MODERN", "service_plan", 100, arrival_day=1, certified=True),
            option("SVC-PREMIUM", "service_plan", 420, arrival_day=1, certified=True),
            option("INST-FAST", "installation", 650, arrival_day=2, certified=True),
            option("INST-PARTNER", "installation", 420, arrival_day=4, certified=True),
        ]
        constraints = [
            *[
                {
                    "type": "slot_attribute",
                    "slot": slot,
                    "attribute": "arrival_day",
                    "op": "le",
                    "value": 4,
                }
                for slot in slots
            ],
            *[
                {
                    "type": "slot_attribute",
                    "slot": slot,
                    "attribute": "certified",
                    "op": "eq",
                    "value": True,
                }
                for slot in slots
            ],
            {
                "type": "allowed_pairs",
                "left_slot": "freezer",
                "right_slot": "battery",
                "pairs": [
                    ["FRZ-LEGACY", "BAT-LEGACY"],
                    ["FRZ-MODERN", "BAT-MODERN"],
                    ["FRZ-PREMIUM", "BAT-PREMIUM"],
                ],
            },
            {
                "type": "allowed_pairs",
                "left_slot": "freezer",
                "right_slot": "service_plan",
                "pairs": [
                    ["FRZ-LEGACY", "SVC-LEGACY"],
                    ["FRZ-MODERN", "SVC-MODERN"],
                    ["FRZ-PREMIUM", "SVC-PREMIUM"],
                ],
            },
            {
                "type": "allowed_pairs",
                "left_slot": "sensor",
                "right_slot": "gateway",
                "pairs": [
                    ["SEN-LORA", "GATE-LORA"],
                    ["SEN-LORA", "GATE-LORA-B"],
                    ["SEN-LORA-B", "GATE-LORA"],
                    ["SEN-LORA-B", "GATE-LORA-B"],
                    ["SEN-CELL", "GATE-CELL"],
                ],
            },
            {"type": "max_lifecycle_cost", "value": 7200},
        ]
        return paired_tasks(
            base_id=f"clinic-battery-{variant.lower()}",
            family_id="clinic-battery-failure",
            variant=variant,
            domain="shopping",
            mechanism="service_contract_cascade",
            split="heldout",
            instruction=(
                "Complete the certified clinic cold-chain kit by day 4 with "
                "one freezer, sensor, compatible backup battery, gateway, "
                "matching service plan, and installation. Keep total retained "
                "spending within $7,200."
            ),
            loss_clause=(
                " Preserve usable paid equipment where possible and avoid "
                "non-refundable service or installation losses."
            ),
            failure_observation=(
                "purchase_product(BATTERY-ORIGINAL) failed because the supplier "
                "reported zero remaining stock."
            ),
            commitments=commitments,
            failed_option_id="BATTERY-ORIGINAL",
            failed_slot="battery",
            catalog=catalog,
            required_slots=slots,
            constraints=constraints,
            search_contexts=context,
            linked_loss_rules=[
                {
                    "rule_id": "CALIBRATION-CREDIT",
                    "description": (
                        "Changing or returning the original freezer or "
                        "installation forfeits a prepaid $220 calibration credit."
                    ),
                    "trigger": "any_changed",
                    "commitment_ids": ["CC-FRZ", "CC-INST"],
                    "amount": 220,
                }
            ],
            source_case="121/122",
        )

    return make("A", True) + make("B", False)


def main() -> None:
    tasks = conference_family() + workstation_family() + cold_chain_family()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    GOLD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.json"):
        old.unlink()
    for item in tasks:
        (OUTPUT / f"{item['task_id']}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from repairscope_bench.oracle import solve_task

    gold = {item["task_id"]: solve_task(item).as_dict() for item in tasks}
    GOLD_OUTPUT.write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tasks)} tasks to {OUTPUT}")
    print(f"Wrote solver-derived gold to {GOLD_OUTPUT}")


if __name__ == "__main__":
    main()
