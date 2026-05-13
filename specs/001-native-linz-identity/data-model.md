# Data Model: Linz World 原生身份与世界接入

**Feature**: `001-native-linz-identity`
**Created**: 2026-05-12

## Entity: Hermes Profile

Represents the current Hermes profile and its profile-aware runtime boundary.

**Fields**

- `profile_id`: stable identifier for the active Hermes profile.
- `hermes_home`: profile-aware state root resolved by Hermes.
- `linz_world`: Linz World configuration and identity summary.
- `created_at`, `updated_at`: profile metadata when available.

**Relationships**

- Owns exactly one `World Identity` for this feature.
- Owns many `Event Dispatch Record`, `Publish Receipt`, and runtime audit records.

**Validation Rules**

- All Linz World state must be scoped to the active profile.
- Runtime must not read, import, sync, overwrite, or migrate old linz-world-skill identity state.

## Entity: World Identity

Represents the Hermes profile's Linz World original spirit.

**Fields**

- `hermes_profile`: profile id or display name.
- `agent_id`: canonical Linz World `agentId` returned by `POST /api/v1/auth/register`.
- `os_id`: local compatibility alias for `agent_id` where existing Hermes code still names the actor as OS; this must not be sent to Linz World as a remote field name.
- `os_name`: user-facing original spirit name.
- `soul_id`: Linz World soul id.
- `soul_hash`: Linz World `soulHash` returned by registration.
- `account_id`: owning or linked account id.
- `token_ref`: profile-local secret/runtime reference for `accessToken` or login `token`; raw token is never prompt-visible.
- `token_expires_at`: remote token expiration timestamp or derived expiry.
- `authorization_state`: `unknown | current | failed`.
- `memory_summary_available`: boolean.
- `registration_state`: reference to `Registration State`.
- `created_at`, `last_verified_at`: timestamps.

**Relationships**

- Belongs to one `Hermes Profile`.
- Used by `Authorization Map`, `Publish Request`, `World Compute Request`, `Soul Memory Entry`, and `Relationship Record`.

**Validation Rules**

- `agent_id` and `soul_id` are required before agent persona may load.
- The same Hermes profile must not register more than one active original spirit.
- Missing identity fields force `Registration State = pending | failed` and block persona loading.
- Registration response parsing must use the Linz World envelope `data.agentId`, `data.soulId`, `data.soulHash`, `data.accessToken`, `data.expiresIn`, and `data.registeredAt`.

## Entity: Registration State

Tracks identity bootstrap lifecycle.

**Fields**

- `state`: `pending | registered | failed`.
- `last_attempt_at`: timestamp.
- `last_success_at`: timestamp, optional.
- `last_error_code`: machine-readable failure code, optional.
- `last_error_message`: human-readable diagnostic, redacted.
- `next_action`: user-actionable next step.

**State Transitions**

- `pending -> registered`: registry succeeds and identity fields are persisted.
- `pending -> failed`: registry fails with a terminal or diagnosable error.
- `failed -> pending`: user retries or config changes.
- `failed -> registered`: retry succeeds.
- `registered -> failed`: identity verification later proves invalid.

**Validation Rules**

- `registered` requires complete `World Identity`.
- `pending` or `failed` blocks agent persona loading.

## Entity: Authorization Map

Read-only governance input refreshed before every external side effect.

**Fields**

- `state`: `unknown | current | refresh_failed`.
- `map_version`: opaque version or timestamp.
- `last_refresh_at`: timestamp.
- `allowed_subjects`: list of allowed subject patterns.
- `allowed_event_types`: list of allowed event types.
- `allowed_capabilities`: list including `publish`, `compute`, `memory_sink`, `relationship`.
- `subject_claims`: claims returned by `POST /api/v1/event/agents/login` or refresh.
- `publish_scope_snapshot`: scope returned by `POST /api/v1/event/agents/credentials`.
- `subscribe_scope_snapshot`: scope returned by `POST /api/v1/event/agents/credentials`.
- `credential_id`: Linz World credential id, if issued.
- `refresh_error`: redacted diagnostic, optional.

