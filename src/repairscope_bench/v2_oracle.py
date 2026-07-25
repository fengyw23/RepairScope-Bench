from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import json
from typing import Any

from .v1_environment import EconomicVector
from .v2_environment import DOMAIN_INTERFACES, DomainRecoveryEnvironmentV2


@dataclass
class V2OracleResult:
    feasible: bool
    frontier: list[dict[str, Any]]
    replay_frontier: list[dict[str, Any]]
    feasible_terminals: list[dict[str, Any]]
    replay_terminals: list[dict[str, Any]]
    feasible_terminal_count: int
    feasible_scope_count: int
    assignment_count: int
    replay_count: int

    @property
    def frontier_vectors(self) -> list[EconomicVector]:
        return [
            EconomicVector(
                int(item["scope_economic_vector"]["irreversible_loss"]),
                int(item["scope_economic_vector"]["net_recovery_outlay"]),
            )
            for item in self.frontier
        ]

    @property
    def accepted_scope_keys(self) -> set[str]:
        return {item["scope_key"] for item in self.frontier}

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "frontier": deepcopy(self.frontier),
            "replay_frontier": deepcopy(self.replay_frontier),
            "feasible_terminals": deepcopy(self.feasible_terminals),
            "replay_terminals": deepcopy(self.replay_terminals),
            "feasible_terminal_count": self.feasible_terminal_count,
            "feasible_scope_count": self.feasible_scope_count,
            "assignment_count": self.assignment_count,
            "replay_count": self.replay_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> V2OracleResult:
        return cls(
            feasible=bool(value["feasible"]),
            frontier=deepcopy(value["frontier"]),
            replay_frontier=deepcopy(value["replay_frontier"]),
            feasible_terminals=deepcopy(value["feasible_terminals"]),
            replay_terminals=deepcopy(value["replay_terminals"]),
            feasible_terminal_count=int(value["feasible_terminal_count"]),
            feasible_scope_count=int(value["feasible_scope_count"]),
            assignment_count=int(value["assignment_count"]),
            replay_count=int(value["replay_count"]),
        )


_CACHE: dict[str, V2OracleResult] = {}


def clear_v2_oracle_cache() -> None:
    _CACHE.clear()


def solve_task_v2(task: dict[str, Any]) -> V2OracleResult:
    public = {key: value for key, value in task.items() if not key.startswith("_")}
    key = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if key not in _CACHE:
        _CACHE[key] = _solve(public)
    return deepcopy(_CACHE[key])


def _solve(task: dict[str, Any]) -> V2OracleResult:
    declarative, assignments = _declarative_terminals(task)
    replayed, replay_count = _tool_replay_terminals(task, declarative)
    frontier = _pareto_frontier(declarative)
    replay_frontier = _pareto_frontier(replayed)
    return V2OracleResult(
        feasible=bool(declarative),
        frontier=frontier,
        replay_frontier=replay_frontier,
        feasible_terminals=declarative,
        replay_terminals=replayed,
        feasible_terminal_count=len(declarative),
        feasible_scope_count=len({item["scope_key"] for item in declarative}),
        assignment_count=assignments,
        replay_count=replay_count,
    )


