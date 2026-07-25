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

V1_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "scenario_id",
    "counterfactual_pair_id",
    "variant_role",
    "domain",
    "environment_type",
    "reasoning_structure",
    "economic_carriers",
    "difficulty_level",
    "split",
    "instruction",
    "initial_snapshot",
    "initial_snapshot_sha256",
    "failure_snapshot",
    "snapshot_sha256",
    "pre_failure_trace",
    "prefix_ledger",
    "latest_failure",
    "boundary_commitments",
    "inventory",
    "contracts",
    "compatibility_rules",
    "hard_goals",
    "changed_fact",
    "construction",
    "max_turns",
}

V11_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
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
    "boundary_commitments",
    "inventory",
    "contracts",
    "compatibility_rules",
    "hard_goals",
    "construction",
    "max_turns",
}

V2_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
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
    "boundary_commitments",
    "inventory",
    "policies",
    "contracts",
    "compatibility_rules",
    "hard_goals",
    "construction",
    "max_turns",
}

V3_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "domain",
    "environment_type",
    "split",
    "now",
    "actor_id",
    "instruction",
    "initial_snapshot",
    "initial_snapshot_sha256",
    "failure_snapshot",
    "snapshot_sha256",
    "pre_failure_trace",
    "prefix_ledger",
    "latest_failure",
    "boundary_commitments",
    "option_metadata",
    "economic_terms",
    "compatibility_rules",
    "hard_goals",
    "price_profile",
    "source",
    "construction",
    "max_turns",
}


class TaskValidationError(ValueError):
    """Raised when a benchmark task violates the public schema."""


def validate_task(task: dict[str, Any]) -> None:
    if task.get("schema_version") == "3.0":
        _validate_v3_task(task)
        return
    if task.get("schema_version") == "2.0":
        _validate_v2_task(task)
        return
    if task.get("schema_version") == "1.1":
        _validate_v11_task(task)
        return
    if task.get("schema_version") == "1.0":
        _validate_v1_task(task)
        return
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


