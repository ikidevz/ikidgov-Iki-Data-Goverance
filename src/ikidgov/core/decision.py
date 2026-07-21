from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    rule_id: str | None = None

    def __bool__(self) -> bool:
        return self.allowed