def _declarative_terminals(
    task: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Oracle A: pure terminal-state enumeration, without runtime calls."""
    boundary = task["boundary_commitments"]
    available = [item for item in task["inventory"] if item.get("available", False)]
    subsets = _option_subsets(task, available)
    terminals: list[dict[str, Any]] = []
    assignments = 0
    for keep_bits in product((False, True), repeat=len(boundary)):
        changed = {
            item["entity_id"]
            for item, keep in zip(boundary, keep_bits, strict=True)
            if not keep
        }
        kept = [
            _boundary_record(item)
            for item, keep in zip(boundary, keep_bits, strict=True)
            if keep
        ]
        for bought in subsets:
            assignments += 1
            active = kept + [_option_record(item) for item in bought]
            if not _static_goal_pass(task, active):
                continue
            vector = _static_economics(task, changed, bought)
            terminals.append(
                _terminal_record(task, changed, bought, vector, source="declarative")
            )
    return _deduplicate_terminals(terminals), assignments


def _tool_replay_terminals(
    task: dict[str, Any],
    candidate_terminals: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Oracle B: independently replay every feasible claim through public tools."""
    interface = DOMAIN_INTERFACES[task["domain"]]
    inventory = {item["option_id"]: item for item in task["inventory"]}
    terminals: list[dict[str, Any]] = []
    replay_count = 0
    for candidate in candidate_terminals:
        replay_count += 1
        changed = set(candidate["changed_boundary_entities"])
        bought = [inventory[option_id] for option_id in candidate["scope_signature"]["added_option_ids"]]
        environment = DomainRecoveryEnvironmentV2(task)
        valid = True
        calls: list[dict[str, Any]] = []
        for entity_id in sorted(changed):
            args = {interface["entity"]: entity_id, "confirm": True}
            result = environment.execute_tool(interface["cancel"], args)
            calls.append({"name": interface["cancel"], "arguments": args})
            if not result.ok:
                valid = False
                break
        if not valid:
            continue
        for option in sorted(bought, key=lambda item: item["option_id"]):
            args = {interface["option"]: option["option_id"]}
            result = environment.execute_tool(interface["book"], args)
            calls.append({"name": interface["book"], "arguments": args})
            if not result.ok:
                valid = False
                break
        if not valid:
            continue
        goal_pass, _ = environment.goal_status()
        if not goal_pass:
            continue
        vector = environment.economic_vector
        record = _terminal_record(
            task, changed, bought, vector, source="tool_replay"
        )
        record["tool_calls"] = calls
        terminals.append(record)
    return _deduplicate_terminals(terminals), replay_count


def _option_subsets(
    task: dict[str, Any], options: list[dict[str, Any]]
) -> list[list[dict[str, Any]]]:
    forbidden = {
        frozenset(rule["option_ids"])
        for rule in task.get("compatibility_rules", [])
        if rule["type"] == "forbid_pair"
    }
    result: list[list[dict[str, Any]]] = []

    def visit(index: int, selected: list[dict[str, Any]]) -> None:
        if index == len(options):
            result.append(deepcopy(selected))
            return
        visit(index + 1, selected)
        candidate = options[index]
        if any(
            frozenset({candidate["option_id"], item["option_id"]}) in forbidden
            for item in selected
        ):
            return
        selected.append(candidate)
        visit(index + 1, selected)
        selected.pop()

    visit(0, [])
    return result


def _boundary_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": item["entity_id"],
        "option_id": item["option_id"],
        "paid_cents": int(item["paid_cents"]),
        "provides": deepcopy(item["provides"]),
        "attributes": deepcopy(item.get("attributes", {})),
    }


def _option_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": None,
        "option_id": item["option_id"],
        "paid_cents": _option_charge(item),
        "provides": deepcopy(item["provides"]),
        "attributes": deepcopy(item.get("attributes", {})),
    }


def _static_goal_pass(task: dict[str, Any], active: list[dict[str, Any]]) -> bool:
    totals: dict[str, int] = {}
    for item in active:
        for capability, amount in item["provides"].items():
            totals[capability] = totals.get(capability, 0) + int(amount)
    for requirement in task["hard_goals"]["capabilities"]:
        observed = totals.get(requirement["capability"], 0)
        if observed < int(requirement.get("min", 0)):
            return False
        maximum = requirement.get("max")
        if maximum is not None and observed > int(maximum):
            return False

    active_options = {item["option_id"] for item in active}
    for rule in task.get("compatibility_rules", []):
        kind = rule["type"]
        if kind == "forbid_pair" and set(rule["option_ids"]).issubset(active_options):
            return False
        if (
            kind == "requires_any"
            and rule["if_option_id"] in active_options
            and not active_options.intersection(rule["any_option_ids"])
        ):
            return False
        if (
            kind == "requires_all"
            and rule["if_option_id"] in active_options
            and not set(rule["all_option_ids"]).issubset(active_options)
        ):
            return False
        if (
            kind == "requires_bridge"
            and set(rule["option_ids"]).issubset(active_options)
            and not active_options.intersection(rule["bridge_option_ids"])
        ):
            return False

    for requirement in task["hard_goals"].get("attribute_requirements", []):
        providers = [
            item
            for item in active
            if int(item["provides"].get(requirement["capability"], 0)) > 0
        ]
        if not providers or not all(
            _compare(
                item.get("attributes", {}).get(requirement["attribute"]),
                requirement["op"],
                requirement["value"],
            )
            for item in providers
        ):
            return False
    maximum_value = task["hard_goals"].get("max_active_value_cents")
    if maximum_value is not None and sum(
        int(item["paid_cents"]) for item in active
    ) > int(maximum_value):
        return False
    return True


