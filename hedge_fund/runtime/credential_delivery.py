"""Private framed transport for external runtime credentials."""

from __future__ import annotations

import json
import os
import re
import socket
import struct
import sys
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Mapping

from hedge_fund.runtime.external_credentials import ExternalCredentialError

MAX_DELIVERY_FRAME_BYTES = 32 * 1024
MAX_DELIVERY_VALUE_BYTES = 16 * 1024
_PROVIDER_ID = re.compile(r"[a-z][a-z0-9._-]{0,63}")
_ROOT_ID = re.compile(r"[a-fA-F0-9]{64}")
_IDENTITY = re.compile(r"[A-Za-z0-9._:-]{1,128}")
SOCKET_PATH = Path("/tmp/aihf-credentials/credential.sock")
_REASONS = frozenset(
    {
        "provider-not-allowed",
        "destination-not-allowed",
        "generation-conflict",
        "delivery-replayed",
        "target-changed",
        "invalid-value",
        "delivery-denied",
        "protocol-error",
        "transport-unavailable",
    }
)


class DeliveryProtocolError(ValueError):
    """Framed credential protocol input is invalid."""


@dataclass(frozen=True, slots=True)
class DeliveryEnvelope:
    """One bounded status or publish request."""

    action: str
    provider_id: str
    destination: str
    root_id: str | None = None
    instance_id: str | None = None
    expected_generation: int | None = None
    delivery_id: str | None = None
    value: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.action not in {"status", "publish"}:
            raise DeliveryProtocolError("delivery action is invalid")
        for field_name in ("provider_id", "destination"):
            field_value = getattr(self, field_name)
            if not isinstance(field_value, str) or not _PROVIDER_ID.fullmatch(field_value.casefold()):
                raise DeliveryProtocolError("delivery identity is invalid")
            object.__setattr__(self, field_name, field_value.casefold())
        if self.action == "status":
            if any(value is not None for value in (self.root_id, self.instance_id, self.expected_generation, self.delivery_id, self.value)):
                raise DeliveryProtocolError("status request fields are invalid")
            return
        if not isinstance(self.root_id, str) or not _ROOT_ID.fullmatch(self.root_id):
            raise DeliveryProtocolError("delivery target is invalid")
        if not isinstance(self.instance_id, str) or not _IDENTITY.fullmatch(self.instance_id):
            raise DeliveryProtocolError("delivery target is invalid")
        if type(self.expected_generation) is not int or self.expected_generation < 0:
            raise DeliveryProtocolError("delivery generation is invalid")
        if not isinstance(self.delivery_id, str) or not _IDENTITY.fullmatch(self.delivery_id):
            raise DeliveryProtocolError("delivery identity is invalid")
        _validate_value(self.value)
        object.__setattr__(self, "root_id", self.root_id.casefold())

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> DeliveryEnvelope:
        if not isinstance(value, Mapping):
            raise DeliveryProtocolError("delivery request is invalid")
        action = value.get("action")
        fields = (
            {"action", "provider_id", "destination"}
            if action == "status"
            else {
                "action",
                "provider_id",
                "destination",
                "root_id",
                "instance_id",
                "expected_generation",
                "delivery_id",
                "value",
            }
        )
        if set(value) != fields:
            raise DeliveryProtocolError("delivery request fields are invalid")
        try:
            return cls(**value)
        except (TypeError, DeliveryProtocolError):
            raise DeliveryProtocolError("delivery request is invalid") from None

    def to_mapping(self) -> dict[str, object]:
        record: dict[str, object] = {
            "action": self.action,
            "provider_id": self.provider_id,
            "destination": self.destination,
        }
        if self.action == "publish":
            record.update(
                {
                    "root_id": self.root_id,
                    "instance_id": self.instance_id,
                    "expected_generation": self.expected_generation,
                    "delivery_id": self.delivery_id,
                    "value": self.value,
                }
            )
        return record


