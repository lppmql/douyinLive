/** 公共场次选择器的数据适配器。 */
import type { SelectOption } from 'naive-ui';
import { formatDuration, formatShortDateTime } from '@/utils/analysisHelpers';

export interface SessionSelectorOption extends SelectOption {
  sessionId: number;
  anchorName: string;
  anchorNickname: string | null;
  douyinId: string | null;
  avatarUrl: string | null;
  metaLabel: string;
}

export interface AnchorSelectorOption extends SelectOption {
  anchorKey: string;
  sessionId: number;
  anchorName: string;
  anchorNickname: string | null;
  douyinId: string | null;
  avatarUrl: string | null;
}

export type SessionDateRange = [number, number] | null;

/** 将公共场次接口转换成统一下拉选项；页面可覆盖右侧业务状态文字。 */
export function buildCommonSessionOptions(
  sessions: Api.Douyin.LiveSessionListItem[],
  metaBuilder?: (session: Api.Douyin.LiveSessionListItem) => string
): SessionSelectorOption[] {
  return sessions.map(session => {
    const metaLabel = metaBuilder
      ? metaBuilder(session)
      : `${formatShortDateTime(session.live_start_time)} · ${formatDuration(session.live_duration_seconds)} · ${session.live_status === 'live' ? '直播中' : '已结束'}`;
    return {
      value: session.id,
      label: `${session.anchor_name || '未知主播'} · ${session.douyin_id || '未获取抖音号'} · ${metaLabel}`,
      sessionId: session.id,
      anchorName: session.anchor_name || '未知主播',
      anchorNickname: session.anchor_nickname,
      douyinId: session.douyin_id,
      avatarUrl: session.anchor_avatar_url,
      metaLabel
    };
  });
}

export function buildAnchorSelectorOptions(
  anchors: Api.Douyin.LiveSessionAnchorOption[]
): AnchorSelectorOption[] {
  return anchors.map(anchor => ({
    value: anchor.anchor_key,
    label: `${anchor.anchor_name}${anchor.douyin_id ? ` · ${anchor.douyin_id}` : ''}`,
    anchorKey: anchor.anchor_key,
    sessionId: anchor.latest_session_id,
    anchorName: anchor.anchor_name,
    anchorNickname: anchor.anchor_nickname,
    douyinId: anchor.douyin_id,
    avatarUrl: anchor.anchor_avatar_url
  }));
}

/**
 * 日期控件的时间戳表示“用户在日历上点中的日期”，不是一个需要换算时区的时刻。
 * 因此读取控件所在浏览器的年月日，并把这个日历日期交给后端按北京时间边界查询。
 */
export function formatSelectorDate(timestamp: number): string {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** 获取当前北京时间对应的日历日期，并转换成日期控件可显示的本地午夜时间戳。 */
export function getShanghaiTodayCalendarTimestamp(now = new Date()): number {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return new Date(Number(values.year), Number(values.month) - 1, Number(values.day)).getTime();
}

/** 按日历日加减，避免夏令时地区用固定 24 小时偏移造成错日。 */
export function shiftSelectorCalendarDate(timestamp: number, days: number): number {
  const date = new Date(timestamp);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days).getTime();
}

export function buildSelectorDateParams(dateRange: SessionDateRange) {
  return dateRange
    ? { start_date: formatSelectorDate(dateRange[0]), end_date: formatSelectorDate(dateRange[1]) }
    : {};
}
