import { computed, h, ref } from 'vue';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';

import { unwrapServiceData } from '@/utils/service';
import {
  fetchAnalysisReports,
  fetchLiveSessions,
  fetchReviewWorkbench,
  generateSessionReview,
  getLiveSessionAvatarUrl,
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

// ========== 类型定义 ==========

/** 操作阶段：空字符串 = 空闲，其他值为具体阶段 */
export type ActionStage = '' | 'evidence' | 'score' | 'optimize' | 'score-only' | 'optimize-only';

/** 场次下拉选项（扩展 SelectOption，带主播头像信息） */
export type SessionSelectOption = SelectOption & {
  anchorName: string;
  avatarUrl: string | null;
};

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

  // ---- 响应式状态 ----

  const sessions = ref<Api.Douyin.LiveSession[]>([]);
  const selectedSessionId = ref<number | null>(null);
  const workbench = ref<Api.Douyin.ReviewWorkbench | null>(null);
  const sessionReports = ref<Api.Douyin.AnalysisReport[]>([]);
  const scoreResult = ref<Api.Douyin.AiScoreResult | null>(null);
  const optimizeResult = ref<Api.Douyin.AiOptimizationResult | null>(null);
  const loading = ref(true);
  const loadError = ref('');
  const contextLoading = ref(false);
  const actionStage = ref<ActionStage>('');
  const activeTab = ref<'overview' | 'evidence' | 'history'>('overview');

  /** 防止异步竞态：每次发起新的上下文加载时 +1，回调里检查是否还是最新请求 */
  let contextRequestId = 0;

  // ---- 计算属性 ----

  /** 当前选中的场次对象 */
  const selectedSession = computed(() =>
    sessions.value.find(item => item.id === selectedSessionId.value) || null
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

  /** 当前选中场次的主播头像 URL（供子组件直接使用） */
  const selectedSessionAvatarUrl = computed(() => {
    if (!selectedSession.value) return undefined;
    return getSessionAvatarUrl(selectedSession.value);
  });

  /** 是否有操作正在进行中 */
  const actionBusy = computed(() => Boolean(actionStage.value));

  /** 场次下拉选项列表（含主播头像信息） */
  const sessionOptions = computed(() =>
    sessions.value.map<SessionSelectOption>(session => ({
      value: session.id,
      label: `${session.anchor_name || '未知主播'} · ${formatShortDateTime(session.live_start_time)} · ${formatDuration(session.live_duration_seconds)} · ${session.live_status === 'live' ? '直播中' : '已结束'}`,
      anchorName: session.anchor_name || '未知主播',
      avatarUrl: session.anchor_avatar_url ? getLiveSessionAvatarUrl(session.id) : null
    }))
  );

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

  // ---- 异步操作 ----

  /** 加载单个场次的复盘上下文（工作台 + 报告列表） */
  async function loadSessionContext(sessionId: number, silent = false) {
    const requestId = ++contextRequestId;
    if (!silent) contextLoading.value = true;
    try {
      const [workbenchResponse, reportsResponse] = await Promise.all([
        fetchReviewWorkbench(sessionId),
        fetchAnalysisReports({ sessionId, limit: 100 })
      ]);
      if (requestId !== contextRequestId) return;
      workbench.value = unwrapServiceData(workbenchResponse, '复盘证据读取失败');
      sessionReports.value = unwrapServiceData(reportsResponse, '分析报告读取失败');
      restoreSavedReports(sessionReports.value);
    } catch (error) {
      if (requestId !== contextRequestId) return;
      workbench.value = null;
      sessionReports.value = [];
      scoreResult.value = null;
      optimizeResult.value = null;
      if (!silent) message.error((error as { message?: string }).message || '复盘上下文加载失败');
    } finally {
      if (requestId === contextRequestId) contextLoading.value = false;
    }
  }

  /** 页面初始化：加载场次列表 + 自动选中最近一场 */
  async function initializePage() {
    loading.value = true;
    loadError.value = '';
    try {
      const sessionsResponse = await fetchLiveSessions();
      sessions.value = sortSessionsByLatest(
        unwrapServiceData(sessionsResponse, '直播场次读取失败')
      );
      const latestSession = sessions.value[0];
      selectedSessionId.value = latestSession?.id || null;
      if (latestSession) await loadSessionContext(latestSession.id);
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
    workbench.value = null;
    sessionReports.value = [];
    scoreResult.value = null;
    optimizeResult.value = null;
    if (value) await loadSessionContext(value);
  }

  /** 完整复盘流程：证据提取 → 评分 → 优化建议 */
  async function runFullReview() {
    const sessionId = selectedSessionId.value;
    if (!sessionId) return message.warning('请先选择直播场次');
    if (!analysisReady.value) return message.warning('当前数据不足，请先补齐分钟指标、评论或话术');
    try {
      actionStage.value = 'evidence';
      const findingsResponse = await generateSessionReview(sessionId);
      const findings = unwrapServiceData(findingsResponse, '真实证据提取失败');
      if (findings.workbench) workbench.value = findings.workbench;

      actionStage.value = 'score';
      const scoreResponse = await scoreSession(sessionId);
      scoreResult.value = unwrapServiceData(scoreResponse, '话术评分失败').result;

      actionStage.value = 'optimize';
      const optimizeResponse = await optimizeSession(sessionId);
      optimizeResult.value = unwrapServiceData(optimizeResponse, '优化建议生成失败').result;

      await loadSessionContext(sessionId, true);
      activeTab.value = 'overview';
      message.success('完整复盘已生成，报告已保存');
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
    router.push({ name: 'transcripts' });
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
    selectedSessionAvatarUrl,
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
    // 渲染辅助
    renderSessionLabel,
    getSessionAvatarUrl,
    // 操作
    initializePage,
    changeSession,
    runFullReview,
    runScore,
    runOptimize,
    openTranscripts,
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
