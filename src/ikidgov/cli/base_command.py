import argparse
import json
from abc import ABC, abstractmethod
from typing import Any


class BaseCommand(ABC):
    name: str = ""

    def execute(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._handle(args)

    @abstractmethod
    def _handle(self, args: argparse.Namespace) -> dict[str, Any]:
        raise NotImplementedError

    def render(self, payload: dict[str, Any], output_format: str = "json") -> str:
        if output_format == "text":
            if isinstance(payload, dict):
                lines: list[str] = []
                for key, value in payload.items():
                    if isinstance(value, list):
                        lines.append(f"{key}:")
                        for item in value:
                            lines.append(f"  - {item}")
                    elif isinstance(value, dict):
                        lines.append(f"{key}:")
                        for sub_key, sub_value in value.items():
                            lines.append(f"  {sub_key}: {sub_value}")
                    else:
                        lines.append(f"{key}: {value}")
                return "\n".join(lines)
            return str(payload)
        return json.dumps(payload, indent=2)
