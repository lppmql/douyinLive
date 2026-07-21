<!--
  采集页 — 编排器（方案 A 重构后）
  职责：持有所有状态、拉取数据、处理业务逻辑，把 UI 委托给子组件渲染
  从 1438 行精简到 ~450 行
-->
<script setup lang="ts">
import { computed, h, onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue';
import { NAlert, NButton, NSpace, NSpin, NGi, NGrid, NTag, useDialog, useMessage } from 'naive-ui';
import { $t } from '@/locales';

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

/* ---- 工具 & 组合式函数 ---- */
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';
import { parseBackendTime, formatLogTime, formatFullTime, getStageLabel, getLogPayload, getLogSummary } from './utils/collectorHelpers';
import { useCollectorPolling } from './composables/useCollectorPolling';
import {
  fetchCollectorStatus,
  fetchCollectorAccounts,
  fetchCollectorLogs,
  clearCollectorLogs,
  startCollectorLogin,
  fetchLoginQR,
  fetchLoginStatus,
  reCollectorLogin,
  deleteCollectorAccount,
  checkCollectorAccountHealth,
  fetchCollectorTasks,
  fetchAsrControlStatus,
  setAsrControl,
  fetchDataEaseStatus,
  syncDataEase,
  fetchMonitorStatus,
  startMonitor,
  stopMonitor,
  triggerMockLive,
  triggerMockEnd,
  collectAllData
} from '@/service/api/douyin';

defineOptions({ name: 'Collector' });

const message = useMessage();
const dialog = useDialog();

/* ========== 状态 ========== */

const loading = ref(true);
const collectorStatus = ref<Api.Douyin.CollectorStatus | null>(null);
const accounts = ref<Api.Douyin.CollectorAccount[]>([]);
const logs = ref<Api.Douyin.CollectorLog[]>([]);
const tasks = ref<Api.Douyin.CollectorTask[]>([]);

/** 页面滚动定位相关 */
const accountSectionRef = ref<HTMLElement | null>(null);
const logSectionRef = ref<HTMLElement | null>(null);
const accountHighlight = ref(false);
const logHighlight = ref(false);

/** 日志筛选 */
const logLevel = ref('all');
const logTaskId = ref<number | null>(null);

/** 日志操作状态 */
const silentRefreshing = ref(false);
const clearLogsLoading = ref(false);
const logDetailVisible = ref(false);
const selectedLog = ref<Api.Douyin.CollectorLog | null>(null);

/** 账号操作状态 */
const accountHealthLoadingId = ref<number | null>(null);

/** ASR 话术服务 */
const asrStatus = ref<Api.Douyin.AsrControlStatus | null>(null);
const asrControlLoading = ref(false);

/** DataEase 同步 */
const dataEaseStatus = ref<Api.Douyin.DataEaseStatus | null>(null);
const dataEaseSyncLoading = ref(false);

/** 数据加载状态 */
const dataLoadFailedCount = ref(0);
const lastDataUpdatedAt = ref<number | null>(null);

/** 监控 */
const monitorStatus = ref<Api.Douyin.MonitorStatus | null>(null);
const monitorLoading = ref(false);

/** 刷新数据采集 */
const collectAllLoading = ref(false);
const collectAllResult = ref<Api.Douyin.CollectAllResponse | null>(null);

/** 任务抽屉 */
const taskDrawerVisible = ref(false);

/** 扫码登录 */
type LoginState = 'idle' | 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';
const showQRModal = ref(false);
const qrImage = ref('');
const loginTaskId = ref<number | null>(null);
const loginStatus = ref<LoginState>('idle');
const loginMessage = ref('');
let loginPollTimer: number | null = null;

/* ========== 计算属性 ========== */

const loggedInAccountCount = computed(() => accounts.value.filter(item => item.login_status === 'logged_in').length);

const latestSuccessfulCollectTime = computed(() => {
  const task = tasks.value.find(item => item.task_type === 'collect_all' && item.status === 'completed');
  const value = task?.completed_at || task?.created_at;
  return value ? parseBackendTime(value) : 0;
});

const errorLogCount = computed(
  () =>
    logs.value.filter(
      item => item.level === 'error' && parseBackendTime(item.created_at) > latestSuccessfulCollectTime.value
    ).length
);

const historicalErrorCount = computed(() => logs.value.filter(item => item.level === 'error').length);
const hasAvailableAccount = computed(() => loggedInAccountCount.value > 0);
const activeTasks = computed(() => tasks.value.filter(item => ['pending', 'running'].includes(item.status)));
const currentCollectTask = computed(() => tasks.value.find(item => item.task_type === 'collect_all'));
const collectionRunning = computed(
  () => collectAllLoading.value || activeTasks.value.some(item => item.task_type === 'collect_all')
);
const collectDisabledReason = computed(() => {
  if (!hasAvailableAccount.value) return '请先扫码登录可用采集账号';
  if (collectionRunning.value) return '已有刷新数据采集任务正在运行，请勿重复提交';
  return '';
});

/* ========== 数据加载 ========== */

/** 并行拉取 7 个 API，静默模式下不显示全屏 loading */
async function loadData(silent = false) {
  if (silent) silentRefreshing.value = true;
  else loading.value = true;
  try {
    const [statusRes, accountsRes, logsRes, tasksRes, monitorRes, asrRes, dataEaseRes] = await Promise.allSettled([
      fetchCollectorStatus(),
      fetchCollectorAccounts(),
      fetchCollectorLogs({
        limit: 100,
        level: logLevel.value === 'all' ? undefined : logLevel.value,
        task_id: logTaskId.value || undefined
      }),
      fetchCollectorTasks(),
      fetchMonitorStatus(),
      fetchAsrControlStatus(),
      fetchDataEaseStatus()
    ]);
    if (statusRes.status === 'fulfilled' && statusRes.value.data != null) collectorStatus.value = statusRes.value.data;
    if (accountsRes.status === 'fulfilled' && accountsRes.value.data != null) accounts.value = accountsRes.value.data;
    if (logsRes.status === 'fulfilled' && logsRes.value.data != null) logs.value = logsRes.value.data;
    if (tasksRes.status === 'fulfilled' && tasksRes.value.data != null) tasks.value = tasksRes.value.data;
    if (monitorRes.status === 'fulfilled' && monitorRes.value.data != null) monitorStatus.value = monitorRes.value.data;
    if (asrRes.status === 'fulfilled' && asrRes.value.data != null) asrStatus.value = asrRes.value.data;
    if (dataEaseRes.status === 'fulfilled' && dataEaseRes.value.data != null) {
      dataEaseStatus.value = dataEaseRes.value.data;
    }

    const failedCount = [statusRes, accountsRes, logsRes, tasksRes, monitorRes, asrRes, dataEaseRes].filter(
      result => result.status === 'rejected' || Boolean(result.value.error)
    ).length;
    dataLoadFailedCount.value = failedCount;
    lastDataUpdatedAt.value = Date.now();
    if (failedCount && !silent) message.warning(`${failedCount} 项数据暂时加载失败，其他区域已正常更新`);
  } catch {
    dataLoadFailedCount.value = 7;
    if (!silent) message.error('加载采集数据失败');
  } finally {
    if (silent) silentRefreshing.value = false;
    else loading.value = false;
  }
}

/* ========== 监控操作 ========== */

async function handleStartMonitor() {
  monitorLoading.value = true;
  try {
    const res = await startMonitor();
    const data = unwrapServiceData(res, '启动监控失败');
    if (data.success) message.success(data.message);
    await loadData(true);
  } catch {
    message.error('启动监控失败');
  } finally {
    monitorLoading.value = false;
  }
}

async function handleStopMonitor() {
  monitorLoading.value = true;
  try {
    const res = await stopMonitor();
    const data = unwrapServiceData(res, '停止监控失败');
    if (data.success) message.success(data.message);
    await loadData(true);
  } catch {
    message.error('停止监控失败');
  } finally {
    monitorLoading.value = false;
  }
}

async function handleTriggerLive() {
  const res = await triggerMockLive();
  const data = unwrapServiceData(res, '模拟开播失败');
  if (data.success) message.success(data.message);
  else message.warning(data.message || '模拟开播失败');
  await loadData(true);
}

async function handleTriggerEnd() {
  const res = await triggerMockEnd();
  const data = unwrapServiceData(res, '模拟下播失败');
  if (data.success) message.success(data.message);
  await loadData(true);
}

/* ========== 刷新数据采集 ========== */

async function handleCollectAll() {
  collectAllLoading.value = true;
  collectAllResult.value = null;
  try {
    const res = await collectAllData();
    const data = unwrapServiceData(res, '刷新数据采集失败');
    collectAllResult.value = data;
    if (data.collected_rooms > 0) {
      message.success(`采集完成：${data.collected_rooms}/${data.total_rooms} 个房间`);
      message.info(`全部场次检查完成，本次补齐 ${data.history_detail_synced_count || 0} 场详情`);
    } else if (data.message) {
      message.warning(data.message);
    }
  } catch {
    await loadData(true);
    const latestTask = tasks.value.find(item => item.task_type === 'collect_all');
    if (latestTask?.status === 'completed') {
      message.success(`后台采集已完成：同步 ${latestTask.collected_session_count} 场`);
    } else if (latestTask?.status === 'running') {
      message.info(`任务 #${latestTask.id} 仍在后台运行，页面将继续自动更新`);
    } else {
      message.error(latestTask?.error_message || '刷新数据采集失败');
    }
  } finally {
    collectAllLoading.value = false;
    await loadData();
  }
}

/* ========== DataEase ========== */

async function handleDataEaseSync() {
  dataEaseSyncLoading.value = true;
  try {
    const res = await syncDataEase();
    const data = unwrapServiceData(res, 'DataEase 同步失败');
    dataEaseStatus.value = data.dataease;
    const text = `DataEase 同步完成：成功 ${data.synced_count} 场，失败 ${data.failed_count} 场，清理旧宽表 ${data.removed_stale_row_count} 行`;
    if (data.failed_count) message.warning(text);
    else message.success(text);
  } catch {
    message.error('DataEase 同步失败，请查看后端日志');
  } finally {
    dataEaseSyncLoading.value = false;
  }
}

/* ========== ASR 话术 ========== */

async function applyAsrToggle(enabled: boolean) {
  asrControlLoading.value = true;
  try {
    const res = await setAsrControl(enabled);
    const data = unwrapServiceData(res, `ASR 话术服务${enabled ? '开启' : '关闭'}失败`);
    asrStatus.value = data;
    message.success(data.message);
  } catch {
    message.error(`ASR 话术服务${enabled ? '开启' : '关闭'}失败`);
    await loadData(true);
  } finally {
    asrControlLoading.value = false;
  }
}

function handleAsrToggle(enabled: boolean) {
  if (!enabled && asrStatus.value?.processing_count) {
    dialog.warning({
      title: '确认停止 ASR',
      content: `当前有 ${asrStatus.value.processing_count} 个话术任务正在生成。停止后会中断任务并立即释放模型内存，是否继续？`,
      positiveText: '停止并释放内存',
      negativeText: '继续生成',
      onPositiveClick: () => applyAsrToggle(false)
    });
    return;
  }
  void applyAsrToggle(enabled);
}

/* ========== 日志操作 ========== */

async function filterLogs(level: string) {
  logLevel.value = level;
  await loadData(true);
  scrollToSection(logSectionRef, logHighlight);
}

async function viewTaskLogs(taskId: number) {
  logTaskId.value = taskId;
  logLevel.value = 'all';
  taskDrawerVisible.value = false;
  await loadData(true);
  scrollToSection(logSectionRef, logHighlight);
}

async function clearTaskLogFilter() {
  logTaskId.value = null;
  await loadData(true);
}

function handleClearLogs() {
  dialog.warning({
    title: '清空采集日志',
    content:
      '确定清空数据库中现有的全部采集日志吗？此操作不会删除采集任务、账号、主播或直播场次；正在运行的任务后续产生的新日志仍会继续显示。',
    positiveText: '确认清空日志',
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      clearLogsLoading.value = true;
      try {
        const response = await clearCollectorLogs();
        const deletedCount = unwrapServiceData(response, '清空采集日志失败').deleted_count || 0;
        logs.value = [];
        selectedLog.value = null;
        logDetailVisible.value = false;
        message.success(`已清空 ${deletedCount} 条采集日志`);
        await loadData(true);
      } catch {
        message.error('清空采集日志失败，请稍后重试');
      } finally {
        clearLogsLoading.value = false;
      }
    }
  });
}

