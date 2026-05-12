# Quickstart: Linz World 原生身份与世界接入

**Feature**: `001-native-linz-identity`
**Repo**: `D:\workspace\hermes-agent`

This quickstart describes expected verification once implementation tasks are generated and completed.

## 1. Environment

```powershell
cd D:\workspace\hermes-agent
.\.venv\Scripts\Activate.ps1
```

If `.venv` is not present, use the repository's existing `venv` or the shared Hermes venv described in AGENTS.md.

## 2. Configure Linz World

Set non-secret settings in the current Hermes profile config:

```yaml
linz_world:
  enabled: true
  auto_register_on_agent_create: true
  registration_failure_mode: fail_agent_create
  server_url: "https://linz-world.example"
  nats_url: ""
  nats:
    enabled: false
```

Place tokens or credentials only in the profile's secret/runtime store. Do not place raw tokens in prompt-visible config.

## 3. Identity Bootstrap Scenario

1. Start with a Hermes profile that has no `linz_world.original_spirit`.
2. Load or create an agent persona.
3. Expected: Hermes attempts registration.
4. If registration succeeds, `hermes linz status` shows `registered` with `os_id` and `soul_id`.
5. If registration fails, the persona load is blocked and status shows `pending` or `failed` with a diagnostic.

## 4. Scope Exclusion Scenario

1. List `hermes linz` native commands.
2. Expected: no legacy identity import, sync, or migration command is present.
3. Inspect implementation paths touched by this feature.
4. Expected: no `agent/linz_world/migration.py` or equivalent legacy identity sync path is implemented.
5. Expected: no old `~/.linz-world` identity file is read, written, migrated, or synchronized.

## 5. Authorization and Publish Scenario

1. Login with `hermes linz login`.
2. Run `hermes linz map`.
3. Attempt a valid publish.
4. Expected: publish refreshes authorization map immediately before external call.
5. Force map refresh failure.
6. Expected: publish, compute, memory sink, and relationship mutation are blocked.
7. Attempt forbidden settlement transfer publish.
8. Expected: request is rejected before external call.

## 6. World Event Ingest Scenario

1. Inject a valid `wsp.chat.message.sent` event through the Linz World gateway adapter or test fake transport.
2. Expected: event is persisted before ack.
3. Expected: Hermes creates at most one user-visible event and one agent turn.
4. Inject the same event 5 times.
5. Expected: duplicates are skipped.
6. Force internal processing failure.
7. Expected: automatic retry stops after 3 attempts, status becomes `failed`, and manual handling is visible.

## 7. Payload Privacy Scenario

1. Inject a world event containing sensitive payload fields.
2. Inspect prompt-visible context, ordinary tool output, and default CLI/UI event display.
3. Expected: only redacted summary and event reference are visible.
4. Verify restricted audit path stores the raw payload reference.
5. Expected: raw payload is not available through normal agent tools.

## 8. Suggested Test Commands

```powershell
python -m pytest tests\linz_world
python -m pytest tests\gateway\test_platform_registry.py tests\gateway\test_internal_event_bypass_pairing.py
python -m pytest tests\tools\test_registry.py tests\test_toolsets.py
python -m pytest tests\hermes_cli\test_config.py tests\hermes_cli\test_commands.py
```

Run broader regressions if implementation touches gateway runner, `run_agent.py`, or shared tool dispatch:

```powershell
python -m pytest tests\gateway
python -m pytest tests\run_agent\test_agent_loop.py tests\test_model_tools.py
```
