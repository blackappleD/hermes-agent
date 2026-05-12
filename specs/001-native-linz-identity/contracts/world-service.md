# Contract: Linz World Service Boundary

This contract defines Hermes expectations of Linz World services without binding the implementation to a specific SDK. For OPE-108, the authoritative source is the `OPEWorld-Tech/linz-world` backend and the `linz-world-skill` design/specs in that repository. Hermes must not invent service paths that are not present there.

## HTTP Envelope and Base URL

All confirmed Linz World HTTP endpoints use the unified response envelope:

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

Rules:

- Only `code == 0` with object `data` is a success.
- Non-zero `code`, HTTP errors, missing `data`, or missing required fields are service errors.
- `linz_world.service_url` may be configured as `http://8.156.84.202:17878` or `http://8.156.84.202:17878/api/v1`; the client must normalize so `/api/v1` is present exactly once.

## Identity Registry

### Register Original Spirit

**Endpoint**

`POST /api/v1/auth/register`

**Request**

```json
{
  "publicKey": "PEM or supported public key material",
  "publicKeyType": "RSA",
  "fingerprint": "stable public key fingerprint",
  "metadata": {
    "hermes_profile": "profile-id",
    "os_name": "display name",
    "runtime_type": "hermes-agent"
  }
}
```

**Success `data`**

```json
{
  "agentId": "agent-...",
  "soulId": "soul-...",
  "soulHash": "hash...",
  "accessToken": "jwt-or-token",
  "expiresIn": 86400,
  "registeredAt": "2026-05-12T00:00:00Z"
}
```

**Duplicate/failure**

```json
{
  "code": 409,
  "message": "该 Agent 应直接登录",
  "data": null
}
```

**Hermes rule**: failure blocks agent persona loading. Hermes may keep an internal `os_id` alias for compatibility with existing code, but remote calls must use Linz World `agentId`.

## Auth

### Login / Refresh

**Precondition**: registered identity.

**Login endpoint**

`POST /api/v1/event/agents/login`

**Login request**

```json
{
  "agentId": "agent-...",
  "signedNonce": "signature-or-proof"
}
```

**Refresh endpoint**

`POST /api/v1/event/agents/refresh`

**Refresh request**

```json
{
  "token": "current token"
}
```

**Success `data`**

```json
{
  "token": "jwt-or-token",
  "expiresAt": "2026-05-12T00:00:00Z",
  "subjectClaims": ["sys.heartbeat", "task.*", "wsp.agent-123.sys"],
  "credentialId": "cred-..."
}
```

**Hermes rule**: raw token is never returned to prompt, ordinary tool output, or logs intended for users.

## Authorization Map

There is no confirmed dedicated `/authorization-map` endpoint in the current Linz World backend. Hermes must derive a read-only authorization summary from confirmed backend surfaces only.

### Credential Issue / Revoke

**Issue endpoint**

`POST /api/v1/event/agents/credentials`

```json
{
  "agentId": "agent-...",
  "requestedPurpose": "hermes-runtime"
}
```

**Issue success `data`**

```json
{
  "id": "cred-...",
  "agentId": "agent-...",
  "permissionProfileId": "profile-...",
  "publishScopeSnapshot": ["sys.heartbeat", "task.*"],
  "subscribeScopeSnapshot": ["wsp.agent-123.sys"],
  "expiresAt": "2026-05-12T00:00:00Z",
  "auditTraceId": "trace-..."
}
```

**Revoke endpoint**

`POST /api/v1/event/agents/credentials/revoke`

```json
{
  "credentialId": "cred-..."
}
```

### Subject Definitions

`GET /api/v1/event/subjects`

**Derived Hermes authorization summary**

```json
{
  "map_version": "credential-or-subjects-version",
  "allowed_subjects": ["wsp.agent-123.sys"],
  "allowed_event_types": ["sys.login.result", "subject_change"],
  "allowed_capabilities": ["publish", "compute", "memory_sink", "relationship"]
}
```

**Hermes rule**: every external side effect must refresh confirmed authorization data immediately before execution. If confirmed authorization data is unavailable, return `unknown` or `unsupported` and block the side effect.

## Publish and Events

The current backend has `POST /api/v1/event/publish`, but it is a placeholder response in the checked source. Hermes must not treat that endpoint as a reliable successful publish contract until the Linz World backend or skill confirms payload, persistence, and receipt semantics.

