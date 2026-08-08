import { h, onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import { fetchGetUserInfo } from '@/service/api/auth';
import {
  approveClip,
  discardClip,
  fetchClipCandidateSessions,
  fetchClipSessionOverview,
  fetchLiveSessionPage,
  generateClipSession,
  regenerateClip,
  rerenderClipSubtitle
} from '@/service/api/douyin';
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';

/** 剪辑任务运行中的状态集合，用于驱动轮询 */
const RUNNING_STATUSES = new Set(['pending', 'running', 'queued', 'processing']);

/**
 * 成片媒体地址（浏览器原生 video/img 标签经媒体 Cookie 鉴权）。
 * - dev（VITE_HTTP_PROXY=Y）：必须带 /proxy-default 前缀，vite 代理才转发到后端，
 *   裸 /api 路径在 dev server 上 404（这是此前页面视频无法播放的根因）；
 * - 生产：走同源 /api 相对路径（nginx 已代理 /api 到后端），
 *   跨域绝对地址会导致浏览器 video 不带媒体 Cookie 而 401。
 */
const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
const mediaApiPrefix = isHttpProxy ? '/proxy-default' : '';

/** 下拉选项：与主播话术工作台同款结构（主播身份字段 + 富信息 raw） */
export interface SessionSelectOption extends SelectOption {
  sessionId: number;
  anchorName: string;
  anchorNickname: string | null;
  douyinId: string | null;
  avatarUrl: string | null;
  raw?: Api.Douyin.ClipCandidateSession;
}

export function clipVideoUrl(clipId: number): string {
  return `${mediaApiPrefix}/api/v1/clip/clips/${clipId}/video`;
}

export function clipCoverUrl(clipId: number): string {
  return `${mediaApiPrefix}/api/v1/clip/clips/${clipId}/cover`;
}

export function clipSubtitleSrtUrl(clipId: number): string {
  return `${mediaApiPrefix}/api/v1/clip/clips/${clipId}/subtitle.srt`;
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
  const route = useRoute();
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

  /** 下拉选项渲染（与主播话术工作台同款公共模式：主播头像 + 元信息） */
  function renderSessionLabel(option: SelectOption) {
    const sessionOption = option as SessionSelectOption;
    const raw = sessionOption.raw;
    const transcript = `${transcriptStatusText(raw?.transcript_status || 'none')}（${raw?.transcript_completed_count || 0}/${raw?.transcript_segment_count || 0}段）`;
    const clips = raw?.clip_available_count ? `已有${raw.clip_available_count}条成片` : '无成片';
    const start = raw?.live_start_time ? new Date(raw.live_start_time) : null;
    const timeText =
      start && !Number.isNaN(start.getTime())
        ? `${start.getMonth() + 1}/${start.getDate()} ${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')}`
        : '时间未知';
    const metaLabel = `${timeText} · ${transcript} · ${clips}`;
    return h('div', { class: 'flex min-w-0 items-center justify-between gap-12px py-2px' }, [
      h(AnchorIdentity, {
        class: 'min-w-0 max-w-200px flex-1',
        sessionId: sessionOption.sessionId,
        avatarUrl: sessionOption.avatarUrl,
        name: sessionOption.anchorName,
        nickname: sessionOption.anchorNickname,
        douyinId: sessionOption.douyinId,
        size: 28,
        dense: true
      }),
      h('span', { class: 'shrink-0 text-11px text-gray-400' }, metaLabel)
    ]);
  }

  /** 回退数据源：项目公共场次列表接口（主播/标题/时间，无话术统计） */
  async function loadSessionOptionsFallback() {
    try {
      const { data } = await fetchLiveSessionPage({ current: 1, size: 50 });
      const records = ((data as Api.Common.PaginatingQueryRecord<Api.Douyin.LiveSessionListItem>)?.records || []).filter(
        item => item.live_status !== 'live'
      );
      sessionOptions.value = records.map(item => ({
        label: `#${item.id} ${item.anchor_name || item.anchor_nickname || ''} ${item.session_title || ''}`,
        value: item.id,
        sessionId: item.id,
        anchorName: item.anchor_name || item.anchor_nickname || '未知主播',
        anchorNickname: item.anchor_nickname,
        douyinId: item.douyin_id,
        avatarUrl: item.anchor_avatar_url,
        raw: {
          session_id: item.id,
          session_title: item.session_title,
          anchor_name: item.anchor_name || item.anchor_nickname,
          anchor_nickname: item.anchor_nickname,
          anchor_avatar_url: item.anchor_avatar_url,
          douyin_id: item.douyin_id,
          live_start_time: item.live_start_time,
          live_duration_seconds: item.live_duration_seconds,
          transcript_segment_count: 0,
          transcript_completed_count: 0,
          transcript_status: 'none',
          clip_count: 0,
          clip_available_count: 0,
          clip_status: 'none'
        }
      }));
    } catch (fallbackError) {
      errorMessage.value = getServiceErrorMessage(fallbackError, '加载失败');
    }
  }

  /** 场次下拉数据：优先候选场次接口（含主播、话术、成片情况），失败回退公共场次列表接口 */
  async function loadSessionOptions() {
    try {
      const data = unwrapServiceData(await fetchClipCandidateSessions(50), '候选场次加载失败');
      sessionOptions.value = (data || []).map(item => ({
        label: `#${item.session_id} ${item.anchor_name || ''} ${item.session_title || ''}`,
        value: item.session_id,
        sessionId: item.session_id,
        anchorName: item.anchor_name || '未知主播',
        anchorNickname: item.anchor_nickname,
        douyinId: item.douyin_id,
        avatarUrl: item.anchor_avatar_url,
        raw: item
      }));
    } catch {
      // 新接口不可用（后端未升级）时，回退到项目公共的场次列表接口，保证下拉始终有内容
      await loadSessionOptionsFallback();
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

  /** 只重制字幕，不重新下载回放或重新选择画面 */
  async function rerenderSubtitle(clipId: number, segments: Api.Douyin.ClipSegment[]) {
    actionLoading.value = true;
    try {
      const action = unwrapServiceData(await rerenderClipSubtitle(clipId, segments), '字幕重制失败');
      message.success(action.message);
      await loadOverview();
      startPolling();
      return true;
    } catch (error) {
      message.error(getServiceErrorMessage(error, '操作失败'));
      return false;
    } finally {
      actionLoading.value = false;
    }
  }

  onMounted(() => {
    mountedFlag = true;
    void loadSessionOptions();
    // 支持从场次详情页「AI 剪辑」入口直达：/clip?sessionId=N
    const routeSessionId = Number(route.query.sessionId);
    if (Number.isInteger(routeSessionId) && routeSessionId > 0) {
      void loadOverview(routeSessionId);
    }
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
    rerenderSubtitle,
    isTaskRunning,
    refreshMediaCookie,
    renderSessionLabel
  };
}
