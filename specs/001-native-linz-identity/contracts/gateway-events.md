# Contract: Linz World Gateway Events

**Gateway surface**: `D:\workspace\hermes-agent\gateway\platform_registry.py`
**Message type**: `D:\workspace\hermes-agent\gateway\platforms\base.py::MessageEvent`

## Platform Identity

- Platform name: `linz_world`
- Source chat id derivation order:
  1. world room id
  2. relationship id
  3. task/order id
  4. subject-derived fallback
- `message_id`: Linz World `event_id`
- `raw_message`: restricted in-memory/source object allowed internally; prompt/default display receives redacted summary only
- `internal`: true only for system-generated, already authorized synthetic events; ordinary world user messages are not internal

## Accepted World Event Input

```json
{
  "event_id": "evt_...",
  "subject": "wsp.chat.message.sent",
  "event_type": "message.sent",
  "payload": {},
  "source": {
    "actor_id": "actor_...",
    "room_id": "room_..."
  },
  "sequence": {
    "stream": "world-events",
    "consumer": "hermes-profile",
    "nats_sequence": 123
  },
  "occurred_at": "2026-05-12T00:00:00Z"
}
```

## Event Projection

| World subject/event family | Hermes event category | Agent turn behavior |
|---|---|---|
| `wsp.chat.message.sent` | user/world message | May create `MessageEvent` with redacted text |
| `wsp.mrk.requirement.published` | opportunity signal | Persist and expose as event summary |
| `wsp.task.*` | task status signal | Persist and expose as event summary |
| `wsp.mrk.order.*` | collaboration/order signal | Persist and expose as event summary |
| `wsp.mrk.settlement.*`, `rent.*` | account/governance signal | Persist; no automatic external action |

## Dispatch State Machine

```text
persisted -> queued -> processing -> handled
persisted -> skipped
queued -> skipped
processing -> failed
failed -> queued   # manual retry only
```

## Reliability Rules

- Persist event and dispatch record before external ack.
- Duplicate `event_id` or duplicate stream sequence must not create another user-visible event.
- Agent processing failure increments `attempt_count`.
- Automatic retries stop after attempt 3.
- After attempt 3 failure, set `dispatch_status=failed` and `requires_manual_handling=true`.
- External ack is not delayed until LLM completion.

## Redaction Rules

- `MessageEvent.text` uses redacted summary.
- Prompt context uses redacted summary and event reference.
- Ordinary tool output uses redacted summary.
- Restricted raw payload is accessible only through explicit audit path not defined as a normal agent tool in this feature.
