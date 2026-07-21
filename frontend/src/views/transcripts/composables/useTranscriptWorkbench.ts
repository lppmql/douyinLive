/**
 * 话术页面 — 全部状态管理
 *
 * 把 index.vue 中所有 ref、computed、异步操作集中到这里，
 * index.vue 只负责布局 + 传 props 给子组件。
 *
 * 使用方式：
 * ```ts
 * const wb = useTranscriptWorkbench();
 * onMounted(wb.initializePage);
 * ```
 */
import { computed, h, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useIntervalFn } from '@vueuse/core';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';

import {
  fetchLiveSessions,
  fetchTranscriptFullText,
  fetchTranscriptSegments,
  fetchTranscriptTasks,
  fetchTranscriptTaskStatus,
  getLiveSessionAvatarUrl,
  queueTranscript,
  queueTranscriptsByAnchor,
  runTranscriptAiPipeline
} from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import { sortSessionsByLatest } from '@/utils/analysisHelpers';
import { formatTime } from '@/utils/transcriptHelpers';

import {
  buildCategoryStats,
  buildSessionOptions,
  buildTaskStatusCards,
  type SessionSelectOption
} from '@/adapters/transcript-adapter';

import { useTranscriptRealtime } from './useTranscriptRealtime';

// ========== 类型别名 ==========

type TaskStatus = Api.Douyin.TranscriptTask['status'];

// ========== Composable ==========

