/**
 * 知识库 — 数据适配器
 *
 * 职责：把 API 返回的原始数据转成 UI 需要的格式。
 * 所有字段映射和默认值逻辑集中在这里。
 */

/** 知识来源类型 → 中文标签 */
const SOURCE_TYPE_LABELS: Record<string, string> = {
  transcript: '话术',
  comments: '评论',
  metrics: '指标',
  knowledge: '知识',
  review: '复盘',
  live_session: '场次'
};

/** 获取来源类型的显示名称 */
export function getSourceTypeLabel(sourceType: string | null | undefined): string {
  if (!sourceType) return '未知';
  return SOURCE_TYPE_LABELS[sourceType] || sourceType;
}

/** 来源类型 → NaiveUI Tag 颜色 */
export function getSourceTypeColor(sourceType: string | null | undefined): 'success' | 'warning' | 'info' | 'default' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'default'> = {
    transcript: 'success',
    comments: 'warning',
    metrics: 'info',
    knowledge: 'default',
    review: 'default',
    live_session: 'info'
  };
  return sourceType ? (map[sourceType] || 'default') : 'default';
}
