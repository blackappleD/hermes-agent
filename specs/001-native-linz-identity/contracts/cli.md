# Contract: Hermes Linz CLI

**Entrypoint**: `hermes linz <command>`
**Registry surface**: `D:\workspace\hermes-agent\hermes_cli\commands.py` and `D:\workspace\hermes-agent\hermes_cli\linz.py`

All commands return a human-readable result by default. JSON output may be added using existing Hermes command conventions if the surrounding CLI supports it.

## Commands

### `hermes linz status`

Shows current profile Linz World identity and registration status.

**Success includes**

- registration state: `registered | pending | failed`
- canonical Linz World `agent_id`, compatibility `os_id`, `soul_id`, `soul_hash`, `os_name`, `account_id` when available
- login state summary
- authorization state summary
- next action if blocked

**Failure**

- Missing or failed registration must be explicit.
- Raw tokens and restricted payloads are never printed.

### `hermes linz login`

Starts or refreshes a Linz World login session for the current profile identity.

**Preconditions**

- Registration state is `registered`.

**Failure**

- If registration is missing/failed, return a fail-closed diagnostic.
- Token values are not printed.

### `hermes linz logout`

Invalidates or removes current profile login session reference.

**Success includes**

- logout status
- updated login state

### `hermes linz map`

Refreshes and displays the authorization map summary.

**Success includes**

- authorization state
- map version
- allowed capabilities summary
- last refresh timestamp

**Failure**

- Refresh errors are shown as diagnostics.
- Cached map may be displayed as stale read-only information, but cannot authorize side effects.

### `hermes linz events`

Shows recent world events and dispatch states for the current profile.

**Success includes**

- event id
- subject/event_type
- redacted payload summary
- dispatch status
- attempt count
- manual handling flag

**Failure**

- Restricted raw payload is not displayed by default.

### `hermes linz publish`

Publishes a formal Linz World event from a structured request.

**Preconditions**

- Registered identity.
- Logged-in session.
- Real-time authorization map refresh succeeds.
- subject/event_type is formal and authorized.
- payload is a structured object.
- event is not a forbidden direct settlement transfer.

**Outcomes**

- `published`: shows world event id and receipt summary.
- `rejected`: shows governance reason.
- `failed`: shows diagnostic.
- `uncertain`: remote publish may have succeeded but local receipt persistence failed.
