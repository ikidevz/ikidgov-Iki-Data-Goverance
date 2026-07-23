import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.metadata_registry import interface as registry
from ikidgov.modules.policy_engine import interface as policy


class RegisterDatasetCommand(BaseCommand):
    name = "register-dataset"

    def _handle(self, args: argparse.Namespace) -> dict:
        decision = policy.check(
            actor_role=args.actor_role, action_type="write")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return registry.register_dataset(source=args.source, name=args.name, owner=args.owner, description=args.description, tags=args.tags)


class ListDatasetsCommand(BaseCommand):
    name = "list-datasets"

    def _handle(self, args: argparse.Namespace) -> dict:
        decision = policy.check(actor_role=args.actor_role, action_type="read")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return {"datasets": registry.list_datasets()}
