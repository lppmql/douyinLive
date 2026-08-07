import { onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import {
  approveClip,
  discardClip,
  fetchClipSessionOverview,
  fetchLiveSessionPage,
  generateClipSession,
  regenerateClip
} from '@/service/api/douyin';
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';

/** 剪辑任务运行中的状态集合，用于驱动轮询 */
const RUNNING_STATUSES = new Set(['pending', 'running', 'queued', 'processing']);

/** 成片视频播放地址（浏览器原生 video 标签经媒体 Cookie 鉴权） */
export function clipVideoUrl(clipId: number): string {
  return `/api/v1/clip/clips/${clipId}/video`;
}

export function clipCoverUrl(clipId: number): string {
  return `/api/v1/clip/clips/${clipId}/cover`;
}

export function useClipData(message: ReturnType<typeof useMessage>) {
  const loading = ref(false);
  const overview = ref<Api.Douyin.ClipSessionOverview | null>(null);
  const sessionOptions = ref<SelectOption[]>([]);
  const selectedSessionId = ref<number | null>(null);
  const actionLoading = ref(false);
  const errorMessage = ref('');

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let mountedFlag = false;
  let requestSeq = 0; // 请求序号：切换场次时丢弃过期响应，防止旧数据覆盖新场次

  /** 场次下拉数据：已结束且详情完整的场次 */
  async function loadSessionOptions() {
    try {
      const { data } = await fetchLiveSessionPage({ current: 1, size: 50 });
      sessionOptions.value = ((data as Api.Common.PaginatingQueryRecord<Api.Douyin.LiveSessionListItem>)?.records || []).map(item => ({
        label: `#${item.id} ${item.session_title || item.anchor_name || '未知场次'}${item.live_start_time ? `（${item.live_start_time.slice(0, 10)}）` : ''}`,
        value: item.id
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
    isTaskRunning
  };
}
