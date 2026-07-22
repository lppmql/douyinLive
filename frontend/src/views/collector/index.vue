<!--
  采集页 — 编排器（方案 A 重构后，二轮瘦身）
  职责：组合子组件 + 生命周期管理。所有状态和业务逻辑委托给 composable。
  752 行 → ~220 行
-->
<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted } from 'vue';
import { NAlert, NButton, NSpace, NSpin, NGi, NGrid, useDialog, useMessage } from 'naive-ui';

/* ---- 子组件 ---- */
import CollectorStatCards from './modules/CollectorStatCards.vue';
import CollectorRefreshCard from './modules/CollectorRefreshCard.vue';
import CollectorMonitorCard from './modules/CollectorMonitorCard.vue';
import CollectorDataEaseCard from './modules/CollectorDataEaseCard.vue';
import CollectorAccountTable from './modules/CollectorAccountTable.vue';
import CollectorLogTable from './modules/CollectorLogTable.vue';
import CollectorTaskDrawer from './modules/CollectorTaskDrawer.vue';
import CollectorLogDetailModal from './modules/CollectorLogDetailModal.vue';
import CollectorQRLogin from './modules/CollectorQRLogin.vue';

/* ---- 组合式函数 ---- */
import { useCollectorPolling } from './composables/useCollectorPolling';
import { useCollectorData } from './composables/useCollectorData';
import { useCollectorLogin } from './composables/useCollectorLogin';

defineOptions({ name: 'Collector' });

const message = useMessage();
const dialog = useDialog();

// ── 核心数据和操作（"大脑"）──
const data = useCollectorData(message, dialog);

// ── 扫码登录流程 ──
const login = useCollectorLogin(() => data.loadData());

// ── 轮询 & 时钟 ──
const { now, startPolling, stopPolling, startClock, stopClock } = useCollectorPolling(
  () => data.collectionRunning.value || Boolean(data.collectorStatus.value?.active_task_count) || data.taskDrawerVisible.value,
  () => data.loadData(true)
);

// ── 生命周期 ──
onMounted(() => {
  data.loadData();
  startPolling();
  startClock();
});

onActivated(() => {
  data.loadData(true);
  startPolling();
  startClock();
});

onDeactivated(() => {
  login.stopLoginPoll();
  stopPolling();
  stopClock();
});

onUnmounted(() => {
  login.stopLoginPoll();
  stopPolling();
  stopClock();
});
</script>

<template>
  <div class="business-page min-h-full">
    <!-- 数据加载异常提示 -->
    <NAlert v-if="data.dataLoadFailedCount.value" type="warning" :bordered="false" show-icon>
      有 {{ data.dataLoadFailedCount.value }} 项采集状态暂时未更新，页面已保留其余真实结果。
      <span v-if="data.lastDataUpdatedAt.value" class="ml-6px text-12px text-gray-500">
        最近尝试 {{ new Date(data.lastDataUpdatedAt.value).toLocaleTimeString('zh-CN', { hour12: false }) }}
      </span>
      <NButton size="small" secondary :loading="data.loading.value" @click="() => data.loadData()">重新加载</NButton>
    </NAlert>

    <NSpin :show="data.loading.value && !data.collectorStatus.value" class="business-loading-panel">
      <NSpace vertical :size="16">
        <!-- 1. 顶部 4 张统计卡片 -->
        <CollectorStatCards
          :collector-status="data.collectorStatus.value"
          :accounts-length="data.accounts.value.length"
          :logged-in-count="data.loggedInAccountCount.value"
          :monitor-status="data.monitorStatus.value"
          :error-log-count="data.errorLogCount.value"
          :historical-error-count="data.historicalErrorCount.value"
          @open-accounts="data.openAccounts"
          @open-tasks="data.openTasks"
          @open-errors="data.openErrors"
        />

        <!-- 2. 刷新采集 + 实时监控（左右布局） -->
        <NGrid cols="1 l:3" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:2">
            <CollectorRefreshCard
              :collect-all-loading="data.collectAllLoading.value"
              :has-available-account="data.hasAvailableAccount.value"
              :current-collect-task="data.currentCollectTask.value"
              :asr-status="data.asrStatus.value"
              :asr-control-loading="data.asrControlLoading.value"
              :collect-disabled-reason="data.collectDisabledReason.value"
              :collect-all-result="data.collectAllResult.value"
              @collect-all="data.handleCollectAll"
              @toggle-asr="data.handleAsrToggle"
            />
          </NGi>
          <NGi>
            <CollectorMonitorCard
              :monitor-status="data.monitorStatus.value"
              :monitor-loading="data.monitorLoading.value"
              @start="data.handleStartMonitor"
              @stop="data.handleStopMonitor"
              @trigger-live="data.handleTriggerLive"
              @trigger-end="data.handleTriggerEnd"
            />
          </NGi>
        </NGrid>

        <!-- 3. DataEase 数据集 -->
        <CollectorDataEaseCard
          :data-ease-status="data.dataEaseStatus.value"
          :data-ease-sync-loading="data.dataEaseSyncLoading.value"
          @sync="data.handleDataEaseSync"
        />

        <!-- 4. 账号表格 -->
        <div
          ref="(el) => { data.accountSectionRef.value = el as HTMLElement | null; }"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': data.accountHighlight.value }"
        >
          <CollectorAccountTable
            :loading="data.loading.value"
            :accounts="data.accounts.value"
            :account-health-loading-id="data.accountHealthLoadingId.value"
            :collection-running="data.collectionRunning.value"
            :monitor-running="Boolean(data.monitorStatus.value?.running)"
            @refresh="() => data.loadData()"
            @start-login="login.handleStartLogin"
            @health-check="data.handleAccountHealth"
            @re-login="login.handleReLogin"
            @delete-account="data.handleDeleteAccount"
          />
        </div>

        <!-- 5. 采集日志表格 -->
        <div
          ref="(el) => { data.logSectionRef.value = el as HTMLElement | null; }"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': data.logHighlight.value }"
        >
          <CollectorLogTable
            :loading="data.loading.value"
            :silent-refreshing="data.silentRefreshing.value"
            :clear-logs-loading="data.clearLogsLoading.value"
            :logs="data.logs.value"
            :log-level="data.logLevel.value"
            :log-task-id="data.logTaskId.value"
            :now="now"
            @refresh="() => data.loadData()"
            @clear="data.handleClearLogs"
            @filter="data.filterLogs"
            @clear-task-filter="data.clearTaskLogFilter"
            @open-detail="data.openLogDetail"
          />
        </div>
      </NSpace>
    </NSpin>

    <!-- 6. 任务队列抽屉 -->
    <CollectorTaskDrawer
      v-model:visible="data.taskDrawerVisible.value"
      :tasks="data.tasks.value"
      :now="now"
      @view-logs="data.viewTaskLogs"
    />

    <!-- 7. 日志详情弹窗 -->
    <CollectorLogDetailModal
      v-model:visible="data.logDetailVisible.value"
      :log="data.selectedLog.value"
    />

    <!-- 8. 扫码登录弹窗 -->
    <CollectorQRLogin
      :visible="login.showQRModal.value"
      :qr-image="login.qrImage.value"
      :status="login.loginStatus.value"
      :message="login.loginMessage.value"
      @close="login.closeQRModal"
      @retry="login.handleStartLogin"
    />
  </div>
</template>

<style scoped>
/*
 * 所有组件样式已移到各自子组件的 <style scoped> 中。
 * 这里只保留最小化的编排器样式（如果有的话）。
 */
</style>
