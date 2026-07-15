import { backendRequest } from '../request';
import { getServiceBaseURL } from '@/utils/service';

/**
 * 抖音留资直播数据分析系统 — API 接口
 */

const API_PREFIX = '/api/v1';

/* ---------- 仪表盘 ---------- */

export function fetchDashboardSummary() {
  return backendRequest<Api.Douyin.DashboardSummary>({ url: `${API_PREFIX}/dashboard/summary` });
}

/* ---------- 直播场次 ---------- */

/** 获取直播场次列表 */
export function fetchLiveSessions() {
  return backendRequest<Api.Douyin.LiveSession[]>({ url: `${API_PREFIX}/live-sessions/`, params: { limit: 1000 } });
}

export function fetchLiveSessionPage(params: {
  current: number;
  size: number;
  anchor_name?: string;
  live_status?: string;
  detail_status?: string;
}) {
  return backendRequest<Api.Common.PaginatingQueryRecord<Api.Douyin.LiveSession>>({
    url: `${API_PREFIX}/live-sessions/page`,
    params
  });
}

/** 获取直播场次详情 */
export function fetchLiveSessionDetail(id: number) {
  return backendRequest<Api.Douyin.LiveSession>({ url: `${API_PREFIX}/live-sessions/${id}` });
}

/** 获取单场直播的趋势、评论和流地址 */
export function fetchLiveSessionData(id: number) {
  return backendRequest<Api.Douyin.LiveSessionDetail>({ url: `${API_PREFIX}/live-sessions/${id}/details` });
}

/** 获取低开销封装 MP4 的下载地址，开发环境自动复用 Vite 后端代理 */
export function getLiveSessionVideoDownloadUrl(id: number) {
  const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
  const { otherBaseURL } = getServiceBaseURL(import.meta.env, isHttpProxy);
  const backendBaseUrl = otherBaseURL.backend || window.location.origin;
  return `${backendBaseUrl}${API_PREFIX}/live-sessions/${id}/video`;
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
  return backendRequest<Api.Douyin.LoginStartResponse>({
    url: `${API_PREFIX}/collector/accounts/login`,
    method: 'POST'
  });
}

/** 获取登录二维码 */
export function fetchLoginQR(taskId: number) {
  return backendRequest<{ qr_code_base64: string }>({ url: `${API_PREFIX}/collector/login-tasks/${taskId}/qr` });
}

/** 获取登录状态 */
export function fetchLoginStatus(taskId: number) {
  return backendRequest<Api.Douyin.LoginStatusResponse>({
    url: `${API_PREFIX}/collector/login-tasks/${taskId}/status`
  });
}

/** 重新扫码登录 */
export function reCollectorLogin(accountId: number) {
  return backendRequest<Api.Douyin.LoginStartResponse>({
    url: `${API_PREFIX}/collector/accounts/${accountId}/re-login`,
    method: 'POST'
  });
}

/** 删除采集账号 */
export function deleteCollectorAccount(accountId: number) {
  return backendRequest<void>({ url: `${API_PREFIX}/collector/accounts/${accountId}`, method: 'DELETE' });
}

/** 静默检查账号 Cookie 存活状态 */
export function checkCollectorAccountHealth(accountId: number) {
  return backendRequest<Api.Douyin.AccountHealthResponse>({
    url: `${API_PREFIX}/collector/accounts/${accountId}/health`,
    method: 'POST'
  });
}

/** 获取 ASR 模型与 Worker 的真实运行状态 */
export function fetchAsrControlStatus() {
  return backendRequest<Api.Douyin.AsrControlStatus>({ url: `${API_PREFIX}/collector/asr-control` });
}

/** 按需启停 ASR，关闭时释放模型内存 */
export function setAsrControl(enabled: boolean) {
  return backendRequest<Api.Douyin.AsrControlStatus>({
    url: `${API_PREFIX}/collector/asr-control/${enabled}`,
    method: 'POST'
  });
}

/** 获取 DataEase 宽表同步覆盖情况 */
export function fetchDataEaseStatus() {
  return backendRequest<Api.Douyin.DataEaseStatus>({ url: `${API_PREFIX}/dataease/status` });
}

