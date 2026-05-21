"""Markdown-backed Linz World guide retrieval.

This module is intentionally read-only. It turns a long Linz World manual into
small, scene-specific sections that tools can expose progressively to the
agent.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home


DEFAULT_MANUAL_RELATIVE_PATH = Path("linz_world") / "manual.md"
PACKAGED_MANUAL_PATH = Path(__file__).resolve().parent / "knowledge" / "linz_world_manual.md"

_SECTION_HEADING_RE = re.compile(r"^(#{2,6})\s+([A-Za-z0-9][A-Za-z0-9_.-]*):\s*(.+?)\s*$")
_META_BLOCK_RE = re.compile(r"<!--\s*linz-world\s*(.*?)-->", re.IGNORECASE | re.DOTALL)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]+|[\u4e00-\u9fff]{2,}")

_LIST_KEYS = {
    "aliases",
    "bubble_types",
    "event_types",
    "forbidden",
    "intents",
    "lifecycle_states",
    "next_steps",
    "required_fields",
    "subjects",
    "tags",
    "tools",
}

_BOOL_KEYS = {"approval_required"}

_TERM_HINTS = {
    "需求": ["需求", "requirement", "demand", "mrk.requirement"],
    "接单": ["接单", "接需求", "accept", "accepted", "accept_demand", "order"],
    "订单": ["订单", "order", "mrk.order"],
    "任务": ["任务", "task", "taskbubble", "task bubble"],
    "挂载": ["挂载", "mount", "slot"],
    "成果": ["成果", "交付", "artifact", "submit_artifact", "delivery"],
    "验收": ["验收", "review", "acceptance", "approve", "reject"],
    "结算": ["结算", "settlement", "rent", "transfer"],
    "聊天": ["聊天", "私聊", "私信", "message", "chat", "dm"],
    "记忆": ["记忆", "memory", "soul memory"],
    "关系": ["关系", "relationship", "collaborator"],
}


@dataclass(frozen=True)
class LinzGuideSection:
    section_id: str
    title: str
    level: int
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return f"{'#' * self.level} {self.section_id}: {self.title}\n\n{self.body}".strip()

    def summary(self, max_chars: int = 700) -> str:
        text = str(self.metadata.get("summary") or "").strip()
        if not text:
            text = _first_paragraph(self.body)
        return _clamp_text(text, max_chars)


@dataclass(frozen=True)
class LinzGuideMatch:
    section: LinzGuideSection
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self, *, max_chars: int = 700, include_content: bool = False) -> dict[str, Any]:
        data = {
            "section_id": self.section.section_id,
            "title": self.section.title,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
            "metadata": _public_metadata(self.section.metadata),
            "summary": self.section.summary(max_chars=max_chars),
        }
        if include_content:
            data["content"] = _clamp_text(self.section.content, max_chars)
        return data


@dataclass(frozen=True)
class LinzGuideManual:
    path: str
    sections: tuple[LinzGuideSection, ...]

    def get(self, section_id: str) -> LinzGuideSection | None:
        needle = _normalize_id(section_id)
        for section in self.sections:
            if _normalize_id(section.section_id) == needle:
                return section
        return None


_MANUAL_CACHE: dict[tuple[str, float, int], LinzGuideManual] = {}


def resolve_manual_path(manual_path: str | os.PathLike[str] | None = None) -> Path:
    if manual_path:
        return Path(manual_path).expanduser().resolve()
    env_path = os.getenv("HERMES_LINZ_WORLD_MANUAL_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    profile_manual = get_hermes_home() / DEFAULT_MANUAL_RELATIVE_PATH
    if profile_manual.is_file():
        return profile_manual.resolve()
    return PACKAGED_MANUAL_PATH


def load_manual(
    manual_path: str | os.PathLike[str] | None = None,
    *,
    use_cache: bool = True,
) -> LinzGuideManual:
    path = resolve_manual_path(manual_path)
    try:
        stat = path.stat()
        cache_key = (str(path), stat.st_mtime, stat.st_size)
    except OSError:
        return LinzGuideManual(path=str(path), sections=())
    if use_cache and cache_key in _MANUAL_CACHE:
        return _MANUAL_CACHE[cache_key]
    text = path.read_text(encoding="utf-8")
    manual = LinzGuideManual(path=str(path), sections=tuple(_parse_sections(text)))
    if use_cache:
        _MANUAL_CACHE.clear()
        _MANUAL_CACHE[cache_key] = manual
    return manual


def search_sections(
    *,
    query: str = "",
    subject: str = "",
    event_type: str = "",
    bubble_type: str = "",
    lifecycle_state: str = "",
    user_intent: str = "",
    tools: list[str] | None = None,
    limit: int = 5,
    manual_path: str | os.PathLike[str] | None = None,
) -> list[LinzGuideMatch]:
    manual = load_manual(manual_path)
    context = {
        "query": str(query or ""),
        "subject": str(subject or ""),
        "event_type": str(event_type or ""),
        "bubble_type": str(bubble_type or ""),
        "lifecycle_state": str(lifecycle_state or ""),
        "user_intent": str(user_intent or ""),
        "tools": [str(item) for item in (tools or [])],
    }
    matches = [_score_section(section, context) for section in manual.sections]
    filtered = [match for match in matches if match.score > 0]
    filtered.sort(key=lambda item: (-item.score, item.section.section_id))
    if not filtered and not any(str(value or "").strip() for value in context.values() if not isinstance(value, list)):
        overview = manual.get("LW-OVERVIEW")
        if overview:
            filtered = [LinzGuideMatch(overview, 1.0, ["default_overview"])]
    return filtered[: _safe_limit(limit)]


def get_section(
    section_id: str,
    *,
    max_chars: int = 6000,
    manual_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    manual = load_manual(manual_path)
    section = manual.get(section_id)
    if not section:
        return {
            "success": False,
            "error": {
                "code": "section_not_found",
                "message": f"Linz World guide section not found: {section_id}",
            },
            "available_section_ids": [item.section_id for item in manual.sections[:50]],
            "manual_path": manual.path,
        }
    return {
        "success": True,
        "section_id": section.section_id,
        "title": section.title,
        "metadata": _public_metadata(section.metadata),
        "content": _clamp_text(section.content, _safe_chars(max_chars)),
        "manual_path": manual.path,
    }


def resolve_flow(
    *,
    query: str = "",
    subject: str = "",
    event_type: str = "",
    bubble_type: str = "",
    lifecycle_state: str = "",
    user_intent: str = "",
    bubble_id: str = "",
    known_fields: dict[str, Any] | None = None,
    limit: int = 5,
    manual_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    matches = search_sections(
        query=query,
        subject=subject,
        event_type=event_type,
        bubble_type=bubble_type,
        lifecycle_state=lifecycle_state,
        user_intent=user_intent,
        limit=limit,
        manual_path=manual_path,
    )
    sections = [match.section for match in matches]
    primary = sections[0] if sections else None
    known = dict(known_fields or {})
    if bubble_id:
        known.setdefault("bubble_id", bubble_id)

    required_fields = _ordered_union(_list_meta(section, "required_fields") for section in sections)
    missing_fields = [field for field in required_fields if not _field_present(known, field)]
    approval_required = any(bool(section.metadata.get("approval_required")) for section in sections)
    recommended_tools = _ordered_union(_list_meta(section, "tools") for section in sections)
    next_steps = _ordered_union(_list_meta(section, "next_steps") for section in sections)
    forbidden = _ordered_union(_list_meta(section, "forbidden") for section in sections)

    if not matches:
        next_steps = [
            "No Linz World workflow rule matched the current context.",
            "Use linz_events_recent or linz_world_guide with more event details before taking side effects.",
            "Ask the user for missing subject, event_type, bubble_id, or lifecycle state.",
        ]
        forbidden = ["external_side_effect_without_matched_rule"]

    phase = str(primary.metadata.get("phase") or "unknown") if primary else "unknown"
    return {
        "success": bool(matches),
        "phase": phase,
        "summary": primary.summary(max_chars=900) if primary else "No matching Linz World workflow section.",
        "matched_sections": [match.to_dict(max_chars=400) for match in matches],
        "recommended_tools": recommended_tools,
        "next_steps": next_steps,
        "approval_required": approval_required,
        "required_fields": required_fields,
        "missing_fields": missing_fields,
        "forbidden": forbidden,
        "context": {
            "subject": subject,
            "event_type": event_type,
            "bubble_type": bubble_type,
            "lifecycle_state": lifecycle_state,
            "user_intent": user_intent,
            "bubble_id": bubble_id,
        },
        "manual_path": load_manual(manual_path).path,
    }


def guide(
    *,
    query: str = "",
    subject: str = "",
    event_type: str = "",
    bubble_type: str = "",
    lifecycle_state: str = "",
    user_intent: str = "",
    limit: int = 5,
    include_content: bool = False,
    manual_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    matches = search_sections(
        query=query,
        subject=subject,
        event_type=event_type,
        bubble_type=bubble_type,
        lifecycle_state=lifecycle_state,
        user_intent=user_intent,
        limit=limit,
        manual_path=manual_path,
    )
    manual = load_manual(manual_path)
    return {
        "success": True,
        "manual_path": manual.path,
        "matches": [
            match.to_dict(max_chars=1400 if include_content else 700, include_content=include_content)
            for match in matches
        ],
        "section_count": len(manual.sections),
        "hint": "Call linz_world_section with a section_id for a fuller section.",
    }


def _parse_sections(text: str) -> list[LinzGuideSection]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str, str]] = []
    for idx, line in enumerate(lines):
        match = _SECTION_HEADING_RE.match(line)
        if not match:
            continue
        headings.append((idx, len(match.group(1)), match.group(2).strip(), match.group(3).strip()))

    sections: list[LinzGuideSection] = []
    for pos, (start, level, section_id, title) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        raw_body = "\n".join(lines[start + 1 : end]).strip()
        metadata = _parse_metadata(raw_body)
        body = _strip_metadata(raw_body).strip()
        sections.append(
            LinzGuideSection(
                section_id=section_id.strip(),
                title=title.strip(),
                level=level,
                body=body,
                metadata=metadata,
            )
        )
    return sections


def _parse_metadata(body: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for block in _META_BLOCK_RE.findall(body):
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in _LIST_KEYS:
                metadata[key] = _split_list(value)
            elif key in _BOOL_KEYS:
                metadata[key] = value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                metadata[key] = value
    return metadata


def _strip_metadata(body: str) -> str:
    return _META_BLOCK_RE.sub("", body).strip()


def _score_section(section: LinzGuideSection, context: dict[str, Any]) -> LinzGuideMatch:
    score = 0.0
    reasons: list[str] = []
    text = _search_text(section)
    metadata = section.metadata

    score += _score_exact("subject", context["subject"], metadata, text, reasons, exact_weight=80, text_weight=12)
    score += _score_exact("event_type", context["event_type"], metadata, text, reasons, exact_weight=80, text_weight=12)
    score += _score_exact("bubble_type", context["bubble_type"], metadata, text, reasons, exact_weight=35, text_weight=8)
    score += _score_exact(
        "lifecycle_state",
        context["lifecycle_state"],
        metadata,
        text,
        reasons,
        exact_weight=30,
        text_weight=5,
    )
    score += _score_intent(context["user_intent"], section, text, reasons)
    score += _score_tools(context.get("tools") or [], metadata, reasons)
    score += _score_query(context["query"], section, text, reasons)

    return LinzGuideMatch(section=section, score=score, reasons=reasons)


def _score_exact(
    name: str,
    value: str,
    metadata: dict[str, Any],
    text: str,
    reasons: list[str],
    *,
    exact_weight: float,
    text_weight: float,
) -> float:
    value = str(value or "").strip()
    if not value:
        return 0.0
    normalized = value.lower()
    list_key = f"{name}s" if name != "lifecycle_state" else "lifecycle_states"
    candidates = [item.lower() for item in _list_value(metadata.get(list_key))]
    if normalized in candidates:
        reasons.append(f"{name}_exact")
        return exact_weight
    if normalized and normalized in text:
        reasons.append(f"{name}_text")
        return text_weight
    return 0.0


def _score_intent(intent: str, section: LinzGuideSection, text: str, reasons: list[str]) -> float:
    intent = str(intent or "").strip().lower()
    if not intent:
        return 0.0
    haystack = set(item.lower() for item in _list_value(section.metadata.get("intents")))
    haystack.update(item.lower() for item in _list_value(section.metadata.get("tags")))
    phase = str(section.metadata.get("phase") or "").lower()
    if intent in haystack or intent == phase:
        reasons.append("intent_exact")
        return 40.0
    if intent in text:
        reasons.append("intent_text")
        return 10.0
    return 0.0


def _score_tools(tools: list[str], metadata: dict[str, Any], reasons: list[str]) -> float:
    section_tools = set(item.lower() for item in _list_value(metadata.get("tools")))
    if not section_tools:
        return 0.0
    matches = [tool for tool in tools if str(tool).lower() in section_tools]
    if not matches:
        return 0.0
    reasons.append("tool_match")
    return min(30.0, 10.0 * len(matches))


def _score_query(query: str, section: LinzGuideSection, text: str, reasons: list[str]) -> float:
    query = str(query or "").strip()
    if not query:
        return 0.0
    score = 0.0
    title = section.title.lower()
    section_terms = _section_terms(section)
    for term in _query_terms(query):
        if term in section_terms:
            score += 12.0
            reasons.append(f"query_term:{term}")
        elif term in title:
            score += 8.0
            reasons.append(f"query_title:{term}")
        elif term in text:
            score += 2.0
    return min(score, 60.0)


def _query_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = [match.group(0).lower() for match in _TOKEN_RE.finditer(lowered)]
    for key, variants in _TERM_HINTS.items():
        if key in query or any(variant in lowered for variant in variants):
            terms.extend(variant.lower() for variant in variants)
            terms.append(key.lower())
    return _dedupe(terms)


def _section_terms(section: LinzGuideSection) -> set[str]:
    terms = set()
    for key in ("tags", "aliases", "intents", "subjects", "event_types", "tools", "bubble_types", "lifecycle_states"):
        terms.update(item.lower() for item in _list_value(section.metadata.get(key)))
    if section.metadata.get("phase"):
        terms.add(str(section.metadata["phase"]).lower())
    return terms


def _search_text(section: LinzGuideSection) -> str:
    parts = [
        section.section_id,
        section.title,
        section.body,
        " ".join(str(item) for item in _public_metadata(section.metadata).values()),
    ]
    return " ".join(parts).lower()


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "internal"}


def _split_list(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,|]", value) if item.strip()]


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)]


def _list_meta(section: LinzGuideSection, key: str) -> list[str]:
    return _list_value(section.metadata.get(key))


def _ordered_union(groups: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
    return result


def _field_present(known_fields: dict[str, Any], field: str) -> bool:
    if field in known_fields and known_fields[field] not in {None, ""}:
        return True
    aliases = {
        "bubble_id": ["bubble_id", "demand_bubble_id", "task_bubble_id", "parent_bubble_id"],
        "task_bubble_id": ["task_bubble_id", "bubble_id"],
        "demand_bubble_id": ["demand_bubble_id", "bubble_id", "parent_bubble_id"],
        "artifact_ref": ["artifact_ref", "summary_ref"],
    }
    return any(known_fields.get(alias) not in {None, ""} for alias in aliases.get(field, []))


def _first_paragraph(text: str) -> str:
    for part in re.split(r"\n\s*\n", text.strip()):
        cleaned = " ".join(line.strip() for line in part.splitlines() if line.strip())
        if cleaned:
            return cleaned
    return ""


def _clamp_text(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 20)].rstrip() + "... [truncated]"


def _safe_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 20))


def _safe_chars(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 6000
    return max(500, min(parsed, 20000))


def _normalize_id(value: str) -> str:
    return str(value or "").strip().upper()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


__all__ = [
    "LinzGuideManual",
    "LinzGuideMatch",
    "LinzGuideSection",
    "get_section",
    "guide",
    "load_manual",
    "resolve_flow",
    "resolve_manual_path",
    "search_sections",
]
