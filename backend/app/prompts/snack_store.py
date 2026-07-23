"""零食店开店避坑直播业务的默认用户提示词。"""

from app.prompts.registry import PromptDefinition


BUSINESS_CONTEXT = (
    "本项目复盘的是零食店开店避坑知识科普直播，不是零食带货直播。"
    "主播通过选址、预算、品牌、供应链、毛利损耗和证照等知识帮助准备开店的人，"
    "再用具体资料引导用户主动在抖音站内私信。"
)


DEFAULT_PROMPTS = (
    PromptDefinition(
        type="speech_score",
        name="零食店避坑科普话术评分",
        version=2,
        description="评价知识价值、问题互动、资料钩子和站内私信承接",
        content=BUSINESS_CONTEXT
        + """

带时间的话术：
{transcript}

请按0-10分评价完整性、互动性、知识价值、资料钩子、站内私信承接和亲和力。所有优缺点必须引用真实时间点；禁止建议抽奖、秒杀、虚假稀缺、收益保证、食品功效夸大或站外导流。按JSON返回各项评分、total_score、strengths、weaknesses、suggestions和evidence。""",
    ),
    PromptDefinition(
        type="trend_analysis",
        name="零食店科普直播跨场趋势",
        version=2,
        description="对比观看、停留、开店问题、私信和线索",
        content=BUSINESS_CONTEXT
        + """

真实场次：
{sessions_data}

区分真实零值和未采集，比较累计观看、峰值在线、平均停留、评论、私信、线索和关注。数据完整度或时长差异明显时不得直接判断主播优劣。按JSON返回summary、dimensions、best_evidence、risks和next_actions。""",
    ),
    PromptDefinition(
        type="anomaly_detection",
        name="零食店科普直播异常检测",
        version=2,
        description="检测留人、问题互动和站内私信异常",
        content=BUSINESS_CONTEXT
        + """

当前场次：{session_data}
历史场次：{history_data}

只依据输入检测在线骤降、问题评论减少、有观看但私信为0、关注或线索显著下降。按JSON返回anomaly_detected、anomalies、comparison和data_limitations。""",
    ),
    PromptDefinition(
        type="optimization",
        name="零食店避坑直播优化建议",
        version=2,
        description="从真实场次证据生成下一场可验证动作",
        content=BUSINESS_CONTEXT
        + """

真实场次：{session_data}
话术评分：{speech_data}

建议应围绕开场留人、具体知识、开店问题互动、资料钩子和站内私信承接。禁止抽奖、优惠券、虚假稀缺、收益保证和站外联系方式。按JSON返回summary、findings、suggestions、next_live_plan和compliance_notes。""",
    ),
    PromptDefinition(
        type="high_intent",
        name="零食店筹备意向识别",
        version=2,
        description="识别真实开店问题和资料领取意向",
        content=BUSINESS_CONTEXT
        + """

真实评论：
{comments}

只输出明确涉及城市选址、预算面积、租金转让费、品牌加盟、货源供应链、毛利损耗、证照或资料领取的评论。必须返回原评论comment_index，不得根据昵称猜测，不得编造联系方式。按JSON返回users数组。""",
    ),
    PromptDefinition(
        type="qa",
        name="零食店避坑复盘知识问答",
        version=2,
        description="仅依据真实场次知识库回答运营问题",
        content=BUSINESS_CONTEXT
        + """

知识库证据：{knowledge_context}
问题：{question}

优先从选址、预算、品牌、供应链、毛利损耗、证照、资料钩子和站内私信承接分析。数据不足时明确说明，不补写不存在的评论、话术、指标或用户。""",
    ),
)
