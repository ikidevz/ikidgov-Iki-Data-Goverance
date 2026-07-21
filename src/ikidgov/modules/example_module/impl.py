from ikidgov.core.module_base import Module


class ExampleModule(Module):
    name = "example_module"

    def describe(self) -> dict:
        return {"name": self.name, "kind": "example"}

    def run(self, **kwargs) -> dict:
        return {"status": "ok", "detail": "example module"}
