import argparse
import os

from ikidgov.cli.base_command import BaseCommand
from ikidgov.config_loader import load_config


class ShowConfigCommand(BaseCommand):
    name = "show-config"

    def _handle(self, args: argparse.Namespace) -> dict:
        environment = os.getenv("IKIDGOV_ENV") or os.getenv(
            "APP_ENV") or "default"
        config = load_config()
        return {
            "environment": environment,
            "config_loaded": bool(config),
            "roles": sorted(config.get("roles", {}).keys()),
            "connectors": sorted(config.get("connectors", {}).keys()),
            "backends": sorted(
                [key for key in ("sqlite", "postgresql",
                                 "mysql", "mssql") if key in config]
            ),
        }
