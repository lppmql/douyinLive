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
import { computed, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useIntervalFn } from '@vueuse/core';
import { useDialog, useMessage } from 'naive-ui';

import {
  fetchLiveSessions,
  fetchTranscriptFullText,
  fetchTranscriptSegments,
  fetchTranscriptTasks,
  fetchTranscriptTaskStatus,
  fetchTranscriptDispatchPolicy,
  queueTranscript,
  queueTranscriptsByAnchor,
  runTranscriptAiPipeline,
  deleteTranscriptTask,
  clearFailedTranscriptTasks,
  updateTranscriptDispatchPolicy,
  fetchAsrControlStatus,
  setAsrControl,
  stopTranscriptTask,
  retryTranscriptTask,
  releaseTranscriptTaskPriority
} from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import { sortSessionsByLatest } from '@/utils/analysisHelpers';
import { formatTime } from '@/utils/transcriptHelpers';

import {
  buildCategoryStats,
  buildReadableSegments,
  buildSessionOptions,
  buildTaskStatusCards,
  selectTranscriptVersionSegments
} from '@/adapters/transcript-adapter';

import { useTranscriptRealtime } from '@/hooks/business/transcript-realtime';

// ========== 类型别名 ==========

type TaskStatus = Api.Douyin.TranscriptTask['status'];
export type TranscriptTaskFilter = TaskStatus | 'all' | 'attention';

function taskPriority(task: Api.Douyin.TranscriptTask): [number, number, number] {
  const statusPriority: Record<string, number> = {
    processing: 0,
    queued: 1,
    failed: 2,
    completed: 3,
    cancelled: 4
  };
  return [statusPriority[task.status] ?? 5, task.task_type === 'offline' ? 0 : 1, -task.id];
}

function isPreferredTask(candidate: Api.Douyin.TranscriptTask, current: Api.Douyin.TranscriptTask): boolean {
  const left = taskPriority(candidate);
  const right = taskPriority(current);
  return (
    left[0] < right[0] ||
    (left[0] === right[0] && left[1] < right[1]) ||
    (left[0] === right[0] && left[1] === right[1] && left[2] < right[2])
  );
}

// ========== Composable ==========