def _validate_v1_task(task: dict[str, Any]) -> None:
    from .v1_environment import DOMAIN_TOOL_NAMES, snapshot_hash

    missing = V1_REQUIRED_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing v1 fields "
            f"{sorted(missing)}"
        )
    if task["domain"] not in DOMAIN_TOOL_NAMES:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v1 domain {task['domain']!r}"
        )
    if task["max_turns"] != 15:
        raise TaskValidationError(
            f"{task['task_id']}: v1 requires exactly 15 turns"
        )
    if task["variant_role"] not in {"alpha", "beta"}:
        raise TaskValidationError(
            f"{task['task_id']}: invalid counterfactual role"
        )
    if task["difficulty_level"] not in {1, 2, 3, 4}:
        raise TaskValidationError(
            f"{task['task_id']}: invalid difficulty level"
        )
    if snapshot_hash(task["failure_snapshot"]) != task["snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: failure snapshot hash mismatch"
        )
    if snapshot_hash(task["initial_snapshot"]) != task["initial_snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: initial snapshot hash mismatch"
        )
    if len(task["boundary_commitments"]) < 4:
        raise TaskValidationError(
            f"{task['task_id']}: fewer than four persistent commitments"
        )
    if len(task["pre_failure_trace"]) != len(task["boundary_commitments"]):
        raise TaskValidationError(
            f"{task['task_id']}: prefix writes do not match commitments"
        )
    if any(
        not step.get("result", {}).get("ok", False)
        for step in task["pre_failure_trace"]
    ):
        raise TaskValidationError(
            f"{task['task_id']}: prefix contains a failed write"
        )
    if task["latest_failure"].get("result", {}).get("ok", True):
        raise TaskValidationError(
            f"{task['task_id']}: latest operation is not a real failure"
        )
    if not task["construction"].get("necessary_action_order_invariant", False):
        raise TaskValidationError(
            f"{task['task_id']}: sequence-dependent gold is forbidden"
        )
    if "oracle_actions" in task or "candidate_scopes" in task:
        raise TaskValidationError(
            f"{task['task_id']}: author-specified Oracle macros are forbidden"
        )
    option_ids = [item["option_id"] for item in task["inventory"]]
    if len(option_ids) != len(set(option_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate option ID")
    boundary_ids = [item["entity_id"] for item in task["boundary_commitments"]]
    if len(boundary_ids) != len(set(boundary_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate boundary ID")
    for item in task["inventory"]:
        integer_fields = [
            item["upfront_cents"],
            item.get("monthly_cents", 0),
            item.get("horizon_months", 0),
            item.get("refund_after_purchase_cents", 0),
        ]
        if any(not isinstance(value, int) or value < 0 for value in integer_fields):
            raise TaskValidationError(
                f"{task['task_id']}: prices must be non-negative integer cents"
            )
        if not item.get("provides"):
            raise TaskValidationError(
                f"{task['task_id']}: option provides no capability"
            )
    known_boundary = set(boundary_ids)
    contract_ids: set[str] = set()
    for contract in task["contracts"]:
        if contract["contract_id"] in contract_ids:
            raise TaskValidationError(
                f"{task['task_id']}: duplicate contract ID"
            )
        contract_ids.add(contract["contract_id"])
        if not set(contract["trigger"].get("entity_ids", [])).issubset(
            known_boundary
        ):
            raise TaskValidationError(
                f"{task['task_id']}: contract references unknown commitment"
            )
        if contract["trigger"]["type"] not in {
            "any_changed",
            "all_changed",
            "changed_count_at_least",
            "retained_paid_below",
        }:
            raise TaskValidationError(
                f"{task['task_id']}: unsupported contract trigger"
            )
        if not isinstance(contract["charge_cents"], int) or contract["charge_cents"] < 0:
            raise TaskValidationError(
                f"{task['task_id']}: invalid contract charge"
            )


def _validate_v11_task(task: dict[str, Any]) -> None:
    from .v1_environment import DOMAIN_TOOL_NAMES, snapshot_hash

    missing = V11_REQUIRED_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing v1.1 fields "
            f"{sorted(missing)}"
        )
    forbidden_public_metadata = {
        "variant_role",
        "changed_fact",
        "frontier_profile",
        "reasoning_structure",
        "counterfactual_pair_id",
        "pair_id",
    }
    leaked = forbidden_public_metadata.intersection(task)
    if leaked:
        raise TaskValidationError(
            f"{task['task_id']}: private benchmark metadata leaked into public "
            f"task: {sorted(leaked)}"
        )
    if task["domain"] not in DOMAIN_TOOL_NAMES:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v1.1 domain {task['domain']!r}"
        )
    if task["max_turns"] != 15:
        raise TaskValidationError(
            f"{task['task_id']}: v1.1 requires exactly 15 turns"
        )
    if snapshot_hash(task["failure_snapshot"]) != task["snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: failure snapshot hash mismatch"
        )
    if snapshot_hash(task["initial_snapshot"]) != task["initial_snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: initial snapshot hash mismatch"
        )
    if not 2 <= len(task["boundary_commitments"]) <= 8:
        raise TaskValidationError(
            f"{task['task_id']}: expected 2-8 persistent commitments"
        )
    if len(task["pre_failure_trace"]) != len(task["boundary_commitments"]):
        raise TaskValidationError(
            f"{task['task_id']}: prefix writes do not match commitments"
        )
    if any(
        not step.get("result", {}).get("ok", False)
        for step in task["pre_failure_trace"]
    ):
        raise TaskValidationError(
            f"{task['task_id']}: prefix contains a failed write"
        )
    if task["latest_failure"].get("result", {}).get("ok", True):
        raise TaskValidationError(
            f"{task['task_id']}: latest operation is not a real failure"
        )
    construction = task["construction"]
    required_construction = {
        "prefix_generated_by_public_tools",
        "failure_generated_by_public_tool",
        "necessary_action_order_invariant",
    }
    if not all(construction.get(key, False) for key in required_construction):
        raise TaskValidationError(
            f"{task['task_id']}: v1.1 construction proof is incomplete"
        )
    if "oracle_actions" in task or "candidate_scopes" in task:
        raise TaskValidationError(
            f"{task['task_id']}: author-specified Oracle macros are forbidden"
        )
    option_ids = [item["option_id"] for item in task["inventory"]]
    if len(option_ids) != len(set(option_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate option ID")
    boundary_ids = [item["entity_id"] for item in task["boundary_commitments"]]
    if len(boundary_ids) != len(set(boundary_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate boundary ID")
    for item in task["inventory"]:
        amounts = [
            item["upfront_cents"],
            item.get("monthly_cents", 0),
            item.get("horizon_months", 0),
            item.get("refund_after_purchase_cents", 0),
        ]
        if any(not isinstance(value, int) or value < 0 for value in amounts):
            raise TaskValidationError(
                f"{task['task_id']}: prices must be non-negative integer cents"
            )
        if not item.get("provides"):
            raise TaskValidationError(
                f"{task['task_id']}: option provides no capability"
            )
    supported_rules = {
        "forbid_pair",
        "requires_all",
        "requires_any",
        "requires_bridge",
    }
    for rule in task["compatibility_rules"]:
        if rule.get("type") not in supported_rules:
            raise TaskValidationError(
                f"{task['task_id']}: unsupported compatibility rule "
                f"{rule.get('type')!r}"
            )
    supported_triggers = {
        "any_changed",
        "all_changed",
        "changed_count_at_least",
        "retained_paid_below",
        "retained_quantity_below",
        "changed_with_retained",
        "active_any",
    }
    known_boundary = set(boundary_ids)
    contract_ids: set[str] = set()
    for contract in task["contracts"]:
        if contract["contract_id"] in contract_ids:
            raise TaskValidationError(
                f"{task['task_id']}: duplicate contract ID"
            )
        contract_ids.add(contract["contract_id"])
        trigger = contract["trigger"]
        referenced = set(trigger.get("entity_ids", []))
        referenced.update(trigger.get("changed_entity_ids", []))
        referenced.update(trigger.get("retained_entity_ids", []))
        if not referenced.issubset(known_boundary):
            raise TaskValidationError(
                f"{task['task_id']}: contract references unknown commitment"
            )
        if trigger.get("type") not in supported_triggers:
            raise TaskValidationError(
                f"{task['task_id']}: unsupported contract trigger"
            )
        referenced_options = set(trigger.get("option_ids", []))
        known_options = {
            item["option_id"] for item in task["inventory"]
        }
        if not referenced_options.issubset(known_options):
            raise TaskValidationError(
                f"{task['task_id']}: contract references unknown option"
            )
        if not isinstance(contract["charge_cents"], int) or contract["charge_cents"] < 0:
            raise TaskValidationError(
                f"{task['task_id']}: invalid contract charge"
            )


def load_task(path: str | Path) -> dict[str, Any]:
    task_path = Path(path)
    with task_path.open("r", encoding="utf-8") as handle:
        task = json.load(handle)
    validate_task(task)
    task["_path"] = str(task_path.resolve())
    if task.get("schema_version") == "3.0":
        _attach_versioned_metadata(task, task_path, "v3")
    elif task.get("schema_version") == "2.0":
        _attach_versioned_metadata(task, task_path, "v2")
    elif task.get("schema_version") == "1.1":
        _attach_v11_metadata(task, task_path)
    return task


def load_tasks(path: str | Path) -> list[dict[str, Any]]:
    root = Path(path)
    if root.is_file():
        paths = [root]
    elif (root / "dev").is_dir() and (root / "test").is_dir():
        paths = sorted((root / "dev").glob("*.json")) + sorted(
            (root / "test").glob("*.json")
        )
    else:
        paths = sorted(root.glob("*.json"))
    return [load_task(item) for item in paths]


_V11_GOLD_CACHE: dict[Path, dict[str, Any]] = {}


def _attach_v11_metadata(task: dict[str, Any], task_path: Path) -> None:
    candidates = [
        task_path.parent.parent / "gold" / "v11.json",
        task_path.parent / "v11.gold.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        if resolved not in _V11_GOLD_CACHE:
            with resolved.open("r", encoding="utf-8") as handle:
                _V11_GOLD_CACHE[resolved] = json.load(handle)
        record = _V11_GOLD_CACHE[resolved].get(task["task_id"])
        if record is not None:
            task["_benchmark_metadata"] = record.get("metadata", {})
        return


def _attach_versioned_metadata(
    task: dict[str, Any], task_path: Path, version: str
) -> None:
    candidates = [
        task_path.parent.parent / "gold" / f"{version}.json",
        task_path.parent.parent.parent / "gold" / f"{version}.json",
        task_path.parent.parent.parent.parent / "gold" / f"{version}.json",
        task_path.parent / f"{version}.gold.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        if resolved not in _V11_GOLD_CACHE:
            with resolved.open("r", encoding="utf-8") as handle:
                _V11_GOLD_CACHE[resolved] = json.load(handle)
        record = _V11_GOLD_CACHE[resolved].get(task["task_id"])
        if record is not None:
            task["_benchmark_metadata"] = record.get("metadata", {})
            if version in {"v2", "v3"}:
                task["_benchmark_gold"] = record
        return


def _validate_v3_task(task: dict[str, Any]) -> None:
    from .v3_environment import snapshot_hash, term_charge_minor, term_credit_minor

    missing = V3_REQUIRED_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing v3 fields "
            f"{sorted(missing)}"
        )
    if task["domain"] not in {"travel", "after_sales"}:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v3 domain {task['domain']!r}"
        )
    if task["split"] not in {"dev", "test"}:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v3 split {task['split']!r}"
        )
    if task["max_turns"] != 15:
        raise TaskValidationError(
            f"{task['task_id']}: v3 requires exactly 15 turns"
        )
    if snapshot_hash(task["initial_snapshot"]) != task["initial_snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: initial snapshot hash mismatch"
        )
    if snapshot_hash(task["failure_snapshot"]) != task["snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: failure snapshot hash mismatch"
        )
    if task["source"].get("commit") != (
        "4efcbf2d4fe60df04878859b692d9391f3d5b33a"
    ):
        raise TaskValidationError(
            f"{task['task_id']}: STATE-Bench dependency is not pinned"
        )
    if len(task["boundary_commitments"]) != 4:
        raise TaskValidationError(
            f"{task['task_id']}: v3 requires four persistent commitments"
        )
    if len(task["pre_failure_trace"]) != 4 or any(
        not item.get("result", {}).get("ok", False)
        for item in task["pre_failure_trace"]
    ):
        raise TaskValidationError(
            f"{task['task_id']}: prefix must contain four successful writes"
        )
    if task["latest_failure"].get("result", {}).get("ok", True):
        raise TaskValidationError(
            f"{task['task_id']}: latest operation must be a real failure"
        )
    if not task["prefix_ledger"]:
        raise TaskValidationError(
            f"{task['task_id']}: missing auditable prefix ledger"
        )
    if not task["construction"].get("necessary_action_order_invariant", False):
        raise TaskValidationError(
            f"{task['task_id']}: order-dependent gold is forbidden"
        )
    if task["construction"].get("currency") != "USD":
        raise TaskValidationError(
            f"{task['task_id']}: v3 uses a single USD currency"
        )
    forbidden = {"irreversible_loss", "net_recovery_outlay", "gap_min"}
    serialized = json.dumps(task, ensure_ascii=False)
    if any(token in serialized for token in forbidden):
        raise TaskValidationError(
            f"{task['task_id']}: deprecated or hidden economic field present"
        )

    entity_ids = [
        item["entity_id"] for item in task["boundary_commitments"]
    ]
    if len(entity_ids) != len(set(entity_ids)):
        raise TaskValidationError(
            f"{task['task_id']}: duplicate boundary entity"
        )
    option_ids = set(task["option_metadata"])
    if not option_ids:
        raise TaskValidationError(f"{task['task_id']}: empty option metadata")
    for option_id, item in task["option_metadata"].items():
        required = {
            "name",
            "slot",
            "native_kind",
            "available",
            "candidate",
            "upfront_minor",
            "monthly_minor",
            "horizon_months",
            "total_charge_minor",
            "post_purchase_cancel_fee_minor",
            "provides",
            "attributes",
        }
        if required - item.keys():
            raise TaskValidationError(
                f"{task['task_id']}: incomplete option {option_id}"
            )
        money_fields = [
            item["upfront_minor"],
            item["monthly_minor"],
            item["total_charge_minor"],
        ]
        if any(
            not isinstance(value, int) or value < 0
            for value in money_fields
        ):
            raise TaskValidationError(
                f"{task['task_id']}: prices must be integer minor units"
            )
    for item in task["boundary_commitments"]:
        if item["option_id"] not in option_ids:
            raise TaskValidationError(
                f"{task['task_id']}: unknown boundary option"
            )
        if any(
            not isinstance(item[key], int) or item[key] < 0
            for key in ("paid_minor", "refund_minor")
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid boundary money"
            )
        if item["refund_minor"] > item["paid_minor"]:
            raise TaskValidationError(
                f"{task['task_id']}: refund exceeds amount paid"
            )
    term_ids: set[str] = set()
    for term in task["economic_terms"]:
        if term["term_id"] in term_ids:
            raise TaskValidationError(
                f"{task['task_id']}: duplicate economic term"
            )
        term_ids.add(term["term_id"])
        if term_charge_minor(term) < 0 or term_credit_minor(term) < 0:
            raise TaskValidationError(
                f"{task['task_id']}: negative term amount"
            )
        if not set(term.get("linked_entity_ids", [])).issubset(
            set(entity_ids)
        ):
            raise TaskValidationError(
                f"{task['task_id']}: term references unknown entity"
            )
        if not set(term.get("linked_option_ids", [])).issubset(option_ids):
            raise TaskValidationError(
                f"{task['task_id']}: term references unknown option"
            )
    constraint_ids: set[str] = set()
    for item in task["hard_goals"]["capabilities"] + task["hard_goals"].get(
        "attributes", []
    ) + task["compatibility_rules"]:
        constraint_id = item.get("constraint_id")
        if not constraint_id or constraint_id in constraint_ids:
            raise TaskValidationError(
                f"{task['task_id']}: missing or duplicate constraint ID"
            )
        constraint_ids.add(constraint_id)
        if not item.get("evidence_refs"):
            raise TaskValidationError(
                f"{task['task_id']}: constraint {constraint_id} has no evidence reference"
            )


def _validate_v2_task(task: dict[str, Any]) -> None:
    from .v2_environment import DOMAIN_INTERFACES, snapshot_hash

    missing = V2_REQUIRED_FIELDS - task.keys()
    if missing:
        raise TaskValidationError(
            f"{task.get('task_id', '<unknown>')}: missing v2 fields "
            f"{sorted(missing)}"
        )
    if task["domain"] not in DOMAIN_INTERFACES:
        raise TaskValidationError(
            f"{task['task_id']}: unsupported v2 domain {task['domain']!r}"
        )
    if task["max_turns"] != 15:
        raise TaskValidationError(
            f"{task['task_id']}: v2 requires exactly 15 turns"
        )
    if snapshot_hash(task["initial_snapshot"]) != task["initial_snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: initial snapshot hash mismatch"
        )
    if snapshot_hash(task["failure_snapshot"]) != task["snapshot_sha256"]:
        raise TaskValidationError(
            f"{task['task_id']}: failure snapshot hash mismatch"
        )
    if len(task["boundary_commitments"]) < 4:
        raise TaskValidationError(
            f"{task['task_id']}: v2 pilot requires at least four commitments"
        )
    if len(task["pre_failure_trace"]) != len(task["boundary_commitments"]):
        raise TaskValidationError(
            f"{task['task_id']}: prefix writes do not match commitments"
        )
    if any(
        not item.get("result", {}).get("ok", False)
        for item in task["pre_failure_trace"]
    ):
        raise TaskValidationError(
            f"{task['task_id']}: prefix contains a failed write"
        )
    if task["latest_failure"].get("result", {}).get("ok", True):
        raise TaskValidationError(
            f"{task['task_id']}: latest operation must be a real failure"
        )
    if not task["construction"].get("necessary_action_order_invariant", False):
        raise TaskValidationError(
            f"{task['task_id']}: sequence-dependent economics are forbidden"
        )

    policy_ids = [item["policy_id"] for item in task["policies"]]
    if len(policy_ids) != len(set(policy_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate policy ID")
    known_policies = set(policy_ids)
    option_ids = [item["option_id"] for item in task["inventory"]]
    if len(option_ids) != len(set(option_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate option ID")
    boundary_ids = [item["entity_id"] for item in task["boundary_commitments"]]
    if len(boundary_ids) != len(set(boundary_ids)):
        raise TaskValidationError(f"{task['task_id']}: duplicate boundary ID")

    forbidden_tokens = {
        "local",
        "bridge",
        "decoy",
        "wrong-site",
        "late",
        "failed",
        "dominated",
        "alt1",
        "alt2",
        "alt3",
    }
    for item in task["inventory"]:
        policy_id = item.get("refund_policy_id")
        if policy_id is not None and policy_id not in known_policies:
            raise TaskValidationError(
                f"{task['task_id']}: unknown option refund policy"
            )
        exposed = f"{item['option_id']} {item.get('name', '')}".lower()
        if any(token in exposed for token in forbidden_tokens):
            raise TaskValidationError(
                f"{task['task_id']}: answer-revealing option label"
            )
        if any(
            not isinstance(value, int) or value < 0
            for value in [
                item["upfront_cents"],
                item.get("monthly_cents", 0),
                item.get("horizon_months", 0),
            ]
        ):
            raise TaskValidationError(
                f"{task['task_id']}: invalid option price"
            )
    for item in task["failure_snapshot"]["commitments"]:
        if item["refund_policy_id"] not in known_policies:
            raise TaskValidationError(
                f"{task['task_id']}: unknown commitment refund policy"
            )
    if {
        item["entity_id"] for item in task["failure_snapshot"]["commitments"]
    } != set(boundary_ids):
        raise TaskValidationError(
            f"{task['task_id']}: boundary and failure snapshot disagree"
        )
