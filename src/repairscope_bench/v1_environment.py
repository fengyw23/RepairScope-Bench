from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .environment import ActionResult


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EconomicVector:
    irreversible_loss: int
    net_recovery_outlay: int

    def as_dict(self) -> dict[str, int]:
        return {
            "irreversible_loss": self.irreversible_loss,
            "net_recovery_outlay": self.net_recovery_outlay,
        }

    def dominates(self, other: EconomicVector) -> bool:
        return (
            self.irreversible_loss <= other.irreversible_loss
            and self.net_recovery_outlay <= other.net_recovery_outlay
            and (
                self.irreversible_loss < other.irreversible_loss
                or self.net_recovery_outlay < other.net_recovery_outlay
            )
        )


DOMAIN_TOOL_NAMES = {
    "travel": {
        "list": "list_current_arrangements",
        "details": "get_arrangement_details",
        "search": "search_trip_options",
        "preview": "preview_arrangement_cancellation",
        "terms": "get_linked_terms",
        "compatibility": "check_trip_compatibility",
        "cancel": "cancel_arrangement",
        "book": "book_trip_option",
        "id": "arrangement_id",
        "option": "option_id",
        "kind": "category",
    },
    "after_sales": {
        "list": "list_customer_orders",
        "details": "get_order_item_details",
        "search": "search_replacement_products",
        "preview": "preview_order_item_return",
        "terms": "get_linked_terms",
        "compatibility": "check_product_compatibility",
        "cancel": "return_order_item",
        "book": "purchase_product",
        "id": "order_item_id",
        "option": "product_id",
        "kind": "category",
    },
    "saas": {
        "list": "list_subscription_components",
        "details": "get_subscription_component",
        "search": "search_service_options",
        "preview": "preview_component_termination",
        "terms": "get_linked_terms",
        "compatibility": "check_service_compatibility",
        "cancel": "terminate_subscription_component",
        "book": "activate_service_option",
        "id": "component_id",
        "option": "service_option_id",
        "kind": "category",
    },
    "event_logistics": {
        "list": "list_event_commitments",
        "details": "get_event_commitment",
        "search": "search_vendor_options",
        "preview": "preview_commitment_cancellation",
        "terms": "get_linked_terms",
        "compatibility": "check_logistics_compatibility",
        "cancel": "cancel_event_commitment",
        "book": "book_vendor_option",
        "id": "commitment_id",
        "option": "vendor_option_id",
        "kind": "category",
    },
}


