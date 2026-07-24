"""Generate the public 16-task pilot from four auditable causal templates."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "pilot"


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
    available: bool,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "slot": slot,
        "price": price,
        "available": available,
        "attributes": attributes,
    }


def base_task(
    *,
    task_id: str,
    family_id: str,
    variant_id: str,
    domain: str,
    source_case: str,
    source_url: str,
    instruction: str,
    failure_observation: str,
    trace: list[dict[str, Any]],
    commitments: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    modification_rules: list[dict[str, Any]],
    required_slots: list[str],
    constraints: list[dict[str, Any]],
    affected_slots: list[str],
    feasible: bool,
    repair_loss: int | None,
    scope: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "task_id": task_id,
        "family_id": family_id,
        "variant_id": variant_id,
        "domain": domain,
        "source_inspiration": {
            "benchmark": "STATE-Bench",
            "case_id": source_case,
            "url": source_url,
            "transformation": (
                "Newly authored post-failure counterfactual. It preserves the "
                "source task's coordination structure but uses a fixed failure "
                "snapshot, explicit financial policies, new text, and a "
                "solver-derived repair oracle."
            ),
        },
        "instruction": instruction,
        "failure_observation": failure_observation,
        "pre_failure_trace": trace,
        "failure_snapshot": {
            "commitments": commitments,
            "note": (
                "Every evaluated model starts from this authoritative state. "
                "The trace is evidence of how the state was produced, not a "
                "model-generated chain of thought."
            ),
        },
        "failure": {
            "affected_slots": affected_slots,
            "side_effect_on_failed_call": "none",
        },
        "catalog": catalog,
        "modification_rules": modification_rules,
        "required_slots": required_slots,
        "constraints": constraints,
        "objective": {
            "mode": "lexicographic",
            "terms": [
                "repair_loss",
                "mutated_prior_commitments",
                "state_changing_actions",
            ],
            "repair_loss_definition": (
                "irrecoverable value of cancelled pre-failure commitments + "
                "net cost of post-failure purchases + explicit modification fees"
            ),
        },
        "expected_oracle": {
            "feasible": feasible,
            "repair_loss": repair_loss,
            "scope": scope,
        },
    }


def trip_package_family() -> list[dict[str, Any]]:
    source = (
        "https://github.com/microsoft/STATE-Bench/blob/main/"
        "state_bench/domains/travel/tasks/"
        "124-cross_plan_trip_budget_with_preference_floor.json"
    )
    family = "travel-package-car-failure"
    common_commitments = [
        commitment(
            "C-FLIGHT-OUT",
            "outbound",
            "UA-DEN-OUT",
            240,
            120,
            trip_city="DEN",
            date="2026-06-23",
        ),
        commitment(
            "C-FLIGHT-RETURN",
            "return",
            "UA-DEN-RETURN",
            250,
            125,
            trip_city="DEN",
            date="2026-06-26",
        ),
        commitment(
            "C-HOTEL-UNION",
            "hotel",
            "HOTEL-UNION",
            279,
            279,
            trip_city="DEN",
            check_in="2026-06-23",
            check_out="2026-06-26",
        ),
    ]
    trace = [
        {
            "step": 1,
            "tool": "book_flight",
            "arguments": {"option_id": "UA-DEN-OUT"},
            "result": {"status": "confirmed", "commitment_id": "C-FLIGHT-OUT"},
        },
        {
            "step": 2,
            "tool": "book_flight",
            "arguments": {"option_id": "UA-DEN-RETURN"},
            "result": {
                "status": "confirmed",
                "commitment_id": "C-FLIGHT-RETURN",
            },
        },
        {
            "step": 3,
            "tool": "book_hotel",
            "arguments": {"option_id": "HOTEL-UNION"},
            "result": {"status": "confirmed", "commitment_id": "C-HOTEL-UNION"},
        },
        {
            "step": 4,
            "tool": "book_car",
            "arguments": {"option_id": "CAR-DEN-ORIGINAL"},
            "result": {"status": "failed", "error": "inventory_changed"},
        },
    ]
    constraints = [
        {
            "type": "slot_attribute",
            "slot": "outbound",
            "attribute": "trip_city",
            "op": "eq",
            "value": "DEN",
        },
        {
            "type": "slot_attribute",
            "slot": "return",
            "attribute": "trip_city",
            "op": "eq",
            "value": "DEN",
        },
        {
            "type": "slot_attribute",
            "slot": "hotel",
            "attribute": "trip_city",
            "op": "eq",
            "value": "DEN",
        },
        {
            "type": "slot_attribute",
            "slot": "car",
            "attribute": "trip_city",
            "op": "eq",
            "value": "DEN",
        },
        {"type": "max_lifecycle_cost", "value": 900},
    ]
    required = ["outbound", "return", "hotel", "car"]
    keep_scope = {
        "C-FLIGHT-OUT": "KEEP",
        "C-FLIGHT-RETURN": "KEEP",
        "C-HOTEL-UNION": "KEEP",
    }

    task_a = base_task(
        task_id="travel-package-a-local-car",
        family_id=family,
        variant_id="A",
        domain="travel",
        source_case="124",
        source_url=source,
        instruction=(
            "Complete the confirmed Denver package under the hard $900 total. "
            "The original car failed; preserve confirmed reservations unless a "
            "change is required to satisfy the stated constraints."
        ),
        failure_observation=(
            "The $126 original car disappeared from inventory during booking. "
            "A comparable $131 Denver car is now available."
        ),
        trace=trace,
        commitments=deepcopy(common_commitments),
        catalog=[
            option(
                "CAR-DEN-ALT",
                "car",
                131,
                True,
                trip_city="DEN",
                pickup="2026-06-23",
                dropoff="2026-06-26",
            )
        ],
        modification_rules=[],
        required_slots=required,
        constraints=constraints,
        affected_slots=["car"],
        feasible=True,
        repair_loss=131,
        scope=keep_scope,
    )

    task_b = base_task(
        task_id="travel-package-b-replace-hotel",
        family_id=family,
        variant_id="B",
        domain="travel",
        source_case="124",
        source_url=source,
        instruction=(
            "Complete the confirmed Denver package under the hard $900 total. "
            "The original car failed; preserve confirmed reservations unless a "
            "change is required to satisfy the stated constraints."
        ),
        failure_observation=(
            "The original car disappeared. The only car is $210. The confirmed "
            "hotel is fully refundable, and a $180 Denver hotel is available."
        ),
        trace=trace,
        commitments=deepcopy(common_commitments),
        catalog=[
            option(
                "CAR-DEN-ALT",
                "car",
                210,
                True,
                trip_city="DEN",
                pickup="2026-06-23",
                dropoff="2026-06-26",
            ),
            option(
                "HOTEL-DEN-BUDGET",
                "hotel",
                180,
                True,
                trip_city="DEN",
                check_in="2026-06-23",
                check_out="2026-06-26",
            ),
        ],
        modification_rules=[],
        required_slots=required,
        constraints=constraints,
        affected_slots=["car"],
        feasible=True,
        repair_loss=390,
        scope={
            "C-FLIGHT-OUT": "KEEP",
            "C-FLIGHT-RETURN": "KEEP",
            "C-HOTEL-UNION": "REPLACE",
        },
    )

    commitments_c = deepcopy(common_commitments)
    commitments_c[2]["refund_if_cancelled"] = 0
    task_c = base_task(
        task_id="travel-package-c-modify-flight",
        family_id=family,
        variant_id="C",
        domain="travel",
        source_case="124",
        source_url=source,
        instruction=(
            "Complete the confirmed Denver package under the hard $900 total. "
            "The original car failed; preserve confirmed reservations unless a "
            "change is required to satisfy the stated constraints."
        ),
        failure_observation=(
            "The only replacement car costs $210. The hotel is non-refundable. "
            "The outbound carrier offers a same-date saver change with a $20 "
            "fee and a $100 fare credit (net cash change: -$80)."
        ),
        trace=trace,
        commitments=commitments_c,
        catalog=[
            option(
                "CAR-DEN-ALT",
                "car",
                210,
                True,
                trip_city="DEN",
                pickup="2026-06-23",
                dropoff="2026-06-26",
            ),
            option(
                "UA-DEN-OUT-SAVER",
                "outbound",
                160,
                True,
                trip_city="DEN",
                date="2026-06-23",
            ),
        ],
        modification_rules=[
            {
                "commitment_id": "C-FLIGHT-OUT",
                "to_option_id": "UA-DEN-OUT-SAVER",
                "fee": 20,
                "net_cash_delta": -80,
                "available": True,
            }
        ],
        required_slots=required,
        constraints=constraints,
        affected_slots=["car"],
        feasible=True,
        repair_loss=230,
        scope={
            "C-FLIGHT-OUT": "MODIFY",
            "C-FLIGHT-RETURN": "KEEP",
            "C-HOTEL-UNION": "KEEP",
        },
    )

    task_d = base_task(
        task_id="travel-package-d-infeasible",
        family_id=family,
        variant_id="D",
        domain="travel",
        source_case="124",
        source_url=source,
        instruction=(
            "Complete the confirmed Denver package under the hard $900 total. "
            "Do not cancel confirmed reservations if no package can meet the cap; "
            "report the blocker instead."
        ),
        failure_observation=(
            "The only replacement car costs $210. The hotel is non-refundable, "
            "and the confirmed flights cannot be changed or refunded enough to "
            "bring the package under $900."
        ),
        trace=trace,
        commitments=commitments_c,
        catalog=[
            option(
                "CAR-DEN-ALT",
                "car",
                210,
                True,
                trip_city="DEN",
                pickup="2026-06-23",
                dropoff="2026-06-26",
            )
        ],
        modification_rules=[],
        required_slots=required,
        constraints=constraints,
        affected_slots=["car"],
        feasible=False,
        repair_loss=None,
        scope=keep_scope,
    )
    return [task_a, task_b, task_c, task_d]


def destination_family() -> list[dict[str, Any]]:
    source = (
        "https://github.com/microsoft/STATE-Bench/blob/main/"
        "state_bench/domains/travel/tasks/"
        "121-change_flight_cascade_replace_hotel.json"
    )
    family = "destination-change-hotel-failure"
    commitments = [
        commitment(
            "C-FLIGHT-SFO",
            "flight",
            "UA183SFO",
            435,
            335,
            arrival_city="SFO",
            date="2026-08-10",
        ),
        commitment(
            "C-HOTEL-LAX",
            "hotel",
            "HOTEL-LAX-OLD",
            525,
            525,
            commute_to_meeting_minutes=330,
            check_in="2026-08-10",
            check_out="2026-08-13",
        ),
    ]
    trace = [
        {
            "step": 1,
            "tool": "change_flight",
            "arguments": {"booking_id": "BK-183", "to": "UA183SFO"},
            "result": {"status": "confirmed", "commitment_id": "C-FLIGHT-SFO"},
        },
        {
            "step": 2,
            "tool": "book_hotel",
            "arguments": {"option_id": "HOTEL-SFO-183"},
            "result": {"status": "failed", "error": "sold_out"},
        },
    ]
    base_constraints = [
        {
            "type": "slot_attribute",
            "slot": "flight",
            "attribute": "arrival_city",
            "op": "eq",
            "value": "SFO",
        }
    ]
    scope_keep = {"C-FLIGHT-SFO": "KEEP", "C-HOTEL-LAX": "KEEP"}

    def make(
        variant: str,
        max_commute: int,
        oak_available: bool,
        sfo_available: bool,
        feasible: bool,
        loss: int | None,
        scope: dict[str, str],
    ) -> dict[str, Any]:
        observation = {
            "A": (
                "The requested SFO hotel sold out. An Oakland hotel with a "
                "45-minute meeting commute is available for $420."
            ),
            "B": (
                "The requested SFO hotel sold out. The user explicitly permits "
                "up to a 360-minute commute; the old LAX hotel remains valid."
            ),
            "C": (
                "The requested SFO hotel sold out. A second SFO hotel with a "
                "15-minute commute is available for $600."
            ),
            "D": (
                "The requested SFO hotel sold out. No available hotel is within "
                "the user's 30-minute hard commute limit."
            ),
        }[variant]
        catalog = [
            option(
                "HOTEL-OAK-ALT",
                "hotel",
                420,
                oak_available,
                commute_to_meeting_minutes=45,
                check_in="2026-08-10",
                check_out="2026-08-13",
            ),
            option(
                "HOTEL-SFO-ALT",
                "hotel",
                600,
                sfo_available,
                commute_to_meeting_minutes=15,
                check_in="2026-08-10",
                check_out="2026-08-13",
            ),
            option(
                "HOTEL-SFO-183",
                "hotel",
                555,
                False,
                commute_to_meeting_minutes=10,
                check_in="2026-08-10",
                check_out="2026-08-13",
            ),
        ]
        return base_task(
            task_id=f"destination-hotel-{variant.lower()}",
            family_id=family,
            variant_id=variant,
            domain="travel",
            source_case="121",
            source_url=source,
            instruction=(
                "Keep the changed San Francisco trip coherent. Lodging must be "
                f"within {max_commute} minutes of the meeting. Preserve confirmed "
                "arrangements when they still satisfy every hard constraint."
            ),
            failure_observation=observation,
            trace=trace,
            commitments=deepcopy(commitments),
            catalog=catalog,
            modification_rules=[],
            required_slots=["flight", "hotel"],
            constraints=base_constraints
            + [
                {
                    "type": "slot_attribute",
                    "slot": "hotel",
                    "attribute": "commute_to_meeting_minutes",
                    "op": "le",
                    "value": max_commute,
                }
            ],
            affected_slots=["hotel"],
            feasible=feasible,
            repair_loss=loss,
            scope=scope,
        )

    return [
        make(
            "A",
            60,
            True,
            False,
            True,
            420,
            {"C-FLIGHT-SFO": "KEEP", "C-HOTEL-LAX": "REPLACE"},
        ),
        make("B", 360, True, False, True, 0, scope_keep),
        make(
            "C",
            30,
            False,
            True,
            True,
            600,
            {"C-FLIGHT-SFO": "KEEP", "C-HOTEL-LAX": "REPLACE"},
        ),
        make("D", 30, False, False, False, None, scope_keep),
    ]


def shortened_trip_family() -> list[dict[str, Any]]:
    source = (
        "https://github.com/microsoft/STATE-Bench/blob/main/"
        "state_bench/domains/travel/tasks/"
        "122-shortened_trip_cancel_hotel_replace_car_dates.json"
    )
    family = "shortened-trip-car-change-failure"
    trace = [
        {
            "step": 1,
            "tool": "cancel_hotel_night",
            "arguments": {"reservation_id": "HR-184", "night": "2026-09-12"},
            "result": {"status": "cancelled", "refund": 190},
        },
        {
            "step": 2,
            "tool": "change_car_dates",
            "arguments": {"rental_id": "CR-184", "dropoff": "2026-09-12"},
            "result": {"status": "failed", "error": "rate_plan_not_changeable"},
        },
    ]
    commitments = [
        commitment(
            "C-FLIGHT-SEA",
            "flight",
            "FLIGHT-SEA-BUNDLE",
            500,
            0,
            trip_end="2026-09-12",
        ),
        commitment(
            "C-HOTEL-SEA",
            "hotel",
            "HOTEL-SEA-2N",
            380,
            190,
            check_out="2026-09-12",
        ),
        commitment(
            "C-CAR-LONG",
            "car",
            "CAR-SEA-LONG",
            210,
            210,
            dropoff="2026-09-13",
        ),
    ]
    scope_keep = {
        "C-FLIGHT-SEA": "KEEP",
        "C-HOTEL-SEA": "KEEP",
        "C-CAR-LONG": "KEEP",
    }

    def constraints(max_dropoff: str) -> list[dict[str, Any]]:
        return [
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
        ]

    task_a = base_task(
        task_id="short-trip-a-keep-extra-day",
        family_id=family,
        variant_id="A",
        domain="travel",
        source_case="122",
        source_url=source,
        instruction=(
            "The Seattle trip ends September 12. It is acceptable to keep the "
            "already-paid car reservation through September 13 if shortening it "
            "fails; do not disturb the flights or remaining hotel nights."
        ),
        failure_observation=(
            "The attempt to shorten the existing car reservation failed. The "
            "existing car remains confirmed through September 13."
        ),
        trace=trace,
        commitments=deepcopy(commitments),
        catalog=[],
        modification_rules=[],
        required_slots=["flight", "hotel", "car"],
        constraints=constraints("2026-09-13"),
        affected_slots=["car"],
        feasible=True,
        repair_loss=0,
        scope=scope_keep,
    )

    task_b = base_task(
        task_id="short-trip-b-replace-car",
        family_id=family,
        variant_id="B",
        domain="travel",
        source_case="122",
        source_url=source,
        instruction=(
            "The Seattle trip ends September 12, and the car must also end by "
            "that date. Preserve the flights and remaining hotel nights."
        ),
        failure_observation=(
            "The original vendor cannot change the car dates. The long rental is "
            "fully refundable, and another two-day car is available for $140."
        ),
        trace=trace,
        commitments=deepcopy(commitments),
        catalog=[
            option(
                "CAR-SEA-SHORT",
                "car",
                140,
                True,
                dropoff="2026-09-12",
            )
        ],
        modification_rules=[],
        required_slots=["flight", "hotel", "car"],
        constraints=constraints("2026-09-12"),
        affected_slots=["car"],
        feasible=True,
        repair_loss=140,
        scope={
            "C-FLIGHT-SEA": "KEEP",
            "C-HOTEL-SEA": "KEEP",
            "C-CAR-LONG": "REPLACE",
        },
    )

    commitments_c = deepcopy(commitments)
    commitments_c[2]["refund_if_cancelled"] = 0
    task_c = base_task(
        task_id="short-trip-c-modify-car",
        family_id=family,
        variant_id="C",
        domain="travel",
        source_case="122",
        source_url=source,
        instruction=(
            "The Seattle trip ends September 12, and the car must also end by "
            "that date. Preserve the flights and remaining hotel nights."
        ),
        failure_observation=(
            "The first date-change API failed. The rental is non-refundable, but "
            "a supervisor modification to September 12 is available for a $30 fee."
        ),
        trace=trace,
        commitments=commitments_c,
        catalog=[
            option(
                "CAR-SEA-SHORT",
                "car",
                140,
                True,
                dropoff="2026-09-12",
            )
        ],
        modification_rules=[
            {
                "commitment_id": "C-CAR-LONG",
                "to_option_id": "CAR-SEA-SHORT",
                "fee": 30,
                "net_cash_delta": 30,
                "available": True,
            }
        ],
        required_slots=["flight", "hotel", "car"],
        constraints=constraints("2026-09-12"),
        affected_slots=["car"],
        feasible=True,
        repair_loss=30,
        scope={
            "C-FLIGHT-SEA": "KEEP",
            "C-HOTEL-SEA": "KEEP",
            "C-CAR-LONG": "MODIFY",
        },
    )

    task_d = base_task(
        task_id="short-trip-d-infeasible",
        family_id=family,
        variant_id="D",
        domain="travel",
        source_case="122",
        source_url=source,
        instruction=(
            "The Seattle trip ends September 12, and the car must also end by "
            "that date. If no compliant car action exists, preserve current "
            "commitments and report the blocker."
        ),
        failure_observation=(
            "The original car cannot be changed or cancelled, and every other "
            "car is sold out through September 12."
        ),
        trace=trace,
        commitments=commitments_c,
        catalog=[],
        modification_rules=[],
        required_slots=["flight", "hotel", "car"],
        constraints=constraints("2026-09-12"),
        affected_slots=["car"],
        feasible=False,
        repair_loss=None,
        scope=scope_keep,
    )
    return [task_a, task_b, task_c, task_d]


def workstation_family() -> list[dict[str, Any]]:
    source = (
        "https://github.com/microsoft/STATE-Bench/blob/main/"
        "state_bench/domains/shopping_assistant/tasks/"
        "105-hard_compat_dock_wrong_laptop.json"
    )
    family = "workstation-dock-compatibility-failure"
    trace = [
        {
            "step": 1,
            "tool": "place_order",
            "arguments": {"option_id": "CREATORBOOK-15"},
            "result": {"status": "confirmed", "commitment_id": "C-LAPTOP"},
        },
        {
            "step": 2,
            "tool": "place_order",
            "arguments": {"option_id": "MONITOR-4K"},
            "result": {"status": "confirmed", "commitment_id": "C-MONITOR"},
        },
        {
            "step": 3,
            "tool": "place_order",
            "arguments": {"option_id": "PROBOOK-DOCK"},
            "result": {"status": "voided", "error": "compatibility_check_failed"},
        },
    ]
    commitments = [
        commitment(
            "C-LAPTOP",
            "laptop",
            "CREATORBOOK-15",
            1200,
            1200,
            arrival_day=2,
        ),
        commitment(
            "C-MONITOR",
            "monitor",
            "MONITOR-4K",
            400,
            300,
            arrival_day=1,
        ),
    ]
    required = ["laptop", "monitor", "dock"]
    constraints = [
        {
            "type": "slot_attribute",
            "slot": "laptop",
            "attribute": "arrival_day",
            "op": "le",
            "value": 3,
        },
        {
            "type": "slot_attribute",
            "slot": "monitor",
            "attribute": "arrival_day",
            "op": "le",
            "value": 3,
        },
        {
            "type": "slot_attribute",
            "slot": "dock",
            "attribute": "arrival_day",
            "op": "le",
            "value": 3,
        },
        {
            "type": "allowed_pairs",
            "left_slot": "laptop",
            "right_slot": "dock",
            "pairs": [
                ["CREATORBOOK-15", "CREATOR-DOCK"],
                ["CREATORBOOK-15", "UNIVERSAL-ADAPTER-DOCK"],
                ["PROBOOK-14", "PROBOOK-DOCK-V2"],
            ],
        },
    ]
    keep_scope = {"C-LAPTOP": "KEEP", "C-MONITOR": "KEEP"}

    def make(
        variant: str,
        laptop_refund: int,
        creator_dock: bool,
        adapter_dock: bool,
        replacement_pair: bool,
        feasible: bool,
        loss: int | None,
        scope: dict[str, str],
    ) -> dict[str, Any]:
        state = deepcopy(commitments)
        state[0]["refund_if_cancelled"] = laptop_refund
        observations = {
            "A": (
                "The selected ProBook dock was voided as incompatible. A "
                "CreatorBook-compatible dock can arrive by day 2 for $180."
            ),
            "B": (
                "No CreatorBook-compatible dock can arrive by day 3. The laptop "
                "is fully refundable; a $900 ProBook and $100 compatible dock "
                "can both arrive by day 2."
            ),
            "C": (
                "The laptop is non-refundable. A $250 universal adapter-dock "
                "compatible with the CreatorBook can arrive by day 2."
            ),
            "D": (
                "No dock compatible with the confirmed laptop can arrive by day "
                "3, and no complete replacement laptop-dock pair can arrive."
            ),
        }
        catalog = [
            option(
                "CREATOR-DOCK",
                "dock",
                180,
                creator_dock,
                arrival_day=2,
            ),
            option(
                "UNIVERSAL-ADAPTER-DOCK",
                "dock",
                250,
                adapter_dock,
                arrival_day=2,
            ),
            option(
                "PROBOOK-14",
                "laptop",
                900,
                replacement_pair,
                arrival_day=2,
            ),
            option(
                "PROBOOK-DOCK-V2",
                "dock",
                100,
                replacement_pair,
                arrival_day=2,
            ),
        ]
        return base_task(
            task_id=f"workstation-{variant.lower()}",
            family_id=family,
            variant_id=variant,
            domain="shopping",
            source_case="105",
            source_url=source,
            instruction=(
                "Complete a laptop, 4K monitor, and compatible dock workstation "
                "that arrives by day 3. Keep already confirmed compatible items "
                "unless changing them is necessary."
            ),
            failure_observation=observations[variant],
            trace=trace,
            commitments=state,
            catalog=catalog,
            modification_rules=[],
            required_slots=required,
            constraints=constraints,
            affected_slots=["dock"],
            feasible=feasible,
            repair_loss=loss,
            scope=scope,
        )

    return [
        make("A", 1200, True, False, False, True, 180, keep_scope),
        make(
            "B",
            1200,
            False,
            False,
            True,
            True,
            1000,
            {"C-LAPTOP": "REPLACE", "C-MONITOR": "KEEP"},
        ),
        make("C", 0, False, True, True, True, 250, keep_scope),
        make("D", 0, False, False, False, False, None, keep_scope),
    ]


def main() -> None:
    tasks = (
        trip_package_family()
        + destination_family()
        + shortened_trip_family()
        + workstation_family()
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for old in OUTPUT.glob("*.json"):
        old.unlink()
    for task in tasks:
        path = OUTPUT / f"{task['task_id']}.json"
        path.write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {len(tasks)} tasks to {OUTPUT}")


if __name__ == "__main__":
    main()