function scrollToSection(section: typeof accountSectionRef, highlight: typeof accountHighlight) {
  section.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  highlight.value = true;
  window.setTimeout(() => {
    highlight.value = false;
  }, 1800);
}

/* ========== 导航辅助 ========== */

function openAccounts() {
  scrollToSection(accountSectionRef, accountHighlight);
}

function openTasks() {
  taskDrawerVisible.value = true;
}

async function openErrors() {
  await filterLogs('error');
}

/* ========== 账号操作 ========== */

async function handleAccountHealth(row: Api.Douyin.CollectorAccount) {
  accountHealthLoadingId.value = row.id;
  try {
    const res = await checkCollectorAccountHealth(row.id);
    const data = unwrapServiceData(res, '账号存活检查失败');
    if (data.valid) message.success(data.message);
    else message.warning(data.message || '账号登录状态已失效');
    await loadData(true);
  } catch {
    message.error('账号存活检查失败');
  } finally {
    accountHealthLoadingId.value = null;
  }
}

async function handleReLogin(accountId: number) {
  try {
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
    const res = await reCollectorLogin(accountId);
    const data = unwrapServiceData(res, '启动重新登录失败');
    loginTaskId.value = data.task_id;
    loginStatus.value = 'pending';
    loginMessage.value = '';
    showQRModal.value = true;
    pollLoginStatus();
  } catch {
    message.error('启动重新登录失败');
  }
}

