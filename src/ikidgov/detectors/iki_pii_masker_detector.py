from ikidgov.core.detector_base import DetectionMatch, Detector


class IkiPIIMaskerDetector(Detector):
    name = "iki_pii_masker"

    def detect_by_name(self, column_names: list[str]) -> dict[str, DetectionMatch]:
        matches = {}
        for column in column_names:
            if "email" in column.lower():
                matches[column] = DetectionMatch(pii_type="email")
        return matches
