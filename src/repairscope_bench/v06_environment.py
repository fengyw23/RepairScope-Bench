from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from state_bench.domains.customer_support.environment import (
    CustomerSupportEnvironment,
)
from state_bench.domains.customer_support.schemas import (
    CSEnvironmentData,
    Order,
    OrderItem,
)
from state_bench.domains.customer_support.tools import (
    TOOL_SCHEMAS as SUPPORT_TOOL_SCHEMAS,
)
from state_bench.domains.travel.environment import TravelEnvironment
from state_bench.domains.travel.schemas import EnvironmentData
from state_bench.domains.travel.tools import TOOL_SCHEMAS as TRAVEL_TOOL_SCHEMAS

from .environment import ActionResult


ACTIVE_ITEM_STATUSES = {
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "return_requested",
    "exchange_requested",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def _simple_schema(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        },
    }


def _normalize_upstream_schema(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": schema["name"],
        "description": schema["description"],
        "parameters": deepcopy(schema["parameters"]),
    }


TRAVEL_EXTENSION_TOOLS = [
    _simple_schema(
        "get_trip_services",
        "List the customer's active local-service reservations, such as transfers, passes, and dining.",
        {"user_id": {"type": "string"}},
        ["user_id"],
    ),
    _simple_schema(
        "get_service_details",
        "Retrieve one local-service reservation and its dates, location, paid amount, and status.",
        {"service_id": {"type": "string"}},
        ["service_id"],
    ),
    _simple_schema(
        "search_local_services",
        "Search live local-service inventory in one category.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _simple_schema(
        "book_local_service",
        "Book one currently available local-service option.",
        {
            "option_id": {"type": "string"},
            "user_id": {"type": "string"},
        },
        ["option_id", "user_id"],
    ),
    _simple_schema(
        "cancel_local_service",
        "Preview or confirm cancellation of one local-service reservation.",
        {
            "service_id": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["service_id"],
    ),
    _simple_schema(
        "get_contract_terms",
        "Read supplier, package, refund-protection, and settlement terms linked to one reservation.",
        {"entity_id": {"type": "string"}},
        ["entity_id"],
    ),
]


SUPPORT_EXTENSION_TOOLS = [
    _simple_schema(
        "get_customer_orders",
        "List all orders belonging to a customer.",
        {"customer_id": {"type": "string"}},
        ["customer_id"],
    ),
    _simple_schema(
        "purchase_product",
        "Purchase one in-stock product and create a persistent order and order item.",
        {
            "customer_id": {"type": "string"},
            "product_id": {"type": "string"},
        },
        ["customer_id", "product_id"],
    ),
    _simple_schema(
        "check_product_compatibility",
        "Check whether two products are compatible according to their published specifications.",
        {
            "left_product_id": {"type": "string"},
            "right_product_id": {"type": "string"},
        },
        ["left_product_id", "right_product_id"],
    ),
    _simple_schema(
        "get_contract_terms",
        "Read refund, bundle, rebate, licence, and service terms linked to one order item.",
        {"entity_id": {"type": "string"}},
        ["entity_id"],
    ),
]


def tool_definitions_v06(task: dict[str, Any]) -> list[dict[str, Any]]:
    if task["domain"] == "travel":
        base = [_normalize_upstream_schema(item) for item in TRAVEL_TOOL_SCHEMAS]
        return base + deepcopy(TRAVEL_EXTENSION_TOOLS)
    base = [_normalize_upstream_schema(item) for item in SUPPORT_TOOL_SCHEMAS]
    return base + deepcopy(SUPPORT_EXTENSION_TOOLS)


@dataclass(frozen=True)
class EconomicVector:
    irreversible_loss: int | float
    net_recovery_outlay: int | float

    def as_dict(self) -> dict[str, int | float]:
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


class StateBackedRecoveryEnvironment:
    """STATE-Bench domain runtime plus a recovery ledger and service extensions."""

    def __init__(self, task: dict[str, Any]):
        self.task = deepcopy(task)
        self.domain = task["domain"]
        raw_snapshot = deepcopy(task["failure_snapshot"])
        if self.domain == "travel":
            state_data = EnvironmentData.from_dict(raw_snapshot["state_bench"])
            self.upstream: TravelEnvironment | CustomerSupportEnvironment = (
                TravelEnvironment(state_data, task["now"])
            )
        else:
            state_data = CSEnvironmentData.from_dict(raw_snapshot["state_bench"])
            self.upstream = CustomerSupportEnvironment(state_data, task["now"])
        extension = raw_snapshot.get("extensions", {})
        self.services: dict[str, dict[str, Any]] = {
            item["service_id"]: deepcopy(item)
            for item in extension.get("services", [])
        }
        self.service_inventory: dict[str, dict[str, Any]] = {
            item["option_id"]: deepcopy(item)
            for item in extension.get("service_inventory", [])
        }
        self.option_metadata: dict[str, dict[str, Any]] = deepcopy(
            task.get("option_metadata", {})
        )
        self.contracts: list[dict[str, Any]] = deepcopy(task.get("contracts", []))
        self.boundary_commitments: dict[str, dict[str, Any]] = {
            item["entity_id"]: deepcopy(item)
            for item in task.get("boundary_commitments", [])
        }
        self.triggered_contracts: set[str] = set()
        self.event_log: list[dict[str, Any]] = []
        self.ledger: list[dict[str, Any]] = []
        self.policy_violations: list[dict[str, Any]] = []
        self._next_service_id = self._next_numeric_id(self.services, "SV-", 1)
        support_items = (
            self.upstream.order_items
            if isinstance(self.upstream, CustomerSupportEnvironment)
            else {}
        )
        support_orders = (
            self.upstream.orders
            if isinstance(self.upstream, CustomerSupportEnvironment)
            else {}
        )
        self._next_order_id = self._next_numeric_id(support_orders, "ORD-R", 1)
        self._next_item_id = self._next_numeric_id(support_items, "ITEM-R", 1)
        self._phase = "recovery"

    def clone(self) -> StateBackedRecoveryEnvironment:
        return deepcopy(self)

    @property
    def irreversible_loss(self) -> int | float:
        return sum(item["irreversible_loss_delta"] for item in self.ledger)

    @property
    def net_recovery_outlay(self) -> int | float:
        return sum(item["net_outlay_delta"] for item in self.ledger)

    @property
    def economic_vector(self) -> EconomicVector:
        return EconomicVector(self.irreversible_loss, self.net_recovery_outlay)

    @property
    def state_changing_actions(self) -> int:
        return sum(
            bool(event.get("state_changed")) and event["result"]["ok"]
            for event in self.event_log
        )

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def execute_tool(self, name: str, args: dict[str, Any]) -> ActionResult:
        before = self.normalized_state()
        before_dispositions = self.dispositions()
        before_entities = self._entity_records()
        try:
            raw = self._dispatch(name, deepcopy(args))
            if isinstance(raw, ActionResult):
                result = raw
            else:
                ok = "error" not in raw and raw.get("status") != "rejected"
                result = ActionResult(ok, self._message_for(raw), deepcopy(raw))
        except (KeyError, TypeError, ValueError) as error:
            result = ActionResult(False, str(error))
        after = self.normalized_state()
        state_changed = before != after
        event = {
            "phase": self._phase,
            "tool": name,
            "arguments": deepcopy(args),
            "result": result.as_dict(),
            "state_changed": state_changed,
        }
        self.event_log.append(event)

        if result.ok and state_changed:
            after_entities = self._entity_records()
            self._record_economic_effect(
                name,
                result,
                before_entities,
                after_entities,
                before_dispositions,
            )
        return result

    def _dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any] | ActionResult:
        if name == "get_contract_terms":
            return self._get_contract_terms(args["entity_id"])
        if self.domain == "travel":
            return self._dispatch_travel(name, args)
        return self._dispatch_support(name, args)

    def _dispatch_travel(
        self, name: str, args: dict[str, Any]
    ) -> dict[str, Any] | ActionResult:
        assert isinstance(self.upstream, TravelEnvironment)
        if name == "get_user_reservations":
            raw = self.upstream.get_user_reservations(args)
            if "error" not in raw:
                raw["service_ids"] = [
                    item["service_id"]
                    for item in self.services.values()
                    if item["user_id"] == args["user_id"]
                ]
            return raw
        if name == "get_trip_services":
            return {
                "user_id": args["user_id"],
                "services": [
                    {
                        "service_id": item["service_id"],
                        "option_id": item["option_id"],
                        "category": item["slot"],
                        "status": item["status"],
                    }
                    for item in self.services.values()
                    if item["user_id"] == args["user_id"]
                ],
            }
        if name == "get_service_details":
            item = self.services.get(args["service_id"])
            return deepcopy(item) if item else {"error": "Service reservation not found."}
        if name == "search_local_services":
            return {
                "category": args["category"],
                "results": [
                    self._public_option(item)
                    for item in self.service_inventory.values()
                    if item["slot"] == args["category"] and item.get("available", False)
                ],
            }
        if name == "book_local_service":
            return self._book_local_service(args)
        if name == "cancel_local_service":
            return self._cancel_local_service(args)
        handler = self.upstream.tool_handlers.get(name)
        if handler is None:
            return {"error": f"Unknown travel operation: {name}"}
        return handler(args)

    def _dispatch_support(
        self, name: str, args: dict[str, Any]
    ) -> dict[str, Any] | ActionResult:
        assert isinstance(self.upstream, CustomerSupportEnvironment)
        if name == "get_customer_orders":
            customer_id = args["customer_id"]
            return {
                "customer_id": customer_id,
                "order_ids": sorted(
                    order.order_id
                    for order in self.upstream.orders.values()
                    if order.customer_id == customer_id
                ),
            }
        if name == "purchase_product":
            return self._purchase_product(args)
        if name == "get_product_details":
            raw = self.upstream.get_product_details(args)
            metadata = self.option_metadata.get(args["product_id"], {})
            if "error" not in raw:
                raw.update(deepcopy(metadata.get("attributes", {})))
                raw["benchmark_slot"] = metadata.get("slot")
            return raw
        if name == "check_product_compatibility":
            left = args["left_product_id"]
            right = args["right_product_id"]
            return {
                "left_product_id": left,
                "right_product_id": right,
                "compatible": self._options_compatible(left, right),
            }
        handler = self.upstream.tool_handlers.get(name)
        if handler is None:
            return {"error": f"Unknown support operation: {name}"}
        return handler(args)

    def _book_local_service(self, args: dict[str, Any]) -> dict[str, Any]:
        option = self.service_inventory.get(args["option_id"])
        if option is None:
            return {"error": f"Unknown service option {args['option_id']}."}
        if not option.get("available", False):
            return {
                "error": option.get(
                    "failure_message", f"Service option {args['option_id']} is unavailable."
                )
            }
        service_id = f"SV-{self._next_service_id:04d}"
        self._next_service_id += 1
        self.services[service_id] = {
            "service_id": service_id,
            "user_id": args["user_id"],
            "option_id": option["option_id"],
            "slot": option["slot"],
            "status": "confirmed",
            "price_paid": option["price"],
            "refund_amount": None,
            "cancellation_fee": None,
            "attributes": deepcopy(option.get("attributes", {})),
        }
        return {
            "status": "confirmed",
            "service_id": service_id,
            "option_id": option["option_id"],
            "charge": option["price"],
        }

    def _cancel_local_service(self, args: dict[str, Any]) -> dict[str, Any]:
        item = self.services.get(args["service_id"])
        if item is None or item["status"] != "confirmed":
            return {"error": "No active service reservation with that ID."}
        base_refund = item["price_paid"]
        if not args.get("confirm", False):
            return {
                "status": "preview",
                "service_id": item["service_id"],
                "base_refund": base_refund,
                "base_cancellation_fee": 0,
                "note": "Linked supplier or package terms are available separately.",
            }
        item["status"] = "cancelled"
        item["refund_amount"] = base_refund
        item["cancellation_fee"] = 0
        return {
            "status": "cancelled",
            "service_id": item["service_id"],
            "refund_amount": base_refund,
            "cancellation_fee": 0,
        }

    def _purchase_product(self, args: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(self.upstream, CustomerSupportEnvironment)
        product = self.upstream.products.get(args["product_id"])
        if product is None:
            return {"error": f"Unknown product {args['product_id']}."}
        if not product.in_stock:
            metadata = self.option_metadata.get(args["product_id"], {})
            return {
                "error": metadata.get(
                    "failure_message", f"Product {args['product_id']} is out of stock."
                )
            }
        if args["customer_id"] not in self.upstream.customers:
            return {"error": f"Unknown customer {args['customer_id']}."}
        order_id = f"ORD-R{self._next_order_id:04d}"
        item_id = f"ITEM-R{self._next_item_id:04d}"
        self._next_order_id += 1
        self._next_item_id += 1
        price = product.current_price if product.current_price is not None else product.price
        self.upstream.orders[order_id] = Order(
            order_id=order_id,
            customer_id=args["customer_id"],
            order_date=self.task["now"],
            status="processing",
            shipping_status="pending",
            shipping_method="standard",
            shipping_cost=0,
            payment_method="credit_card",
            payment_details={"credit_card": price},
            subtotal=price,
            total_paid=price,
        )
        self.upstream.order_items[item_id] = OrderItem(
            item_id=item_id,
            order_id=order_id,
            product_id=product.product_id,
            quantity=1,
            unit_price=price,
            item_status="processing",
        )
        return {
            "status": "confirmed",
            "order_id": order_id,
            "item_id": item_id,
            "product_id": product.product_id,
            "charge": price,
        }

    def _get_contract_terms(self, entity_id: str) -> dict[str, Any]:
        if entity_id not in self._entity_records():
            return {"error": f"Unknown reservation or order item {entity_id}."}
        terms = [
            {
                "contract_id": item["contract_id"],
                "description": item["description"],
                "trigger": item["trigger"],
                "refund_adjustment": item.get("refund_adjustment", 0),
                "settlement_charge": item.get("settlement_charge", 0),
                "linked_entity_ids": deepcopy(item["entity_ids"]),
            }
            for item in self.contracts
            if entity_id in item["entity_ids"]
        ]
        return {"entity_id": entity_id, "terms": terms}

    def _record_economic_effect(
        self,
        tool_name: str,
        result: ActionResult,
        before_entities: dict[str, dict[str, Any]],
        after_entities: dict[str, dict[str, Any]],
        before_dispositions: dict[str, str],
    ) -> None:
        data = dict(result.data or {})
        charge = 0
        refund = 0
        base_loss = 0
        if tool_name in {
            "create_booking",
            "book_hotel",
            "book_car_rental",
            "book_local_service",
            "purchase_product",
        }:
            charge = self._new_charge(before_entities, after_entities)
        elif tool_name in {
            "cancel_booking",
            "cancel_hotel_reservation",
            "cancel_car_rental",
            "cancel_local_service",
            "cancel_order",
            "process_return",
        }:
            refund = data.get("refund_amount", 0) or 0
            changed_to_inactive = [
                identifier
                for identifier, before in before_entities.items()
                if before.get("active")
                and not after_entities.get(identifier, {}).get("active", False)
            ]
            paid = sum(before_entities[item].get("paid_value", 0) for item in changed_to_inactive)
            base_loss = max(0, paid - refund)
        elif tool_name in {"update_booking", "process_exchange"}:
            charge = data.get("customer_pays", 0) or 0
            refund = data.get("store_credit_refund", 0) or 0
            fee = data.get("change_fee", 0) or 0
            base_loss = fee

        entry = {
            "event_index": len(self.ledger) + 1,
            "tool": tool_name,
            "charge": charge,
            "refund": refund,
            "contract_refund_adjustment": 0,
            "settlement_charge": 0,
            "irreversible_loss_delta": base_loss,
            "net_outlay_delta": charge - refund,
        }
        if any((charge, refund, base_loss)):
            self.ledger.append(entry)

        after_dispositions = self.dispositions()
        newly_changed = {
            identifier
            for identifier, disposition in after_dispositions.items()
            if disposition != "KEEP"
            and before_dispositions.get(identifier, "KEEP") == "KEEP"
        }
        if newly_changed:
            self._apply_contracts(newly_changed, result)

    def _apply_contracts(
        self, changed_entity_ids: set[str], result: ActionResult
    ) -> None:
        adjustments: list[dict[str, Any]] = []
        for contract in self.contracts:
            contract_id = contract["contract_id"]
            if contract_id in self.triggered_contracts:
                continue
            linked = set(contract["entity_ids"])
            trigger = contract.get("trigger", "any_changed")
            applies = (
                bool(changed_entity_ids & linked)
                if trigger == "any_changed"
                else linked.issubset(
                    {
                        identifier
                        for identifier, value in self.dispositions().items()
                        if value != "KEEP"
                    }
                )
            )
            if not applies:
                continue
            dispositions = self.dispositions()
            required_dispositions = set(contract.get("dispositions", []))
            if required_dispositions and not any(
                dispositions.get(identifier) in required_dispositions
                for identifier in linked
            ):
                continue
            self.triggered_contracts.add(contract_id)
            refund_adjustment = contract.get("refund_adjustment", 0)
            settlement = contract.get("settlement_charge", 0)
            self.ledger.append(
                {
                    "event_index": len(self.ledger) + 1,
                    "tool": "contract_settlement",
                    "contract_id": contract_id,
                    "charge": 0,
                    "refund": 0,
                    "contract_refund_adjustment": refund_adjustment,
                    "settlement_charge": settlement,
                    "irreversible_loss_delta": settlement - refund_adjustment,
                    "net_outlay_delta": settlement - refund_adjustment,
                }
            )
            self._apply_refund_adjustment(changed_entity_ids & linked, refund_adjustment)
            adjustments.append(
                {
                    "contract_id": contract_id,
                    "refund_adjustment": refund_adjustment,
                    "settlement_charge": settlement,
                }
            )
        if adjustments and isinstance(result.data, dict):
            result.data["contract_adjustments_applied"] = adjustments

    def _apply_refund_adjustment(
        self, entity_ids: set[str], adjustment: int | float
    ) -> None:
        if adjustment == 0 or not entity_ids:
            return
        share = adjustment / len(entity_ids)
        for entity_id in entity_ids:
            record = self._find_mutable_entity(entity_id)
            if record is None:
                continue
            current = getattr(record, "refund_amount", None)
            if current is None and isinstance(record, dict):
                current = record.get("refund_amount")
            current = current or 0
            new_value = max(0, current + share)
            if isinstance(record, dict):
                record["refund_amount"] = new_value
                record["cancellation_fee"] = max(
                    0, record.get("price_paid", 0) - new_value
                )
            else:
                record.refund_amount = new_value
                if hasattr(record, "cancellation_fee"):
                    paid = self._paid_value_for_entity(entity_id)
                    record.cancellation_fee = max(0, paid - new_value)

    def normalized_state(self) -> dict[str, Any]:
        return {
            "state_bench": self._export_upstream(),
            "extensions": {
                "services": sorted(
                    (deepcopy(item) for item in self.services.values()),
                    key=lambda item: item["service_id"],
                ),
                "service_inventory": sorted(
                    (deepcopy(item) for item in self.service_inventory.values()),
                    key=lambda item: item["option_id"],
                ),
            },
        }

    def state_key(self) -> str:
        state = self.normalized_state()
        state["extensions"].pop("service_inventory", None)
        return snapshot_hash(state)

    def active_options_by_slot(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for entity_id, record in self._entity_records().items():
            if not record.get("active"):
                continue
            option_id = record.get("option_id")
            metadata = self.option_metadata.get(option_id, {})
            slot = metadata.get("slot") or record.get("slot")
            if not slot:
                continue
            result.setdefault(slot, []).append(
                {
                    "entity_id": entity_id,
                    "option_id": option_id,
                    "slot": slot,
                    "paid_value": record.get("paid_value", 0),
                    "attributes": deepcopy(metadata.get("attributes", {})),
                }
            )
        return result

    def dispositions(self) -> dict[str, str]:
        current = self._entity_records()
        active_by_slot = self.active_options_by_slot()
        result: dict[str, str] = {}
        for entity_id, original in self.boundary_commitments.items():
            now = current.get(entity_id)
            if now and now.get("active"):
                result[entity_id] = (
                    "KEEP"
                    if now.get("option_id") == original["option_id"]
                    else "MODIFY"
                )
                continue
            replacements = [
                item
                for item in active_by_slot.get(original["slot"], [])
                if item["entity_id"] != entity_id
            ]
            result[entity_id] = "REPLACE" if replacements else "CANCEL"
        return result

    def changed_boundary_entities(self) -> set[str]:
        return {
            identifier
            for identifier, disposition in self.dispositions().items()
            if disposition != "KEEP"
        }

    def integrity_violations(self) -> list[dict[str, Any]]:
        """Return deterministic database-reference and ledger-integrity errors."""
        violations: list[dict[str, Any]] = []
        if isinstance(self.upstream, TravelEnvironment):
            for item in self.upstream.bookings.values():
                if item.user_id not in self.upstream.users:
                    violations.append(
                        {
                            "kind": "missing_user_reference",
                            "entity_id": item.booking_id,
                            "reference": item.user_id,
                        }
                    )
                if item.flight_id not in self.upstream.flights:
                    violations.append(
                        {
                            "kind": "missing_flight_reference",
                            "entity_id": item.booking_id,
                            "reference": item.flight_id,
                        }
                    )
            for item in self.upstream.hotels.values():
                if item.user_id not in self.upstream.users:
                    violations.append(
                        {
                            "kind": "missing_user_reference",
                            "entity_id": item.reservation_id,
                            "reference": item.user_id,
                        }
                    )
                if item.hotel_id not in self.upstream.hotel_inventory:
                    violations.append(
                        {
                            "kind": "missing_hotel_reference",
                            "entity_id": item.reservation_id,
                            "reference": item.hotel_id,
                        }
                    )
            for item in self.upstream.car_rentals.values():
                if item.user_id not in self.upstream.users:
                    violations.append(
                        {
                            "kind": "missing_user_reference",
                            "entity_id": item.rental_id,
                            "reference": item.user_id,
                        }
                    )
                if item.car_id not in self.upstream.car_inventory:
                    violations.append(
                        {
                            "kind": "missing_car_reference",
                            "entity_id": item.rental_id,
                            "reference": item.car_id,
                        }
                    )
            for item in self.services.values():
                if item["user_id"] not in self.upstream.users:
                    violations.append(
                        {
                            "kind": "missing_user_reference",
                            "entity_id": item["service_id"],
                            "reference": item["user_id"],
                        }
                    )
                if item["option_id"] not in self.service_inventory:
                    violations.append(
                        {
                            "kind": "missing_service_option_reference",
                            "entity_id": item["service_id"],
                            "reference": item["option_id"],
                        }
                    )
        else:
            for item in self.upstream.orders.values():
                if item.customer_id not in self.upstream.customers:
                    violations.append(
                        {
                            "kind": "missing_customer_reference",
                            "entity_id": item.order_id,
                            "reference": item.customer_id,
                        }
                    )
            for item in self.upstream.order_items.values():
                if item.order_id not in self.upstream.orders:
                    violations.append(
                        {
                            "kind": "missing_order_reference",
                            "entity_id": item.item_id,
                            "reference": item.order_id,
                        }
                    )
                if item.product_id not in self.upstream.products:
                    violations.append(
                        {
                            "kind": "missing_product_reference",
                            "entity_id": item.item_id,
                            "reference": item.product_id,
                        }
                    )

        for expected_index, entry in enumerate(self.ledger, start=1):
            if entry.get("event_index") != expected_index:
                violations.append(
                    {
                        "kind": "ledger_index_gap",
                        "expected": expected_index,
                        "observed": entry.get("event_index"),
                    }
                )
            expected_outlay = (
                entry.get("charge", 0)
                - entry.get("refund", 0)
                + entry.get("settlement_charge", 0)
                - entry.get("contract_refund_adjustment", 0)
            )
            if entry.get("net_outlay_delta") != expected_outlay:
                violations.append(
                    {
                        "kind": "ledger_outlay_mismatch",
                        "event_index": expected_index,
                        "expected": expected_outlay,
                        "observed": entry.get("net_outlay_delta"),
                    }
                )
        return violations

    def _entity_records(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if isinstance(self.upstream, TravelEnvironment):
            for item in self.upstream.bookings.values():
                result[item.booking_id] = {
                    "option_id": item.flight_id,
                    "active": item.status != "cancelled",
                    "paid_value": item.price_paid,
                }
            for item in self.upstream.hotels.values():
                result[item.reservation_id] = {
                    "option_id": item.hotel_id,
                    "active": item.status != "cancelled",
                    "paid_value": item.total_price,
                }
            for item in self.upstream.car_rentals.values():
                result[item.rental_id] = {
                    "option_id": item.car_id,
                    "active": item.status != "cancelled",
                    "paid_value": item.total_price,
                }
            for item in self.services.values():
                result[item["service_id"]] = {
                    "option_id": item["option_id"],
                    "active": item["status"] != "cancelled",
                    "paid_value": item["price_paid"],
                    "slot": item["slot"],
                }
        else:
            for item in self.upstream.order_items.values():
                result[item.item_id] = {
                    "option_id": item.product_id,
                    "active": item.item_status in ACTIVE_ITEM_STATUSES,
                    "paid_value": item.unit_price,
                }
        return result

    def _find_mutable_entity(self, entity_id: str) -> Any:
        if isinstance(self.upstream, TravelEnvironment):
            return (
                self.upstream.bookings.get(entity_id)
                or self.upstream.hotels.get(entity_id)
                or self.upstream.car_rentals.get(entity_id)
                or self.services.get(entity_id)
            )
        return self.upstream.order_items.get(entity_id)

    def _paid_value_for_entity(self, entity_id: str) -> int | float:
        return self._entity_records().get(entity_id, {}).get("paid_value", 0)

    def _new_charge(
        self,
        before: dict[str, dict[str, Any]],
        after: dict[str, dict[str, Any]],
    ) -> int | float:
        return sum(
            record.get("paid_value", 0)
            for identifier, record in after.items()
            if identifier not in before and record.get("active")
        )

    def _options_compatible(self, left: str, right: str) -> bool:
        for rule in self.task.get("compatibility_rules", []):
            pair = [left, right]
            reverse = [right, left]
            if pair in rule["pairs"] or reverse in rule["pairs"]:
                return True
            left_slot = self.option_metadata.get(left, {}).get("slot")
            right_slot = self.option_metadata.get(right, {}).get("slot")
            if {left_slot, right_slot} == {
                rule["left_slot"],
                rule["right_slot"],
            }:
                return False
        return True

    def _export_upstream(self) -> dict[str, Any]:
        if isinstance(self.upstream, TravelEnvironment):
            return {
                "flights": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.flights.values(), key=lambda item: item.flight_id
                    )
                ],
                "bookings": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.bookings.values(), key=lambda item: item.booking_id
                    )
                ],
                "users": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.users.values(), key=lambda item: item.user_id
                    )
                ],
                "hotel_inventory": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.hotel_inventory.values(),
                        key=lambda item: item.hotel_id,
                    )
                ],
                "hotels": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.hotels.values(),
                        key=lambda item: item.reservation_id,
                    )
                ],
                "car_inventory": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.car_inventory.values(),
                        key=lambda item: item.car_id,
                    )
                ],
                "car_rentals": [
                    item.to_dict()
                    for item in sorted(
                        self.upstream.car_rentals.values(),
                        key=lambda item: item.rental_id,
                    )
                ],
            }
        return {
            "products": [
                item.to_dict()
                for item in sorted(
                    self.upstream.products.values(), key=lambda item: item.product_id
                )
            ],
            "orders": [
                item.to_dict()
                for item in sorted(
                    self.upstream.orders.values(), key=lambda item: item.order_id
                )
            ],
            "order_items": [
                item.to_dict()
                for item in sorted(
                    self.upstream.order_items.values(), key=lambda item: item.item_id
                )
            ],
            "customers": [
                item.to_dict()
                for item in sorted(
                    self.upstream.customers.values(),
                    key=lambda item: item.customer_id,
                )
            ],
            "warranties": [
                item.to_dict()
                for item in sorted(
                    self.upstream.warranties.values(),
                    key=lambda item: item.warranty_id,
                )
            ],
        }

    @staticmethod
    def _message_for(raw: dict[str, Any]) -> str:
        if "error" in raw:
            return str(raw["error"])
        if "message" in raw:
            return str(raw["message"])
        return str(raw.get("status", "Tool call completed."))

    @staticmethod
    def _public_option(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "option_id": item["option_id"],
            "category": item["slot"],
            "price": item["price"],
            **deepcopy(item.get("attributes", {})),
        }

    @staticmethod
    def _next_numeric_id(
        records: dict[str, Any], prefix: str, default: int
    ) -> int:
        values: list[int] = []
        for key in records:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix) :]
            if suffix.isdigit():
                values.append(int(suffix))
        return max(values, default=default - 1) + 1


def environment_from_task(task: dict[str, Any]) -> StateBackedRecoveryEnvironment:
    return StateBackedRecoveryEnvironment(task)
