/**
 * 主播话术页面 — 数据适配器
 *
 * 把原始 API 数据转换成前端展示需要的格式。
 * 所有函数都是纯函数，不依赖响应式状态。
 */
import { formatDate, formatDuration, getStatusLabel } from '@/utils/transcriptHelpers';
import type { SessionSelectorOption } from '@/adapters/session-selector-adapter';

// ========== 类型定义 ==========

/** 场次下拉选项（扩展 SelectOption，带主播头像信息） */
export type SessionSelectOption = SessionSelectorOption;

/** 话术分类统计项 */
export interface CategoryStat {
  name: string;
  count: number;
  percent: number;
  tone: 'info' | 'warning' | 'success' | 'error' | 'default';
}

/** 页面使用的可读话术片段：保留真实 ASR 字段，只增加规则标签。 */
export interface TranscriptSegmentView extends Api.Douyin.TranscriptSegment {
  contentCategory: string;
  categoryTone: CategoryStat['tone'];
  sourceLabel: string;
}

/** 任务状态卡片配置 */
export interface TaskStatusCard {
  status: string;
  label: string;
  value: number;
  icon: string;
  tone: 'info' | 'warning' | 'success' | 'error';
  /** 处理中任务里最快的进度百分比（0-100），仅 processing 卡片有意义 */
  maxProgress?: number;
}

// ========== 适配函数 ==========

/**
 * 计算话术分类统计（按真实文本的业务规则分组）
 * 把平铺的片段列表转成按分类汇总的结构，用于侧边栏展示
 */
