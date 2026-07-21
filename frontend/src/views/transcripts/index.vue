<script setup lang="ts">
/**
 * 主播话术页面 — 编排器
 *
 * 职责：组合子组件，不写业务逻辑。
 * 所有状态、计算属性、异步操作都在 useTranscriptWorkbench 中管理。
 */
import { useTranscriptWorkbench } from './composables/useTranscriptWorkbench';

defineOptions({ name: 'Transcripts' });

// ── 从 composable 解构全部状态和操作 ──
// 注意：必须在 script setup 顶层解构，Vue 才会在模板中自动 unwrap ref
const wb = useTranscriptWorkbench();

const {
  // 状态
  loading,
  loadError,
  // 任务卡片
  taskStatusCards,
  taskSummary,
  // 场次控制
  selectedSessionId,
  sessionOptions,
  selectedSession,
  selectedTask,
  hasContent,
  queueLoading,
  batchLoading,
  aiLoading,
  livePreview,
  wsConnected,
  selectedSessionAvatarUrl,
  // 统计卡片
  segments,
  totalCharacters,
  coveragePercent,
  averageAiScore,
  // 内容面板
  viewMode,
  searchKeyword,
  categoryFilter,
  categoryOptions,
  filteredSegments,
  visibleSegments,
  visibleSegmentLimit,
  fullText,
  transcribedSeconds,
  categoryStats,
  // 任务抽屉
  taskDrawerVisible,
  taskFilter,
  filteredTasks,
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
} = wb;
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <!-- 加载错误 -->
    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      主播话术数据未能完整更新：{{ loadError }}
      <NButton size="small" secondary :loading="loading" @click="initializePage">重新加载</NButton>
    </NAlert>

    <!-- 1. 任务状态卡片 -->
    <TranscriptTaskCards
      :task-status-cards="taskStatusCards"
      :failed-count="taskSummary.failed"
      @open-drawer="openTaskDrawer"
    />

    <!-- 2. 场次选择 + 操作工具栏 -->
    <TranscriptSessionControl
      :session-options="sessionOptions"
      :selected-session-id="selectedSessionId"
      :loading="loading"
      :selected-session="selectedSession"
      :selected-task="selectedTask"
      :has-content="hasContent"
      :queue-loading="queueLoading"
      :batch-loading="batchLoading"
      :ai-loading="aiLoading"
      :live-preview="livePreview"
      :ws-connected="wsConnected"
      :selected-session-avatar-url="selectedSessionAvatarUrl"
      @update:selected-session-id="(val: number) => loadTranscript(val)"
      @start-transcription="startTranscription"
      @run-ai-pipeline="runAiPipeline"
      @copy-full-text="copyFullText"
      @queue-anchor-batch="queueAnchorBatch"
      @open-task-drawer="openTaskDrawer"
      @open-session-detail="openSessionDetail"
    />

    <!-- 3. 统计卡片 -->
    <TranscriptStatCards
      :visible="Boolean(selectedSessionId)"
      :segment-count="segments.length"
      :total-characters="totalCharacters"
      :coverage-percent="coveragePercent"
      :average-ai-score="averageAiScore"
    />

    <!-- 4. 话术内容面板（主内容 + 侧边栏） -->
    <TranscriptContentPanel
      :has-session="Boolean(selectedSessionId)"
      :loading="loading"
      :view-mode="viewMode"
      :search-keyword="searchKeyword"
      :category-filter="categoryFilter"
      :category-options="categoryOptions"
      :segments="segments"
      :filtered-segments="filteredSegments"
      :visible-segments="visibleSegments"
      :full-text="fullText"
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
      @update:visible="taskDrawerVisible = $event"
      @update:task-filter="taskFilter = $event"
      @select-task="selectTask"
      @open-session-detail="openSessionDetail"
    />
  </NSpace>
</template>
