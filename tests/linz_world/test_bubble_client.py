from __future__ import annotations

import pytest

from agent.linz_world.api_client import LinzWorldServiceError, store_runtime_secret
from agent.linz_world.bubble_client import LinzBubbleClient


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.reason_phrase = "error"

    def json(self):
        return self._payload


def test_bubble_snapshot_uses_api_and_normalizes_go_fields(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "Bubble": {
                        "BubbleID": "bub_task_1",
                        "BubbleType": "task",
                        "Name": "Adapter task",
                        "LifecycleState": "active",
                        "Spec": {"large": "raw"},
                    },
                    "Children": [],
                    "Mounts": [
                        {
                            "MountID": "mount_1",
                            "TaskBubbleID": "bub_task_1",
                            "MountedBubbleID": "agent_1",
                            "SlotID": "slot.task.coder",
                            "MountState": "mounted_active",
                        }
                    ],
                    "BehaviorEvents": [
                        {
                            "EventID": "evt_1",
                            "BehaviorEventType": "bubble.produced",
                            "BubbleID": "bub_task_1",
                            "AfterState": "produced",
                        }
                    ],
                    "RelationEvents": [],
                    "Residues": [],
                    "MountedBubbles": [],
                    "MemoryBubbles": [],
                    "MemoryRecords": [],
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)

    snapshot = LinzBubbleClient("http://linz.test").get_snapshot("bub_task_1")

    assert calls[0][0] == "GET"
    assert calls[0][1] == "http://linz.test/api/v1/bubbles/bub_task_1/snapshot"
    assert snapshot.bubble.bubble_id == "bub_task_1"
    assert snapshot.bubble.bubble_type == "task"
    assert snapshot.mounts[0].mount_id == "mount_1"
    assert snapshot.behavior_events[0].behavior_event_type == "bubble.produced"
    assert snapshot.summary()["bubble"]["lifecycle_state"] == "active"


def test_bubble_create_task_posts_contract_with_bearer_token(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    token_ref = store_runtime_secret("event_token", "login-token")

    def fake_request(method, url, json=None, headers=None, **kwargs):
        calls.append((method, url, json, headers))
        return _Response(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "BubbleID": "bub_task_2",
                    "BubbleType": "task",
                    "ParentBubbleID": "bub_demand_1",
                    "LifecycleState": "produced",
                },
            }
        )

    monkeypatch.setattr("httpx.request", fake_request)

    bubble = LinzBubbleClient("http://linz.test/api/v1").create_task(
        parent_bubble_id="bub_demand_1",
        name="Implement adapter",
        goal="Connect Hermes to BPS",
        tech_lead_os_id="agent_1",
        token_ref=token_ref,
    )

    assert calls[0][0] == "POST"
    assert calls[0][1] == "http://linz.test/api/v1/bubbles/tasks"
    assert calls[0][2] == {
        "parent_bubble_id": "bub_demand_1",
        "name": "Implement adapter",
        "goal": "Connect Hermes to BPS",
        "tech_lead_os_id": "agent_1",
    }
    assert calls[0][3]["Authorization"] == "Bearer login-token"
    assert bubble.bubble_id == "bub_task_2"
    assert bubble.lifecycle_state == "produced"


def test_bubble_client_nonzero_envelope_raises(monkeypatch):
    monkeypatch.setattr(
        "httpx.request",
        lambda *args, **kwargs: _Response({"code": 400, "message": "bubble not found", "data": None}, status_code=404),
    )

    with pytest.raises(LinzWorldServiceError, match="bubble not found"):
        LinzBubbleClient("http://linz.test").get_snapshot("missing")
