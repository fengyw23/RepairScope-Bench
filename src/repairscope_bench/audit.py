from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from .v2_environment import snapshot_hash
from .v2_oracle import solve_task_v2


ROLE_TOKENS = {
    "local",
    "bridge",
    "decoy",
    "wrong-site",
    "wrong_site",
    "late",
    "failed",
    "dominated",
    "alt1",
    "alt2",
    "alt3",
    "continuity",
}


def public_role_leakage_hits(task: dict[str, Any]) -> list[dict[str, str]]:
    hits = []
    for option in task["inventory"]:
        for field in ["option_id", "name"]:
            value = str(option.get(field, "")).lower()
            for token in ROLE_TOKENS:
                if token in value:
                    hits.append(
                        {
                            "option_id": option["option_id"],
                            "field": field,
                            "token": token,
                        }
                    )
    return hits


def permutation_invariance_certificate(task: dict[str, Any]) -> dict[str, Any]:
    original = solve_task_v2(task)
    permuted = permute_public_identifiers(task)
    changed = solve_task_v2(permuted)
    original_shape = normalized_oracle_shape(original)
    changed_shape = normalized_oracle_shape(changed)
    return {
        "identifier_permutation_invariant": original_shape == changed_shape,
        "original_shape": original_shape,
        "permuted_shape": changed_shape,
    }


def permute_public_identifiers(task: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy({key: value for key, value in task.items() if not key.startswith("_")})
    identifiers = []
    identifiers.extend(item["option_id"] for item in result["inventory"])
    identifiers.extend(
        item["entity_id_on_purchase"]
        for item in result["inventory"]
        if item.get("entity_id_on_purchase")
    )
    identifiers.extend(
        item["entity_id"] for item in result["failure_snapshot"]["commitments"]
    )
    identifiers.extend(item["policy_id"] for item in result["policies"])
    identifiers.extend(item["contract_id"] for item in result["contracts"])
    mapping = {
        identifier: _permuted_id(identifier, index)
        for index, identifier in enumerate(sorted(set(identifiers)), start=1)
    }
    result = _replace_values(result, mapping)
    result["inventory"] = list(reversed(result["inventory"]))
    result["policies"] = list(reversed(result["policies"]))
    result["contracts"] = list(reversed(result["contracts"]))
    result["compatibility_rules"] = list(
        reversed(result["compatibility_rules"])
    )
    result["failure_snapshot"]["commitments"] = sorted(
        result["failure_snapshot"]["commitments"],
        key=lambda item: item["entity_id"],
    )
    result["boundary_commitments"] = sorted(
        result["boundary_commitments"],
        key=lambda item: item["entity_id"],
    )
    result["snapshot_sha256"] = snapshot_hash(result["failure_snapshot"])
    return result


def normalized_oracle_shape(oracle: Any) -> dict[str, Any]:
    frontier = sorted(
        (
            int(item["scope_economic_vector"]["irreversible_loss"]),
            int(item["scope_economic_vector"]["net_recovery_outlay"]),
            len(item["changed_boundary_entities"]),
            len(item["scope_signature"]["added_option_ids"]),
            tuple(sorted(item["scope_signature"]["boundary"].values())),
        )
        for item in oracle.frontier
    )
    return {
        "feasible_terminal_count": oracle.feasible_terminal_count,
        "feasible_scope_count": oracle.feasible_scope_count,
        "frontier": frontier,
    }


def _replace_values(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_values(item, mapping) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_values(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _permuted_id(identifier: str, index: int) -> str:
    digest = hashlib.sha256(f"v2-permute::{identifier}::{index}".encode()).hexdigest()
    return f"X-{digest[:12]}"


__all__ = [
    "ROLE_TOKENS",
    "normalized_oracle_shape",
    "permutation_invariance_certificate",
    "permute_public_identifiers",
    "public_role_leakage_hits",
]