async function handleDeleteAccount(accountId: number) {
  const account = accounts.value.find(item => item.id === accountId);
  dialog.warning({
    title: '删除采集账号',
    content: `确定删除"${account?.account_name || `账号 #${accountId}`}"吗？删除后将清空本地 Cookie 与浏览器环境指纹，后续必须重新扫码登录。历史直播数据不会删除。`,
    positiveText: '确认删除并清空登录状态',
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const result = await deleteCollectorAccount(accountId);
        if (result.error) throw new Error(getServiceErrorMessage(result.error, '删除采集账号失败'));
        message.success($t('common.deleteSuccess'));
        await loadData();
      } catch {
        message.error('删除失败');
      }
    }
  });
}

/* ========== 扫码登录流程 ========== */

async function handleStartLogin() {
  try {
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
    const res = await startCollectorLogin();
    const data = unwrapServiceData(res, '启动登录失败');
    loginTaskId.value = data.task_id;
    loginStatus.value = 'pending';
    loginMessage.value = '';
    showQRModal.value = true;
    pollLoginStatus();
  } catch {
    message.error('启动登录失败');
  }
}

async function pollLoginStatus() {
  if (loginPollTimer) window.clearInterval(loginPollTimer);

  loginPollTimer = window.setInterval(async () => {
    if (!loginTaskId.value) return;

    try {
      // 先获取二维码图片
      if (!qrImage.value) {
        try {
          const qrRes = await fetchLoginQR(loginTaskId.value);
          const qrData = unwrapServiceData(qrRes, '二维码尚未生成');
          qrImage.value = qrData.qr_code_base64;
          loginStatus.value = 'scanning';
          loginMessage.value = $t('page.collector.scanQrCode');
        } catch {
          // 二维码可能还没生成好，下一轮再试
        }
      }

      // 检查登录状态
      const statusRes = await fetchLoginStatus(loginTaskId.value);
      const statusData = unwrapServiceData(statusRes, '登录状态读取失败');

      loginStatus.value = statusData.status as LoginState;
      loginMessage.value = statusData.message;

      if (statusData.status === 'success') {
        message.success($t('page.collector.loginSuccess'));
        stopLoginPoll();
        showQRModal.value = false;
        await loadData();
      } else if (statusData.status === 'failed' || statusData.status === 'timeout') {
        message.error(statusData.message || $t('page.collector.loginFailed'));
        stopLoginPoll();
      }
    } catch {
      // 轮询临时错误忽略
    }
  }, 3000);
}

