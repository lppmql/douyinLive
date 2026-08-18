"""话术关键词风险提示；只生成“涉嫌违规、待人工复核”，不替代合规结论。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.review import ComplianceRule


@dataclass(frozen=True, slots=True)
class ComplianceRuleSnapshot:
    """脱离 ORM 会话的规则快照，避免 Worker 每次提交后重复刷新规则。"""

    rule_code: str
    name: str
    category: str
    pattern: str
    severity: str
    guidance: str


def load_enabled_compliance_rules(db: Session) -> list[ComplianceRuleSnapshot]:
    """读取已启用规则并转为稳定快照，供长任务跨事务复用。"""
    rules = (
        db.query(ComplianceRule)
        .filter(ComplianceRule.enabled == 1)
        .order_by(
            ComplianceRule.rule_code.asc(),
            ComplianceRule.version.desc(),
            ComplianceRule.severity.desc(),
        )
        .all()
    )
    return [
        ComplianceRuleSnapshot(
            rule_code=rule.rule_code,
            name=rule.name,
            category=rule.category,
            pattern=rule.pattern or "",
            severity=rule.severity or "warning",
            guidance=rule.guidance or "",
        )
        for rule in rules
    ]


def match_compliance_text(
    text: str, rules: Iterable[ComplianceRule | ComplianceRuleSnapshot]
) -> list[dict[str, Any]]:
    """按规则关键词匹配话术，返回可追溯的人工复核提示。"""
    normalized = (text or "").casefold()
    if not normalized:
        return []

    hits: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for rule in rules:
        if rule.rule_code in seen_codes:
            continue
        keywords = [
            item.strip() for item in (rule.pattern or "").split("|") if item.strip()
        ]
        matched = next(
            (item for item in keywords if item.casefold() in normalized), None
        )
        if not matched:
            continue
        hits.append(
            {
                "rule_code": rule.rule_code,
                "name": rule.name,
                "category": rule.category,
                "matched_keyword": matched,
                "severity": rule.severity or "warning",
                "guidance": rule.guidance,
                "review_status": "suspected",
            }
        )
        seen_codes.add(rule.rule_code)
    return hits
