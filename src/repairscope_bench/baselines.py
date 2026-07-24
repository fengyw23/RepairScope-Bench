from __future__ import annotations

from copy import deepcopy
from typing import Any

from .oracle import solve_task


def make_actions(task: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    if task.get("schema_version") == "0.6":
        return _make_v06_calls(task, strategy)
    if strategy == "oracle":
        oracle = solve_task(task)
        if not oracle.feasible:
            return [
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No constraint-satisfying repair exists."},
                }
            ]
        return oracle.optimal_plans[0] + _completion_actions(task)
    if strategy == "no_repair":
        return _completion_actions(task)
    if strategy == "local_repair":
        return _local_repair(task)
    if strategy == "full_rollback":
        return _full_rollback(task)
    if strategy == "dependency_repair":
        return _dependency_repair(task)
    if strategy == "global_cost":
        cost_task = deepcopy(task)
        cost_task["objective"]["terms"] = [
            "financial_cost",
            "recovery_loss",
            "mutated_prior_commitments",
            "state_changing_actions",
        ]
        oracle = solve_task(cost_task)
        if not oracle.feasible:
            return [
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No constraint-satisfying repair exists."},
                }
            ]
        return oracle.optimal_plans[0] + _completion_actions(task)
    raise ValueError(f"Unknown baseline strategy: {strategy}")


def _make_v06_calls(
    task: dict[str, Any], strategy: str
) -> list[dict[str, Any]]:
    from .v06_constraints import check_v06_constraints
    from .v06_environment import StateBackedRecoveryEnvironment
    from .v06_oracle import solve_task_v06

    if strategy == "no_repair":
        return []
    if strategy in {"local_repair", "dependency_repair"}:
        return deepcopy(_v06_action(task, "local-repair")["tool_calls"])
    if strategy in {"oracle", "pareto_oracle"}:
        oracle = solve_task_v06(task)
        return deepcopy(oracle.frontier[0]["tool_calls"])
    if strategy == "full_rollback":
        return _v06_full_rollback(task)

    evaluated: list[
        tuple[
            dict[str, Any],
            StateBackedRecoveryEnvironment,
            bool,
        ]
    ] = []
    for action in task["oracle_actions"]:
        environment = StateBackedRecoveryEnvironment(task)
        valid = True
        for call in action["tool_calls"]:
            if not environment.execute_tool(
                call["name"], call.get("arguments", {})
            ).ok:
                valid = False
                break
        passed, _ = check_v06_constraints(task, environment)
        evaluated.append((action, environment, bool(valid and passed)))
    feasible = [item for item in evaluated if item[2]]
    if not feasible:
        return []
    if strategy in {"sticker_price", "global_cost"}:
        selected = min(
            feasible,
            key=lambda item: sum(
                record["paid_value"]
                for records in item[1].active_options_by_slot().values()
                for record in records
            ),
        )
        return deepcopy(selected[0]["tool_calls"])
    if strategy == "refund_only":
        selected = min(
            feasible,
            key=lambda item: (
                -sum(entry["refund"] for entry in item[1].ledger),
                item[1].state_changing_actions,
            ),
        )
        return deepcopy(selected[0]["tool_calls"])
    raise ValueError(f"Unknown v0.6 baseline strategy: {strategy}")


def _v06_action(task: dict[str, Any], action_id: str) -> dict[str, Any]:
    return next(
        item for item in task["oracle_actions"] if item["action_id"] == action_id
    )


