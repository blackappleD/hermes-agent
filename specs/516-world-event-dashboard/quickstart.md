# Quickstart: World Event Dashboard

## Prerequisites

- Active branch: `516-world-event-dashboard`
- Hermes Python environment available for pytest
- Web dependencies installed under `D:\workspace\hermes-agent\web`

## Backend Verification

Run focused backend tests after implementation:

```powershell
python -m pytest tests\gateway\test_event_projection_store.py tests\gateway\test_message_event_projection_ledger.py tests\hermes_cli\test_web_server_world_events.py tests\linz_world\test_gateway_adapter.py
```

If the local environment does not have `pytest-xdist` installed but the project
configuration still injects `-n auto`, use the same focused set with the
project addopts disabled:

```powershell
python -m pytest -o addopts="" tests\gateway\test_event_projection_store.py tests\gateway\test_message_event_projection_ledger.py tests\hermes_cli\test_web_server_world_events.py tests\linz_world\test_gateway_adapter.py
```

Expected coverage:

- profile-scoped ledger persists records across repository re-open/restart simulation
- duplicate event id/sequence handling records duplicate status without losing original
- Linz World/NATS records retain `source_category=linz_world_nats`, `subject`, `event_id`, `nats_sequence`, and full raw payload in detail
- dashboard list endpoint defaults to 100 records and supports source/category/status/text filters
- detail endpoint returns raw payload only in detail response and returns 404 for missing records

## Frontend Verification

Build and lint the dashboard:

```powershell
cd web
npm run build
npm run lint
```

Manual visual checks:

- open the dashboard and navigate to the new event projection page
- compare density, controls, nav placement, badges, borders, refresh button, and auto-refresh switch against the existing Logs/OS_RUNTIME page
- verify desktop wide layout and narrower viewport do not overlap labels, filters, detail payload, or action buttons
- verify the full raw payload is collapsed by default and scrolls/expands without breaking layout
- switch between `/events`, `/logs`, and `/chat` and confirm the persistent chat host is not remounted or covered by the event page
- use the auto-refresh switch for at least one 5-second interval and verify the latest refreshed timestamp updates without moving expanded payload content unexpectedly

Implementation verification notes:

- Focused backend tests passed with `python -m pytest -o addopts="" ...`.
- `npm run build` passed; Vite reported the existing large chunk warning.
- Full `npm run lint` currently reports pre-existing lint errors in unrelated dashboard files; targeted lint for `WorldEventsPage.tsx`, `App.tsx`, `api.ts`, and edited i18n files passed.

## Functional Smoke Scenario

1. Start or restart the Hermes gateway for the active profile.
2. Deliver at least one normal gateway inbound message through any configured platform or test adapter.
3. Deliver or simulate one Linz World/NATS event.
4. Open dashboard page `/events` or the implemented route.
5. Confirm the default list shows latest records, source category filtering can isolate `Linz World/NATS`, and detail view shows:
   - original inbound event identifiers
   - `MessageEvent` summary/reference
   - consume/projection status
   - full raw payload after explicit expansion
6. Restart the dashboard or gateway.
7. Reopen the page and confirm previously recorded events remain visible in the default latest 100 or via filters/load-more.

## Non-Goals For This Plan

- no replay/retry/delete actions from the dashboard
- no new external publishing or NATS side effects
- no optional plugin dependency
- no replacement of the embedded TUI/chat dashboard surface
