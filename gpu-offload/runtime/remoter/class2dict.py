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
_NAME_TO_TYPE: dict[str, type[Any]] = {}
_TYPE_TO_NAME: dict[type[Any], str] = {}


def _qualname(cls: type) -> str:
    return _TYPE_TO_NAME.get(cls, f"{cls.__module__}:{cls.__qualname__}")


def register_type(cls: type[Any], *, name: str | None = None) -> None:
    """Register a stable wire name for a class2dict-serialized type."""
    wire_name = name or f"{cls.__module__}:{cls.__qualname__}"
    module_name, separator, qualname = wire_name.partition(":")
    if not separator or not module_name or not qualname:
        raise ValueError("class2dict type name must use the format 'module:qualname'")

    registered_type = _NAME_TO_TYPE.get(wire_name)
    if registered_type is not None and registered_type is not cls:
        raise ValueError(f"class2dict type name {wire_name!r} is already registered")

    registered_name = _TYPE_TO_NAME.get(cls)
    if registered_name is not None and registered_name != wire_name:
        raise ValueError(f"class {cls!r} is already registered as {registered_name!r}")

    _NAME_TO_TYPE[wire_name] = cls
    _TYPE_TO_NAME[cls] = wire_name


def _resolve(path: str) -> type:
    registered_type = _NAME_TO_TYPE.get(path)
    if registered_type is not None:
        return registered_type

    module_name, _, qualname = path.partition(":")
    try:
        obj: Any = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise TypeError(
            f"Cannot reconstruct class2dict type {path!r}: module {module_name!r} is not importable. "
            "Install the defining module on this endpoint or register the local equivalent with "
            "remoter.register_class2dict_type(..., wire_name=<sender type name>)."
        ) from exc
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type):
        raise TypeError(f"Resolved class2dict type {path!r} to non-type object {obj!r}")
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


__all__ = ["to_dict", "from_dict", "register_type", "TYPE_KEY", "VALUE_KEY"]
