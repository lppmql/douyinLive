<script setup lang="ts">
/**
 * AI 复盘页面 — 编排器
 *
 * 职责：组合 useReviewWorkbench composable + 传递 props 给 5 个子组件。
 * 自身只处理顶层状态（加载骨架 / 错误 / 空状态 / 数据不足警告）。
 *
 * 子组件分工：
 * - AnalysisSessionControl  — 场次搜索 + 复盘启动面板
 * - AnalysisStatCards       — 4 张统计卡片
 * - AnalysisScoreOverview   — 复盘总览 Tab（评分 + 优缺点 + 动作计划）
 * - AnalysisEvidence        — 证据与发现 Tab（领域覆盖 + 复盘发现 + 话术证据）
 * - AnalysisReportHistory   — 历史报告 Tab
 */

import { onMounted } from 'vue';
import { useReviewWorkbench } from './composables/useReviewWorkbench';
import AnalysisSessionControl from './components/AnalysisSessionControl.vue';
import AnalysisStatCards from './components/AnalysisStatCards.vue';
import AnalysisScoreOverview from './components/AnalysisScoreOverview.vue';
import AnalysisEvidence from './components/AnalysisEvidence.vue';
import AnalysisReportHistory from './components/AnalysisReportHistory.vue';
import SessionWorkflowNav from '@/components/business/session-workflow-nav.vue';

defineOptions({ name: 'Analysis' });

// ---- 解构 composable（顶层解构 → 模板自动解包 ref） ----

const {
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
  // 操作
  initializePage,
  changeSession,
  runFullReview,
  runScore,
  runOptimize,
  openTranscripts
} = useReviewWorkbench();

onMounted(initializePage);
</script>

<template>
  <NSpace vertical :size="16" class="analysis-page business-page" :aria-busy="loading">
    <SessionWorkflowNav :session-id="selectedSessionId" active="analysis" />

    <!-- 加载失败（且无缓存数据） -->
    <NResult
      v-if="loadError && !sessions.length"
      status="error"
      title="AI 复盘数据暂时无法读取"
      :description="loadError"
      class="card-wrapper bg-white py-32px dark:bg-dark"
    >
      <template #footer>
        <NButton type="primary" :loading="loading" @click="initializePage">重新加载</NButton>
      </template>
    </NResult>

    <!-- 首次加载骨架 -->
    <NCard v-if="loading && !sessions.length" :bordered="false" class="business-loading-panel card-wrapper">
      <NSkeleton text :repeat="2" />
      <NSkeleton class="mt-18px" height="120px" :sharp="false" />
    </NCard>

    <!-- 主内容区 -->
    <template v-if="!loadError || sessions.length">
      <!-- 场次选择控制卡片 -->
      <AnalysisSessionControl
        :sessions="sessions"
        :selected-session-id="selectedSessionId"
        :loading="loading"
        :session-options="sessionOptions"
        :selected-session="selectedSession"
        :action-busy="actionBusy"
        :action-stage="actionStage"
        :latest-report="latestReport"
        :analysis-ready="analysisReady"
        :score-result="scoreResult"
        :workbench="workbench"
        @update:selected-session-id="changeSession"
        @run-full-review="runFullReview"
      />

      <!-- 数据不足警告 -->
      <NAlert
        v-if="selectedSessionId && workbench && !analysisReady"
        type="warning"
        show-icon
        :bordered="false"
      >
        <template #header>当前数据不足以形成稳定 AI 结论</template>
        数据可以回看，但请先补齐分钟指标、评论或 ASR 话术后再运行完整复盘。
        <NButton text type="primary" class="ml-6px" @click="openTranscripts">前往主播话术</NButton>
      </NAlert>

      <!-- 统计卡片 -->
      <AnalysisStatCards
        :selected-session="selectedSession"
        :score-result="scoreResult"
        :workbench="workbench"
        :open-finding-count="openFindingCount"
      />

      <!-- 标签页内容 -->
      <NCard v-if="selectedSessionId" :bordered="false" class="card-wrapper content-card">
        <NTabs v-model:value="activeTab" type="line" animated>
          <NTabPane name="overview" tab="复盘总览">
            <NSpin :show="contextLoading">
              <AnalysisScoreOverview
                :score-result="scoreResult"
                :optimize-result="optimizeResult"
                :score-metrics="scoreMetrics"
                :improvement-suggestions="improvementSuggestions"
                :next-live-plan="nextLivePlan"
                :compliance-notes="complianceNotes"
                :action-stage="actionStage"
                :action-busy="actionBusy"
                :analysis-ready="analysisReady"
                @run-score="runScore"
                @run-optimize="runOptimize"
                @run-full-review="runFullReview"
              />
            </NSpin>
          </NTabPane>

          <NTabPane name="evidence" :tab="`证据与发现 (${workbench?.findings.length || 0})`">
            <NSpin :show="contextLoading">
              <AnalysisEvidence
                :workbench="workbench"
                :score-result="scoreResult"
                :covered-domain-count="coveredDomainCount"
                :analysis-ready="analysisReady"
                :action-busy="actionBusy"
                @run-full-review="runFullReview"
              />
            </NSpin>
          </NTabPane>

          <NTabPane name="history" :tab="`历史报告 (${sessionReports.length})`">
            <AnalysisReportHistory :session-reports="sessionReports" />
          </NTabPane>
        </NTabs>
      </NCard>
    </template>

    <!-- 无场次空状态 -->
    <NResult
      v-if="!loading && !sessions.length && !loadError"
      status="warning"
      title="暂无可复盘场次"
      description="请先完成真实直播场次采集。"
    />
  </NSpace>
</template>

<style scoped>
.analysis-page {
  --analysis-line: rgba(148, 163, 184, 0.18);
}

.content-card :deep(.n-card__content) {
  padding-top: 10px;
}
</style>
