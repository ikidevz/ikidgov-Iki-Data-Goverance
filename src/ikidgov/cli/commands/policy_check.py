import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.policy_engine import interface as policy


class PolicyCheckCommand(BaseCommand):
    name = "policy-check"

    def _handle(self, args: argparse.Namespace) -> dict:
        decision = policy.check(actor_role=args.actor_role, action_type=args.action_type,
                                dataset_id=args.dataset_id, column=args.column)
        return {"allowed": decision.allowed, "reason": decision.reason, "rule_id": decision.rule_id}