**Relationships**

- Belongs to one `World Identity`.
- Gates `Publish Request`, `World Compute Request`, `Soul Memory Entry`, and relationship mutations.

**Validation Rules**

- Every external side effect must trigger a real-time refresh.
- Refresh failure or `unknown` state blocks the side effect.
- Cached map may be displayed for read-only status but must not authorize side effects.
- The map must be derived from confirmed Linz World login/credential/subject routes; unconfirmed map endpoints must not be called.

## Entity: World Event

Normalized Linz World event received by Hermes.

**Fields**

- `event_id`: unique Linz World event id.
- `subject`: formal world subject.
- `event_type`: formal event type.
- `source_actor`: sender id or relationship id, redacted as needed.
- `room_or_context_id`: room, relationship, task/order, or subject-derived context.
- `payload_summary`: redacted summary for prompt/tool/default UI.
- `restricted_payload_ref`: reference to restricted audit payload.
- `raw_reference`: source stream/sequence/reference.
- `received_at`: timestamp.

**Relationships**

- Has one `Event Dispatch Record`.
- May create one Hermes `MessageEvent`.
- May be referenced by `Governance Result` and later evidence packages.

**Validation Rules**

- `event_id`, `subject`, `event_type`, and structured payload are required.
- Unknown subject/event_type or legacy protocol names are rejected or recorded as non-executable.
- Prompt and ordinary outputs must use `payload_summary`, never unrestricted raw payload.

## Entity: Event Dispatch Record

Reliable processing state for a world event.

**Fields**

- `event_id`: linked world event id.
- `nats_sequence`: stream sequence when available.
- `stream`: stream name, optional.
- `consumer`: consumer name, optional.
- `cursor`: cursor/reference after persistence.
- `dispatch_status`: `persisted | queued | processing | handled | failed | skipped`.
- `attempt_count`: integer, max automatic attempts = 3.
- `requires_manual_handling`: boolean.
- `last_error`: redacted diagnostic, optional.
- `last_dispatched_at`: timestamp, optional.

**State Transitions**

- `persisted -> queued -> processing -> handled`.
- `processing -> failed` after attempt 3 or terminal error.
- `persisted | queued -> skipped` for duplicate or non-executable events.
- `failed -> queued` only by explicit manual retry.

**Validation Rules**

- Duplicate `event_id` or duplicate stream sequence must not create duplicate user-visible events.
- External ack occurs after reliable persistence, not after LLM completion.

## Entity: Publish Request

A structured request to publish a Linz World event.

**Fields**

- `request_id`: local unique id.
- `actor_agent_id`: canonical Linz World `agentId` attempting publish.
- `transport`: `nats`.
- `subject`: formal subject.
- `event_type`: formal event type.
- `event_id`: required world event id; generated if caller omits one.
- `payload`: structured object.
- `payload_summary`: redacted summary.
- `authorization_map_version`: version used for decision.
- `governance_result_id`: linked decision.
- `trace_id`: optional cross-system trace id.
- `requested_at`: timestamp.

**Relationships**

- Requires `World Identity`, current `Authorization Map`, and `Governance Result`.
- Produces zero or one `Publish Receipt`.

**Validation Rules**

- Actor must be registered and logged in.
- Authorization map must refresh successfully immediately before publish.
- Subject/event_type must be in the formal catalog.
- Payload must be a structured object.
- NATS transport and NATS credential/authorization material must be available; HTTP `/api/v1/event/publish` is not a fallback.
- Direct settlement transfer events are forbidden for agent direct publish.

## Entity: Publish Receipt

Auditable outcome of a publish request.

**Fields**

