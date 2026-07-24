"""Generate the v0.4 loss-sensitive fixed-failure benchmark pilot."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "legacy" / "v0.5" / "pilot"
GOLD_OUTPUT = ROOT / "data" / "legacy" / "v0.5" / "gold" / "pilot.json"
NATURAL_MONEY_REQUEST = (
    " Please sort this out without wasting money or undoing arrangements that "
    "still help with the trip."
)


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
        "attributes": attributes,
    }


def task(
    *,
    task_id: str,
    family_id: str,
    variant_id: str,
    domain: str,
    source_case: str,
    instruction: str,
    failure_observation: str,
    trace: list[dict[str, Any]],
    commitments: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    modification_rules: list[dict[str, Any]],
    required_slots: list[str],
    constraints: list[dict[str, Any]],
    affected_slots: list[str],
    loss_sensitive: bool,
) -> dict[str, Any]:
    public_catalog = deepcopy(catalog)
    known = {item["option_id"] for item in public_catalog}
    for item in commitments:
        if item["option_id"] in known:
            continue
        public_catalog.append(
            {
                "option_id": item["option_id"],
                "slot": item["slot"],
                "price": item["price_paid"],
                "available": True,
                "refund_if_cancelled_after_booking": 0,
                "attributes": deepcopy(item.get("attributes", {})),
                "provenance": "existing_record",
            }
        )
        known.add(item["option_id"])
    return {
        "schema_version": "0.4",
        "task_id": task_id,
        "family_id": family_id,
        "variant_id": variant_id,
        "domain": domain,
        "evaluation_class": (
            "loss_sensitive" if loss_sensitive else "infeasible_control"
        ),
        "source_inspiration": {
            "benchmark": "STATE-Bench",
            "case_id": source_case,
            "url": (
                "https://github.com/microsoft/STATE-Bench/tree/main/"
                f"state_bench/domains/{'travel' if domain == 'travel' else 'shopping_assistant'}"
            ),
            "transformation": (
                "Fixed post-failure state with STATE-style domain operations, "
                "new inventory and policy counterfactuals, and ledger-derived gold."
            ),
        },
        "instruction": instruction,
        "failure_observation": failure_observation,
        "pre_failure_trace": trace,
        "failure_snapshot": {
            "commitments": commitments,
            "note": "Authoritative state immediately after the failed operation.",
        },
        "failure": {
            "affected_slots": affected_slots,
            "side_effect_on_failed_call": "none",
        },
        "catalog": public_catalog,
        "modification_rules": modification_rules,
        "required_slots": required_slots,
        "constraints": constraints,
        "objective": {
            "mode": "lexicographic",
            "terms": [
                "recovery_loss",
                "financial_cost",
                "mutated_prior_commitments",
                "state_changing_actions",
            ],
        },
        "max_actions": 20,
    }


def destination_family() -> list[dict[str, Any]]:
    family = "destination-change-hotel-failure"
    trace = [
        {
            "step": 1,
            "tool": "change_reservation",
            "arguments": {
                "reservation_id": "BK-183",
                "to_option_id": "UA183SFO",
            },
            "result": {"status": "confirmed"},
        },
        {
            "step": 2,
            "tool": "book_travel_option",
            "arguments": {"option_id": "HOTEL-SFO-183"},
            "result": {"status": "failed", "error": "sold_out"},
        },
    ]

    def make(
        variant: str,
        *,
        max_commute: int,
        hotel_refund: int,
        alternative: bool,
        change_fee: int | None = None,
    ) -> dict[str, Any]:
        commitments = [
            commitment(
                "BK-183",
                "flight",
                "UA183SFO",
                435,
                335,
                arrival_city="SFO",
                date="2026-08-10",
            ),
            commitment(
                "HR-183",
                "hotel",
                "HOTEL-LAX-OLD",
                525,
                hotel_refund,
                commute_to_meeting_minutes=330,
                check_in="2026-08-10",
                check_out="2026-08-13",
            ),
        ]
        catalog = (
            [
                option(
                    "HOTEL-OAK-ALT",
                    "hotel",
                    420,
                    commute_to_meeting_minutes=45,
                    check_in="2026-08-10",
                    check_out="2026-08-13",
                )
            ]
            if alternative
            else []
        )
        catalog.extend(
            [
                option(
                    "HOTEL-SJC-DECOY",
                    "hotel",
                    300,
                    commute_to_meeting_minutes=95,
                    check_in="2026-08-10",
                    check_out="2026-08-13",
                ),
                option(
                    "HOTEL-SFO-WRONG-DATES",
                    "hotel",
                    280,
                    commute_to_meeting_minutes=20,
                    check_in="2026-08-11",
                    check_out="2026-08-13",
                ),
            ]
        )
        rules = []
        if change_fee is not None:
            rules.append(
                {
                    "commitment_id": "HR-183",
                    "from_option_id": "HOTEL-LAX-OLD",
                    "to_option_id": "HOTEL-OAK-ALT",
                    "fee": change_fee,
                    "net_cash_delta": change_fee,
                    "cash_components": {"hotel_change_fee": change_fee},
                    "available": True,
                }
            )
        return task(
            task_id=f"destination-hotel-{variant.lower()}",
            family_id=family,
            variant_id=variant,
            domain="travel",
            source_case="121",
            instruction=(
                "Keep the San Francisco meeting trip workable with a flight "
                "arriving in SFO and a hotel for August 10-13. The hotel commute "
                f"to the meeting must be no more than {max_commute} minutes."
                + NATURAL_MONEY_REQUEST
            ),
            failure_observation=(
                "book_travel_option(HOTEL-SFO-183) failed because the room sold out."
            ),
            trace=trace,
            commitments=commitments,
            catalog=catalog,
            modification_rules=rules,
            required_slots=["flight", "hotel"],
            constraints=[
                {
                    "type": "slot_attribute",
                    "slot": "flight",
                    "attribute": "arrival_city",
                    "op": "eq",
                    "value": "SFO",
                },
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "commute_to_meeting_minutes",
                    "op": "le",
                    "value": max_commute,
                },
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "check_in",
                    "op": "eq",
                    "value": "2026-08-10",
                },
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "check_out",
                    "op": "eq",
                    "value": "2026-08-13",
                },
            ],
            affected_slots=["hotel"],
            loss_sensitive=variant != "D",
        )

    return [
        make("A", max_commute=360, hotel_refund=225, alternative=True),
        make(
            "B",
            max_commute=60,
            hotel_refund=525,
            alternative=True,
            change_fee=80,
        ),
        make(
            "C",
            max_commute=60,
            hotel_refund=325,
            alternative=True,
            change_fee=50,
        ),
        make("D", max_commute=60, hotel_refund=0, alternative=False),
    ]


def shortened_trip_family() -> list[dict[str, Any]]:
    family = "shortened-trip-car-change-failure"
    trace = [
        {
            "step": 1,
            "tool": "change_reservation",
            "arguments": {
                "reservation_id": "HR-SEA",
                "to_option_id": "HOTEL-SEA-2N",
            },
            "result": {
                "status": "confirmed",
                "check_out": "2026-09-12",
            },
        },
        {
            "step": 2,
            "tool": "change_reservation",
            "arguments": {
                "reservation_id": "CR-184",
                "to_option_id": "CAR-SEA-SHORT",
            },
            "result": {"status": "failed", "error": "old_rate_plan_closed"},
        },
    ]

    def make(
        variant: str,
        *,
        max_dropoff: str,
        car_refund: int,
        replacement: bool,
        change_fee: int | None,
    ) -> dict[str, Any]:
        commitments = [
            commitment(
                "BK-SEA",
                "flight",
                "FLIGHT-SEA-BUNDLE",
                500,
                0,
                trip_end="2026-09-12",
            ),
            commitment(
                "HR-SEA",
                "hotel",
                "HOTEL-SEA-2N",
                380,
                190,
                check_out="2026-09-12",
            ),
            commitment(
                "CR-184",
                "car",
                "CAR-SEA-LONG",
                210,
                car_refund,
                dropoff="2026-09-13",
                pickup_city="SEA",
            ),
        ]
        catalog = (
            [
                option(
                    "CAR-SEA-SHORT",
                    "car",
                    140,
                    dropoff="2026-09-12",
                    pickup_city="SEA",
                )
            ]
            if replacement
            else []
        )
        catalog.extend(
            [
                option(
                    "CAR-SEA-LATE",
                    "car",
                    100,
                    dropoff="2026-09-13",
                    pickup_city="SEA",
                ),
                option("CAR-PDX-DECOY", "car", 90, dropoff="2026-09-12", pickup_city="PDX"),
            ]
        )
        rules = []
        if change_fee is not None:
            rules.append(
                {
                    "commitment_id": "CR-184",
                    "from_option_id": "CAR-SEA-LONG",
                    "to_option_id": "CAR-SEA-SHORT",
                    "fee": change_fee,
                    "net_cash_delta": change_fee,
                    "cash_components": {"rate_change_fee": change_fee},
                    "available": True,
                }
            )
        return task(
            task_id={
                "A": "short-trip-a-modify-car",
                "B": "short-trip-b-replace-car",
                "C": "short-trip-c-keep-extra-day",
                "D": "short-trip-d-infeasible",
            }[variant],
            family_id=family,
            variant_id=variant,
            domain="travel",
            source_case="122",
            instruction=(
                "The Seattle trip now ends on September 12. Keep the flight and "
                "hotel coherent and make sure the car is returned no later than "
                f"{max_dropoff}." + NATURAL_MONEY_REQUEST
            ),
            failure_observation=(
                "change_reservation(CR-184, CAR-SEA-SHORT) failed because the old rate plan closed."
            ),
            trace=trace,
            commitments=commitments,
            catalog=catalog,
            modification_rules=rules,
            required_slots=["flight", "hotel", "car"],
            constraints=[
                {
                    "type": "slot_attribute",
                    "slot": "flight",
                    "attribute": "trip_end",
                    "op": "eq",
                    "value": "2026-09-12",
                },
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "check_out",
                    "op": "eq",
                    "value": "2026-09-12",
                },
                {
                    "type": "slot_attribute",
                    "slot": "car",
                    "attribute": "dropoff",
                    "op": "le",
                    "value": max_dropoff,
                },
                {
                    "type": "slot_attribute",
                    "slot": "car",
                    "attribute": "pickup_city",
                    "op": "eq",
                    "value": "SEA",
                },
            ],
            affected_slots=["car"],
            loss_sensitive=variant != "D",
        )

    return [
        make(
            "A",
            max_dropoff="2026-09-12",
            car_refund=0,
            replacement=True,
            change_fee=30,
        ),
        make(
            "B",
            max_dropoff="2026-09-12",
            car_refund=140,
            replacement=True,
            change_fee=120,
        ),
        make(
            "C",
            max_dropoff="2026-09-13",
            car_refund=140,
            replacement=True,
            change_fee=30,
        ),
        make(
            "D",
            max_dropoff="2026-09-12",
            car_refund=0,
            replacement=False,
            change_fee=None,
        ),
    ]


def workstation_family() -> list[dict[str, Any]]:
    family = "workstation-dock-failure"
    trace = [
        {
            "step": 1,
            "tool": "purchase_product",
            "arguments": {"product_id": "CREATORBOOK-15"},
            "result": {"status": "confirmed", "order_id": "ORD-LAPTOP"},
        },
        {
            "step": 2,
            "tool": "purchase_product",
            "arguments": {"product_id": "MONITOR-4K"},
            "result": {"status": "confirmed", "order_id": "ORD-MONITOR"},
        },
        {
            "step": 3,
            "tool": "purchase_product",
            "arguments": {"product_id": "PROBOOK-DOCK"},
            "result": {"status": "voided", "error": "compatibility_check_failed"},
        },
    ]

    def make(
        variant: str,
        *,
        laptop_refund: int,
        adapter: bool,
        replacement_pair: bool,
        exchange_fee: int | None,
    ) -> dict[str, Any]:
        commitments = [
            commitment(
                "ORD-LAPTOP",
                "laptop",
                "CREATORBOOK-15",
                1200,
                laptop_refund,
                arrival_day=2,
            ),
            commitment(
                "ORD-MONITOR",
                "monitor",
                "MONITOR-4K",
                400,
                300,
                arrival_day=1,
            ),
        ]
        catalog = []
        if adapter:
            catalog.append(
                option(
                    "UNIVERSAL-ADAPTER-DOCK",
                    "dock",
                    250,
                    arrival_day=2,
                )
            )
        if replacement_pair:
            catalog.extend(
                [
                    option("PROBOOK-14", "laptop", 900, arrival_day=2),
                    option("PROBOOK-DOCK-V2", "dock", 100, arrival_day=2),
                ]
            )
        catalog.extend(
            [
                option("LEGACY-USB-A-DOCK", "dock", 70, arrival_day=1),
                option("PROBOOK-DOCK-LATE", "dock", 80, arrival_day=5),
                option("BUDGETBOOK-LATE", "laptop", 600, arrival_day=6),
            ]
        )
        rules = []
        if exchange_fee is not None:
            rules.append(
                {
                    "commitment_id": "ORD-LAPTOP",
                    "from_option_id": "CREATORBOOK-15",
                    "to_option_id": "PROBOOK-14",
                    "fee": exchange_fee,
                    "net_cash_delta": exchange_fee,
                    "cash_components": {"exchange_fee": exchange_fee},
                    "available": True,
                }
            )
        return task(
            task_id=f"workstation-{variant.lower()}",
            family_id=family,
            variant_id=variant,
            domain="shopping",
            source_case="105",
            instruction=(
                "Complete the workstation with one laptop, the 4K monitor, and "
                "a compatible dock, with everything arriving by day 3. Please "
                "avoid unnecessary return losses or replacing equipment that "
                "still works."
            ),
            failure_observation=(
                "purchase_product(PROBOOK-DOCK) was voided because it is incompatible with the purchased laptop."
            ),
            trace=trace,
            commitments=commitments,
            catalog=catalog,
            modification_rules=rules,
            required_slots=["laptop", "monitor", "dock"],
            constraints=[
                *[
                    {
                        "type": "slot_attribute",
                        "slot": slot,
                        "attribute": "arrival_day",
                        "op": "le",
                        "value": 3,
                    }
                    for slot in ["laptop", "monitor", "dock"]
                ],
                {
                    "type": "allowed_pairs",
                    "left_slot": "laptop",
                    "right_slot": "dock",
                    "pairs": [
                        ["CREATORBOOK-15", "UNIVERSAL-ADAPTER-DOCK"],
                        ["PROBOOK-14", "PROBOOK-DOCK-V2"],
                    ],
                },
            ],
            affected_slots=["dock"],
            loss_sensitive=variant != "D",
        )

    return [
        make(
            "A",
            laptop_refund=900,
            adapter=True,
            replacement_pair=True,
            exchange_fee=None,
        ),
        make(
            "B",
            laptop_refund=900,
            adapter=False,
            replacement_pair=True,
            exchange_fee=40,
        ),
        make(
            "C",
            laptop_refund=1100,
            adapter=False,
            replacement_pair=True,
            exchange_fee=400,
        ),
        make(
            "D",
            laptop_refund=0,
            adapter=False,
            replacement_pair=False,
            exchange_fee=None,
        ),
    ]


def package_family() -> list[dict[str, Any]]:
    family = "travel-package-car-failure"
    trace = [
        {
            "step": 1,
            "tool": "book_travel_option",
            "arguments": {"option_id": "UA-DEN-OUT"},
            "result": {"status": "confirmed", "reservation_id": "BK-OUT"},
        },
        {
            "step": 2,
            "tool": "book_travel_option",
            "arguments": {"option_id": "UA-DEN-RETURN"},
            "result": {"status": "confirmed", "reservation_id": "BK-RETURN"},
        },
        {
            "step": 3,
            "tool": "book_travel_option",
            "arguments": {"option_id": "HOTEL-UNION"},
            "result": {"status": "confirmed", "reservation_id": "HR-DEN"},
        },
        {
            "step": 4,
            "tool": "book_travel_option",
            "arguments": {"option_id": "CAR-DEN-ORIGINAL"},
            "result": {"status": "failed", "error": "inventory_changed"},
        },
    ]

    def make(
        variant: str,
        *,
        car_price: int,
        budget: int,
        hotel_refund: int,
        cheap_hotel: bool,
        outbound_refund: int,
        saver_flight: bool,
    ) -> dict[str, Any]:
        commitments = [
            commitment(
                "BK-OUT",
                "outbound",
                "UA-DEN-OUT",
                240,
                outbound_refund,
                trip_city="DEN",
                date="2026-06-23",
            ),
            commitment(
                "BK-RETURN",
                "return",
                "UA-DEN-RETURN",
                250,
                125,
                trip_city="DEN",
                date="2026-06-26",
            ),
            commitment(
                "HR-DEN",
                "hotel",
                "HOTEL-UNION",
                279,
                hotel_refund,
                trip_city="DEN",
                check_in="2026-06-23",
                check_out="2026-06-26",
            ),
        ]
        catalog = [
            option(
                "CAR-DEN-ALT",
                "car",
                car_price,
                trip_city="DEN",
                pickup="2026-06-23",
                dropoff="2026-06-26",
            )
        ]
        catalog.extend(
            [
                option(
                    "CAR-COS-DECOY",
                    "car",
                    80,
                    trip_city="COS",
                    pickup="2026-06-23",
                    dropoff="2026-06-26",
                ),
                option(
                    "HOTEL-COS-DECOY",
                    "hotel",
                    120,
                    trip_city="COS",
                    check_in="2026-06-23",
                    check_out="2026-06-26",
                ),
                option(
                    "UA-COS-OUT-DECOY",
                    "outbound",
                    90,
                    trip_city="COS",
                    date="2026-06-23",
                ),
            ]
        )
        if cheap_hotel:
            catalog.append(
                option(
                    "HOTEL-DEN-BUDGET",
                    "hotel",
                    180,
                    trip_city="DEN",
                    check_in="2026-06-23",
                    check_out="2026-06-26",
                )
            )
        if saver_flight:
            catalog.append(
                option(
                    "UA-DEN-OUT-SAVER",
                    "outbound",
                    60,
                    trip_city="DEN",
                    date="2026-06-23",
                )
            )
        return task(
            task_id={
                "A": "travel-package-a-keep-commitments",
                "B": "travel-package-b-replace-hotel",
                "C": "travel-package-c-replace-flight",
                "D": "travel-package-d-infeasible",
            }[variant],
            family_id=family,
            variant_id=variant,
            domain="travel",
            source_case="124",
            instruction=(
                "Complete the Denver trip with an outbound flight, return "
                "flight, hotel, and car for June 23-26. All arrangements must "
                f"be in Denver and final trip spending must stay within ${budget}."
                + NATURAL_MONEY_REQUEST
            ),
            failure_observation=(
                "book_travel_option(CAR-DEN-ORIGINAL) failed because inventory changed."
            ),
            trace=trace,
            commitments=commitments,
            catalog=catalog,
            modification_rules=[],
            required_slots=["outbound", "return", "hotel", "car"],
            constraints=[
                *[
                    {
                        "type": "slot_attribute",
                        "slot": slot,
                        "attribute": "trip_city",
                        "op": "eq",
                        "value": "DEN",
                    }
                    for slot in ["outbound", "return", "hotel", "car"]
                ],
                {"type": "max_lifecycle_cost", "value": budget},
            ],
            affected_slots=["car"],
            loss_sensitive=variant != "D",
        )

    return [
        make(
            "A",
            car_price=131,
            budget=1050,
            hotel_refund=79,
            cheap_hotel=True,
            outbound_refund=120,
            saver_flight=False,
        ),
        make(
            "B",
            car_price=210,
            budget=900,
            hotel_refund=279,
            cheap_hotel=True,
            outbound_refund=140,
            saver_flight=True,
        ),
        make(
            "C",
            car_price=210,
            budget=900,
            hotel_refund=179,
            cheap_hotel=True,
            outbound_refund=190,
            saver_flight=True,
        ),
        make(
            "D",
            car_price=210,
            budget=900,
            hotel_refund=0,
            cheap_hotel=False,
            outbound_refund=0,
            saver_flight=False,
        ),
    ]


def main() -> None:
    tasks = (
        destination_family()
        + shortened_trip_family()
        + workstation_family()
        + package_family()
    )
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
