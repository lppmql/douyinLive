"""前端、API 与 DataEase 共用的指标定义。"""
from typing import Any


def _metric(
    key: str,
    name: str,
    description: str,
    dataset: str,
    expression: str,
    value_format: str = "integer",
    time_field: str = "platform_start_time",
    time_semantics: str = "优先使用抖音平台事件时间，不使用数据库创建时间作为业务统计时间",
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "description": description,
        "dataset": dataset,
        "expression": expression,
        "format": value_format,
        "time_field": time_field,
        "time_semantics": time_semantics,
    }


METRIC_DEFINITIONS = (
    _metric("total_viewers", "累计观看人数", "筛选范围内各直播场次累计观看人数之和", "de_v_fact_live_session", "SUM(total_viewers)"),
    _metric("peak_online_count", "峰值在线人数", "筛选范围内分钟或场次最高在线人数", "de_v_fact_live_session", "MAX(peak_online_count)"),
    _metric("avg_watch_seconds", "人均观看时长", "按累计观看人数加权的人均观看秒数", "de_v_fact_live_session", "SUM(avg_watch_seconds * total_viewers) / NULLIF(SUM(total_viewers), 0)", "duration"),
    _metric("comment_count", "评论总数", "真实采集评论记录数", "de_v_fact_comment", "COUNT(comment_id)"),
    _metric("unique_comment_users", "独立评论用户数", "按稳定用户标识去重的评论用户数", "de_v_fact_comment", "COUNT(DISTINCT user_key)"),
    _metric("high_intent_rate", "高意向用户率", "高意向独立评论用户数除以全部独立评论用户数", "de_v_fact_comment", "COUNT(DISTINCT CASE WHEN is_high_intent = 1 THEN user_key END) / NULLIF(COUNT(DISTINCT user_key), 0)", "percent", "platform_comment_time"),
    _metric("follow_conversion_rate", "关注转化率", "新增关注人数除以累计观看人数", "de_v_fact_live_session", "SUM(new_followers) / NULLIF(SUM(total_viewers), 0)", "percent"),
    _metric("lead_conversion_rate", "线索转化率", "留资人数除以累计观看人数", "de_v_fact_live_session", "SUM(leads_count) / NULLIF(SUM(total_viewers), 0)", "percent"),
    _metric("lead_cost", "线索成本", "广告消耗除以留资人数", "de_v_fact_live_session", "SUM(ad_cost) / NULLIF(SUM(leads_count), 0)", "currency"),
    _metric("private_message_count", "站内私信人数", "筛选范围内各场直播采集到的站内私信人数之和", "de_v_fact_live_session", "SUM(private_message_count)"),
    _metric("private_message_rate", "私信转化率", "站内私信人数除以累计观看人数", "de_v_fact_live_session", "SUM(private_message_count) / NULLIF(SUM(total_viewers), 0)", "percent"),
    _metric("high_intent_comment_count", "高意向评论数", "命中零食店筹备问题或资料领取意图的真实评论数", "de_v_fact_comment", "SUM(CASE WHEN is_high_intent = 1 THEN 1 ELSE 0 END)"),
    _metric("review_risk_count", "待复核风险数", "未关闭的直播复盘风险发现数量", "de_v_fact_review_finding", "SUM(CASE WHEN finding_type = 'risk' AND status IN ('open', 'confirmed') THEN 1 ELSE 0 END)", "integer", "platform_start_time"),
    _metric("review_action_completion_rate", "整改完成率", "已完成或已验证整改任务占全部整改任务的比例", "de_v_fact_review_action", "SUM(CASE WHEN status IN ('completed', 'verified') THEN 1 ELSE 0 END) / NULLIF(COUNT(action_id), 0)", "percent", "platform_start_time"),
    _metric("approved_script_asset_count", "已确认话术资产数", "从真实直播话术中人工确认可复用的片段数量", "de_v_fact_script_asset", "SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END)", "integer", "platform_start_time"),
    _metric("transcript_coverage_seconds", "话术覆盖时长", "完成转写片段的去重前累计秒数", "de_v_fact_transcript_segment", "SUM(GREATEST(segment_end - segment_start, 0))", "duration", "platform_start_time"),
    _metric("ai_call_success_rate", "AI调用成功率", "成功AI调用占全部AI调用的比例", "de_v_fact_ai_call_trace", "SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / NULLIF(COUNT(ai_call_id), 0)", "percent", "observed_at", "使用模型调用发生时的系统观测时间"),
    _metric("ai_call_avg_latency_ms", "AI平均耗时", "AI调用平均耗时毫秒数", "de_v_fact_ai_call_trace", "AVG(latency_ms)", "integer", "observed_at", "使用模型调用发生时的系统观测时间"),
    _metric("ai_total_tokens", "AI Token用量", "成功或失败调用返回的总Token数", "de_v_fact_ai_call_trace", "SUM(total_tokens)", "integer", "observed_at", "使用模型调用发生时的系统观测时间"),
)


SEMANTIC_DATASETS = (
    {"name": "主播维度", "view": "de_v_dim_anchor", "grain": "每位主播一行", "time_field": None},
    {"name": "日期维度", "view": "de_v_dim_date", "grain": "每个有直播的自然日一行", "time_field": "date_key"},
    {"name": "直播场次事实", "view": "de_v_fact_live_session", "grain": "每场直播一行", "time_field": "platform_start_time"},
    {"name": "分钟指标事实", "view": "de_v_fact_live_minute_metric", "grain": "每个真实指标采样点一行", "time_field": "platform_metric_time"},
    {"name": "评论事实", "view": "de_v_fact_comment", "grain": "每条真实评论一行", "time_field": "platform_comment_time"},
    {"name": "话术事实", "view": "de_v_fact_transcript_segment", "grain": "每个完成转写片段一行", "time_field": "segment_start"},
    {"name": "AI 分析事实", "view": "de_v_fact_ai_analysis", "grain": "每份分析报告一行", "time_field": "generated_at"},
    {"name": "复盘发现事实", "view": "de_v_fact_review_finding", "grain": "每条可追溯复盘发现一行", "time_field": "platform_start_time"},
    {"name": "整改任务事实", "view": "de_v_fact_review_action", "grain": "每个复盘整改任务一行", "time_field": "platform_start_time"},
    {"name": "话术资产事实", "view": "de_v_fact_script_asset", "grain": "每个真实直播话术资产一行", "time_field": "platform_start_time"},
    {"name": "AI 调用事实", "view": "de_v_fact_ai_call_trace", "grain": "每次AI模型调用一行，仅含脱敏元数据", "time_field": "observed_at"},
)
