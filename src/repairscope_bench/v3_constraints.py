from __future__ import annotations

from typing import Any

from .v3_environment import NativeRecoveryEnvironmentV3, options_compatible


def check_v3_constraints(
    task: dict[str, Any],
    environment: NativeRecoveryEnvironmentV3,
) -> tuple[bool, list[dict[str, Any]]]:
    return check_active_records(task, environment.active_records())


def check_active_records(
    task: dict[str, Any],
    active: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    for record in active:
        for capability, quantity in record.get("provides", {}).items():
            totals[capability] = totals.get(capability, 0) + int(quantity)

    for requirement in task["hard_goals"]["capabilities"]:
        observed = totals.get(requirement["capability"], 0)
        minimum = int(requirement.get("min", 0))
        maximum = requirement.get("max")
        if observed < minimum or (
            maximum is not None and observed > int(maximum)
        ):
            failures.append(
                {
                    "constraint_id": requirement["constraint_id"],
                    "type": "capability_quantity",
                    "capability": requirement["capability"],
                    "minimum": minimum,
                    "maximum": maximum,
                    "observed": observed,
                }
            )

    for requirement in task["hard_goals"].get("attributes", []):
        providers = [
            record
            for record in active
            if int(
                record.get("provides", {}).get(
                    requirement["capability"], 0
                )
            )
            > 0
        ]
        if not providers or not all(
            _compare(
                record.get("attributes", {}).get(requirement["attribute"]),
                requirement["op"],
                requirement["value"],
            )
            for record in providers
        ):
            failures.append(
                {
                    "constraint_id": requirement["constraint_id"],
                    "type": "attribute",
                    "capability": requirement["capability"],
                    "attribute": requirement["attribute"],
                    "op": requirement["op"],
                    "expected": requirement["value"],
                    "observed": [
                        record.get("attributes", {}).get(
                            requirement["attribute"]
                        )
                        for record in providers
                    ],
                }
            )

    active_options = {record["option_id"] for record in active}
    for rule in task.get("compatibility_rules", []):
        kind = rule["type"]
        failed = False
        if kind == "forbid_pair":
            failed = set(rule["option_ids"]).issubset(active_options)
        elif kind == "requires_any":
            failed = (
                rule["if_option_id"] in active_options
                and not active_options.intersection(rule["any_option_ids"])
            )
        elif kind == "requires_all":
            failed = (
                rule["if_option_id"] in active_options
                and not set(rule["all_option_ids"]).issubset(active_options)
            )
        else:
            failures.append(
                {
                    "constraint_id": rule["constraint_id"],
                    "type": "unsupported_compatibility_rule",
                    "rule": rule,
                }
            )
            continue
        if failed:
            failures.append(
                {
                    "constraint_id": rule["constraint_id"],
                    "type": kind,
                    "rule": rule,
                }
            )

    option_ids = sorted(active_options)
    for index, left in enumerate(option_ids):
        for right in option_ids[index + 1 :]:
            if not options_compatible(task, left, right):
                rule_ids = [
                    item["constraint_id"]
                    for item in task.get("compatibility_rules", [])
                    if item["type"] == "forbid_pair"
                    and set(item["option_ids"]) == {left, right}
                ]
                if not any(
                    item.get("constraint_id") in rule_ids
                    for item in failures
                ):
                    failures.append(
                        {
                            "constraint_id": rule_ids[0]
                            if rule_ids
                            else "compatibility",
                            "type": "incompatible_pair",
                            "option_ids": [left, right],
                        }
                    )

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
    raise ValueError(f"Unsupported v3 comparison: {op}")


__all__ = ["check_active_records", "check_v3_constraints"]
