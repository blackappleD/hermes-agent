import json
import socket
import threading

import pytest

from agent.linz_world.api_client import HttpLinzWorldService
from agent.linz_world.config import LinzWorldConfig
from agent.linz_world.nats_transport import NatsEventListener, NatsPublishError, publish_linz_event


class _FakeNatsServer:
    def __init__(self, *, push_subject="", push_envelope=None):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._closed = threading.Event()
        self.published: list[tuple[str, bytes]] = []
        self.connect_frame = ""
        self.push_subject = push_subject
        self.push_envelope = push_envelope
        self._push_sent = False
        self._subscriptions: dict[str, str] = {}
        host, port = self._sock.getsockname()
        self.url = f"nats://{host}:{port}"
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def close(self):
        self._closed.set()
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            socket.create_connection(("127.0.0.1", int(self.url.rsplit(":", 1)[1])), timeout=0.1).close()
        except OSError:
            pass
        self._thread.join(timeout=1)

    def _serve(self):
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(2)
            conn.sendall(b'INFO {"server_id":"test"}\r\n')
            while not self._closed.is_set():
                try:
                    line = _read_line(conn)
                except OSError:
                    return
                if not line:
                    return
                if line.startswith("CONNECT "):
                    self.connect_frame = line
                elif line == "PING":
                    conn.sendall(b"PONG\r\n")
                    self._maybe_push_message(conn)
                elif line.startswith("SUB "):
                    _, subject, sid = line.split()[:3]
                    self._subscriptions[sid] = subject
                elif line.startswith("PUB "):
                    parts = line.split()
                    subject = parts[1]
                    size = int(parts[-1])
                    payload = _read_exact(conn, size)
                    _read_exact(conn, 2)
                    self.published.append((subject, payload))

    def _maybe_push_message(self, conn: socket.socket) -> None:
        if self._push_sent or not self.push_subject or not self.push_envelope:
            return
        sid = next((sid for sid, subject in self._subscriptions.items() if subject == self.push_subject), "")
        if not sid:
            return
        payload = json.dumps(self.push_envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        conn.sendall(f"MSG {self.push_subject} {sid} {len(payload)}\r\n".encode("ascii"))
        conn.sendall(payload)
        conn.sendall(b"\r\n")
        self._push_sent = True


def _read_line(conn: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\r\n"):
        chunk = conn.recv(1)
        if not chunk:
            return ""
        data.extend(chunk)
    return data[:-2].decode("utf-8")


def _read_exact(conn: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            raise OSError("connection closed")
        data.extend(chunk)
    return bytes(data)


def test_nats_publish_sends_formal_linz_event_envelope():
    server = _FakeNatsServer()
    try:
        result = publish_linz_event(
            nats_url=server.url,
            subject="wsp.agent_b",
            event_type="wsp.chat.message.sent",
            payload={"message_id": "msg_1", "from": "agent_a", "to": "agent_b", "content": "hi"},
            event_id="evt_1",
            connect_timeout=1,
        )

        assert result["transport"] == "nats"
        assert result["world_event_id"] == "evt_1"
        assert result["acknowledged"] is True
        assert server.published
        subject, raw_payload = server.published[0]
        envelope = json.loads(raw_payload.decode("utf-8"))
        assert subject == "wsp.agent_b"
        assert envelope["event_type"] == "wsp.chat.message.sent"
        assert envelope["event_id"] == "evt_1"
        assert envelope["payload"]["content"] == "hi"
    finally:
        server.close()


def test_http_service_publish_uses_nats_transport(monkeypatch):
    server = _FakeNatsServer()
    try:
        monkeypatch.setattr(
            "agent.linz_world.api_client.load_linz_world_config",
            lambda config=None: LinzWorldConfig(nats_url=server.url),
        )

        result = HttpLinzWorldService("http://linz.test").publish_event(
            "token-ref",
            "wsp.agent_b",
            "wsp.chat.message.sent",
            {"message_id": "msg_1", "from": "agent_a", "to": "agent_b", "content": "hi"},
        )

        assert result["transport"] == "nats"
        assert json.loads(server.published[0][1].decode("utf-8"))["event_type"] == "wsp.chat.message.sent"
    finally:
        server.close()


def test_nats_publish_fails_closed_without_transport():
    with pytest.raises(NatsPublishError) as exc_info:
        publish_linz_event(
            nats_url="",
            subject="wsp.agent_b",
            event_type="wsp.chat.message.sent",
            payload={},
        )

    assert exc_info.value.code == "missing_transport"


def test_nats_listener_decodes_subscribed_events():
    ready = threading.Event()
    received = []
    server = _FakeNatsServer(
        push_subject="wsp.agent_b",
        push_envelope={
            "event_type": "wsp.chat.message.sent",
            "event_id": "evt_2",
            "timestamp": "2026-05-14T00:00:00Z",
            "payload": {"message_id": "msg_2", "from": "agent_a", "to": "agent_b", "content": "hello"},
        },
    )

    def _on_event(event):
        received.append(event)
        ready.set()

    listener = NatsEventListener(nats_url=server.url, subjects=["wsp.agent_b"], on_event=_on_event)
    try:
        listener.start()
        assert ready.wait(2)
        assert received[0]["event_id"] == "evt_2"
        assert received[0]["subject"] == "wsp.agent_b"
        assert received[0]["event_type"] == "wsp.chat.message.sent"
        assert received[0]["source"]["actor_id"] == "agent_a"
    finally:
        listener.stop()
        server.close()
