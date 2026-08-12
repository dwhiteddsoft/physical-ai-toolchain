from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import msgpack


class CodecError(Exception):
    """Base codec error."""


class CodecLimitsError(CodecError):
    """Raised when message exceeds configured limits."""


class CodecTypeError(CodecError):
    """Raised when a type is unsupported and unregistered."""


@dataclass(frozen=True)
class CodecLimits:
    max_encoded_bytes: int = 8 * 1024 * 1024
    max_nesting: int = 64
    max_collection_length: int = 100_000
    max_str_length: int = 1_048_576
    max_bytes_length: int = 8 * 1024 * 1024


@dataclass(frozen=True)
class AdapterContext:
    role: str


@dataclass(frozen=True)
class TypeAdapter:
    ext_code: int
    py_type: type[Any]
    encode: Callable[[Any, AdapterContext], Any]
    decode: Callable[[Any, AdapterContext], Any]


@dataclass(frozen=True)
class _ExtEnvelope:
    code: int
    data: bytes


class AdapterRegistry:
    """Explicit adapter registry for non-builtin types."""

    def __init__(self) -> None:
        self._code_to_adapter: dict[int, TypeAdapter] = {}
        self._type_to_adapter: dict[type[Any], TypeAdapter] = {}
        self._fallback_adapter: TypeAdapter | None = None

    def register(self, adapter: TypeAdapter) -> None:
        if adapter.ext_code in _RESERVED_EXT_CODES:
            raise ValueError(f"ext_code {adapter.ext_code} is reserved")
        if not 16 <= adapter.ext_code <= 127:
            raise ValueError("ext_code must be in range 16..127")
        if adapter.ext_code in self._code_to_adapter:
            raise ValueError(f"ext_code {adapter.ext_code} already registered")
        if adapter.py_type in self._type_to_adapter:
            raise ValueError(f"type {adapter.py_type} already registered")
        self._code_to_adapter[adapter.ext_code] = adapter
        self._type_to_adapter[adapter.py_type] = adapter

    def register_fallback(self, adapter: TypeAdapter) -> None:
        if self._fallback_adapter is not None:
            raise ValueError("fallback adapter already registered")
        if adapter.ext_code in _RESERVED_EXT_CODES:
            raise ValueError(f"ext_code {adapter.ext_code} is reserved")
        if not 16 <= adapter.ext_code <= 127:
            raise ValueError("ext_code must be in range 16..127")
        if adapter.ext_code in self._code_to_adapter:
            raise ValueError(f"ext_code {adapter.ext_code} already registered")
        self._code_to_adapter[adapter.ext_code] = adapter
        self._fallback_adapter = adapter

    def find_by_type(self, value: Any) -> TypeAdapter | None:
        # First hit exact type registrations; then fallback to isinstance matching.
        adapter = self._type_to_adapter.get(type(value))
        if adapter is not None:
            return adapter
        for registered_type, candidate in self._type_to_adapter.items():
            if isinstance(value, registered_type):
                return candidate
        return None

    def find_by_code(self, code: int) -> TypeAdapter | None:
        return self._code_to_adapter.get(code)

    def find_fallback(self) -> TypeAdapter | None:
        return self._fallback_adapter


_VERSION = 1
_RESERVED_EXT_TUPLE = 1
_RESERVED_EXT_UUID = 2
_RESERVED_EXT_CODES = {_RESERVED_EXT_TUPLE, _RESERVED_EXT_UUID}


def dumps(
    obj: Any,
    registry: AdapterRegistry,
    *,
    limits: CodecLimits,
    context: AdapterContext,
) -> bytes:
    payload = _encode_value(obj, 0, registry, limits, context)
    packet = {"v": _VERSION, "p": payload}
    encoded = msgpack.packb(packet, use_bin_type=True, strict_types=True)
    if len(encoded) > limits.max_encoded_bytes:
        raise CodecLimitsError(f"encoded bytes {len(encoded)} exceed max_encoded_bytes={limits.max_encoded_bytes}")
    return encoded


def loads(
    data: bytes,
    registry: AdapterRegistry,
    *,
    limits: CodecLimits,
    context: AdapterContext,
) -> Any:
    if len(data) > limits.max_encoded_bytes:
        raise CodecLimitsError(f"encoded bytes {len(data)} exceed max_encoded_bytes={limits.max_encoded_bytes}")

    def _ext_hook(code: int, ext_data: bytes) -> _ExtEnvelope:
        return _ExtEnvelope(code=code, data=ext_data)

    packet = msgpack.unpackb(
        data,
        raw=False,
        strict_map_key=False,
        ext_hook=_ext_hook,
        max_str_len=limits.max_str_length,
        max_bin_len=limits.max_bytes_length,
        max_array_len=limits.max_collection_length,
        max_map_len=limits.max_collection_length,
        max_ext_len=limits.max_bytes_length,
    )
    if not isinstance(packet, dict) or packet.get("v") != _VERSION or "p" not in packet:
        raise CodecError("invalid codec packet envelope")
    return _decode_value(packet["p"], 0, registry, limits, context)


