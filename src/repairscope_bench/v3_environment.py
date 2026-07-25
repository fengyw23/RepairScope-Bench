from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from state_bench.domains.customer_support.environment import (
    CustomerSupportEnvironment,
)
from state_bench.domains.travel.environment import TravelEnvironment

from .environment import ActionResult
from .v06_environment import StateBackedRecoveryEnvironment, snapshot_hash


MONEY_KEYS = {
    "amount",
    "amount_paid",
    "base_cancellation_fee",
    "base_refund",
    "cancellation_fee",
    "cash_amount",
    "charge",
    "credit",
    "current_price",
    "customer_pays",
    "direct_refund",
    "fee",
    "monthly_price",
    "monthly_charge",
    "nightly_rate",
    "one_time_charge",
    "paid_value",
    "price",
    "price_difference",
    "price_paid",
    "post_purchase_cancellation_fee",
    "post_purchase_refund",
    "refund",
    "refund_amount",
    "restocking_fee",
    "settlement_charge",
    "shipping_cost",
    "store_credit_refund",
    "subtotal",
    "total_charge",
    "total_paid",
    "total_price",
    "unit_price",
    "upfront_price",
}


def money(amount_minor: int) -> dict[str, str]:
    sign = "-" if amount_minor < 0 else ""
    absolute = abs(int(amount_minor))
    return {
        "amount": f"{sign}{absolute // 100}.{absolute % 100:02d}",
        "currency": "USD",
    }


