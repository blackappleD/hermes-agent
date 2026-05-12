# Contract: Linz World Agent Tools

**Entrypoint**: `D:\workspace\hermes-agent\tools\linz_world_tools.py`
**Registry**: `D:\workspace\hermes-agent\tools\registry.py`
**Toolset exposure**: `D:\workspace\hermes-agent\toolsets.py`

All handlers return JSON strings, following Hermes tool conventions. Tool outputs must not contain raw tokens, private keys, or unrestricted world event payloads.

## Tool: `linz_status`

**Purpose**: Return current profile Linz World identity, registration, login, and authorization summary.

**Parameters**

```json
{}
```

**Result**

```json
{
  "success": true,
  "registration_state": "registered",
  "identity": {
    "os_id": "os_...",
    "soul_id": "soul_...",
    "os_name": "Hermes",
    "account_id": "acct_..."
  },
  "login_state": "logged_in",
  "authorization_state": "current",
  "next_action": null
}
```

## Tool: `linz_map`

**Purpose**: Refresh and return authorization map summary.

**Parameters**

```json
{}
```

**Result**

```json
{
  "success": true,
  "state": "current",
  "map_version": "opaque-version",
  "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"],
  "last_refresh_at": "2026-05-12T00:00:00Z"
}
```

## Tool: `linz_events_recent`

**Purpose**: Return recent world events using redacted summaries.

**Parameters**

```json
{
  "limit": 20,
  "status": "failed"
}
```

**Rules**

- `limit` must be bounded by implementation.
- `status` is optional and filters dispatch status.
- Result must not include unrestricted raw payload.

**Result**

```json
{
  "success": true,
  "events": [
    {
      "event_id": "evt_...",
      "subject": "wsp.chat.message.sent",
      "event_type": "message.sent",
      "payload_summary": "redacted summary",
      "dispatch_status": "handled",
      "attempt_count": 1,
      "requires_manual_handling": false
    }
  ]
}
```

## Tool: `linz_publish`

**Purpose**: Publish a formal Linz World event after governance checks.

**Parameters**

```json
{
  "subject": "wsp.chat.message.sent",
  "event_type": "message.sent",
  "payload": {}
}
```

**Rules**

- Must reject when registration/login is missing.
- Must refresh authorization map immediately before publish.
- Must reject if refresh fails.
- Must reject unknown subject/event_type.
- Must reject forbidden direct settlement transfer events.

**Result**

```json
{
  "success": true,
  "status": "published",
  "world_event_id": "evt_...",
  "receipt": {
    "recorded": true
  }
}
```

## Tool: `linz_compute`

**Purpose**: Invoke Linz World compute through the current login session.

**Parameters**

```json
{
  "task": "short task description",
  "input": {}
}
```

**Rules**

- Must not accept explicit API keys or tokens.
- Must refresh authorization map immediately before invocation.
- Result includes provider/model/source summary, not credentials.

## Tool: `linz_memory_sink`

**Purpose**: Write structured evidence or artifact reference to Soul Memory.

**Parameters**

```json
{
  "artifact_ref": "artifact-or-evidence-id",
  "sink_reason": "why this should be remembered",
  "summary": "redacted summary"
}
```

**Rules**

- `artifact_ref` and `sink_reason` are required.
- Free text without source reference is invalid.
- Must refresh authorization map immediately before write.

## Tool: `linz_relationship`

**Purpose**: Read relationship summaries or add ACTIVE relationship.

**Parameters**

```json
{
  "action": "read",
  "counterparty_id": "actor_..."
}
```

**Rules**

- `action=read` returns redacted summaries.
- Relationship mutation is an external side effect and requires real-time authorization map refresh.

## Common Error Result

```json
{
  "success": false,
  "error": {
    "code": "authorization_refresh_failed",
    "message": "Authorization map refresh failed; external side effect blocked.",
    "next_action": "Retry after Linz World authorization service is reachable."
  }
}
```
