<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue';
import { NButton, NSpace, NTag, useDialog, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import {
  fetchCollectorStatus,
  fetchCollectorAccounts,
  fetchCollectorLogs,
  startCollectorLogin,
  fetchLoginQR,
  fetchLoginStatus,
  reCollectorLogin,
  deleteCollectorAccount,
  checkCollectorAccountHealth,
  fetchCollectorTasks,
  fetchAsrControlStatus,
  setAsrControl,
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
const asrStatus = ref<Api.Douyin.AsrControlStatus | null>(null);
const asrControlLoading = ref(false);

const loggedInAccountCount = computed(() => accounts.value.filter(item => item.login_status === 'logged_in').length);
const errorLogCount = computed(() => logs.value.filter(item => item.level === 'error').length);
const hasAvailableAccount = computed(() => loggedInAccountCount.value > 0);
const activeTasks = computed(() => tasks.value.filter(item => ['pending', 'running'].includes(item.status)));
const currentCollectTask = computed(() =>
  tasks.value.find(item => item.task_type === 'collect_all' && item.status === 'running')
);

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

/* ---------- 一键采集 ---------- */
const collectAllLoading = ref(false);
const collectAllResult = ref<Api.Douyin.CollectAllResponse | null>(null);
const collectionRunning = computed(
  () => collectAllLoading.value || activeTasks.value.some(item => item.task_type === 'collect_all')
);
const collectDisabledReason = computed(() => {
  if (!hasAvailableAccount.value) return '请先扫码登录可用采集账号';
  if (monitorStatus.value?.running) return '当前正在直播监控中，请先停止监控再执行全量历史采集';
  if (collectionRunning.value) return '已有全量采集任务正在运行，请勿重复提交';
  return '';
});

async function loadMonitorStatus() {
  const res = await fetchMonitorStatus();
  if (res.data) monitorStatus.value = res.data;
}

async function handleStartMonitor() {
  if (collectionRunning.value) {
    message.warning('全量采集正在运行，请等待任务结束后再启动监控');
    return;
  }
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

/* ---------- 一键采集 ---------- */
async function handleCollectAll() {
  collectAllLoading.value = true;
  collectAllResult.value = null;
  try {
    const res = await collectAllData();
    collectAllResult.value = res.data;
    if (res.data?.collected_rooms && res.data.collected_rooms > 0) {
      message.success(`采集完成：${res.data.collected_rooms}/${res.data.total_rooms} 个房间`);
      if ((res.data.history_detail_remaining_count || 0) > 0) {
        message.info(
          `历史场次本次补齐 ${res.data.history_detail_synced_count} 场，剩余 ${res.data.history_detail_remaining_count} 场，继续点一次会接着补`
        );
      }
    } else if (res.data?.message) {
      message.warning(res.data.message);
    }
  } catch {
    message.error('一键采集失败');
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
    const [statusRes, accountsRes, logsRes, tasksRes, monitorRes, asrRes] = await Promise.all([
      fetchCollectorStatus(),
      fetchCollectorAccounts(),
      fetchCollectorLogs({
        limit: 100,
        level: logLevel.value === 'all' ? undefined : logLevel.value,
        taskId: logTaskId.value || undefined
      }),
      fetchCollectorTasks(),
      fetchMonitorStatus(),
      fetchAsrControlStatus()
    ]);
    if (statusRes.data != null) collectorStatus.value = statusRes.data;
    if (accountsRes.data != null) accounts.value = accountsRes.data;
    if (logsRes.data != null) logs.value = logsRes.data;
    if (tasksRes.data != null) tasks.value = tasksRes.data;
    if (monitorRes.data != null) monitorStatus.value = monitorRes.data;
    if (asrRes.data != null) asrStatus.value = asrRes.data;
  } catch {
    if (!silent) message.error('加载采集数据失败');
  } finally {
    if (silent) silentRefreshing.value = false;
    else loading.value = false;
  }
}

async function handleAsrToggle(enabled: boolean) {
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
        collect_all: '全量采集',
        login: '扫码登录',
        metrics: '指标采集',
        comments: '评论采集',
        leads: '留资采集',
        profile: '画像采集'
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
  <div class="min-h-full flex-col gap-16px overflow-auto">
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
              <NButton class="mt-12px" text type="error" size="tiny" @click.stop="openErrors">
                近 50 条日志中 {{ errorLogCount }} 条异常，点击查看
              </NButton>
            </NCard>
          </NGi>
        </NGrid>

        <NGrid cols="1 l:3" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:2">
            <NCard :bordered="false" class="card-wrapper h-full" title="全量数据采集">
              <template #header-extra>
                <NTag v-if="collectAllLoading" type="warning" round size="small">任务执行中</NTag>
                <NTag v-else-if="hasAvailableAccount" type="success" round size="small">账号已就绪</NTag>
                <NTag v-else type="error" round size="small">请先扫码登录</NTag>
              </template>
              <div class="flex flex-col gap-16px">
                <NAlert type="info" :show-icon="true" :bordered="false">
                  自动发现账号下全部主播，依次同步直播场次、主播资料、指标、评论和观众画像。采集期间请勿删除当前账号。
                </NAlert>
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
                        ASR 话术生成
                        <NTag :type="asrStatus?.enabled ? 'success' : 'default'" round size="small">
                          {{ asrStatus?.enabled ? '已开启' : '已关闭' }}
                        </NTag>
                      </div>
                      <div class="mt-3px text-12px text-gray-500">
                        <template v-if="asrStatus?.enabled">
                          模型与 Worker 正在运行 · 排队 {{ asrStatus.queued_count }} · 处理中
                          {{ asrStatus.processing_count }}
                        </template>
                        <template v-else>按需开启；关闭时不占用 FunASR 模型内存</template>
                      </div>
                    </div>
                  </div>
                  <NSwitch
                    :value="Boolean(asrStatus?.enabled)"
                    :loading="asrControlLoading"
                    :disabled="Boolean(asrStatus?.processing_count)"
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
                          {{ collectAllLoading ? '正在采集全部数据' : '开始全量采集' }}
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
                    <NTag type="primary" round>任务 #{{ currentCollectTask.id }}</NTag>
                  </div>
                  <NProgress
                    type="line"
                    :percentage="currentCollectTask.progress_percent || 0"
                    indicator-placement="inside"
                    processing
                  />
                  <div class="mt-8px flex justify-between text-12px text-gray-500">
                    <span>
                      已完成 {{ currentCollectTask.progress_current || 0 }}
                      <template v-if="currentCollectTask.progress_total">
                        / {{ currentCollectTask.progress_total }}
                      </template>
                    </span>
                    <span>页面每 5 秒自动更新</span>
                  </div>
                  <NGrid class="mt-12px" cols="2" :x-gap="12">
                    <NGi>
                      <div class="rounded-8px bg-white/70 px-12px py-10px dark:bg-black/15">
                        <div class="text-12px text-gray-500">已采集主播</div>
                        <div class="mt-2px text-20px font-600">
                          {{ currentCollectTask.collected_anchor_count || 0 }} 位
                        </div>
                      </div>
                    </NGi>
                    <NGi>
                      <div class="rounded-8px bg-white/70 px-12px py-10px dark:bg-black/15">
                        <div class="text-12px text-gray-500">已采集场次</div>
                        <div class="mt-2px text-20px font-600">
                          {{ currentCollectTask.collected_session_count || 0 }} 场
                        </div>
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
                    <span v-if="collectAllResult.message" class="text-12px text-gray-500">
                      {{ collectAllResult.message }}
                    </span>
                  </div>
                  <NGrid cols="2 s:3 l:6" responsive="screen" :x-gap="12" :y-gap="12">
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
                      <NStatistic label="本次补详情" :value="collectAllResult.history_detail_synced_count || 0" />
                    </NGi>
                    <NGi>
                      <NStatistic label="剩余待补" :value="collectAllResult.history_detail_remaining_count || 0" />
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
                <NTag v-if="monitorStatus?.mock_mode" type="warning" round size="small">Mock 模式</NTag>
              </template>
              <div class="flex flex-col gap-16px">
                <div class="flex items-center justify-between gap-12px rounded-8px bg-gray-100 p-12px dark:bg-white/5">
                  <div>
                    <div class="font-600">{{ monitorStatus?.running ? '正在监听开播状态' : '监控服务未启动' }}</div>
                    <div class="mt-4px text-12px text-gray-500">
                      活跃场次 {{ monitorStatus?.active_session_count || 0 }} 场
                    </div>
                  </div>
                  <NBadge :type="monitorStatus?.running ? 'success' : 'default'" dot />
                </div>
                <NButton
                  block
                  :type="monitorStatus?.running ? 'warning' : 'primary'"
                  :loading="monitorLoading"
                  :disabled="!monitorStatus?.running && collectionRunning"
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
              </NSpace>
            </template>
            <NDataTable
              :loading="loading"
              :columns="logColumns"
              :data="logs"
              :row-key="getLogRowKey"
              :scroll-x="1260"
              :bordered="false"
              size="small"
            />
          </NCard>
        </div>
      </NSpace>
    </NSpin>

    <NDrawer v-model:show="taskDrawerVisible" :width="560" placement="right">
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

<style scoped></style>