@dataclass(frozen=True, slots=True)
class DeliveryReply:
    """Value-free delivery status."""

    state: str
    generation: int
    provider_id: str
    destination: str
    root_id: str | None = None
    instance_id: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"available", "requires-auth", "revoked", "denied"}:
            raise DeliveryProtocolError("delivery status is invalid")
        if type(self.generation) is not int or self.generation < 0:
            raise DeliveryProtocolError("delivery status is invalid")
        if not isinstance(self.provider_id, str) or not _PROVIDER_ID.fullmatch(self.provider_id):
            raise DeliveryProtocolError("delivery status is invalid")
        if not isinstance(self.destination, str) or not _PROVIDER_ID.fullmatch(self.destination):
            raise DeliveryProtocolError("delivery status is invalid")
        if self.root_id is not None and (not isinstance(self.root_id, str) or not _ROOT_ID.fullmatch(self.root_id)):
            raise DeliveryProtocolError("delivery status is invalid")
        if self.instance_id is not None and (not isinstance(self.instance_id, str) or not _IDENTITY.fullmatch(self.instance_id)):
            raise DeliveryProtocolError("delivery status is invalid")
        if self.reason_code is not None and self.reason_code not in _REASONS:
            raise DeliveryProtocolError("delivery status is invalid")

    def to_mapping(self) -> dict[str, object]:
        return {
            "state": self.state,
            "generation": self.generation,
            "provider_id": self.provider_id,
            "destination": self.destination,
            "root_id": self.root_id,
            "instance_id": self.instance_id,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_mapping(cls, value: object) -> DeliveryReply:
        fields = {
            "state",
            "generation",
            "provider_id",
            "destination",
            "root_id",
            "instance_id",
            "reason_code",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise DeliveryProtocolError("delivery status is malformed")
        try:
            return cls(**value)
        except (TypeError, DeliveryProtocolError):
            raise DeliveryProtocolError("delivery status is malformed") from None


def encode_delivery_reply(reply: DeliveryReply) -> bytes:
    if not isinstance(reply, DeliveryReply):
        raise DeliveryProtocolError("delivery status is invalid")
    payload = json.dumps(reply.to_mapping(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(payload) + 4 > MAX_DELIVERY_FRAME_BYTES:
        raise DeliveryProtocolError("delivery status exceeds its bound")
    return len(payload).to_bytes(4, "big") + payload


def read_delivery_reply(stream: BinaryIO) -> DeliveryReply:
    header = _read_exact(stream, 4)
    payload_size = int.from_bytes(header, "big")
    if payload_size < 1 or payload_size + 4 > MAX_DELIVERY_FRAME_BYTES:
        raise DeliveryProtocolError("delivery status exceeds its bound")
    payload = _read_exact(stream, payload_size)
    if stream.read(1) != b"":
        raise DeliveryProtocolError("delivery status contains trailing data")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DeliveryProtocolError("delivery status is malformed") from None
    return DeliveryReply.from_mapping(record)


class CredentialDeliveryServer:
    """Receive one framed request over owner-only local IPC."""

    def __init__(
        self,
        lease_store,
        *,
        socket_path: Path = SOCKET_PATH,
        peer_validator=None,
        admission_check=None,
    ) -> None:
        self._lease_store = lease_store
        self._socket_path = Path(socket_path)
        self._peer_validator = peer_validator or _valid_delivery_peer
        if admission_check is not None and not callable(admission_check):
            raise DeliveryProtocolError("delivery admission check is invalid")
        self._admission_check = admission_check
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._directory_created = False
        self._socket_created = False

    def start(self) -> None:
        if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
            raise DeliveryProtocolError("private local IPC is unavailable")
        if len(os.fsencode(self._socket_path)) >= 104:
            raise DeliveryProtocolError("private local IPC path is invalid")
        parent = self._socket_path.parent
        try:
            parent.mkdir(mode=0o700)
            self._directory_created = True
            info = parent.stat()
            if not parent.is_dir() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise DeliveryProtocolError("private local IPC permissions are invalid")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket = server
            server.bind(os.fspath(self._socket_path))
            self._socket_created = True
            os.chmod(self._socket_path, 0o600)
            server.listen(4)
            server.settimeout(0.25)
        except (OSError, DeliveryProtocolError):
            self.close()
            raise DeliveryProtocolError("private local IPC is unavailable") from None
        self._thread = threading.Thread(target=self._serve, name="credential-delivery-ipc", daemon=True)
        self._thread.start()

    def close(self) -> None:
        server = self._socket
        self._socket = None
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        try:
            if self._socket_created and self._socket_path.is_socket():
                self._socket_path.unlink()
            if self._directory_created:
                self._socket_path.parent.rmdir()
        except OSError:
            pass
        self._directory_created = False
        self._socket_created = False

    def handle(self, request: DeliveryEnvelope) -> DeliveryReply:
        if not isinstance(request, DeliveryEnvelope):
            return DeliveryReply("denied", 0, "openai", "openai", reason_code="protocol-error")
        try:
            if self._admission_check is not None:
                self._admission_check()
            if request.action == "status":
                status = self._lease_store.delivery_status(
                    request.provider_id,
                    destination=request.destination,
                )
                return DeliveryReply(**status, reason_code=None)
            handle = self._lease_store.publish(
                request.provider_id,
                request.value,
                expected_generation=request.expected_generation,
                delivery_id=request.delivery_id,
                root_id=request.root_id,
                instance_id=request.instance_id,
                destination=request.destination,
            )
            return DeliveryReply(
                state="available",
                generation=handle.generation,
                provider_id=handle.provider_id,
                destination=handle.destination,
                root_id=handle.root_id,
                instance_id=handle.instance_id,
            )
        except Exception as exc:
            reason = provider_delivery_error(exc)
            return DeliveryReply(
                state="denied",
                generation=0,
                provider_id=request.provider_id,
                destination=request.destination,
                reason_code=reason,
            )

    def _serve(self) -> None:
        server = self._socket
        while server is not None:
            try:
                connection, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                try:
                    connection.settimeout(30.0)
                    if not self._peer_validator(connection):
                        continue
                    stream = connection.makefile("rb")
                    try:
                        request = read_delivery_frame(stream)
                    finally:
                        stream.close()
                    connection.sendall(encode_delivery_reply(self.handle(request)))
                except (DeliveryProtocolError, OSError):
                    try:
                        connection.sendall(
                            encode_delivery_reply(
                                DeliveryReply(
                                    "denied",
                                    0,
                                    "openai",
                                    "openai",
                                    reason_code="protocol-error",
                                )
                            )
                        )
                    except OSError:
                        pass


def receive_delivery_request(
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    socket_path: Path = SOCKET_PATH,
) -> int:
    input_stream = sys.stdin.buffer if stdin is None else stdin
    output_stream = sys.stdout.buffer if stdout is None else stdout
    try:
        request = read_delivery_frame(input_stream)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30.0)
            client.connect(os.fspath(socket_path))
            client.sendall(encode_delivery_frame(request))
            client.shutdown(socket.SHUT_WR)
            response = read_delivery_reply(client.makefile("rb"))
        output_stream.write(encode_delivery_reply(response))
        output_stream.flush()
        return 0 if response.state != "denied" else 2
    except (DeliveryProtocolError, OSError, TimeoutError):
        response = DeliveryReply(
            "denied",
            0,
            "openai",
            "openai",
            reason_code="transport-unavailable",
        )
        try:
            output_stream.write(encode_delivery_reply(response))
            output_stream.flush()
        except OSError:
            pass
        return 2


def _valid_delivery_peer(connection: socket.socket) -> bool:
    if not hasattr(socket, "SO_PEERCRED"):
        return False
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", raw)
        if pid < 1 or uid != os.geteuid():
            return False
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except (OSError, struct.error):
        return False
    return b"hedge_fund.runtime.credential_delivery" in arguments and b"--receive" in arguments


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["--receive"]:
        return 2
    return receive_delivery_request()


if __name__ == "__main__":
    raise SystemExit(main())


def encode_delivery_frame(request: DeliveryEnvelope | Mapping[str, object]) -> bytes:
    if isinstance(request, DeliveryEnvelope):
        envelope = request
    else:
        envelope = DeliveryEnvelope.from_mapping(request)
    try:
        payload = json.dumps(
            envelope.to_mapping(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise DeliveryProtocolError("delivery request is invalid") from None
    frame_size = 4 + len(payload)
    if frame_size > MAX_DELIVERY_FRAME_BYTES:
        raise DeliveryProtocolError("delivery frame exceeds its bound")
    return len(payload).to_bytes(4, "big") + payload


def read_delivery_frame(stream: BinaryIO) -> DeliveryEnvelope:
    if not hasattr(stream, "read"):
        raise DeliveryProtocolError("delivery stream is invalid")
    header = _read_exact(stream, 4)
    payload_size = int.from_bytes(header, "big")
    if payload_size < 1 or payload_size + 4 > MAX_DELIVERY_FRAME_BYTES:
        raise DeliveryProtocolError("delivery frame exceeds its bound")
    payload = _read_exact(stream, payload_size)
    if stream.read(1) != b"":
        raise DeliveryProtocolError("delivery stream contains trailing data")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DeliveryProtocolError("delivery frame is malformed") from None
    if not isinstance(record, dict):
        raise DeliveryProtocolError("delivery frame is malformed")
    return DeliveryEnvelope.from_mapping(record)


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not isinstance(chunk, bytes) or not chunk:
            raise DeliveryProtocolError("delivery frame is incomplete")
        result.extend(chunk)
    return bytes(result)


def _validate_value(value: object) -> None:
    if not isinstance(value, str) or not value or not value.strip():
        raise DeliveryProtocolError("credential value is invalid")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise DeliveryProtocolError("credential value is invalid")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise DeliveryProtocolError("credential value is invalid") from None
    if size > MAX_DELIVERY_VALUE_BYTES:
        raise DeliveryProtocolError("credential value is invalid")


def provider_delivery_error(exc: Exception) -> str:
    """Map private lease errors to a value-free protocol code."""
    if isinstance(exc, ExternalCredentialError):
        message = str(exc)
        if message == "provider is not allowed":
            return "provider-not-allowed"
        if message == "provider destination is not allowed":
            return "destination-not-allowed"
        if message == "credential generation changed":
            return "generation-conflict"
        if message == "delivery was already used":
            return "delivery-replayed"
        if message == "runtime target changed":
            return "target-changed"
        if message in {"credential value is invalid", "credential value exceeds its bound"}:
            return "invalid-value"
    return "delivery-denied"
