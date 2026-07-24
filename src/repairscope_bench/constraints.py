from __future__ import annotations

from typing import Any

from .environment import RepairEnvironment


def check_constraints(
    task: dict[str, Any], environment: RepairEnvironment
) -> tuple[bool, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    active_by_slot = {
        slot: environment.active_commitments(slot) for slot in task["required_slots"]
    }

    for slot, commitments in active_by_slot.items():
        if len(commitments) != 1:
            failures.append(
                {
                    "type": "exactly_one_active",
                    "slot": slot,
                    "observed": len(commitments),
                }
            )

    for constraint in task["constraints"]:
        kind = constraint["type"]
        if kind == "slot_attribute":
            slot = constraint["slot"]
            commitments = active_by_slot.get(slot, [])
            if len(commitments) != 1:
                continue
            observed = commitments[0].get("attributes", {}).get(
                constraint["attribute"]
            )
            if not _compare(observed, constraint["op"], constraint["value"]):
                failures.append(
                    {
                        "type": kind,
                        "slot": slot,
                        "attribute": constraint["attribute"],
                        "op": constraint["op"],
                        "expected": constraint["value"],
                        "observed": observed,
                    }
                )
        elif kind == "allowed_pairs":
            left = active_by_slot.get(constraint["left_slot"], [])
            right = active_by_slot.get(constraint["right_slot"], [])
            if len(left) != 1 or len(right) != 1:
                continue
            observed_pair = [left[0]["option_id"], right[0]["option_id"]]
            if observed_pair not in constraint["pairs"]:
                failures.append(
                    {
                        "type": kind,
                        "left_slot": constraint["left_slot"],
                        "right_slot": constraint["right_slot"],
                        "observed": observed_pair,
                    }
                )
        elif kind == "max_lifecycle_cost":
            if environment.lifecycle_cost > constraint["value"]:
                failures.append(
                    {
                        "type": kind,
                        "expected_max": constraint["value"],
                        "observed": environment.lifecycle_cost,
                    }
                )
        else:
            failures.append({"type": "unknown_constraint", "constraint": constraint})

    return not failures, failures


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

