<script setup lang="ts">
/**
 * 主播话术页面 — 编排器
 *
 * 职责：组合子组件，不写业务逻辑。
 * 所有状态、计算属性、异步操作都在 useTranscriptWorkbench 中管理。
 */
import { useTranscriptWorkbench } from './composables/useTranscriptWorkbench';
import TranscriptTaskCards from './components/TranscriptTaskCards.vue';
import TranscriptSessionControl from './components/TranscriptSessionControl.vue';
import TranscriptStatCards from './components/TranscriptStatCards.vue';
import TranscriptContentPanel from './components/TranscriptContentPanel.vue';
import TranscriptTaskDrawer from './components/TranscriptTaskDrawer.vue';
import SessionWorkflowNav from '@/components/business/session-workflow-nav.vue';

defineOptions({ name: 'Transcripts' });

// ── 从 composable 解构全部状态和操作 ──
// 注意：必须在 script setup 顶层解构，Vue 才会在模板中自动 unwrap ref
const wb = useTranscriptWorkbench();

const {
  // 状态
  loading,
  sessionLoading,
  loadError,
  // 任务卡片
  taskStatusCards,
  taskSummary,
  // 场次控制
  selectedSessionId,
  sessionOptions,
  selectedSession,
  selectedTask,
  selectorAnchorKey,
  selectorDateRange,
  selectorAnchorOptions,
  hasContent,
  queueLoading,
  batchLoading,
  aiLoading,
  livePreview,
  wsConnected,
  dispatchPolicy,
  dispatchPolicyLoading,
  asrRuntime,
  runtimeActionLoading,
  taskActionIds,
  // 统计卡片
  readableSegments,
  totalCharacters,
  coverageLabel,
  averageAiScore,
  contentVersion,
  contentVersionLabel,
  hiddenDuplicateCount,
  canRunAiPipeline,
  // 内容面板
  viewMode,
  searchKeyword,
  categoryFilter,
  categoryOptions,
  filteredSegments,
  visibleSegments,
  visibleSegmentLimit,
  displayedFullText,
  transcribedSeconds,
  categoryStats,
  // 任务抽屉
  taskDrawerVisible,
  taskFilter,
  filteredTasks,
  // 删除相关
  deletingTaskIds,
  clearFailedLoading,
  deleteTask,
  clearFailedTasks,
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
  retryTask,
  prioritizeTask,
  releaseTaskPriority,
  stopTask,
  restoreAsrRuntime,
  openSessionDetail,
  changeDispatchOrder,
  updateSelectorAnchor,
  updateSelectorDateRange,
  searchSelectorSessions,
  resetSelectorFilters
} = wb;
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <SessionWorkflowNav :session-id="selectedSessionId" active="transcripts" />

    <!-- 加载错误 -->
    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      主播话术数据未能完整更新：{{ loadError }}
      <NButton size="small" secondary :loading="loading" @click="initializePage">重新加载</NButton>
    </NAlert>

    <!-- 1. 当前场次工作台：先完成选择、修复和生成终稿等核心任务。 -->
    <TranscriptSessionControl
      :session-options="sessionOptions"
      :anchor-options="selectorAnchorOptions"
      :anchor-key="selectorAnchorKey"
      :date-range="selectorDateRange"
      :selected-session-id="selectedSessionId"
      :loading="sessionLoading"
      :selected-session="selectedSession"
      :selected-task="selectedTask"
      :has-content="hasContent"
      :queue-loading="queueLoading"
      :batch-loading="batchLoading"
      :ai-loading="aiLoading"
      :can-run-ai-pipeline="canRunAiPipeline"
      :content-version="contentVersion"
      :content-version-label="contentVersionLabel"
      :live-preview="livePreview"
      :ws-connected="wsConnected"
      :dispatch-policy="dispatchPolicy"
      :dispatch-policy-loading="dispatchPolicyLoading"
      :asr-runtime="asrRuntime"
      :runtime-action-loading="runtimeActionLoading"
      @update:selected-session-id="(val: number | null) => val && loadTranscript(val)"
      @update:anchor-key="updateSelectorAnchor"
      @update:date-range="updateSelectorDateRange"
      @search-sessions="searchSelectorSessions"
      @reset-filters="resetSelectorFilters"
      @start-transcription="startTranscription"
      @run-ai-pipeline="runAiPipeline"
      @copy-full-text="copyFullText"
      @queue-anchor-batch="queueAnchorBatch"
      @open-task-drawer="(status: any) => openTaskDrawer(status)"
      @open-session-detail="openSessionDetail"
      @change-dispatch-order="changeDispatchOrder"
      @restore-runtime="restoreAsrRuntime"
      @release-task-priority="releaseTaskPriority"
      @stop-task="stopTask"
    />

    <!-- 2. 当前场次数据质量 -->
    <TranscriptStatCards
      :visible="Boolean(selectedSessionId)"
      :segment-count="readableSegments.length"
      :total-characters="totalCharacters"
      :coverage-label="coverageLabel"
      :average-ai-score="averageAiScore"
      :content-version-label="contentVersionLabel"
      :hidden-duplicate-count="hiddenDuplicateCount"
    />

    <!-- 3. 全局任务队列压缩为一行，不再遮挡当前场次内容。 -->
    <TranscriptTaskCards
      :task-status-cards="taskStatusCards"
      :attention-count="taskSummary.needs_attention"
      :asr-runtime="asrRuntime"
      :runtime-action-loading="runtimeActionLoading"
      @open-drawer="(status: any) => openTaskDrawer(status)"
      @restore-runtime="restoreAsrRuntime"
    />

    <!-- 4. 话术内容工作区（主内容 + 业务结构 + 时间导航） -->
    <TranscriptContentPanel
      :has-session="Boolean(selectedSessionId)"
      :loading="loading"
      :view-mode="viewMode"
      :search-keyword="searchKeyword"
      :category-filter="categoryFilter"
      :category-options="categoryOptions"
      :segments="readableSegments"
      :filtered-segments="filteredSegments"
      :visible-segments="visibleSegments"
      :full-text="displayedFullText"
      :transcribed-seconds="transcribedSeconds"
      :category-stats="categoryStats"
      @update:search-keyword="searchKeyword = $event"
      @update:category-filter="categoryFilter = $event"
      @update:view-mode="viewMode = $event"
      @load-more="visibleSegmentLimit += 80"
      @jump-to-segment="jumpToSegment"
      @copy-segment="(text: string) => copyText(text, '该段话术已复制')"
      @filter-by-category="
        categoryFilter = $event;
        viewMode = 'segments';
      "
    />

    <!-- 5. 任务抽屉 -->
    <TranscriptTaskDrawer
      :visible="taskDrawerVisible"
      :task-filter="taskFilter"
      :filtered-tasks="filteredTasks"
      :clear-failed-loading="clearFailedLoading"
      :deleting-task-ids="deletingTaskIds"
      :task-action-ids="taskActionIds"
      :asr-runtime="asrRuntime"
      :dispatch-policy="dispatchPolicy"
      @update:visible="taskDrawerVisible = $event"
      @update:task-filter="taskFilter = $event"
      @select-task="selectTask"
      @open-session-detail="openSessionDetail"
      @delete-task="deleteTask"
      @retry-task="retryTask"
      @prioritize-task="prioritizeTask"
      @release-task-priority="releaseTaskPriority"
      @stop-task="stopTask"
      @clear-failed-tasks="clearFailedTasks"
    />
  </NSpace>
</template>
