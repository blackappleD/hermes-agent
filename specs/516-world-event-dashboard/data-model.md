# Data Model: World Event Dashboard

## Entity: GatewayInboundEventRecord

Represents one gateway inbound event that reached or attempted to reach the Hermes `MessageEvent` boundary.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `record_id` | string | yes | Stable ledger primary key. Recommended shape: deterministic hash of source category + platform + external event id, or generated id when no external id exists. |
| `event_id` | string | no | Platform/NATS event id when available. |
| `source_category` | enum | yes | Examples: `linz_world_nats`, `telegram`, `discord`, `slack`, `webhook`, `api_server`, `other`. Must support filtering `linz_world_nats`. |
| `platform` | string | no | `SessionSource.platform.value` when present. |
| `source` | object | no | Normalized source fields: `chat_id`, `chat_name`, `chat_type`, `thread_id`, `user_id`, `user_name`. |
| `subject` | string | no | NATS subject or equivalent platform subject/category. |
| `event_type` | string | no | Platform/NATS event type or message type. |
| `occurred_at` | string datetime | no | Event occurrence time if provided by source. |
| `consumed_at` | string datetime | yes | Time Hermes consumed/received the event. |
| `updated_at` | string datetime | yes | Last ledger update time. |
| `sequence_key` | string | no | Sequence/dedupe key where available. |
| `nats_sequence` | string | no | Required in detail for Linz World/NATS when available. |
| `payload_summary` | string | yes | Short summary safe for list display. |
| `raw_payload_json` | JSON string/object | no | Full raw payload for explicit detail expansion. |
| `raw_payload_available` | boolean | yes | False when source did not expose a serializable raw payload. |
| `raw_payload_error` | string | no | Serialization/availability note. |
| `consume_status` | enum | yes | `received`, `queued`, `processing`, `handled`, `failed`, `duplicate`, `ignored`, `unauthorized`. |
| `projection_status` | enum | yes | `pending`, `projected`, `failed`. |
| `dedupe_status` | enum | no | `unique`, `duplicate`, `merged`, `unknown`. |
| `duplicate_of_record_id` | string | no | Points at the original record when deduplicated. |
| `attempt_count` | integer | yes | Processing attempts; starts at `0` or `1` depending lifecycle point. |
| `last_error` | string | no | Most recent user-readable error summary. |

### Validation Rules

- `record_id`, `source_category`, `consumed_at`, `updated_at`, `consume_status`, and `projection_status` must always be present.
- `source_category = linz_world_nats` records must preserve `subject` and `event_id`; `nats_sequence` is preserved when available.
- Default list responses include summaries and identifiers, not full `raw_payload_json`.
- Full raw payload is returned only by detail endpoint or when explicitly requested by detail fetch.
- Records must be scoped to the active Hermes profile by storage path, not by a global shared database.

## Entity: HermesMessageEventProjection

Represents the normalized Hermes `MessageEvent` projection associated with a gateway inbound event.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `record_id` | string | yes | Foreign key to `GatewayInboundEventRecord`. |
| `message_event_id` | string | no | Usually `MessageEvent.message_id` or generated fallback. |
| `message_type` | string | yes | `text`, `photo`, `audio`, `voice`, `document`, `command`, etc. |
| `text_summary` | string | yes | Short summary of `MessageEvent.text`. |
| `source_snapshot` | object | yes | Snapshot of `MessageEvent.source` fields used for correlation. |
| `raw_message_summary` | string | no | Summary of `MessageEvent.raw_message` for list/detail collapsed view. |
| `media_count` | integer | yes | Number of media URLs on the message event. |
| `session_id` | string | no | Hermes session id used for processing. |
| `session_key` | string | no | Gateway session key where available. |
| `session_message_ref` | string | no | Optional reference to the persisted user transcript message if implementation can resolve it. |
| `projected_at` | string datetime | no | Time projection was recorded. |

### Validation Rules

- Projection row exists when `projection_status = projected`.
- `source_snapshot.platform` should match `GatewayInboundEventRecord.platform` when both are known.
- If `session_id` exists, dashboard may link or display it as a troubleshooting reference; absence does not make the event invalid.

## Entity: EventProcessingTransition

Tracks lifecycle transitions useful for diagnosing why a record is pending, failed, duplicate, or handled.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `transition_id` | string | yes | Stable id or autoincrement id. |
| `record_id` | string | yes | Parent event record. |
| `from_status` | string | no | Previous combined status. |
| `to_status` | string | yes | New combined status. |
| `at` | string datetime | yes | Transition time. |
| `reason` | string | no | User-readable reason. |
| `error` | string | no | Error summary when relevant. |
| `metadata` | object | no | Small structured details, not full payload. |

### State Transitions

```text
received -> projected -> processing -> handled
received -> projected -> queued -> processing -> handled
received -> projected -> failed
received -> projection_failed
received -> duplicate
received -> unauthorized
processing -> failed
failed -> queued -> processing
```

## Entity: EventListFilter

Represents dashboard query state.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `limit` | integer | yes | Defaults to 100; bounded by API. |
| `cursor` | string | no | Load-more cursor. |
| `source_category` | string | no | Includes `linz_world_nats`. |
| `consume_status` | string | no | Filter by lifecycle status. |
| `projection_status` | string | no | Filter by projection state. |
| `source` | string | no | Platform/source keyword. |
| `subject` | string | no | NATS/platform subject. |
| `event_type` | string | no | Event/message type. |
| `q` | string | no | Free-text search over event id, subject, type, message id, source summary. |
| `from` | string datetime | no | Start time. |
| `to` | string datetime | no | End time. |

## Relationships

- `GatewayInboundEventRecord` 1:0..1 `HermesMessageEventProjection`
- `GatewayInboundEventRecord` 1:N `EventProcessingTransition`
- `GatewayInboundEventRecord.duplicate_of_record_id` 0..1 -> `GatewayInboundEventRecord.record_id`
- `HermesMessageEventProjection.session_id` 0..1 -> `SessionDB.sessions.id`