def _schema(
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


TRAVEL_TOOLS_V3 = [
    _schema(
        "list_trip_reservations",
        "List the customer's live flight, hotel, transfer, admission, and local-service reservations.",
        {"user_id": {"type": "string"}},
        ["user_id"],
    ),
    _schema(
        "get_travel_reservation",
        "Read one authoritative reservation, including what it covers, schedule, location, status, and amount paid.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "search_travel_options",
        "Search live inventory in a travel category. Results include coverage, location, schedule, and prices.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _schema(
        "get_travel_terms",
        "Read authoritative refund, package, threshold, recurring-charge, and settlement terms linked to a reservation or option.",
        {"record_id": {"type": "string"}},
        ["record_id"],
    ),
    _schema(
        "check_travel_compatibility",
        "Check whether two travel options can coexist under the current itinerary and supplier rules.",
        {
            "left_option_id": {"type": "string"},
            "right_option_id": {"type": "string"},
        },
        ["left_option_id", "right_option_id"],
    ),
    _schema(
        "preview_travel_cancellation",
        "Preview the direct refund and fee for one reservation without changing state.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "cancel_travel_reservation",
        "Cancel one reservation after reviewing its terms and preview.",
        {
            "reservation_id": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["reservation_id", "confirm"],
    ),
    _schema(
        "book_travel_option",
        "Create a persistent booking for one live flight, hotel, or local-service option.",
        {
            "option_id": {"type": "string"},
            "user_id": {"type": "string"},
        },
        ["option_id", "user_id"],
    ),
]


AFTER_SALES_TOOLS_V3 = [
    _schema(
        "list_customer_orders",
        "List the customer's live product, warranty, licence, and service order items.",
        {"customer_id": {"type": "string"}},
        ["customer_id"],
    ),
    _schema(
        "get_order_item",
        "Read one authoritative order item, including product coverage, quantity, compatibility attributes, status, and amount paid.",
        {"item_id": {"type": "string"}},
        ["item_id"],
    ),
    _schema(
        "search_product_options",
        "Search in-stock products, bundles, warranties, licences, and services in one category.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _schema(
        "get_product_terms",
        "Read authoritative return, bundle, threshold, licence, recurring-charge, and settlement terms linked to an item or product.",
        {"record_id": {"type": "string"}},
        ["record_id"],
    ),
    _schema(
        "check_product_compatibility",
        "Check whether two products or services can coexist under current specifications and contracts.",
        {
            "left_product_id": {"type": "string"},
            "right_product_id": {"type": "string"},
        },
        ["left_product_id", "right_product_id"],
    ),
    _schema(
        "preview_product_return",
        "Preview the direct refund and fee for one order item without changing state.",
        {"item_id": {"type": "string"}},
        ["item_id"],
    ),
    _schema(
        "return_product",
        "Return one order item after reviewing its terms and preview.",
        {
            "item_id": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["item_id", "confirm"],
    ),
    _schema(
        "purchase_product_option",
        "Purchase one in-stock product, bundle, warranty, licence, or service option.",
        {
            "product_id": {"type": "string"},
            "customer_id": {"type": "string"},
        },
        ["product_id", "customer_id"],
    ),
]


def tool_definitions_v3(task: dict[str, Any]) -> list[dict[str, Any]]:
    if task["domain"] == "travel":
        return deepcopy(TRAVEL_TOOLS_V3)
    if task["domain"] == "after_sales":
        return deepcopy(AFTER_SALES_TOOLS_V3)
    raise ValueError(f"Unsupported v3 domain: {task['domain']}")


@dataclass(frozen=True)
class EconomicEvent:
    event_index: int
    category: str
    debit_minor: int
    credit_minor: int
    source: str
    source_record_id: str | None = None

    @property
    def net_minor(self) -> int:
        return self.debit_minor - self.credit_minor

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_index": self.event_index,
            "category": self.category,
            "debit_minor": self.debit_minor,
            "credit_minor": self.credit_minor,
            "net_minor": self.net_minor,
            "currency": "USD",
            "source": self.source,
            "source_record_id": self.source_record_id,
        }


class NativeRecoveryEnvironmentV3:
    """Two native STATE-Bench domains with a shared audit-only interface."""

    def __init__(self, task: dict[str, Any]):
        self.task = deepcopy(task)
        self.domain = task["domain"]
        base_task = deepcopy(task)
        # v0.6's runtime supplies the tested STATE-Bench persistence adapter.
        # v3 owns all economics, so the old two-dimensional contract layer is disabled.
        base_task["domain"] = (
            "travel" if self.domain == "travel" else "customer_support"
        )
        base_task["contracts"] = []
        self._base = StateBackedRecoveryEnvironment(base_task)
        self.upstream = self._base.upstream
        self.option_metadata = deepcopy(task["option_metadata"])
        self.boundary = {
            item["entity_id"]: deepcopy(item)
            for item in task.get("boundary_commitments", [])
        }
        self.terms = deepcopy(task.get("economic_terms", []))
        self.event_log: list[dict[str, Any]] = []
        self._economic_events: list[EconomicEvent] = []
        self._base_ledger_cursor = 0
        self._active_settlements: set[str] = set()

    def clone(self) -> NativeRecoveryEnvironmentV3:
        return deepcopy(self)

    @property
    def incremental_recovery_cost_minor(self) -> int:
        return sum(item.net_minor for item in self._economic_events)

    @property
    def state_changing_actions(self) -> int:
        return sum(
            bool(item.get("state_changed")) and item["result"].get("ok", False)
            for item in self.event_log
        )

    def economic_events(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self._economic_events]

    def normalized_state(self) -> dict[str, Any]:
        return self._base.normalized_state()

    def state_fingerprint(self) -> str:
        return self._base.state_key()

    def native_runtime_name(self) -> str:
        if isinstance(self.upstream, TravelEnvironment):
            return "state_bench.domains.travel.TravelEnvironment"
        if isinstance(self.upstream, CustomerSupportEnvironment):
            return "state_bench.domains.customer_support.CustomerSupportEnvironment"
        raise AssertionError("Unexpected STATE-Bench runtime")

    def active_records(self) -> list[dict[str, Any]]:
        raw = self._base._entity_records()
        records: list[dict[str, Any]] = []
        for entity_id, record in raw.items():
            if not record.get("active"):
                continue
            option_id = record["option_id"]
            metadata = self.option_metadata.get(option_id, {})
            records.append(
                {
                    "entity_id": entity_id,
                    "option_id": option_id,
                    "category": metadata.get("slot", record.get("slot")),
                    "provides": deepcopy(metadata.get("provides", {})),
                    "attributes": deepcopy(metadata.get("attributes", {})),
                    "paid_minor": int(round(record.get("paid_value", 0) * 100)),
                }
            )
        return sorted(records, key=lambda item: item["entity_id"])

    def canonical_scope(self) -> dict[str, Any]:
        current = {
            item["entity_id"]: item for item in self.active_records()
        }
        boundary_ids = set(self.boundary)
        boundary_scope: dict[str, str] = {}
        for entity_id, original in self.boundary.items():
            record = current.get(entity_id)
            if record is None:
                boundary_scope[entity_id] = "CANCEL"
            elif record["option_id"] == original["option_id"]:
                boundary_scope[entity_id] = "KEEP"
            else:
                boundary_scope[entity_id] = "MODIFY"
        return {
            "boundary": boundary_scope,
            "added_option_ids": sorted(
                item["option_id"]
                for item in current.values()
                if item["entity_id"] not in boundary_ids
            ),
        }

    def execute_tool(self, name: str, args: dict[str, Any]) -> ActionResult:
        before = self.normalized_state()
        before_records = {
            item["entity_id"]: item for item in self.active_records()
        }
        try:
            if self.domain == "travel":
                raw = self._dispatch_travel(name, deepcopy(args))
            else:
                raw = self._dispatch_after_sales(name, deepcopy(args))
            result = raw if isinstance(raw, ActionResult) else ActionResult(
                "error" not in raw and raw.get("status") != "rejected",
                str(raw.get("message", raw.get("status", raw.get("error", "completed")))),
                deepcopy(raw),
            )
        except (KeyError, TypeError, ValueError) as error:
            result = ActionResult(False, str(error))
        self._sync_direct_economics()
        post_purchase_fee = self._apply_post_purchase_cancellation_fee(
            name, args, before_records, before, result
        )
        settlement_changes = self._reconcile_settlements()
        after = self.normalized_state()
        adjustments = []
        if post_purchase_fee is not None:
            adjustments.append(post_purchase_fee)
        adjustments.extend(settlement_changes)
        if adjustments and result.ok and isinstance(result.data, dict):
            result.data["economic_adjustments"] = adjustments
        public_result = ActionResult(
            result.ok,
            result.message,
            _format_public_money(result.data),
        )
        self.event_log.append(
            {
                "tool": name,
                "arguments": deepcopy(args),
                "result": public_result.as_dict(),
                "state_changed": before != after,
            }
        )
        return public_result

    def _dispatch_travel(
        self, name: str, args: dict[str, Any]
    ) -> dict[str, Any] | ActionResult:
        assert isinstance(self.upstream, TravelEnvironment)
        if name == "list_trip_reservations":
            return self._list_travel(args["user_id"])
        if name == "get_travel_reservation":
            return self._travel_record(args["reservation_id"])
        if name == "search_travel_options":
            return self._search_options(args["category"])
        if name == "get_travel_terms":
            return self._terms_for(args["record_id"])
        if name == "check_travel_compatibility":
            return self._compatibility(
                args["left_option_id"], args["right_option_id"]
            )
        if name == "preview_travel_cancellation":
            return self._travel_cancel(args["reservation_id"], False)
        if name == "cancel_travel_reservation":
            if not args.get("confirm", False):
                return {"error": "Set confirm=true after reviewing the preview."}
            return self._travel_cancel(args["reservation_id"], True)
        if name == "book_travel_option":
            return self._book_travel(args["option_id"], args["user_id"])
        return {"error": f"Unknown travel operation: {name}"}

    def _dispatch_after_sales(
        self, name: str, args: dict[str, Any]
    ) -> dict[str, Any] | ActionResult:
        assert isinstance(self.upstream, CustomerSupportEnvironment)
        if name == "list_customer_orders":
            return self._list_after_sales(args["customer_id"])
        if name == "get_order_item":
            return self._after_sales_record(args["item_id"])
        if name == "search_product_options":
            return self._search_options(args["category"])
        if name == "get_product_terms":
            # STATE-Bench requires a policy read before cancellation writes.
            self._base.execute_tool("get_policies", {"topic": "cancellation"})
            return self._terms_for(args["record_id"])
        if name == "check_product_compatibility":
            return self._compatibility(
                args["left_product_id"], args["right_product_id"]
            )
        if name == "preview_product_return":
            return self._support_cancel(args["item_id"], False)
        if name == "return_product":
            if not args.get("confirm", False):
                return {"error": "Set confirm=true after reviewing the preview."}
            return self._support_cancel(args["item_id"], True)
        if name == "purchase_product_option":
            return self._base.execute_tool(
                "purchase_product",
                {
                    "customer_id": args["customer_id"],
                    "product_id": args["product_id"],
                },
            )
        return {"error": f"Unknown after-sales operation: {name}"}

    def _list_travel(self, user_id: str) -> dict[str, Any]:
        active = self.active_records()
        return {
            "user_id": user_id,
            "reservations": [
                {
                    "reservation_id": item["entity_id"],
                    "option_id": item["option_id"],
                    "category": item["category"],
                    "status": "confirmed",
                }
                for item in active
            ],
        }

    def _list_after_sales(self, customer_id: str) -> dict[str, Any]:
        active = self.active_records()
        return {
            "customer_id": customer_id,
            "items": [
                {
                    "item_id": item["entity_id"],
                    "product_id": item["option_id"],
                    "category": item["category"],
                    "status": "active",
                }
                for item in active
            ],
        }

    def _travel_record(self, entity_id: str) -> dict[str, Any]:
        return self._record_details(entity_id, "reservation_id")

    def _after_sales_record(self, entity_id: str) -> dict[str, Any]:
        return self._record_details(entity_id, "item_id")

    def _record_details(self, entity_id: str, id_key: str) -> dict[str, Any]:
        record = next(
            (item for item in self.active_records() if item["entity_id"] == entity_id),
            None,
        )
        if record is None:
            return {"error": f"No active record {entity_id}."}
        metadata = self.option_metadata[record["option_id"]]
        return {
            id_key: entity_id,
            "option_id": record["option_id"],
            "name": metadata["name"],
            "category": metadata["slot"],
            "status": "active",
            "covers": _public_coverage(metadata.get("provides", {})),
            "attributes": deepcopy(metadata.get("attributes", {})),
            "amount_paid": metadata["total_charge_minor"] / 100,
        }

    def _search_options(self, category: str) -> dict[str, Any]:
        results = []
        active_option_ids = {item["option_id"] for item in self.active_records()}
        for option_id, metadata in self.option_metadata.items():
            if (
                not metadata.get("available", False)
                or metadata.get("slot") != category
                or option_id in active_option_ids
            ):
                continue
            results.append(
                {
                    "option_id": option_id,
                    "name": metadata["name"],
                    "category": metadata["slot"],
                    "covers": _public_coverage(metadata.get("provides", {})),
                    "attributes": deepcopy(metadata.get("attributes", {})),
                    "upfront_price": metadata.get("upfront_minor", 0) / 100,
                    "monthly_price": metadata.get("monthly_minor", 0) / 100,
                    "billing_months": metadata.get("horizon_months", 0),
                    "total_charge": metadata["total_charge_minor"] / 100,
                }
            )
        return {"category": category, "results": results}

    def _terms_for(self, record_id: str) -> dict[str, Any]:
        entity = self.boundary.get(record_id)
        active_record = next(
            (
                item
                for item in self.active_records()
                if item["entity_id"] == record_id
            ),
            None,
        )
        option_id = (
            entity["option_id"]
            if entity
            else active_record["option_id"]
            if active_record
            else record_id
        )
        if option_id not in self.option_metadata:
            return {"error": f"Unknown reservation, item, or option {record_id}."}
        linked_terms = []
        for term in self.terms:
            linked = set(term.get("linked_entity_ids", []))
            linked.update(term.get("linked_option_ids", []))
            if record_id not in linked and option_id not in linked:
                continue
            linked_terms.append(
                {
                    "term_id": term["term_id"],
                    "description": term["description"],
                    "trigger": deepcopy(term["trigger"]),
                    "one_time_charge": int(
                        term.get("charge_minor", 0)
                    )
                    / 100,
                    "monthly_charge": int(
                        term.get("monthly_minor", 0)
                    )
                    / 100,
                    "billing_months": int(
                        term.get("horizon_months", 0)
                    ),
                    "total_charge": term_charge_minor(term) / 100,
                    "credit": term_credit_minor(term) / 100,
                }
            )
        metadata = self.option_metadata.get(option_id, {})
        post_purchase_fee = int(
            metadata.get("post_purchase_cancel_fee_minor", 0)
        )
        post_purchase_refund = max(
            0,
            int(metadata.get("total_charge_minor", 0))
            - post_purchase_fee,
        )
        direct_refund_minor = (
            int(entity.get("refund_minor", 0))
            if entity
            else post_purchase_refund
            if active_record
            else 0
        )
        return {
            "record_id": record_id,
            "direct_refund": direct_refund_minor / 100,
            "post_purchase_cancellation_fee": post_purchase_fee / 100,
            "post_purchase_refund": post_purchase_refund / 100,
            "linked_terms": linked_terms,
        }

    def _compatibility(self, left: str, right: str) -> dict[str, Any]:
        known = set(self.option_metadata)
        if left not in known or right not in known:
            return {"error": "Unknown option identifier."}
        return {
            "left_option_id": left,
            "right_option_id": right,
            "compatible": options_compatible(self.task, left, right),
        }

    def _travel_cancel(
        self, entity_id: str, confirm: bool
    ) -> dict[str, Any] | ActionResult:
        if entity_id in self.upstream.bookings:
            return self._base.execute_tool(
                "cancel_booking",
                {"booking_id": entity_id, **({"confirm": True} if confirm else {})},
            )
        if entity_id in self.upstream.hotels:
            return self._base.execute_tool(
                "cancel_hotel_reservation",
                {
                    "reservation_id": entity_id,
                    **({"confirm": True} if confirm else {}),
                },
            )
        if entity_id in self.upstream.car_rentals:
            return self._base.execute_tool(
                "cancel_car_rental",
                {"rental_id": entity_id, **({"confirm": True} if confirm else {})},
            )
        if entity_id in self._base.services:
            return self._base.execute_tool(
                "cancel_local_service",
                {"service_id": entity_id, "confirm": confirm},
            )
        return {"error": f"Unknown reservation {entity_id}."}

    def _book_travel(
        self, option_id: str, user_id: str
    ) -> dict[str, Any] | ActionResult:
        metadata = self.option_metadata.get(option_id)
        if metadata is None:
            return {"error": f"Unknown travel option {option_id}."}
        native_kind = metadata["native_kind"]
        if native_kind == "flight":
            return self._base.execute_tool(
                "create_booking",
                {
                    "flight_id": option_id,
                    "user_id": user_id,
                    "cabin_class": "economy",
                    "seat_type": "aisle",
                    "meal_preference": "standard",
                    "add_wifi": False,
                    "add_extra_legroom": False,
                    "add_insurance": False,
                    "payment_method": "credit_card",
                },
            )
        if native_kind == "hotel":
            return self._base.execute_tool(
                "book_hotel", {"hotel_id": option_id, "user_id": user_id}
            )
        return self._base.execute_tool(
            "book_local_service", {"option_id": option_id, "user_id": user_id}
        )

    def _support_cancel(
        self, item_id: str, confirm: bool
    ) -> dict[str, Any] | ActionResult:
        item = self.upstream.order_items.get(item_id)
        if item is None:
            return {"error": f"Unknown order item {item_id}."}
        return self._base.execute_tool(
            "cancel_order",
            {
                "order_id": item.order_id,
                **({"confirm": True} if confirm else {}),
            },
        )

    def _sync_direct_economics(self) -> None:
        while self._base_ledger_cursor < len(self._base.ledger):
            raw = self._base.ledger[self._base_ledger_cursor]
            self._base_ledger_cursor += 1
            debit = int(
                round(
                    (
                        raw.get("charge", 0)
                        + raw.get("settlement_charge", 0)
                    )
                    * 100
                )
            )
            credit = int(
                round(
                    (
                        raw.get("refund", 0)
                        + raw.get("contract_refund_adjustment", 0)
                    )
                    * 100
                )
            )
            if not debit and not credit:
                continue
            self._economic_events.append(
                EconomicEvent(
                    len(self._economic_events) + 1,
                    "direct_transaction",
                    debit,
                    credit,
                    str(raw.get("tool", "state_bench")),
                    raw.get("entity_id"),
                )
            )

    def _apply_post_purchase_cancellation_fee(
        self,
        name: str,
        args: dict[str, Any],
        before_records: dict[str, dict[str, Any]],
        before_state: dict[str, Any],
        result: ActionResult,
    ) -> dict[str, Any] | None:
        target_key = (
            "reservation_id"
            if name
            in {
                "preview_travel_cancellation",
                "cancel_travel_reservation",
            }
            else "item_id"
            if name in {"preview_product_return", "return_product"}
            else None
        )
        if target_key is None or not result.ok:
            return None
        entity_id = args.get(target_key)
        record = before_records.get(entity_id)
        if record is None or entity_id in self.boundary:
            return None
        metadata = self.option_metadata.get(record["option_id"], {})
        fee = int(metadata.get("post_purchase_cancel_fee_minor", 0))
        if fee <= 0:
            return None
        data = result.data if isinstance(result.data, dict) else {}
        raw_refund = data.get("refund_amount", data.get("base_refund", 0))
        raw_fee = data.get(
            "cancellation_fee", data.get("base_cancellation_fee", 0)
        )
        adjusted_refund = max(0.0, float(raw_refund or 0) - fee / 100)
        adjusted_fee = float(raw_fee or 0) + fee / 100
        if "refund_amount" in data:
            data["refund_amount"] = adjusted_refund
        elif "base_refund" in data:
            data["base_refund"] = adjusted_refund
        if "cancellation_fee" in data:
            data["cancellation_fee"] = adjusted_fee
        elif "base_cancellation_fee" in data:
            data["base_cancellation_fee"] = adjusted_fee

        confirmed = name in {
            "cancel_travel_reservation",
            "return_product",
        } and before_state != self.normalized_state()
        if not confirmed:
            return None
        self._economic_events.append(
            EconomicEvent(
                len(self._economic_events) + 1,
                "post_purchase_cancellation_fee",
                fee,
                0,
                name,
                str(entity_id),
            )
        )
        return {
            "source_record_id": entity_id,
            "kind": "post_purchase_cancellation_fee",
            "net_cost": money(fee),
            "status": "applied",
        }

    def _reconcile_settlements(self) -> list[dict[str, Any]]:
        active_now = {
            term["term_id"]
            for term in self.terms
            if term_triggered(self.task, term, self.canonical_scope(), self.active_records())
        }
        changes: list[dict[str, Any]] = []
        by_id = {item["term_id"]: item for item in self.terms}
        for term_id in sorted(active_now - self._active_settlements):
            term = by_id[term_id]
            debit = term_charge_minor(term)
            credit = term_credit_minor(term)
            self._economic_events.append(
                EconomicEvent(
                    len(self._economic_events) + 1,
                    "contract_settlement",
                    debit,
                    credit,
                    term_id,
                    term_id,
                )
            )
            changes.append(
                {
                    "term_id": term_id,
                    "net_cost": money(debit - credit),
                    "status": "applied",
                }
            )
        for term_id in sorted(self._active_settlements - active_now):
            term = by_id[term_id]
            debit = term_credit_minor(term)
            credit = term_charge_minor(term)
            self._economic_events.append(
                EconomicEvent(
                    len(self._economic_events) + 1,
                    "contract_reversal",
                    debit,
                    credit,
                    term_id,
                    term_id,
                )
            )
            changes.append(
                {
                    "term_id": term_id,
                    "net_cost": money(debit - credit),
                    "status": "reversed",
                }
            )
        self._active_settlements = active_now
        return changes


def options_compatible(task: dict[str, Any], left: str, right: str) -> bool:
    active_pair = {left, right}
    for rule in task.get("compatibility_rules", []):
        kind = rule["type"]
        if kind == "forbid_pair" and set(rule["option_ids"]) == active_pair:
            return False
    return True


def term_charge_minor(term: dict[str, Any]) -> int:
    return int(term.get("charge_minor", 0)) + int(
        term.get("monthly_minor", 0)
    ) * int(term.get("horizon_months", 0))


def term_credit_minor(term: dict[str, Any]) -> int:
    return int(term.get("credit_minor", 0))


def term_triggered(
    task: dict[str, Any],
    term: dict[str, Any],
    scope: dict[str, Any],
    active_records: list[dict[str, Any]],
) -> bool:
    trigger = term["trigger"]
    kind = trigger["type"]
    boundary_scope = scope["boundary"]
    changed = {
        entity_id
        for entity_id, disposition in boundary_scope.items()
        if disposition != "KEEP"
    }
    active_options = {item["option_id"] for item in active_records}
    entity_ids = set(trigger.get("entity_ids", []))
    option_ids = set(trigger.get("option_ids", []))
    if kind == "any_changed":
        return bool(changed & entity_ids)
    if kind == "all_changed":
        return bool(entity_ids) and entity_ids.issubset(changed)
    if kind == "changed_count_at_least":
        return len(changed & entity_ids) >= int(trigger["count"])
    if kind == "changed_with_retained":
        changed_ids = set(trigger["changed_entity_ids"])
        retained_ids = set(trigger["retained_entity_ids"])
        return bool(changed & changed_ids) and all(
            boundary_scope.get(entity_id) == "KEEP" for entity_id in retained_ids
        )
    if kind == "retained_paid_below":
        boundary = {
            item["entity_id"]: item for item in task["boundary_commitments"]
        }
        retained = sum(
            int(boundary[entity_id]["paid_minor"])
            for entity_id in entity_ids
            if boundary_scope.get(entity_id) == "KEEP"
        )
        return retained < int(trigger["threshold_minor"])
    if kind == "retained_quantity_below":
        boundary = {
            item["entity_id"]: item for item in task["boundary_commitments"]
        }
        retained = sum(
            int(boundary[entity_id].get("quantity", 1))
            for entity_id in entity_ids
            if boundary_scope.get(entity_id) == "KEEP"
        )
        return retained < int(trigger["quantity"])
    if kind == "active_any":
        return bool(active_options & option_ids)
    if kind == "active_all":
        return bool(option_ids) and option_ids.issubset(active_options)
    raise ValueError(f"Unsupported v3 term trigger: {kind}")


def _format_public_money(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: _format_public_money(item_value, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_format_public_money(item, key) for item in value]
    if (
        (key in MONEY_KEYS or (key is not None and key.endswith("_minor")))
        and isinstance(value, (int, float))
    ):
        if key is not None and key.endswith("_minor"):
            return money(int(value))
        return money(int(round(value * 100)))
    return deepcopy(value)


def _public_coverage(provides: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"requirement": key, "quantity": int(value)}
        for key, value in sorted(provides.items())
        if int(value) > 0
    ]


__all__ = [
    "AFTER_SALES_TOOLS_V3",
    "EconomicEvent",
    "NativeRecoveryEnvironmentV3",
    "TRAVEL_TOOLS_V3",
    "money",
    "options_compatible",
    "snapshot_hash",
    "term_charge_minor",
    "term_credit_minor",
    "term_triggered",
    "tool_definitions_v3",
]