def _static_economics(
    task: dict[str, Any],
    changed: set[str],
    bought: list[dict[str, Any]],
) -> EconomicVector:
    """Independent economics for Oracle A; no runtime helpers are called."""
    policies = {item["policy_id"]: item for item in task["policies"]}
    boundary = {item["entity_id"]: item for item in task["boundary_commitments"]}
    refund = sum(
        int(policies[boundary[entity_id]["refund_policy_id"]]["refund_cents"])
        for entity_id in changed
    )
    direct_loss = sum(
        int(boundary[entity_id]["paid_cents"])
        - int(policies[boundary[entity_id]["refund_policy_id"]]["refund_cents"])
        for entity_id in changed
    )
    purchase = sum(_option_charge(item) for item in bought)
    active_options = {
        item["option_id"]
        for item in task["boundary_commitments"]
        if item["entity_id"] not in changed
    } | {item["option_id"] for item in bought}
    contract_charge = sum(
        int(contract["charge_cents"])
        for contract in task.get("contracts", [])
        if _static_contract_triggered(
            contract["trigger"],
            changed,
            task["boundary_commitments"],
            active_options,
        )
    )
    return EconomicVector(
        direct_loss + contract_charge,
        purchase + contract_charge - refund,
    )


def _static_contract_triggered(
    trigger: dict[str, Any],
    changed: set[str],
    boundary: list[dict[str, Any]],
    active_options: set[str],
) -> bool:
    """Oracle-A contract semantics, deliberately independent from runtime."""
    entity_ids = set(trigger.get("entity_ids", []))
    kind = trigger["type"]
    if kind == "any_changed":
        return bool(entity_ids & changed)
    if kind == "all_changed":
        return bool(entity_ids) and entity_ids.issubset(changed)
    if kind == "changed_count_at_least":
        return len(entity_ids & changed) >= int(trigger["count"])
    if kind == "retained_paid_below":
        retained = sum(
            int(item["paid_cents"])
            for item in boundary
            if item["entity_id"] not in changed
            and (not entity_ids or item["entity_id"] in entity_ids)
        )
        return retained < int(trigger["threshold_cents"])
    if kind == "retained_quantity_below":
        retained = sum(
            int(item["provides"].get(trigger["capability"], 0))
            for item in boundary
            if item["entity_id"] not in changed
            and (not entity_ids or item["entity_id"] in entity_ids)
        )
        return retained < int(trigger["threshold_quantity"])
    if kind == "changed_with_retained":
        return bool(set(trigger.get("changed_entity_ids", [])) & changed) and bool(
            set(trigger.get("retained_entity_ids", [])) - changed
        )
    if kind == "active_any":
        return bool(set(trigger.get("option_ids", [])) & active_options)
    raise ValueError(f"Unknown static contract trigger: {kind}")


