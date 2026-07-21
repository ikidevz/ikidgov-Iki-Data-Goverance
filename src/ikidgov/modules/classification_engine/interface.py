def classify(columns: list[dict], detector_name: str = "builtin") -> dict:
    from .impl import ClassificationEngine

    return ClassificationEngine().classify(columns=columns, detector_name=detector_name)
