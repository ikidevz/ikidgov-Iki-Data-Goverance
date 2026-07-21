from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionMatch:
    pii_type: str
    confidence: float = 1.0


class Detector(ABC):
    name: str = ""

    @abstractmethod
    def detect_by_name(self, column_names: list[str]) -> dict[str, DetectionMatch]:
        raise NotImplementedError

    def detect_by_value(self, values: list[str]) -> dict[str, DetectionMatch]:
        return {}
