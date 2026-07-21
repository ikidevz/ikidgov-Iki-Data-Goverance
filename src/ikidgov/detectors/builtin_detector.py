import re

from ikidgov.core.detector_base import DetectionMatch, Detector


class BuiltinDetector(Detector):
    name = "builtin"

    def detect_by_name(self, column_names: list[str]) -> dict[str, DetectionMatch]:
        matches: dict[str, DetectionMatch] = {}
        patterns = {
            "email": r"e[-_]?mail",
            "phone": r"phone|mobile|telephone",
            "ssn": r"ssn|social[_ -]?security",
            "password": r"password|passwd|pwd",
        }
        for column in column_names:
            lowered = column.lower()
            for pii_type, pattern in patterns.items():
                if re.search(pattern, lowered):
                    matches[column] = DetectionMatch(pii_type=pii_type)
                    break
        return matches
