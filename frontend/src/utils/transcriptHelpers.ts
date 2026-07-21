/**
 * 主播话术页面 — 纯工具函数
 *
 * 所有函数都不依赖响应式状态或外部 API，只做纯数据转换。
 * 子组件可直接导入使用，无需通过 props 传递。
 */

/** 格式化秒数为 MM:SS 或 H:MM:SS（用于时间轴展示） */
export function formatTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = Math.floor(seconds % 60);
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

/** 格式化秒数为 "X.X小时" 或 "X分钟"（用于概览展示） */
export function formatDuration(seconds: number): string {
  if (!seconds) return '时长未知';
  return seconds >= 3600 ? `${(seconds / 3600).toFixed(1)}小时` : `${Math.round(seconds / 60)}分钟`;
}

/** 格式化日期字符串为 "MM-DD HH:mm" */
export function formatDate(value: string | null): string {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/** 转写任务/片段状态 → 展示文案 */
export function getStatusLabel(status?: string): string {
  if (!status) return '未转写';
  const map: Record<string, string> = {
    queued: '等待中',
    pending: '待处理',
    processing: '转写中',
    completed: '已完成',
    failed: '失败'
  };
  return map[status] || status;
}

/** 转写任务/片段状态 → NaiveUI Tag type */
export function getStatusType(status?: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (!status) return 'default';
  const map: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
    queued: 'info',
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'error'
  };
  return map[status] || 'default';
}

/** 后处理状态 → 展示文案 */
export function getPostprocessLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待复盘',
    processing: '复盘入库中',
    completed: '已复盘入库',
    failed: '复盘入库失败'
  };
  return map[status] || status;
}

/** 后处理状态 → NaiveUI Tag type */
export function getPostprocessType(status: string): 'info' | 'warning' | 'success' | 'error' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'error'> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'error'
  };
  return map[status] || 'info';
}