export function useTranscriptWorkbench() {
  const router = useRouter();
  const route = useRoute();
  const message = useMessage();
  const dialog = useDialog();

  // ── 响应式状态 ──

  const sessions = ref<Api.Douyin.LiveSession[]>([]);
  const tasks = ref<Api.Douyin.TranscriptTask[]>([]);
  const segments = ref<Api.Douyin.TranscriptSegment[]>([]);
  const fullText = ref('');
  const selectedSessionId = ref<number | null>(null);
  const taskSummary = ref<Api.Douyin.TranscriptTaskSummary>({
    queued: 0,
    processing: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
    needs_attention: 0
  });
  const loading = ref(true);
  const refreshing = ref(false);
  const queueLoading = ref(false);
  const batchLoading = ref(false);
  const aiLoading = ref(false);
  const taskDrawerVisible = ref(false);
  const taskFilter = ref<TranscriptTaskFilter>('all');
  const searchKeyword = ref('');
  const categoryFilter = ref<string | null>(null);
  const viewMode = ref<'segments' | 'full'>('segments');
  const visibleSegmentLimit = ref(80);
  const loadError = ref('');
  const pageActive = ref(true);
  const dispatchPolicy = ref<Api.Douyin.TranscriptDispatchPolicy | null>(null);
  const dispatchPolicyLoading = ref(false);
  const asrRuntime = ref<Api.Douyin.AsrControlStatus | null>(null);
  const runtimeActionLoading = ref(false);
  const taskActionIds = ref(new Set<number>());

  // ── 实时话术 WebSocket ──

  const {
    livePreview,
    wsConnected,
    onPageActivated: wsActivate,
    onPageDeactivated: wsDeactivate
  } = useTranscriptRealtime({
    selectedSessionId,
    onSegment: (segment, sessionId) => {
      if (sessionId !== selectedSessionId.value) return;
      const index = segments.value.findIndex(item => item.id === segment.id);
      if (index >= 0) segments.value[index] = segment;
      else
        segments.value = [...segments.value, segment].sort(
          (left, right) => left.segment_start - right.segment_start || left.id - right.id
        );
    }
  });

  // ── 计算属性 ──

  const selectedSession = computed(() => sessions.value.find(item => item.id === selectedSessionId.value) || null);

  /** 同场可能同时存在直播初稿与下播终稿，统一选出页面应该展示的那一条。 */
  const taskBySession = computed(() => {
    const result = new Map<number, Api.Douyin.TranscriptTask>();
    for (const task of tasks.value) {
      const current = result.get(task.session_id);
      if (!current || isPreferredTask(task, current)) result.set(task.session_id, task);
    }
    return result;
  });

  const selectedTask = computed(() => {
    const sessionId = selectedSessionId.value;
    return sessionId === null ? null : taskBySession.value.get(sessionId) || null;
  });

  const activeTaskCount = computed(() => taskSummary.value.queued + taskSummary.value.processing);

  /** 4 张任务状态卡片配置（含进度信息） */
  const taskStatusCards = computed(() => buildTaskStatusCards(taskSummary.value, tasks.value));

  /** 场次下拉选项列表 */
  const sessionOptions = computed(() => buildSessionOptions(sessions.value, taskBySession.value));

  /** 页面只选择一个话术版本：终稿存在时完全排除实时初稿，避免重复统计。 */
  const versionSegments = computed(() => selectTranscriptVersionSegments(segments.value));

  /** 页面可读片段：仅隐藏同一实时窗口的包含式短重复，不改数据库原文。 */
  const readableSegments = computed(() => buildReadableSegments(versionSegments.value));

  /** 话术业务内容结构统计 */
  const categoryStats = computed(() => buildCategoryStats(readableSegments.value));

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
    return readableSegments.value.filter(item => {
      const matchesCategory = !categoryFilter.value || item.contentCategory === categoryFilter.value;
      const matchesKeyword = !keyword || item.text_content.toLowerCase().includes(keyword);
      return matchesCategory && matchesKeyword;
    });
  });

  /** 当前可见的分段（懒加载，默认 80 条） */
  const visibleSegments = computed(() => filteredSegments.value.slice(0, visibleSegmentLimit.value));

  /** 话术总字数 */
  const totalCharacters = computed(() =>
    readableSegments.value.reduce((total, item) => total + item.text_content.length, 0)
  );

  /** 已转写的最大秒数 */
  const transcribedSeconds = computed(() => Math.max(0, ...versionSegments.value.map(item => item.segment_end || 0)));

  /** 话术时间覆盖率（已转写 / 直播时长） */
  const coveragePercent = computed(() => {
    const duration = selectedSession.value?.live_duration_seconds || 0;
    return duration ? Math.min(100, (transcribedSeconds.value / duration) * 100) : 0;
  });

  /** 时长未知时不显示误导性的 0%，改为明确的实时累计进度。 */
  const coverageLabel = computed(() => {
    const duration = selectedSession.value?.live_duration_seconds || 0;
    if (!duration) {
      return transcribedSeconds.value > 0 ? `已转到 ${formatTime(transcribedSeconds.value)}` : '等待话术';
    }
    return `${coveragePercent.value.toFixed(1)}%`;
  });

  /** 平均 AI 评分 */
  const averageAiScore = computed(() => {
    const scores = readableSegments.value.map(item => item.ai_score).filter((value): value is number => value !== null);
    return scores.length ? scores.reduce((total, value) => total + value, 0) / scores.length : null;
  });

  const contentVersion = computed<'offline-final' | 'realtime-draft' | 'empty'>(() => {
    if (versionSegments.value.some(item => item.segment_type === 'asr_offline')) return 'offline-final';
    return readableSegments.value.length ? 'realtime-draft' : 'empty';
  });

  const contentVersionLabel = computed(() => {
    if (contentVersion.value === 'offline-final') return '离线终稿';
    if (contentVersion.value === 'realtime-draft') return '实时初稿';
    return '尚无话术';
  });

  const hiddenDuplicateCount = computed(() =>
    Math.max(0, versionSegments.value.length - readableSegments.value.length)
  );

  /** AI 复盘只使用下播后的完整终稿，避免拿直播初稿生成错误结论。 */
  const canRunAiPipeline = computed(
    () =>
      contentVersion.value === 'offline-final' &&
      selectedTask.value?.task_type === 'offline' &&
      selectedTask.value.status === 'completed'
  );

  const displayedFullText = computed(() => {
    if (contentVersion.value === 'offline-final' && fullText.value) return fullText.value;
    return readableSegments.value.map(item => `[${formatTime(item.segment_start)}] ${item.text_content}`).join('\n\n');
  });

  /** 按状态筛选后的任务列表 */
  const filteredTasks = computed(() =>
    taskFilter.value === 'all'
      ? tasks.value
      : taskFilter.value === 'attention'
        ? tasks.value.filter(item => ['failed', 'cancelled'].includes(item.status))
        : tasks.value.filter(item => item.status === taskFilter.value)
  );

  /** 是否有话术内容（控制复制按钮等 UI 状态） */
  const hasContent = computed(() => readableSegments.value.length > 0 || Boolean(fullText.value));

  // ── 异步操作 ──

  /** 加载场次列表（按最新开播排序） */
  async function loadSessions() {
    const response = await fetchLiveSessions();
    sessions.value = sortSessionsByLatest(unwrapServiceData(response, '直播场次读取失败'));
  }

  /** 加载任务汇总 + 任务列表 */
  async function loadTaskData() {
    const [summaryResponse, taskResponse, policyResponse, runtimeResponse] = await Promise.all([
      fetchTranscriptTaskStatus(),
      fetchTranscriptTasks(),
      fetchTranscriptDispatchPolicy(),
      fetchAsrControlStatus()
    ]);
    taskSummary.value = unwrapServiceData(summaryResponse, '话术任务汇总读取失败');
    tasks.value = unwrapServiceData(taskResponse, '话术任务读取失败');
    dispatchPolicy.value = unwrapServiceData(policyResponse, '话术调度策略读取失败');
    asrRuntime.value = unwrapServiceData(runtimeResponse, 'ASR 运行状态读取失败');
  }

  /** 加载单个场次的话术数据（分段 + 全文） */
  async function loadTranscript(sessionId: number, silent = false) {
    selectedSessionId.value = sessionId;
    if (String(route.query.sessionId || '') !== String(sessionId)) {
      void router.replace({ query: { ...route.query, sessionId: String(sessionId) } });
    }
    if (!silent) loading.value = true;
    livePreview.value = '';
    try {
      const [loadedSegments, textResponse] = await Promise.all([
        fetchAllTranscriptSegments(sessionId),
        fetchTranscriptFullText(sessionId).catch(() => ({ data: null }))
      ]);
      segments.value = loadedSegments;
      fullText.value = textResponse.data?.full_text || '';
    } catch (error) {
      segments.value = [];
      fullText.value = '';
      if (!silent) message.error(error instanceof Error ? error.message : '话术数据加载失败，请稍后重试');
    } finally {
      loading.value = false;
    }
  }

  /** 分页读取全部真实话术，避免长直播被接口默认的前 500 段截断。 */
  async function fetchAllTranscriptSegments(sessionId: number) {
    const pageSize = 500;
    const maxPages = 40;
    const result: Api.Douyin.TranscriptSegment[] = [];
    for (let page = 0; page < maxPages; page += 1) {
      const response = await fetchTranscriptSegments(sessionId, page * pageSize, pageSize);
      const batch = unwrapServiceData(response, '话术分段读取失败');
      result.push(...batch);
      if (batch.length < pageSize) return result;
    }
    throw new Error(`本场话术超过 ${pageSize * maxPages} 段，请缩小场次范围后重试`);
  }

  /** 页面初始化：加载场次列表 + 任务数据 + 默认打开最新场次 */
  async function initializePage() {
    loading.value = true;
    loadError.value = '';
    try {
      await Promise.all([loadSessions(), loadTaskData()]);
      const rawSessionId = Array.isArray(route.query.sessionId) ? route.query.sessionId[0] : route.query.sessionId;
      const requestedSessionId = Number(rawSessionId);
      const requestedSession = sessions.value.find(item => item.id === requestedSessionId);
      const initialSession = requestedSession || sessions.value[0];
      if (initialSession) await loadTranscript(initialSession.id);
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
    const isRecovery = ['failed', 'cancelled'].includes(selectedTask.value?.status || '');
    queueLoading.value = true;
    try {
      const response = await queueTranscript(selectedSessionId.value);
      const data = unwrapServiceData(response, '转写任务响应为空');
      message.success(
        isRecovery
          ? `人工任务 #${data.task_id} 已断点续传，其他场次将在安全边界暂停`
          : `人工任务 #${data.task_id} 已优先，完成后自动恢复其他场次`
      );
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '该场次暂无可用回放，请先刷新采集或检查 m3u8');
    } finally {
      queueLoading.value = false;
    }
  }

  /** 补排今日自动转写范围内的场次。 */
  async function queueAnchorBatch() {
    batchLoading.value = true;
    try {
      const response = await queueTranscriptsByAnchor(1);
      const data = unwrapServiceData(response, '批量任务响应为空');
      message.success(`已检查今日 ${data.anchor_count} 位主播，新建 ${data.created_count} 个自动任务`);
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '增量转写失败，请确认已采集真实回放');
    } finally {
      batchLoading.value = false;
    }
  }

  /** 修改自动队列排序，不改变直播和人工任务的硬优先级。 */
  async function changeDispatchOrder(orderMode: Api.Douyin.TranscriptDispatchPolicy['order_mode']) {
    dispatchPolicyLoading.value = true;
    try {
      const response = await updateTranscriptDispatchPolicy(orderMode);
      dispatchPolicy.value = unwrapServiceData(response, '话术调度策略更新失败');
      message.success('自动转写排序已更新');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '自动转写排序更新失败');
    } finally {
      dispatchPolicyLoading.value = false;
    }
  }

  /** 对当前场次执行 AI 复盘并入库 */
  async function runAiPipeline() {
    if (!selectedSessionId.value || !canRunAiPipeline.value) {
      message.warning('请先完成本场离线终稿，再生成 AI 复盘');
      return;
    }
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
    return copyText(displayedFullText.value, '当前可读话术已复制');
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
    document
      .getElementById(`transcript-segment-${segment.id}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /** 打开任务抽屉（可选按状态预筛选） */
  function openTaskDrawer(status: TranscriptTaskFilter = 'all') {
    taskFilter.value = status;
    taskDrawerVisible.value = true;
  }

  /** 从任务抽屉中选择一个任务 → 关闭抽屉并加载对应场次 */
  function selectTask(task: Api.Douyin.TranscriptTask) {
    taskDrawerVisible.value = false;
    void loadTranscript(task.session_id);
  }

  /** 从任务抽屉直接断点重试指定失败场次。 */
  async function retryTask(task: Api.Douyin.TranscriptTask) {
    taskActionIds.value.add(task.id);
    taskActionIds.value = new Set(taskActionIds.value);
    try {
      const response = await retryTranscriptTask(task.id);
      const data = unwrapServiceData(response, '断点重试响应为空');
      message.success(data.message);
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '断点重试失败');
    } finally {
      taskActionIds.value.delete(task.id);
      taskActionIds.value = new Set(taskActionIds.value);
    }
  }

  /** 从任务抽屉直接把某一场设为人工独占。 */
  async function prioritizeTask(task: Api.Douyin.TranscriptTask) {
    taskActionIds.value.add(task.id);
    taskActionIds.value = new Set(taskActionIds.value);
    selectedSessionId.value = task.session_id;
    try {
      await startTranscription();
    } finally {
      taskActionIds.value.delete(task.id);
      taskActionIds.value = new Set(taskActionIds.value);
    }
  }

  /** 取消人工独占但不中止任务，其他场次立即恢复自动调度。 */
  async function releaseTaskPriority(task: Api.Douyin.TranscriptTask) {
    if (task.session_id === selectedSessionId.value) queueLoading.value = true;
    taskActionIds.value.add(task.id);
    taskActionIds.value = new Set(taskActionIds.value);
    try {
      const response = await releaseTranscriptTaskPriority(task.id);
      const data = unwrapServiceData(response, '取消人工优先响应为空');
      message.success(data.message);
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '取消人工优先失败');
    } finally {
      queueLoading.value = false;
      taskActionIds.value.delete(task.id);
      taskActionIds.value = new Set(taskActionIds.value);
    }
  }

  /** 安全停止任务，处理中任务会在当前音频安全点结束。 */
  function stopTask(task: Api.Douyin.TranscriptTask) {
    dialog.warning({
      title: '停止转写任务',
      content: `确定停止任务 #${task.id} 吗？已经完成的分片和话术会保留。`,
      positiveText: '安全停止',
      negativeText: '继续转写',
      onPositiveClick: async () => {
        taskActionIds.value.add(task.id);
        taskActionIds.value = new Set(taskActionIds.value);
        try {
          const response = await stopTranscriptTask(task.id);
          const data = unwrapServiceData(response, '停止任务响应为空');
          message.success(data.message);
          await loadTaskData();
        } catch (error) {
          message.error(error instanceof Error ? error.message : '停止任务失败');
        } finally {
          taskActionIds.value.delete(task.id);
          taskActionIds.value = new Set(taskActionIds.value);
        }
      }
    });
  }

  /** 页面检测到无心跳时，手动触发同一套僵死清理与恢复逻辑。 */
  async function restoreAsrRuntime() {
    runtimeActionLoading.value = true;
    try {
      const response = await setAsrControl(true);
      asrRuntime.value = unwrapServiceData(response, 'ASR 恢复响应为空');
      message.success('ASR 转写服务已恢复，排队任务将从断点继续');
      await loadTaskData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'ASR 转写服务恢复失败');
    } finally {
      runtimeActionLoading.value = false;
    }
  }

  /** 正在删除中的任务 ID 集合（用于按钮 loading 状态） */
  const deletingTaskIds = ref(new Set<number>());
  /** 是否正在清空全部失败任务 */
  const clearFailedLoading = ref(false);

  /** 删除单条失败任务（带确认弹窗） */
  function deleteTask(task: Api.Douyin.TranscriptTask) {
    dialog.warning({
      title: '确认删除',
      content: `确定要删除「${task.anchor_name} - ${task.session_title}」的失败任务吗？关联的话术分段也会被清理。`,
      positiveText: '确认删除',
      negativeText: '取消',
      onPositiveClick: async () => {
        deletingTaskIds.value.add(task.id);
        try {
          const response = await deleteTranscriptTask(task.id);
          const data = response.data;
          if (data?.deleted) {
            message.success(data.message || `任务 #${task.id} 已删除`);
          } else {
            message.success(`任务 #${task.id} 已删除`);
          }
          await loadTaskData();
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败，请稍后重试');
        } finally {
          deletingTaskIds.value.delete(task.id);
          deletingTaskIds.value = new Set(deletingTaskIds.value);
        }
      }
    });
  }

  /** 一键清空全部失败任务（带确认弹窗） */
  function clearFailedTasks() {
    const attentionCount = taskSummary.value.needs_attention;
    if (!attentionCount) {
      message.info('当前没有暂停或失败任务需要清理');
      return;
    }
    dialog.warning({
      title: '确认清空',
      content: `确定要清空全部 ${attentionCount} 条暂停或失败任务吗？关联的话术分段也会被清理，此操作不可撤销。`,
      positiveText: '全部清空',
      negativeText: '取消',
      onPositiveClick: async () => {
        clearFailedLoading.value = true;
        try {
          const response = await clearFailedTranscriptTasks();
          const data = response.data;
          if (data?.deleted_count) {
            message.success(data.message || `已清理 ${data.deleted_count} 条失败任务`);
          } else {
            message.info(data?.message || '没有需要清理的失败任务');
          }
          await loadTaskData();
        } catch (error) {
          message.error(error instanceof Error ? error.message : '清空失败，请稍后重试');
        } finally {
          clearFailedLoading.value = false;
        }
      }
    });
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
  watch(activeTaskCount, count => (count && pageActive.value ? resumePolling() : pausePolling()), { immediate: true });

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
    versionSegments,
    readableSegments,
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
    dispatchPolicy,
    dispatchPolicyLoading,
    asrRuntime,
    runtimeActionLoading,
    taskActionIds,
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
    coverageLabel,
    averageAiScore,
    contentVersion,
    contentVersionLabel,
    hiddenDuplicateCount,
    canRunAiPipeline,
    displayedFullText,
    wsConnected,
    hasContent,
    // 操作
    initializePage,
    loadTranscript,
    startTranscription,
    queueAnchorBatch,
    changeDispatchOrder,
    runAiPipeline,
    copyText,
    copyFullText,
    jumpToSegment,
    openTaskDrawer,
    selectTask,
    retryTask,
    prioritizeTask,
    releaseTaskPriority,
    stopTask,
    restoreAsrRuntime,
    openSessionDetail,
    // 删除相关
    deletingTaskIds,
    clearFailedLoading,
    deleteTask,
    clearFailedTasks
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