export function buildCategoryStats(segments: TranscriptSegmentView[]): CategoryStat[] {
  const counts = new Map<string, number>();
  segments.forEach(item => {
    const category = item.contentCategory;
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({
      name,
      count,
      percent: segments.length ? (count / segments.length) * 100 : 0,
      tone: categoryTone(name)
    }))
    .sort((a, b) => b.count - a.count);
}

const CATEGORY_RULES: Array<{ name: string; words: string[] }> = [
  {
    name: '留资承接',
    words: ['联系方式', '手机号', '微信号', '小助理联系', '注意接听', '把电话', '把微信']
  },
  {
    name: '资料钩子',
    words: [
      '领取资料',
      '发资料',
      '资料免费',
      '免费送给你',
      '资料送给你',
      '找老师领',
      '怎么领',
      '避坑名单',
      '评估表',
      '计算表',
      '调研报告',
      '免费分析',
      '红色按钮',
      '弹窗',
      '后台私信'
    ]
  },
  {
    name: '互动引导',
    words: ['欢迎', '公屏', '扣个一', '扣1', '点点赞', '点关注', '还有什么问题', '打在评论区']
  },
  {
    name: '用户答疑',
    words: ['你问', '你这个问题', '老板你', '你在哪', '你的预算', '你准备', '你想开']
  },
  {
    name: '开店知识',
    words: ['零食店', '开店', '选址', '预算', '品牌', '加盟', '快招', '供应链', '货源', '毛利', '利润', '回本', '房租']
  }
];

function categoryTone(name: string): CategoryStat['tone'] {
  const tones: Record<string, CategoryStat['tone']> = {
    留资承接: 'success',
    资料钩子: 'warning',
    互动引导: 'info',
    用户答疑: 'info',
    开店知识: 'default',
    其他话术: 'default'
  };
  return tones[name] || 'default';
}

function classifyTranscriptContent(text: string): string {
  const normalized = text.replace(/\s+/g, '').toLowerCase();
  return CATEGORY_RULES.find(rule => rule.words.some(word => normalized.includes(word.toLowerCase())))?.name || '其他话术';
}

function normalizedTranscriptText(text: string): string {
  return text.replace(/[\s，。！？、：；,.!?:;“”'"（）()-]/g, '').toLowerCase();
}

/** 同场同时存在初稿和终稿时只返回一个可信版本，禁止跨版本重复统计。 */
export function selectTranscriptVersionSegments(
  segments: Api.Douyin.TranscriptSegment[]
): Api.Douyin.TranscriptSegment[] {
  const hasOfflineFinal = segments.some(item => item.segment_type === 'asr_offline');
  return hasOfflineFinal
    ? segments.filter(item => item.segment_type === 'asr_offline')
    : segments.filter(item => item.segment_type !== 'asr_offline_pending');
}

/**
 * 合并实时两遍识别产生的重复片段。
 * 只对实时初稿中时间区间重叠（或起点误差不超过 3 秒）的包含文本隐藏短片段；
 * 离线终稿和 45 秒内正常重复的 CTA 均保留，不改写真实原文。
 */
export function buildReadableSegments(segments: Api.Douyin.TranscriptSegment[]): TranscriptSegmentView[] {
  const sorted = [...segments].sort((a, b) => a.segment_start - b.segment_start || a.id - b.id);
  const normalized = sorted.map(item => normalizedTranscriptText(item.text_content));
  return sorted
    .filter((item, index) => {
      if (item.segment_type !== 'asr_realtime') return true;
      const text = normalized[index];
      if (text.length < 8) return true;
      return !sorted.some((other, otherIndex) => {
        if (index === otherIndex || other.segment_type !== 'asr_realtime') return false;
        const itemEnd = Math.max(item.segment_start, item.segment_end || item.segment_start);
        const otherEnd = Math.max(other.segment_start, other.segment_end || other.segment_start);
        const intervalsOverlap = Math.max(item.segment_start, other.segment_start) <= Math.min(itemEnd, otherEnd);
        const startsNear = Math.abs(other.segment_start - item.segment_start) <= 3;
        if (!intervalsOverlap && !startsNear) return false;
        const otherText = normalized[otherIndex];
        return otherText.length >= text.length + 8 && otherText.includes(text);
      });
    })
    .map(item => {
      const contentCategory = classifyTranscriptContent(item.text_content);
      return {
        ...item,
        contentCategory,
        categoryTone: categoryTone(contentCategory),
        sourceLabel: item.segment_type === 'asr_offline' ? '离线终稿' : '实时初稿'
      };
    });
}

/**
 * 构建任务状态卡片配置
 * 把任务汇总数字转成 4 张卡片需要的展示数据。
 * tasks 用于计算处理中任务的最快进度（显示在「正在转写」卡片上）。
 */
export function buildTaskStatusCards(
  taskSummary: Record<string, number>,
  tasks?: Api.Douyin.TranscriptTask[]
): TaskStatusCard[] {
  // 计算处理中任务的最快进度百分比
  const processingTasks = (tasks || []).filter(t => t.status === 'processing' && t.progress_percent > 0);
  const maxProgress = processingTasks.length
    ? Math.max(...processingTasks.map(t => t.progress_percent))
    : undefined;
  return [
    { status: 'queued', label: '等待转写', value: taskSummary.queued || 0, icon: 'mdi:clock-outline', tone: 'info' },
    { status: 'processing', label: '正在转写', value: taskSummary.processing || 0, icon: 'mdi:waveform', tone: 'warning', maxProgress },
    { status: 'completed', label: '转写完成', value: taskSummary.completed || 0, icon: 'mdi:check-circle-outline', tone: 'success' },
    {
      status: 'attention',
      label: '暂停或失败',
      value: taskSummary.needs_attention || 0,
      icon: 'mdi:alert-circle-outline',
      tone: 'error'
    }
  ];
}

/**
 * 构建场次下拉选项列表
 * 把场次列表 + 任务映射表合并成 NSelect 需要的选项格式
 */
export function buildSessionOptions(
  sessions: Api.Douyin.LiveSessionListItem[],
  taskBySession: Map<number, Api.Douyin.TranscriptTask>
): SessionSelectOption[] {
  return sessions.map(session => {
    const task = taskBySession.get(session.id);
    const date = session.live_start_time ? formatDate(session.live_start_time) : '时间未知';
    const metaLabel = `${date} · ${formatDuration(session.live_duration_seconds)} · ${getStatusLabel(task?.status)}`;
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