def _v06_full_rollback(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Cancel every boundary commitment, rebuild it, then repair the gap."""
    calls: list[dict[str, Any]] = []
    boundary = task["boundary_commitments"]
    if task["domain"] == "travel":
        state = task["failure_snapshot"]["state_bench"]
        booking_ids = {item["booking_id"] for item in state["bookings"]}
        hotel_ids = {item["reservation_id"] for item in state["hotels"]}
        car_ids = {item["rental_id"] for item in state["car_rentals"]}
        prefix_by_option = {
            step["arguments"].get("flight_id")
            or step["arguments"].get("hotel_id")
            or step["arguments"].get("car_id")
            or step["arguments"].get("option_id"): step
            for step in task["pre_failure_trace"]
        }
        for item in boundary:
            entity_id = item["entity_id"]
            if entity_id in booking_ids:
                tool, key = "cancel_booking", "booking_id"
            elif entity_id in hotel_ids:
                tool, key = "cancel_hotel_reservation", "reservation_id"
            elif entity_id in car_ids:
                tool, key = "cancel_car_rental", "rental_id"
            else:
                tool, key = "cancel_local_service", "service_id"
            calls.extend(
                [
                    {"name": tool, "arguments": {key: entity_id}},
                    {
                        "name": tool,
                        "arguments": {key: entity_id, "confirm": True},
                    },
                ]
            )
        for item in boundary:
            prefix = prefix_by_option[item["option_id"]]
            calls.append(
                {
                    "name": prefix["tool"],
                    "arguments": deepcopy(prefix["arguments"]),
                }
            )
    else:
        item_to_order = {
            item["item_id"]: item["order_id"]
            for item in task["failure_snapshot"]["state_bench"]["order_items"]
        }
        calls.append(
            {"name": "get_policies", "arguments": {"topic": "cancellation"}}
        )
        for item in boundary:
            order_id = item_to_order[item["entity_id"]]
            calls.extend(
                [
                    {"name": "cancel_order", "arguments": {"order_id": order_id}},
                    {
                        "name": "cancel_order",
                        "arguments": {"order_id": order_id, "confirm": True},
                    },
                ]
            )
        customer_id = task["pre_failure_trace"][0]["arguments"]["customer_id"]
        calls.extend(
            {
                "name": "purchase_product",
                "arguments": {
                    "customer_id": customer_id,
                    "product_id": item["option_id"],
                },
            }
            for item in boundary
        )
    calls.extend(deepcopy(_v06_action(task, "local-repair")["tool_calls"]))
    return calls


def _local_repair(task: dict[str, Any]) -> list[dict[str, Any]]:
    active_slots = {
        item["slot"]
        for item in task["failure_snapshot"]["commitments"]
        if item["status"] == "confirmed"
    }
    actions: list[dict[str, Any]] = []
    for slot in task["required_slots"]:
        if slot in active_slots:
            continue
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.extend(_completion_actions(task))
    return actions


def _full_rollback(task: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "cancel",
            "args": {"commitment_id": item["commitment_id"]},
        }
        for item in task["failure_snapshot"]["commitments"]
        if item["status"] == "confirmed"
    ]
    for slot in task["required_slots"]:
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.extend(_completion_actions(task))
    return actions


def _dependency_repair(task: dict[str, Any]) -> list[dict[str, Any]]:
    affected = set(task.get("failure", {}).get("affected_slots", []))
    actions: list[dict[str, Any]] = []
    active_slots: set[str] = set()
    for item in task["failure_snapshot"]["commitments"]:
        if item["status"] != "confirmed":
            continue
        if item["slot"] in affected:
            actions.append(
                {
                    "action": "cancel",
                    "args": {"commitment_id": item["commitment_id"]},
                }
            )
        else:
            active_slots.add(item["slot"])
    for slot in task["required_slots"]:
        if slot in active_slots:
            continue
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.extend(_completion_actions(task))
    return actions


def _completion_actions(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep the legacy pilot protocol without adding it to v0.5 traces."""
    if task["schema_version"] == "0.5":
        return []
    return [{"action": "finish", "args": {}}]


def _cheapest_available(
    task: dict[str, Any], slot: str
) -> dict[str, Any] | None:
    options = [
        option
        for option in task["catalog"]
        if option["slot"] == slot and option.get("available", False)
    ]
    return min(options, key=lambda option: option["price"]) if options else None