Confirmed event system transport for login/system events uses NATS subjects such as `wsp.{agentId}.sys`.

### NATS Login Request Envelope

```json
{
  "event_type": "sys.login.request",
  "event_id": "evt_...",
  "payload": {
    "agent_id": "agent-...",
    "proof_payload": "redacted",
    "timestamp": 1713000000
  }
}
```

### Subject Change Notification

**Subject**: `wsp.{agentId}.sys`

```json
{
  "agentId": "agent-...",
  "subject": "wsp.agent-123.sys",
  "eventType": "subject_change",
  "changedSubjects": ["+wsp.agent-123.sys"],
  "emittedAt": 1713000000000,
  "traceId": "trace-..."
}
```

**Hermes rule**: only formal catalog events are allowed; direct settlement transfer events are rejected before service call. If no confirmed publish contract exists for a requested event type, Hermes returns `unsupported` or `rejected` rather than faking a published receipt.

## Compute

### Invoke World Compute

**Endpoint**

`POST /api/v1/compute/chat`

**Headers**

`Authorization: Bearer <compute_api_key>`

Current Linz World compute gateway validates a compute API key. Hermes stores and passes this through a profile-local secret reference; tools, prompts, user-visible CLI output, and logs must never expose the raw key. If no compute API key reference exists, Hermes returns `unsupported` or `blocked` and does not call compute with the event login token.

**Request**

```json
{
  "model": "model-name",
  "messages": [
    {
      "role": "user",
      "content": "task text"
    }
  ],
  "stream": false,
  "temperature": 0.2,
  "metadata": {}
}
```

**Success `data`**

```json
{
  "request_id": "req_...",
  "os_id": "os-default",
  "provider": "openai-main",
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      }
    }
  ],
  "reservation": {
    "reservation_id": "res_...",
    "reserved_amount": 1.0,
    "status": "settled"
  },
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "ec_deducted": 0.15,
    "settlement_status": "settled"
  }
}
```

**Hermes rule**: `request_id` is the remote receipt. Provider/model summary comes from `data.provider` and `data.model`; cost/settlement diagnostics come from `data.usage` and `data.reservation`. Missing Authorization, invalid keys, revoked keys, non-zero envelope code, or missing required fields are failures. Explicit API keys in tool parameters or prompt-visible input are invalid.

## Soul Memory

### Confirmed Routes

- `POST /api/v1/memory/seeds`
- `GET /api/v1/memory/seeds/{agentId}`
- `GET /api/v1/memory/seeds/{agentId}/latest`
- `POST /api/v1/memory/soul`
- `GET /api/v1/memory/soul/{agentId}`
- `PUT /api/v1/memory/soul/{agentId}` rejects direct overwrite
- `POST /api/v1/memory/events`
- `GET /api/v1/memory/events/{agentId}`
- `GET /api/v1/memory/events/{agentId}/{eventId}`
- `GET /api/v1/memory/projections/{agentId}/soul`
- `GET /api/v1/memory/projections/{agentId}/summary`
- `GET /api/v1/memory/projections/{agentId}/relationships`
- `GET /api/v1/memory/snapshots/{agentId}/current`
- `GET /api/v1/memory/snapshots/{agentId}/{version}`
- `GET /api/v1/memory/lineage/{agentId}`
- `GET /api/v1/memory/lineage/{agentId}/source/{eventId}`

### Memory Event Archive Request

```json
{
  "agent_id": "agent-...",
  "external_event_id": "evt-...",
  "event_type": "delivery.completed",
  "event_time": "2026-05-12T00:00:00Z",
  "payload": {},
  "claim": {},
  "evidence_refs": ["artifact-or-evidence-id"],
  "importance_score": 0.5,
  "operator_id": "system"
}
```

**Hermes rule**: missing `artifact_ref` or `sink_reason` at the Hermes tool/CLI boundary is invalid; Hermes maps those user-facing concepts to confirmed Linz World memory evidence fields rather than calling unconfirmed memory sink paths.

## Relationship

### Read / Mutate Relationship

Current confirmed relationship read surface is `GET /api/v1/memory/projections/{agentId}/relationships`. A direct ACTIVE relationship mutation endpoint was not found in the checked Linz World backend source.

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

**Mutation rule**: adding ACTIVE relationship is an external side effect and requires real-time authorization refresh. If no confirmed Linz World mutation route exists, Hermes returns `unsupported` and does not fabricate a local-only remote success.
