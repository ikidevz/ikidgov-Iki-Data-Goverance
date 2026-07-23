import argparse

from ikidgov.cli.base_command import BaseCommand
from ikidgov.modules.classification_engine import interface as classifier
from ikidgov.modules.metadata_registry import interface as registry
from ikidgov.modules.policy_engine import interface as policy


class ClassifyCommand(BaseCommand):
    name = "classify"

    def _handle(self, args: argparse.Namespace) -> dict:
        decision = policy.check(
            actor_role=args.actor_role, action_type="write")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        dataset = registry.get_dataset(args.dataset_id)
        if not dataset:
            return {"error": "dataset not found"}

        columns = dataset.get("columns", [])
        if not columns:
            return {"error": "dataset has no columns"}

        return classifier.classify(columns=columns, detector_name=args.detector)
