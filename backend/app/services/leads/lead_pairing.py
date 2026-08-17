"""把同主播一分钟内分离记录配成一条确认客资。"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models.comment_user_profiles import CommentUserProfile
from app.models.comments import Comment
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.leads import Lead
from app.models.live_sessions import LiveSession


PAIR_WINDOW_SECONDS = 60


def normalize_anchor(value: str | None) -> str:
    """主播维度仅忽略空白和大小写，不做首字等宽松猜测。"""
    return re.sub(r"\s+", "", value or "").casefold()


def normalize_douyin_id(value: str | None) -> str:
    """只去除空白和@并忽略大小写，用于公开抖音号完全一致匹配。"""
    return re.sub(r"[\s@]", "", value or "").casefold()


def contact_type(value: str | None) -> str | None:
    """只接受明确的大陆手机号或微信号，屏蔽号和异常文本不计留资。"""
    text = (value or "").strip()
    if not text:
        return None
    compact = re.sub(r"[\s+-]", "", text)
    if compact.startswith("86") and len(compact) == 13:
        compact = compact[2:]
    if re.fullmatch(r"1[3-9]\d{9}", compact):
        return "phone"
    if re.fullmatch(r"[A-Za-z][-_A-Za-z0-9]{5,19}", text):
        return "wechat"
    if re.search(r"(?:微信\s*[:：]?|\b(?:vx|wx|v)\s*[:：])\s*[A-Za-z][-_A-Za-z0-9]{5,19}", text, re.IGNORECASE):
        return "wechat"
    return None


@dataclass(frozen=True)
class PairCandidate:
    douyin_lead: Lead
    contact_lead: Lead
    gap_seconds: int


def _build_candidates(leads: list[Lead]) -> list[PairCandidate]:
    """按主播生成一对一配对：先最大化对数，再最小化总时间差。"""
    groups: dict[str, list[Lead]] = defaultdict(list)
    for lead in leads:
        anchor_key = normalize_anchor(lead.anchor_name)
        if anchor_key and lead.create_time:
            groups[anchor_key].append(lead)

    result: list[PairCandidate] = []
    for rows in groups.values():
        direct = [row for row in rows if (row.douyin_id or "").strip() and contact_type(row.lead_phone)]
        used_douyin: set[int] = set()
        used_contact: set[int] = set()
        for row in direct:
            result.append(PairCandidate(row, row, 0))
            used_douyin.add(int(row.id))
            used_contact.add(int(row.id))

        douyin_rows = sorted(
            (row for row in rows if (row.douyin_id or "").strip() and int(row.id) not in used_douyin),
            key=lambda row: (row.create_time, int(row.id)),
        )
        contact_rows = sorted(
            (row for row in rows if contact_type(row.lead_phone) and int(row.id) not in used_contact),
            key=lambda row: (row.create_time, int(row.id)),
        )
        # 时间轴上的最小费用最大匹配。actions 仅保存回溯方向，
        # 分数用滚动数组，避免保存两张完整整数矩阵。
        previous = [(0, 0)] * (len(contact_rows) + 1)
        actions = [bytearray(len(contact_rows) + 1) for _ in range(len(douyin_rows) + 1)]
        for i, douyin in enumerate(douyin_rows, start=1):
            current = [(0, 0)] * (len(contact_rows) + 1)
            actions[i][0] = 1
            for j, contact in enumerate(contact_rows, start=1):
                best = previous[j]
                action = 1  # 跳过当前抖音号记录
                if current[j - 1][0] > best[0] or (
                    current[j - 1][0] == best[0] and current[j - 1][1] < best[1]
                ):
                    best = current[j - 1]
                    action = 2  # 跳过当前联系方式记录
                gap = abs(int((douyin.create_time - contact.create_time).total_seconds()))
                if gap <= PAIR_WINDOW_SECONDS:
                    paired = (previous[j - 1][0] + 1, previous[j - 1][1] + gap)
                    if paired[0] > best[0] or (paired[0] == best[0] and paired[1] < best[1]):
                        best = paired
                        action = 3
                current[j] = best
                actions[i][j] = action
            previous = current
        i, j = len(douyin_rows), len(contact_rows)
        matched: list[PairCandidate] = []
        while i and j:
            action = actions[i][j]
            if action == 3:
                douyin = douyin_rows[i - 1]
                contact = contact_rows[j - 1]
                gap = abs(int((douyin.create_time - contact.create_time).total_seconds()))
                matched.append(PairCandidate(douyin, contact, gap))
                i -= 1
                j -= 1
            elif action == 2:
                j -= 1
            else:
                i -= 1
        result.extend(reversed(matched))
    return result


def _comment_session_index(db: Session) -> dict[str, list[LiveSession]]:
    """把评论公开抖音号映射到真实出现过的场次，不使用昵称或 sec_uid 猜测。"""
    profile_ids: dict[str, set[str]] = defaultdict(set)
    for profile in db.query(CommentUserProfile).all():
        for value in (profile.public_douyin_id, profile.unique_id, profile.short_id):
            normalized = normalize_douyin_id(value)
            if normalized:
                profile_ids[profile.sec_uid].add(normalized)
    result: dict[str, list[LiveSession]] = defaultdict(list)
    rows = (
        db.query(Comment, LiveSession)
        .join(LiveSession, LiveSession.id == Comment.session_id)
        .all()
    )
    for comment, session in rows:
        ids = set(profile_ids.get(comment.user_sec_uid or "", set()))
        normalized_comment_id = normalize_douyin_id(comment.user_douyin_id)
        if normalized_comment_id:
            ids.add(normalized_comment_id)
        for douyin_id in ids:
            if all(existing.id != session.id for existing in result[douyin_id]):
                result[douyin_id].append(session)
    return result


def comment_session_ids_for_douyin(db: Session, douyin_id: str | None) -> set[int]:
    """返回该公开抖音号在评论中真实出现过的场次 ID。"""
    normalized = normalize_douyin_id(douyin_id)
    if not normalized:
        return set()
    return {int(session.id) for session in _comment_session_index(db).get(normalized, [])}


def _pair_session(candidate: PairCandidate, index: dict[str, list[LiveSession]]) -> tuple[int | None, str]:
    """优先由客户抖音号出现过的评论场次归属，再回退原始记录已有场次。"""
    pair_time = max(candidate.douyin_lead.create_time, candidate.contact_lead.create_time)
    anchor_key = normalize_anchor(candidate.douyin_lead.anchor_name or candidate.contact_lead.anchor_name)
    matched_sessions = []
    for session in index.get(normalize_douyin_id(candidate.douyin_lead.douyin_id), []):
        session_anchor_keys = {
            normalize_anchor(session.anchor_name),
            normalize_anchor(session.anchor_nickname),
        } - {""}
        if anchor_key and anchor_key not in session_anchor_keys:
            continue
        if not session.live_start_time:
            continue
        end_time = session.live_end_time or session.live_start_time
        if session.live_start_time <= pair_time <= end_time:
            distance = 0
        elif pair_time > end_time:
            distance = int((pair_time - end_time).total_seconds())
        else:
            distance = int((session.live_start_time - pair_time).total_seconds())
        # 私信留资可能略晚于下播，最多允许一小时；开播前只允许30分钟。
        if (pair_time >= end_time and distance <= 3600) or (pair_time < session.live_start_time and distance <= 1800) or distance == 0:
            matched_sessions.append((distance, session.id))
    if matched_sessions:
        matched_sessions.sort()
        return matched_sessions[0][1], "douyin_comment_session"
    douyin_session_id = candidate.douyin_lead.session_id
    contact_session_id = candidate.contact_lead.session_id
    # 只信任两条原始记录共同确认的旧归属；单边或冲突时保持未归属。
    if douyin_session_id and douyin_session_id == contact_session_id:
        return douyin_session_id, "confirmed_record_session"
    return None, "anchor_60s_pair"


def rebuild_lead_conversion_pairs(db: Session) -> dict[str, int]:
    """从真实原始记录重建派生配对，并同步所有受影响场次的确认客资数。"""
    leads = (
        db.query(Lead)
        .filter(Lead.is_valid == 1)
        .order_by(Lead.create_time.asc(), Lead.id.asc())
        .all()
    )
    existing_pairs = db.query(LeadConversionPair).all()
    lead_by_id = {int(lead.id): lead for lead in leads}
    manual_pairs = [
        pair
        for pair in existing_pairs
        if pair.attribution_method == "manual" and pair.session_id
    ]
    locked_douyin_ids = {int(pair.douyin_lead_id) for pair in manual_pairs}
    locked_contact_ids = {int(pair.contact_lead_id) for pair in manual_pairs}
    candidates = [
        candidate
        for candidate in _build_candidates(leads)
        if int(candidate.douyin_lead.id) not in locked_douyin_ids
        and int(candidate.contact_lead.id) not in locked_contact_ids
    ]
    # 人工确认同时锁定原始记录的一对一关系，增量数据不能把其中一边重新配走。
    for pair in manual_pairs:
        douyin_lead = lead_by_id.get(int(pair.douyin_lead_id))
        contact_lead = lead_by_id.get(int(pair.contact_lead_id))
        if douyin_lead and contact_lead:
            candidates.append(PairCandidate(douyin_lead, contact_lead, pair.gap_seconds))
    comment_session_index = _comment_session_index(db)
    existing_by_source = {
        (int(pair.douyin_lead_id), int(pair.contact_lead_id)): pair for pair in existing_pairs
    }
    old_session_ids = {pair.session_id for pair in existing_pairs if pair.session_id is not None}
    desired_sources = {
        (int(candidate.douyin_lead.id), int(candidate.contact_lead.id)) for candidate in candidates
    }
    for source_key, pair in list(existing_by_source.items()):
        if source_key not in desired_sources:
            db.delete(pair)
            existing_by_source.pop(source_key)
    # 先释放旧的单边唯一键，再插入因时间调整而改变的配对。
    db.flush()
    new_session_ids: set[int] = set()
    attributed_count = 0
    phone_count = 0
    wechat_count = 0
    for candidate in candidates:
        douyin_value = (candidate.douyin_lead.douyin_id or "").strip()
        contact_value = (candidate.contact_lead.lead_phone or "").strip()
        kind = contact_type(contact_value)
        if not douyin_value or not contact_value or not kind:
            continue
        source_key = (int(candidate.douyin_lead.id), int(candidate.contact_lead.id))
        pair = existing_by_source.get(source_key)
        session_id, attribution_method = _pair_session(candidate, comment_session_index)
        # 人工确认是最高优先级事实；后续增量同步和重建不能覆盖或清空。
        if pair and pair.attribution_method == "manual" and pair.session_id:
            session_id = int(pair.session_id)
            attribution_method = "manual"
        if session_id:
            new_session_ids.add(session_id)
            attributed_count += 1
        if kind == "phone":
            phone_count += 1
        else:
            wechat_count += 1
        if pair is None:
            pair = LeadConversionPair(
                douyin_lead_id=candidate.douyin_lead.id,
                contact_lead_id=candidate.contact_lead.id,
            )
            db.add(pair)
        pair.session_id = session_id
        pair.anchor_name = (candidate.douyin_lead.anchor_name or candidate.contact_lead.anchor_name or "").strip()
        pair.douyin_id = douyin_value
        pair.contact_type = kind
        pair.contact_value = contact_value
        pair.douyin_recorded_at = candidate.douyin_lead.create_time
        pair.contact_recorded_at = candidate.contact_lead.create_time
        pair.converted_at = max(candidate.douyin_lead.create_time, candidate.contact_lead.create_time)
        pair.gap_seconds = candidate.gap_seconds
        pair.attribution_status = "attributed" if session_id else "paired"
        pair.attribution_method = attribution_method
    db.flush()
    for session_id in old_session_ids | new_session_ids:
        session = db.get(LiveSession, session_id)
        if session:
            session.leads_count = (
                db.query(LeadConversionPair.id)
                .filter(LeadConversionPair.session_id == session_id)
                .count()
            )
    return {
        "pair_count": len(candidates),
        "attributed_count": attributed_count,
        "phone_count": phone_count,
        "wechat_count": wechat_count,
    }
