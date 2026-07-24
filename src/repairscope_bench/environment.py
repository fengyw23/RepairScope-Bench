from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


class ToolError(RuntimeError):
    """A recoverable tool/API error exposed to the evaluated agent."""


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    data: dict[str, Any] | list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "message": self.message, "data": self.data}


class RepairEnvironment:
    """Small transactional environment initialized at a fixed failure boundary."""

    def __init__(self, task: dict[str, Any]):
        self.task = deepcopy(task)
        self.commitments: list[dict[str, Any]] = deepcopy(
            task["failure_snapshot"]["commitments"]
        )
        for item in self.commitments:
            item["_origin"] = "pre_failure"
            item["_original_option_id"] = item["option_id"]
        self._initial_commitments = self._public_commitments(self.commitments)
        self._pre_failure_spend = sum(
            item["price_paid"] for item in self.commitments
        )
        self.catalog = {
            item["option_id"]: deepcopy(item) for item in task.get("catalog", [])
        }
        self.modification_rules = deepcopy(task.get("modification_rules", []))
        self.event_log: list[dict[str, Any]] = []
        self.new_charges = 0
        self.original_refunds = 0
        self.new_refunds = 0
        self.modification_net_cash = 0
        self.modification_fees = 0
        self.terminal_mode: str | None = None
        self.terminal_message: str | None = None
        self._next_id = 1

    @property
    def pre_failure_spend(self) -> int | float:
        return self._pre_failure_spend

    @property
    def financial_delta(self) -> int | float:
        """Net cash paid after the standardized failure boundary."""
        return (
            self.new_charges
            + self.modification_net_cash
            + self.linked_loss
            - self.original_refunds
            - self.new_refunds
        )

    @property
    def lifecycle_cost(self) -> int | float:
        """Total cash retained by providers across the complete task lifecycle."""
        return self.pre_failure_spend + self.financial_delta

    @property
    def cancellation_loss(self) -> int | float:
        """Irrecoverable value caused by cancelling pre-failure commitments."""
        return sum(
            item["price_paid"] - item.get("_refund_received", 0)
            for item in self.commitments
            if item["_origin"] == "pre_failure" and item["status"] == "cancelled"
        )

    @property
    def post_failure_waste(self) -> int | float:
        """Non-refunded spend on bookings created and cancelled during recovery."""
        return sum(
            item["price_paid"] - item.get("_refund_received", 0)
            for item in self.commitments
            if item["_origin"] == "post_failure" and item["status"] == "cancelled"
        )

    @property
    def rollback_damage(self) -> int | float:
        """Backward-compatible name for objectively auditable recovery loss."""
        return self.recovery_loss

    @property
    def recovery_loss(self) -> int | float:
        """Irrecoverable recovery damage; useful retained purchases are not waste."""
        return (
            self.cancellation_loss
            + self.post_failure_waste
            + max(0, self.modification_net_cash)
            + self.linked_loss
        )

    @property
    def linked_loss(self) -> int | float:
        """Objective settlement loss caused by breaking a prior bundle/commitment."""
        dispositions = self.dispositions()
        total: int | float = 0
        for rule in self.task.get("linked_loss_rules", []):
            changed = [
                dispositions.get(identifier, "KEEP") != "KEEP"
                for identifier in rule["commitment_ids"]
            ]
            trigger = rule.get("trigger", "any_changed")
            applies = any(changed) if trigger == "any_changed" else all(changed)
            if applies:
                total += rule["amount"]
        return total

    def active_commitments(self, slot: str | None = None) -> list[dict[str, Any]]:
        active = [item for item in self.commitments if item["status"] == "confirmed"]
        if slot is not None:
            active = [item for item in active if item["slot"] == slot]
        return active

    def list_commitments(self) -> ActionResult:
        return ActionResult(
            True,
            "Current persistent commitments.",
            [
                {
                    "commitment_id": item["commitment_id"],
                    "slot": item["slot"],
                    "option_id": item["option_id"],
                    "status": item["status"],
                }
                for item in self._public_commitments(self.commitments)
            ],
        )

    def get_commitment_details(self, commitment_id: str) -> ActionResult:
        commitment = self._get_any(commitment_id)
        return ActionResult(
            True,
            f"Details for {commitment_id}.",
            {
                "commitment_id": commitment["commitment_id"],
                "slot": commitment["slot"],
                "option_id": commitment["option_id"],
                "status": commitment["status"],
                "price_paid": commitment["price_paid"],
                "attributes": deepcopy(commitment.get("attributes", {})),
            },
        )

    def get_cancellation_quote(self, commitment_id: str) -> ActionResult:
        commitment = self._get_active(commitment_id)
        refund = commitment.get("refund_if_cancelled", 0)
        return ActionResult(
            True,
            f"Cancellation quote for {commitment_id}. No state was changed.",
            {
                "commitment_id": commitment_id,
                "price_paid": commitment["price_paid"],
                "refund": refund,
                "irrecoverable_loss": commitment["price_paid"] - refund,
            },
        )

    def search_options(self, slot: str) -> ActionResult:
        """Return live inventory for a public, structured category.

        The category is the hard filter.  Earlier challenge versions also
        compared a free-form model string against a hidden literal stored in
        the task.  That made semantically equivalent searches return different
        inventories and measured prompt guessing rather than environment
        exploration.
        """
        options = [
            {
                "option_id": option["option_id"],
                "slot": option["slot"],
                "price": option["price"],
                "attributes": deepcopy(option.get("attributes", {})),
                "refund_if_cancelled_after_booking": option.get(
                    "refund_if_cancelled_after_booking", 0
                ),
            }
            for option in self.catalog.values()
            if option["slot"] == slot and option.get("available", False)
        ]
        return ActionResult(
            True,
            f"Found {len(options)} currently available option(s) for {slot}.",
            options,
        )

    def get_linked_loss_quote(self, commitment_id: str) -> ActionResult:
        self._get_active(commitment_id)
        rules = []
        for rule in self.task.get("linked_loss_rules", []):
            if commitment_id not in rule["commitment_ids"]:
                continue
            rules.append(
                {
                    "rule_id": rule["rule_id"],
                    "description": rule["description"],
                    "trigger": rule.get("trigger", "any_changed"),
                    "linked_commitment_ids": deepcopy(rule["commitment_ids"]),
                    "settlement_charge": rule["amount"],
                }
            )
        return ActionResult(
            True,
            f"Found {len(rules)} linked term(s) for {commitment_id}.",
            rules,
        )

    def get_modification_quote(
        self, commitment_id: str, to_option_id: str
    ) -> ActionResult:
        commitment = self._get_active(commitment_id)
        rules = [
            rule
            for rule in self.modification_rules
            if rule["commitment_id"] == commitment_id
            and rule["to_option_id"] == to_option_id
            and rule.get("from_option_id", commitment["option_id"])
            == commitment["option_id"]
            and rule.get("available", True)
        ]
        if not rules:
            return ActionResult(
                True,
                f"No in-place modification is offered from {commitment_id} "
                f"to {to_option_id}.",
                {
                    "commitment_id": commitment_id,
                    "to_option_id": to_option_id,
                    "available": False,
                },
            )
        rule = rules[0]
        return ActionResult(
            True,
            f"Modification quote for {commitment_id}. No state was changed.",
            {
                "commitment_id": commitment_id,
                "from_option_id": commitment["option_id"],
                "to_option_id": to_option_id,
                "available": True,
                "fee": rule.get("fee", 0),
                "net_cash_delta": rule.get("net_cash_delta", 0),
                "cash_components": deepcopy(rule.get("cash_components", {})),
            },
        )

    def check_compatibility(
        self, left_option_id: str, right_option_id: str
    ) -> ActionResult:
        left = self._find_option_or_commitment(left_option_id)
        right = self._find_option_or_commitment(right_option_id)
        applicable = False
        compatible = True
        for constraint in self.task["constraints"]:
            if constraint["type"] != "allowed_pairs":
                continue
            expected_slots = {
                constraint["left_slot"],
                constraint["right_slot"],
            }
            if {left["slot"], right["slot"]} != expected_slots:
                continue
            applicable = True
            pair = (
                [left_option_id, right_option_id]
                if left["slot"] == constraint["left_slot"]
                else [right_option_id, left_option_id]
            )
            compatible = compatible and pair in constraint["pairs"]
        return ActionResult(
            True,
            "Compatibility check completed.",
            {
                "left_option_id": left_option_id,
                "right_option_id": right_option_id,
                "applicable": applicable,
                "compatible": compatible if applicable else None,
            },
        )

    def get_cost_summary(self) -> ActionResult:
        return ActionResult(
            True,
            "Current cash summary.",
            {
                "pre_failure_spend": self.pre_failure_spend,
                "post_failure_net_cash": self.financial_delta,
                "current_lifecycle_cost": self.lifecycle_cost,
            },
        )

    def cancel(self, commitment_id: str) -> ActionResult:
        commitment = self._get_active(commitment_id)
        commitment["status"] = "cancelled"
        if commitment["_origin"] == "pre_failure":
            refund = commitment["refund_if_cancelled"]
            self.original_refunds += refund
        else:
            refund = commitment.get("refund_if_cancelled", 0)
            self.new_refunds += refund
        commitment["_refund_received"] = refund
        return ActionResult(
            True,
            f"Cancelled {commitment_id}; refund={refund}.",
            {"refund": refund},
        )

    def book(self, option_id: str) -> ActionResult:
        if option_id not in self.catalog:
            raise ToolError(f"Unknown option: {option_id}")
        option = self.catalog[option_id]
        if not option.get("available", False):
            raise ToolError(f"Option {option_id} is unavailable")
        if self.active_commitments(option["slot"]):
            raise ToolError(
                f"Slot {option['slot']} already has an active commitment; "
                "cancel or modify it first"
            )
        commitment = {
            "commitment_id": f"NEW-{self._next_id:04d}",
            "slot": option["slot"],
            "option_id": option_id,
            "status": "confirmed",
            "price_paid": option["price"],
            "refund_if_cancelled": option.get("refund_if_cancelled_after_booking", 0),
            "attributes": deepcopy(option.get("attributes", {})),
            "_origin": "post_failure",
            "_original_option_id": option_id,
        }
        self._next_id += 1
        self.commitments.append(commitment)
        self.new_charges += option["price"]
        return ActionResult(
            True,
            f"Booked {option_id} as {commitment['commitment_id']}.",
            {"commitment_id": commitment["commitment_id"], "charge": option["price"]},
        )

    def modify(self, commitment_id: str, to_option_id: str) -> ActionResult:
        commitment = self._get_active(commitment_id)
        if commitment["option_id"] == to_option_id:
            raise ToolError(f"{commitment_id} already uses {to_option_id}")
        rules = [
            rule
            for rule in self.modification_rules
            if rule["commitment_id"] == commitment_id
            and rule["to_option_id"] == to_option_id
            and rule.get("from_option_id", commitment["option_id"])
            == commitment["option_id"]
            and rule.get("available", True)
        ]
        if not rules:
            raise ToolError(
                f"No available modification from {commitment_id} to {to_option_id}"
            )
        rule = rules[0]
        target = self.catalog.get(to_option_id)
        if target is None:
            raise ToolError(f"Unknown modification target: {to_option_id}")
        commitment["option_id"] = to_option_id
        commitment["attributes"] = deepcopy(target.get("attributes", {}))
        commitment["_modified"] = True
        commitment["_modification_fee"] = rule.get("fee", 0)
        commitment["_modification_net_cash"] = rule.get("net_cash_delta", 0)
        commitment["_modification_rule_used"] = deepcopy(rule)
        self.modification_fees += rule.get("fee", 0)
        self.modification_net_cash += rule.get("net_cash_delta", 0)
        return ActionResult(
            True,
            f"Modified {commitment_id} to {to_option_id}.",
            {
                "fee": rule.get("fee", 0),
                "net_cash_delta": rule.get("net_cash_delta", 0),
            },
        )

    def finish(self) -> ActionResult:
        self.terminal_mode = "finish"
        self.terminal_message = "Agent declared recovery complete."
        return ActionResult(True, self.terminal_message)

    def report_infeasible(self, reason: str) -> ActionResult:
        self.terminal_mode = "infeasible"
        self.terminal_message = reason
        return ActionResult(True, "Agent reported that no safe feasible repair exists.")

    def execute(self, action: dict[str, Any]) -> ActionResult:
        name = action.get("action")
        args = action.get("args", {})
        try:
            if self.terminal_mode is not None:
                raise ToolError(
                    f"Episode already terminated via {self.terminal_mode}; "
                    "no further actions are allowed"
                )
            if name == "list_commitments":
                result = self.list_commitments()
            elif name == "get_commitment_details":
                result = self.get_commitment_details(args["commitment_id"])
            elif name == "get_cancellation_quote":
                result = self.get_cancellation_quote(args["commitment_id"])
            elif name == "search_options":
                result = self.search_options(args["slot"])
            elif name == "get_linked_loss_quote":
                result = self.get_linked_loss_quote(args["commitment_id"])
            elif name == "get_modification_quote":
                result = self.get_modification_quote(
                    args["commitment_id"], args["to_option_id"]
                )
            elif name == "check_compatibility":
                result = self.check_compatibility(
                    args["left_option_id"], args["right_option_id"]
                )
            elif name == "get_cost_summary":
                result = self.get_cost_summary()
            elif name == "cancel":
                result = self.cancel(args["commitment_id"])
            elif name == "book":
                result = self.book(args["option_id"])
            elif name == "modify":
                result = self.modify(args["commitment_id"], args["to_option_id"])
            elif name == "finish":
                result = self.finish()
            elif name == "report_infeasible":
                result = self.report_infeasible(args.get("reason", ""))
            else:
                raise ToolError(f"Unknown action: {name}")
        except (KeyError, ToolError) as error:
            result = ActionResult(False, str(error))
        self.event_log.append({"action": deepcopy(action), "result": result.as_dict()})
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "commitments": self._public_commitments(self.commitments),
            "pre_failure_spend": self.pre_failure_spend,
            "financial_delta": self.financial_delta,
            "lifecycle_cost": self.lifecycle_cost,
            "cancellation_loss": self.cancellation_loss,
            "post_failure_waste": self.post_failure_waste,
            "linked_loss": self.linked_loss,
            "recovery_loss": self.recovery_loss,
            "rollback_damage": self.rollback_damage,
            "terminal_mode": self.terminal_mode,
            "terminal_message": self.terminal_message,
            "event_log": deepcopy(self.event_log),
        }

    def dispositions(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.commitments:
            if item["_origin"] != "pre_failure":
                continue
            if item["status"] == "confirmed":
                result[item["commitment_id"]] = (
                    "MODIFY" if item.get("_modified") else "KEEP"
                )
                continue
            replacement_exists = any(
                candidate["status"] == "confirmed"
                and candidate["slot"] == item["slot"]
                and candidate["_origin"] == "post_failure"
                for candidate in self.commitments
            )
            result[item["commitment_id"]] = (
                "REPLACE" if replacement_exists else "CANCEL"
            )
        return result

    def mutated_prior_commitments(self) -> int:
        return sum(value != "KEEP" for value in self.dispositions().values())

    def state_changing_actions(self) -> int:
        return sum(
            event["action"].get("action") in {"cancel", "book", "modify"}
            and event["result"]["ok"]
            for event in self.event_log
        )

    def state_matches_failure_boundary(self) -> bool:
        return self._public_commitments(self.commitments) == self._initial_commitments

    def objective_tuple(self) -> tuple[int | float, ...]:
        """Return the declared lexicographic objective without subjective weights."""
        values: dict[str, int | float] = {
            "financial_cost": self.lifecycle_cost,
            "financial_delta": self.financial_delta,
            "recovery_loss": self.recovery_loss,
            "rollback_damage": self.rollback_damage,
            "mutated_prior_commitments": self.mutated_prior_commitments(),
            "state_changing_actions": self.state_changing_actions(),
        }
        terms = self.task.get("objective", {}).get(
            "terms",
            [
                "recovery_loss",
                "financial_cost",
                "mutated_prior_commitments",
                "state_changing_actions",
            ],
        )
        unknown = [term for term in terms if term not in values]
        if unknown:
            raise ValueError(f"Unknown objective term(s): {unknown}")
        return tuple(values[term] for term in terms)

    def _get_active(self, commitment_id: str) -> dict[str, Any]:
        for item in self.commitments:
            if (
                item["commitment_id"] == commitment_id
                and item["status"] == "confirmed"
            ):
                return item
        raise ToolError(f"No active commitment: {commitment_id}")

    def _get_any(self, commitment_id: str) -> dict[str, Any]:
        for item in self.commitments:
            if item["commitment_id"] == commitment_id:
                return item
        raise ToolError(f"Unknown commitment: {commitment_id}")

    def _find_option_or_commitment(self, option_id: str) -> dict[str, Any]:
        if option_id in self.catalog:
            return self.catalog[option_id]
        for item in self.commitments:
            if item["option_id"] == option_id:
                return item
        raise ToolError(f"Unknown option: {option_id}")

    @staticmethod
    def _public_commitments(
        commitments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        public = [
            {key: deepcopy(value) for key, value in item.items() if not key.startswith("_")}
            for item in commitments
        ]
        return sorted(
            public,
            key=lambda item: (item["commitment_id"], item["slot"], item["option_id"]),
        )
