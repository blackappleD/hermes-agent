# Contract: Linz World Configuration

**File scope**: current Hermes profile config and profile-aware runtime state.
**Authoritative config loader**: `D:\workspace\hermes-agent\hermes_cli\config.py`

## `config.yaml` Shape

```yaml
linz_world:
  enabled: true
  identity_required_on_agent_load: true
  registration_state: pending
  service_url: ""
  nats_url: ""
  os_name: "Hermes"
  original_spirit:
    agent_id: ""
    os_id: ""
    soul_id: ""
    soul_hash: ""
    os_name: ""
    account_id: ""
  auth:
    auto_login: false
    token_ref: ""
    last_login_at: ""
  auto_listen: false
  auto_respond: false
  auto_publish: false
  self_drive: false
  authorization:
    state: unknown
    map_version: ""
    last_refresh_at: ""
  nats:
    enabled: false
    stream: ""
    consumer: ""
    cursor_ref: ""
    ack_after_persist: true
  event_handling:
    mode: passive
    max_auto_retry_attempts: 3
  privacy:
    retain_restricted_payload: true
    prompt_payload_mode: redacted_summary
```

## Rules

- Non-secret identity/config fields live in `config.yaml`.
- Raw tokens, private keys, restricted payload blobs, cursors, dispatch states, and receipts are runtime state and must not be written into prompt-visible config.
- `linz_compute` uses the current successful Linz World login token reference as its bearer credential.
- `identity_required_on_agent_load` must default to true for this feature.
- `service_url` is the canonical and only user-visible service address key.
- `service_url` accepts either origin root, for example `http://8.156.84.202:17878`, or API root, for example `http://8.156.84.202:17878/api/v1`; HTTP calls must normalize `/api/v1` exactly once.
- `auto_listen`, `auto_respond`, `auto_publish`, and `self_drive` remain false unless explicitly enabled in a later feature.
- Adding this section does not require a `_config_version` bump because no existing Hermes config key is renamed or migrated.

## Validation

- `registered` requires non-empty Linz World `agent_id`/`agentId` and `soul_id`/`soulId`; internal `os_id` aliases must not change the remote field names.
- External side effects require current login session and real-time authorization map refresh.
- `max_auto_retry_attempts` must be `3` for this feature.
- `prompt_payload_mode` must not expose unrestricted payload.
