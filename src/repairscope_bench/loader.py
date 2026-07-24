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
    "expected_oracle",
}


class TaskValidationError(ValueError):
    """Raised when a benchmark task violates the public schema."""


def validate_task(task: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_LEVEL_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing fields {sorted(missing)}"
        )
    if task["schema_version"] != "0.1":
        raise TaskValidationError(
            f"{task['task_id']}: unsupported schema_version {task['schema_version']!r}"
        )
    if not task["required_slots"]:
        raise TaskValidationError(f"{task['task_id']}: required_slots cannot be empty")

    commitments = task["failure_snapshot"].get("commitments", [])
    commitment_ids = [item["commitment_id"] for item in commitments]
    if len(commitment_ids) != len(set(commitment_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate commitment_id")
    option_ids = [item["option_id"] for item in task["catalog"]]
    if len(option_ids) != len(set(option_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate catalog option_id")

    active_by_slot: dict[str, int] = {}
    for commitment in commitments:
        if commitment.get("status") == "confirmed":
            slot = commitment["slot"]
            active_by_slot[slot] = active_by_slot.get(slot, 0) + 1
        paid = commitment["price_paid"]
        refund = commitment["refund_if_cancelled"]
        if paid < 0 or refund < 0 or refund > paid:
            raise TaskValidationError(
                f"{task['task_id']}: invalid paid/refund values for "
                f"{commitment['commitment_id']}"
            )
    duplicated_slots = [slot for slot, count in active_by_slot.items() if count > 1]
    if duplicated_slots:
        raise TaskValidationError(
            f"{task['task_id']}: multiple active commitments in slots {duplicated_slots}"
        )

    known_options = set(option_ids)
    known_options.update(item["option_id"] for item in commitments)
    for rule in task["modification_rules"]:
        if rule["to_option_id"] not in known_options:
            raise TaskValidationError(
                f"{task['task_id']}: modification target "
                f"{rule['to_option_id']} is unknown"
            )
        if rule["commitment_id"] not in commitment_ids:
            raise TaskValidationError(
                f"{task['task_id']}: modification source "
                f"{rule['commitment_id']} is unknown"
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

