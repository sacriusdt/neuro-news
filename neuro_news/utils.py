from __future__ import annotations

from typing import Any, Type, TypeVar

T = TypeVar("T")


def model_validate(model_cls: Type[T], data: Any) -> T:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(data)  # type: ignore[attr-defined]
    return model_cls.parse_obj(data)  # type: ignore[attr-defined]


def model_dump(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()  # type: ignore[attr-defined]
