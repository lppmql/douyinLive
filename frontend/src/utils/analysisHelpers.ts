import type { TagProps } from 'naive-ui';

/**
 * AI 复盘页面工具函数
 *
 * 把格式化、判定、元数据查询等纯函数从组件中抽出来，
 * 让组件只关心渲染，不关心"怎么算"。
 */

// ========== 数据安全工具 ==========

/** 安全地从 unknown 值中提取字符串数组（过滤空字符串） */
export function toStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : [];
}

/** 安全地从 unknown 值中提取有限数字，非数字返回 0 */
export function toNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

// ========== 格式化工具 ==========

/** 格式化为短日期时间（MM/DD HH:mm），供下拉选项显示 */
export function formatShortDateTime(value: string | null): string {
  if (!value) return '时间未知';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/** 格式化为完整日期时间（含年/秒），供报告时间显示 */
export function formatFullDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

/** 秒数 → "X小时X分" 或 "X分钟" */
export function formatDuration(seconds: number): string {
  if (!seconds) return '时长未知';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}小时${minutes}分` : `${minutes}分钟`;
}

/** 数字加千分位逗号（中文格式） */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value || 0);
}

// ========== 排序工具 ==========

/** 把日期字符串安全转为毫秒时间戳 */
export function toSessionTimestamp(value: string | null): number {
  const timestamp = value ? Date.parse(value) : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

/** 按开播时间倒序排列场次（最新的在前），时间相同时按 ID 倒序 */
export function sortSessionsByLatest<T extends { live_start_time: string | null; id: number }>(
  items: T[]
): T[] {
  return [...items].sort((a, b) => {
    const timeDiff = toSessionTimestamp(b.live_start_time) - toSessionTimestamp(a.live_start_time);
    return timeDiff || b.id - a.id;
  });
}

// ========== 评分计算工具 ==========

/** 计算百分比（0~100），防止除零 */
export function scorePercent(value: number, max: number): number {
  return Math.min(100, Math.max(0, (value / max) * 100));
}

/** 根据得分百分比返回 NaiveUI 进度条状态 */
export function scoreStatus(value: number, max: number): 'success' | 'warning' | 'error' | 'default' {
  const pct = scorePercent(value, max);
  if (pct >= 80) return 'success';
  if (pct < 50) return 'error';
  if (pct < 70) return 'warning';
  return 'default';
}

/** 综合评分 → 文字评级 */
export function scoreLevel(totalScore: number | undefined): string {
  if (typeof totalScore !== 'number') return '待生成';
  if (totalScore >= 40) return '表现优秀';
  if (totalScore >= 30) return '基础可用';
  if (totalScore >= 20) return '需要优化';
  return '优先整改';
}

// ========== 复盘判定工具 ==========

/** 数据可信度 → Tag 颜色 */
export function readinessTagType(score: number | undefined): TagProps['type'] {
  const s = score ?? 0;
  if (s >= 85) return 'success';
  if (s >= 60) return 'warning';
  return 'error';
}

/** 复盘发现严重程度 → Tag 颜色 */
export function findingTagType(severity: string): TagProps['type'] {
  if (severity === 'critical') return 'error';
  if (severity === 'warning') return 'warning';
  return 'info';
}

/** 复盘发现严重程度 → 中文标签 */
export function findingLabel(severity: string): string {
  const labels: Record<string, string> = {
    critical: '重点风险',
    warning: '需要关注',
    info: '运营观察'
  };
  return labels[severity] || '运营观察';
}

// ========== 报告元数据 ==========

/** 报告类型 → 显示标签、Tag 颜色、图标 */
export function reportTypeMeta(reportType: string): {
  label: string;
  tag: TagProps['type'];
  icon: string;
} {
  const mapping: Record<string, { label: string; tag: TagProps['type']; icon: string }> = {
    speech_score: { label: '话术评分', tag: 'success', icon: 'mdi:chart-box-outline' },
    optimization: { label: '优化建议', tag: 'info', icon: 'mdi:lightbulb-on-outline' },
    anomaly: { label: '异常检测', tag: 'warning', icon: 'mdi:alert-decagram-outline' },
    trend: { label: '趋势分析', tag: 'default', icon: 'mdi:chart-timeline-variant' }
  };
  return mapping[reportType] || { label: reportType, tag: 'default', icon: 'mdi:file-document-outline' };
}

/** 生成报告摘要文本（评分报告显示"综合得分 X/50"，其他类型取 summary 字段） */
export function reportSummary(report: { report_type: string; report_content?: Record<string, unknown> | null; summary?: string | null }): string {
  if (report.report_type === 'speech_score') {
    const total = report.report_content?.total_score;
    return typeof total === 'number' ? `综合得分 ${total}/50` : report.summary || '评分报告已保存';
  }
  const summary = report.report_content?.summary;
  return (
    (typeof summary === 'string' && summary.trim()) || report.summary || '报告内容已保存，可重新生成获得最新结论。'
  );
}

/** 当前操作阶段 → 进度提示文字 */
export function actionStageLabel(stage: string): string {
  const labels: Record<string, string> = {
    evidence: '正在提取真实证据与运营发现…',
    score: '正在评价知识价值、互动和私信承接…',
    optimize: '正在生成下一场可验证动作…',
    'score-only': '正在重新计算话术评分…',
    'optimize-only': '正在更新优化建议…'
  };
  return labels[stage] || '';
}
