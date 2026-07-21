import importlib.metadata
import pytest


def discover_modules():
    return [ep.load()() for ep in importlib.metadata.entry_points(group="4p.modules")]


@pytest.fixture(scope="session")
def all_modules():
    return discover_modules()
