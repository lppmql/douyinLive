/**
 * 主播排班页面 — 纯工具函数
 *
 * 所有函数都不依赖响应式状态或外部 API，只做纯数据转换。
 * 子组件可直接导入使用，无需通过 props 传递。
 */
import dayjs from 'dayjs';
import { getLiveSessionAvatarUrl } from '@/service/api/douyin';

// ========== 状态映射表 ==========

/** 排班状态 → 展示文案 + NaiveUI Tag 颜色类型 */
export const statusMap: Record<
  Api.Douyin.AnchorScheduleStatus,
  { label: string; type: 'success' | 'warning' | 'error' | 'info' | 'default' }
> = {
  upcoming: { label: '未到时间', type: 'info' },
  live: { label: '直播中', type: 'success' },
  completed: { label: '已达标', type: 'success' },
  missing: { label: '缺少场次', type: 'error' },
  duration_short: { label: '时长不足', type: 'warning' },
  invalid: { label: '无效场次', type: 'error' },
  extra: { label: '加场', type: 'info' }
};

// ========== 格式化函数 ==========

/** 格式化时间字符串为 HH:mm（用于计划/实际开播时间展示） */
export function formatClock(value: string | null): string {
  return value ? dayjs(value).format('HH:mm') : '-';
}

/** 格式化秒数为 "X 分 Y 秒"（用于排班时长展示） */
export function formatDuration(seconds: number): string {
  if (!seconds) return '0 分钟';
  const totalSeconds = Math.max(Math.floor(seconds), 0);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return remainingSeconds ? `${minutes} 分 ${remainingSeconds} 秒` : `${minutes} 分钟`;
}

/** 获取主播头像 URL（通过场次 ID 间接获取） */
export function getAnchorAvatarUrl(anchor: Api.Douyin.AnchorScheduleAnchor | undefined): string | undefined {
  return anchor?.anchor_avatar_session_id ? getLiveSessionAvatarUrl(anchor.anchor_avatar_session_id) : undefined;
}

// ========== 缺场/无效/加场 摘要格式化 ==========

/** 格式化缺场摘要（卡片上用，只显示前 2 天） */
export function formatMissingSummary(anchor: Api.Douyin.AnchorScheduleAnchor): string {
  if (!anchor.missing_count) return '缺场：无';
  const visibleDates = anchor.missing_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.missing_by_date.length - 2;
  return `缺场：${visibleDates}${remaining > 0 ? ` 等 ${anchor.missing_by_date.length} 天` : ''}`;
}

/** 格式化缺场场次编号（tooltip 明细用） */
export function formatMissingSessions(sessionIndexes: number[]): string {
  return sessionIndexes.map(index => `第 ${index} 场`).join('、');
}

/** 格式化无效场次摘要（卡片上用，只显示前 2 天） */
export function formatInvalidSummary(anchor: Api.Douyin.AnchorScheduleAnchor): string {
  if (!anchor.invalid_count) return '无效：无';
  const visibleDates = anchor.invalid_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.invalid_by_date.length - 2;
  return `无效：${visibleDates}${remaining > 0 ? ` 等 ${anchor.invalid_by_date.length} 天` : ''}`;
}

/** 格式化单条无效场次明细（tooltip 明细用） */
export function formatInvalidSessions(item: Api.Douyin.AnchorScheduleAnchor['invalid_by_date'][number]): string {
  return item.session_ids
    .map((_, index) => {
      const startTime = item.live_start_times[index];
      const extraLabel = item.extra_flags[index] ? '加场 · ' : '';
      return `${extraLabel}${startTime ? dayjs(startTime).format('HH:mm') : '时间未知'} · ${formatDuration(item.durations_seconds[index] || 0)}`;
    })
    .join('；');
}

/** 格式化加场摘要（卡片上用，只显示前 2 天） */
export function formatExtraSummary(anchor: Api.Douyin.AnchorScheduleAnchor): string {
  if (!anchor.extra_count) return '加场：无';
  const visibleDates = anchor.extra_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.extra_by_date.length - 2;
  return `加场：${visibleDates}${remaining > 0 ? ` 等 ${anchor.extra_by_date.length} 天` : ''}`;
}

/** 格式化加场开播时间列表（tooltip 明细用） */
export function formatExtraStartTimes(liveStartTimes: string[]): string {
  return liveStartTimes.map(value => dayjs(value).format('HH:mm')).join('、');
}
