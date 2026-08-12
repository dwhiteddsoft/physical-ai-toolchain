"""Utilities to convert class instances to plain dictionaries and back.

The produced dictionary embeds the fully qualified type name under the
``__type__`` key so the original object can be reconstructed later.
"""

from __future__ import annotations

import enum
import importlib
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from typing import Any

TYPE_KEY = "__type__"
VALUE_KEY = "__value__"

_PRIMITIVES = (str, int, float, bool, type(None))


def _qualname(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _resolve(path: str) -> type:
    module_name, _, qualname = path.partition(":")
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def to_dict(obj: Any) -> Any:
    """Recursively convert ``obj`` into JSON friendly primitives."""
    if isinstance(obj, _PRIMITIVES):
        return obj
    if isinstance(obj, enum.Enum):
        return {TYPE_KEY: _qualname(type(obj)), VALUE_KEY: obj.value}
    if isinstance(obj, (datetime, date)):
        return {TYPE_KEY: _qualname(type(obj)), VALUE_KEY: obj.isoformat()}
    if isinstance(obj, (list, tuple, set)):
        items = [to_dict(item) for item in obj]
        if isinstance(obj, list):
            return items
        return {TYPE_KEY: _qualname(type(obj)), VALUE_KEY: items}
    if isinstance(obj, dict):
        return {key: to_dict(value) for key, value in obj.items()}

    if is_dataclass(obj):
        data = {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    elif hasattr(obj, "__dict__"):
        data = {k: to_dict(v) for k, v in vars(obj).items()}
    elif hasattr(obj, "__slots__"):
        data = {
            name: to_dict(getattr(obj, name))
            for name in obj.__slots__
            if hasattr(obj, name)
        }
    else:
        raise TypeError(f"Cannot serialize object of type {type(obj)!r}")

    data[TYPE_KEY] = _qualname(type(obj))
    return data


def from_dict(data: Any, cls: type | None = None) -> Any:
    """Rebuild an object previously produced by :func:`to_dict`."""
    if isinstance(data, _PRIMITIVES):
        return data
    if isinstance(data, list):
        return [from_dict(item) for item in data]
    if not isinstance(data, dict):
        return data

    if TYPE_KEY not in data and cls is None:
        return {key: from_dict(value) for key, value in data.items()}

    target = cls if cls is not None else _resolve(data[TYPE_KEY])

    if VALUE_KEY in data:
        value = data[VALUE_KEY]
        if isinstance(target, type) and issubclass(target, enum.Enum):
            return target(value)
        if isinstance(target, type) and issubclass(target, (datetime, date)):
            return target.fromisoformat(value)
        if isinstance(target, type) and issubclass(target, (tuple, set, frozenset)):
            return target(from_dict(item) for item in value)
        return target(value)

    payload = {k: from_dict(v) for k, v in data.items() if k != TYPE_KEY}

    try:
        return target(**payload)
    except TypeError:
        instance = object.__new__(target)
        for key, value in payload.items():
            setattr(instance, key, value)
        return instance


__all__ = ["to_dict", "from_dict", "TYPE_KEY", "VALUE_KEY"]
