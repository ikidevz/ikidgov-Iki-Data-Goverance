from ikidgov.core.detector_base import Detector
from ikidgov.core.module_base import Module
from ikidgov.core.decision import Decision


_KNOWN_DETECTORS = {"builtin", "iki_pii_masker"}


class ClassificationEngine(Module):
    name = "classification_engine"

    def __init__(self, detector: Detector | None = None):
        self.detector = detector

    def describe(self) -> dict:
        return {"name": self.name, "detector": getattr(self.detector, "name", "builtin")}

    def run(self, **kwargs) -> dict:
        columns = kwargs.get("columns", [])
        detector = kwargs.get("detector")
        if detector is None:
            detector = self.detector or self._load_detector("builtin")
        elif isinstance(detector, str):
            detector = self._load_detector(detector)
        matches = detector.detect_by_name(
            [column["name"] for column in columns])
        results = []
        for column in columns:
            match = matches.get(column["name"])
            result = {
                "name": column["name"],
                "classification": match.pii_type if match else "unclassified",
                "sensitivity_level": "high" if match else "low",
                "detector": detector.name,
            }
            results.append(result)
        return {"results": results}

    def classify(self, columns: list[dict], detector_name: str = "builtin") -> dict:
        detector = self._load_detector(detector_name)
        return self.run(columns=columns, detector=detector)

    def _load_detector(self, detector_name: str) -> Detector:
        if detector_name not in _KNOWN_DETECTORS:
            raise ValueError(detector_name)

        from importlib.metadata import entry_points

        for group in ("ikidgov.detectors",):
            detectors = entry_points(group=group)
            for entry_point in detectors:
                if entry_point.name == detector_name:
                    return entry_point.load()()
        raise ValueError(detector_name)
        raise ValueError(detector_name)
