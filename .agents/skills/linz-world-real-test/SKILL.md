---
name: linz-world-real-test
description: Run and monitor the real WSL Linz World MRK/Bubble integration flow for hermes-agent. Use when the user asks to execute, rerun, debug, or report the real Linz World/Bubble/MRK workflow in WSL, especially with /root/.hermes, localhost:8080, two Hermes profiles, and reports under experiment/results. Also use for directed MRK requirement delivery checks.
---

# Linz World Real Test

## Ground Rules

This skill is for the real workflow, not a fake smoke pass.

- Run from Windows repo `D:\workspace\hermes-agent`; WSL path is `/mnt/d/workspace/hermes-agent`.
- Use WSL root and `HERMES_HOME=/root/.hermes`.
- Use the local Linz World backend at `http://localhost:8080` unless the user says otherwise.
- Store all reports under `D:\workspace\hermes-agent\experiment\results` (`/mnt/d/workspace/hermes-agent/experiment/results` in WSL).
- Use two different profiles and two different Linz World identities:
  - publisher: usually `default` / `pipi`
  - receiver: usually `bubble-mrk-receiver-bubble-mrk-20260519-091525`
- Do not manually publish derived WSP events such as `wsp.mrk.requirement.published` or broadcast events. Publish the source MRK event and let Linz World dispatch derived notifications.
- Do not claim success unless the report or evidence shows the real gateway/LLM/tool flow completed. A real failed run is still valuable evidence.

If Linz World business behavior is unclear, inspect `D:\workspace\linz-world` first. For MRK/Bubble behavior, search:

```powershell
rg -n "ProcessPublished|ProcessOrderAccepted|ProcessHandoverDelivered|target_os_id|BridgeMRK" D:\workspace\linz-world\backend\internal -S
```

## Preflight

Check that no stale real test process is running:

```powershell
wsl -u root -- bash -lc 'ps -eo pid,ppid,etime,cmd | grep -E "linz_bubble_mrk_flow_test|real-bubble-mrk|gateway run --accept-hooks" | grep -v grep || true'
```

Check the two profile identities:

```powershell
wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
import json
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.status import status_summary
print(json.dumps(status_summary(LinzStateRepository()).get("identity"), ensure_ascii=False, indent=2))
PY'

wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes/profiles/bubble-mrk-receiver-bubble-mrk-20260519-091525 bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
import json
from agent.linz_world.event_state import LinzStateRepository
from agent.linz_world.status import status_summary
print(json.dumps(status_summary(LinzStateRepository()).get("identity"), ensure_ascii=False, indent=2))
PY'
```

Check config points to localhost and Bubble mutations are enabled:

```powershell
wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
from agent.linz_world.config import load_linz_world_config
cfg = load_linz_world_config()
print(cfg.enabled, cfg.service_url, cfg.bubble.enabled, cfg.bubble.allow_mutations, cfg.bubble.read_only)
PY'
```

Expected backend/config shape:

- `cfg.enabled == True`
- `cfg.service_url == "http://localhost:8080"`
- `cfg.bubble.enabled == True`
- `cfg.bubble.allow_mutations == True`
- `cfg.bubble.read_only == False`

## Run Real Flow

Use the existing script in `scripts/linz-world`. Prefer a synchronous run when the user wants only the final report:

```powershell
$runId = "real-bubble-mrk-" + (Get-Date -Format "yyyyMMdd-HHmmss")
wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes bash -lc "cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python scripts/linz-world/linz_bubble_mrk_flow_test.py real --publisher-profile default --receiver-profile bubble-mrk-receiver-bubble-mrk-20260519-091525 --run-id $runId --output-root /mnt/d/workspace/hermes-agent/experiment/results --hermes-home /root/.hermes --confirm-mutations --start-missing-gateways --timeout-seconds 1200 --gateway-event-timeout 300 --agent-timeout-seconds 600 --poll-interval 10"
```

If the command is launched in the background, save stdout/stderr and monitor until `REPORT.md` appears. Do not end the turn while a needed test process is still running.

Monitor:

```powershell
wsl -u root -- bash -lc 'ps -eo pid,ppid,etime,pcpu,cmd | grep -E "real-bubble-mrk|linz_bubble_mrk_flow_test|gateway run" | grep -v grep || true'

Get-ChildItem experiment\results -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name,FullName,LastWriteTime
```

When complete, read:

```powershell
Get-Content experiment\results\<run-id>\REPORT.md -Raw
```

## Directed Requirement Check

Directed MRK demand is sent by publishing the source requirement event with `target_os_id`:

- subject: `mrk.requirement.published`
- event_type: `mrk.requirement.published`
- payload includes `target_os_id` and optional `target_os_name`

