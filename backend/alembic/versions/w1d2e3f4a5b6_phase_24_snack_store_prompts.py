"""Snack-store education and private-message lead prompts.

Revision ID: w1d2e3f4a5b6
Revises: v1d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision = "w1d2e3f4a5b6"
down_revision = "v1d2e3f4a5b6"
branch_labels = None
depends_on = None


PROMPTS = [
    {
        "type": "speech_score",
        "name": "零食店避坑科普话术评分",
        "version": 2,
        "description": "评价知识价值、开场留人、问题诊断、资料钩子和站内私信承接",
        "content": """你是一位零食店开店避坑知识科普直播的复盘专家。业务目标不是直播卖零食，而是通过选址、预算、品牌、供应链、毛利、临期损耗和证照等知识，帮助准备开店的人避坑，并通过真实资料钩子引导用户主动在抖音站内私信。

带时间的话术：
{transcript}

请从以下维度评分（0-10）：
1. 完整性：开场主题、知识展开、案例或条件、问题互动、资料钩子、站内私信承接、阶段总结。
2. 互动性：是否询问城市、预算、面积、租金、竞品和经营阶段，并真正回应用户问题。
3. 留资引导：资料名称和适用对象是否具体，领取动作是否清晰，是否引导用户主动站内私信。
4. 亲和力：是否专业、克制、易懂，不制造焦虑，不贬损或承诺收益。
5. 知识价值：是否讲清判断条件、计算方法和风险边界，而非只报品牌结论。

禁止建议抽奖促单、虚假稀缺、保证赚钱、夸大食品功效或站外导流。优缺点必须引用真实时间点和话术原文。

按JSON返回：
{
  "completeness_score": 0,
  "interactivity_score": 0,
  "lead_guidance_score": 0,
  "affinity_score": 0,
  "knowledge_value_score": 0,
  "total_score": 0,
  "strengths": ["带时间证据的优点"],
  "weaknesses": ["带时间证据的不足"],
  "suggestions": ["下一场可执行改进"],
  "evidence": [{"start_seconds": 0, "category": "选址/预算/品牌/供应链/毛利损耗/资料钩子/私信承接", "quote": "真实短句"}]
}""",
    },
    {
        "type": "trend_analysis",
        "name": "零食店科普直播跨场趋势",
        "version": 2,
        "description": "对比观看、停留、评论、私信和线索，不以GMV为核心",
        "content": """你是零食店避坑知识科普直播的数据分析师。请对比以下真实场次：
{sessions_data}

重点分析累计观看、峰值在线、平均停留、评论、私信、线索和新增关注；区分数据为0与未采集。说明表现变化，但不要在场次时长或数据完整度差异明显时直接判断主播优劣。给出围绕知识主题、问题互动、资料钩子和站内私信承接的改进建议。按JSON返回summary、dimensions、best_evidence、risks、next_actions。""",
    },
    {
        "type": "anomaly_detection",
        "name": "零食店科普直播异常检测",
        "version": 2,
        "description": "检测留人、互动和私信转化异常",
        "content": """你是零食店避坑知识科普直播的异常分析师。
当前场次：{session_data}
历史场次：{history_data}

检测在线和停留异常、评论问题减少、已有流量但私信为0、关注或线索显著下降。只能依据提供的数据判断；历史也持续为0时应标记为长期转化缺口，而不是统计异常。按JSON返回anomaly_detected、anomalies、comparison和data_limitations。""",
    },
    {
        "type": "optimization",
        "name": "零食店避坑直播优化建议",
        "version": 2,
        "description": "基于真实场次、评论、话术和评分生成可执行建议",
        "content": """请复盘以下零食店开店避坑知识科普直播真实数据：
{session_data}

已有话术评分：
{speech_data}

目标是帮助准备开零食店的人理解选址、预算、品牌、供应链、毛利、临期损耗和证照风险，并通过具体资料（如选址检查表、预算测算表、品牌尽调清单）引导用户主动在抖音站内私信。不要建议抽奖、优惠券、秒杀、虚假稀缺、保证收益或站外联系方式。

按JSON返回：
{
  "summary": "基于真实证据的总结",
  "findings": [{"category": "留人/互动/内容/资料钩子/私信留资/合规", "title": "问题", "evidence": "真实指标、评论或话术", "start_seconds": 0, "severity": "info/warning/critical"}],
  "suggestions": ["下一场可直接执行的建议"],
  "next_live_plan": [{"stage": "开场/知识展开/问题诊断/资料钩子/私信承接/总结", "action": "动作", "success_metric": "可验证指标"}],
  "compliance_notes": ["需要人工复核的宣传或导流风险"]
}""",
    },
    {
        "type": "high_intent",
        "name": "零食店筹备意向识别",
        "version": 2,
        "description": "从真实评论识别开店筹备问题和资料领取意向",
        "content": """以下是零食店避坑知识科普直播的真实评论：
{comments}

只识别明确涉及选址、城市、预算、面积、租金转让费、品牌加盟、供应链货源、毛利损耗、证照或资料领取的用户。不得根据昵称猜测，不得编造手机号。intent_level规则：主动要资料或给出具体预算/面积/租金为high；提出明确开店问题为medium；泛聊为low且不要输出。

按JSON返回：
{"users": [{"comment_index": 1, "user_name": "必须与评论一致", "product_interest": "选址/预算/品牌/供应链/经营测算/证照/资料领取", "intent_level": "high/medium", "reason": "引用该条真实评论"}]}""",
    },
    {
        "type": "qa",
        "name": "零食店避坑复盘知识问答",
        "version": 2,
        "description": "基于真实场次证据回答运营问题",
        "content": """你是零食店避坑知识科普直播的运营复盘助手。请只根据以下知识库真实内容回答：
{knowledge_context}

问题：{question}

优先从选址、预算、品牌、供应链、毛利损耗、证照、资料钩子和站内私信承接角度分析。数据不足时明确说明，不补写不存在的评论、话术、指标或用户信息；回答中标注主播、场次和时间范围。""",
    },
]


def upgrade() -> None:
    table = sa.table(
        "prompt_templates",
        sa.column("type", sa.String),
        sa.column("name", sa.String),
        sa.column("content", sa.Text),
        sa.column("version", sa.Integer),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    now = datetime.utcnow()
    op.bulk_insert(table, [{**item, "created_at": now, "updated_at": now} for item in PROMPTS])


def downgrade() -> None:
    types = ", ".join(f"'{item['type']}'" for item in PROMPTS)
    op.execute(f"DELETE FROM prompt_templates WHERE version = 2 AND type IN ({types})")
