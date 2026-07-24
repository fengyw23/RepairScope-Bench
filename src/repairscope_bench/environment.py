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
        return sum(
            item["price_paid"]
            for item in self.commitments
            if item["_origin"] == "pre_failure"
        )

    @property
    def lifecycle_cost(self) -> int | float:
        return (
            self.pre_failure_spend
            + self.new_charges
            + self.modification_net_cash
            - self.original_refunds
            - self.new_refunds
        )

    @property
    def repair_loss(self) -> int | float:
        original_irrecoverable = sum(
            item["price_paid"] - item.get("_refund_received", 0)
            for item in self.commitments
            if item["_origin"] == "pre_failure" and item["status"] == "cancelled"
        )
        return (
            original_irrecoverable
            + self.new_charges
            - self.new_refunds
            + self.modification_fees
        )

    def active_commitments(self, slot: str | None = None) -> list[dict[str, Any]]:
        active = [item for item in self.commitments if item["status"] == "confirmed"]
        if slot is not None:
            active = [item for item in active if item["slot"] == slot]
        return active

    def query_state(self) -> ActionResult:
        return ActionResult(
            True,
            "Authoritative post-failure state.",
            {
                "commitments": deepcopy(self.commitments),
                "lifecycle_cost": self.lifecycle_cost,
                "repair_loss": self.repair_loss,
                "failure_observation": self.task["failure_observation"],
            },
        )

    def list_options(self, slot: str) -> ActionResult:
        options = [
            deepcopy(option)
            for option in self.catalog.values()
            if option["slot"] == slot
        ]
        return ActionResult(True, f"{len(options)} option(s) for slot {slot}.", options)

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
        rules = [
            rule
            for rule in self.modification_rules
            if rule["commitment_id"] == commitment_id
            and rule["to_option_id"] == to_option_id
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
            if name == "query_state":
                result = self.query_state()
            elif name == "list_options":
                result = self.list_options(args["slot"])
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
            "commitments": deepcopy(self.commitments),
            "lifecycle_cost": self.lifecycle_cost,
            "repair_loss": self.repair_loss,
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

    def _get_active(self, commitment_id: str) -> dict[str, Any]:
        for item in self.commitments:
            if (
                item["commitment_id"] == commitment_id
                and item["status"] == "confirmed"
            ):
                return item
        raise ToolError(f"No active commitment: {commitment_id}")