/** 增量同步缺失或已过期的 DataEase 数据 */
export function syncDataEase(limit = 100) {
  return backendRequest<Api.Douyin.DataEaseSyncResult>({
    url: `${API_PREFIX}/dataease/sync`,
    method: 'POST',
    params: { limit }
  });
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

export function queueTranscriptsByAnchor(perAnchor = 1) {
  return backendRequest<{
    anchor_count: number;
    selected_count: number;
    created_count: number;
    tasks: Array<{ anchor_name: string; session_id: number; task_id: number; status: string; created: boolean }>;
  }>({
    url: `${API_PREFIX}/transcripts/batch/queue-by-anchor`,
    method: 'POST',
    params: { per_anchor: perAnchor }
  });
}

export function fetchTranscriptTaskStatus() {
  return backendRequest<Record<'queued' | 'processing' | 'completed' | 'failed', number>>({
    url: `${API_PREFIX}/transcripts/tasks/status`
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
  return backendRequest<Api.Douyin.KnowledgeSyncResult & { result: Record<string, unknown> }>({
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

/** 获取知识时间片覆盖状态 */
export function fetchKnowledgeTimeSliceStatus() {
  return backendRequest<Api.Douyin.KnowledgeTimeSliceStatus>({
    url: `${API_PREFIX}/knowledge-base/time-slices/status`
  });
}

/** 获取最近知识时间片 */
export function fetchKnowledgeTimeSlices(params?: { session_id?: number; limit?: number }) {
  return backendRequest<Api.Douyin.KnowledgeTimeSlice[]>({
    url: `${API_PREFIX}/knowledge-base/time-slices`,
    params
  });
}

/* ---------- 刷新数据采集 ---------- */

/** 刷新全部主播、直播场次及场次详情数据 */
export function collectAllData() {
  return backendRequest<Api.Douyin.CollectAllResponse>({
    url: `${API_PREFIX}/collector/collect-all`,
    method: 'POST',
    timeout: 30 * 60 * 1000
  });
}

/* ---------- AI 分析 ---------- */

/** 测试 DeepSeek 连通 */
export function testAiConnection() {
  return backendRequest<{ status: string; reply: string }>({ url: `${API_PREFIX}/ai/test`, method: 'POST' });
}

/** 话术评分 */
export function scoreSession(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({
    url: `${API_PREFIX}/ai/score/${sessionId}`,
    method: 'POST'
  });
}

/** 趋势分析 */
export function trendAnalysis(sessionIds: number[]) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({
    url: `${API_PREFIX}/ai/trend`,
    method: 'POST',
    params: { session_ids: sessionIds }
  });
}

/** 异常检测 */
export function detectAnomaly(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({
    url: `${API_PREFIX}/ai/anomaly/${sessionId}`,
    method: 'POST'
  });
}

/** 优化建议 */
export function optimizeSession(sessionId: number) {
  return backendRequest<{ status: string; result: Record<string, unknown> }>({
    url: `${API_PREFIX}/ai/optimize/${sessionId}`,
    method: 'POST'
  });
}

/** 高意向用户识别 */
export function detectHighIntent(sessionId: number) {
  return backendRequest<{ status: string; count: number; users: unknown[] }>({
    url: `${API_PREFIX}/ai/high-intent/${sessionId}`,
    method: 'POST'
  });
}

/** 知识问答 */
export function askKnowledge(question: string, category?: string) {
  return backendRequest<{ answer: string; sources: Api.Douyin.KnowledgeSource[]; has_result: boolean }>({
    url: `${API_PREFIX}/ai/qa`,
    method: 'POST',
    data: { question, category }
  });
}

/** 保存到知识库 */
export function saveToKnowledgeBase(sessionId: number) {
  return backendRequest<Api.Douyin.KnowledgeSyncResult>({
    url: `${API_PREFIX}/ai/kb/save/${sessionId}`,
    method: 'POST'
  });
}

/** 增量同步最近场次的数据、评论、话术和分析到知识库 */
export function syncRecentKnowledge(limit = 20) {
  return backendRequest<Api.Douyin.KnowledgeSyncResult & { session_count: number }>({
    url: `${API_PREFIX}/ai/kb/sync/recent`,
    method: 'POST',
    params: { limit }
  });
}

/** 获取提示词模板列表 */
export function fetchPrompts(type?: string) {
  return backendRequest<Api.Douyin.PromptTemplate[]>({ url: `${API_PREFIX}/ai/prompts/`, params: { type } });
}
