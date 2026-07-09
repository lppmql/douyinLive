import { request } from '../request';

/**
 * 抖音留资直播数据分析系统 — API 接口
 *
 * @note Phase 2 使用 Mock 数据，API 函数已定义但暂不调用
 *       后续 Phase 对接后端时取消注释实际调用
 */

/* ---------- 直播场次 ---------- */

/** 获取直播场次列表 */
export function fetchLiveSessions() {
  return request<Api.Douyin.LiveSession[]>({ url: '/live/sessions' });
}

/** 获取直播场次详情 */
export function fetchLiveSessionDetail(id: number) {
  return request<Api.Douyin.LiveSession>({ url: `/live/sessions/${id}` });
}

/* ---------- 采集 ---------- */

/** 获取采集器状态 */
export function fetchCollectorStatus() {
  return request<Api.Douyin.CollectorStatus>({ url: '/collector/status' });
}

/** 获取采集账号列表 */
export function fetchCollectorAccounts() {
  return request<Api.Douyin.CollectorAccount[]>({ url: '/collector/accounts' });
}

/** 获取采集日志 */
export function fetchCollectorLogs() {
  return request<Api.Douyin.CollectorLog[]>({ url: '/collector/logs' });
}

/* ---------- 话术 ---------- */

/** 获取话术分段列表 */
export function fetchTranscriptSegments(sessionId: number) {
  return request<Api.Douyin.TranscriptSegment[]>({ url: `/transcripts/${sessionId}/segments` });
}

/* ---------- AI 分析 ---------- */

/** 获取 AI 评分 */
export function fetchAnalysisScore(sessionId: number) {
  return request<Api.Douyin.AnalysisScore>({ url: `/analysis/${sessionId}/score` });
}

/** 获取异常告警 */
export function fetchAnalysisAlerts(sessionId: number) {
  return request<Api.Douyin.AlertItem[]>({ url: `/analysis/${sessionId}/alerts` });
}

/* ---------- 知识库 ---------- */

/** 获取知识库条目 */
export function fetchKnowledgeItems(params?: { category?: string }) {
  return request<Api.Douyin.KnowledgeItem[]>({ url: '/knowledge/items', params });
}