def _schema(
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


def tool_definitions_v1(task: dict[str, Any]) -> list[dict[str, Any]]:
    names = DOMAIN_TOOL_NAMES[task["domain"]]
    entity_id = names["id"]
    option_id = names["option"]
    kind = names["kind"]
    categories = sorted(
        {item["kind"] for item in task["inventory"]}
        | {item["kind"] for item in task["failure_snapshot"]["commitments"]}
    )
    return [
        _schema(
            names["list"],
            "List all current active commitments and their identifiers.",
            {},
            [],
        ),
        _schema(
            names["details"],
            "Read one commitment, including what it provides, its status, dates, location, and paid amount.",
            {entity_id: {"type": "string"}},
            [entity_id],
        ),
        _schema(
            names["search"],
            "Search live alternatives in one category. Prices, recurring charges, delivery facts, and functional capabilities are returned.",
            {kind: {"type": "string", "enum": categories}},
            [kind],
        ),
        _schema(
            names["preview"],
            "Preview the refund and direct irreversible loss from cancelling one commitment. This does not mutate state.",
            {entity_id: {"type": "string"}},
            [entity_id],
        ),
        _schema(
            names["terms"],
            "Read supplier, bundle, threshold, licence, warranty, or service terms linked to one commitment or option.",
            {"entity_or_option_id": {"type": "string"}},
            ["entity_or_option_id"],
        ),
        _schema(
            names["compatibility"],
            "Check whether two options can coexist under the published compatibility rules.",
            {
                "left_option_id": {"type": "string"},
                "right_option_id": {"type": "string"},
            },
            ["left_option_id", "right_option_id"],
        ),
        _schema(
            names["cancel"],
            "Preview or confirm cancellation/return/termination of one active commitment.",
            {
                entity_id: {"type": "string"},
                "confirm": {"type": "boolean"},
            },
            [entity_id],
        ),
        _schema(
            names["book"],
            "Create a persistent commitment for one currently available option.",
            {option_id: {"type": "string"}},
            [option_id],
        ),
    ]


class CommitmentRecoveryEnvironment:
    """Executable fixed-boundary environment for schema v1.0."""

    def __init__(self, task: dict[str, Any]):
        self.task = deepcopy({k: v for k, v in task.items() if not k.startswith("_")})
        self.domain = task["domain"]
        self.names = DOMAIN_TOOL_NAMES[self.domain]
        self.commitments = {
            item["entity_id"]: deepcopy(item)
            for item in task["failure_snapshot"]["commitments"]
        }
        self.inventory = {
            item["option_id"]: deepcopy(item) for item in task["inventory"]
        }
        self.boundary_ids = {
            item["entity_id"] for item in task["boundary_commitments"]
        }
        self.changed_boundary: set[str] = set()
        self.triggered_contracts: set[str] = set()
        self.ledger: list[dict[str, Any]] = []
        self.event_log: list[dict[str, Any]] = []
        existing_numbers = [
            int(entity_id.split("-")[-1])
            for entity_id in self.commitments
            if entity_id.startswith("NEW-") and entity_id.split("-")[-1].isdigit()
        ]
        self._next_entity = max(existing_numbers, default=0) + 1

    def clone(self) -> CommitmentRecoveryEnvironment:
        return deepcopy(self)

    @property
    def economic_vector(self) -> EconomicVector:
        return EconomicVector(
            sum(int(item["irreversible_loss_delta"]) for item in self.ledger),
            sum(int(item["net_outlay_delta"]) for item in self.ledger),
        )

    @property
    def state_changing_actions(self) -> int:
        return sum(
            bool(item["state_changed"]) and item["result"]["ok"]
            for item in self.event_log
        )

    def execute_tool(self, name: str, args: dict[str, Any]) -> ActionResult:
        before = self.state_key()
        try:
            result = self._dispatch(name, deepcopy(args))
        except (KeyError, TypeError, ValueError) as error:
            result = ActionResult(False, str(error))
        after = self.state_key()
        self.event_log.append(
            {
                "tool": name,
                "arguments": deepcopy(args),
                "result": result.as_dict(),
                "state_changed": before != after,
            }
        )
        return result

    def _dispatch(self, name: str, args: dict[str, Any]) -> ActionResult:
        if name == self.names["list"]:
            return ActionResult(
                True,
                "Current commitments retrieved.",
                {
                    "commitments": [
                        self._public_commitment(item)
                        for item in self.commitments.values()
                        if item["status"] == "active"
                    ]
                },
            )
        if name == self.names["details"]:
            return self._details(args[self.names["id"]])
        if name == self.names["search"]:
            return self._search(args[self.names["kind"]])
        if name == self.names["preview"]:
            return self._preview(args[self.names["id"]])
        if name == self.names["terms"]:
            return self._terms(args["entity_or_option_id"])
        if name == self.names["compatibility"]:
            return self._compatibility(
                args["left_option_id"], args["right_option_id"]
            )
        if name == self.names["cancel"]:
            entity_id = args[self.names["id"]]
            if not args.get("confirm", False):
                return self._preview(entity_id)
            return self._cancel(entity_id)
        if name == self.names["book"]:
            return self._book(args[self.names["option"]])
        return ActionResult(False, f"Unknown {self.domain} operation: {name}")

    def _details(self, entity_id: str) -> ActionResult:
        item = self.commitments.get(entity_id)
        if item is None:
            return ActionResult(False, "Commitment not found.")
        data = self._public_commitment(item)
        option = self.inventory.get(item["option_id"])
        if option is not None:
            data["attributes"] = deepcopy(option.get("attributes", {}))
        return ActionResult(True, "Commitment retrieved.", data)

    def _search(self, kind: str) -> ActionResult:
        results = [
            self._public_option(item)
            for item in self.inventory.values()
            if item["kind"] == kind and item.get("available", False)
        ]
        return ActionResult(
            True,
            f"Found {len(results)} available option(s).",
            {"category": kind, "results": results},
        )

    def _preview(self, entity_id: str) -> ActionResult:
        item = self.commitments.get(entity_id)
        if item is None or item["status"] != "active":
            return ActionResult(False, "Active commitment not found.")
        paid = int(item["paid_cents"])
        refund = int(item.get("refund_cents", 0))
        linked = [
            contract["contract_id"]
            for contract in self.task["contracts"]
            if entity_id in contract["trigger"].get("entity_ids", [])
        ]
        return ActionResult(
            True,
            "Cancellation preview generated; no state was changed.",
            {
                "entity_id": entity_id,
                "paid_cents": paid,
                "refund_cents": refund,
                "direct_irreversible_loss_cents": paid - refund,
                "linked_term_ids": linked,
                "confirmation_required": True,
            },
        )

    def _terms(self, identifier: str) -> ActionResult:
        known = identifier in self.commitments or identifier in self.inventory
        terms = []
        for contract in self.task["contracts"]:
            trigger = contract["trigger"]
            linked = set(trigger.get("entity_ids", []))
            linked.update(contract.get("linked_option_ids", []))
            if identifier in linked:
                terms.append(
                    {
                        "contract_id": contract["contract_id"],
                        "description": contract["description"],
                        "trigger": deepcopy(trigger),
                        "charge_cents": contract["charge_cents"],
                    }
                )
        option = self.inventory.get(identifier)
        if option is not None:
            known = True
            terms.append(
                {
                    "term_id": f"{identifier}-price",
                    "description": (
                        f"Upfront {option['upfront_cents']} cents plus "
                        f"{option.get('monthly_cents', 0)} cents per month for "
                        f"{option.get('horizon_months', 0)} months."
                    ),
                    "total_charge_cents": self._option_charge(option),
                }
            )
        for rule in self.task.get("compatibility_rules", []):
            linked = set(rule.get("option_ids", []))
            linked.add(rule.get("if_option_id", ""))
            linked.update(rule.get("all_option_ids", []))
            if identifier in linked and rule["type"] == "requires_all":
                terms.append(
                    {
                        "term_id": f"{identifier}-required-components",
                        "description": (
                            "This option is valid only when every listed "
                            "companion component is active."
                        ),
                        "required_option_ids": deepcopy(rule["all_option_ids"]),
                    }
                )
        if not known:
            return ActionResult(False, "Unknown commitment or option.")
        return ActionResult(True, "Linked terms retrieved.", {"terms": terms})

    def _compatibility(self, left: str, right: str) -> ActionResult:
        if left == right:
            return ActionResult(True, "An option is compatible with itself.", {"compatible": True})
        pair = frozenset({left, right})
        forbidden = {
            frozenset(item["option_ids"])
            for item in self.task.get("compatibility_rules", [])
            if item["type"] == "forbid_pair"
        }
        return ActionResult(
            True,
            "Compatibility checked.",
            {"compatible": pair not in forbidden},
        )

    def _cancel(self, entity_id: str) -> ActionResult:
        item = self.commitments.get(entity_id)
        if item is None or item["status"] != "active":
            return ActionResult(False, "Active commitment not found.")
        paid = int(item["paid_cents"])
        refund = int(item.get("refund_cents", 0))
        item["status"] = "cancelled"
        if entity_id in self.boundary_ids:
            self.changed_boundary.add(entity_id)
        self._append_ledger(
            tool=self.names["cancel"],
            entity_id=entity_id,
            charge=0,
            refund=refund,
            irreversible=paid - refund,
            contract_id=None,
        )
        applied = self._apply_newly_triggered_contracts()
        return ActionResult(
            True,
            "Commitment cancelled.",
            {
                "entity_id": entity_id,
                "refund_cents": refund,
                "direct_irreversible_loss_cents": paid - refund,
                "contract_charges_applied": applied,
            },
        )

    def _book(self, option_id: str) -> ActionResult:
        option = self.inventory.get(option_id)
        if option is None or not option.get("available", False):
            return ActionResult(False, "The selected option is unavailable.")
        if any(
            item["status"] == "active" and item["option_id"] == option_id
            for item in self.commitments.values()
        ):
            return ActionResult(False, "The selected option is already active.")
        active_option_ids = {
            item["option_id"]
            for item in self.commitments.values()
            if item["status"] == "active"
        }
        forbidden_pairs = {
            frozenset(rule["option_ids"])
            for rule in self.task.get("compatibility_rules", [])
            if rule["type"] == "forbid_pair"
        }
        if any(
            frozenset({option_id, active_option}) in forbidden_pairs
            for active_option in active_option_ids
        ):
            return ActionResult(
                False,
                "The selected option conflicts with an active recovery option.",
            )
        entity_id = f"NEW-{self._next_entity:04d}"
        self._next_entity += 1
        charge = self._option_charge(option)
        self.commitments[entity_id] = {
            "entity_id": entity_id,
            "option_id": option_id,
            "name": option.get("name", option_id),
            "kind": option["kind"],
            "status": "active",
            "paid_cents": charge,
            "refund_cents": int(option.get("refund_after_purchase_cents", 0)),
            "provides": deepcopy(option["provides"]),
            "attributes": deepcopy(option.get("attributes", {})),
            "created_after_boundary": True,
        }
        self._append_ledger(
            tool=self.names["book"],
            entity_id=entity_id,
            charge=charge,
            refund=0,
            irreversible=0,
            contract_id=None,
        )
        return ActionResult(
            True,
            "New commitment created.",
            {
                "entity_id": entity_id,
                "option_id": option_id,
                "charge_cents": charge,
            },
        )

    def _apply_newly_triggered_contracts(self) -> list[dict[str, Any]]:
        applied = []
        for contract in self.task["contracts"]:
            contract_id = contract["contract_id"]
            if contract_id in self.triggered_contracts:
                continue
            if not contract_triggered(
                contract["trigger"],
                self.changed_boundary,
                self.task["boundary_commitments"],
            ):
                continue
            self.triggered_contracts.add(contract_id)
            charge = int(contract["charge_cents"])
            self._append_ledger(
                tool="contract_settlement",
                entity_id=None,
                charge=charge,
                refund=0,
                irreversible=charge,
                contract_id=contract_id,
            )
            applied.append(
                {"contract_id": contract_id, "charge_cents": charge}
            )
        return applied

    def _append_ledger(
        self,
        *,
        tool: str,
        entity_id: str | None,
        charge: int,
        refund: int,
        irreversible: int,
        contract_id: str | None,
    ) -> None:
        self.ledger.append(
            {
                "event_index": len(self.ledger) + 1,
                "tool": tool,
                "entity_id": entity_id,
                "contract_id": contract_id,
                "charge_cents": charge,
                "refund_cents": refund,
                "irreversible_loss_delta": irreversible,
                "net_outlay_delta": charge - refund,
            }
        )

    def active_commitments(self) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in self.commitments.values()
            if item["status"] == "active"
        ]

    def goal_status(self) -> tuple[bool, list[dict[str, Any]]]:
        active = self.active_commitments()
        totals: dict[str, int] = {}
        for item in active:
            for capability, amount in item["provides"].items():
                totals[capability] = totals.get(capability, 0) + int(amount)
        failures: list[dict[str, Any]] = []
        for requirement in self.task["hard_goals"]["capabilities"]:
            observed = totals.get(requirement["capability"], 0)
            minimum = int(requirement.get("min", 0))
            maximum = requirement.get("max")
            if observed < minimum or (
                maximum is not None and observed > int(maximum)
            ):
                failures.append(
                    {
                        "type": "capability_count",
                        "capability": requirement["capability"],
                        "observed": observed,
                        "min": minimum,
                        "max": maximum,
                    }
                )
        active_options = {item["option_id"] for item in active}
        for rule in self.task.get("compatibility_rules", []):
            if rule["type"] == "forbid_pair" and set(rule["option_ids"]).issubset(
                active_options
            ):
                failures.append(
                    {"type": "forbidden_pair", "option_ids": rule["option_ids"]}
                )
            elif rule["type"] == "requires_any":
                if (
                    rule["if_option_id"] in active_options
                    and not active_options.intersection(rule["any_option_ids"])
                ):
                    failures.append(
                        {
                            "type": "missing_required_companion",
                            "if_option_id": rule["if_option_id"],
                        }
                    )
            elif rule["type"] == "requires_all":
                if (
                    rule["if_option_id"] in active_options
                    and not set(rule["all_option_ids"]).issubset(active_options)
                ):
                    failures.append(
                        {
                            "type": "missing_required_components",
                            "if_option_id": rule["if_option_id"],
                        }
                    )
        for requirement in self.task["hard_goals"].get(
            "attribute_requirements", []
        ):
            providers = [
                item
                for item in active
                if item["provides"].get(requirement["capability"], 0) > 0
            ]
            if not providers or not all(
                _compare(
                    item.get("attributes", {}).get(requirement["attribute"]),
                    requirement["op"],
                    requirement["value"],
                )
                for item in providers
            ):
                failures.append(
                    {
                        "type": "attribute_requirement",
                        "capability": requirement["capability"],
                        "attribute": requirement["attribute"],
                    }
                )
        max_total = self.task["hard_goals"].get("max_active_value_cents")
        active_value = sum(int(item["paid_cents"]) for item in active)
        if max_total is not None and active_value > int(max_total):
            failures.append(
                {
                    "type": "max_active_value",
                    "observed": active_value,
                    "max": int(max_total),
                }
            )
        return not failures, failures

    def dispositions(self) -> dict[str, str]:
        active = self.active_commitments()
        new_active = [
            item for item in active if item["entity_id"] not in self.boundary_ids
        ]
        result = {}
        for boundary in self.task["boundary_commitments"]:
            entity_id = boundary["entity_id"]
            current = self.commitments[entity_id]
            if current["status"] == "active":
                result[entity_id] = "KEEP"
                continue
            primary = boundary["primary_capability"]
            result[entity_id] = (
                "REPLACE"
                if any(item["provides"].get(primary, 0) > 0 for item in new_active)
                else "CANCEL"
            )
        return result

    def normalized_state(self) -> dict[str, Any]:
        return {
            "commitments": sorted(
                (deepcopy(item) for item in self.commitments.values()),
                key=lambda item: item["entity_id"],
            ),
            "changed_boundary": sorted(self.changed_boundary),
            "triggered_contracts": sorted(self.triggered_contracts),
            "ledger": deepcopy(self.ledger),
        }

    def state_key(self) -> str:
        return snapshot_hash(self.normalized_state())

    def _public_commitment(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_id": item["entity_id"],
            "option_id": item["option_id"],
            "name": item.get("name", item["option_id"]),
            "category": item["kind"],
            "status": item["status"],
            "paid_cents": item["paid_cents"],
            "provides": deepcopy(item["provides"]),
            "attributes": deepcopy(item.get("attributes", {})),
        }

    def _public_option(self, option: dict[str, Any]) -> dict[str, Any]:
        return {
            "option_id": option["option_id"],
            "name": option.get("name", option["option_id"]),
            "category": option["kind"],
            "upfront_cents": option["upfront_cents"],
            "monthly_cents": option.get("monthly_cents", 0),
            "horizon_months": option.get("horizon_months", 0),
            "total_charge_cents": self._option_charge(option),
            "provides": deepcopy(option["provides"]),
            "attributes": deepcopy(option.get("attributes", {})),
        }

    @staticmethod
    def _option_charge(option: dict[str, Any]) -> int:
        return int(option["upfront_cents"]) + int(
            option.get("monthly_cents", 0)
        ) * int(option.get("horizon_months", 0))


def contract_triggered(
    trigger: dict[str, Any],
    changed_boundary: set[str],
    boundary: list[dict[str, Any]],
) -> bool:
    entity_ids = set(trigger.get("entity_ids", []))
    kind = trigger["type"]
    if kind == "any_changed":
        return bool(entity_ids & changed_boundary)
    if kind == "all_changed":
        return bool(entity_ids) and entity_ids.issubset(changed_boundary)
    if kind == "changed_count_at_least":
        return (
            len(entity_ids & changed_boundary)
            >= int(trigger["count"])
        )
    if kind == "retained_paid_below":
        retained = sum(
            int(item["paid_cents"])
            for item in boundary
            if item["entity_id"] not in changed_boundary
            and (
                not entity_ids or item["entity_id"] in entity_ids
            )
        )
        return retained < int(trigger["threshold_cents"])
    raise ValueError(f"Unknown contract trigger type: {kind}")


def _compare(observed: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return observed == expected
    if op == "le":
        return observed is not None and observed <= expected
    if op == "ge":
        return observed is not None and observed >= expected
    if op == "in":
        return observed in expected
    raise ValueError(f"Unsupported comparison operator: {op}")
