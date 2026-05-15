# Research: World Event Dashboard

## Decision: Use a dedicated profile-scoped SQLite projection ledger

**Rationale**: Existing `SessionDB.messages` persists conversation turns, not the gateway `MessageEvent` envelope. Linz World currently persists a Linz-specific `EventDispatchRecord`, but other gateway platforms do not share that state shape. A dedicated ledger can store normalized inbound event metadata, raw payload, projection state, processing state, session reference, and `MessageEvent` summary without forcing unrelated transcript schema changes.

**Alternatives considered**:
- Extend `SessionDB.messages`: rejected because it mixes transcript replay concerns with gateway envelope diagnostics and does not naturally store raw inbound payload or consume/projection status.
- Reuse Linz `state.json`: rejected because it is Linz-specific and would not cover Slack/Telegram/webhook/other gateway events.
- In-memory queue only: rejected because the spec requires history to survive gateway/dashboard restarts.

## Decision: Capture records at the gateway `MessageEvent` boundary, with Linz/NATS raw-event preservation

**Rationale**: All platform adapters normalize into `gateway.platforms.base.MessageEvent` before `GatewayRunner._handle_message()`. Recording at this boundary gives one common integration point for all platforms. Linz World/NATS also has a pre-projection raw event in `dispatch_world_event()`, so implementation must preserve that raw NATS event and correlate it with the resulting `MessageEvent` record.

**Alternatives considered**:
- Patch every platform adapter independently: rejected because it increases blast radius and risks inconsistent event schemas.
- Record only after `run_conversation()`: rejected because unauthorized, failed, queued, pending, or pre-agent events would be invisible.
- Record only Linz/NATS: rejected by clarification; v1 must cover all gateway inbound events and filter Linz World/NATS as a category.

## Decision: Keep dashboard API read-only

**Rationale**: The feature is for inspection and troubleshooting. The spec explicitly excludes re-delivery, deletion, or mutation. Read-only endpoints preserve fail-closed external side-effect requirements and keep implementation scope focused.

**Alternatives considered**:
- Add replay/retry actions: rejected as out of v1 scope.
- Add deletion/prune controls: rejected because retention policy was not requested and could destroy troubleshooting evidence.

## Decision: Reuse LogsPage interaction patterns for refresh and density

**Rationale**: `web\src\pages\LogsPage.tsx` already implements the target dashboard idiom: compact segmented filters, manual refresh button, auto-refresh switch, status badges, high-density cards, and expandable raw data sections. Reusing these patterns keeps the new page visually consistent with the screenshot and avoids a second dashboard design language.

**Alternatives considered**:
- Build a custom dashboard layout from scratch: rejected because it risks visual drift.
- Implement as plugin page: rejected because the requirement asks for a dashboard page and the feature is native gateway behavior.

## Decision: Default to summaries and explicit payload expansion

**Rationale**: User clarification states the dashboard runs locally and does not need payload redaction, but default readability still matters. The list and collapsed detail view should show summaries and key identifiers; the full raw payload is available through explicit expansion in the detail panel.

**Alternatives considered**:
- Always show raw payload inline: rejected because large payloads would break layout and scanning.
- Never show full raw payload: rejected because the user explicitly chose full payload visibility.

## Decision: Use cursor/load-more pagination with default limit 100

**Rationale**: The spec sets default latest 100 and load more. Cursor pagination based on `(consumed_at, record_id)` avoids offset drift when auto-refresh inserts new records and supports indexed queries over a growing local ledger.

**Alternatives considered**:
- Offset-only pagination: rejected because auto-refresh can shift offsets during troubleshooting.
- Load all records: rejected because long-running gateway listeners can produce unbounded event history.

## Decision: Test backend behavior before visual polish

**Rationale**: The highest risks are data loss across restart, incorrect correlation, and missing Linz/NATS filtering. Store/API/gateway tests should lock those behaviors before front-end iteration. Frontend build/lint and visual verification then validate dashboard consistency.

**Alternatives considered**:
- Frontend-only mock page first: rejected because it would not prove the core troubleshooting value.
- End-to-end-only tests: rejected because failures would be slower to diagnose than focused store/API tests.