function stopLoginPoll() {
  if (loginPollTimer) {
    window.clearInterval(loginPollTimer);
    loginPollTimer = null;
  }
}

function closeQRModal() {
  showQRModal.value = false;
  stopLoginPoll();
  qrImage.value = '';
  loginTaskId.value = null;
  loginStatus.value = 'idle';
  loginMessage.value = '';
}

/* ========== 轮询 & 时钟（必须在 logColumns 前面，logColumns 的 render 函数用到了 now） ========== */

const { now, startPolling, stopPolling, startClock, stopClock } = useCollectorPolling(
  () => collectionRunning.value || Boolean(collectorStatus.value?.active_task_count) || taskDrawerVisible.value,
  () => loadData(true)
);

/* ========== 日志表格列定义（传给 CollectorLogTable） ========== */

function openLogDetail(log: Api.Douyin.CollectorLog) {
  selectedLog.value = log;
  logDetailVisible.value = true;
}

const logColumns = [
  {
    title: () => $t('page.collector.logTime'),
    key: 'created_at',
    width: 150,
    render(row: Api.Douyin.CollectorLog) {
      return h('span', { title: formatFullTime(row.created_at) }, formatLogTime(row.created_at, now.value));
    }
  },
  {
    title: '任务',
    key: 'task_id',
    width: 90,
    render(row: Api.Douyin.CollectorLog) {
      return row.task_id ? `#${row.task_id}` : '-';
    }
  },
  {
    title: '阶段',
    key: 'stage',
    width: 100,
    render(row: Api.Douyin.CollectorLog) {
      return getStageLabel(getLogPayload(row).stage);
    }
  },
  {
    title: () => $t('page.collector.logLevel'),
    key: 'level',
    width: 80,
    render(row: { level: string }) {
      const typeMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
        info: 'info',
        warn: 'warning',
        error: 'error'
      };
      return h(NTag, { type: typeMap[row.level] || 'info', size: 'small' }, { default: () => row.level.toUpperCase() });
    }
  },
  { title: () => $t('page.collector.logMessage'), key: 'message', minWidth: 300, ellipsis: { tooltip: true } },
  {
    title: '数据摘要',
    key: 'summary',
    minWidth: 240,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.CollectorLog) {
      return getLogSummary(row);
    }
  },
  {
    title: '详情',
    key: 'detail',
    width: 70,
    fixed: 'right' as const,
    render(row: Api.Douyin.CollectorLog) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'tiny', onClick: () => openLogDetail(row) },
        { default: () => '查看' }
      );
    }
  }
];

