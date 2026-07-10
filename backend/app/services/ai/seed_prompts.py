"""初始化 AI 提示词模板（首次运行时执行）"""
from sqlalchemy.orm import Session
from app.models.prompt_templates import PromptTemplate

INITIAL_PROMPTS = [
    {
        "type": "speech_score",
        "name": "话术评分",
        "version": 1,
        "description": "对主播话术进行多维度评分：完整性、互动性、留资引导能力",
        "content": """你是一位专业的直播话术分析师。请对以下主播话术进行评分。

话术内容：
{transcript}

请从以下维度评分（满分10分）：
1. 完整性（开头引入-产品讲解-互动引导-收尾）：结构是否完整，逻辑是否清晰
2. 互动性：是否主动引导观众互动（提问、扣屏、点赞等）
3. 留资引导：是否有效引导观众留资（明确引导语、福利诱惑、紧迫感等）
4. 亲和力：语气是否亲切、专业、有说服力

请按以下 JSON 格式回复：
{
  "completeness_score": 0-10,
  "interactivity_score": 0-10,
  "lead_guidance_score": 0-10,
  "affinity_score": 0-10,
  "total_score": 平均分,
  "strengths": ["优点1", "优点2"],
  "weaknesses": ["不足1", "不足2"],
  "suggestions": ["改进建议1", "改进建议2"]
}"""
    },
    {
        "type": "trend_analysis",
        "name": "趋势分析",
        "version": 1,
        "description": "多场直播数据对比分析",
        "content": """你是一位直播运营数据分析师。请对比分析以下多场直播数据。

直播场次数据：
{sessions_data}

请分析：
1. 整体趋势：关键指标（留资数、在线人数、互动率等）的变化趋势
2. 高/低效场次特征：表现最好和最差的场次有什么特征
3. 改进方向：基于数据趋势给出优化建议

请按 JSON 格式回复。"""
    },
    {
        "type": "anomaly_detection",
        "name": "异常检测",
        "version": 1,
        "description": "检测直播数据中的异常：流量突降、互动骤减、留资归零等",
        "content": """你是一位直播数据异常检测分析师。请分析以下直播数据是否存在异常。

直播场次数据：
{session_data}

历史对比数据：
{history_data}

检测以下异常：
1. 流量异常：在线人数是否出现异常波动或骤降
2. 互动异常：评论、点赞等互动数据是否骤减
3. 留资异常：留资数是否归零或大幅下降
4. 转化异常：各转化环节是否有异常偏低

请按 JSON 格式回复。"""
    },
    {
        "type": "optimization",
        "name": "优化建议",
        "version": 1,
        "description": "针对单场直播生成可操作的优化建议",
        "content": """你是一位直播运营专家。请根据以下直播数据给出优化建议。

直播场次数据：
{session_data}

话术评分数据：
{speech_data}

请从以下维度给出建议：
1. 话术优化：话术结构和内容的改进方向
2. 流量优化：提升曝光和进入的策略
3. 互动优化：提升互动率的技巧
4. 转化优化：提升留资转化率的具体方法

请按 JSON 格式回复。"""
    },
    {
        "type": "high_intent",
        "name": "高意向用户识别",
        "version": 1,
        "description": "从评论中识别高意向用户",
        "content": """你是一位直播销售分析师。请从以下评论中识别高意向用户。

评论列表：
{comments}

高意向用户特征：
- 明确询问产品价格、规格、购买方式
- 表示有购买需求或意向
- 询问优惠、活动、赠品
- 留下联系方式或询问联系方式的

请识别出高意向用户及其意向产品/服务，按 JSON 格式回复。"""
    },
    {
        "type": "qa",
        "name": "知识问答",
        "version": 1,
        "description": "基于知识库内容回答用户问题",
        "content": """你是一位直播数据分析助手。请基于以下知识库内容回答用户问题。

知识库相关内容：
{knowledge_context}

用户问题：
{question}

请基于提供的知识库内容回答。如果知识库中没有相关信息，请如实告知。回复中请标注引用来源。"""
    },
]


def seed_prompts(db: Session):
    """初始化提示词模板（仅当数据库为空时）"""
    existing = db.query(PromptTemplate).first()
    if existing:
        return

    for p in INITIAL_PROMPTS:
        db.add(PromptTemplate(**p))
    db.commit()
    print(f"✅ 已初始化 {len(INITIAL_PROMPTS)} 条提示词模板")
