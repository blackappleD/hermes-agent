from agent.linz_world.guide import get_section, guide, resolve_flow, search_sections


def test_requirement_event_resolves_to_acceptance_workflow():
    result = resolve_flow(
        subject="wsp.mrk.requirement.published",
        event_type="wsp.mrk.requirement.published",
        user_intent="accept_demand",
        known_fields={},
    )

    assert result["success"] is True
    assert result["phase"] == "requirement_intake"
    assert "linz_publish" in result["recommended_tools"]
    assert "requirement_id" in result["missing_fields"]
    assert "direct_bubble_accept_as_mrk_order" in result["forbidden"]
    assert result["approval_required"] is True
    assert "auto_accept_demand" in result["forbidden"]


def test_chinese_chat_query_matches_chat_section():
    result = guide(query="怎么在 Linz World 里私聊回复消息", limit=3)

    section_ids = [item["section_id"] for item in result["matches"]]
    assert section_ids
    assert section_ids[0] == "LW-CHAT"
    assert "linz_chat_send" in result["matches"][0]["metadata"]["tools"]


def test_section_progressive_disclosure_returns_single_section():
    result = get_section("LW-ARTIFACT-SUBMIT", max_chars=2000)

    assert result["success"] is True
    assert result["section_id"] == "LW-ARTIFACT-SUBMIT"
    assert "linz_bubble_submit_artifact" in result["metadata"]["tools"]
    assert "LW-REVIEW-ACCEPTANCE" not in result["content"]


def test_search_sections_can_use_bubble_state():
    matches = search_sections(
        bubble_type="task",
        lifecycle_state="active",
        user_intent="submit_artifact",
        limit=5,
    )

    section_ids = [match.section.section_id for match in matches]
    assert "LW-ARTIFACT-SUBMIT" in section_ids
    assert "LW-BUBBLE-TASK" in section_ids