def _terminal_record(
    task: dict[str, Any],
    changed: set[str],
    bought: list[dict[str, Any]],
    vector: EconomicVector,
    *,
    source: str,
) -> dict[str, Any]:
    bought_ids = sorted(item["option_id"] for item in bought)
    boundary_scope: dict[str, str] = {}
    for item in task["boundary_commitments"]:
        entity_id = item["entity_id"]
        if entity_id not in changed:
            boundary_scope[entity_id] = "KEEP"
        elif any(
            int(option["provides"].get(item["primary_capability"], 0)) > 0
            for option in bought
        ):
            boundary_scope[entity_id] = "REPLACE"
        else:
            boundary_scope[entity_id] = "CANCEL"
    scope_signature = {
        "boundary": boundary_scope,
        "added_option_ids": bought_ids,
    }
    interface = DOMAIN_INTERFACES[task["domain"]]
    calls = [
        {
            "name": interface["cancel"],
            "arguments": {interface["entity"]: entity_id, "confirm": True},
        }
        for entity_id in sorted(changed)
    ] + [
        {
            "name": interface["book"],
            "arguments": {interface["option"]: option_id},
        }
        for option_id in bought_ids
    ]
    return {
        "scope_economic_vector": vector.as_dict(),
        "scope_signature": scope_signature,
        "scope_key": json.dumps(scope_signature, sort_keys=True, separators=(",", ":")),
        "terminal_key": _terminal_key(changed, bought_ids),
        "changed_boundary_entities": sorted(changed),
        "active_option_ids": sorted(
            [
                item["option_id"]
                for item in task["boundary_commitments"]
                if item["entity_id"] not in changed
            ]
            + bought_ids
        ),
        "tool_calls": calls,
        "source": source,
    }


def observed_terminal_key(
    task: dict[str, Any], environment: DomainRecoveryEnvironmentV2
) -> str:
    active = environment.active_commitments()
    boundary_ids = {item["entity_id"] for item in task["boundary_commitments"]}
    active_boundary = {
        item["entity_id"] for item in active if item["entity_id"] in boundary_ids
    }
    changed = boundary_ids - active_boundary
    bought = sorted(
        item["option_id"] for item in active if item["entity_id"] not in boundary_ids
    )
    return _terminal_key(changed, bought)


def frontier_signature(frontier: list[dict[str, Any]]) -> set[tuple[Any, ...]]:
    return {
        (
            item["terminal_key"],
            int(item["scope_economic_vector"]["irreversible_loss"]),
            int(item["scope_economic_vector"]["net_recovery_outlay"]),
        )
        for item in frontier
    }


def _terminal_key(changed: set[str], bought: list[str]) -> str:
    return json.dumps(
        {"changed": sorted(changed), "bought": sorted(bought)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _pareto_frontier(terminals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for candidate in terminals:
        vector = _vector(candidate)
        if any(
            _vector(other).dominates(vector)
            for other in terminals
            if other["terminal_key"] != candidate["terminal_key"]
        ):
            continue
        result.append(deepcopy(candidate))
    return sorted(
        _deduplicate_terminals(result),
        key=lambda item: (
            int(item["scope_economic_vector"]["irreversible_loss"]),
            int(item["scope_economic_vector"]["net_recovery_outlay"]),
            item["terminal_key"],
        ),
    )


def _vector(item: dict[str, Any]) -> EconomicVector:
    raw = item["scope_economic_vector"]
    return EconomicVector(
        int(raw["irreversible_loss"]),
        int(raw["net_recovery_outlay"]),
    )


def _deduplicate_terminals(
    terminals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for terminal in terminals:
        result[terminal["terminal_key"]] = terminal
    return [result[key] for key in sorted(result)]


def _option_charge(option: dict[str, Any]) -> int:
    return int(option["upfront_cents"]) + int(option.get("monthly_cents", 0)) * int(
        option.get("horizon_months", 0)
    )


def _compare(observed: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return observed == expected
    if operator == "le":
        return observed is not None and observed <= expected
    if operator == "ge":
        return observed is not None and observed >= expected
    if operator == "in":
        return observed in expected
    raise ValueError(f"Unsupported static comparison: {operator}")


__all__ = [
    "V2OracleResult",
    "clear_v2_oracle_cache",
    "frontier_signature",
    "observed_terminal_key",
    "solve_task_v2",
]
