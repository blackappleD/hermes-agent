# Contract: Linz World Configuration

**File scope**: current Hermes profile config and profile-aware runtime state.
**Authoritative config loader**: `D:\workspace\hermes-agent\hermes_cli\config.py`

## `config.yaml` Shape

```yaml
linz_world:
  enabled: true
  auto_register_on_agent_create: true
  registration_failure_mode: fail_agent_create
  registration_state: pending
  server_url: ""
  nats_url: ""
  original_spirit:
    os_id: ""
    soul_id: ""
    os_name: ""
    account_id: ""
  auth:
    auto_login: false
    token_ref: ""
    last_login_at: ""
  online_by_default: false
  require_map_before_publish: true
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
- `registration_failure_mode` for this feature is `fail_agent_create`.
- `auto_register_on_agent_create` must be true for this feature.
- `online_by_default`, automatic response, and automatic publish remain false unless explicitly enabled in a later feature.
- Adding this section does not require a `_config_version` bump because no existing Hermes config key is renamed or migrated.

## Validation

- `registered` requires non-empty `os_id` and `soul_id`.
- External side effects require current login session and real-time authorization map refresh.
- `max_auto_retry_attempts` must be `3` for this feature.
- `prompt_payload_mode` must not expose unrestricted payload.
