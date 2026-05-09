from __future__ import annotations

from typing import Any, Generic, TypeVar

from .context import SpeconnContext

T = TypeVar("T")


class ContextKey(Generic[T]):
    def __init__(self, id: str, default_value: T) -> None:
        self.id = id
        self.default_value = default_value


def set_value(ctx: SpeconnContext, key: ContextKey[T], value: T) -> None:
    ctx.values[key.id] = value


def get_value(ctx: SpeconnContext, key: ContextKey[T]) -> T:
    if key.id in ctx.values:
        return ctx.values[key.id]
    return key.default_value


def delete_value(ctx: SpeconnContext, key: ContextKey[Any]) -> None:
    if key.id in ctx.values:
        del ctx.values[key.id]


UserKey: ContextKey[str] = ContextKey(id="user", default_value="")
RequestIDKey: ContextKey[str] = ContextKey(id="request-id", default_value="")
UserIDKey: ContextKey[int] = ContextKey(id="user-id", default_value=0)
