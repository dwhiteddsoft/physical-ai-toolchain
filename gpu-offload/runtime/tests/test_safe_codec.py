from __future__ import annotations

import threading
import uuid

import pytest

from remoter import class2dict, remoter
from remoter.safe_codec import (
    AdapterContext,
    AdapterRegistry,
    CodecLimits,
    CodecLimitsError,
    CodecTypeError,
    TypeAdapter,
    dumps,
    loads,
)


def test_safe_builtins_round_trip() -> None:
    registry = AdapterRegistry()
    payload = {
        "none": None,
        "bool": True,
        "int": 7,
        "float": 2.5,
        "str": "hello",
        "bytes": b"abc",
        "list": [1, "x", False],
        "tuple": ("a", 1),
        "dict": {"k": "v"},
        "uuid": uuid.uuid4(),
    }
    encoded = dumps(payload, registry, limits=CodecLimits(), context=AdapterContext(role="test"))
    decoded = loads(encoded, registry, limits=CodecLimits(), context=AdapterContext(role="test"))
    assert decoded == payload


def test_arbitrary_precision_integers_round_trip() -> None:
    registry = AdapterRegistry()
    payload = [2**64, -(2**63) - 1, 2**1024, -(2**1024)]

    encoded = dumps(payload, registry, limits=CodecLimits(), context=AdapterContext(role="test"))
    decoded = loads(encoded, registry, limits=CodecLimits(), context=AdapterContext(role="test"))

    assert decoded == payload


def test_class2dict_preserves_uuid_for_safe_codec() -> None:
    value = uuid.uuid4()

    converted = class2dict.to_dict({"id": value})
    encoded = remoter.serialize_payload(converted)

    assert converted["id"] is value
    assert remoter.deserialize_payload(encoded) == {"id": value}


def test_class2dict_reconstruction_does_not_call_constructor() -> None:
    class ConstructorHasSideEffects:
        def __init__(self) -> None:
            raise AssertionError("constructor must not run during deserialization")

    original = object.__new__(ConstructorHasSideEffects)
    original.value = 7
    converted = class2dict.to_dict(original)

    decoded = class2dict.from_dict(converted, cls=ConstructorHasSideEffects)

    assert isinstance(decoded, ConstructorHasSideEffects)
    assert decoded.value == 7


def test_unknown_type_fails_without_adapter_and_no_reduce_exec() -> None:
    class Evil:
        def __init__(self) -> None:
            self.reduce_called = False

        def __reduce__(self):  # pragma: no cover - must never be invoked
            self.reduce_called = True
            raise AssertionError("__reduce__ should never run")

    registry = AdapterRegistry()
    obj = Evil()

    with pytest.raises(CodecTypeError):
        dumps(obj, registry, limits=CodecLimits(), context=AdapterContext(role="test"))

    assert obj.reduce_called is False


def test_limit_enforcement() -> None:
    registry = AdapterRegistry()
    with pytest.raises(CodecLimitsError):
        dumps(
            "x" * 20,
            registry,
            limits=CodecLimits(max_str_length=5),
            context=AdapterContext(role="test"),
        )


def test_meta_remote_uuid_round_trip() -> None:
    class DummyRemote:
        def __init__(self) -> None:
            self.uuid_rmt0bf = uuid.uuid4()
            self.rmtloc_rmt0bf = "tcp://127.0.0.1:9000"

    meta = remoter.MetaRemotedUUID(DummyRemote())
    encoded = remoter.serialize_payload(meta)
    decoded = remoter.deserialize_payload(encoded)
    assert isinstance(decoded, remoter.MetaRemotedUUID)
    assert decoded.uuid_rmt0bf == meta.uuid_rmt0bf
    assert decoded.rmtloc_rmt0bf == meta.rmtloc_rmt0bf
    assert decoded.name == meta.name


def test_remote_error_descriptor_round_trip() -> None:
    runtime = remoter.Remoter.createemptyinstance()
    runtime.remotedClasses = {}
    funcargs = {"key": "unit/test", "loc": "direct"}

    payload = runtime.encode_result(funcargs, None, ValueError("bad input"), None)
    _, _, ex = runtime.decode_result(payload, "direct", None)

    assert isinstance(ex, remoter.RemoteExecutionError)
    assert "ValueError" in str(ex)
    assert "bad input" in str(ex)


def test_remote_attribute_error_preserves_python_attribute_fallback() -> None:
    runtime = remoter.Remoter.createemptyinstance()
    runtime.remotedClasses = {}
    funcargs = {"key": "unit/objgetattr", "loc": "direct"}

    payload = runtime.encode_result(funcargs, None, AttributeError("value2x"), None)
    _, _, ex = runtime.decode_result(payload, "direct", None)

    assert type(ex) is AttributeError
    assert str(ex) == "value2x"


def test_send_result_returns_serialization_failure_to_client() -> None:
    class FakeMessenger:
        def __init__(self) -> None:
            self.messages: list[bytes] = []

        def senddata(self, message: bytes) -> None:
            self.messages.append(message)

    runtime = remoter.Remoter.createemptyinstance()
    runtime.remotedClasses = {}
    fnid = uuid.uuid4()
    messenger = FakeMessenger()
    conn = {
        "alive": True,
        "classes": set(),
        "fns": {fnid: object()},
        "lock": threading.Lock(),
    }
    funcargs = {"key": "unit/test", "loc": "direct"}

    runtime.sendResult(messenger, conn, fnid, object(), None, funcargs)

    assert len(messenger.messages) == 1
    message = messenger.messages[0]
    assert message[1:17] == fnid.bytes
    _, result, ex = runtime.decode_result(message[17:], "direct", None)
    assert result is None
    assert isinstance(ex, remoter.RemoteExecutionError)
    assert "Cannot serialize object" in str(ex)
    assert fnid not in conn["fns"]


def test_imagep_style_adapter() -> None:
    class ImageP:
        def __init__(self, b: bytes, recompress_quality: int = 10) -> None:
            self.b = b
            self.rmtloc_rmt0bf: str | None = None
            self.recompress_quality = recompress_quality

        def setremoteloc(self, loc: str) -> None:
            self.rmtloc_rmt0bf = loc

    def encode_state(image: ImageP) -> dict[str, object]:
        image_bytes = image.b if image.rmtloc_rmt0bf in {"direct", "directqueue"} else image.b[:4]
        return {
            "b": image_bytes,
            "rmtloc": image.rmtloc_rmt0bf,
            "recompress_quality": image.recompress_quality,
        }

    def decode_state(state: dict[str, object]) -> ImageP:
        image = ImageP(state["b"])  # type: ignore[arg-type]
        image.rmtloc_rmt0bf = state["rmtloc"]  # type: ignore[assignment]
        image.recompress_quality = state["recompress_quality"]  # type: ignore[assignment]
        return image

    try:
        remoter.register_state_adapter(
            ext_code=30,
            cls=ImageP,
            encode_state=encode_state,
            decode_state=decode_state,
        )
    except ValueError:
        # Adapter may already be registered when tests are re-run in the same interpreter.
        pass

    image = ImageP(b"abcdefghij")
    image.setremoteloc("tcp://10.0.0.1:9000")
    encoded = remoter.serialize_payload(image)
    decoded = remoter.deserialize_payload(encoded)

    assert isinstance(decoded, ImageP)
    assert decoded.b == b"abcd"
    assert decoded.rmtloc_rmt0bf == "tcp://10.0.0.1:9000"
