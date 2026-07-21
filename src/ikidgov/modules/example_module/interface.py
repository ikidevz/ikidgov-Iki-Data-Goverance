from typing import TypedDict


class ExampleResult(TypedDict):
    status: str
    detail: str


def describe() -> dict:
    from .impl import ExampleModule

    return ExampleModule().describe()


def run(**kwargs) -> ExampleResult:
    from .impl import ExampleModule

    return ExampleModule().run(**kwargs)
