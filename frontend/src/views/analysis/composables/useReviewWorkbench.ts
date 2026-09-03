import { computed, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useRoute, useRouter } from 'vue-router';

import { unwrapServiceData } from '@/utils/service';
import {
  fetchAnalysisReports,
  fetchLiveSessionDetail,
  fetchSessionSelectorOptions,
  fetchReviewWorkbench,
  generateSessionReview,
  optimizeSession,
  scoreSession
} from '@/service/api/douyin';

import {
  formatShortDateTime,
  formatFullDateTime,
  formatDuration,
  formatNumber,
  scoreLevel,
  readinessTagType,
  sortSessionsByLatest
} from '@/utils/analysisHelpers';

import { restoreReportsFromList } from '@/adapters/review-report-adapter';
import { buildCommonSessionOptions } from '@/adapters/session-selector-adapter';
import {
  appendUniqueSelectorPage,
  useSessionSelectorFilters,
  type SessionSelectorChangeContext
} from '@/hooks/business/session-selector';

// ========== 类型定义 ==========

/** 操作阶段：空字符串 = 空闲，其他值为具体阶段 */
export type ActionStage = '' | 'evidence' | 'score' | 'optimize' | 'score-only' | 'optimize-only';

// ========== Composable ==========

/**
 * 复盘工作台状态管理
 *
 * 把 AI 复盘页面全部状态、计算属性、异步操作集中到这里，
 * index.vue 只负责布局 + 传 props 给子组件。
 *
 * 使用方式：
 * ```ts
 * const wb = useReviewWorkbench();
 * onMounted(wb.initializePage);
 * ```
 */
