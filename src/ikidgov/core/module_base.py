from abc import ABC, abstractmethod
from typing import Any


class Module(ABC):
    """Base contract for every composable module."""

    name: str = ""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError
