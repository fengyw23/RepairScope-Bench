from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "task_id",
    "family_id",
    "variant_id",
    "domain",
    "instruction",
    "failure_observation",
    "pre_failure_trace",
    "failure_snapshot",
    "catalog",
    "modification_rules",
    "required_slots",
    "constraints",
    "objective",
}


class TaskValidationError(ValueError):
    """Raised when a benchmark task violates the public schema."""


def validate_task(task: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_LEVEL_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing fields {sorted(missing)}"
        )
    if task["schema_version"] not in {"0.4", "0.5"}:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported schema_version {task['schema_version']!r}"
        )
    if not task["required_slots"]:
        raise TaskValidationError(f"{task['task_id']}: required_slots cannot be empty")
    if task.get("max_mutations") is not None and (
        not isinstance(task["max_mutations"], int)
        or task["max_mutations"] <= 0
    ):
        raise TaskValidationError(
            f"{task['task_id']}: max_mutations must be a positive integer"
        )
    supported_terms = {
        "financial_cost",
        "financial_delta",
        "recovery_loss",
        "rollback_damage",
        "mutated_prior_commitments",
        "state_changing_actions",
    }
    terms = task["objective"].get("terms", [])
    if not terms or any(term not in supported_terms for term in terms):
        raise TaskValidationError(
            f"{task['task_id']}: unsupported or empty objective terms {terms}"
        )

    commitments = task["failure_snapshot"].get("commitments", [])
    commitment_ids = [item["commitment_id"] for item in commitments]
    if len(commitment_ids) != len(set(commitment_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate commitment_id")
    option_ids = [item["option_id"] for item in task["catalog"]]
    if len(option_ids) != len(set(option_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate catalog option_id")
    for option in task["catalog"]:
        price = option["price"]
        refund = option.get("refund_if_cancelled_after_booking", 0)
        if (
            not isinstance(price, (int, float))
            or not isinstance(refund, (int, float))
            or price < 0
            or refund < 0
            or refund > price
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid catalog price/refund for "
                f"{option['option_id']}"
            )

    active_by_slot: dict[str, int] = {}
    for commitment in commitments:
        if commitment.get("status") != "confirmed":
            raise TaskValidationError(
                f"{task['task_id']}: failure snapshot commitments must be confirmed"
            )
        if commitment.get("status") == "confirmed":
            slot = commitment["slot"]
            active_by_slot[slot] = active_by_slot.get(slot, 0) + 1
        paid = commitment["price_paid"]
        refund = commitment["refund_if_cancelled"]
        if (
            not isinstance(paid, (int, float))
            or not isinstance(refund, (int, float))
            or paid < 0
            or refund < 0
            or refund > paid
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid paid/refund values for "
                f"{commitment['commitment_id']}"
            )
    duplicated_slots = [slot for slot, count in active_by_slot.items() if count > 1]
    if duplicated_slots:
        raise TaskValidationError(
            f"{task['task_id']}: multiple active commitments in slots {duplicated_slots}"
        )

    required_slots = set(task["required_slots"])
    supported_ops = {"eq", "ne", "le", "lt", "ge", "gt", "in"}
    for constraint in task["constraints"]:
        kind = constraint.get("type")
        if kind == "slot_attribute":
            if constraint.get("slot") not in required_slots:
                raise TaskValidationError(
                    f"{task['task_id']}: constraint references a non-required slot"
                )
            if constraint.get("op") not in supported_ops:
                raise TaskValidationError(
                    f"{task['task_id']}: unsupported comparison operator"
                )
        elif kind == "allowed_pairs":
            if (
                constraint.get("left_slot") not in required_slots
                or constraint.get("right_slot") not in required_slots
                or not isinstance(constraint.get("pairs"), list)
            ):
                raise TaskValidationError(
                    f"{task['task_id']}: invalid allowed_pairs constraint"
                )
        elif kind == "max_lifecycle_cost":
            if not isinstance(constraint.get("value"), (int, float)):
                raise TaskValidationError(
                    f"{task['task_id']}: invalid lifecycle cost constraint"
                )
        else:
            raise TaskValidationError(
                f"{task['task_id']}: unknown constraint type {kind!r}"
            )

    for rule in task["modification_rules"]:
        if rule["to_option_id"] not in set(option_ids):
            raise TaskValidationError(
                f"{task['task_id']}: modification target "
                f"{rule['to_option_id']} is not in the catalog"
            )
        if rule["commitment_id"] not in commitment_ids:
            raise TaskValidationError(
                f"{task['task_id']}: modification source "
                f"{rule['commitment_id']} is unknown"
            )
        if "from_option_id" in rule:
            source = next(
                item
                for item in commitments
                if item["commitment_id"] == rule["commitment_id"]
            )
            if rule["from_option_id"] != source["option_id"]:
                raise TaskValidationError(
                    f"{task['task_id']}: invalid modification from_option_id"
                )
        source = next(
            item
            for item in commitments
            if item["commitment_id"] == rule["commitment_id"]
        )
        target = next(
            item for item in task["catalog"]
            if item["option_id"] == rule["to_option_id"]
        )
        if target["slot"] != source["slot"]:
            raise TaskValidationError(
                f"{task['task_id']}: modification changes slots"
            )
        components = rule.get("cash_components")
        net_cash = rule.get("net_cash_delta", 0)
        fee = rule.get("fee", 0)
        if (
            not isinstance(net_cash, (int, float))
            or not isinstance(fee, (int, float))
            or fee < 0
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid modification cash values"
            )
        if components is not None:
            if not isinstance(components, dict) or any(
                not isinstance(value, (int, float))
                for value in components.values()
            ):
                raise TaskValidationError(
                    f"{task['task_id']}: invalid modification cash components"
                )
            if sum(components.values()) != net_cash:
                raise TaskValidationError(
                    f"{task['task_id']}: modification cash components do not sum "
                    "to net_cash_delta"
                )

    known_commitments = set(commitment_ids)
    linked_rule_ids: set[str] = set()
    for rule in task.get("linked_loss_rules", []):
        if rule.get("rule_id") in linked_rule_ids:
            raise TaskValidationError(
                f"{task['task_id']}: duplicate linked loss rule_id"
            )
        linked_rule_ids.add(rule.get("rule_id"))
        if (
            not rule.get("rule_id")
            or rule.get("trigger", "any_changed") not in {"any_changed", "all_changed"}
            or not isinstance(rule.get("amount"), (int, float))
            or rule["amount"] < 0
            or not rule.get("description")
            or not set(rule.get("commitment_ids", [])).issubset(known_commitments)
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid linked loss rule {rule!r}"
            )

    if task["schema_version"] == "0.5":
        required_metadata = {
            "pair_id",
            "evaluation_track",
            "mechanism",
            "split",
            "challenge_requirements",
        }
        missing_metadata = required_metadata - task.keys()
        if missing_metadata:
            raise TaskValidationError(
                f"{task['task_id']}: missing v0.5 metadata "
                f"{sorted(missing_metadata)}"
            )
        if task["evaluation_track"] not in {"goal", "loss_aware"}:
            raise TaskValidationError(
                f"{task['task_id']}: invalid evaluation_track"
            )


def load_task(path: str | Path) -> dict[str, Any]:
    task_path = Path(path)
    with task_path.open("r", encoding="utf-8") as handle:
        task = json.load(handle)
    validate_task(task)
    task["_path"] = str(task_path.resolve())
    return task


def load_tasks(path: str | Path) -> list[dict[str, Any]]:
    root = Path(path)
    paths = [root] if root.is_file() else sorted(root.glob("*.json"))
    return [load_task(item) for item in paths]
