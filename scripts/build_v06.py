"""Build the v0.6 STATE-backed fixed-failure benchmark."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repairscope_bench.v06_environment import (  # noqa: E402
    StateBackedRecoveryEnvironment,
    snapshot_hash,
)
from repairscope_bench.v06_oracle import clear_v06_oracle_cache, solve_task_v06  # noqa: E402


OUTPUT = ROOT / "data" / "v06"
GOLD_OUTPUT = ROOT / "data" / "gold" / "v06.json"
STATE_COMMIT = "4efcbf2d4fe60df04878859b692d9391f3d5b33a"


VARIANTS = [
    {
        "variant": "refund-low",
        "pair": "refund",
        "refund_adjustment": -800,
        "settlement_charge": 0,
        "local_price": 300,
        "replacement_total": 950,
    },
    {
        "variant": "refund-full",
        "pair": "refund",
        "refund_adjustment": 0,
        "settlement_charge": 0,
        "local_price": 300,
        "replacement_total": 950,
    },
    {
        "variant": "penalty-none",
        "pair": "penalty",
        "refund_adjustment": 0,
        "settlement_charge": 0,
        "local_price": 450,
        "replacement_total": 900,
    },
    {
        "variant": "penalty-high",
        "pair": "penalty",
        "refund_adjustment": 0,
        "settlement_charge": 900,
        "local_price": 450,
        "replacement_total": 900,
    },
]


TRAVEL_FAMILIES = [
    {
        "family_id": "conference-dinner",
        "split": "dev",
        "failed_slot": "dinner",
        "failed_label": "conference dinner",
        "instruction": (
            "Complete my Shanghai conference trip for September 14-16. The "
            "flights, hotel, airport transfer, and conference pass already "
            "exist, but the dinner booking just failed. Keep the trip coherent "
            "and within CNY 4,800."
        ),
    },
    {
        "family_id": "destination-ground-plan",
        "split": "test",
        "failed_slot": "venue_shuttle",
        "failed_label": "venue shuttle",
        "instruction": (
            "Finish the ground arrangements for my Shanghai client visit. My "
            "flights, hotel, airport transfer, and meeting pass are already "
            "confirmed, but the venue-shuttle reservation failed. Keep every "
            "active arrangement mutually coherent and within CNY 4,800."
        ),
    },
    {
        "family_id": "shortened-trip",
        "split": "heldout",
        "failed_slot": "departure_transfer",
        "failed_label": "departure-day transfer",
        "instruction": (
            "Complete the revised Shanghai trip that now ends on September 16. "
            "The flights, hotel, local transfer, and event pass are already "
            "confirmed, but the departure-day transfer failed. Resolve the "
            "remaining arrangement coherently within CNY 4,800."
        ),
    },
]


SUPPORT_FAMILIES = [
    {
        "family_id": "radiology-workstation",
        "split": "dev",
        "anchor": "laptop",
        "failed_slot": "dock",
        "instruction": (
            "Complete the approved radiology workstation by day 4. The laptop, "
            "monitor, security key, warranty, and software orders already "
            "exist, but the dock purchase failed. Make the final workstation "
            "compatible and keep retained equipment spending below CNY 5,500."
        ),
    },
    {
        "family_id": "clinic-cold-chain",
        "split": "test",
        "anchor": "freezer",
        "failed_slot": "battery",
        "instruction": (
            "Complete the certified clinic cold-chain kit by day 4. The "
            "freezer, sensor, gateway, service plan, and installation orders "
            "already exist, but the backup battery purchase failed. Deliver a "
            "compatible certified kit below CNY 5,500."
        ),
    },
    {
        "family_id": "media-production-kit",
        "split": "heldout",
        "anchor": "camera",
        "failed_slot": "storage",
        "instruction": (
            "Complete the approved media-production kit by day 4. The camera, "
            "monitor, security device, protection plan, and editing licence "
            "orders already exist, but the storage-module purchase failed. "
            "Deliver a compatible kit below CNY 5,500."
        ),
    },
]


def _task_base(
    family: dict[str, Any],
    variant: dict[str, Any],
    domain: str,
) -> dict[str, Any]:
    task_id = f"{family['family_id']}-{variant['variant']}"
    return {
        "schema_version": "0.6",
        "task_id": task_id,
        "family_id": family["family_id"],
        "variant_id": variant["variant"],
        "counterfactual_pair_id": (
            f"{family['family_id']}-{variant['pair']}"
        ),
        "domain": domain,
        "environment_type": (
            "state_bench.travel+repair_extensions"
            if domain == "travel"
            else "state_bench.customer_support+repair_extensions"
        ),
        "split": family["split"],
        "now": "2026-08-01T10:00:00",
        "instruction": family["instruction"],
        "source": {
            "benchmark": "STATE-Bench",
            "repository": "https://github.com/microsoft/STATE-Bench",
            "commit": STATE_COMMIT,
            "reuse": (
                "Domain schemas, policy engine, read tools, preview-confirm "
                "writes, and persistent state runtime are imported directly."
            ),
        },
        "max_turns": 15,
        "oracle_max_semantic_actions": 2,
        "contracts": [],
        "boundary_commitments": [],
        "pre_failure_trace": [],
        "prefix_ledger": [],
        "latest_failure": {},
        "initial_snapshot": {},
        "initial_snapshot_sha256": "",
        "failure_snapshot": {},
        "snapshot_sha256": "",
    }


def build_travel_task(
    family: dict[str, Any], variant: dict[str, Any]
) -> dict[str, Any]:
    task = _task_base(family, variant, "travel")
    failed_slot = family["failed_slot"]
    user_id = "user_repair"
    original_hotel = f"{family['family_id']}-HOTEL-ORIG"
    alt1_hotel = f"{family['family_id']}-HOTEL-A"
    alt2_hotel = f"{family['family_id']}-HOTEL-B"
    decoy_hotel = f"{family['family_id']}-HOTEL-DECOY"
    local_failed = f"{family['family_id']}-{failed_slot}-LOCAL"
    alt1_failed = f"{family['family_id']}-{failed_slot}-A"
    alt2_failed = f"{family['family_id']}-{failed_slot}-B"
    failed_original = f"{family['family_id']}-{failed_slot}-FAILED"
    transfer_original = f"{family['family_id']}-TRANSFER-ORIG"
    transfer_alt1 = f"{family['family_id']}-TRANSFER-A"
    transfer_alt2 = f"{family['family_id']}-TRANSFER-B"
    pass_original = f"{family['family_id']}-PASS-ORIG"
    pass_alt2 = f"{family['family_id']}-PASS-B"

    replacement_total = variant["replacement_total"]
    alt1_hotel_price = replacement_total - 250
    alt2_bundle_total = 1600
    alt2_hotel_price = alt2_bundle_total - 250
    service_inventory = [
        _service_option(
            transfer_original, "transfer", 160, area="Huangpu", city="Shanghai"
        ),
        _service_option(
            pass_original, "pass", 300, area="citywide", city="Shanghai"
        ),
        _service_option(
            pass_alt2, "pass", 50, area="citywide", city="Shanghai"
        ),
        _service_option(
            failed_original,
            failed_slot,
            180,
            available=False,
            area="Huangpu",
            city="Shanghai",
            failure_message=(
                f"The selected {family['failed_label']} has no remaining inventory."
            ),
        ),
        _service_option(
            local_failed,
            failed_slot,
            variant["local_price"],
            area="Huangpu",
            city="Shanghai",
        ),
        _service_option(
            transfer_alt1, "transfer", 150, area="Lujiazui", city="Shanghai"
        ),
        _service_option(
            alt1_failed, failed_slot, 100, area="Lujiazui", city="Shanghai"
        ),
        _service_option(
            transfer_alt2, "transfer", 120, area="JingAn", city="Shanghai"
        ),
        _service_option(
            alt2_failed, failed_slot, 80, area="JingAn", city="Shanghai"
        ),
        _service_option(
            f"{family['family_id']}-{failed_slot}-DECOY",
            failed_slot,
            50,
            area="Chaoyang",
            city="Beijing",
        ),
        _service_option(
            f"{family['family_id']}-TRANSFER-DECOY",
            "transfer",
            40,
            area="Chaoyang",
            city="Beijing",
        ),
    ]
    hotels = [
        _hotel(original_hotel, "Huangpu Existing Hotel", "Shanghai", 450, 900),
        _hotel(alt1_hotel, "Lujiazui Riverside Hotel", "Shanghai", alt1_hotel_price // 2, alt1_hotel_price),
        _hotel(alt2_hotel, "JingAn Business Hotel", "Shanghai", alt2_hotel_price // 2, alt2_hotel_price),
        _hotel(decoy_hotel, "Beijing Decoy Hotel", "Beijing", 200, 400),
    ]
    flights = [
        _flight("MU-OUT-ORIG", "PEK", "PVG", "2026-09-14T08:00:00", "2026-09-14T10:30:00", 520),
        _flight("MU-RET-ORIG", "PVG", "PEK", "2026-09-16T19:00:00", "2026-09-16T21:30:00", 480),
    ]
    clean_snapshot = {
        "state_bench": {
            "flights": flights,
            "bookings": [],
            "users": [
                {
                    "user_id": user_id,
                    "name": "Repair Scope User",
                    "email": "repair@example.com",
                    "loyalty_tier": "basic",
                    "loyalty_points": 0,
                    "budget": 4800,
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
            "service_inventory": service_inventory,
        },
    }
    option_metadata = {
        "MU-OUT-ORIG": _metadata("outbound", 520, city="Shanghai"),
        "MU-RET-ORIG": _metadata("return", 480, city="Shanghai"),
        original_hotel: _metadata("hotel", 900, city="Shanghai", area="Huangpu"),
        alt1_hotel: _metadata("hotel", alt1_hotel_price, city="Shanghai", area="Lujiazui"),
        alt2_hotel: _metadata("hotel", alt2_hotel_price, city="Shanghai", area="JingAn"),
        decoy_hotel: _metadata("hotel", 400, city="Beijing", area="Chaoyang"),
    }
    for item in service_inventory:
        option_metadata[item["option_id"]] = _metadata(
            item["slot"],
            item["price"],
            available=item["available"],
            **item["attributes"],
        )
    task.update(
        {
            "failure_snapshot": clean_snapshot,
            "option_metadata": option_metadata,
            "compatibility_rules": [
                {
                    "left_slot": "hotel",
                    "right_slot": "transfer",
                    "pairs": [
                        [original_hotel, transfer_original],
                        [alt1_hotel, transfer_alt1],
                        [alt2_hotel, transfer_alt2],
                    ],
                },
                {
                    "left_slot": "hotel",
                    "right_slot": failed_slot,
                    "pairs": [
                        [original_hotel, local_failed],
                        [alt1_hotel, alt1_failed],
                        [alt2_hotel, alt2_failed],
                    ],
                },
            ],
            "required_slots": [
                "outbound",
                "return",
                "hotel",
                "transfer",
                "pass",
                failed_slot,
            ],
            "hard_constraints": [
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "city",
                    "op": "eq",
                    "value": "Shanghai",
                },
                {
                    "type": "slot_attribute",
                    "slot": "transfer",
                    "attribute": "city",
                    "op": "eq",
                    "value": "Shanghai",
                },
                {
                    "type": "slot_attribute",
                    "slot": failed_slot,
                    "attribute": "city",
                    "op": "eq",
                    "value": "Shanghai",
                },
                {
                    "type": "allowed_pairs",
                    "left_slot": "hotel",
                    "right_slot": "transfer",
                    "pairs": [
                        [original_hotel, transfer_original],
                        [alt1_hotel, transfer_alt1],
                        [alt2_hotel, transfer_alt2],
                    ],
                },
                {
                    "type": "allowed_pairs",
                    "left_slot": "hotel",
                    "right_slot": failed_slot,
                    "pairs": [
                        [original_hotel, local_failed],
                        [alt1_hotel, alt1_failed],
                        [alt2_hotel, alt2_failed],
                    ],
                },
                {"type": "max_active_total", "value": 4800},
            ],
        }
    )
    task["initial_snapshot"] = deepcopy(clean_snapshot)
    task["initial_snapshot_sha256"] = snapshot_hash(clean_snapshot)

    environment = StateBackedRecoveryEnvironment(task)
    environment.set_phase("prefix")
    prefix_calls = [
        {
            "name": "create_booking",
            "arguments": _flight_booking_args("MU-OUT-ORIG", user_id),
        },
        {
            "name": "create_booking",
            "arguments": _flight_booking_args("MU-RET-ORIG", user_id),
        },
        {
            "name": "book_hotel",
            "arguments": {"hotel_id": original_hotel, "user_id": user_id},
        },
        {
            "name": "book_local_service",
            "arguments": {"option_id": transfer_original, "user_id": user_id},
        },
        {
            "name": "book_local_service",
            "arguments": {"option_id": pass_original, "user_id": user_id},
        },
    ]
    _execute_prefix(environment, prefix_calls)
    failure_call = {
        "name": "book_local_service",
        "arguments": {"option_id": failed_original, "user_id": user_id},
    }
    failure_result = environment.execute_tool(
        failure_call["name"], failure_call["arguments"]
    )
    if failure_result.ok:
        raise RuntimeError(f"{task['task_id']}: failure call unexpectedly succeeded")

    task["failure_snapshot"] = environment.normalized_state()
    task["snapshot_sha256"] = snapshot_hash(task["failure_snapshot"])
    task["prefix_ledger"] = deepcopy(environment.ledger)
    task["pre_failure_trace"] = _public_trace(environment.event_log[:-1])
    task["latest_failure"] = {
        "tool": failure_call["name"],
        "arguments": failure_call["arguments"],
        "result": failure_result.as_dict(),
    }
    task["failure_observation"] = failure_result.message
    task["boundary_commitments"] = _boundary_commitments(environment)
    hotel_entity = _entity_for_slot(task["boundary_commitments"], "hotel")
    transfer_entity = _entity_for_slot(task["boundary_commitments"], "transfer")
    task["contracts"] = [
        {
            "contract_id": f"{task['task_id']}-refund-term",
            "description": (
                "The original hotel supplier adjusts the refund by "
                f"{variant['refund_adjustment']} if that reservation is cancelled."
            ),
            "trigger": "any_changed",
            "dispositions": ["CANCEL", "REPLACE"],
            "entity_ids": [hotel_entity],
            "refund_adjustment": variant["refund_adjustment"],
            "settlement_charge": 0,
        },
        {
            "contract_id": f"{task['task_id']}-package-term",
            "description": (
                "Changing the original hotel breaks its linked ground-service "
                f"package and charges {variant['settlement_charge']}."
            ),
            "trigger": "any_changed",
            "entity_ids": [hotel_entity, transfer_entity],
            "refund_adjustment": 0,
            "settlement_charge": variant["settlement_charge"],
        },
    ]
    task["oracle_actions"] = [
        {
            "action_id": "local-repair",
            "tool_calls": [
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": local_failed, "user_id": user_id},
                }
            ],
        },
        {
            "action_id": "replace-hotel-bundle-a",
            "tool_calls": [
                {
                    "name": "cancel_hotel_reservation",
                    "arguments": {"reservation_id": hotel_entity},
                },
                {
                    "name": "cancel_hotel_reservation",
                    "arguments": {"reservation_id": hotel_entity, "confirm": True},
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {"service_id": transfer_entity},
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {"service_id": transfer_entity, "confirm": True},
                },
                {
                    "name": "book_hotel",
                    "arguments": {"hotel_id": alt1_hotel, "user_id": user_id},
                },
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": transfer_alt1, "user_id": user_id},
                },
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": alt1_failed, "user_id": user_id},
                },
            ],
        },
        {
            "action_id": "replace-hotel-bundle-b",
            "tool_calls": [
                {
                    "name": "cancel_hotel_reservation",
                    "arguments": {"reservation_id": hotel_entity},
                },
                {
                    "name": "cancel_hotel_reservation",
                    "arguments": {"reservation_id": hotel_entity, "confirm": True},
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {"service_id": transfer_entity},
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {"service_id": transfer_entity, "confirm": True},
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {
                        "service_id": _entity_for_slot(
                            task["boundary_commitments"], "pass"
                        )
                    },
                },
                {
                    "name": "cancel_local_service",
                    "arguments": {
                        "service_id": _entity_for_slot(
                            task["boundary_commitments"], "pass"
                        ),
                        "confirm": True,
                    },
                },
                {
                    "name": "book_hotel",
                    "arguments": {"hotel_id": alt2_hotel, "user_id": user_id},
                },
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": transfer_alt2, "user_id": user_id},
                },
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": alt2_failed, "user_id": user_id},
                },
                {
                    "name": "book_local_service",
                    "arguments": {"option_id": pass_alt2, "user_id": user_id},
                },
            ],
        },
    ]
    task["candidate_scopes"] = [
        {"scope_id": item["action_id"], "action_ids": [item["action_id"]]}
        for item in task["oracle_actions"]
    ]
    return task


def build_support_task(
    family: dict[str, Any], variant: dict[str, Any]
) -> dict[str, Any]:
    task = _task_base(family, variant, "customer_support")
    customer_id = "cust_repair"
    anchor_slot = family["anchor"]
    failed_slot = family["failed_slot"]
    unaffected_a = "monitor" if anchor_slot != "freezer" else "sensor"
    unaffected_b = "security_key" if anchor_slot != "freezer" else "gateway"
    warranty_slot = "warranty" if anchor_slot != "freezer" else "service_plan"
    software_slot = "software" if anchor_slot != "freezer" else "installation"

    option_ids = {
        "anchor_original": f"{family['family_id']}-ANCHOR-ORIG",
        "unaffected_a": f"{family['family_id']}-AUX-A",
        "unaffected_b": f"{family['family_id']}-AUX-B",
        "warranty_original": f"{family['family_id']}-WARRANTY-ORIG",
        "software_original": f"{family['family_id']}-SOFTWARE-ORIG",
        "failed_original": f"{family['family_id']}-{failed_slot}-FAILED",
        "local": f"{family['family_id']}-{failed_slot}-LOCAL",
        "anchor_a": f"{family['family_id']}-ANCHOR-A",
        "warranty_a": f"{family['family_id']}-WARRANTY-A",
        "software_a": f"{family['family_id']}-SOFTWARE-A",
        "failed_a": f"{family['family_id']}-{failed_slot}-A",
        "anchor_b": f"{family['family_id']}-ANCHOR-B",
        "warranty_b": f"{family['family_id']}-WARRANTY-B",
        "software_b": f"{family['family_id']}-SOFTWARE-B",
        "failed_b": f"{family['family_id']}-{failed_slot}-B",
        "unaffected_a_b": f"{family['family_id']}-AUX-A-B",
    }
    replacement_total = variant["replacement_total"]
    bundle_a_prices = [replacement_total - 300, 100, 100, 100]
    bundle_b_total = 1600
    bundle_b_prices = [bundle_b_total - 400, 80, 80, 120, 120]
    products: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}

    def add_product(
        key: str,
        slot: str,
        price: int,
        *,
        in_stock: bool = True,
        arrival_day: int = 2,
        approved: bool = True,
    ) -> None:
        product_id = option_ids[key]
        products.append(
            _product(
                product_id,
                f"{family['family_id']} {slot} {key}",
                slot,
                price,
                in_stock,
            )
        )
        metadata[product_id] = _metadata(
            slot,
            price,
            available=in_stock,
            arrival_day=arrival_day,
            approved=approved,
        )
        if not in_stock:
            metadata[product_id]["failure_message"] = (
                f"The supplier reports zero stock for {product_id}."
            )

    add_product("anchor_original", anchor_slot, 900)
    add_product("unaffected_a", unaffected_a, 520)
    add_product("unaffected_b", unaffected_b, 90)
    add_product("warranty_original", warranty_slot, 180)
    add_product("software_original", software_slot, 260)
    add_product("failed_original", failed_slot, 180, in_stock=False)
    add_product("local", failed_slot, variant["local_price"])
    add_product("anchor_a", anchor_slot, bundle_a_prices[0])
    add_product("warranty_a", warranty_slot, bundle_a_prices[1])
    add_product("software_a", software_slot, bundle_a_prices[2])
    add_product("failed_a", failed_slot, bundle_a_prices[3])
    add_product("anchor_b", anchor_slot, bundle_b_prices[0])
    add_product("warranty_b", warranty_slot, bundle_b_prices[1])
    add_product("software_b", software_slot, bundle_b_prices[2])
    add_product("failed_b", failed_slot, bundle_b_prices[3])
    add_product("unaffected_a_b", unaffected_a, bundle_b_prices[4])
    for slot in [anchor_slot, warranty_slot, software_slot, failed_slot]:
        product_id = f"{family['family_id']}-{slot}-DECOY"
        option_ids[f"decoy_{slot}"] = product_id
        products.append(
            _product(product_id, f"Decoy {slot}", slot, 40, True)
        )
        metadata[product_id] = _metadata(
            slot, 40, arrival_day=8, approved=False
        )

    clean_snapshot = {
        "state_bench": {
            "products": products,
            "orders": [],
            "order_items": [],
            "customers": [
                {
                    "customer_id": customer_id,
                    "name": "Repair Scope Customer",
                    "email": "repair-shop@example.com",
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
    allowed_anchor_failed = [
        [option_ids["anchor_original"], option_ids["local"]],
        [option_ids["anchor_a"], option_ids["failed_a"]],
        [option_ids["anchor_b"], option_ids["failed_b"]],
    ]
    allowed_anchor_warranty = [
        [option_ids["anchor_original"], option_ids["warranty_original"]],
        [option_ids["anchor_a"], option_ids["warranty_a"]],
        [option_ids["anchor_b"], option_ids["warranty_b"]],
    ]
    allowed_anchor_software = [
        [option_ids["anchor_original"], option_ids["software_original"]],
        [option_ids["anchor_a"], option_ids["software_a"]],
        [option_ids["anchor_b"], option_ids["software_b"]],
    ]
    task.update(
        {
            "failure_snapshot": clean_snapshot,
            "option_metadata": metadata,
            "compatibility_rules": [
                {
                    "left_slot": anchor_slot,
                    "right_slot": failed_slot,
                    "pairs": allowed_anchor_failed,
                },
                {
                    "left_slot": anchor_slot,
                    "right_slot": warranty_slot,
                    "pairs": allowed_anchor_warranty,
                },
                {
                    "left_slot": anchor_slot,
                    "right_slot": software_slot,
                    "pairs": allowed_anchor_software,
                },
            ],
            "required_slots": [
                anchor_slot,
                unaffected_a,
                unaffected_b,
                warranty_slot,
                software_slot,
                failed_slot,
            ],
            "hard_constraints": [
                *[
                    {
                        "type": "slot_attribute",
                        "slot": slot,
                        "attribute": "arrival_day",
                        "op": "le",
                        "value": 4,
                    }
                    for slot in [
                        anchor_slot,
                        warranty_slot,
                        software_slot,
                        failed_slot,
                    ]
                ],
                *[
                    {
                        "type": "slot_attribute",
                        "slot": slot,
                        "attribute": "approved",
                        "op": "eq",
                        "value": True,
                    }
                    for slot in [
                        anchor_slot,
                        warranty_slot,
                        software_slot,
                        failed_slot,
                    ]
                ],
                {
                    "type": "allowed_pairs",
                    "left_slot": anchor_slot,
                    "right_slot": failed_slot,
                    "pairs": allowed_anchor_failed,
                },
                {
                    "type": "allowed_pairs",
                    "left_slot": anchor_slot,
                    "right_slot": warranty_slot,
                    "pairs": allowed_anchor_warranty,
                },
                {
                    "type": "allowed_pairs",
                    "left_slot": anchor_slot,
                    "right_slot": software_slot,
                    "pairs": allowed_anchor_software,
                },
                {"type": "max_active_total", "value": 5500},
            ],
        }
    )
    task["initial_snapshot"] = deepcopy(clean_snapshot)
    task["initial_snapshot_sha256"] = snapshot_hash(clean_snapshot)

    environment = StateBackedRecoveryEnvironment(task)
    environment.set_phase("prefix")
    prefix_product_keys = [
        "anchor_original",
        "unaffected_a",
        "unaffected_b",
        "warranty_original",
        "software_original",
    ]
    _execute_prefix(
        environment,
        [
            {
                "name": "purchase_product",
                "arguments": {
                    "customer_id": customer_id,
                    "product_id": option_ids[key],
                },
            }
            for key in prefix_product_keys
        ],
    )
    failure_call = {
        "name": "purchase_product",
        "arguments": {
            "customer_id": customer_id,
            "product_id": option_ids["failed_original"],
        },
    }
    failure_result = environment.execute_tool(
        failure_call["name"], failure_call["arguments"]
    )
    if failure_result.ok:
        raise RuntimeError(f"{task['task_id']}: failure call unexpectedly succeeded")

    task["failure_snapshot"] = environment.normalized_state()
    task["snapshot_sha256"] = snapshot_hash(task["failure_snapshot"])
    task["prefix_ledger"] = deepcopy(environment.ledger)
    task["pre_failure_trace"] = _public_trace(environment.event_log[:-1])
    task["latest_failure"] = {
        "tool": failure_call["name"],
        "arguments": failure_call["arguments"],
        "result": failure_result.as_dict(),
    }
    task["failure_observation"] = failure_result.message
    task["boundary_commitments"] = _boundary_commitments(environment)
    anchor_entity = _entity_for_slot(task["boundary_commitments"], anchor_slot)
    task["contracts"] = [
        {
            "contract_id": f"{task['task_id']}-refund-term",
            "description": (
                "The original anchor supplier adjusts the cancellation refund "
                f"by {variant['refund_adjustment']}."
            ),
            "trigger": "any_changed",
            "dispositions": ["CANCEL", "REPLACE"],
            "entity_ids": [anchor_entity],
            "refund_adjustment": variant["refund_adjustment"],
            "settlement_charge": 0,
        },
        {
            "contract_id": f"{task['task_id']}-bundle-term",
            "description": (
                "Changing the original anchor triggers a rebate, licence, or "
                f"service settlement charge of {variant['settlement_charge']}."
            ),
            "trigger": "any_changed",
            "entity_ids": [anchor_entity],
            "refund_adjustment": 0,
            "settlement_charge": variant["settlement_charge"],
        },
    ]

    by_slot = {
        item["slot"]: item["entity_id"] for item in task["boundary_commitments"]
    }
    entity_to_order = _support_entity_to_order(task["failure_snapshot"])
    cancel_slots = [anchor_slot, warranty_slot, software_slot]

    def replacement_calls(suffix: str) -> list[dict[str, Any]]:
        slots_to_cancel = list(cancel_slots)
        if suffix == "b":
            slots_to_cancel.append(unaffected_a)
        calls: list[dict[str, Any]] = [
            {"name": "get_policies", "arguments": {"topic": "cancellation"}}
        ]
        for slot in slots_to_cancel:
            order_id = entity_to_order[by_slot[slot]]
            calls.extend(
                [
                    {
                        "name": "cancel_order",
                        "arguments": {"order_id": order_id},
                    },
                    {
                        "name": "cancel_order",
                        "arguments": {"order_id": order_id, "confirm": True},
                    },
                ]
            )
        for key in [
            f"anchor_{suffix}",
            f"warranty_{suffix}",
            f"software_{suffix}",
            f"failed_{suffix}",
        ]:
            calls.append(
                {
                    "name": "purchase_product",
                    "arguments": {
                        "customer_id": customer_id,
                        "product_id": option_ids[key],
                    },
                }
            )
        if suffix == "b":
            calls.append(
                {
                    "name": "purchase_product",
                    "arguments": {
                        "customer_id": customer_id,
                        "product_id": option_ids["unaffected_a_b"],
                    },
                }
            )
        return calls

    task["oracle_actions"] = [
        {
            "action_id": "local-repair",
            "tool_calls": [
                {
                    "name": "purchase_product",
                    "arguments": {
                        "customer_id": customer_id,
                        "product_id": option_ids["local"],
                    },
                }
            ],
        },
        {
            "action_id": "replace-anchor-bundle-a",
            "tool_calls": replacement_calls("a"),
        },
        {
            "action_id": "replace-anchor-bundle-b",
            "tool_calls": replacement_calls("b"),
        },
    ]
    task["candidate_scopes"] = [
        {"scope_id": item["action_id"], "action_ids": [item["action_id"]]}
        for item in task["oracle_actions"]
    ]
    return task


def _execute_prefix(
    environment: StateBackedRecoveryEnvironment,
    calls: list[dict[str, Any]],
) -> None:
    for call in calls:
        result = environment.execute_tool(call["name"], call["arguments"])
        if not result.ok:
            raise RuntimeError(
                f"Prefix call failed: {call['name']} {result.message}"
            )


def _public_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": index,
            "tool": event["tool"],
            "arguments": event["arguments"],
            "result": event["result"],
        }
        for index, event in enumerate(events, start=1)
    ]


def _boundary_commitments(
    environment: StateBackedRecoveryEnvironment,
) -> list[dict[str, Any]]:
    result = []
    for slot, records in sorted(environment.active_options_by_slot().items()):
        for record in records:
            result.append(
                {
                    "entity_id": record["entity_id"],
                    "slot": slot,
                    "option_id": record["option_id"],
                    "paid_value": record["paid_value"],
                }
            )
    return result


def _entity_for_slot(commitments: list[dict[str, Any]], slot: str) -> str:
    matches = [item["entity_id"] for item in commitments if item["slot"] == slot]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one boundary entity for slot {slot}: {matches}")
    return matches[0]


def _support_entity_to_order(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        item["item_id"]: item["order_id"]
        for item in snapshot["state_bench"]["order_items"]
    }


def _flight_booking_args(flight_id: str, user_id: str) -> dict[str, Any]:
    return {
        "flight_id": flight_id,
        "user_id": user_id,
        "cabin_class": "economy",
        "seat_type": "aisle",
        "meal_preference": "standard",
        "add_wifi": False,
        "add_extra_legroom": False,
        "add_insurance": False,
        "payment_method": "credit_card",
    }


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
        "airline_code": "MU",
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
    available: bool = True,
    failure_message: str | None = None,
    **attributes: Any,
) -> dict[str, Any]:
    item = {
        "option_id": option_id,
        "slot": slot,
        "price": price,
        "available": available,
        "attributes": attributes,
    }
    if failure_message:
        item["failure_message"] = failure_message
    return item


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


def _metadata(
    slot: str,
    price: int,
    available: bool = True,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "slot": slot,
        "price": price,
        "available": available,
        "attributes": attributes,
    }


def _frontier_signature(frontier: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            tuple(sorted(item["scope"].items())),
        )
        for item in frontier
    )


def main() -> None:
    tasks = [
        build_travel_task(family, variant)
        for family in TRAVEL_FAMILIES
        for variant in VARIANTS
    ] + [
        build_support_task(family, variant)
        for family in SUPPORT_FAMILIES
        for variant in VARIANTS
    ]
    clear_v06_oracle_cache()
    gold: dict[str, Any] = {}
    for task in tasks:
        oracle = solve_task_v06(task)
        if oracle.feasible_scope_count < 3:
            raise RuntimeError(
                f"{task['task_id']}: fewer than three feasible scopes"
            )
        if _frontier_signature(oracle.frontier) != _frontier_signature(
            oracle.independent_frontier
        ):
            raise RuntimeError(
                f"{task['task_id']}: search and independent frontier differ"
            )
        gold[task["task_id"]] = oracle.as_dict()

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
    print(f"Wrote {len(tasks)} v0.6 tasks to {OUTPUT}")
    print(f"Wrote Pareto gold to {GOLD_OUTPUT}")


if __name__ == "__main__":
    main()
