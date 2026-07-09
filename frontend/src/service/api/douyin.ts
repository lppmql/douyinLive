import { request } from '../request';

/**
 * 抖音留资直播数据分析系统 — API 接口
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
export function fetchCollectorLogs(params?: { taskId?: number; level?: string; limit?: number }) {
  return request<Api.Douyin.CollectorLog[]>({ url: '/collector/logs', params });
}

/** 获取采集任务列表 */
export function fetchCollectorTasks(params?: { status?: string; taskType?: string }) {
  return request<Api.Douyin.CollectorTask[]>({ url: '/collector/tasks', params });
}

/** 启动扫码登录 */
export function startCollectorLogin() {
  return request<Api.Douyin.LoginStartResponse>({ url: '/collector/accounts/login', method: 'POST' });
}

/** 获取登录二维码 */
export function fetchLoginQR(taskId: number) {
  return request<{ qr_code_base64: string }>({ url: `/collector/login-tasks/${taskId}/qr` });
}

/** 获取登录状态 */
export function fetchLoginStatus(taskId: number) {
  return request<Api.Douyin.LoginStatusResponse>({ url: `/collector/login-tasks/${taskId}/status` });
}

/** 重新扫码登录 */
export function reCollectorLogin(accountId: number) {
  return request<Api.Douyin.LoginStartResponse>({ url: `/collector/accounts/${accountId}/re-login`, method: 'POST' });
}

/** 删除采集账号 */
export function deleteCollectorAccount(accountId: number) {
  return request<void>({ url: `/collector/accounts/${accountId}`, method: 'DELETE' });
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

/* ---------- 监控管理 ---------- */

/** 获取监控器状态 */
export function fetchMonitorStatus() {
  return request<Api.Douyin.MonitorStatus>({ url: '/monitor/status' });
}

/** 启动监控 */
export function startMonitor() {
  return request<Api.Douyin.MonitorAction>({ url: '/monitor/start', method: 'POST' });
}

/** 停止监控 */
export function stopMonitor() {
  return request<Api.Douyin.MonitorAction>({ url: '/monitor/stop', method: 'POST' });
}

/** 获取已配置监控的房间列表 */
export function fetchMonitorRooms() {
  return request<Api.Douyin.MonitorRoom[]>({ url: '/monitor/rooms' });
}

/** Mock 模式模拟开播 */
export function triggerMockLive() {
  return request<Api.Douyin.MonitorAction>({ url: '/monitor/test/trigger-live', method: 'POST' });
}

/** Mock 模式模拟下播 */
export function triggerMockEnd() {
  return request<Api.Douyin.MonitorAction>({ url: '/monitor/test/trigger-end', method: 'POST' });
}

/* ---------- 知识库 ---------- */

/** 获取知识库条目 */
export function fetchKnowledgeItems(params?: { category?: string }) {
  return request<Api.Douyin.KnowledgeItem[]>({ url: '/knowledge/items', params });
}
