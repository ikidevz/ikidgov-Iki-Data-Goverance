import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.policy_engine import interface as policy
from ikidgov.modules.policy_engine.impl import redact_sql_secrets


class PolicyCompileCommand(BaseCommand):
    name = "policy-compile"

    def _handle(self, args: argparse.Namespace) -> dict:
        payload = policy.compile(
            policy_name=args.policy, table=args.table, dialect=args.dialect)
        if getattr(args, "reveal_secrets", False):
            return payload
        payload["sql"] = redact_sql_secrets(payload.get("sql", []))
        return payload

    def render(self, payload: dict, output_format: str = "json") -> str:
        if output_format == "text":
            return "\n".join(payload.get("sql", []))
        return super().render(payload, output_format)
