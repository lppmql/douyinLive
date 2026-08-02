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
    failed: '失败',
    cancelled: '已暂停'
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
    failed: 'error',
    cancelled: 'info'
  };
  return map[status] || 'default';
}

/** 后处理状态 → 展示文案 */
export function getPostprocessLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待复盘',
    processing: '复盘入库中',
    completed: '已复盘入库',
    failed: '复盘入库失败',
    skipped: '初稿无需复盘'
  };
  return map[status] || status;
}

/** 后处理状态 → NaiveUI Tag type */
export function getPostprocessType(status: string): 'info' | 'warning' | 'success' | 'error' {
  const map: Record<string, 'info' | 'warning' | 'success' | 'error'> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'error',
    skipped: 'info'
  };
  return map[status] || 'info';
}

export interface TranscriptFailureInfo {
  category: 'stream' | 'engine' | 'live-ended' | 'duration' | 'unknown';
  title: string;
  hint: string;
  actionLabel: string;
}

/** 将后端真实错误归纳为运营人员可以直接执行的恢复建议。 */
export function getTranscriptFailureInfo(errorMessage?: string | null): TranscriptFailureInfo {
  const message = (errorMessage || '').toLowerCase();
  if (
    ['404', '403', '410', 'input/output error', 'tls', '未输出任何音频帧', '流地址已失效'].some(marker =>
      message.includes(marker)
    )
  ) {
    return {
      category: 'stream',
      title: '直播回放地址已失效或读取中断',
      hint: '系统会重新进入大屏页面获取可用回放，并从失败分片继续，不会重跑已经完成的部分。',
      actionLabel: '刷新回放并断点续传'
    };
  }
  if (message.includes('直播音频缓存不完整') || message.includes('直播音频缓存等待超时')) {
    return {
      category: 'live-ended',
      title: '直播结束时实时缓存没有覆盖完整窗口',
      hint: '已有实时初稿会保留；下播回放生成后重新转写，即可补齐离线终稿。',
      actionLabel: '生成离线终稿'
    };
  }
  if (message.includes('funasr') || message.includes('容器') || message.includes('模型')) {
    return {
      category: 'engine',
      title: '话术识别服务暂时不可用',
      hint: '重新转写会自动检查并启动 FunASR；模型准备完成后任务继续执行。',
      actionLabel: '检查服务并重试'
    };
  }
  if (message.includes('完整度') || message.includes('直播时长仍在变化')) {
    return {
      category: 'duration',
      title: '场次时长仍在变化，终稿暂未收齐',
      hint: '请先刷新场次采集数据，确认下播时间后再从已有分片继续。',
      actionLabel: '重新检查并续传'
    };
  }
  return {
    category: 'unknown',
    title: '本场话术转写需要重新处理',
    hint: '系统会保留已完成片段，并从失败位置继续。若再次失败，可展开技术详情进一步排查。',
    actionLabel: '断点重试'
  };
}
