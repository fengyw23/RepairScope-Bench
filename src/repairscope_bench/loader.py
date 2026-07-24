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

V06_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "family_id",
    "variant_id",
    "counterfactual_pair_id",
    "domain",
    "environment_type",
    "split",
    "now",
    "instruction",
    "initial_snapshot",
    "initial_snapshot_sha256",
    "failure_snapshot",
    "snapshot_sha256",
    "pre_failure_trace",
    "prefix_ledger",
    "latest_failure",
    "option_metadata",
    "boundary_commitments",
    "contracts",
    "required_slots",
    "hard_constraints",
    "compatibility_rules",
    "oracle_actions",
    "candidate_scopes",
    "max_turns",
}


class TaskValidationError(ValueError):
    """Raised when a benchmark task violates the public schema."""


def validate_task(task: dict[str, Any]) -> None:
    if task.get("schema_version") == "0.6":
        _validate_v06_task(task)
        return
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


def _validate_v06_task(task: dict[str, Any]) -> None:
    from .v06_constraints import constraint_is_effective
    from .v06_environment import snapshot_hash

    missing = V06_REQUIRED_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing v0.6 fields "
            f"{sorted(missing)}"
        )
    if task["domain"] not in {"travel", "customer_support"}:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v0.6 domain {task['domain']!r}"
        )
    if task["max_turns"] != 15:
        raise TaskValidationError(
            f"{task['task_id']}: the v0.6 protocol requires exactly 15 turns"
        )
    if snapshot_hash(task["failure_snapshot"]) != task["snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: failure snapshot hash mismatch"
        )
    if snapshot_hash(task["initial_snapshot"]) != task["initial_snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: initial snapshot hash mismatch"
        )
    if not task["required_slots"]:
        raise TaskValidationError(
            f"{task['task_id']}: required_slots cannot be empty"
        )
    boundary_ids = [
        item["entity_id"] for item in task["boundary_commitments"]
    ]
    if len(boundary_ids) != len(set(boundary_ids)):
        raise TaskValidationError(
            f"{task['task_id']}: duplicate boundary entity"
        )
    if len(task["boundary_commitments"]) < 3:
        raise TaskValidationError(
            f"{task['task_id']}: too few persistent prefix commitments"
        )
    if not task["pre_failure_trace"] or any(
        not step.get("result", {}).get("ok", False)
        for step in task["pre_failure_trace"]
    ):
        raise TaskValidationError(
            f"{task['task_id']}: prefix trace must contain only successful calls"
        )
    if task["latest_failure"].get("result", {}).get("ok", True):
        raise TaskValidationError(
            f"{task['task_id']}: latest tool result must be a real failure"
        )
    if not task["prefix_ledger"]:
        raise TaskValidationError(
            f"{task['task_id']}: missing auditable prefix ledger"
        )
    for constraint in task["hard_constraints"]:
        if constraint["type"] not in {
            "slot_attribute",
            "allowed_pairs",
            "max_active_total",
            "forbid_option",
        }:
            raise TaskValidationError(
                f"{task['task_id']}: unsupported hard constraint "
                f"{constraint['type']!r}"
            )
        if not constraint_is_effective(task, constraint):
            raise TaskValidationError(
                f"{task['task_id']}: ineffective hard constraint {constraint!r}"
            )
    action_ids = [item["action_id"] for item in task["oracle_actions"]]
    if len(action_ids) != len(set(action_ids)) or len(action_ids) < 3:
        raise TaskValidationError(
            f"{task['task_id']}: expected at least three unique semantic actions"
        )
    forbidden_tools = {"finish", "get_cost_summary", "get_linked_loss_quote"}
    for action in task["oracle_actions"]:
        names = {call["name"] for call in action["tool_calls"]}
        if names & forbidden_tools:
            raise TaskValidationError(
                f"{task['task_id']}: oracle uses forbidden protocol tool "
                f"{sorted(names & forbidden_tools)}"
            )
    known_actions = set(action_ids)
    if len(task["candidate_scopes"]) < 3:
        raise TaskValidationError(
            f"{task['task_id']}: fewer than three candidate scopes"
        )
    for scope in task["candidate_scopes"]:
        if not set(scope["action_ids"]).issubset(known_actions):
            raise TaskValidationError(
                f"{task['task_id']}: candidate scope references unknown action"
            )
    contract_ids: set[str] = set()
    for contract in task["contracts"]:
        if contract["contract_id"] in contract_ids:
            raise TaskValidationError(
                f"{task['task_id']}: duplicate contract ID"
            )
        contract_ids.add(contract["contract_id"])
        if not set(contract["entity_ids"]).issubset(set(boundary_ids)):
            raise TaskValidationError(
                f"{task['task_id']}: contract references unknown boundary entity"
            )
        if not isinstance(contract.get("refund_adjustment", 0), (int, float)):
            raise TaskValidationError(
                f"{task['task_id']}: invalid refund adjustment"
            )
        if (
            not isinstance(contract.get("settlement_charge", 0), (int, float))
            or contract.get("settlement_charge", 0) < 0
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid settlement charge"
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
