import { backendRequest } from '../request';

/**
 * 抖音留资直播数据分析系统 — API 接口
 */

const API_PREFIX = '/api/v1';

/* ---------- 直播场次 ---------- */

/** 获取直播场次列表 */
export function fetchLiveSessions() {
  return backendRequest<Api.Douyin.LiveSession[]>({ url: `${API_PREFIX}/live-sessions/`, params: { limit: 1000 } });
}

/** 获取直播场次详情 */
export function fetchLiveSessionDetail(id: number) {
  return backendRequest<Api.Douyin.LiveSession>({ url: `${API_PREFIX}/live-sessions/${id}` });
}

/** 获取单场直播的趋势、评论和流地址 */
export function fetchLiveSessionData(id: number) {
  return backendRequest<Api.Douyin.LiveSessionDetail>({ url: `${API_PREFIX}/live-sessions/${id}/details` });
}

/* ---------- 采集 ---------- */

/** 获取采集器状态 */
export function fetchCollectorStatus() {
  return backendRequest<Api.Douyin.CollectorStatus>({ url: `${API_PREFIX}/collector/status` });
}

/** 获取采集账号列表 */
export function fetchCollectorAccounts() {
  return backendRequest<Api.Douyin.CollectorAccount[]>({ url: `${API_PREFIX}/collector/accounts` });
}

/** 获取采集日志 */
export function fetchCollectorLogs(params?: { taskId?: number; level?: string; limit?: number }) {
  return backendRequest<Api.Douyin.CollectorLog[]>({ url: `${API_PREFIX}/collector/logs`, params });
}

/** 获取采集任务列表 */
export function fetchCollectorTasks(params?: { status?: string; taskType?: string }) {
  return backendRequest<Api.Douyin.CollectorTask[]>({ url: `${API_PREFIX}/collector/tasks`, params });
}

/** 启动扫码登录 */
export function startCollectorLogin() {
  return backendRequest<Api.Douyin.LoginStartResponse>({ url: `${API_PREFIX}/collector/accounts/login`, method: 'POST' });
}

/** 获取登录二维码 */
export function fetchLoginQR(taskId: number) {
  return backendRequest<{ qr_code_base64: string }>({ url: `${API_PREFIX}/collector/login-tasks/${taskId}/qr` });
}

/** 获取登录状态 */
export function fetchLoginStatus(taskId: number) {
  return backendRequest<Api.Douyin.LoginStatusResponse>({ url: `${API_PREFIX}/collector/login-tasks/${taskId}/status` });
}

/** 重新扫码登录 */
export function reCollectorLogin(accountId: number) {
  return backendRequest<Api.Douyin.LoginStartResponse>({ url: `${API_PREFIX}/collector/accounts/${accountId}/re-login`, method: 'POST' });
}

/** 删除采集账号 */
export function deleteCollectorAccount(accountId: number) {
  return backendRequest<void>({ url: `${API_PREFIX}/collector/accounts/${accountId}`, method: 'DELETE' });
}

/* ---------- 话术/ASR ---------- */

/** 获取话术分段列表 */
export function fetchTranscriptSegments(sessionId: number) {
  return backendRequest<Api.Douyin.TranscriptSegment[]>({ url: `${API_PREFIX}/transcripts/${sessionId}/segments` });
}

/** 获取完整话术文本 */
export function fetchTranscriptFullText(sessionId: number) {
  return backendRequest<Api.Douyin.TranscriptFullText>({ url: `${API_PREFIX}/transcripts/${sessionId}/full-text` });
}

export function queueTranscript(sessionId: number) {
  return backendRequest<{ task_id: number; status: string; created: boolean }>({
    url: `${API_PREFIX}/transcripts/${sessionId}/queue`,
    method: 'POST'
  });
}

/* ---------- AI 分析 ---------- */

/** 获取 AI 评分 */
export function fetchAnalysisScore(sessionId: number) {
  return backendRequest<Api.Douyin.AnalysisScore>({ url: `${API_PREFIX}/analysis/${sessionId}/score` });
}

/** 获取异常告警 */
export function fetchAnalysisAlerts(sessionId: number) {
  return backendRequest<Api.Douyin.AlertItem[]>({ url: `${API_PREFIX}/analysis/${sessionId}/alerts` });
}

