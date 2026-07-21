import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.example_module import interface as example_module


class RunExampleCommand(BaseCommand):
    name = "run-example"

    def _handle(self, args: argparse.Namespace) -> dict:
        return example_module.run()