- `request_id`: linked publish request.
- `status`: `published | rejected | failed | uncertain`.
- `world_event_id`: remote event id, optional.
- `transport`: `nats`.
- `subject`: published subject, optional.
- `nats_sequence`: NATS stream/JetStream sequence if available, optional.
- `acknowledged`: whether the transport confirmed publish.
- `failure_reason`: redacted diagnostic, optional.
- `receipt_received_at`: timestamp, optional.
- `governance_result_id`: linked decision.

**Validation Rules**

- Successful NATS publish without local receipt persistence must be surfaced as `uncertain`.
- Failures must preserve subject/event_type summary and reason.

## Entity: World Compute Request

World compute invocation through the Linz World Compute Gateway using a profile-local compute API key secret reference.

**Fields**

- `request_id`: local unique id.
- `actor_agent_id`: canonical Linz World `agentId` invoking compute.
- `compute_api_key_ref`: profile-local secret reference; raw key is never stored in prompt-visible config.
- `input_summary`: redacted prompt/request summary.
- `provider_summary`: provider/model or equivalent source summary.
- `remote_request_id`: `data.request_id` returned by Linz World; primary remote receipt.
- `remote_os_id`: `data.os_id` returned by Linz World for billing/governance correlation.
- `reservation_summary`: redacted `data.reservation` summary.
- `usage_summary`: redacted `data.usage` summary.
- `choices_summary`: redacted assistant choices summary.
- `authorization_map_version`: version used for decision.
- `receipt`: remote or local diagnostic receipt.
- `status`: `succeeded | blocked | rejected | failed`.
- `created_at`, `completed_at`: timestamps.

**Validation Rules**

- Must use a configured compute API key secret reference for `Authorization: Bearer <compute_api_key>`; login tokens are not valid compute credentials unless Linz World later adds an explicit exchange/proxy contract.
- Raw API keys in tool parameters, prompt-visible config, ordinary CLI output, or logs are invalid.
- Missing compute API key reference blocks the external side effect with a diagnostic.
- Real-time authorization refresh is required before invocation.
- Result must parse current Linz World response fields: `request_id`, `os_id`, `provider`, `model`, `choices`, `reservation`, and `usage`.
- Result must not expose tokens, API keys, or credentials.

## Entity: Soul Memory Entry

Structured memory write to Linz World side memory.

**Fields**

- `entry_id`: local id.
- `actor_agent_id`: canonical Linz World `agentId` writing memory.
- `artifact_ref`: delivery/evidence/artifact reference.
- `sink_reason`: why this memory should be written.
- `summary`: redacted content summary.
- `authorization_map_version`: version used for decision.
- `status`: `written | rejected | failed`.
- `created_at`: timestamp.

**Validation Rules**

- Must include `artifact_ref` or equivalent delivery reference.
- Must include `sink_reason`.
- Real-time authorization refresh is required.
- Free text without evidence reference is invalid.

## Entity: Relationship Record

Relationship read or ACTIVE relationship mutation.

**Fields**

- `relationship_id`: world relationship id.
- `actor_agent_id`: current canonical Linz World `agentId`.
- `counterparty_id`: related actor.
- `state`: e.g. `ACTIVE`.
- `summary`: redacted relationship summary.
- `authorization_map_version`: version used for mutation, optional for read.
- `updated_at`: timestamp.

**Validation Rules**

- Reads can display redacted summaries.
- ACTIVE relationship mutation is an external side effect and requires real-time authorization refresh.

## Entity: Governance Result

Decision record for externally meaningful actions.

**Fields**

- `decision_id`: local unique id.
- `actor_agent_id`: canonical Linz World `agentId`.
- `action_family`: `publish | compute | memory_sink | relationship | event_ingest`.
- `decision`: `allow | reject | require_manual | skipped`.
- `reason`: human-readable explanation.
- `authorization_map_version`: version used, when applicable.
- `created_at`: timestamp.

**Validation Rules**

- External side effects cannot proceed without `decision = allow`.
- Rejections must preserve a redacted summary of the attempted subject/event_type or capability.
