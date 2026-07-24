from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

from .v06_constraints import check_v06_constraints
from .v06_environment import EconomicVector, StateBackedRecoveryEnvironment


@dataclass
class V06OracleResult:
    feasible: bool
    frontier: list[dict[str, Any]]
    feasible_terminal_count: int
    feasible_scope_count: int
    explored_state_count: int
    semantic_action_count: int
    independent_frontier: list[dict[str, Any]]

    @property
    def frontier_vectors(self) -> list[EconomicVector]:
        return [
            EconomicVector(
                item["economic_vector"]["irreversible_loss"],
                item["economic_vector"]["net_recovery_outlay"],
            )
            for item in self.frontier
        ]

    @property
    def optimal_scopes(self) -> list[dict[str, str]]:
        return _deduplicate([item["scope"] for item in self.frontier])

    @property
    def optimal_plans(self) -> list[list[dict[str, Any]]]:
        return [deepcopy(item["tool_calls"]) for item in self.frontier]

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "frontier": deepcopy(self.frontier),
            "feasible_terminal_count": self.feasible_terminal_count,
            "feasible_scope_count": self.feasible_scope_count,
            "explored_state_count": self.explored_state_count,
            "semantic_action_count": self.semantic_action_count,
            "independent_frontier": deepcopy(self.independent_frontier),
        }


_CACHE: dict[str, V06OracleResult] = {}


def solve_task_v06(task: dict[str, Any]) -> V06OracleResult:
    public = {key: value for key, value in task.items() if not key.startswith("_")}
    key = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if key not in _CACHE:
        _CACHE[key] = _search(public)
    return deepcopy(_CACHE[key])


def clear_v06_oracle_cache() -> None:
    _CACHE.clear()


def _search(task: dict[str, Any]) -> V06OracleResult:
    actions = {item["action_id"]: item for item in task["oracle_actions"]}
    max_depth = int(task.get("oracle_max_semantic_actions", 7))
    initial = StateBackedRecoveryEnvironment(task)
    queue: deque[
        tuple[StateBackedRecoveryEnvironment, tuple[str, ...], list[dict[str, Any]]]
    ] = deque([(initial, (), [])])
    seen: dict[tuple[str, tuple[str, ...]], list[EconomicVector]] = {}
    terminals: list[dict[str, Any]] = []
    explored = 0

    while queue:
        environment, used, raw_calls = queue.popleft()
        explored += 1
        passed, _ = check_v06_constraints(task, environment)
        if passed:
            terminals.append(
                _terminal_record(environment, list(used), raw_calls)
            )
        if len(used) >= max_depth:
            continue
        remaining = [
            action_id
            for action_id in actions
            if action_id not in used
        ]
        for action_id in remaining:
            candidate = environment.clone()
            calls = deepcopy(actions[action_id]["tool_calls"])
            if not _replay_calls(candidate, calls):
                continue
            next_used = used + (action_id,)
            state_key = (candidate.state_key(), tuple(sorted(next_used)))
            vector = candidate.economic_vector
            prior = seen.setdefault(state_key, [])
            if any(item.dominates(vector) or item == vector for item in prior):
                continue
            prior[:] = [item for item in prior if not vector.dominates(item)]
            prior.append(vector)
            queue.append((candidate, next_used, raw_calls + calls))

    terminals = _deduplicate_terminals(terminals)
    frontier = _pareto_frontier(terminals)
    independent = _independent_enumeration(task, actions)
    return V06OracleResult(
        feasible=bool(terminals),
        frontier=frontier,
        feasible_terminal_count=len(terminals),
        feasible_scope_count=len(_deduplicate([item["scope"] for item in terminals])),
        explored_state_count=explored,
        semantic_action_count=len(actions),
        independent_frontier=independent,
    )


def _independent_enumeration(
    task: dict[str, Any], actions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    terminals: list[dict[str, Any]] = []
    for scope in task["candidate_scopes"]:
        environment = StateBackedRecoveryEnvironment(task)
        calls: list[dict[str, Any]] = []
        valid = True
        for action_id in scope["action_ids"]:
            action_calls = deepcopy(actions[action_id]["tool_calls"])
            calls.extend(action_calls)
            if not _replay_calls(environment, action_calls):
                valid = False
                break
        if not valid:
            continue
        passed, _ = check_v06_constraints(task, environment)
        if passed:
            record = _terminal_record(
                environment, list(scope["action_ids"]), calls
            )
            record["candidate_scope_id"] = scope["scope_id"]
            terminals.append(record)
    return _pareto_frontier(_deduplicate_terminals(terminals))


def _replay_calls(
    environment: StateBackedRecoveryEnvironment,
    calls: list[dict[str, Any]],
) -> bool:
    for call in calls:
        result = environment.execute_tool(call["name"], call.get("arguments", {}))
        if not result.ok:
            return False
    return True


def _terminal_record(
    environment: StateBackedRecoveryEnvironment,
    semantic_actions: list[str],
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "economic_vector": environment.economic_vector.as_dict(),
        "scope": environment.dispositions(),
        "semantic_actions": semantic_actions,
        "tool_calls": deepcopy(tool_calls),
        "state_hash": environment.state_key(),
        "changed_boundary_entities": sorted(environment.changed_boundary_entities()),
        "state_changing_actions": environment.state_changing_actions,
    }


def _pareto_frontier(terminals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in terminals:
        vector = _vector(candidate)
        if any(_vector(other).dominates(vector) for other in terminals):
            continue
        result.append(deepcopy(candidate))
    return sorted(
        _deduplicate_terminals(result),
        key=lambda item: (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            item["state_hash"],
        ),
    )


def _vector(item: dict[str, Any]) -> EconomicVector:
    return EconomicVector(
        item["economic_vector"]["irreversible_loss"],
        item["economic_vector"]["net_recovery_outlay"],
    )


def _deduplicate_terminals(
    terminals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, int | float, int | float]] = set()
    result: list[dict[str, Any]] = []
    for item in terminals:
        key = (
            item["state_hash"],
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _deduplicate(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
