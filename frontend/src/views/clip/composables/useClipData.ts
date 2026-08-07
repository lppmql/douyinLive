import { h, onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import { fetchGetUserInfo } from '@/service/api/auth';
import {
  approveClip,
  discardClip,
  fetchClipCandidateSessions,
  fetchClipSessionOverview,
  generateClipSession,
  regenerateClip
} from '@/service/api/douyin';
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';

/** 剪辑任务运行中的状态集合，用于驱动轮询 */
const RUNNING_STATUSES = new Set(['pending', 'running', 'queued', 'processing']);

/** 下拉选项：附带候选场次原始信息供富信息渲染 */
export interface SessionSelectOption extends SelectOption {
  raw?: Api.Douyin.ClipCandidateSession;
}

/** 成片视频播放地址（浏览器原生 video 标签经媒体 Cookie 鉴权） */
export function clipVideoUrl(clipId: number): string {
  return `/api/v1/clip/clips/${clipId}/video`;
}

export function clipCoverUrl(clipId: number): string {
  return `/api/v1/clip/clips/${clipId}/cover`;
}

/** 转写状态可读文案 */
export function transcriptStatusText(status: string): string {
  const map: Record<string, string> = {
    none: '无话术',
    processing: '转写中',
    partial: `部分完成`,
    completed: '话术完整'
  };
  return map[status] || status;
}

export function useClipData(message: ReturnType<typeof useMessage>) {
  const loading = ref(false);
  const overview = ref<Api.Douyin.ClipSessionOverview | null>(null);
  const sessionOptions = ref<SessionSelectOption[]>([]);
  const selectedSessionId = ref<number | null>(null);
  const actionLoading = ref(false);
  const errorMessage = ref('');

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let mountedFlag = false;
  let requestSeq = 0; // 请求序号：切换场次时丢弃过期响应，防止旧数据覆盖新场次

  /** 刷新浏览器媒体 Cookie（30 分钟短时效，播放视频前调用续期） */
  async function refreshMediaCookie() {
    try {
      await fetchGetUserInfo();
    } catch {
      // 续期失败不阻断：视频请求失败时页面会给出明确提示
    }
  }

  /** 下拉选项富信息渲染：主播、标题、时间、话术转写、成片情况 */
  function renderSessionOption(option: SessionSelectOption) {
    const raw = option.raw;
    const transcript = `${transcriptStatusText(raw?.transcript_status || 'none')}（${raw?.transcript_completed_count || 0}/${raw?.transcript_segment_count || 0}段）`;
    const clips = raw?.clip_available_count ? `已有${raw.clip_available_count}条成片` : '无成片';
    const start = raw?.live_start_time ? new Date(raw.live_start_time) : null;
    const timeText = start
      ? `${start.getMonth() + 1}/${start.getDate()} ${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')}`
      : '-';
    return h('div', { class: 'clip-page__option' }, [
      h(
        'div',
        { class: 'clip-page__option-main' },
        `#${raw?.session_id} ${raw?.anchor_name || ''} ${raw?.session_title || ''}`
      ),
      h('div', { class: 'clip-page__option-sub' }, `${timeText} · ${transcript} · ${clips}`)
    ]);
  }

  /** 场次下拉数据：可剪辑候选场次（含主播、话术、成片情况） */
  async function loadSessionOptions() {
    try {
      const data = unwrapServiceData(await fetchClipCandidateSessions(50), '候选场次加载失败');
      sessionOptions.value = (data || []).map(item => ({
        label: `#${item.session_id} ${item.anchor_name || ''} ${item.session_title || ''}`,
        value: item.session_id,
        raw: item,
        render: (option: SelectOption) => renderSessionOption(option as SessionSelectOption)
      }));
    } catch (error) {
      errorMessage.value = getServiceErrorMessage(error, '加载失败');
    }
  }

  /** 加载选中场次的剪辑总览 */
  async function loadOverview(sessionId?: number | null) {
    const target = sessionId ?? selectedSessionId.value;
    if (!target) {
      overview.value = null;
      return;
    }
    selectedSessionId.value = target;
    const seq = ++requestSeq;
    loading.value = true;
    try {
      const data = unwrapServiceData(await fetchClipSessionOverview(target), '剪辑总览加载失败');
      if (seq !== requestSeq) return; // 已有更新的请求，丢弃过期响应
      overview.value = data;
      errorMessage.value = '';
    } catch (error) {
      if (seq !== requestSeq) return;
      errorMessage.value = getServiceErrorMessage(error, '加载失败');
    } finally {
      if (seq === requestSeq) {
        loading.value = false;
      }
    }
  }

  function isTaskRunning(): boolean {
    const task = overview.value?.task;
    return Boolean(task && RUNNING_STATUSES.has(task.status));
  }

  function startPolling() {
    stopPolling();
    if (!isTaskRunning()) return;
    pollTimer = setInterval(() => {
      void loadOverview();
      // 任务结束后自动停止轮询，避免页面 keep-alive 期间持续空请求
      if (!isTaskRunning()) {
        stopPolling();
      }
    }, 5000);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  /** 整场生成 */
  async function generateAll(userHint?: string) {
    if (!selectedSessionId.value) return;
    actionLoading.value = true;
    try {
      const action = unwrapServiceData(
        await generateClipSession(selectedSessionId.value, userHint),
        '触发生成失败'
      );
      if (action.success) {
        message.success(action.message);
        await loadOverview();
        startPolling();
      } else {
        message.warning(action.message);
      }
    } catch (error) {
      message.error(getServiceErrorMessage(error, '操作失败'));
    } finally {
      actionLoading.value = false;
    }
  }

  /** 单条重剪 */
  async function regenerateOne(clipOrder: number, userHint?: string) {
    if (!selectedSessionId.value) return;
    actionLoading.value = true;
    try {
      const action = unwrapServiceData(
        await regenerateClip(selectedSessionId.value, clipOrder, userHint),
        '触发重剪失败'
      );
      if (action.success) {
        message.success(action.message);
        await loadOverview();
        startPolling();
      } else {
        message.warning(action.message);
      }
    } catch (error) {
      message.error(getServiceErrorMessage(error, '操作失败'));
    } finally {
      actionLoading.value = false;
    }
  }

  /** 确认成片 */
  async function approve(clipId: number) {
    try {
      const action = unwrapServiceData(await approveClip(clipId), '确认成片失败');
      message.success(action.message);
      await loadOverview();
    } catch (error) {
      message.error(getServiceErrorMessage(error, '操作失败'));
    }
  }

  /** 丢弃成片 */
  async function discard(clipId: number) {
    try {
      const action = unwrapServiceData(await discardClip(clipId), '丢弃成片失败');
      message.success(action.message);
      await loadOverview();
    } catch (error) {
      message.error(getServiceErrorMessage(error, '操作失败'));
    }
  }

  onMounted(() => {
    mountedFlag = true;
    void loadSessionOptions();
  });

  onActivated(() => {
    if (mountedFlag) {
      void loadSessionOptions();
      void loadOverview();
      startPolling();
    }
  });

  onDeactivated(() => {
    stopPolling();
  });

  onUnmounted(() => {
    stopPolling();
  });

  return {
    loading,
    overview,
    sessionOptions,
    selectedSessionId,
    actionLoading,
    errorMessage,
    loadSessionOptions,
    loadOverview,
    startPolling,
    stopPolling,
    generateAll,
    regenerateOne,
    approve,
    discard,
    isTaskRunning,
    refreshMediaCookie
  };
}