export function useTranscriptWorkbench() {
  const router = useRouter();
  const message = useMessage();

  // ── 响应式状态 ──

  const sessions = ref<Api.Douyin.LiveSession[]>([]);
  const tasks = ref<Api.Douyin.TranscriptTask[]>([]);
  const segments = ref<Api.Douyin.TranscriptSegment[]>([]);
  const fullText = ref('');
  const selectedSessionId = ref<number | null>(null);
  const taskSummary = ref<Record<TaskStatus, number>>({ queued: 0, processing: 0, completed: 0, failed: 0 });
  const loading = ref(true);
  const refreshing = ref(false);
  const queueLoading = ref(false);
  const batchLoading = ref(false);
  const aiLoading = ref(false);
  const taskDrawerVisible = ref(false);
  const taskFilter = ref<TaskStatus | 'all'>('all');
  const searchKeyword = ref('');
  const categoryFilter = ref<string | null>(null);
  const viewMode = ref<'segments' | 'full'>('segments');
  const visibleSegmentLimit = ref(80);
  const loadError = ref('');
  const pageActive = ref(true);

  // ── 实时话术 WebSocket ──

  const {
    livePreview,
    wsConnected,
    onPageActivated: wsActivate,
    onPageDeactivated: wsDeactivate
  } = useTranscriptRealtime({
    selectedSessionId,
    onFinalSegment: (sid) => { loadTranscript(sid, true); }
  });

  // ── 计算属性 ──

  const selectedSession = computed(() =>
    sessions.value.find(item => item.id === selectedSessionId.value) || null
  );

  const selectedTask = computed(() =>
    tasks.value.find(item => item.session_id === selectedSessionId.value) || null
  );

  const activeTaskCount = computed(() =>
    taskSummary.value.queued + taskSummary.value.processing
  );

  /** 场次 ID → 任务映射表（用于下拉选项构建） */
  const taskBySession = computed(() =>
    new Map(tasks.value.map(item => [item.session_id, item]))
  );

  /** 4 张任务状态卡片配置 */
  const taskStatusCards = computed(() =>
    buildTaskStatusCards(taskSummary.value)
  );

  /** 场次下拉选项列表 */
  const sessionOptions = computed(() =>
    buildSessionOptions(sessions.value, taskBySession.value)
  );

  /** 话术分类统计 */
  const categoryStats = computed(() =>
    buildCategoryStats(segments.value)
  );

  /** 分类筛选下拉选项 */
  const categoryOptions = computed(() => [
    { label: '全部分类', value: '' },
    ...categoryStats.value.map(item => ({
      label: `${item.name} (${item.count})`,
      value: item.name
    }))
  ]);

  /** 按关键词 + 分类筛选后的片段 */
  const filteredSegments = computed(() => {
    const keyword = searchKeyword.value.trim().toLowerCase();
    return segments.value.filter(item => {
      const matchesCategory = !categoryFilter.value || (item.segment_type || '未分类') === categoryFilter.value;
      const matchesKeyword = !keyword || item.text_content.toLowerCase().includes(keyword);
      return matchesCategory && matchesKeyword;
    });
  });

  /** 当前可见的分段（懒加载，默认 80 条） */
  const visibleSegments = computed(() =>
    filteredSegments.value.slice(0, visibleSegmentLimit.value)
  );

  /** 话术总字数 */
  const totalCharacters = computed(() =>
    segments.value.reduce((total, item) => total + item.text_content.length, 0)
  );

  /** 已转写的最大秒数 */
  const transcribedSeconds = computed(() =>
    Math.max(0, ...segments.value.map(item => item.segment_end || 0))
  );

  /** 话术时间覆盖率（已转写 / 直播时长） */
  const coveragePercent = computed(() => {
    const duration = selectedSession.value?.live_duration_seconds || 0;
    return duration ? Math.min(100, (transcribedSeconds.value / duration) * 100) : 0;
  });

  /** 平均 AI 评分 */
  const averageAiScore = computed(() => {
    const scores = segments.value
      .map(item => item.ai_score)
      .filter((value): value is number => value !== null);
    return scores.length
      ? scores.reduce((total, value) => total + value, 0) / scores.length
      : null;
  });

  /** 按状态筛选后的任务列表 */
  const filteredTasks = computed(() =>
    taskFilter.value === 'all'
      ? tasks.value
      : tasks.value.filter(item => item.status === taskFilter.value)
  );

  /** 当前选中场次的主播头像 URL */
  const selectedSessionAvatarUrl = computed(() => {
    if (!selectedSession.value) return undefined;
    return selectedSession.value.anchor_avatar_url
      ? getLiveSessionAvatarUrl(selectedSession.value.id)
      : undefined;
  });

  /** 是否有话术内容（控制复制按钮等 UI 状态） */
  const hasContent = computed(() =>
    segments.value.length > 0 || Boolean(fullText.value)
  );

  // ── UI 渲染辅助 ──

  /** 渲染场次下拉选项（带主播头像） */
  function renderSessionLabel(option: SelectOption) {
    const sessionOption = option as SessionSelectOption;
    return h('div', { class: 'flex min-w-0 items-center gap-8px' }, [
      h(AnchorAvatar, { size: 26, src: sessionOption.avatarUrl || undefined, name: sessionOption.anchorName }),
      h('span', { class: 'min-w-0 flex-1 truncate' }, String(sessionOption.label || ''))
    ]);
  }

  /** 获取场次主播头像 URL */
  function getSessionAvatarUrl(session: Api.Douyin.LiveSession) {
    return session.anchor_avatar_url ? getLiveSessionAvatarUrl(session.id) : undefined;
  }

  // ── 异步操作 ──

  /** 加载场次列表（按最新开播排序） */
  async function loadSessions() {
    const response = await fetchLiveSessions();
    sessions.value = sortSessionsByLatest(unwrapServiceData(response, '直播场次读取失败'));
  }

  /** 加载任务汇总 + 任务列表 */
  async function loadTaskData() {
    const [summaryResponse, taskResponse] = await Promise.all([
      fetchTranscriptTaskStatus(),
      fetchTranscriptTasks()
    ]);
    taskSummary.value = unwrapServiceData(summaryResponse, '话术任务汇总读取失败');
    tasks.value = unwrapServiceData(taskResponse, '话术任务读取失败');
  }

  /** 加载单个场次的话术数据（分段 + 全文） */
  async function loadTranscript(sessionId: number, silent = false) {
    selectedSessionId.value = sessionId;
    if (!silent) loading.value = true;
    livePreview.value = '';
    try {
      const [segmentResponse, textResponse] = await Promise.all([
        fetchTranscriptSegments(sessionId),
        fetchTranscriptFullText(sessionId).catch(() => ({ data: null }))
      ]);
      segments.value = unwrapServiceData(segmentResponse, '话术分段读取失败');
      fullText.value = textResponse.data?.full_text || '';
    } catch (error) {
      segments.value = [];
      fullText.value = '';
      if (!silent) message.error(error instanceof Error ? error.message : '话术数据加载失败，请稍后重试');
    } finally {
      loading.value = false;
    }
  }

  /** 页面初始化：加载场次列表 + 任务数据 + 默认打开最新场次 */
  async function initializePage() {
    loading.value = true;
    loadError.value = '';
    try {
      await Promise.all([loadSessions(), loadTaskData()]);
      const latestSession = sessions.value[0];
      if (latestSession) await loadTranscript(latestSession.id);
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : '主播话术页面加载失败';
      message.error(loadError.value);
    } finally {
      loading.value = false;
    }
  }

  /** 发起转写任务（对当前选中场次） */
  async function startTranscription() {
    if (!selectedSessionId.value) return;
    queueLoading.value = true;
    try {
      const response = await queueTranscript(selectedSessionId.value);
      const data = unwrapServiceData(response, '转写任务响应为空');
      message.success(`任务已${data.created ? '创建' : '在队列中'}，编号 ${data.task_id}`);
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '该场次暂无可用回放，请先刷新采集或检查 m3u8');
    } finally {
      queueLoading.value = false;
    }
  }

  /** 批量增量转写（每主播最近 1 场） */
  async function queueAnchorBatch() {
    batchLoading.value = true;
    try {
      const response = await queueTranscriptsByAnchor(1);
      const data = unwrapServiceData(response, '批量任务响应为空');
      message.success(`检查 ${data.anchor_count} 位主播，新建 ${data.created_count} 个任务`);
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '增量转写失败，请确认已采集真实回放');
    } finally {
      batchLoading.value = false;
    }
  }

  /** 对当前场次执行 AI 复盘并入库 */
  async function runAiPipeline() {
    if (!selectedSessionId.value || !segments.value.length) return;
    aiLoading.value = true;
    try {
      const response = await runTranscriptAiPipeline(selectedSessionId.value);
      const data = unwrapServiceData(response, 'AI 分析没有返回处理结果');
      const saved =
        data.live_data_saved + data.comments_saved + data.transcript_saved + data.analysis_saved + data.review_saved;
      message.success(`AI 复盘完成，知识库新增或更新 ${saved} 条真实数据`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 分析失败，请确认本场已有完整话术');
    } finally {
      aiLoading.value = false;
    }
  }

  /** 复制文本到剪贴板（带降级方案） */
  async function copyText(text: string, successMessage: string) {
    if (!text) return message.warning('当前没有可复制的话术');
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // 降级方案：创建临时 textarea
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      textarea.remove();
    }
    message.success(successMessage);
  }

  /** 复制完整话术（全文优先，否则合并分段） */
  function copyFullText() {
    const text =
      fullText.value ||
      segments.value.map(item => `[${formatTime(item.segment_start)}] ${item.text_content}`).join('\n');
    return copyText(text, '完整话术已复制');
  }

  /** 跳转到指定片段并滚动到视图 */
  async function jumpToSegment(segment: Api.Douyin.TranscriptSegment) {
    viewMode.value = 'segments';
    searchKeyword.value = '';
    categoryFilter.value = null;
    await nextTick();
    const segmentIndex = segments.value.findIndex(item => item.id === segment.id);
    visibleSegmentLimit.value = Math.max(80, segmentIndex + 1);
    await nextTick();
    document.getElementById(`transcript-segment-${segment.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /** 打开任务抽屉（可选按状态预筛选） */
  function openTaskDrawer(status: TaskStatus | 'all' = 'all') {
    taskFilter.value = status;
    taskDrawerVisible.value = true;
  }

  /** 从任务抽屉中选择一个任务 → 关闭抽屉并加载对应场次 */
  function selectTask(task: Api.Douyin.TranscriptTask) {
    taskDrawerVisible.value = false;
    void loadTranscript(task.session_id);
  }

  /** 跳转到场次详情页 */
  function openSessionDetail(sessionId: number) {
    void router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
  }

  // ── 定时轮询（有活跃任务时每 5 秒刷新） ──

  const { pause: pausePolling, resume: resumePolling } = useIntervalFn(
    async () => {
      if (!pageActive.value || document.visibilityState !== 'visible') return;
      await loadTaskData();
      if (selectedSessionId.value) await loadTranscript(selectedSessionId.value, true);
    },
    5000,
    { immediate: false }
  );

  // 有活跃任务就轮询，没有就暂停
  watch(
    activeTaskCount,
    count => (count && pageActive.value ? resumePolling() : pausePolling()),
    { immediate: true }
  );

  // 切换场次 / 搜索 / 筛选 → 重置懒加载数量
  watch([selectedSessionId, searchKeyword, categoryFilter], () => {
    visibleSegmentLimit.value = 80;
  });

  // ── 生命周期 ──

  onMounted(initializePage);

  onActivated(() => {
    pageActive.value = true;
    if (activeTaskCount.value) resumePolling();
    wsActivate();
  });

  onDeactivated(() => {
    pageActive.value = false;
    pausePolling();
    wsDeactivate();
  });

  onUnmounted(() => {
    pageActive.value = false;
    pausePolling();
    wsDeactivate();
  });

  // ── 导出 ──

  return {
    // 状态
    sessions,
    selectedSessionId,
    segments,
    fullText,
    tasks,
    taskSummary,
    loading,
    refreshing,
    queueLoading,
    batchLoading,
    aiLoading,
    taskDrawerVisible,
    taskFilter,
    searchKeyword,
    categoryFilter,
    viewMode,
    visibleSegmentLimit,
    loadError,
    livePreview,
    // 计算属性
    selectedSession,
    selectedTask,
    activeTaskCount,
    taskStatusCards,
    sessionOptions,
    categoryStats,
    categoryOptions,
    filteredSegments,
    visibleSegments,
    filteredTasks,
    totalCharacters,
    transcribedSeconds,
    coveragePercent,
    averageAiScore,
    wsConnected,
    selectedSessionAvatarUrl,
    hasContent,
    // 渲染辅助
    renderSessionLabel,
    getSessionAvatarUrl,
    // 操作
    initializePage,
    loadTranscript,
    startTranscription,
    queueAnchorBatch,
    runAiPipeline,
    copyText,
    copyFullText,
    jumpToSegment,
    openTaskDrawer,
    selectTask,
    openSessionDetail
  };
}

// ── 重新导出工具函数（方便子组件只从 composable 一个地方导入） ──

export {
  formatTime,
  formatDuration,
  formatDate,
  getStatusLabel,
  getStatusType,
  getPostprocessLabel,
  getPostprocessType
} from '@/utils/transcriptHelpers';

// 从 adapter 重导出类型
export type { SessionSelectOption, CategoryStat, TaskStatusCard } from '@/adapters/transcript-adapter';