def _encode_value(
    value: Any,
    depth: int,
    registry: AdapterRegistry,
    limits: CodecLimits,
    context: AdapterContext,
) -> Any:
    if depth > limits.max_nesting:
        raise CodecLimitsError(f"nesting depth {depth} exceeds max_nesting={limits.max_nesting}")

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > limits.max_str_length:
            raise CodecLimitsError(f"string length {len(value)} exceeds max_str_length={limits.max_str_length}")
        return value
    if isinstance(value, bytes):
        if len(value) > limits.max_bytes_length:
            raise CodecLimitsError(f"bytes length {len(value)} exceeds max_bytes_length={limits.max_bytes_length}")
        return value
    if isinstance(value, uuid.UUID):
        return msgpack.ExtType(_RESERVED_EXT_UUID, value.bytes)
    if isinstance(value, list):
        if len(value) > limits.max_collection_length:
            raise CodecLimitsError(
                f"list length {len(value)} exceeds max_collection_length={limits.max_collection_length}"
            )
        return [_encode_value(item, depth + 1, registry, limits, context) for item in value]
    if isinstance(value, tuple):
        if len(value) > limits.max_collection_length:
            raise CodecLimitsError(
                f"tuple length {len(value)} exceeds max_collection_length={limits.max_collection_length}"
            )
        encoded = [_encode_value(item, depth + 1, registry, limits, context) for item in value]
        return msgpack.ExtType(
            _RESERVED_EXT_TUPLE,
            msgpack.packb(encoded, use_bin_type=True, strict_types=True),
        )
    if isinstance(value, dict):
        if len(value) > limits.max_collection_length:
            raise CodecLimitsError(
                f"dict length {len(value)} exceeds max_collection_length={limits.max_collection_length}"
            )
        encoded_dict: dict[Any, Any] = {}
        for key, item in value.items():
            encoded_key = _encode_value(key, depth + 1, registry, limits, context)
            if not _is_hashable(encoded_key):
                raise CodecTypeError(f"decoded dict key type {type(key)} is not hashable")
            encoded_dict[encoded_key] = _encode_value(item, depth + 1, registry, limits, context)
        return encoded_dict

    adapter = registry.find_by_type(value)
    if adapter is None:
        adapter = registry.find_fallback()
        if adapter is None:
            raise CodecTypeError(f"unsupported type {type(value)!r}; register an explicit adapter")

    payload = adapter.encode(value, context)
    encoded_payload = _encode_value(payload, depth + 1, registry, limits, context)
    return msgpack.ExtType(
        adapter.ext_code,
        msgpack.packb(encoded_payload, use_bin_type=True, strict_types=True),
    )


def _decode_value(
    value: Any,
    depth: int,
    registry: AdapterRegistry,
    limits: CodecLimits,
    context: AdapterContext,
) -> Any:
    if depth > limits.max_nesting:
        raise CodecLimitsError(f"nesting depth {depth} exceeds max_nesting={limits.max_nesting}")

    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        if isinstance(value, str) and len(value) > limits.max_str_length:
            raise CodecLimitsError(f"string length {len(value)} exceeds max_str_length={limits.max_str_length}")
        if isinstance(value, bytes) and len(value) > limits.max_bytes_length:
            raise CodecLimitsError(f"bytes length {len(value)} exceeds max_bytes_length={limits.max_bytes_length}")
        return value

    if isinstance(value, list):
        if len(value) > limits.max_collection_length:
            raise CodecLimitsError(
                f"list length {len(value)} exceeds max_collection_length={limits.max_collection_length}"
            )
        return [_decode_value(item, depth + 1, registry, limits, context) for item in value]

    if isinstance(value, dict):
        if len(value) > limits.max_collection_length:
            raise CodecLimitsError(
                f"dict length {len(value)} exceeds max_collection_length={limits.max_collection_length}"
            )
        decoded_dict: dict[Any, Any] = {}
        for key, item in value.items():
            decoded_key = _decode_value(key, depth + 1, registry, limits, context)
            if not _is_hashable(decoded_key):
                raise CodecTypeError(f"decoded dict key type {type(decoded_key)} is not hashable")
            decoded_dict[decoded_key] = _decode_value(item, depth + 1, registry, limits, context)
        return decoded_dict

    if isinstance(value, _ExtEnvelope):
        if value.code == _RESERVED_EXT_TUPLE:
            as_list = msgpack.unpackb(
                value.data,
                raw=False,
                strict_map_key=False,
                ext_hook=lambda c, d: _ExtEnvelope(c, d),
                max_str_len=limits.max_str_length,
                max_bin_len=limits.max_bytes_length,
                max_array_len=limits.max_collection_length,
                max_map_len=limits.max_collection_length,
                max_ext_len=limits.max_bytes_length,
            )
            if not isinstance(as_list, list):
                raise CodecError("tuple extension payload must be a list")
            return tuple(_decode_value(item, depth + 1, registry, limits, context) for item in as_list)

        if value.code == _RESERVED_EXT_UUID:
            if len(value.data) != 16:
                raise CodecError("UUID extension payload must be 16 bytes")
            return uuid.UUID(bytes=value.data)

        adapter = registry.find_by_code(value.code)
        if adapter is None:
            raise CodecTypeError(f"unknown extension code {value.code}")

        raw_payload = msgpack.unpackb(
            value.data,
            raw=False,
            strict_map_key=False,
            ext_hook=lambda c, d: _ExtEnvelope(c, d),
            max_str_len=limits.max_str_length,
            max_bin_len=limits.max_bytes_length,
            max_array_len=limits.max_collection_length,
            max_map_len=limits.max_collection_length,
            max_ext_len=limits.max_bytes_length,
        )
        decoded_payload = _decode_value(raw_payload, depth + 1, registry, limits, context)
        return adapter.decode(decoded_payload, context)

    raise CodecTypeError(f"unsupported decoded wire type {type(value)!r}")


def _is_hashable(value: Any) -> bool:
    try:
        hash(value)
        return True
    except TypeError:
        return False
