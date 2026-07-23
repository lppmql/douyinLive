<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted } from 'vue';
import { NAlert, NButton, NSpace, NSpin, useDialog, useMessage } from 'naive-ui';
import CollectorAccountTable from './modules/CollectorAccountTable.vue';
import CollectorControlCenter from './modules/CollectorControlCenter.vue';
import CollectorLogDetailModal from './modules/CollectorLogDetailModal.vue';
import CollectorLogTable from './modules/CollectorLogTable.vue';
import CollectorQRLogin from './modules/CollectorQRLogin.vue';
import CollectorTaskDrawer from './modules/CollectorTaskDrawer.vue';
import { useCollectorData } from './composables/useCollectorData';
import { useCollectorLogin } from './composables/useCollectorLogin';
import { useCollectorPolling } from './composables/useCollectorPolling';

defineOptions({ name: 'Collector' });

const data = useCollectorData(useMessage(), useDialog());
const login = useCollectorLogin(() => data.loadData());
const { now, startPolling, stopPolling, startClock, stopClock } = useCollectorPolling(
  () => data.shouldPoll.value,
  () => data.loadData(true, false)
);

onMounted(() => {
  void data.loadData();
  startPolling();
  startClock();
});

onActivated(() => {
  void data.loadData(true);
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
  <NSpace vertical :size="16" class="business-page">
    <NAlert v-if="data.dataLoadFailedCount.value" type="warning" :bordered="false" show-icon>
      有 {{ data.dataLoadFailedCount.value }} 项状态暂时未更新，页面已保留其余真实结果。
      <NButton size="small" secondary :loading="data.loading.value" @click="data.loadData()">重新加载</NButton>
    </NAlert>

    <NSpin :show="data.loading.value && !data.controlCenter.value" class="business-loading-panel">
      <NSpace vertical :size="16">
        <CollectorControlCenter
          :modules="data.controlCenter.value?.modules || []"
          :active-task-count="data.controlCenter.value?.active_task_count || 0"
          :queued-task-count="data.controlCenter.value?.queued_task_count || 0"
          :loading-keys="data.moduleLoadingKeys.value"
          :has-available-account="data.hasAvailableAccount.value"
          :refreshing="data.silentRefreshing.value"
          :resource-usage="data.controlCenter.value?.resource_usage || null"
          @toggle="data.handleModuleToggle"
          @run="data.handleDataRefresh"
          @open-tasks="data.taskDrawerVisible.value = true"
          @refresh="data.loadData(true)"
        />

        <div
          :ref="data.setAccountSectionRef"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': data.accountHighlight.value }"
        >
          <CollectorAccountTable
            :loading="data.loading.value"
            :accounts="data.accounts.value"
            :account-health-loading-id="data.accountHealthLoadingId.value"
            :collection-running="data.collectionRunning.value"
            @refresh="data.loadData()"
            @start-login="login.handleStartLogin"
            @health-check="data.handleAccountHealth"
            @re-login="login.handleReLogin"
            @delete-account="data.handleDeleteAccount"
          />
        </div>

        <div
          :ref="data.setLogSectionRef"
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
            @refresh="data.loadData()"
            @clear="data.handleClearLogs"
            @filter="data.filterLogs"
            @clear-task-filter="data.clearTaskLogFilter"
            @open-detail="data.openLogDetail"
          />
        </div>
      </NSpace>
    </NSpin>

    <CollectorTaskDrawer
      v-model:visible="data.taskDrawerVisible.value"
      :tasks="data.tasks.value"
      :now="now"
      :action-loading-key="data.taskActionLoadingKey.value"
      @view-logs="data.viewTaskLogs"
      @stop="data.handleStopTask"
      @retry="data.handleRetryTask"
    />

    <CollectorLogDetailModal
      v-model:visible="data.logDetailVisible.value"
      :log="data.selectedLog.value"
    />

    <CollectorQRLogin
      :visible="login.showQRModal.value"
      :qr-image="login.qrImage.value"
      :status="login.loginStatus.value"
      :message="login.loginMessage.value"
      @close="login.closeQRModal"
      @retry="login.handleStartLogin"
    />
  </NSpace>
</template>
