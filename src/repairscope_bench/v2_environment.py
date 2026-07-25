from __future__ import annotations

from copy import deepcopy
from typing import Any

from .environment import ActionResult
from .v1_environment import (
    CommitmentRecoveryEnvironment,
    EconomicVector,
    canonical_json,
    snapshot_hash,
)


DOMAIN_INTERFACES = {
    "travel": {
        "list": "list_travel_commitments",
        "details": "get_travel_commitment",
        "search": "search_travel_inventory",
        "preview": "preview_travel_cancellation",
        "policy": "get_travel_terms",
        "compatibility": "check_travel_compatibility",
        "cancel": "cancel_travel_commitment",
        "book": "reserve_travel_option",
        "entity": "commitment_id",
        "option": "travel_option_id",
        "category": "service_category",
    },
    "after_sales": {
        "list": "list_order_commitments",
        "details": "get_order_commitment",
        "search": "search_product_inventory",
        "preview": "preview_product_return",
        "policy": "get_product_terms",
        "compatibility": "check_product_compatibility",
        "cancel": "return_product_commitment",
        "book": "purchase_product_option",
        "entity": "order_item_id",
        "option": "product_option_id",
        "category": "product_category",
    },
    "saas": {
        "list": "list_service_commitments",
        "details": "get_service_commitment",
        "search": "search_service_catalog",
        "preview": "preview_service_termination",
        "policy": "get_service_terms",
        "compatibility": "check_service_compatibility",
        "cancel": "terminate_service_commitment",
        "book": "activate_service_option",
        "entity": "service_component_id",
        "option": "service_option_id",
        "category": "service_category",
    },
    "event_logistics": {
        "list": "list_event_commitments",
        "details": "get_event_commitment",
        "search": "search_event_suppliers",
        "preview": "preview_event_cancellation",
        "policy": "get_event_contract_terms",
        "compatibility": "check_event_compatibility",
        "cancel": "cancel_event_commitment",
        "book": "book_event_option",
        "entity": "event_commitment_id",
        "option": "event_option_id",
        "category": "service_category",
    },
}


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def tool_definitions_v2(task: dict[str, Any]) -> list[dict[str, Any]]:
    interface = DOMAIN_INTERFACES[task["domain"]]
    entity = interface["entity"]
    option = interface["option"]
    category = interface["category"]
    categories = sorted({item["kind"] for item in task["inventory"]})
    return [
        _tool(
            interface["list"],
            "List the customer's currently active commitments.",
            {},
            [],
        ),
        _tool(
            interface["details"],
            "Read one active or cancelled commitment and its operational facts.",
            {entity: {"type": "string"}},
            [entity],
        ),
        _tool(
            interface["search"],
            "Search currently available alternatives in one domain category.",
            {category: {"type": "string", "enum": categories}},
            [category],
        ),
        _tool(
            interface["preview"],
            "Preview the direct refund from changing one existing commitment. This does not mutate state.",
            {entity: {"type": "string"}},
            [entity],
        ),
        _tool(
            interface["policy"],
            "Read authoritative price, refund, bundle, licence, threshold, or service terms linked to a commitment or option.",
            {"record_id": {"type": "string"}},
            ["record_id"],
        ),
        _tool(
            interface["compatibility"],
            "Check whether two options can coexist under current rules.",
            {
                "left_option_id": {"type": "string"},
                "right_option_id": {"type": "string"},
            },
            ["left_option_id", "right_option_id"],
        ),
        _tool(
            interface["cancel"],
            "Cancel, return, or terminate one existing commitment.",
            {entity: {"type": "string"}, "confirm": {"type": "boolean"}},
            [entity, "confirm"],
        ),
        _tool(
            interface["book"],
            "Create a persistent commitment for one available option.",
            {option: {"type": "string"}},
            [option],
        ),
    ]


def _policy_map(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["policy_id"]: item for item in task.get("policies", [])}


def runtime_task_v2(task: dict[str, Any]) -> dict[str, Any]:
    """Resolve normalized policy references for the executable v1 ledger core."""
    runtime = deepcopy({key: value for key, value in task.items() if not key.startswith("_")})
    runtime["schema_version"] = "1.1"
    policies = _policy_map(task)
    for commitment in runtime["failure_snapshot"]["commitments"]:
        policy = policies[commitment["refund_policy_id"]]
        commitment["refund_cents"] = int(policy["refund_cents"])
    for commitment in runtime["boundary_commitments"]:
        policy = policies[commitment["refund_policy_id"]]
        commitment["refund_cents"] = int(policy["refund_cents"])
    for option in runtime["inventory"]:
        policy_id = option.get("refund_policy_id")
        option["refund_after_purchase_cents"] = (
            int(policies[policy_id]["refund_cents"]) if policy_id else 0
        )
    return runtime


