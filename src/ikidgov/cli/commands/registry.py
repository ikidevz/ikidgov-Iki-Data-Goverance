import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.metadata_registry import interface as registry


class RegisterDatasetCommand(BaseCommand):
    name = "register-dataset"

    def _handle(self, args: argparse.Namespace) -> dict:
        return registry.register_dataset(source=args.source, name=args.name, owner=args.owner, description=args.description, tags=args.tags)


class ListDatasetsCommand(BaseCommand):
    name = "list-datasets"

    def _handle(self, args: argparse.Namespace) -> dict:
        return {"datasets": registry.list_datasets()}