The backend should persist the requirement, create a DemandBubble, and dispatch:

- subject: `wsp.{target_os_id}`
- event_type: `wsp.mrk.requirement.published`

Do not directly publish that WSP event yourself.

Minimal directed check:

```powershell
$runId = "directed-mrk-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$outDir = "D:\workspace\hermes-agent\experiment\results\$runId"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes RUN_ID=$runId bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
import json, os
from tools.linz_world_tools import linz_publish

run_id = os.environ["RUN_ID"]
payload = {
    "requirement_id": f"REQ-{run_id}",
    "publisher_os_id": "3e0a3d1e-5f54-4067-b0de-3bf1091d7a07",
    "publisher_os_name": "pipi",
    "target_os_id": "78867306-5f5d-4cd5-b7de-d085c562b2d9",
    "target_os_name": "bubble-mrk-receiver-bubble-mrk-20260519-091525",
    "title": f"Develop JSONL event summary script {run_id}",
    "description": "Develop linz_event_summary.py. Support --input and optional --output. Count total_lines, valid_events, invalid_lines, by_event_type, by_subject. Deliver source and usage example.",
    "budget_amount": "100",
    "budget_unit": "EC",
    "deadline_at": "2026-06-01T18:00:00+08:00",
}
print(linz_publish({"subject": "mrk.requirement.published", "event_type": "mrk.requirement.published", "payload": payload}))
PY'
```

Check delivery:

```powershell
wsl -u root -- env HOME=/root RUN_ID=<run-id> bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
from pathlib import Path
from gateway.event_projection_store import EventProjectionStore
import json, os

run = os.environ["RUN_ID"]
profiles = [
    ("publisher", Path("/root/.hermes")),
    ("receiver", Path("/root/.hermes/profiles/bubble-mrk-receiver-bubble-mrk-20260519-091525")),
]
for name, root in profiles:
    records = EventProjectionStore(root=root).list_records(limit=100, q=run).get("records", [])
    print("PROFILE", name, "records", len(records))
    for r in records:
        print(json.dumps({k: r.get(k) for k in ["event_type", "subject", "consume_status", "session_id", "payload_summary"]}, ensure_ascii=False, default=str))
PY'
```

Expected result for directed delivery:

- receiver has one `wsp.mrk.requirement.published` record on `wsp.78867306-5f5d-4cd5-b7de-d085c562b2d9`
- receiver `consume_status` is `handled`
- publisher has zero records for its own directed demand

## Evidence Interpretation

For the full real test, PASS requires the generated report to show:

- receiver gateway consumed the requirement
- receiver session evidence includes real `linz_*` / `linz_bubble_*` tool calls
- final DemandBubble is archived

Common current failure:

- receiver gets `wsp.mrk.requirement.published`
- receiver calls direct Bubble API tools such as `linz_bubble_accept_demand` and `linz_bubble_create_task`
- backend does not create the MRK default TaskBubble `task_{requirement_id}_{worker_os_id}`
- publisher does not receive `wsp.mrk.order.handover.delivered`
- report fails with missing `DemandBubble archived`

Do not treat that as a fake script problem. It means the real agent ran, but chose the wrong business path.

## Useful Debug Commands

Snapshot a demand:

```powershell
wsl -u root -- env HOME=/root HERMES_HOME=/root/.hermes bash -lc 'cd /mnt/d/workspace/hermes-agent; /src/hermes-agent/venv/bin/python - <<'"'"'PY'"'"'
from tools.linz_world_bubble_tools import linz_bubble_snapshot
import json
req = "REQ-REPLACE-ME"
res = json.loads(linz_bubble_snapshot({"bubble_id": req}))
s = res.get("snapshot", {})
print(json.dumps({
    "demand": s.get("bubble"),
    "children": s.get("children"),
    "events": [
        {"type": e.get("behavior_event_type"), "bubble_id": e.get("bubble_id"), "after": e.get("after_state"), "reason": e.get("reason")}
        for e in s.get("behavior_events", [])
    ],
}, ensure_ascii=False, indent=2))
PY'
```

Find session evidence:

```powershell
wsl -u root -- env HOME=/root bash -lc 'rg -n "REQ-REPLACE-ME|mrk.order.accepted|linz_bubble_accept_demand|linz_bubble_create_task|handover.delivered" /root/.hermes/profiles/bubble-mrk-receiver-bubble-mrk-20260519-091525/sessions -S || true'
```

Check report directories:

```powershell
Get-ChildItem D:\workspace\hermes-agent\experiment\results -Directory |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 Name,FullName,LastWriteTime
```
