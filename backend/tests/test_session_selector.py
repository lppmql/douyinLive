"""公共场次选择器与知识库场次范围的契约测试。"""
from datetime import datetime
from types import SimpleNamespace

from app.models.knowledge_time_slices import KnowledgeTimeSlice
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.ai.time_slice_service import search_time_slices
from app.services.ai import vector_store


def _seed_sessions(db):
    room = LiveRoom(account_name="企业号", anchor_name="入口账号")
    db.add(room)
    db.flush()
    sessions = [
        LiveSession(
            room_id=room.id,
            anchor_name="丹姐",
            anchor_nickname="丹姐开店避坑",
            douyin_id="dan-jie",
            douyin_uid="uid-dan",
            session_title="安徽选址避坑",
            live_start_time=datetime(2026, 8, 27, 10, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
        LiveSession(
            room_id=room.id,
            anchor_name="丹姐",
            anchor_nickname="丹姐开店避坑",
            douyin_id="dan-jie",
            douyin_uid="uid-dan",
            session_title="预算测算",
            live_start_time=datetime(2026, 8, 29, 14, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
        LiveSession(
            room_id=room.id,
            anchor_name="李老师",
            douyin_id="li-laoshi",
            douyin_uid="uid-li",
            session_title="品牌快招避坑",
            live_start_time=datetime(2026, 8, 29, 18, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
    ]
    db.add_all(sessions)
    db.commit()
    return sessions


def test_public_selector_filters_real_anchor_and_inclusive_date(client, db, auth_headers):
    sessions = _seed_sessions(db)

    response = client.get(
        "/api/v1/live-sessions/selector-options",
        params={"anchor_key": "uid:uid-dan", "start_date": "2026-08-29", "end_date": "2026-08-29"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [sessions[1].id]


def test_public_selector_always_includes_deep_link_session(client, db, auth_headers):
    sessions = _seed_sessions(db)

    response = client.get(
        "/api/v1/live-sessions/selector-options",
        params={
            "anchor_key": "uid:uid-li",
            "start_date": "2026-08-29",
            "end_date": "2026-08-29",
            "include_session_id": sessions[0].id,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {sessions[0].id, sessions[2].id}


def test_public_anchor_options_use_latest_real_session_snapshot(client, db, auth_headers):
    sessions = _seed_sessions(db)

    response = client.get("/api/v1/live-sessions/anchors", headers=auth_headers)

    assert response.status_code == 200
    anchors = {item["anchor_name"]: item for item in response.json()}
    assert anchors["丹姐"]["anchor_key"] == "uid:uid-dan"
    assert anchors["丹姐"]["latest_session_id"] == sessions[1].id
    assert anchors["丹姐"]["douyin_id"] == "dan-jie"
    assert anchors["李老师"]["latest_session_id"] == sessions[2].id


def test_public_anchor_options_order_snapshot_by_live_time_not_insert_id(
    client, db, auth_headers
):
    sessions = _seed_sessions(db)
    historical_backfill = LiveSession(
        room_id=sessions[0].room_id,
        anchor_name="丹姐旧快照",
        anchor_nickname="历史补采记录",
        douyin_id="dan-jie",
        douyin_uid="uid-dan",
        session_title="后入库的历史场次",
        live_start_time=datetime(2026, 8, 20, 10, 0),
        live_status="ended",
        detail_collection_status="complete",
    )
    db.add(historical_backfill)
    db.commit()
    assert historical_backfill.id > sessions[1].id

    response = client.get("/api/v1/live-sessions/anchors", headers=auth_headers)

    assert response.status_code == 200
    anchor = next(item for item in response.json() if item["anchor_key"] == "uid:uid-dan")
    assert anchor["latest_session_id"] == sessions[1].id
    assert anchor["anchor_name"] == "丹姐"


def test_public_anchor_key_keeps_same_name_different_uids_separate(client, db, auth_headers):
    sessions = _seed_sessions(db)
    same_name_other_anchor = LiveSession(
        room_id=sessions[0].room_id,
        anchor_name="丹姐",
        douyin_id="another-dan",
        douyin_uid="uid-another-dan",
        session_title="同名主播的真实场次",
        live_start_time=datetime(2026, 8, 30, 10, 0),
        live_status="ended",
        detail_collection_status="complete",
    )
    db.add(same_name_other_anchor)
    db.commit()

    anchors_response = client.get("/api/v1/live-sessions/anchors", headers=auth_headers)
    selector_response = client.get(
        "/api/v1/live-sessions/selector-options",
        params={"anchor_key": "uid:uid-another-dan"},
        headers=auth_headers,
    )

    assert anchors_response.status_code == 200
    assert {item["anchor_key"] for item in anchors_response.json()} >= {
        "uid:uid-dan",
        "uid:uid-another-dan",
    }
    assert selector_response.status_code == 200
    assert [item["id"] for item in selector_response.json()] == [same_name_other_anchor.id]


def test_public_anchor_fallback_separates_room_hosts_and_skips_blank_identity(
    client, db, auth_headers
):
    sessions = _seed_sessions(db)
    fallback_sessions = [
        LiveSession(
            room_id=sessions[0].room_id,
            anchor_name="轮班主播甲",
            session_title="甲主播场次",
            live_start_time=datetime(2026, 8, 30, 11, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
        LiveSession(
            room_id=sessions[0].room_id,
            anchor_nickname="轮班主播乙",
            session_title="乙主播场次",
            live_start_time=datetime(2026, 8, 30, 12, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
        LiveSession(
            room_id=sessions[0].room_id,
            session_title="缺少主播身份的脏快照",
            live_start_time=datetime(2026, 8, 30, 13, 0),
            live_status="ended",
            detail_collection_status="complete",
        ),
    ]
    db.add_all(fallback_sessions)
    db.commit()

    anchors_response = client.get("/api/v1/live-sessions/anchors", headers=auth_headers)
    anchors = anchors_response.json()
    fallback_options = {item["anchor_name"]: item for item in anchors if item["anchor_key"].startswith("room:")}

    assert anchors_response.status_code == 200
    assert set(fallback_options) == {"轮班主播甲", "轮班主播乙"}
    assert fallback_options["轮班主播甲"]["anchor_key"] != fallback_options["轮班主播乙"]["anchor_key"]

    selector_response = client.get(
        "/api/v1/live-sessions/selector-options",
        params={"anchor_key": fallback_options["轮班主播乙"]["anchor_key"]},
        headers=auth_headers,
    )
    assert selector_response.status_code == 200
    assert [item["id"] for item in selector_response.json()] == [fallback_sessions[1].id]


def test_public_selector_rejects_reversed_date_range(client, db, auth_headers):
    _seed_sessions(db)

    response = client.get(
        "/api/v1/live-sessions/selector-options",
        params={"start_date": "2026-08-30", "end_date": "2026-08-29"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "开始日期不能晚于结束日期" in response.text


def test_clip_candidates_reuse_anchor_and_date_filters(client, db, auth_headers):
    sessions = _seed_sessions(db)

    response = client.get(
        "/api/v1/clip/candidate-sessions",
        params={"anchor_key": "uid:uid-dan", "start_date": "2026-08-29", "end_date": "2026-08-29"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert [item["session_id"] for item in response.json()] == [sessions[1].id]


def test_knowledge_search_uses_explicit_session_boundary(db, client):
    sessions = _seed_sessions(db)
    for index, session in enumerate(sessions[:2]):
        db.add(
            KnowledgeTimeSlice(
                session_id=session.id,
                slice_index=0,
                slice_start_seconds=0,
                slice_end_seconds=300,
                anchor_name=session.anchor_name,
                session_title=session.session_title,
                transcript_text="选址预算避坑真实话术",
                search_text="选址预算避坑真实话术",
                source_hash=f"hash-{index}",
                parser_version="time-slice-v1",
            )
        )
    db.commit()

    results = search_time_slices(db, "选址预算", session_id=sessions[0].id)

    assert results
    assert {item["session_id"] for item in results} == {sessions[0].id}


def test_knowledge_conversation_persists_session_scope(client, db, auth_headers):
    session = _seed_sessions(db)[0]

    created = client.post(
        "/api/v1/ai/conversations",
        json={"title": "单场问答", "session_id": session.id},
        headers=auth_headers,
    )
    detail = client.get(
        f"/api/v1/ai/conversations/{created.json()['id']}",
        headers=auth_headers,
    )

    assert created.status_code == 200
    assert created.json()["session_id"] == session.id
    assert detail.status_code == 200
    assert detail.json()["session_id"] == session.id


def test_knowledge_qa_passes_explicit_session_to_retrieval(client, db, auth_headers, monkeypatch):
    session = _seed_sessions(db)[0]
    captured = {}

    def fake_qa_search(_db, **kwargs):
        captured.update(kwargs)
        return {"answer": "真实回答", "sources": [], "has_result": True}

    monkeypatch.setattr("app.api.v1.ai.qa_search", fake_qa_search)

    response = client.post(
        "/api/v1/ai/qa",
        json={"question": "这场有哪些避坑重点？", "session_id": session.id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert captured["session_id"] == session.id


def test_vector_search_passes_session_filter(monkeypatch):
    captured = {}

    class FakeClient:
        def search(self, **kwargs):
            captured.update(kwargs)
            return [
                SimpleNamespace(
                    id=7,
                    payload={"slice_id": 7, "session_id": 23, "anchor_name": "丹姐", "search_text": "避坑"},
                    score=0.9,
                )
            ]

    monkeypatch.setattr(vector_store, "get_client", lambda: FakeClient())

    results = vector_store.search_time_slice_vectors([0.1] * 512, session_id=23)

    assert results[0]["session_id"] == 23
    assert captured["query_filter"].must[0].match.value == 23
