from typing import TypedDict


def register_dataset(source: str, name: str, owner: str | None = None, description: str | None = None, tags: list | None = None) -> dict:
    from .impl import MetadataRegistry

    return MetadataRegistry().run(action="register_dataset", source=source, name=name, owner=owner, description=description, tags=tags)


def register_column(dataset_id: int, name: str, dtype: str | None = None, classification: str | None = None, sensitivity_level: str = "unclassified") -> dict:
    from .impl import MetadataRegistry

    return MetadataRegistry().run(action="register_column", dataset_id=dataset_id, name=name, dtype=dtype, classification=classification, sensitivity_level=sensitivity_level)


def get_dataset(dataset_id: int) -> dict:
    from .impl import MetadataRegistry

    return MetadataRegistry().run(action="get_dataset", dataset_id=dataset_id)


def list_datasets() -> dict:
    from .impl import MetadataRegistry

    return MetadataRegistry().run(action="list_datasets")
