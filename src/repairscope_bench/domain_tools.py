from __future__ import annotations

from copy import deepcopy
from typing import Any

from .environment import ActionResult, RepairEnvironment


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


TRAVEL_TOOLS = [
    _schema(
        "get_user_reservations",
        "List the customer's active flight, hotel, and car reservations.",
    ),
    _schema(
        "get_booking",
        "Retrieve one flight booking, including route, dates, fare, and status.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "get_hotel_reservation",
        "Retrieve one hotel reservation, including dates, location, and status.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "get_car_rental",
        "Retrieve one car rental, including pickup/drop-off dates and status.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "search_flights",
        "Search currently available outbound, return, or single-flight options.",
        {"journey": {"type": "string", "enum": ["outbound", "return", "flight"]}},
        ["journey"],
    ),
    _schema(
        "search_hotels",
        "Search currently available hotel inventory for this trip.",
    ),
    _schema(
        "search_car_rentals",
        "Search currently available car-rental inventory for this trip.",
    ),
    _schema(
        "preview_cancellation",
        "Preview the refund and cancellation fee for one active reservation. No state is changed.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "get_change_quote",
        "Check whether a reservation can be changed to a specific option and return the quoted cash components.",
        {
            "reservation_id": {"type": "string"},
            "to_option_id": {"type": "string"},
        },
        ["reservation_id", "to_option_id"],
    ),
    _schema(
        "check_travel_compatibility",
        "Check whether two specific travel options satisfy a configured cross-booking compatibility rule.",
        {
            "left_option_id": {"type": "string"},
            "right_option_id": {"type": "string"},
        },
        ["left_option_id", "right_option_id"],
    ),
    _schema(
        "cancel_reservation",
        "Cancel one active reservation and apply the applicable refund.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "book_travel_option",
        "Book one currently available flight, hotel, or car option.",
        {"option_id": {"type": "string"}},
        ["option_id"],
    ),
    _schema(
        "change_reservation",
        "Apply an available in-place change to one reservation.",
        {
            "reservation_id": {"type": "string"},
            "to_option_id": {"type": "string"},
        },
        ["reservation_id", "to_option_id"],
    ),
    _schema("finish", "Declare that the customer's request is complete."),
    _schema(
        "report_infeasible",
        "Report that the request cannot be completed from the current state.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
]

TRAVEL_V05_TOOLS = [
    _schema(
        "get_user_reservations",
        "List every active reservation and service commitment for this trip.",
    ),
    _schema(
        "get_reservation_details",
        "Retrieve one reservation or service commitment, including its paid amount, schedule, location, and status.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "search_travel_options",
        "Search all currently available travel or local-service options in one category. Returned records include their city and dates for the agent to check.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _schema(
        "preview_cancellation",
        "Preview the refund and cancellation fee for one active reservation. No state is changed.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "get_change_quote",
        "Check whether a reservation can be changed to a specific option and return the quoted cash components.",
        {
            "reservation_id": {"type": "string"},
            "to_option_id": {"type": "string"},
        },
        ["reservation_id", "to_option_id"],
    ),
    _schema(
        "get_package_change_impact",
        "Retrieve settlement charges that would be triggered by changing or cancelling this reservation.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "check_travel_compatibility",
        "Check whether two specific travel options satisfy configured cross-booking rules.",
        {
            "left_option_id": {"type": "string"},
            "right_option_id": {"type": "string"},
        },
        ["left_option_id", "right_option_id"],
    ),
    _schema(
        "cancel_reservation",
        "Cancel one active reservation and apply its refund and any linked settlement terms.",
        {"reservation_id": {"type": "string"}},
        ["reservation_id"],
    ),
    _schema(
        "book_travel_option",
        "Book one currently available travel or local-service option.",
        {"option_id": {"type": "string"}},
        ["option_id"],
    ),
    _schema(
        "change_reservation",
        "Apply an available in-place change to one reservation.",
        {
            "reservation_id": {"type": "string"},
            "to_option_id": {"type": "string"},
        },
        ["reservation_id", "to_option_id"],
    ),
    _schema(
        "report_infeasible",
        "Report that the request cannot be completed from the current state.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
]


SHOPPING_TOOLS = [
    _schema(
        "get_customer_orders",
        "List the customer's active purchased products.",
    ),
    _schema(
        "get_product_order",
        "Retrieve one purchased product and its order details.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "search_products",
        "Search available products in a requested category.",
        {
            "category": {
                "type": "string",
                "enum": ["laptop", "monitor", "dock"],
            }
        },
        ["category"],
    ),
    _schema(
        "get_return_quote",
        "Preview the refund and restocking or return fee for one purchased product. No state is changed.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "get_exchange_quote",
        "Check whether an ordered product can be exchanged for a specific product and return the cash components.",
        {
            "order_id": {"type": "string"},
            "to_product_id": {"type": "string"},
        },
        ["order_id", "to_product_id"],
    ),
    _schema(
        "check_product_compatibility",
        "Check whether two specific products are compatible.",
        {
            "left_product_id": {"type": "string"},
            "right_product_id": {"type": "string"},
        },
        ["left_product_id", "right_product_id"],
    ),
    _schema(
        "return_product",
        "Return one active purchased product and apply its refund.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "purchase_product",
        "Purchase one currently available product.",
        {"product_id": {"type": "string"}},
        ["product_id"],
    ),
    _schema(
        "exchange_product",
        "Apply an available in-place exchange to one purchased product.",
        {
            "order_id": {"type": "string"},
            "to_product_id": {"type": "string"},
        },
        ["order_id", "to_product_id"],
    ),
    _schema("finish", "Declare that the customer's request is complete."),
    _schema(
        "report_infeasible",
        "Report that the request cannot be completed from the current state.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
]

SHOPPING_V05_TOOLS = [
    _schema(
        "get_customer_orders",
        "List every active product and service order in this purchase.",
    ),
    _schema(
        "get_product_order",
        "Retrieve one order, including its paid amount, product attributes, and status.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "search_products",
        "Search all currently available products or services in one category. Returned records include their delivery and approval attributes for the agent to check.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _schema(
        "get_return_quote",
        "Preview the refund and return fee for one purchased product. No state is changed.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "get_exchange_quote",
        "Check whether an order can be exchanged for a specific product and return the cash components.",
        {
            "order_id": {"type": "string"},
            "to_product_id": {"type": "string"},
        },
        ["order_id", "to_product_id"],
    ),
    _schema(
        "get_bundle_change_impact",
        "Retrieve rebates, licenses, or service charges triggered by changing or returning this order.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "check_product_compatibility",
        "Check whether two specific products are compatible.",
        {
            "left_product_id": {"type": "string"},
            "right_product_id": {"type": "string"},
        },
        ["left_product_id", "right_product_id"],
    ),
    _schema(
        "return_product",
        "Return one active purchased product and apply its refund and any linked settlement terms.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "purchase_product",
        "Purchase one currently available product or service.",
        {"product_id": {"type": "string"}},
        ["product_id"],
    ),
    _schema(
        "exchange_product",
        "Apply an available in-place exchange to one purchased product.",
        {
            "order_id": {"type": "string"},
            "to_product_id": {"type": "string"},
        },
        ["order_id", "to_product_id"],
    ),
    _schema(
        "report_infeasible",
        "Report that the request cannot be completed from the current state.",
        {"reason": {"type": "string"}},
        ["reason"],
    ),
]


def tool_definitions_for_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    if task["schema_version"] in {"1.0", "1.1"}:
        from .v1_environment import tool_definitions_v1

        return tool_definitions_v1(task)
    if task["schema_version"] == "0.6":
        from .v06_environment import tool_definitions_v06

        return tool_definitions_v06(task)
    if task["schema_version"] == "0.5":
        tools = TRAVEL_V05_TOOLS if task["domain"] == "travel" else SHOPPING_V05_TOOLS
        result = deepcopy(tools)
        search_name = (
            "search_travel_options"
            if task["domain"] == "travel"
            else "search_products"
        )
        for tool in result:
            if tool["name"] == search_name:
                tool["parameters"]["properties"]["category"]["enum"] = sorted(
                    task["required_slots"]
                )
        return result
    return deepcopy(TRAVEL_TOOLS if task["domain"] == "travel" else SHOPPING_TOOLS)


class DomainToolRouter:
    """Expose STATE-style domain operations over the deterministic ledger."""

    def __init__(self, environment: RepairEnvironment):
        self.environment = environment
        self.domain = environment.task["domain"]

    def execute(self, name: str, args: dict[str, Any]) -> ActionResult:
        if self.domain == "travel":
            return self._travel(name, args)
        return self._shopping(name, args)

    def _generic(self, action: str, args: dict[str, Any]) -> ActionResult:
        return self.environment.execute({"action": action, "args": args})

    def _list(self, *, id_name: str) -> ActionResult:
        raw = self._generic("list_commitments", {})
        if not raw.ok:
            return raw
        records = []
        for item in raw.data or []:
            records.append(
                {
                    id_name: item["commitment_id"],
                    "type": item["slot"],
                    "reference": item["option_id"],
                    "status": item["status"],
                }
            )
        return ActionResult(True, "Active records found.", records)

    def _details(
        self, identifier: str, allowed_slots: set[str], *, id_name: str
    ) -> ActionResult:
        raw = self._generic(
            "get_commitment_details", {"commitment_id": identifier}
        )
        if not raw.ok:
            return raw
        data = dict(raw.data or {})
        if data.get("slot") not in allowed_slots:
            return ActionResult(False, f"{identifier} is not the requested record type.")
        return ActionResult(
            True,
            f"Details for {identifier}.",
            {
                id_name: identifier,
                "type": data["slot"],
                "reference": data["option_id"],
                "status": data["status"],
                "amount_paid": data["price_paid"],
                **deepcopy(data.get("attributes", {})),
            },
        )

    def _search(self, slots: set[str], requested_slot: str | None = None) -> ActionResult:
        candidates: list[dict[str, Any]] = []
        for slot in slots:
            if requested_slot is not None and slot != requested_slot:
                continue
            raw = self._generic("search_options", {"slot": slot})
            if not raw.ok:
                return raw
            for option in raw.data or []:
                candidates.append(
                    {
                        "option_id": option["option_id"],
                        "type": option["slot"],
                        "price": option["price"],
                        **deepcopy(option.get("attributes", {})),
                    }
                )
        return ActionResult(
            True, f"Found {len(candidates)} available option(s).", candidates
        )

    def _search_category(self, slot: str) -> ActionResult:
        raw = self._generic("search_options", {"slot": slot})
        if not raw.ok:
            return raw
        candidates = [
            {
                "option_id": option["option_id"],
                "type": option["slot"],
                "price": option["price"],
                **deepcopy(option.get("attributes", {})),
            }
            for option in raw.data or []
        ]
        return ActionResult(
            True, f"Found {len(candidates)} matching live option(s).", candidates
        )

    def _quote(self, identifier: str, *, id_name: str) -> ActionResult:
        raw = self._generic(
            "get_cancellation_quote", {"commitment_id": identifier}
        )
        if not raw.ok:
            return raw
        data = dict(raw.data or {})
        return ActionResult(
            True,
            f"Cancellation or return preview for {identifier}.",
            {
                id_name: identifier,
                "amount_paid": data["price_paid"],
                "refund_amount": data["refund"],
                "fee": data["price_paid"] - data["refund"],
            },
        )

    def _change_quote(
        self, identifier: str, target: str, *, id_name: str, target_name: str
    ) -> ActionResult:
        raw = self._generic(
            "get_modification_quote",
            {"commitment_id": identifier, "to_option_id": target},
        )
        if not raw.ok:
            return raw
        data = dict(raw.data or {})
        return ActionResult(
            True,
            raw.message,
            {
                id_name: identifier,
                target_name: target,
                "available": data.get("available", False),
                "quoted_fee": data.get("fee"),
                "net_cash_delta": data.get("net_cash_delta"),
                "cash_components": deepcopy(data.get("cash_components", {})),
            },
        )

    def _travel(self, name: str, args: dict[str, Any]) -> ActionResult:
        if name == "get_user_reservations":
            return self._list(id_name="reservation_id")
        if name == "get_booking":
            return self._details(
                args["reservation_id"],
                {"flight", "outbound", "return"},
                id_name="reservation_id",
            )
        if name == "get_hotel_reservation":
            return self._details(
                args["reservation_id"], {"hotel"}, id_name="reservation_id"
            )
        if name == "get_car_rental":
            return self._details(
                args["reservation_id"], {"car"}, id_name="reservation_id"
            )
        if name == "get_reservation_details":
            return self._details(
                args["reservation_id"],
                set(self.environment.task["required_slots"]),
                id_name="reservation_id",
            )
        if name == "search_travel_options":
            return self._search_category(args["category"])
        if name == "search_flights":
            return self._search(
                {"flight", "outbound", "return"}, args.get("journey")
            )
        if name == "search_hotels":
            return self._search({"hotel"})
        if name == "search_car_rentals":
            return self._search({"car"})
        if name == "preview_cancellation":
            return self._quote(args["reservation_id"], id_name="reservation_id")
        if name == "get_change_quote":
            return self._change_quote(
                args["reservation_id"],
                args["to_option_id"],
                id_name="reservation_id",
                target_name="to_option_id",
            )
        if name == "get_package_change_impact":
            return self._generic(
                "get_linked_loss_quote",
                {"commitment_id": args["reservation_id"]},
            )
        if name == "check_travel_compatibility":
            return self._generic(
                "check_compatibility",
                {
                    "left_option_id": args["left_option_id"],
                    "right_option_id": args["right_option_id"],
                },
            )
        if name == "cancel_reservation":
            return self._generic(
                "cancel", {"commitment_id": args["reservation_id"]}
            )
        if name == "book_travel_option":
            return self._generic("book", {"option_id": args["option_id"]})
        if name == "change_reservation":
            return self._generic(
                "modify",
                {
                    "commitment_id": args["reservation_id"],
                    "to_option_id": args["to_option_id"],
                },
            )
        if name in {"finish", "report_infeasible"}:
            return self._generic(name, args)
        return ActionResult(False, f"Unknown travel operation: {name}")

    def _shopping(self, name: str, args: dict[str, Any]) -> ActionResult:
        if name == "get_customer_orders":
            return self._list(id_name="order_id")
        if name == "get_product_order":
            return self._details(
                args["order_id"],
                set(self.environment.task["required_slots"]),
                id_name="order_id",
            )
        if name == "search_products":
            if self.environment.task["schema_version"] == "0.5":
                return self._search_category(args["category"])
            return self._search({args["category"]})
        if name == "get_return_quote":
            return self._quote(args["order_id"], id_name="order_id")
        if name == "get_exchange_quote":
            return self._change_quote(
                args["order_id"],
                args["to_product_id"],
                id_name="order_id",
                target_name="to_product_id",
            )
        if name == "get_bundle_change_impact":
            return self._generic(
                "get_linked_loss_quote",
                {"commitment_id": args["order_id"]},
            )
        if name == "check_product_compatibility":
            return self._generic(
                "check_compatibility",
                {
                    "left_option_id": args["left_product_id"],
                    "right_option_id": args["right_product_id"],
                },
            )
        if name == "return_product":
            return self._generic(
                "cancel", {"commitment_id": args["order_id"]}
            )
        if name == "purchase_product":
            return self._generic("book", {"option_id": args["product_id"]})
        if name == "exchange_product":
            return self._generic(
                "modify",
                {
                    "commitment_id": args["order_id"],
                    "to_option_id": args["to_product_id"],
                },
            )
        if name in {"finish", "report_infeasible"}:
            return self._generic(name, args)
        return ActionResult(False, f"Unknown shopping operation: {name}")