export function useReviewWorkbench() {
  const message = useMessage();
  const router = useRouter();
  const route = useRoute();

  // ---- 响应式状态 ----

  const sessions = ref<Api.Douyin.LiveSessionListItem[]>([]);
  const selectedSessionDetail = ref<Api.Douyin.LiveSession | null>(null);
  const selectedSessionId = ref<number | null>(null);
  const workbench = ref<Api.Douyin.ReviewWorkbench | null>(null);
  const sessionReports = ref<Api.Douyin.AnalysisReport[]>([]);
  const scoreResult = ref<Api.Douyin.AiScoreResult | null>(null);
  const optimizeResult = ref<Api.Douyin.AiOptimizationResult | null>(null);
  const loading = ref(true);
  const loadError = ref('');
  const contextLoading = ref(false);
  const actionStage = ref<ActionStage>('');
  const activeTab = ref<'overview' | 'evidence' | 'audience' | 'history'>('audience');

  /** 防止异步竞态：每次发起新的上下文加载时 +1，回调里检查是否还是最新请求 */
  let contextRequestId = 0;

  // ---- 计算属性 ----

  /** 当前选中的场次对象 */
  const selectedSession = computed(() =>
    selectedSessionDetail.value?.id === selectedSessionId.value ? selectedSessionDetail.value : null
  );

  /** 数据是否足够支撑 AI 分析 */
  const analysisReady = computed(() =>
    Boolean(workbench.value?.completeness.analysis_ready)
  );

  /** 已覆盖的避坑知识领域数量 */
  const coveredDomainCount = computed(() =>
    workbench.value?.domain_coverage.filter(item => item.covered).length || 0
  );

  /** 待处理（open 状态）的复盘发现数量 */
  const openFindingCount = computed(() =>
    workbench.value?.findings.filter(item => item.status === 'open').length || 0
  );

  /** 最近一份分析报告 */
  const latestReport = computed(() => sessionReports.value[0] || null);

  /** 是否有操作正在进行中 */
  const actionBusy = computed(() => Boolean(actionStage.value));

  /** 场次下拉选项列表（含主播头像信息） */
  const sessionOptions = computed(() => buildCommonSessionOptions(sessions.value));

  /** 五维评分指标列表（已过滤无效值） */
  const scoreMetrics = computed(() => {
    if (!scoreResult.value) return [];
    const result = scoreResult.value;
    const metrics = [
      { key: 'knowledge', label: '知识价值', value: result.knowledge_value_score, max: 10, icon: 'mdi:book-open-page-variant-outline' },
      { key: 'completeness', label: '内容完整', value: result.completeness_score, max: 10, icon: 'mdi:format-list-checks' },
      { key: 'interaction', label: '问题互动', value: result.interactivity_score, max: 10, icon: 'mdi:comment-question-outline' },
      { key: 'lead', label: '私信承接', value: result.lead_guidance_score, max: 10, icon: 'mdi:message-arrow-right-outline' },
      { key: 'affinity', label: '表达亲和', value: result.affinity_score, max: 10, icon: 'mdi:account-heart-outline' },
      { key: 'total', label: '综合得分', value: result.total_score, max: 50, icon: 'mdi:chart-areaspline' }
    ];
    return metrics.filter(item => typeof item.value === 'number') as Array<{
      key: string; label: string; value: number; max: number; icon: string;
    }>;
  });

  /** 改进建议列表：优先取优化结果中的建议，fallback 到评分中的建议 */
  const improvementSuggestions = computed(() => {
    const optimizeSuggestions = toStringArray(optimizeResult.value?.suggestions);
    if (optimizeSuggestions.length) return optimizeSuggestions;
    return scoreResult.value?.suggestions || [];
  });

  /** 下一场直播执行计划 */
  const nextLivePlan = computed(() =>
    Array.isArray(optimizeResult.value?.next_live_plan) ? optimizeResult.value.next_live_plan : []
  );

  /** 合规人工复核事项 */
  const complianceNotes = computed(() =>
    toStringArray(optimizeResult.value?.compliance_notes)
  );

  // ---- 辅助函数 ----

  /** 安全提取字符串数组 */
  function toStringArray(value: unknown): string[] {
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
      : [];
  }

  /** 从已保存的报告列表中恢复评分和优化结果 */
  function restoreSavedReports(reports: Api.Douyin.AnalysisReport[]) {
    restoreReportsFromList(reports, v => { scoreResult.value = v; }, v => { optimizeResult.value = v; });
  }

  // ---- 异步操作 ----

  /** 加载单个场次的复盘上下文（工作台 + 报告列表） */
  async function loadSessionContext(sessionId: number, silent = false) {
    const requestId = ++contextRequestId;
    if (!silent) contextLoading.value = true;
    try {
      const [sessionResponse, workbenchResponse, reportsResponse] = await Promise.all([
        fetchLiveSessionDetail(sessionId),
        fetchReviewWorkbench(sessionId),
        fetchAnalysisReports({ sessionId, limit: 100 })
      ]);
      if (requestId !== contextRequestId) return;
      selectedSessionDetail.value = unwrapServiceData(sessionResponse, '场次详情读取失败');
      workbench.value = unwrapServiceData(workbenchResponse, '复盘证据读取失败');
      sessionReports.value = unwrapServiceData(reportsResponse, '分析报告读取失败');
      restoreSavedReports(sessionReports.value);
    } catch (error) {
      if (requestId !== contextRequestId) return;
      workbench.value = null;
      selectedSessionDetail.value = null;
      sessionReports.value = [];
      scoreResult.value = null;
      optimizeResult.value = null;
      if (!silent) message.error((error as { message?: string }).message || '复盘上下文加载失败');
    } finally {
      if (requestId === contextRequestId) contextLoading.value = false;
    }
  }

  async function loadSessionOptions(
    includeSessionId?: number | null,
    context?: SessionSelectorChangeContext
  ) {
    const response = await fetchSessionSelectorOptions(selectorFilters.buildQuery(includeSessionId, context));
    if (context && !context.isCurrent()) return 0;
    const records = sortSessionsByLatest(unwrapServiceData(response, '直播场次读取失败'));
    sessions.value = context?.mode === 'append'
      ? appendUniqueSelectorPage(sessions.value, records, item => item.id)
      : records;
    if (!context) selectorFilters.registerInitialPage(records.length);
    return records.length;
  }

  /** 筛选发生变化时，保留仍命中的当前场次，否则打开筛选结果中的最新一场。 */
  async function reloadFilteredSessions(context: SessionSelectorChangeContext) {
    if (context.mode === 'replace') loading.value = true;
    try {
      const count = await loadSessionOptions(undefined, context);
      if (!context.isCurrent() || context.mode === 'append') return count;
      const nextSession = sessions.value.find(item => item.id === selectedSessionId.value) || sessions.value[0];
      await changeSession(nextSession?.id || null);
      return count;
    } catch (error) {
      if (!context.isCurrent()) return;
      message.error((error as { message?: string }).message || '场次筛选失败');
    } finally {
      if (context.isCurrent() && context.mode === 'replace') loading.value = false;
    }
  }

  const selectorFilters = useSessionSelectorFilters(reloadFilteredSessions);

  /** 页面初始化：加载场次列表 + 自动选中最近一场 */
  async function initializePage() {
    loading.value = true;
    loadError.value = '';
    try {
      const rawSessionId = Array.isArray(route.query.sessionId) ? route.query.sessionId[0] : route.query.sessionId;
      const requestedSessionId = Number(rawSessionId);
      selectedSessionId.value = Number.isInteger(requestedSessionId) && requestedSessionId > 0 ? requestedSessionId : null;
      await Promise.all([
        loadSessionOptions(selectedSessionId.value),
        selectorFilters.loadAnchors()
      ]);
      const initialSession =
        sessions.value.find(item => item.id === requestedSessionId) ||
        sessions.value.find(item => item.live_status !== 'live') ||
        sessions.value[0];
      selectedSessionId.value = initialSession?.id || null;
      if (initialSession) {
        if (String(route.query.sessionId || '') !== String(initialSession.id)) {
          void router.replace({ query: { ...route.query, sessionId: String(initialSession.id) } });
        }
        await loadSessionContext(initialSession.id);
      }
    } catch (error) {
      loadError.value = (error as { message?: string }).message || 'AI 复盘页面加载失败';
      message.error(loadError.value);
    } finally {
      loading.value = false;
    }
  }

  /** 切换场次 */
  async function changeSession(value: number | null) {
    selectedSessionId.value = value;
    if (value && String(route.query.sessionId || '') !== String(value)) {
      void router.replace({ query: { ...route.query, sessionId: String(value) } });
    } else if (!value && route.query.sessionId) {
      const nextQuery = { ...route.query };
      delete nextQuery.sessionId;
      void router.replace({ query: nextQuery });
    }
    workbench.value = null;
    selectedSessionDetail.value = null;
    sessionReports.value = [];
    scoreResult.value = null;
    optimizeResult.value = null;
    if (value) await loadSessionContext(value);
  }

  /** 完整复盘流程：证据提取与用户转化分析由统一 AI 复盘一次生成。 */
  async function runFullReview() {
    const sessionId = selectedSessionId.value;
    if (!sessionId) return message.warning('请先选择直播场次');
    if (!analysisReady.value) return message.warning('当前数据不足，请先补齐分钟指标、评论或话术');
    try {
      actionStage.value = 'evidence';
      const findingsResponse = await generateSessionReview(sessionId);
      const findings = unwrapServiceData(findingsResponse, '统一 AI 复盘生成失败');
      if (findings.workbench) workbench.value = findings.workbench;

      await loadSessionContext(sessionId, true);
      activeTab.value = 'audience';
      message.success('统一 AI 复盘已生成，已打开最新分析结果');
    } catch (error) {
      message.error((error as { message?: string }).message || '复盘生成中断，已完成的结果仍会保留');
    } finally {
      actionStage.value = '';
    }
  }

  /** 单独重新评分 */
  async function runScore() {
    if (!selectedSessionId.value) return;
    actionStage.value = 'score-only';
    try {
      const response = await scoreSession(selectedSessionId.value);
      scoreResult.value = unwrapServiceData(response, '话术评分失败').result;
      await loadSessionContext(selectedSessionId.value, true);
      message.success('话术评分已更新');
    } catch (error) {
      message.error((error as { message?: string }).message || '话术评分失败');
    } finally {
      actionStage.value = '';
    }
  }

  /** 单独生成优化建议 */
  async function runOptimize() {
    if (!selectedSessionId.value) return;
    actionStage.value = 'optimize-only';
    try {
      const response = await optimizeSession(selectedSessionId.value);
      optimizeResult.value = unwrapServiceData(response, '优化建议生成失败').result;
      await loadSessionContext(selectedSessionId.value, true);
      message.success('下一场优化建议已更新');
    } catch (error) {
      message.error((error as { message?: string }).message || '优化建议生成失败');
    } finally {
      actionStage.value = '';
    }
  }

  /** 跳转到话术转写页面 */
  function openTranscripts() {
    router.push({
      name: 'transcripts',
      query: selectedSessionId.value ? { sessionId: String(selectedSessionId.value) } : undefined
    });
  }

  // ---- 导出 ----

  return {
    // 状态
    sessions,
    selectedSessionId,
    workbench,
    sessionReports,
    scoreResult,
    optimizeResult,
    loading,
    loadError,
    contextLoading,
    actionStage,
    activeTab,
    // 计算属性
    selectedSession,
    analysisReady,
    coveredDomainCount,
    openFindingCount,
    latestReport,
    actionBusy,
    sessionOptions,
    scoreMetrics,
    improvementSuggestions,
    nextLivePlan,
    complianceNotes,
    selectorAnchorKey: selectorFilters.anchorKey,
    selectorDateRange: selectorFilters.dateRange,
    selectorAnchorOptions: selectorFilters.anchorOptions,
    selectorHasMore: selectorFilters.hasMore,
    selectorLoadingMore: selectorFilters.loadingMore,
    // 操作
    initializePage,
    changeSession,
    runFullReview,
    runScore,
    runOptimize,
    openTranscripts,
    updateSelectorAnchor: selectorFilters.updateAnchor,
    updateSelectorDateRange: selectorFilters.updateDateRange,
    searchSelectorSessions: selectorFilters.search,
    loadMoreSelectorSessions: selectorFilters.loadMore,
    resetSelectorFilters: selectorFilters.reset,
    // 工具
    scoreLevel,
    readinessTagType,
    formatShortDateTime,
    formatFullDateTime,
    formatDuration,
    formatNumber
  };
}

// 重新导出工具函数（方便子组件只从一个地方导入）
export {
  formatFullDateTime,
  formatShortDateTime,
  formatDuration,
  formatNumber,
  scoreLevel,
  readinessTagType
} from '@/utils/analysisHelpers';
