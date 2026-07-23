import argparse
import os
from typing import Iterable

from ikidgov.cli.commands.classify import ClassifyCommand
from ikidgov.cli.commands.policy_check import PolicyCheckCommand
from ikidgov.cli.commands.policy_compile import PolicyCompileCommand
from ikidgov.cli.commands.registry import ListDatasetsCommand, RegisterDatasetCommand
from ikidgov.cli.commands.run_example import RunExampleCommand
from ikidgov.cli.commands.scan import ScanCommand
from ikidgov.cli.commands.show_config import ShowConfigCommand

COMMANDS = [
    ShowConfigCommand(),
    RunExampleCommand(),
    RegisterDatasetCommand(),
    ListDatasetsCommand(),
    ScanCommand(),
    ClassifyCommand(),
    PolicyCheckCommand(),
    PolicyCompileCommand(),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iki-datagov")
    parser.add_argument(
        "--env",
        "--environment",
        dest="environment",
        default=None,
        help="Select an environment-specific config file such as governance.dev.yaml",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = subparsers.add_parser(command.name)
        subparser.add_argument(
            "--format", choices=["json", "text"], default="json")
        if command.name == "run-example":
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "register-dataset":
            subparser.add_argument("--actor-role", required=True)
            subparser.add_argument("--source", required=True)
            subparser.add_argument("--name", required=True)
            subparser.add_argument("--owner")
            subparser.add_argument("--description")
            subparser.add_argument("--tags", nargs="*", default=[])
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "list-datasets":
            subparser.add_argument("--actor-role", required=True)
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "scan":
            subparser.add_argument("--actor-role", required=True)
            subparser.add_argument(
                "--type", choices=["csv", "json", "sql"], required=True)
            subparser.add_argument("--path")
            subparser.add_argument("--table")
            subparser.add_argument("--owner")
            subparser.add_argument(
                "--backend",
                choices=["sqlite", "postgres", "postgresql", "mysql", "mssql"],
                default=None,
                help="Select a backend for SQL scans (defaults to the configured governance YAML backend)",
            )
            subparser.add_argument(
                "--config",
                default=None,
                help="Path to a governance YAML file to use for this scan",
            )
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "classify":
            subparser.add_argument("--actor-role", required=True)
            subparser.add_argument("--dataset-id", type=int, required=True)
            subparser.add_argument("--detector", default="builtin")
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "policy-check":
            subparser.add_argument("--actor-role", required=True)
            subparser.add_argument(
                "--action-type",
                required=True,
                choices=["read", "select", "write", "insert", "update",
                         "delete", "drop", "alter", "create", "truncate"],
            )
            subparser.add_argument("--dataset-id", type=int)
            subparser.add_argument("--column")
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "policy-compile":
            subparser.add_argument("--policy", required=True)
            subparser.add_argument("--table", required=True)
            subparser.add_argument(
                "--dialect",
                choices=["generic", "mysql",
                         "postgres", "postgresql", "mssql"],
                default="generic",
            )
            subparser.add_argument(
                "--reveal-secrets",
                action="store_true",
                help="Print the unredacted SQL instead of the default redacted output",
            )
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
        elif command.name == "show-config":
            subparser.set_defaults(
                handler=lambda args, command=command: _run_command(command, args))
    return parser


def _run_command(command, args: argparse.Namespace) -> None:
    saved_env = os.getenv("IKIGOV_ENV")
    if getattr(args, "environment", None) is not None:
        os.environ["IKIGOV_ENV"] = args.environment
    try:
        payload = command.execute(args)
        print(command.render(payload, getattr(args, "format", "json")))
    finally:
        if saved_env is None:
            os.environ.pop("IKIGOV_ENV", None)
        else:
            os.environ["IKIGOV_ENV"] = saved_env


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not hasattr(args, "handler"):
        parser.error("a subcommand is required")

    try:
        args.handler(args)
        return 0
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(status=2, message=f"Error: {exc}\n")
    except Exception as exc:
        parser.exit(status=2, message=f"Error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
