/**
 * 主播话术页面 — 数据适配器
 *
 * 把原始 API 数据转换成前端展示需要的格式。
 * 所有函数都是纯函数，不依赖响应式状态。
 */
import type { SelectOption } from 'naive-ui';
import { getLiveSessionAvatarUrl } from '@/service/api/douyin';
import { formatDate, formatDuration, getStatusLabel } from '@/utils/transcriptHelpers';

// ========== 类型定义 ==========

/** 场次下拉选项（扩展 SelectOption，带主播头像信息） */
export interface SessionSelectOption extends SelectOption {
  anchorName: string;
  avatarUrl: string | null;
}

/** 话术分类统计项 */
export interface CategoryStat {
  name: string;
  count: number;
  percent: number;
}

/** 任务状态卡片配置 */
export interface TaskStatusCard {
  status: string;
  label: string;
  value: number;
  icon: string;
  tone: 'info' | 'warning' | 'success' | 'error';
}

// ========== 适配函数 ==========

/**
 * 计算话术分类统计（按 segment_type 分组）
 * 把平铺的片段列表转成按分类汇总的结构，用于侧边栏展示
 */
export function buildCategoryStats(segments: Api.Douyin.TranscriptSegment[]): CategoryStat[] {
  const counts = new Map<string, number>();
  segments.forEach(item => {
    const category = item.segment_type || '未分类';
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({
      name,
      count,
      percent: segments.length ? (count / segments.length) * 100 : 0
    }))
    .sort((a, b) => b.count - a.count);
}

/**
 * 构建任务状态卡片配置
 * 把任务汇总数字转成 4 张卡片需要的展示数据
 */
export function buildTaskStatusCards(taskSummary: Record<string, number>): TaskStatusCard[] {
  return [
    { status: 'queued', label: '等待转写', value: taskSummary.queued || 0, icon: 'mdi:clock-outline', tone: 'info' },
    { status: 'processing', label: '正在转写', value: taskSummary.processing || 0, icon: 'mdi:waveform', tone: 'warning' },
    { status: 'completed', label: '转写完成', value: taskSummary.completed || 0, icon: 'mdi:check-circle-outline', tone: 'success' },
    { status: 'failed', label: '需要处理', value: taskSummary.failed || 0, icon: 'mdi:alert-circle-outline', tone: 'error' }
  ];
}

/**
 * 构建场次下拉选项列表
 * 把场次列表 + 任务映射表合并成 NSelect 需要的选项格式
 */
export function buildSessionOptions(
  sessions: Api.Douyin.LiveSession[],
  taskBySession: Map<number, Api.Douyin.TranscriptTask>
): SessionSelectOption[] {
  return sessions.map(session => {
    const task = taskBySession.get(session.id);
    const date = session.live_start_time ? formatDate(session.live_start_time) : '时间未知';
    return {
      value: session.id,
      label: `${session.anchor_name || '未知主播'} · ${date} · ${formatDuration(session.live_duration_seconds)} · ${getStatusLabel(task?.status)}`,
      anchorName: session.anchor_name || '未知主播',
      avatarUrl: session.anchor_avatar_url ? getLiveSessionAvatarUrl(session.id) : null
    };
  });
}
