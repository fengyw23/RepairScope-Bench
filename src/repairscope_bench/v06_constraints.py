from __future__ import annotations

from typing import Any

from .v06_environment import StateBackedRecoveryEnvironment


def check_v06_constraints(
    task: dict[str, Any],
    environment: StateBackedRecoveryEnvironment,
) -> tuple[bool, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    active = environment.active_options_by_slot()

    for slot in task["required_slots"]:
        observed = len(active.get(slot, []))
        if observed != 1:
            failures.append(
                {
                    "type": "exactly_one_active",
                    "slot": slot,
                    "expected": 1,
                    "observed": observed,
                }
            )

    for constraint in task["hard_constraints"]:
        kind = constraint["type"]
        if kind == "slot_attribute":
            records = active.get(constraint["slot"], [])
            if len(records) != 1:
                continue
            observed = records[0]["attributes"].get(constraint["attribute"])
            if not _compare(observed, constraint["op"], constraint["value"]):
                failures.append(
                    {
                        "type": kind,
                        "slot": constraint["slot"],
                        "attribute": constraint["attribute"],
                        "expected": constraint["value"],
                        "op": constraint["op"],
                        "observed": observed,
                    }
                )
        elif kind == "allowed_pairs":
            left = active.get(constraint["left_slot"], [])
            right = active.get(constraint["right_slot"], [])
            if len(left) != 1 or len(right) != 1:
                continue
            pair = [left[0]["option_id"], right[0]["option_id"]]
            if pair not in constraint["pairs"]:
                failures.append(
                    {
                        "type": kind,
                        "left_slot": constraint["left_slot"],
                        "right_slot": constraint["right_slot"],
                        "observed": pair,
                    }
                )
        elif kind == "max_active_total":
            total = sum(
                record["paid_value"]
                for records in active.values()
                for record in records
            )
            if total > constraint["value"]:
                failures.append(
                    {
                        "type": kind,
                        "expected_max": constraint["value"],
                        "observed": total,
                    }
                )
        elif kind == "forbid_option":
            observed = [
                record["option_id"]
                for records in active.values()
                for record in records
                if record["option_id"] == constraint["option_id"]
            ]
            if observed:
                failures.append(
                    {
                        "type": kind,
                        "option_id": constraint["option_id"],
                    }
                )
        else:
            failures.append(
                {"type": "unknown_constraint", "constraint": constraint}
            )

    if environment.policy_violations:
        failures.extend(
            {
                "type": "policy_violation",
                **violation,
            }
            for violation in environment.policy_violations
        )
    failures.extend(
        {"type": "integrity_violation", **violation}
        for violation in environment.integrity_violations()
    )
    if environment.irreversible_loss < 0:
        failures.append(
            {
                "type": "negative_irreversible_loss",
                "observed": environment.irreversible_loss,
            }
        )
    return not failures, failures


def constraint_is_effective(
    task: dict[str, Any], constraint: dict[str, Any]
) -> bool:
    metadata = task.get("option_metadata", {})
    if constraint["type"] == "slot_attribute":
        candidates = [
            item
            for item in metadata.values()
            if item.get("slot") == constraint["slot"]
            and item.get("available", True)
        ]
        return any(
            not _compare(
                item.get("attributes", {}).get(constraint["attribute"]),
                constraint["op"],
                constraint["value"],
            )
            for item in candidates
        )
    if constraint["type"] == "allowed_pairs":
        left = [
            option_id
            for option_id, item in metadata.items()
            if item.get("slot") == constraint["left_slot"]
            and item.get("available", True)
        ]
        right = [
            option_id
            for option_id, item in metadata.items()
            if item.get("slot") == constraint["right_slot"]
            and item.get("available", True)
        ]
        return any([a, b] not in constraint["pairs"] for a in left for b in right)
    if constraint["type"] == "max_active_total":
        return True
    if constraint["type"] == "forbid_option":
        return constraint["option_id"] in metadata
    return False


def _compare(observed: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return observed == expected
    if op == "ne":
        return observed != expected
    if op == "le":
        return observed is not None and observed <= expected
    if op == "lt":
        return observed is not None and observed < expected
    if op == "ge":
        return observed is not None and observed >= expected
    if op == "gt":
        return observed is not None and observed > expected
    if op == "in":
        return observed in expected
    raise ValueError(f"Unsupported comparison operator: {op}")
