# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Small helpers shared by every resource: turning a caller-supplied dict or
model instance into a wire payload, and turning a response payload back into
generated pydantic models.

Accepting either a dict or the exact generated request model (rather than
only a dict) gets callers real validation against the pinned spec for free —
a value beyond what the reference Node SDK's compile-time-only types give,
made possible because pydantic validates at runtime.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Type, TypeVar, Union

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)

Body = Union[BaseModel, Mapping[str, Any]]


def dump_body(model_cls: Type[BaseModel], body: Body) -> Any:
    """Validates ``body`` against the generated request model (whether it was
    handed to us as a dict or already as that model) and returns the JSON-
    ready payload — never a hand-widened shape, since the model IS the spec."""
    model = body if isinstance(body, model_cls) else model_cls.model_validate(body)
    return model.model_dump(mode="json", exclude_none=True)


def dump_list_body(item_cls: Type[BaseModel], items) -> Any:
    return [dump_body(item_cls, item) for item in items]


def parse(model_cls: Type[M], data: Any) -> M:
    return model_cls.model_validate(data)


def parse_optional(model_cls: Type[M], data: Any) -> Optional[M]:
    return None if data is None else model_cls.model_validate(data)


def parse_list(model_cls: Type[M], data: Any) -> List[M]:
    return [model_cls.model_validate(item) for item in (data or [])]


def parse_map(model_cls: Type[M], data: Any) -> "dict[str, M]":
    return {key: model_cls.model_validate(value) for key, value in (data or {}).items()}
