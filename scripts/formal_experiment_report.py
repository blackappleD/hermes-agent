#!/usr/bin/env python3
"""Generate a static HTML report for formal experiment exports."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SIGNAL_FIELDS = (
    "life_state",
    "tension_field",
    "tension_set",
    "action_potential",
    "self_prompt",
    "open_intent",
    "arbitration",
    "actual_action",
    "evidence_refs",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _short(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "..."


def _raw_summary(row: dict[str, Any]) -> str:
    step = str(row.get("step") or "")
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    if step == "life_state":
        return _short(data.get("life_state") or data)
    if step in {"tension_operation", "tension_set"}:
        return _short(data.get("tension_set") or data.get("tension_delta") or data.get("tension_field") or data)
    if step == "action_potential":
        ap = data.get("action_potential") or data
        if isinstance(ap, dict):
            parts = [
                f"{key}={ap[key]}"
                for key in (
                    "recommended_depth",
                    "overall_score",
                    "risk_cost",
                    "value_potential",
                    "mutual_benefit_potential",
                    "learning_potential",
                )
                if key in ap
            ]
            if parts:
                return "; ".join(parts)
        return _short(ap)
    if step == "self_prompt":
        prompt = data.get("self_prompt") or data
        if isinstance(prompt, dict):
            return _short(
                prompt.get("potential_summary")
                or prompt.get("state_summary")
                or prompt.get("tension_summary")
                or prompt
            )
        return _short(prompt)
    if step == "open_intent":
        return _short(data.get("open_intent") or data.get("intent") or data)
    if step == "arbiter":
        return _short(data.get("arbitration") or data.get("arbiter") or data)
    if step in {"goal_event", "signal_set"}:
        return _short(data.get("event_ref") or data.get("signals") or data)
    return _short(data)


def _payload_dict(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("raw", {}).get("payload_summary") or row.get("payload_summary") or ""
    parsed = _json_loads(data, {})
    return parsed if isinstance(parsed, dict) else {}


def _json_loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def _transition_event_ids(row: dict[str, Any], run_id: str) -> list[str]:
    ids = row.get("source_event_ids") if isinstance(row.get("source_event_ids"), list) else []
    if not ids and isinstance(row.get("event_id"), str):
        ids = [row["event_id"]]
    prefix = f"formal:{run_id}:"
    return [value for value in ids if isinstance(value, str) and value.startswith(prefix)]


def _best_transition_by_event(transitions: list[dict[str, Any]], run_id: str) -> dict[str, dict[str, Any]]:
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in transitions:
        if row.get("pipeline_scope") != "formal_event":
            continue
        for event_id in _transition_event_ids(row, run_id):
            by_event[event_id].append(row)

    def score(row: dict[str, Any]) -> int:
        return sum(
            bool(row.get(key))
            for key in ("tension_field", "tension_set", "action_potential", "self_prompt", "open_intent", "arbitration")
        )

    return {event_id: max(rows, key=score) for event_id, rows in by_event.items() if rows}


def _life_summary(row: dict[str, Any]) -> str:
    if row.get("life_state"):
        return _short(row.get("life_state"), 500)
    prompt = row.get("self_prompt") if isinstance(row.get("self_prompt"), dict) else {}
    return str(prompt.get("state_summary") or "")


def _parse_life_state(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"cycle": "", "recovery": "", "energy": None, "fatigue": None, "wakefulness": None, "restraint": None}
    for key in ("cycle", "recovery"):
        match = re.search(rf"\b{key}=([^\s]+)", text or "")
        if match:
            out[key] = match.group(1)
    for key in ("energy", "fatigue", "wakefulness", "restraint"):
        match = re.search(rf"\b{key}=([-+]?\d+(?:\.\d+)?)", text or "")
        if match:
            out[key] = float(match.group(1))
    return out


def _action_summary(row: dict[str, Any]) -> dict[str, Any]:
    action = row.get("action_potential") if isinstance(row.get("action_potential"), dict) else {}
    return {
        key: action.get(key)
        for key in (
            "overall_score",
            "value_potential",
            "mutual_benefit_potential",
            "learning_potential",
            "risk_cost",
            "recommended_depth",
        )
    }


def _tension_operations(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    field = row.get("tension_field") if isinstance(row.get("tension_field"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for op in field.get("operations") or []:
        if isinstance(op, dict) and op.get("tension_id"):
            out[str(op["tension_id"])] = op
    return out


def _tension_values(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tension_set = row.get("tension_set") if isinstance(row.get("tension_set"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for group in ("core_tensions", "dynamic_tensions"):
        for item in tension_set.get(group) or []:
            if isinstance(item, dict) and item.get("tension_id"):
                out[str(item["tension_id"])] = item
    return out


def _build_effect_rows(events: list[dict[str, Any]], transitions: list[dict[str, Any]], run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    best = _best_transition_by_event(transitions, run_id)
    event_effects: list[dict[str, Any]] = []
    tension_effects: list[dict[str, Any]] = []

    for event in events:
        payload = _payload_dict(event)
        transition = best.get(str(event.get("event_id") or ""), {})
        life_text = _life_summary(transition)
        life = _parse_life_state(life_text)
        action = _action_summary(transition)
        base = {
            "phase": event.get("phase"),
            "scenario_id": event.get("scenario_id"),
            "sequence": payload.get("sequence"),
            "subject": event.get("subject"),
            "event_type": event.get("event_type"),
            "event_id": event.get("event_id"),
        }
        event_effects.append(
            {
                **base,
                **action,
                **life,
                "life_state_summary": life_text,
                "runtime_transition_rows": len(
                    [row for row in transitions if str(event.get("event_id") or "") in _transition_event_ids(row, run_id)]
                ),
                "missing_core_modules": ";".join(transition.get("missing_core_modules") or []),
            }
        )

        operations = _tension_operations(transition)
        values = _tension_values(transition)
        for tension_id in sorted(set(operations) | set(values)):
            op = operations.get(tension_id, {})
            value = values.get(tension_id, {})
            tension_effects.append(
                {
                    **base,
                    "tension_id": tension_id,
                    "tension_type": value.get("tension_type") or op.get("tension_type"),
                    "operation": op.get("operation"),
                    "intensity_delta": op.get("intensity_delta"),
                    "activation_after": value.get("activation"),
                    "baseline_after": value.get("baseline"),
                    "intensity_after": value.get("intensity"),
                    "trend_after": value.get("trend"),
                    "trend_slope_after": value.get("trend_slope"),
                    "reason": op.get("reason"),
                }
            )
    return event_effects, tension_effects


def build_report_data(base: Path) -> dict[str, Any]:
    summary = _read_json(base / "summary.json")
    manifest = _read_json(base / "manifest.json")
    events = _read_jsonl(base / "events.jsonl")
    transitions = _read_jsonl(base / "transitions.jsonl")
    raw_rows = _read_jsonl(base / "os_runtime_raw.jsonl")
    anomalies = _read_json(base / "anomalies.json")
    event_effects, tension_effects = _build_effect_rows(events, transitions, str(summary.get("run_id") or manifest.get("run_id") or ""))

    raw_by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        raw_by_trace[str(row.get("trace_id") or row.get("session_id") or "unknown")].append(row)

    trace_summaries = []
    for trace_id, rows in raw_by_trace.items():
        steps = [str(row.get("step") or "unknown") for row in rows]
        trace_summaries.append(
            {
                "trace_id": trace_id,
                "session_id": next((row.get("session_id") for row in rows if row.get("session_id")), ""),
                "first_timestamp": min((str(row.get("timestamp") or "") for row in rows), default=""),
                "row_count": len(rows),
                "unique_steps": list(dict.fromkeys(steps)),
            }
        )
    trace_summaries.sort(key=lambda item: item["first_timestamp"])

    event_rows = [
        {
            "idx": idx,
            "phase": row.get("phase"),
            "scenario_id": row.get("scenario_id"),
            "event_id": row.get("event_id"),
            "subject": row.get("subject"),
            "event_type": row.get("event_type"),
            "consume_status": row.get("consume_status"),
            "projection_status": row.get("projection_status"),
            "payload_summary": row.get("payload_summary"),
            "gateway_transition_count": len(row.get("gateway_transitions") or []),
            "raw": row,
            "gateway_transitions_markdown": row.get("gateway_transitions_markdown") or "",
        }
        for idx, row in enumerate(events, start=1)
    ]

    transition_rows = []
    signal_counts: Counter[str] = Counter()
    for idx, row in enumerate(transitions, start=1):
        present = [field for field in SIGNAL_FIELDS if row.get(field) not in (None, "", [])]
        signal_counts.update(present)
        transition_rows.append(
            {
                "idx": idx,
                "timestamp": row.get("timestamp"),
                "event_id": row.get("event_id"),
                "trace_id": row.get("trace_id"),
                "session_id": row.get("session_id"),
                "fields": present,
                "summary": _short({field: row.get(field) for field in present[:3]}, 320),
                "raw": row,
            }
        )

    runtime_rows = [
        {
            "idx": idx,
            "timestamp": row.get("timestamp"),
            "phase": row.get("phase"),
            "step": row.get("step"),
            "step_index": row.get("step_index"),
            "trace_id": row.get("trace_id"),
            "session_id": row.get("session_id"),
            "summary": _raw_summary(row),
            "raw": row,
        }
        for idx, row in enumerate(raw_rows, start=1)
    ]

    return {
        "summary": summary,
        "manifest": manifest,
        "metrics": {
            "phase_counts": dict(Counter(row.get("phase") or "unknown" for row in events)),
            "consume_counts": dict(Counter(row.get("consume_status") or "unknown" for row in events)),
            "projection_counts": dict(Counter(row.get("projection_status") or "unknown" for row in events)),
            "step_counts": dict(Counter(row.get("step") or "unknown" for row in raw_rows)),
            "anomaly_counts": dict(Counter(row.get("code") or "unknown" for row in anomalies)),
            "transition_signal_counts": dict(signal_counts),
            "effect_event_count": len(event_effects),
            "effect_tension_count": len(tension_effects),
            "raw_count": len(raw_rows),
            "trace_count": len(trace_summaries),
        },
        "events": event_rows,
        "eventEffects": event_effects,
        "tensionEffects": tension_effects,
        "transitions": transition_rows,
        "runtimeRows": runtime_rows,
        "traceSummaries": trace_summaries,
        "anomalies": anomalies,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Formal Experiment Report</title>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--ink:#18202a;--muted:#637083;--line:#d9dee7;--soft:#eef1f5;--teal:#0f766e;--blue:#2563eb;--amber:#b45309;--rose:#be123c;--green:#15803d;--shadow:0 12px 28px rgba(18,28,45,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}header{background:#101827;color:#fff;border-bottom:4px solid var(--teal)}header .wrap{max-width:1280px;margin:0 auto;padding:28px 28px 24px}.wrap{max-width:1280px;margin:0 auto;padding:22px 28px}h1{margin:0 0 10px;font-size:30px;line-height:1.15}h2{font-size:18px;margin:0 0 14px}h3{font-size:14px;margin:0 0 10px}.sub{color:#c8d1df;font-size:14px;line-height:1.5}.grid{display:grid;gap:14px}.metrics{grid-template-columns:repeat(6,minmax(0,1fr));margin-top:-34px}.metric,.panel{background:var(--panel);border:1px solid var(--line);box-shadow:var(--shadow)}.metric{padding:14px;min-height:86px}.metric .label{font-size:11px;text-transform:uppercase;color:var(--muted);font-weight:750}.metric .value{font-size:28px;font-weight:780;margin-top:6px}.metric .hint{font-size:12px;color:var(--muted)}.panel{padding:16px;margin-bottom:18px}.cols{grid-template-columns:1.1fr .9fr}.bars{display:grid;gap:8px}.barrow{display:grid;grid-template-columns:142px 1fr 42px;align-items:center;gap:10px;font-size:13px}.bar{height:10px;background:var(--soft);overflow:hidden}.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--teal),var(--blue))}.note{border-left:4px solid var(--amber);background:#fff7ed;padding:12px 14px;color:#5f370e;margin-bottom:18px}.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 18px}.tab{border:1px solid var(--line);background:#fff;color:var(--ink);height:34px;padding:0 12px;font-weight:650;cursor:pointer}.tab.active{background:#101827;color:#fff;border-color:#101827}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;align-items:center}.toolbar input,.toolbar select{height:34px;border:1px solid var(--line);background:#fff;padding:0 10px;font-size:13px;color:var(--ink);min-width:170px}.scroll{max-height:640px;overflow:auto;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left;vertical-align:top}th{font-size:11px;text-transform:uppercase;color:var(--muted);background:#f9fafb;position:sticky;top:0;z-index:1}tbody tr:hover{background:#f8fafc}.pill{display:inline-flex;align-items:center;min-height:22px;padding:2px 8px;font-size:12px;font-weight:720;border:1px solid var(--line);background:#f8fafc;color:#334155}.pill.good{background:#ecfdf5;color:#166534;border-color:#bbf7d0}.pill.warn{background:#fffbeb;color:#92400e;border-color:#fde68a}.pill.bad{background:#fff1f2;color:#9f1239;border-color:#fecdd3}.pill.info{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:12px}.muted{color:var(--muted)}.small{font-size:12px}.truncate{max-width:380px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.btn{border:1px solid var(--line);background:#fff;height:28px;padding:0 9px;cursor:pointer;font-size:12px}.btn:hover{border-color:#94a3b8}.hidden{display:none!important}.footer{color:var(--muted);font-size:12px;padding:12px 0 30px}@media(max-width:980px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:0}.cols{grid-template-columns:1fr}.wrap{padding:18px}.barrow{grid-template-columns:96px 1fr 34px}}
</style>
</head>
<body>
<header><div class="wrap"><h1>Hermes Formal Experiment Report</h1><div class="sub">Run ID: <span class="mono" id="runId"></span><br>Profile: <span class="mono" id="profile"></span> · Exported: <span class="mono" id="exportedAt"></span> · Hermes Home: <span class="mono" id="home"></span></div></div></header>
<main class="wrap">
<section class="grid metrics" id="metrics"></section>
<section class="note"><strong>说明：</strong>本报告展示 direct NATS 注入后的 gateway 投影、OS Runtime 原始管线日志和导出器校验结果。Events 页的 <span class="mono">Copy MD</span> 会复制该事件的 raw payload 与全部 gateway transitions；Runtime Pipeline 展示张力场、张力集合、行动势能等模块输出。</section>
<section class="grid cols">
  <div class="panel"><h2>阶段与状态分布</h2><div class="grid cols"><div><h3>Events by Phase</h3><div class="bars" id="phaseBars"></div></div><div><h3>Gateway Consume Status</h3><div class="bars" id="consumeBars"></div><h3 style="margin-top:16px">Projection Status</h3><div class="bars" id="projectionBars"></div></div></div></div>
  <div class="panel"><h2>OS Runtime Step Counts</h2><div class="bars" id="stepBars"></div></div>
</section>
<section class="tabs"><button class="tab active" data-tab="effects">Event Effects</button><button class="tab" data-tab="tensions">Tension Effects</button><button class="tab" data-tab="events">Events</button><button class="tab" data-tab="runtime">Runtime Pipeline</button><button class="tab" data-tab="traces">Trace Groups</button><button class="tab" data-tab="anomalies">Anomalies</button><button class="tab" data-tab="sources">Sources</button></section>
<section id="tab-effects" class="panel"><h2>Event Effects</h2><div class="toolbar"><input id="effectSearch" placeholder="Search phase/scenario/event"><select id="effectPhaseFilter"><option value="">All phases</option></select></div><div class="scroll"><table><thead><tr><th>#</th><th>Phase</th><th>Scenario</th><th>Event Type</th><th>Overall</th><th>Value</th><th>Mutual</th><th>Learning</th><th>Risk</th><th>Depth</th><th>Life State</th><th>Event</th></tr></thead><tbody id="effectBody"></tbody></table></div></section>
<section id="tab-tensions" class="panel hidden"><h2>Tension Effects</h2><div class="toolbar"><input id="tensionSearch" placeholder="Search tension/scenario/reason"><select id="tensionPhaseFilter"><option value="">All phases</option></select><select id="tensionIdFilter"><option value="">All tensions</option></select></div><div class="scroll"><table><thead><tr><th>#</th><th>Phase</th><th>Scenario</th><th>Tension</th><th>Operation</th><th>Delta</th><th>Activation</th><th>Intensity</th><th>Trend</th><th>Reason</th></tr></thead><tbody id="tensionBody"></tbody></table></div></section>
<section id="tab-events" class="panel hidden"><h2>Gateway Events</h2><div class="toolbar"><input id="eventSearch" placeholder="Search event/scenario/subject"><select id="phaseFilter"><option value="">All phases</option></select><select id="consumeFilter"><option value="">All statuses</option></select></div><div class="scroll"><table><thead><tr><th>#</th><th>Phase</th><th>Scenario</th><th>Subject</th><th>Event Type</th><th>Consume</th><th>Projection</th><th>Transitions</th><th>Markdown</th><th>Detail</th></tr></thead><tbody id="eventBody"></tbody></table></div></section>
<section id="tab-runtime" class="panel hidden"><h2>Runtime Pipeline Rows</h2><div class="toolbar"><input id="runtimeSearch" placeholder="Search step/trace/summary"><select id="stepFilter"><option value="">All steps</option></select></div><div class="scroll"><table><thead><tr><th>#</th><th>Time</th><th>Step</th><th>Trace</th><th>Session</th><th>Summary</th><th>Raw</th></tr></thead><tbody id="runtimeBody"></tbody></table></div></section>
<section id="tab-traces" class="panel hidden"><h2>Trace Groups</h2><div class="scroll"><table><thead><tr><th>#</th><th>First Time</th><th>Trace</th><th>Session</th><th>Rows</th><th>Steps</th></tr></thead><tbody id="traceBody"></tbody></table></div></section>
<section id="tab-anomalies" class="panel hidden"><h2>Anomalies</h2><div class="toolbar"><input id="anomalySearch" placeholder="Search anomaly/message/event"><select id="anomalyFilter"><option value="">All codes</option></select></div><div class="scroll"><table><thead><tr><th>#</th><th>Code</th><th>Event/Trace</th><th>Message</th><th>Raw</th></tr></thead><tbody id="anomalyBody"></tbody></table></div></section>
<section id="tab-sources" class="panel hidden"><h2>Source Files</h2><table><tbody id="sourceBody"></tbody></table></section>
<div class="footer">Generated as a static single-file report. Raw export files remain next to this HTML.</div>
</main>
<script type="application/json" id="report-data">__REPORT_DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('report-data').textContent);
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = v => JSON.stringify(v, null, 2);
const pill = v => { const s=String(v||''); const cls=/handled|projected|published|current|success|P[0-9]/.test(s)?'good':/processing|missing|anomaly|pending/.test(s)?'warn':/failed|rejected|error/.test(s)?'bad':'info'; return `<span class="pill ${cls}">${esc(s||'-')}</span>`; };
function renderMetrics(){const s=DATA.summary,m=DATA.metrics;const cards=[['Events',s.counts.events,'gateway projected'],['Effect Rows',m.effect_event_count,'event-level'],['Tensions',m.effect_tension_count,'tension effects'],['Transitions',s.counts.transitions,'runtime groups'],['Anomalies',s.counts.anomalies,'export checks'],['Traces',m.trace_count,'runtime groups']];$('metrics').innerHTML=cards.map(c=>`<div class="metric"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="hint">${c[2]}</div></div>`).join('');}
function bars(id,obj){const entries=Object.entries(obj||{}).sort((a,b)=>b[1]-a[1]);const max=Math.max(1,...entries.map(e=>e[1]));$(id).innerHTML=entries.map(([k,v])=>`<div class="barrow"><span class="truncate">${esc(k)}</span><div class="bar"><span style="width:${Math.max(4,v/max*100)}%"></span></div><span class="mono">${v}</span></div>`).join('')||'<div class="muted small">No data</div>';}
function options(id,values){const el=$(id);[...new Set(values.filter(Boolean))].sort().forEach(v=>el.insertAdjacentHTML('beforeend',`<option value="${esc(v)}">${esc(v)}</option>`));}
async function copyText(value){if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(value);return;}const t=document.createElement('textarea');t.value=value;t.setAttribute('readonly','true');t.style.position='fixed';t.style.left='-9999px';document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();}
function copyEventMd(idx){const event=DATA.events.find(x=>x.idx===idx);copyText(event?.gateway_transitions_markdown||'');}
function fmtNum(v){return typeof v==='number'?v.toFixed(3):esc(v??'-');}
function renderEffects(){const q=$('effectSearch').value.toLowerCase(),ph=$('effectPhaseFilter').value;const rows=DATA.eventEffects.filter(e=>(!ph||e.phase===ph)&&JSON.stringify(e).toLowerCase().includes(q));$('effectBody').innerHTML=rows.map((e,i)=>`<tr><td class="mono">${i+1}</td><td>${pill(e.phase)}</td><td><div class="truncate" title="${esc(e.scenario_id)}">${esc(e.scenario_id)}${e.sequence?` #${esc(e.sequence)}`:''}</div></td><td class="mono truncate">${esc(e.event_type)}</td><td class="mono">${fmtNum(e.overall_score)}</td><td class="mono">${fmtNum(e.value_potential)}</td><td class="mono">${fmtNum(e.mutual_benefit_potential)}</td><td class="mono">${fmtNum(e.learning_potential)}</td><td class="mono">${fmtNum(e.risk_cost)}</td><td>${pill(e.recommended_depth)}</td><td class="truncate" title="${esc(e.life_state_summary)}">cycle=${esc(e.cycle)} energy=${fmtNum(e.energy)} wake=${fmtNum(e.wakefulness)} restraint=${fmtNum(e.restraint)}</td><td class="mono truncate">${esc(e.event_id)}</td></tr>`).join('');}
function renderTensions(){const q=$('tensionSearch').value.toLowerCase(),ph=$('tensionPhaseFilter').value,tid=$('tensionIdFilter').value;const rows=DATA.tensionEffects.filter(e=>(!ph||e.phase===ph)&&(!tid||e.tension_id===tid)&&JSON.stringify(e).toLowerCase().includes(q));$('tensionBody').innerHTML=rows.map((e,i)=>`<tr><td class="mono">${i+1}</td><td>${pill(e.phase)}</td><td><div class="truncate" title="${esc(e.scenario_id)}">${esc(e.scenario_id)}${e.sequence?` #${esc(e.sequence)}`:''}</div><div class="mono muted truncate">${esc(e.event_type)}</div></td><td class="mono truncate">${esc(e.tension_id)}</td><td>${pill(e.operation)}</td><td class="mono">${fmtNum(e.intensity_delta)}</td><td class="mono">${fmtNum(e.activation_after)}</td><td class="mono">${fmtNum(e.intensity_after)}</td><td class="mono">${fmtNum(e.trend_after)}</td><td class="truncate" title="${esc(e.reason)}">${esc(e.reason)}</td></tr>`).join('');}
function renderEvents(){const q=$('eventSearch').value.toLowerCase(),ph=$('phaseFilter').value,st=$('consumeFilter').value;const rows=DATA.events.filter(e=>(!ph||e.phase===ph)&&(!st||e.consume_status===st)&&JSON.stringify(e).toLowerCase().includes(q));$('eventBody').innerHTML=rows.map(e=>`<tr><td class="mono">${e.idx}</td><td>${pill(e.phase)}</td><td><div class="truncate" title="${esc(e.scenario_id)}">${esc(e.scenario_id)}</div><div class="mono muted truncate">${esc(e.event_id)}</div></td><td class="mono truncate">${esc(e.subject)}</td><td class="mono truncate">${esc(e.event_type)}</td><td>${pill(e.consume_status)}</td><td>${pill(e.projection_status)}</td><td class="mono">${e.gateway_transition_count}</td><td><button class="btn" onclick="copyEventMd(${e.idx})">Copy MD</button></td><td><button class="btn" onclick="showRaw(DATA.events.find(x=>x.idx===${e.idx}).raw)">JSON</button></td></tr>`).join('');}
function renderRuntime(){const q=$('runtimeSearch').value.toLowerCase(),step=$('stepFilter').value;const rows=DATA.runtimeRows.filter(r=>(!step||r.step===step)&&JSON.stringify([r.step,r.trace_id,r.session_id,r.summary]).toLowerCase().includes(q));$('runtimeBody').innerHTML=rows.map(r=>`<tr><td class="mono">${r.idx}</td><td class="mono truncate">${esc(r.timestamp)}</td><td>${pill(r.step)}</td><td class="mono truncate">${esc(r.trace_id)}</td><td class="mono truncate">${esc(r.session_id)}</td><td>${esc(r.summary)}</td><td><button class="btn" onclick="showRaw(DATA.runtimeRows.find(x=>x.idx===${r.idx}).raw)">JSON</button></td></tr>`).join('');}
function renderTraces(){$('traceBody').innerHTML=DATA.traceSummaries.map((t,i)=>`<tr><td class="mono">${i+1}</td><td class="mono truncate">${esc(t.first_timestamp)}</td><td class="mono truncate">${esc(t.trace_id)}</td><td class="mono truncate">${esc(t.session_id)}</td><td class="mono">${t.row_count}</td><td>${t.unique_steps.map(pill).join(' ')}</td></tr>`).join('');}
function renderAnomalies(){const q=$('anomalySearch').value.toLowerCase(),code=$('anomalyFilter').value;const rows=DATA.anomalies.map((a,i)=>({...a,idx:i+1})).filter(a=>(!code||a.code===code)&&JSON.stringify(a).toLowerCase().includes(q));$('anomalyBody').innerHTML=rows.map(a=>`<tr><td class="mono">${a.idx}</td><td>${pill(a.code)}</td><td class="mono truncate">${esc(a.event_id||a.trace_id||a.session_id||'')}</td><td>${esc(a.message)}</td><td><button class="btn" onclick="showRaw(DATA.anomalies[${a.idx-1}])">JSON</button></td></tr>`).join('');}
function renderSources(){const m=DATA.manifest;const rows=[['Run ID',m.run_id],['Profile',m.profile],['Exported At',m.exported_at],['Hermes Home',m.hermes_home],...Object.entries(m.source_paths||{})];$('sourceBody').innerHTML=rows.map(([k,v])=>`<tr><th>${esc(k)}</th><td class="mono">${esc(v)}</td></tr>`).join('');}
function showRaw(obj){const w=window.open('','_blank','width=980,height=760');w.document.write(`<title>Raw JSON</title><style>body{margin:0;background:#0b1220;color:#dbeafe}pre{white-space:pre-wrap;padding:18px;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace}</style><pre>${esc(pretty(obj))}</pre>`);}
document.querySelectorAll('.tab').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));btn.classList.add('active');['effects','tensions','events','runtime','traces','anomalies','sources'].forEach(t=>$('tab-'+t).classList.toggle('hidden',t!==btn.dataset.tab));}));
const m=DATA.manifest;$('runId').textContent=m.run_id;$('profile').textContent=m.profile;$('exportedAt').textContent=m.exported_at;$('home').textContent=m.hermes_home;renderMetrics();bars('phaseBars',DATA.metrics.phase_counts);bars('consumeBars',DATA.metrics.consume_counts);bars('projectionBars',DATA.metrics.projection_counts);bars('stepBars',DATA.metrics.step_counts);options('effectPhaseFilter',DATA.eventEffects.map(e=>e.phase));options('tensionPhaseFilter',DATA.tensionEffects.map(e=>e.phase));options('tensionIdFilter',DATA.tensionEffects.map(e=>e.tension_id));options('phaseFilter',DATA.events.map(e=>e.phase));options('consumeFilter',DATA.events.map(e=>e.consume_status));options('stepFilter',DATA.runtimeRows.map(r=>r.step));options('anomalyFilter',DATA.anomalies.map(a=>a.code));['effectSearch','effectPhaseFilter'].forEach(id=>$(id).addEventListener('input',renderEffects));['tensionSearch','tensionPhaseFilter','tensionIdFilter'].forEach(id=>$(id).addEventListener('input',renderTensions));['eventSearch','phaseFilter','consumeFilter'].forEach(id=>$(id).addEventListener('input',renderEvents));['runtimeSearch','stepFilter'].forEach(id=>$(id).addEventListener('input',renderRuntime));['anomalySearch','anomalyFilter'].forEach(id=>$(id).addEventListener('input',renderAnomalies));renderEffects();renderTensions();renderEvents();renderRuntime();renderTraces();renderAnomalies();renderSources();
</script>
</body>
</html>
"""


def generate(base: Path) -> Path:
    data = build_report_data(base)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/")
    output = base / "report.html"
    output.write_text(HTML_TEMPLATE.replace("__REPORT_DATA__", payload), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: formal_experiment_report.py <experiment-results-dir>", file=sys.stderr)
        return 2
    base = Path(args[0]).expanduser().resolve()
    output = generate(base)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
