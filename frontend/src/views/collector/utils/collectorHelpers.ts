/**
 * 采集页纯工具函数
 * 不依赖任何 Vue 组件状态，可在任何地方直接调用
 */

/** 把后端返回的时间字符串（可能带时区也可能不带）统一转成毫秒时间戳 */
export function parseBackendTime(value: string): number {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasTimezone ? value : `${value}Z`).getTime();
}

/** 格式化为完整中文日期时间（如 2026/7/21 14:30:00） */
export function formatFullTime(value: string | null): string {
  if (!value) return '-';
  return new Date(parseBackendTime(value)).toLocaleString('zh-CN', { hour12: false });
}

/**
 * 格式化为相对时间
 * 60 秒内 → "刚刚"
 * 60 分钟内 → "X 分钟前"
 * 超过 60 分钟 → "MM-DD HH:mm:ss"
 * @param value 后端时间字符串
 * @param now 当前毫秒时间戳（由父组件传入，驱动响应式更新）
 */
export function formatLogTime(value: string, now: number): string {
  const timestamp = parseBackendTime(value);
  if (!Number.isFinite(timestamp)) return value || '-';
  const diff = Math.max(0, now - timestamp);
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const date = new Date(timestamp);
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

/** 从采集日志中安全提取结构化 JSON 数据 */
export function getLogPayload(log: { raw_json?: unknown }): Record<string, unknown> {
  return log.raw_json && typeof log.raw_json === 'object' && !Array.isArray(log.raw_json)
    ? (log.raw_json as Record<string, unknown>)
    : {};
}

/** 把采集阶段英文 key 翻译成中文标签（用于进度展示） */
export function getStageLabel(stage: unknown): string {
  const labels: Record<string, string> = {
    prepare: '准备账号',
    login_check: '验证登录',
    room_collection: '房间采集',
    enterprise_sync: '主播同步',
    history_sync: '历史同步',
    detail_enrichment: '详情补齐',
    cookie_refresh: '保存登录态',
    dataease_sync: '同步 DataEase',
    asr_queue: '排队生成话术',
    post_collection: '话术/复盘入库',
    completed: '采集完成',
    failed: '采集失败'
  };
  return labels[String(stage || '')] || String(stage || '常规日志');
}

/**
 * 从日志的结构化数据中拼出可读摘要
 * 比如："主播 张三 · 房间 123456 · 指标 42 · 评论 89"
 */
export function getLogSummary(log: { raw_json?: unknown }): string {
  const payload = getLogPayload(log);
  const detailSource = payload.details;
  const details =
    detailSource && typeof detailSource === 'object' && !Array.isArray(detailSource)
      ? (detailSource as Record<string, unknown>)
      : payload;
  const parts = [
    details.anchor_name && `主播 ${details.anchor_name}`,
    details.room_id && `房间 ${details.room_id}`,
    details.metrics_count !== undefined && `指标 ${details.metrics_count}`,
    details.comments_count !== undefined && `评论 ${details.comments_count}`,
    details.profiles_count !== undefined && `画像 ${details.profiles_count}`,
    details.transcript_count !== undefined && `话术 ${details.transcript_count} 段`,
    details.review_finding_count !== undefined && `复盘 ${details.review_finding_count} 条`,
    payload.progress_percent !== undefined && `进度 ${payload.progress_percent}%`
  ].filter(Boolean);
  return parts.join(' · ') || '-';
}
