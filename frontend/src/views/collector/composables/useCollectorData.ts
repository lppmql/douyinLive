/**
 * 采集页 — 核心数据与操作管理
 *
 * 职责：管理所有采集相关状态、数据加载、业务操作（监控/采集/ASR/DataEase/日志/账号）。
 * 这是 index.vue 的"大脑"——编排器只负责把 state 和 handler 传给子组件。
 */
import { computed, ref } from 'vue';
import type { MessageApi, DialogApi } from 'naive-ui';
import { $t } from '@/locales';
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';
import { parseBackendTime } from '../utils/collectorHelpers';
import {
  fetchCollectorStatus,
  fetchCollectorAccounts,
  fetchCollectorLogs,
  clearCollectorLogs,
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

export function useCollectorData(message: MessageApi, dialog: DialogApi) {
  /* ==================================================================
   *  一、核心数据状态
   * ================================================================== */

  const loading = ref(true);
  const collectorStatus = ref<Api.Douyin.CollectorStatus | null>(null);
  const accounts = ref<Api.Douyin.CollectorAccount[]>([]);
  const logs = ref<Api.Douyin.CollectorLog[]>([]);
  const tasks = ref<Api.Douyin.CollectorTask[]>([]);

  /** 页面滚动定位 */
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

  /* ==================================================================
   *  二、计算属性
   * ================================================================== */

  const loggedInAccountCount = computed(() =>
    accounts.value.filter(item => item.login_status === 'logged_in').length
  );

  const latestSuccessfulCollectTime = computed(() => {
    const task = tasks.value.find(item => item.task_type === 'collect_all' && item.status === 'completed');
    const value = task?.completed_at || task?.created_at;
    return value ? parseBackendTime(value) : 0;
  });

  const errorLogCount = computed(() =>
    logs.value.filter(
      item => item.level === 'error' && parseBackendTime(item.created_at) > latestSuccessfulCollectTime.value
    ).length
  );

  const historicalErrorCount = computed(() =>
    logs.value.filter(item => item.level === 'error').length
  );

  const hasAvailableAccount = computed(() => loggedInAccountCount.value > 0);

  const activeTasks = computed(() =>
    tasks.value.filter(item => ['pending', 'running'].includes(item.status))
  );

  const currentCollectTask = computed(() =>
    tasks.value.find(item => item.task_type === 'collect_all')
  );

  const collectionRunning = computed(() =>
    collectAllLoading.value || activeTasks.value.some(item => item.task_type === 'collect_all')
  );

  const collectDisabledReason = computed(() => {
    if (!hasAvailableAccount.value) return '请先扫码登录可用采集账号';
    if (collectionRunning.value) return '已有刷新数据采集任务正在运行，请勿重复提交';
    return '';
  });

  /* ==================================================================
   *  三、数据加载（并行拉取 7 个 API）
   * ================================================================== */

  async function loadData(silent = false) {
    if (silent) silentRefreshing.value = true;
    else loading.value = true;
    try {
      const [statusRes, accountsRes, logsRes, tasksRes, monitorRes, asrRes, dataEaseRes] =
        await Promise.allSettled([
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

  /* ==================================================================
   *  四、监控操作
   * ================================================================== */

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

  /* ==================================================================
   *  五、刷新数据采集
   * ================================================================== */

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

  /* ==================================================================
   *  六、DataEase 同步
   * ================================================================== */

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

  /* ==================================================================
   *  七、ASR 话术
   * ================================================================== */

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

  /* ==================================================================
   *  八、日志操作
   * ================================================================== */

  /** 通用滚动定位（页面锚点跳转 + 高亮动画） */
  function scrollToSection(
    section: typeof accountSectionRef,
    highlight: typeof accountHighlight
  ) {
    section.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    highlight.value = true;
    window.setTimeout(() => {
      highlight.value = false;
    }, 1800);
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

  /* ==================================================================
   *  九、账号操作
   * ================================================================== */

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

  /* ==================================================================
   *  十、导航辅助
   * ================================================================== */

  function openAccounts() {
    scrollToSection(accountSectionRef, accountHighlight);
  }

  function openTasks() {
    taskDrawerVisible.value = true;
  }

  async function openErrors() {
    await filterLogs('error');
  }

  function openLogDetail(log: Api.Douyin.CollectorLog) {
    selectedLog.value = log;
    logDetailVisible.value = true;
  }

  /* ==================================================================
   *  十一、导出
   * ================================================================== */

  return {
    // ── 状态 ──
    loading,
    collectorStatus,
    accounts,
    logs,
    tasks,
    accountSectionRef,
    logSectionRef,
    accountHighlight,
    logHighlight,
    logLevel,
    logTaskId,
    silentRefreshing,
    clearLogsLoading,
    logDetailVisible,
    selectedLog,
    accountHealthLoadingId,
    asrStatus,
    asrControlLoading,
    dataEaseStatus,
    dataEaseSyncLoading,
    dataLoadFailedCount,
    lastDataUpdatedAt,
    monitorStatus,
    monitorLoading,
    collectAllLoading,
    collectAllResult,
    taskDrawerVisible,

    // ── 计算属性 ──
    loggedInAccountCount,
    latestSuccessfulCollectTime,
    errorLogCount,
    historicalErrorCount,
    hasAvailableAccount,
    activeTasks,
    currentCollectTask,
    collectionRunning,
    collectDisabledReason,

    // ── 核心方法 ──
    loadData,

    // ── 操作处理器 ──
    handleStartMonitor,
    handleStopMonitor,
    handleTriggerLive,
    handleTriggerEnd,
    handleCollectAll,
    handleDataEaseSync,
    handleAsrToggle,
    filterLogs,
    viewTaskLogs,
    clearTaskLogFilter,
    handleClearLogs,
    handleAccountHealth,
    handleDeleteAccount,

    // ── 导航 ──
    openAccounts,
    openTasks,
    openErrors,
    openLogDetail
  };
}
