# Contract: Linz World Service Boundary

This contract defines Hermes expectations of Linz World services without binding the implementation to a specific transport or SDK.

## Identity Registry

### Register Original Spirit

**Input**

```json
{
  "hermes_profile": "profile-id",
  "os_name": "display name"
}
```

**Success**

```json
{
  "os_id": "os_...",
  "soul_id": "soul_...",
  "os_name": "display name",
  "account_id": "acct_..."
}
```

**Failure**

```json
{
  "error": {
    "code": "service_unavailable",
    "message": "redacted diagnostic"
  }
}
```

**Hermes rule**: failure blocks agent persona loading.

## Auth

### Login / Refresh

**Precondition**: registered identity.

**Success**

```json
{
  "token_ref": "profile-local-secret-reference",
  "expires_at": "2026-05-12T00:00:00Z"
}
```

**Hermes rule**: raw token is never returned to prompt, ordinary tool output, or logs intended for users.

## Authorization Map

### Refresh Map

**Success**

```json
{
  "map_version": "opaque-version",
  "allowed_subjects": ["wsp.chat.message.sent"],
  "allowed_event_types": ["message.sent"],
  "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"]
}
```

**Hermes rule**: every external side effect must call refresh immediately before execution. Failure blocks the side effect.

## Publish

### Publish Event

**Input**

```json
{
  "subject": "wsp.chat.message.sent",
  "event_type": "message.sent",
  "payload": {}
}
```

**Success**

```json
{
  "world_event_id": "evt_...",
  "published_at": "2026-05-12T00:00:00Z"
}
```

**Hermes rule**: only formal catalog events are allowed; direct settlement transfer events are rejected before service call.

## Compute

### Invoke World Compute

**Input**

```json
{
  "task": "short task description",
  "input": {}
}
```

**Success**

```json
{
  "result": {},
  "provider_summary": "provider/model/source summary",
  "receipt": "opaque receipt"
}
```

**Hermes rule**: invocation uses login session token reference only; explicit API key input is invalid.

## Soul Memory

### Write Memory

**Input**

```json
{
  "artifact_ref": "artifact-or-evidence-id",
  "sink_reason": "why this should be remembered",
  "summary": "redacted summary"
}
```

**Hermes rule**: missing `artifact_ref` or `sink_reason` is invalid.

## Relationship

### Read / Mutate Relationship

**Read Success**

```json
{
  "relationships": [
    {
      "relationship_id": "rel_...",
      "counterparty_id": "actor_...",
      "state": "ACTIVE",
      "summary": "redacted summary"
    }
  ]
}
```

**Mutation rule**: adding ACTIVE relationship is an external side effect and requires real-time authorization refresh.
