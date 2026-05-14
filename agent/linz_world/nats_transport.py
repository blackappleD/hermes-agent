"""Minimal NATS transport for Linz World events."""

from __future__ import annotations

import json
import socket
import ssl
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from .models import utc_now_iso


class NatsPublishError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NatsServer:
    host: str
    port: int
    use_tls: bool = False
    user: str = ""
    password: str = ""
    token: str = ""


def publish_linz_event(
    *,
    nats_url: str,
    subject: str,
    event_type: str,
    payload: dict[str, Any],
    event_id: str = "",
    connect_timeout: float = 3.0,
) -> dict[str, Any]:
    """Publish a formal Linz World event envelope through NATS core protocol."""

    server = _parse_nats_url(nats_url)
    event_id = str(event_id or uuid.uuid4())
    timestamp = utc_now_iso()
    envelope = {
        "event_type": event_type,
        "event_id": event_id,
        "timestamp": timestamp,
        "payload": payload,
    }
    encoded = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

    client = _NatsCoreClient(server, timeout=connect_timeout)
    try:
        client.connect()
        client.publish(subject, encoded)
    finally:
        client.close()

    return {
        "transport": "nats",
        "subject": subject,
        "event_type": event_type,
        "world_event_id": event_id,
        "event_id": event_id,
        "acknowledged": True,
        "nats_sequence": "",
        "published_at": timestamp,
        "diagnostic": "NATS core publish acknowledged by PONG; stream sequence is unavailable without JetStream ack.",
    }


def decode_linz_nats_message(subject: str, data: bytes | str) -> dict[str, Any]:
    text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError as exc:
        raise NatsPublishError("invalid_event_envelope", f"NATS message payload is not JSON: {exc}") from exc
    if not isinstance(envelope, dict):
        raise NatsPublishError("invalid_event_envelope", "NATS message payload must be an event envelope object.")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    event_type = str(envelope.get("event_type") or envelope.get("eventType") or "")
    event_id = str(envelope.get("event_id") or envelope.get("eventId") or uuid.uuid4())
    source = _source_from_payload(payload)
    return {
        "event_id": event_id,
        "subject": subject,
        "event_type": event_type,
        "payload": payload,
        "source": source,
        "occurred_at": str(envelope.get("timestamp") or envelope.get("occurred_at") or utc_now_iso()),
    }


class NatsEventListener:
    """Background NATS core subscriber that emits normalized Linz World events."""

    def __init__(
        self,
        *,
        nats_url: str,
        subjects: list[str],
        on_event: Callable[[dict[str, Any]], None],
        connect_timeout: float = 3.0,
    ):
        self.nats_url = nats_url
        self.subjects = [str(subject).strip() for subject in subjects if str(subject or "").strip()]
        self.on_event = on_event
        self.connect_timeout = connect_timeout
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error = ""
        self._startup_error = ""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if not self.subjects:
            raise NatsPublishError("missing_subscriptions", "No Linz World NATS subjects are configured for subscribe.")
        self._stop.clear()
        self._ready.clear()
        self._startup_error = ""
        self._thread = threading.Thread(target=self._run, name="linz-world-nats-listener", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.connect_timeout + 1.0):
            raise NatsPublishError("transport_unavailable", "NATS listener did not start before timeout.")
        if self._startup_error:
            raise NatsPublishError("transport_unavailable", self._startup_error)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        client: _NatsCoreClient | None = None
        try:
            server = _parse_nats_url(self.nats_url)
            client = _NatsCoreClient(server, timeout=self.connect_timeout)
            client.connect()
            if client.sock is not None:
                client.sock.settimeout(0.25)
            for index, subject in enumerate(self.subjects, start=1):
                sid = str(index)
                client._write(f"SUB {subject} {sid}\r\n".encode("ascii"))
            client._ping()
            self._ready.set()
            while not self._stop.is_set():
                try:
                    line = client._read_line()
                except socket.timeout:
                    continue
                if not line or line == "+OK":
                    continue
                if line == "PING":
                    client._write(b"PONG\r\n")
                    continue
                if line.startswith("-ERR"):
                    raise NatsPublishError("transport_rejected", line)
                if not line.startswith("MSG "):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                subject = parts[1]
                size = int(parts[-1])
                raw_payload = client._read_frame_payload(size)
                self.on_event(decode_linz_nats_message(subject, raw_payload))
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            if not self._ready.is_set():
                self._startup_error = self.last_error
                self._ready.set()
        finally:
            if not self._ready.is_set():
                self._ready.set()
            if client is not None:
                client.close()