class DomainRecoveryEnvironmentV2:
    """Schema-v2 public domain interface over an auditable persistent ledger."""

    def __init__(self, task: dict[str, Any]):
        self.task = deepcopy(task)
        self.interface = DOMAIN_INTERFACES[task["domain"]]
        self._runtime = CommitmentRecoveryEnvironment(runtime_task_v2(task))

    def clone(self) -> DomainRecoveryEnvironmentV2:
        return deepcopy(self)

    @property
    def ledger(self) -> list[dict[str, Any]]:
        return self._runtime.ledger

    @property
    def event_log(self) -> list[dict[str, Any]]:
        return self._runtime.event_log

    @property
    def economic_vector(self) -> EconomicVector:
        return self._runtime.economic_vector

    @property
    def state_changing_actions(self) -> int:
        return self._runtime.state_changing_actions

    def active_commitments(self) -> list[dict[str, Any]]:
        return self._runtime.active_commitments()

    def goal_status(self) -> tuple[bool, list[dict[str, Any]]]:
        return self._runtime.goal_status()

    def dispositions(self) -> dict[str, str]:
        return self._runtime.dispositions()

    def state_key(self) -> str:
        return self._runtime.state_key()

    def public_tool_name(self, event_tool_name: str) -> str:
        """Map a normalized runtime event name back to the model-visible API."""
        internal = self._runtime.names
        mapping = {
            internal["list"]: self.interface["list"],
            internal["details"]: self.interface["details"],
            internal["search"]: self.interface["search"],
            internal["preview"]: self.interface["preview"],
            internal["compatibility"]: self.interface["compatibility"],
            internal["cancel"]: self.interface["cancel"],
            internal["book"]: self.interface["book"],
        }
        return mapping.get(event_tool_name, event_tool_name)

    def execute_tool(self, name: str, args: dict[str, Any]) -> ActionResult:
        interface = self.interface
        internal = self._runtime.names
        if name == interface["list"]:
            return self._runtime.execute_tool(internal["list"], {})
        if name == interface["details"]:
            return self._runtime.execute_tool(
                internal["details"], {internal["id"]: args[interface["entity"]]}
            )
        if name == interface["search"]:
            return self._runtime.execute_tool(
                internal["search"], {internal["kind"]: args[interface["category"]]}
            )
        if name == interface["preview"]:
            return self._runtime.execute_tool(
                internal["preview"], {internal["id"]: args[interface["entity"]]}
            )
        if name == interface["policy"]:
            return self._linked_terms(args["record_id"])
        if name == interface["compatibility"]:
            return self._runtime.execute_tool(
                internal["compatibility"],
                {
                    "left_option_id": args["left_option_id"],
                    "right_option_id": args["right_option_id"],
                },
            )
        if name == interface["cancel"]:
            return self._runtime.execute_tool(
                internal["cancel"],
                {
                    internal["id"]: args[interface["entity"]],
                    "confirm": args["confirm"],
                },
            )
        if name == interface["book"]:
            result = self._runtime.execute_tool(
                internal["book"], {internal["option"]: args[interface["option"]]}
            )
            if not result.ok:
                return result
            option_id = args[interface["option"]]
            source = next(
                item
                for item in self.task["inventory"]
                if item["option_id"] == option_id
            )
            target_id = source.get("entity_id_on_purchase")
            raw_id = result.data["entity_id"]
            if not target_id or target_id == raw_id:
                return result
            commitment = self._runtime.commitments.pop(raw_id)
            commitment["entity_id"] = target_id
            self._runtime.commitments[target_id] = commitment
            for ledger_item in reversed(self._runtime.ledger):
                if ledger_item.get("entity_id") == raw_id:
                    ledger_item["entity_id"] = target_id
                    break
            data = deepcopy(result.data)
            data["entity_id"] = target_id
            result = ActionResult(True, result.message, data)
            self._runtime.event_log[-1]["result"] = result.as_dict()
            return result
        result = ActionResult(False, f"Unknown {self.task['domain']} operation: {name}")
        self._runtime.event_log.append(
            {
                "tool": name,
                "arguments": deepcopy(args),
                "result": result.as_dict(),
                "state_changed": False,
            }
        )
        return result

    def _linked_terms(self, record_id: str) -> ActionResult:
        policies = _policy_map(self.task)
        policy_ids: list[str] = []
        if record_id in self._runtime.commitments:
            commitment = self._runtime.commitments[record_id]
            source = next(
                item
                for item in self.task["inventory"]
                if item["option_id"] == commitment["option_id"]
            )
            policy_ids.append(source["refund_policy_id"])
        elif record_id in self._runtime.inventory:
            option = next(
                item for item in self.task["inventory"] if item["option_id"] == record_id
            )
            if option.get("refund_policy_id"):
                policy_ids.append(option["refund_policy_id"])
        else:
            return ActionResult(False, "Unknown commitment or option.")

        terms = [deepcopy(policies[policy_id]) for policy_id in policy_ids]
        internal = self._runtime._terms(record_id)
        if internal.ok:
            terms.extend(deepcopy(internal.data["terms"]))
        existing_ids = {
            item.get("contract_id") for item in terms if item.get("contract_id")
        }
        for contract in self.task.get("contracts", []):
            trigger = contract["trigger"]
            linked = set(trigger.get("entity_ids", []))
            linked.update(trigger.get("changed_entity_ids", []))
            linked.update(trigger.get("retained_entity_ids", []))
            linked.update(trigger.get("option_ids", []))
            linked.update(contract.get("linked_option_ids", []))
            if (
                record_id in linked
                and contract["contract_id"] not in existing_ids
            ):
                terms.append(
                    {
                        "contract_id": contract["contract_id"],
                        "description": contract["description"],
                        "trigger": deepcopy(trigger),
                        "charge_cents": int(contract["charge_cents"]),
                    }
                )
        result = ActionResult(True, "Authoritative linked terms retrieved.", {"terms": terms})
        self._runtime.event_log.append(
            {
                "tool": self.interface["policy"],
                "arguments": {"record_id": record_id},
                "result": result.as_dict(),
                "state_changed": False,
            }
        )
        return result


__all__ = [
    "DOMAIN_INTERFACES",
    "DomainRecoveryEnvironmentV2",
    "EconomicVector",
    "canonical_json",
    "runtime_task_v2",
    "snapshot_hash",
    "tool_definitions_v2",
]
