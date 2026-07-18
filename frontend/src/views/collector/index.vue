<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue';
import { NButton, NSpace, NTag, useDialog, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import BusinessPageHeader from '@/components/business/page-header.vue';
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

defineOptions({
  name: 'Collector'
});

const message = useMessage();
const dialog = useDialog();

/* ---------- 状态 ---------- */
const loading = ref(true);
const collectorStatus = ref<Api.Douyin.CollectorStatus | null>(null);
const accounts = ref<Api.Douyin.CollectorAccount[]>([]);
const logs = ref<Api.Douyin.CollectorLog[]>([]);
const tasks = ref<Api.Douyin.CollectorTask[]>([]);
const accountSectionRef = ref<HTMLElement | null>(null);
const logSectionRef = ref<HTMLElement | null>(null);
const accountHighlight = ref(false);
const logHighlight = ref(false);
const taskDrawerVisible = ref(false);
const logLevel = ref('all');
const logTaskId = ref<number | null>(null);
const now = ref(Date.now());
const silentRefreshing = ref(false);
const accountHealthLoadingId = ref<number | null>(null);
const logDetailVisible = ref(false);
const selectedLog = ref<Api.Douyin.CollectorLog | null>(null);
const clearLogsLoading = ref(false);
const asrStatus = ref<Api.Douyin.AsrControlStatus | null>(null);
const asrControlLoading = ref(false);
const dataEaseStatus = ref<Api.Douyin.DataEaseStatus | null>(null);
const dataEaseSyncLoading = ref(false);

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

const getAccountRowKey = (row: Api.Douyin.CollectorAccount) => row.id;
const getLogRowKey = (row: Api.Douyin.CollectorLog) => row.id;
const getCollectResultRowKey = (row: Api.Douyin.CollectRoomResult) => row.room_id;
const getTaskRowKey = (row: Api.Douyin.CollectorTask) => row.id;

type LoginState = 'idle' | 'pending' | 'scanning' | 'success' | 'failed' | 'timeout' | 'not_found';

/* ---------- 扫码登录 ---------- */
const showQRModal = ref(false);
const qrImage = ref('');
const loginTaskId = ref<number | null>(null);
const loginStatus = ref<LoginState>('idle');
const loginMessage = ref('');
let loginPollTimer: number | null = null;
let dataPollTimer: number | null = null;
let clockTimer: number | null = null;

/* ---------- 监控 ---------- */
const monitorStatus = ref<Api.Douyin.MonitorStatus | null>(null);
const monitorLoading = ref(false);

/* ---------- 刷新数据采集 ---------- */
const collectAllLoading = ref(false);
const collectAllResult = ref<Api.Douyin.CollectAllResponse | null>(null);
const collectionRunning = computed(
  () => collectAllLoading.value || activeTasks.value.some(item => item.task_type === 'collect_all')
);
const collectDisabledReason = computed(() => {
  if (!hasAvailableAccount.value) return '请先扫码登录可用采集账号';
  if (collectionRunning.value) return '已有刷新数据采集任务正在运行，请勿重复提交';
  return '';
});

async function loadMonitorStatus() {
  const res = await fetchMonitorStatus();
  if (res.data) monitorStatus.value = res.data;
}

async function handleStartMonitor() {
  monitorLoading.value = true;
  try {
    const res = await startMonitor();
    if (res.data?.success) message.success(res.data.message);
    await loadMonitorStatus();
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
    if (res.data?.success) message.success(res.data.message);
    await loadMonitorStatus();
  } catch {
    message.error('停止监控失败');
  } finally {
    monitorLoading.value = false;
  }
}

async function handleTriggerLive() {
  const res = await triggerMockLive();
  if (res.data?.success) message.success(res.data.message);
  else message.warning(res.data?.message || '模拟开播失败');
  await loadMonitorStatus();
}

async function handleTriggerEnd() {
  const res = await triggerMockEnd();
  if (res.data?.success) message.success(res.data.message);
  await loadMonitorStatus();
}

/* ---------- 刷新数据采集 ---------- */
async function handleCollectAll() {
  collectAllLoading.value = true;
  collectAllResult.value = null;
  try {
    const res = await collectAllData();
    collectAllResult.value = res.data;
    if (res.data?.collected_rooms && res.data.collected_rooms > 0) {
      message.success(`采集完成：${res.data.collected_rooms}/${res.data.total_rooms} 个房间`);
      message.info(`全部场次检查完成，本次补齐 ${res.data.history_detail_synced_count || 0} 场详情`);
    } else if (res.data?.message) {
      message.warning(res.data.message);
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

/* ---------- 加载数据 ---------- */
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
      result => result.status === 'rejected'
    ).length;
    if (failedCount && !silent) message.warning(`${failedCount} 项数据暂时加载失败，其他区域已正常更新`);
  } catch {
    if (!silent) message.error('加载采集数据失败');
  } finally {
    if (silent) silentRefreshing.value = false;
    else loading.value = false;
  }
}

async function handleDataEaseSync() {
  dataEaseSyncLoading.value = true;
  try {
    const res = await syncDataEase();
    if (res.data) {
      dataEaseStatus.value = res.data.dataease;
      const text = `DataEase 同步完成：成功 ${res.data.synced_count} 场，失败 ${res.data.failed_count} 场，清理旧宽表 ${res.data.removed_stale_row_count} 行`;
      if (res.data.failed_count) message.warning(text);
      else message.success(text);
    }
  } catch {
    message.error('DataEase 同步失败，请查看后端日志');
  } finally {
    dataEaseSyncLoading.value = false;
  }
}

async function applyAsrToggle(enabled: boolean) {
  asrControlLoading.value = true;
  try {
    const res = await setAsrControl(enabled);
    if (res.data) {
      asrStatus.value = res.data;
      message.success(res.data.message);
    }
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
        const deletedCount = response.data?.deleted_count || 0;
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

function openAccounts() {
  scrollToSection(accountSectionRef, accountHighlight);
}

function openTasks() {
  taskDrawerVisible.value = true;
}

async function openErrors() {
  await filterLogs('error');
}

async function handleAccountHealth(row: Api.Douyin.CollectorAccount) {
  accountHealthLoadingId.value = row.id;
  try {
    const res = await checkCollectorAccountHealth(row.id);
    if (res.data?.valid) message.success(res.data.message);
    else message.warning(res.data?.message || '账号登录状态已失效');
    await loadData(true);
  } catch {
    message.error('账号存活检查失败');
  } finally {
    accountHealthLoadingId.value = null;
  }
}

function formatLogTime(value: string) {
  const timestamp = parseBackendTime(value);
  if (!Number.isFinite(timestamp)) return value || '-';
  const diff = Math.max(0, now.value - timestamp);
  if (diff < 60_000) return '刚刚';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  const date = new Date(timestamp);
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatFullTime(value: string | null) {
  if (!value) return '-';
  return new Date(parseBackendTime(value)).toLocaleString('zh-CN', { hour12: false });
}

function parseBackendTime(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasTimezone ? value : `${value}Z`).getTime();
}

function getLogPayload(log: Api.Douyin.CollectorLog): Record<string, unknown> {
  return log.raw_json && typeof log.raw_json === 'object' && !Array.isArray(log.raw_json)
    ? (log.raw_json as Record<string, unknown>)
    : {};
}

function getStageLabel(stage: unknown) {
  const labels: Record<string, string> = {
    prepare: '准备账号',
    login_check: '验证登录',
    room_collection: '房间采集',
    enterprise_sync: '主播同步',
    history_sync: '历史同步',
    detail_enrichment: '详情补齐',
    cookie_refresh: '保存登录态',
    dataease_sync: '同步 DataEase',
    asr_queue: '排队生成话术',
    post_collection: '话术/复盘入库',
    completed: '采集完成',
    failed: '采集失败'
  };
  return labels[String(stage || '')] || String(stage || '常规日志');
}

function getLogSummary(log: Api.Douyin.CollectorLog) {
  const payload = getLogPayload(log);
  const detailSource = payload.details;
  const details =
    detailSource && typeof detailSource === 'object' && !Array.isArray(detailSource)
      ? (detailSource as Record<string, unknown>)
      : payload;
  const parts = [
    details.anchor_name && `主播 ${details.anchor_name}`,
    details.room_id && `房间 ${details.room_id}`,
    details.metrics_count !== undefined && `指标 ${details.metrics_count}`,
    details.comments_count !== undefined && `评论 ${details.comments_count}`,
    details.profiles_count !== undefined && `画像 ${details.profiles_count}`,
    details.transcript_count !== undefined && `话术 ${details.transcript_count} 段`,
    details.review_finding_count !== undefined && `复盘 ${details.review_finding_count} 条`,
    payload.progress_percent !== undefined && `进度 ${payload.progress_percent}%`
  ].filter(Boolean);
  return parts.join(' · ') || '-';
}

function openLogDetail(log: Api.Douyin.CollectorLog) {
  selectedLog.value = log;
  logDetailVisible.value = true;
}

function startDataPolling() {
  stopDataPolling();
  dataPollTimer = window.setInterval(() => {
    if (collectionRunning.value || collectorStatus.value?.active_task_count || taskDrawerVisible.value) {
      loadData(true);
    }
  }, 5000);
}

function stopDataPolling() {
  if (dataPollTimer) window.clearInterval(dataPollTimer);
  dataPollTimer = null;
}

/* ---------- 扫码登录流程 ---------- */
async function handleStartLogin() {
  try {
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
    const res = await startCollectorLogin();
    if (!res.data) return;
    loginTaskId.value = res.data.task_id;
    loginStatus.value = 'pending';
    loginMessage.value = '';
    showQRModal.value = true;
    pollLoginStatus();
  } catch {
    message.error('启动登录失败');
  }
}

async function handleReLogin(accountId: number) {
  try {
    qrImage.value = '';
    loginMessage.value = '';
    stopLoginPoll();
    const res = await reCollectorLogin(accountId);
    if (!res.data) return;
    loginTaskId.value = res.data.task_id;
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
    content: `确定删除“${account?.account_name || `账号 #${accountId}`}”吗？删除后将清空本地 Cookie 与浏览器环境指纹，后续必须重新扫码登录。历史直播数据不会删除。`,
    positiveText: '确认删除并清空登录状态',
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      try {
        await deleteCollectorAccount(accountId);
        message.success($t('common.deleteSuccess'));
        await loadData();
      } catch {
        message.error('删除失败');
      }
    }
  });
}

async function pollLoginStatus() {
  if (loginPollTimer) window.clearInterval(loginPollTimer);

  loginPollTimer = window.setInterval(async () => {
    if (!loginTaskId.value) return;

    try {
      // 获取二维码
      if (!qrImage.value) {
        try {
          const qrRes = await fetchLoginQR(loginTaskId.value);
          if (qrRes.data) {
            qrImage.value = qrRes.data.qr_code_base64;
            loginStatus.value = 'scanning';
            loginMessage.value = $t('page.collector.scanQrCode');
          }
        } catch {
          // QR 可能还没生成
        }
      }

      // 检查登录状态
      const statusRes = await fetchLoginStatus(loginTaskId.value);
      if (!statusRes.data) return;

      loginStatus.value = statusRes.data.status as LoginState;
      loginMessage.value = statusRes.data.message;

      if (statusRes.data.status === 'success') {
        message.success($t('page.collector.loginSuccess'));
        stopLoginPoll();
        showQRModal.value = false;
        await loadData();
      } else if (statusRes.data.status === 'failed' || statusRes.data.status === 'timeout') {
        message.error(statusRes.data.message || $t('page.collector.loginFailed'));
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

/* ---------- 表格列 ---------- */
const accountColumns = [
  { title: 'ID', key: 'id', width: 60 },
  {
    title: () => $t('page.collector.accountName'),
    key: 'account_name',
    ellipsis: { tooltip: true }
  },
  {
    title: () => $t('page.collector.douyinId'),
    key: 'douyin_id',
    minWidth: 150,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.CollectorAccount) {
      if (row.douyin_id) return row.douyin_id;
      return h(
        NButton,
        {
          text: true,
          type: 'warning',
          size: 'tiny',
          loading: accountHealthLoadingId.value === row.id,
          onClick: () => handleAccountHealth(row)
        },
        { default: () => '未获取 / 点此刷新' }
      );
    }
  },
  {
    title: () => $t('page.collector.loginStatus'),
    key: 'login_status',
    width: 100,
    render(row: Api.Douyin.CollectorAccount) {
      const map: Record<string, { type: 'success' | 'warning' | 'error' | 'info'; label: string }> = {
        logged_in: { type: 'success', label: $t('page.collector.loggedIn') },
        expired: { type: 'error', label: $t('page.collector.statusExpired') },
        never: { type: 'warning', label: $t('page.collector.neverLogin') }
      };
      const info = map[row.login_status] || { type: 'warning', label: row.login_status };
      return h(NTag, { type: info.type, size: 'small' }, { default: () => info.label });
    }
  },
  {
    title: () => $t('page.collector.lastLogin'),
    key: 'last_login_at',
    width: 170,
    render(row: Api.Douyin.CollectorAccount) {
      return row.last_login_at || '-';
    }
  },
  {
    title: () => $t('common.action'),
    key: 'actions',
    width: 220,
    render(row: Api.Douyin.CollectorAccount) {
      const btns: ReturnType<typeof h>[] = [];
      btns.push(
        h(
          NButton,
          {
            text: true,
            type: 'primary',
            size: 'tiny',
            loading: accountHealthLoadingId.value === row.id,
            disabled: collectionRunning.value || Boolean(monitorStatus.value?.running),
            onClick: () => handleAccountHealth(row)
          },
          { default: () => '检查存活' }
        )
      );
      if (row.login_status === 'expired') {
        btns.push(
          h(
            NButton,
            {
              text: true,
              type: 'warning',
              size: 'tiny',
              onClick: () => handleReLogin(row.id)
            },
            { default: () => $t('page.collector.reLogin') }
          )
        );
      }
      btns.push(
        h(
          NButton,
          {
            text: true,
            type: 'error',
            size: 'tiny',
            onClick: () => handleDeleteAccount(row.id)
          },
          { default: () => $t('page.collector.deleteAccount') }
        )
      );
      return h(NSpace, { size: 12, wrap: false }, { default: () => btns });
    }
  }
];

const collectResultColumns = [
  { title: '主播', key: 'anchor_name', minWidth: 140, ellipsis: { tooltip: true } },
  {
    title: '直播',
    key: 'is_live',
    width: 60,
    render(row: { is_live: boolean }) {
      return row.is_live
        ? h(NTag, { type: 'success', size: 'small' }, { default: () => '直播中' })
        : h(NTag, { type: 'default', size: 'small' }, { default: () => '未开播' });
    }
  },
  { title: '指标数', key: 'metrics_count', width: 80 },
  { title: '评论数', key: 'comments_count', width: 80 },
  { title: '画像数', key: 'profiles_count', width: 80 },
  {
    title: '状态',
    key: 'error',
    minWidth: 160,
    render(row: { error: string | null }) {
      return row.error
        ? h(NTag, { type: 'error', size: 'small' }, { default: () => row.error })
        : h(NTag, { type: 'success', size: 'small' }, { default: () => '成功' });
    }
  }
];

const logColumns = [
  {
    title: () => $t('page.collector.logTime'),
    key: 'created_at',
    width: 150,
    render(row: Api.Douyin.CollectorLog) {
      return h('span', { title: formatFullTime(row.created_at) }, formatLogTime(row.created_at));
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

const taskColumns = [
  { title: '任务 ID', key: 'id', width: 90 },
  {
    title: '任务类型',
    key: 'task_type',
    minWidth: 120,
    render(row: Api.Douyin.CollectorTask) {
      const labels: Record<string, string> = {
        collect_all: '刷新数据采集',
        login: '扫码登录',
        metrics: '指标采集',
        comments: '评论采集',
        leads: '留资采集',
        profile: '画像采集',
        live_detail: '实时场次采集'
      };
      return labels[row.task_type] || row.task_type;
    }
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render(row: Api.Douyin.CollectorTask) {
      const states: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'error' }> = {
        pending: { label: '排队中', type: 'info' },
        running: { label: '运行中', type: 'warning' },
        completed: { label: '已完成', type: 'success' },
        failed: { label: '失败', type: 'error' }
      };
      const state = states[row.status] || { label: row.status, type: 'info' as const };
      return h(NTag, { type: state.type, size: 'small', round: true }, { default: () => state.label });
    }
  },
  {
    title: '进度',
    key: 'progress_percent',
    width: 210,
    render(row: Api.Douyin.CollectorTask) {
      return h('div', { class: 'flex flex-col gap-4px' }, [
        h('span', { class: 'text-12px' }, `${row.progress_percent || 0}% · ${getStageLabel(row.progress_stage)}`),
        h('span', { class: 'text-11px text-gray-500' }, row.progress_message || '-'),
        row.task_type === 'collect_all'
          ? h(
              'span',
              { class: 'text-11px text-primary' },
              `主播 ${row.collected_anchor_count || 0} 位 · 场次 ${row.collected_session_count || 0} 场`
            )
          : null
      ]);
    }
  },
  {
    title: '开始时间',
    key: 'started_at',
    width: 180,
    render(row: Api.Douyin.CollectorTask) {
      return formatFullTime(row.started_at);
    }
  },
  {
    title: '执行信息',
    key: 'trace_id',
    width: 210,
    render(row: Api.Douyin.CollectorTask) {
      const trace = row.trace_id ? row.trace_id.slice(0, 12) : '-';
      const heartbeat = row.heartbeat_at ? formatLogTime(row.heartbeat_at) : '-';
      return h('div', { class: 'flex flex-col gap-4px text-11px' }, [
        h('span', { class: 'font-mono text-gray-600', title: row.trace_id || '' }, `Trace ${trace}`),
        h(
          'span',
          { class: 'text-gray-500' },
          `心跳 ${heartbeat} · 执行 ${row.retry_count || 0}/${row.max_retries || 0}`
        )
      ]);
    }
  },
  { title: '失败原因', key: 'error_message', minWidth: 220, ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: 'action',
    width: 90,
    render(row: Api.Douyin.CollectorTask) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'tiny', onClick: () => viewTaskLogs(row.id) },
        { default: () => '查看日志' }
      );
    }
  }
];

/* ---------- 生命周期 ---------- */
onMounted(() => {
  loadData();
  startDataPolling();
  clockTimer = window.setInterval(() => {
    now.value = Date.now();
  }, 30_000);
});

onUnmounted(() => {
  stopLoginPoll();
  stopDataPolling();
  if (clockTimer) window.clearInterval(clockTimer);
});
</script>

<template>
  <div class="min-h-full flex flex-col gap-16px">
    <BusinessPageHeader
      title="数据采集中心"
      description="使用已保存的 Cookie 与浏览器指纹发现全部主播，并持续补齐直播场次、评论、画像、分钟指标和直播流地址。"
      icon="mdi:database-sync-outline"
      :status="hasAvailableAccount ? `${loggedInAccountCount} 个账号可用` : '需要扫码登录'"
      :status-type="hasAvailableAccount ? 'success' : 'error'"
    >
      <template #actions>
        <NButton secondary @click="openAccounts">
          <template #icon><SvgIcon icon="mdi:account-key-outline" /></template>
          管理采集账号
        </NButton>
        <NButton type="primary" :disabled="!hasAvailableAccount" @click="openTasks">
          <template #icon><SvgIcon icon="mdi:clipboard-text-clock-outline" /></template>
          查看任务队列
        </NButton>
      </template>
      <div class="flex flex-wrap items-center gap-x-18px gap-y-6px text-12px text-gray-500">
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-1-circle-outline" />
          扫码并检查存活
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-2-circle-outline" />
          选择刷新采集或实时监控
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-3-circle-outline" />
          查看进度与失败日志
        </span>
        <span class="flex items-center gap-5px">
          <SvgIcon icon="mdi:numeric-4-circle-outline" />
          同步 DataEase
        </span>
      </div>
    </BusinessPageHeader>

    <NSpin :show="loading">
      <NSpace vertical :size="16">
        <NGrid cols="1 s:2 l:4" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">采集服务</div>
                  <div class="mt-8px text-20px font-600">
                    {{ collectorStatus?.connected ? '连接正常' : '连接异常' }}
                  </div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-primary-100 text-primary dark:bg-primary-900/30">
                  <SvgIcon icon="mdi:database-sync-outline" class="text-24px" />
                </div>
              </div>
              <NTag class="mt-16px" :type="collectorStatus?.connected ? 'success' : 'error'" round size="small">
                {{ collectorStatus?.connected ? $t('page.collector.connected') : $t('page.collector.disconnected') }}
              </NTag>
            </NCard>
          </NGi>
          <NGi>
            <NCard
              :bordered="false"
              class="card-wrapper h-full cursor-pointer transition-shadow hover:shadow-md"
              size="small"
              role="button"
              tabindex="0"
              @click="openAccounts"
              @keydown.enter="openAccounts"
            >
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">可用账号</div>
                  <div class="mt-8px text-20px font-600">{{ loggedInAccountCount }} / {{ accounts.length }}</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-success-100 text-success dark:bg-success-900/30">
                  <SvgIcon icon="mdi:account-check-outline" class="text-24px" />
                </div>
              </div>
              <div class="mt-16px text-12px text-gray-500">已保存 Cookie 与浏览器指纹</div>
            </NCard>
          </NGi>
          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" size="small">
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">直播监控</div>
                  <div class="mt-8px text-20px font-600">{{ monitorStatus?.active_session_count || 0 }} 场</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-warning-100 text-warning dark:bg-warning-900/30">
                  <SvgIcon icon="mdi:radar" class="text-24px" />
                </div>
              </div>
              <NTag class="mt-16px" :type="monitorStatus?.running ? 'success' : 'default'" round size="small">
                {{ monitorStatus?.running ? '监控运行中' : '监控已停止' }}
              </NTag>
            </NCard>
          </NGi>
          <NGi>
            <NCard
              :bordered="false"
              class="card-wrapper h-full cursor-pointer transition-shadow hover:shadow-md"
              size="small"
              role="button"
              tabindex="0"
              @click="openTasks"
              @keydown.enter="openTasks"
            >
              <div class="flex items-center justify-between gap-12px">
                <div>
                  <div class="text-13px text-gray-500">当前任务</div>
                  <div class="mt-8px text-20px font-600">{{ collectorStatus?.active_task_count || 0 }} 个</div>
                </div>
                <div class="size-44px flex-center rounded-12px bg-error-100 text-error dark:bg-error-900/30">
                  <SvgIcon icon="mdi:progress-clock" class="text-24px" />
                </div>
              </div>
              <NButton
                class="mt-12px"
                text
                :type="errorLogCount ? 'error' : 'success'"
                size="tiny"
                @click.stop="openErrors"
              >
                <template v-if="errorLogCount">成功采集后新增 {{ errorLogCount }} 条异常，点击查看</template>
                <template v-else-if="historicalErrorCount">当前无未恢复异常，点击查看历史</template>
                <template v-else>当前无采集异常</template>
              </NButton>
            </NCard>
          </NGi>
        </NGrid>

        <NGrid cols="1 l:3" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:2">
            <NCard :bordered="false" class="card-wrapper h-full" title="刷新数据采集">
              <template #header-extra>
                <NTag v-if="collectAllLoading" type="warning" round size="small">任务执行中</NTag>
                <NTag v-else-if="hasAvailableAccount" type="success" round size="small">账号已就绪</NTag>
                <NTag v-else type="error" round size="small">请先扫码登录</NTag>
              </template>
              <div class="flex flex-col gap-16px">
                <NAlert type="info" :show-icon="true" :bordered="false">
                  重新发现账号下全部主播和直播场次，并补齐每场直播的主播资料、指标、评论和观众画像。可与实时监控同时开启，刷新期间由全量任务接管重复采集，完成后自动恢复监控。
                </NAlert>
                <NSteps
                  size="small"
                  :current="
                    currentCollectTask?.status === 'running' ? 2 : currentCollectTask?.status === 'completed' ? 3 : 1
                  "
                  status="process"
                  responsive="screen"
                >
                  <NStep title="账号就绪" description="Cookie 与指纹有效" />
                  <NStep title="发现与补齐" description="主播、场次和详情" />
                  <NStep title="自动后处理" description="话术、AI复盘与知识库" />
                </NSteps>
                <div
                  class="flex flex-wrap items-center justify-between gap-12px rounded-10px bg-gray-100 p-12px dark:bg-white/5"
                >
                  <div class="flex items-center gap-12px">
                    <div
                      class="size-38px flex-center rounded-10px"
                      :class="
                        asrStatus?.enabled
                          ? 'bg-success-100 text-success dark:bg-success-900/30'
                          : 'bg-gray-200 text-gray-500 dark:bg-white/10'
                      "
                    >
                      <SvgIcon icon="mdi:waveform" class="text-21px" />
                    </div>
                    <div>
                      <div class="flex items-center gap-8px font-600">
                        话术、AI 复盘与知识库
                        <NTag :type="asrStatus?.enabled ? 'success' : 'default'" round size="small">
                          {{ asrStatus?.enabled ? '已开启' : '已关闭' }}
                        </NTag>
                      </div>
                      <div class="mt-3px text-12px text-gray-500">
                        <template v-if="asrStatus?.enabled">
                          话术排队 {{ asrStatus.queued_count }} · 话术处理中 {{ asrStatus.processing_count }} ·
                          复盘处理中 {{ asrStatus.postprocess_processing_count }} · 已入库
                          {{ asrStatus.postprocess_completed_count }}
                          <span v-if="!asrStatus.queued_count && !asrStatus.processing_count">
                            · 当前空闲但仍占用模型内存，不使用时建议关闭
                          </span>
                        </template>
                        <template v-else>服务已关闭；开启后按单并发继续完成话术、复盘与知识库队列</template>
                      </div>
                    </div>
                  </div>
                  <NSwitch
                    :value="Boolean(asrStatus?.enabled)"
                    :loading="asrControlLoading"
                    @update:value="handleAsrToggle"
                  >
                    <template #checked>开启</template>
                    <template #unchecked>关闭</template>
                  </NSwitch>
                </div>
                <div class="flex flex-wrap items-center gap-12px">
                  <NTooltip :disabled="!collectDisabledReason">
                    <template #trigger>
                      <span>
                        <NButton
                          type="primary"
                          size="large"
                          :loading="collectAllLoading"
                          :disabled="Boolean(collectDisabledReason)"
                          @click="handleCollectAll"
                        >
                          <template #icon><SvgIcon icon="mdi:database-arrow-down-outline" /></template>
                          {{ collectAllLoading ? '正在刷新全部数据' : '刷新数据采集' }}
                        </NButton>
                      </span>
                    </template>
                    {{ collectDisabledReason }}
                  </NTooltip>
                  <span class="text-12px text-gray-500">采集完成后自动刷新账号状态与最近日志</span>
                </div>

                <div v-if="currentCollectTask" class="rounded-10px bg-primary-50 p-16px dark:bg-primary-900/15">
                  <div class="mb-10px flex flex-wrap items-center justify-between gap-8px">
                    <div>
                      <div class="font-600">{{ getStageLabel(currentCollectTask.progress_stage) }}</div>
                      <div class="mt-4px text-12px text-gray-500">
                        {{ currentCollectTask.progress_message || '正在执行采集任务' }}
                      </div>
                    </div>
                    <NTag
                      :type="
                        currentCollectTask.status === 'completed'
                          ? 'success'
                          : currentCollectTask.status === 'failed'
                            ? 'error'
                            : 'primary'
                      "
                      round
                    >
                      任务 #{{ currentCollectTask.id }} ·
                      {{
                        currentCollectTask.status === 'completed'
                          ? '已完成'
                          : currentCollectTask.status === 'failed'
                            ? '失败'
                            : '运行中'
                      }}
                    </NTag>
                  </div>
                  <NProgress
                    type="line"
                    :percentage="currentCollectTask.progress_percent || 0"
                    indicator-placement="inside"
                    :processing="currentCollectTask.status === 'running'"
                  />
                  <div class="mt-8px flex justify-between text-12px text-gray-500">
                    <span>
                      已完成 {{ currentCollectTask.progress_current || 0 }}
                      <template v-if="currentCollectTask.progress_total">
                        / {{ currentCollectTask.progress_total }}
                      </template>
                    </span>
                    <span>
                      {{
                        currentCollectTask.status === 'running'
                          ? '页面每 5 秒自动更新'
                          : formatFullTime(currentCollectTask.completed_at)
                      }}
                    </span>
                  </div>
                  <NGrid class="mt-12px" cols="2 s:4 l:8" responsive="screen" :x-gap="10" :y-gap="10">
                    <NGi>
                      <div class="rounded-8px bg-white/70 px-12px py-10px dark:bg-black/15">
                        <div class="text-12px text-gray-500">已采集主播</div>
                        <div class="mt-2px text-20px font-600">
                          {{ currentCollectTask.collected_anchor_count || 0 }} 位
                        </div>
                      </div>
                    </NGi>
                    <NGi
                      v-for="item in [
                        { label: '已发现场次', value: currentCollectTask.collected_session_count },
                        { label: '新增场次', value: currentCollectTask.new_session_count },
                        { label: '主播映射', value: currentCollectTask.mapped_session_count },
                        { label: '已检查详情', value: currentCollectTask.checked_detail_count },
                        { label: '已补齐详情', value: currentCollectTask.refreshed_detail_count },
                        { label: '详情失败', value: currentCollectTask.failed_detail_count },
                        { label: '剩余待补', value: currentCollectTask.remaining_detail_count }
                      ]"
                      :key="item.label"
                    >
                      <div class="rounded-8px bg-white/70 px-10px py-10px dark:bg-black/15">
                        <div class="text-12px text-gray-500">{{ item.label }}</div>
                        <div class="mt-2px text-18px font-600">{{ item.value || 0 }} 场</div>
                      </div>
                    </NGi>
                  </NGrid>
                </div>

                <template v-if="collectAllResult">
                  <NDivider class="!my-0" />
                  <div class="flex flex-wrap items-center gap-8px">
                    <span class="font-600">最近一次采集结果</span>
                    <NTag :type="collectAllResult.collected_rooms > 0 ? 'success' : 'warning'" round size="small">
                      {{ collectAllResult.collected_rooms }}/{{ collectAllResult.total_rooms }} 个房间成功
                    </NTag>
                    <NTag :type="collectAllResult.dataease_failed_count ? 'warning' : 'success'" round size="small">
                      DataEase 同步 {{ collectAllResult.dataease_synced_count || 0 }} 场
                    </NTag>
                    <NTag type="info" round size="small">
                      话术新增排队 {{ collectAllResult.asr_queued_count || 0 }} 场 · 当前
                      {{ collectAllResult.asr_active_count || 0 }}/{{ collectAllResult.asr_queue_capacity || 5 }}
                    </NTag>
                    <NTag
                      :type="collectAllResult.postprocess_failed_count ? 'warning' : 'success'"
                      round
                      size="small"
                    >
                      AI复盘入库 {{ collectAllResult.postprocess_completed_count || 0 }} 场 · 待处理
                      {{ collectAllResult.postprocess_pending_count || 0 }} 场
                    </NTag>
                    <span v-if="collectAllResult.message" class="text-12px text-gray-500">
                      {{ collectAllResult.message }}
                    </span>
                  </div>
                  <NGrid cols="2 s:4 l:8" responsive="screen" :x-gap="12" :y-gap="12">
                    <NGi><NStatistic label="企业主播" :value="collectAllResult.enterprise_anchor_count || 0" /></NGi>
                    <NGi>
                      <NStatistic label="发现场次" :value="collectAllResult.enterprise_session_discovered_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="新增场次" :value="collectAllResult.enterprise_session_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="主播映射" :value="collectAllResult.anchor_profile_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="已检查详情" :value="collectAllResult.history_detail_checked_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="已补齐详情" :value="collectAllResult.history_detail_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="本次失败" :value="collectAllResult.history_detail_failed_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="待重试详情" :value="collectAllResult.history_detail_remaining_count || 0" />
                    </NGi>
                  </NGrid>
                  <NDataTable
                    v-if="collectAllResult.results?.length"
                    :columns="collectResultColumns"
                    :data="collectAllResult.results"
                    :row-key="getCollectResultRowKey"
                    :scroll-x="720"
                    :bordered="false"
                    size="small"
                  />
                </template>
              </div>
            </NCard>
          </NGi>

          <NGi>
            <NCard :bordered="false" class="card-wrapper h-full" title="实时监控">
              <template #header-extra>
                <NSpace :size="8">
                  <NTag v-if="monitorStatus?.paused_for_collection" type="warning" round size="small">
                    刷新采集接管中
                  </NTag>
                  <NTag v-if="monitorStatus?.mock_mode" type="warning" round size="small">Mock 模式</NTag>
                </NSpace>
              </template>
              <div class="flex flex-col gap-16px">
                <NAlert type="info" :bordered="false" show-icon>
                  适合长期开启：周期检查主播是否开播，开播后持续采集直播间指标和评论；刷新采集运行时会自动协调重复任务。
                </NAlert>
                <div class="flex items-center justify-between gap-12px rounded-8px bg-gray-100 p-12px dark:bg-white/5">
                  <div>
                    <div class="font-600">
                      {{
                        monitorStatus?.paused_for_collection
                          ? '监控已开启，当前由刷新采集接管'
                          : monitorStatus?.running
                            ? '正在监听开播状态'
                            : '监控服务未启动'
                      }}
                    </div>
                    <div class="mt-4px text-12px text-gray-500">
                      活跃场次 {{ monitorStatus?.active_session_count || 0 }} 场
                    </div>
                    <div v-if="monitorStatus?.last_error" class="mt-4px text-12px text-error">
                      最近错误：{{ monitorStatus.last_error }}
                    </div>
                  </div>
                  <NBadge :type="monitorStatus?.running ? 'success' : 'default'" dot />
                </div>
                <NButton
                  block
                  :type="monitorStatus?.running ? 'warning' : 'primary'"
                  :loading="monitorLoading"
                  @click="monitorStatus?.running ? handleStopMonitor() : handleStartMonitor()"
                >
                  <template #icon>
                    <SvgIcon :icon="monitorStatus?.running ? 'mdi:stop-circle-outline' : 'mdi:play-circle-outline'" />
                  </template>
                  {{ monitorStatus?.running ? '停止直播监控' : '启动直播监控' }}
                </NButton>
                <NSpace v-if="monitorStatus?.mock_mode" :wrap="false">
                  <NButton class="flex-1" type="success" secondary @click="handleTriggerLive">模拟开播</NButton>
                  <NButton class="flex-1" type="error" secondary @click="handleTriggerEnd">模拟下播</NButton>
                </NSpace>
              </div>
            </NCard>
          </NGi>
        </NGrid>

        <NCard :bordered="false" class="card-wrapper" title="DataEase 分析数据集">
          <template #header-extra>
            <NTag :type="dataEaseStatus?.pending_session_count ? 'warning' : 'success'" round size="small">
              {{
                dataEaseStatus?.pending_session_count
                  ? `待同步 ${dataEaseStatus.pending_session_count} 场`
                  : '数据已同步'
              }}
            </NTag>
          </template>
          <div class="flex flex-col gap-14px">
            <NGrid cols="2 s:3 l:6" responsive="screen" :x-gap="12" :y-gap="12">
              <NGi><NStatistic label="完整场次" :value="dataEaseStatus?.source_session_count || 0" /></NGi>
              <NGi><NStatistic label="已同步场次" :value="dataEaseStatus?.synced_session_count || 0" /></NGi>
              <NGi><NStatistic label="分钟指标" :value="dataEaseStatus?.metric_row_count || 0" /></NGi>
              <NGi><NStatistic label="观众画像" :value="dataEaseStatus?.profile_row_count || 0" /></NGi>
              <NGi><NStatistic label="评论汇总" :value="dataEaseStatus?.comment_summary_count || 0" /></NGi>
              <NGi><NStatistic label="AI 汇总" :value="dataEaseStatus?.ai_summary_count || 0" /></NGi>
            </NGrid>
            <NProgress
              type="line"
              :percentage="dataEaseStatus?.coverage_rate || 0"
              :status="dataEaseStatus?.pending_session_count ? 'warning' : 'success'"
              indicator-placement="inside"
            />
            <div class="flex flex-wrap items-center justify-between gap-12px">
              <span class="text-12px text-gray-500">
                最后同步：{{ formatFullTime(dataEaseStatus?.last_synced_at || null) }}；DataEase 只读 MySQL 的 de_*
                宽表。
              </span>
              <NSpace>
                <NButton
                  size="small"
                  type="primary"
                  :loading="dataEaseSyncLoading"
                  :disabled="!dataEaseStatus?.pending_session_count"
                  @click="handleDataEaseSync"
                >
                  同步待更新数据
                </NButton>
                <NButton
                  tag="a"
                  href="http://localhost:8100"
                  target="_blank"
                  rel="noopener noreferrer"
                  size="small"
                  secondary
                >
                  打开 DataEase
                </NButton>
              </NSpace>
            </div>
          </div>
        </NCard>

        <div
          ref="accountSectionRef"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': accountHighlight }"
        >
          <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.accountList')">
            <template #header-extra>
              <NSpace>
                <NButton size="small" :loading="loading" @click="() => loadData()">
                  <template #icon><SvgIcon icon="mdi:refresh" /></template>
                  {{ $t('common.refresh') }}
                </NButton>
                <NButton type="primary" size="small" @click="handleStartLogin">
                  <template #icon><SvgIcon icon="mdi:qrcode-scan" /></template>
                  {{ $t('page.collector.scanLogin') }}
                </NButton>
              </NSpace>
            </template>
            <NDataTable
              :loading="loading"
              :columns="accountColumns"
              :data="accounts"
              :row-key="getAccountRowKey"
              :scroll-x="900"
              :bordered="false"
              size="small"
              :empty-text="$t('page.collector.noAccount')"
            />
          </NCard>
        </div>

        <div
          ref="logSectionRef"
          class="scroll-mt-16px rounded-8px transition-shadow duration-300"
          :class="{ 'ring-2 ring-primary ring-offset-2': logHighlight }"
        >
          <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.logTitle')">
            <template #header-extra>
              <NSpace>
                <NTag v-if="logTaskId" type="primary" closable @close="clearTaskLogFilter">
                  仅任务 #{{ logTaskId }}
                </NTag>
                <NRadioGroup v-model:value="logLevel" size="small" @update:value="filterLogs">
                  <NRadioButton value="all">全部</NRadioButton>
                  <NRadioButton value="info">信息</NRadioButton>
                  <NRadioButton value="warn">警告</NRadioButton>
                  <NRadioButton value="error">异常</NRadioButton>
                </NRadioGroup>
                <NButton size="small" :loading="loading || silentRefreshing" @click="() => loadData()">
                  <template #icon><SvgIcon icon="mdi:refresh" /></template>
                  {{ $t('common.refresh') }}
                </NButton>
                <NButton size="small" type="error" secondary :loading="clearLogsLoading" @click="handleClearLogs">
                  <template #icon><SvgIcon icon="mdi:delete-sweep-outline" /></template>
                  清空日志
                </NButton>
              </NSpace>
            </template>
            <NDataTable
              class="collector-log-table"
              :loading="loading"
              :columns="logColumns"
              :data="logs"
              :row-key="getLogRowKey"
              :scroll-x="1260"
              flex-height
              :bordered="false"
              size="small"
            />
          </NCard>
        </div>
      </NSpace>
    </NSpin>

    <NDrawer v-model:show="taskDrawerVisible" width="min(560px, 94vw)" placement="right">
      <NDrawerContent title="采集任务队列" closable>
        <div class="mb-12px flex justify-end">
          <NTag :type="activeTasks.length ? 'warning' : 'success'" round size="small">
            {{ activeTasks.length ? `${activeTasks.length} 个运行中` : '当前空闲' }}
          </NTag>
        </div>
        <NAlert class="mb-16px" type="info" :bordered="false">
          任务运行期间页面每 5 秒静默刷新；任务结束后自动停止高频请求。
        </NAlert>
        <NDataTable
          :columns="taskColumns"
          :data="tasks"
          :row-key="getTaskRowKey"
          :scroll-x="920"
          :bordered="false"
          size="small"
        />
      </NDrawerContent>
    </NDrawer>

    <NModal v-model:show="logDetailVisible" preset="card" title="采集日志详情" class="w-720px max-w-[calc(100vw-32px)]">
      <NDescriptions v-if="selectedLog" :column="2" bordered label-placement="left" size="small">
        <NDescriptionsItem label="日志 ID">#{{ selectedLog.id }}</NDescriptionsItem>
        <NDescriptionsItem label="任务 ID">
          {{ selectedLog.task_id ? `#${selectedLog.task_id}` : '-' }}
        </NDescriptionsItem>
        <NDescriptionsItem label="时间">{{ formatFullTime(selectedLog.created_at) }}</NDescriptionsItem>
        <NDescriptionsItem label="级别">{{ selectedLog.level.toUpperCase() }}</NDescriptionsItem>
        <NDescriptionsItem label="阶段">{{ getStageLabel(getLogPayload(selectedLog).stage) }}</NDescriptionsItem>
        <NDescriptionsItem label="数据摘要">{{ getLogSummary(selectedLog) }}</NDescriptionsItem>
        <NDescriptionsItem label="消息" :span="2">{{ selectedLog.message || '-' }}</NDescriptionsItem>
      </NDescriptions>
      <div v-if="selectedLog" class="mt-16px">
        <div class="mb-8px font-600">结构化数据</div>
        <pre
          class="max-h-360px overflow-auto whitespace-pre-wrap rounded-8px bg-gray-100 p-12px text-12px dark:bg-white/5"
        >{{ JSON.stringify(getLogPayload(selectedLog), null, 2) }}</pre>
      </div>
    </NModal>

    <!-- 扫码登录弹窗 -->
    <NModal
      v-model:show="showQRModal"
      :mask-closable="false"
      preset="card"
      class="w-420px max-w-[calc(100vw-32px)]"
      @after-leave="closeQRModal"
    >
      <template #header>
        {{ $t('page.collector.scanLogin') }}
      </template>

      <div class="flex flex-col items-center py-12px">
        <NSteps class="mb-20px" size="small" :current="loginStatus === 'pending' ? 1 : 2" status="process">
          <NStep title="生成二维码" />
          <NStep title="抖音扫码确认" />
          <NStep title="保存登录状态" />
        </NSteps>
        <div v-if="qrImage" class="mb-16px size-240px rounded-12px bg-white p-10px shadow-sm ring-1 ring-gray-200">
          <img :src="`data:image/png;base64,${qrImage}`" class="size-full" alt="抖音扫码登录二维码" />
        </div>
        <div v-else class="mb-16px size-240px flex-center rounded-12px bg-gray-100 dark:bg-white/5">
          <NSpin :size="24" />
        </div>
        <NAlert
          class="w-full"
          :type="loginStatus === 'failed' || loginStatus === 'timeout' ? 'error' : 'info'"
          :show-icon="true"
        >
          {{ loginMessage || $t('page.collector.scanQrCode') }}
        </NAlert>
      </div>

      <template #footer>
        <NSpace justify="end">
          <NButton @click="closeQRModal">{{ $t('common.cancel') }}</NButton>
          <NButton
            v-if="loginStatus === 'failed' || loginStatus === 'timeout'"
            type="primary"
            @click="handleStartLogin"
          >
            重新生成二维码
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.collector-log-table {
  height: 420px;
}

@media (max-width: 640px) {
  .collector-log-table {
    height: 360px;
  }
}
</style>
