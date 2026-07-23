/** 把后端结构化日志转换成业务人员能直接阅读的数据详情。 */

export interface CollectorLogDetailEntry {
  key: string;
  label: string;
  value: string;
}

const detailLabels: Record<string, string> = {
  progress_percent: '任务进度',
  progress_current: '当前完成',
  progress_total: '任务总量',
  collected_anchor_count: '已采集主播',
  collected_session_count: '已发现直播场次',
  new_session_count: '新增场次',
  mapped_session_count: '更新主播映射场次',
  checked_detail_count: '已检查场次详情',
  refreshed_detail_count: '已补齐场次详情',
  failed_detail_count: '详情失败场次',
  remaining_detail_count: '待补齐场次',
  anchor_count: '主播数量',
  anchor_name: '主播名称',
  anchor_nickname: '主播昵称',
  anchor_profile_synced_count: '已同步主播资料',
  enterprise_anchor_count: '发现主播',
  discovered_session_count: '发现直播场次',
  enterprise_session_discovered_count: '发现直播场次',
  enterprise_session_synced_count: '同步企业场次',
  session_count: '同步场次',
  checked_count: '已检查详情',
  enriched_count: '已补齐详情',
  failed_count: '失败数量',
  remaining_count: '剩余数量',
  metrics_count: '分钟指标',
  comments_count: '直播评论',
  comment_count: '评论数量',
  lead_count: '留资数量',
  profiles_count: '观众画像',
  profile_count: '更新主播资料',
  transcript_count: '话术片段',
  finding_count: 'AI 复盘发现',
  review_finding_count: 'AI 复盘发现',
  saved_item_count: '知识条目',
  synced_count: 'DataEase 已同步场次',
  dataease_synced: '是否已同步 DataEase',
  dataease_status: 'DataEase 状态',
  dataease_failed_count: 'DataEase 失败场次',
  dataease_synced_count: 'DataEase 成功场次',
  selected_count: '本次选择场次',
  warning_count: '警告数量',
  error: '错误原因',
  errors: '失败明细',
  warnings: '注意事项',
  message: '说明',
  room_id: '直播房间 ID',
  room_name: '直播间名称',
  session_id: '场次 ID',
  douyin_id: '抖音号',
  is_live: '是否正在直播',
  stream_saved: '直播流是否保存',
  duration_seconds: '直播时长（秒）',
  score_generated: '是否生成评分',
  speech_score: '话术评分结果',
  speech_score_status: '话术评分状态',
  knowledge: '知识库处理结果',
  review_saved: '复盘是否保存',
  analysis_saved: 'AI 分析是否保存',
  comments_saved: '评论知识是否保存',
  live_data_saved: '直播数据知识是否保存',
  transcript_saved: '话术知识是否保存',
  time_slices_total: '知识时间片总数',
  time_slices_created: '新增知识时间片',
  time_slices_updated: '更新知识时间片',
  time_slices_unchanged: '未变化知识时间片',
  unmapped_comments: '未匹配时间的评论',
  total_rooms: '配置直播间',
  collected_rooms: '采集成功直播间',
  history_synced_count: '历史同步场次',
  history_detail_batch_size: '详情处理批次',
  history_detail_checked_count: '历史详情已检查',
  history_detail_synced_count: '历史详情已补齐',
  history_detail_failed_count: '历史详情失败',
  history_detail_remaining_count: '历史详情待补齐',
  unmapped_session_pruned_count: '清理未匹配场次',
  asr_active_count: 'ASR 活跃任务',
  asr_queued_count: 'ASR 新增排队',
  asr_queue_capacity: 'ASR 队列容量',
  postprocess_pending_count: '旧后处理等待数量',
  postprocess_processing_count: '旧后处理进行数量',
  postprocess_completed_count: '旧后处理完成数量',
  postprocess_failed_count: '旧后处理失败数量',
  batch_size: '本批场次',
  concurrency: '采集并发数',
  success: '是否成功',
  pending: '等待数量',
  pending_count: '待处理数量',
  processing: '处理中数量',
  completed: '完成数量',
  failed: '失败数量',
  results: '逐场结果',
  removed_stale_row_count: '清理旧数据行',
  created_count: '新增数量',
  updated_count: '更新数量'
};

function humanizeKey(key: string): string {
  const parts = key.split('.').filter(Boolean);
  const leaf = parts.at(-1) || key;
  const label = detailLabels[leaf] || leaf.replaceAll('_', ' ');
  const item = parts.find(part => part.startsWith('第 '));
  return item ? `${item} / ${label}` : label;
}

function formatScalar(value: unknown, key: string): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (key.endsWith('percent')) return `${value}%`;
  if (typeof value === 'number') return value.toLocaleString('zh-CN');
  return String(value);
}

function flattenDetails(
  value: unknown,
  path: string,
  result: CollectorLogDetailEntry[],
  depth = 0
): void {
  if (result.length >= 80) return;
  if (Array.isArray(value)) {
    if (!value.length) {
      result.push({ key: path, label: humanizeKey(path), value: '无' });
      return;
    }
    if (value.every(item => item === null || ['string', 'number', 'boolean'].includes(typeof item))) {
      result.push({ key: path, label: humanizeKey(path), value: value.map(item => formatScalar(item, path)).join('、') });
      return;
    }
    value.forEach((item, index) => flattenDetails(item, `${path}.第 ${index + 1} 项`, result, depth + 1));
    return;
  }
  if (value && typeof value === 'object' && depth < 4) {
    Object.entries(value as Record<string, unknown>).forEach(([key, child]) => {
      flattenDetails(child, path ? `${path}.${key}` : key, result, depth + 1);
    });
    return;
  }
  result.push({ key: path, label: humanizeKey(path), value: formatScalar(value, path) });
}

export function getCollectorLogDetailEntries(log: Api.Douyin.CollectorLog | null): CollectorLogDetailEntry[] {
  if (!log) return [];
  const result: CollectorLogDetailEntry[] = [];
  flattenDetails(log.data_details || {}, '', result);
  return result.filter(item => item.key);
}

export function getCollectorLogDetailPreview(log: Api.Douyin.CollectorLog): string {
  const entries = getCollectorLogDetailEntries(log).filter(item => item.value !== '-');
  if (!entries.length) return '暂无额外数据';
  const preview = entries.slice(0, 4).map(item => `${item.label} ${item.value}`).join(' · ');
  return entries.length > 4 ? `${preview} · 另有 ${entries.length - 4} 项` : preview;
}