/* ========== 生命周期 ========== */

onMounted(() => {
  loadData();
  startPolling();
  startClock();
});

onActivated(() => {
  loadData(true);
  startPolling();
  startClock();
});

onDeactivated(() => {
  stopLoginPoll();
  stopPolling();
  stopClock();
});

onUnmounted(() => {
  stopLoginPoll();
  stopPolling();
  stopClock();
});
</script>

<template>
  <div class="business-page min-h-full">
    <!-- 数据加载异常提示 -->
    <NAlert v-if="dataLoadFailedCount" type="warning" :bordered="false" show-icon>
      有 {{ dataLoadFailedCount }} 项采集状态暂时未更新，页面已保留其余真实结果。
      <span v-if="lastDataUpdatedAt" class="ml-6px text-12px text-gray-500">
        最近尝试 {{ new Date(lastDataUpdatedAt).toLocaleTimeString('zh-CN', { hour12: false }) }}
      </span>
      <NButton size="small" secondary :loading="loading" @click="() => loadData()">重新加载</NButton>
    </NAlert>

    <NSpin :show="loading && !collectorStatus" class="business-loading-panel">
      <NSpace vertical :size="16">
        <!-- 1. 顶部 4 张统计卡片 -->
        <CollectorStatCards
          :collector-status="collectorStatus"
          :accounts-length="accounts.length"
          :logged-in-count="loggedInAccountCount"
          :monitor-status="monitorStatus"
          :error-log-count="errorLogCount"
          :historical-error-count="historicalErrorCount"
          @open-accounts="openAccounts"
          @open-tasks="openTasks"
          @open-errors="openErrors"
        />

        <!-- 2. 刷新采集 + 实时监控（左右布局） -->
        <NGrid cols="1 l:3" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:2">
            <CollectorRefreshCard
              :collect-all-loading="collectAllLoading"
              :has-available-account="hasAvailableAccount"
              :current-collect-task="currentCollectTask"
              :asr-status="asrStatus"
              :asr-control-loading="asrControlLoading"
              :collect-disabled-reason="collectDisabledReason"
              :collect-all-result="collectAllResult"
              @collect-all="handleCollectAll"
              @toggle-asr="handleAsrToggle"
            />
          </NGi>
          <NGi>
            <CollectorMonitorCard
              :monitor-status="monitorStatus"
              :monitor-loading="monitorLoading"
              @start="handleStartMonitor"
              @stop="handleStopMonitor"
              @trigger-live="handleTriggerLive"
              @trigger-end="handleTriggerEnd"
            />
          </NGi>
        </NGrid>

        <!-- 3. DataEase 数据集 -->
        <CollectorDataEaseCard
          :data-ease-status="dataEaseStatus"
          :data-ease-sync-loading="dataEaseSyncLoading"
          @sync="handleDataEaseSync"
        />

        <!-- 4. 账号表格 -->
        <div
          ref="accountSectionRef"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': accountHighlight }"
        >
          <CollectorAccountTable
            :loading="loading"
            :accounts="accounts"
            :account-health-loading-id="accountHealthLoadingId"
            :collection-running="collectionRunning"
            :monitor-running="Boolean(monitorStatus?.running)"
            @refresh="() => loadData()"
            @start-login="handleStartLogin"
            @health-check="handleAccountHealth"
            @re-login="handleReLogin"
            @delete-account="handleDeleteAccount"
          />
        </div>

        <!-- 5. 采集日志表格 -->
        <div
          ref="logSectionRef"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': logHighlight }"
        >
          <CollectorLogTable
            :loading="loading"
            :silent-refreshing="silentRefreshing"
            :clear-logs-loading="clearLogsLoading"
            :logs="logs"
            :log-columns="logColumns"
            :log-level="logLevel"
            :log-task-id="logTaskId"
            @refresh="() => loadData()"
            @clear="handleClearLogs"
            @filter="filterLogs"
            @clear-task-filter="clearTaskLogFilter"
          />
        </div>
      </NSpace>
    </NSpin>

    <!-- 6. 任务队列抽屉 -->
    <CollectorTaskDrawer
      v-model:visible="taskDrawerVisible"
      :tasks="tasks"
      :now="now"
      @view-logs="viewTaskLogs"
    />

    <!-- 7. 日志详情弹窗 -->
    <CollectorLogDetailModal
      v-model:visible="logDetailVisible"
      :log="selectedLog"
    />

    <!-- 8. 扫码登录弹窗 -->
    <CollectorQRLogin
      :visible="showQRModal"
      :qr-image="qrImage"
      :status="loginStatus"
      :message="loginMessage"
      @close="closeQRModal"
      @retry="handleStartLogin"
    />
  </div>
</template>

<style scoped>
/*
 * .collector-log-table 的样式已移到 CollectorLogTable.vue 子组件中，
 * 因为 Vue 3 scoped CSS 不会穿透到子组件内部元素。
 */
</style>