def _parse_nats_url(raw_url: str) -> NatsServer:
    url = str(raw_url or "").strip()
    if not url:
        raise NatsPublishError("missing_transport", "Linz World nats_url is not configured.")
    parsed = urlsplit(url if "://" in url else f"nats://{url}")
    if parsed.scheme not in {"nats", "tcp", "tls"}:
        raise NatsPublishError("unsupported_transport", f"Unsupported Linz World NATS URL scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if not host:
        raise NatsPublishError("invalid_transport", "Linz World nats_url is missing a host.")
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    return NatsServer(
        host=host,
        port=int(parsed.port or 4222),
        use_tls=parsed.scheme == "tls",
        user=username if password else "",
        password=password,
        token=username if username and not password else "",
    )


def _source_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    actor_id = str(
        payload.get("from")
        or payload.get("publisher_os_id")
        or payload.get("deliverer_os_id")
        or payload.get("reviewer_os_id")
        or payload.get("counterparty_os_id")
        or ""
    )
    actor_name = str(
        payload.get("from_os_name")
        or payload.get("publisher_os_name")
        or payload.get("deliverer_os_name")
        or payload.get("reviewer_os_name")
        or ""
    )
    source = {}
    if actor_id:
        source["actor_id"] = actor_id
        source["os_id"] = actor_id
    if actor_name:
        source["actor_name"] = actor_name
    for key in ("room_id", "relationship_id", "task_id", "order_id", "requirement_id"):
        if payload.get(key):
            source[key] = str(payload[key])
    return source


class _NatsCoreClient:
    def __init__(self, server: NatsServer, *, timeout: float = 3.0):
        self.server = server
        self.timeout = timeout
        self.sock: socket.socket | ssl.SSLSocket | None = None
        self.buffer = bytearray()

    def connect(self) -> None:
        try:
            sock: socket.socket | ssl.SSLSocket = socket.create_connection(
                (self.server.host, self.server.port),
                timeout=self.timeout,
            )
            sock.settimeout(self.timeout)
            if self.server.use_tls:
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.server.host)
            self.sock = sock
            line = self._read_line()
            if line.startswith("-ERR"):
                raise NatsPublishError("transport_rejected", line)
            if line and not line.startswith("INFO"):
                raise NatsPublishError("invalid_transport", f"Unexpected NATS greeting: {line}")
            self._write_connect()
            self._ping()
        except NatsPublishError:
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise NatsPublishError("transport_unavailable", f"NATS connection failed: {exc}") from exc

    def publish(self, subject: str, data: bytes) -> None:
        self._write(f"PUB {subject} {len(data)}\r\n".encode("ascii"))
        self._write(data)
        self._write(b"\r\n")
        self._ping()

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _write_connect(self) -> None:
        options: dict[str, Any] = {
            "verbose": False,
            "pedantic": False,
            "lang": "python",
            "version": "0.1.0",
            "name": "hermes-linz",
            "protocol": 1,
        }
        if self.server.user:
            options["user"] = self.server.user
            options["pass"] = self.server.password
        elif self.server.token:
            options["auth_token"] = self.server.token
        self._write(f"CONNECT {json.dumps(options, separators=(',', ':'))}\r\n".encode("utf-8"))

    def _ping(self) -> None:
        self._write(b"PING\r\n")
        while True:
            line = self._read_line()
            if not line or line == "+OK":
                continue
            if line == "PING":
                self._write(b"PONG\r\n")
                continue
            if line == "PONG":
                return
            if line.startswith("-ERR"):
                raise NatsPublishError("transport_rejected", line)

    def _read_line(self) -> str:
        while b"\r\n" not in self.buffer:
            if self.sock is None:
                raise NatsPublishError("transport_unavailable", "NATS socket is not connected.")
            chunk = self.sock.recv(4096)
            if not chunk:
                raise NatsPublishError("transport_unavailable", "NATS connection closed before acknowledgement.")
            self.buffer.extend(chunk)
        line, _, rest = bytes(self.buffer).partition(b"\r\n")
        self.buffer = bytearray(rest)
        return line.decode("utf-8", errors="replace")

    def _read_frame_payload(self, size: int) -> bytes:
        while len(self.buffer) < size + 2:
            if self.sock is None:
                raise NatsPublishError("transport_unavailable", "NATS socket is not connected.")
            chunk = self.sock.recv(4096)
            if not chunk:
                raise NatsPublishError("transport_unavailable", "NATS connection closed during message payload.")
            self.buffer.extend(chunk)
        payload = bytes(self.buffer[:size])
        trailer = bytes(self.buffer[size : size + 2])
        if trailer != b"\r\n":
            raise NatsPublishError("invalid_transport", "Malformed NATS message frame.")
        self.buffer = self.buffer[size + 2 :]
        return payload

    def _write(self, data: bytes) -> None:
        if self.sock is None:
            raise NatsPublishError("transport_unavailable", "NATS socket is not connected.")
        try:
            self.sock.sendall(data)
        except OSError as exc:
            raise NatsPublishError("transport_unavailable", f"NATS write failed: {exc}") from exc