export function runTranscriptAiPipeline(sessionId: number) {
  return backendRequest<{ status: string; transcript_saved: number; analysis_saved: number }>({
    url: `${API_PREFIX}/ai/pipeline/${sessionId}`,
    method: 'POST'
  });
}

/* ---------- 监控管理 ---------- */

/** 获取监控器状态 */
export function fetchMonitorStatus() {
  return backendRequest<Api.Douyin.MonitorStatus>({ url: `${API_PREFIX}/monitor/status` });
}

/** 启动监控 */
export function startMonitor() {
  return backendRequest<Api.Douyin.MonitorAction>({ url: `${API_PREFIX}/monitor/start`, method: 'POST' });
}

/** 停止监控 */
export function stopMonitor() {
  return backendRequest<Api.Douyin.MonitorAction>({ url: `${API_PREFIX}/monitor/stop`, method: 'POST' });
}

/** 获取已配置监控的房间列表 */
export function fetchMonitorRooms() {
  return backendRequest<Api.Douyin.MonitorRoom[]>({ url: `${API_PREFIX}/monitor/rooms` });
}

/** Mock 模式模拟开播 */
export function triggerMockLive() {
  return backendRequest<Api.Douyin.MonitorAction>({ url: `${API_PREFIX}/monitor/test/trigger-live`, method: 'POST' });
}

/** Mock 模式模拟下播 */
export function triggerMockEnd() {
  return backendRequest<Api.Douyin.MonitorAction>({ url: `${API_PREFIX}/monitor/test/trigger-end`, method: 'POST' });
}

/* ---------- 知识库 ---------- */

/** 获取知识库条目 */
export function fetchKnowledgeItems(params?: { category?: string }) {
  return backendRequest<Api.Douyin.KnowledgeItem[]>({ url: `${API_PREFIX}/knowledge-base/`, params });
}

/* ---------- 一键采集 ---------- */

/** 一键采集所有主播房间数据 */
export function collectAllData() {
  return backendRequest<Api.Douyin.CollectAllResponse>({ url: `${API_PREFIX}/collector/collect-all`, method: 'POST' });
}

/* ---------- AI 分析 ---------- */

/** 测试 DeepSeek 连通 */
export function testAiConnection() {
  return backendRequest<{ status: string; reply: string }>({ url: `${API_PREFIX}/ai/test`, method: 'POST' });
}

/** 话术评分 */
export function scoreSession(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({ url: `${API_PREFIX}/ai/score/${sessionId}`, method: 'POST' });
}

/** 趋势分析 */
export function trendAnalysis(sessionIds: number[]) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({ url: `${API_PREFIX}/ai/trend`, method: 'POST', params: { session_ids: sessionIds } });
}

/** 异常检测 */
export function detectAnomaly(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({ url: `${API_PREFIX}/ai/anomaly/${sessionId}`, method: 'POST' });
}

/** 优化建议 */
export function optimizeSession(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({ url: `${API_PREFIX}/ai/optimize/${sessionId}`, method: 'POST' });
}

/** 高意向用户识别 */
export function detectHighIntent(sessionId: number) {
  return backendRequest<{ status: string; count: number; users: unknown[] }>({ url: `${API_PREFIX}/ai/high-intent/${sessionId}`, method: 'POST' });
}

/** 知识问答 */
export function askKnowledge(question: string, category?: string) {
  return backendRequest<{ answer: string; sources: unknown[]; has_result: boolean }>({
    url: `${API_PREFIX}/ai/qa`,
    method: 'POST',
    data: { question, category }
  });
}

/** 保存到知识库 */
export function saveToKnowledgeBase(sessionId: number) {
  return backendRequest<{ status: string; transcript_saved: number; analysis_saved: number }>({ url: `${API_PREFIX}/ai/kb/save/${sessionId}`, method: 'POST' });
}

/** 获取提示词模板列表 */
export function fetchPrompts(type?: string) {
  return backendRequest<Api.Douyin.PromptTemplate[]>({ url: `${API_PREFIX}/ai/prompts/`, params: { type } });
}
