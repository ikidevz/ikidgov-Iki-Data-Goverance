import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.policy_engine import interface as policy


class PolicyCompileCommand(BaseCommand):
    name = "policy-compile"

    def _handle(self, args: argparse.Namespace) -> dict:
        return policy.compile(policy_name=args.policy, table=args.table, dialect=args.dialect)

    def render(self, payload: dict, output_format: str = "json") -> str:
        if output_format == "text":
            return "\n".join(payload.get("sql", []))
        return super().render(payload, output_format)
