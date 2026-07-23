/** 数据采集页状态与交互，页面组件只负责布局和展示。 */
import { computed, ref } from 'vue';
import type { ComponentPublicInstance } from 'vue';
import type { DialogApi, MessageApi } from 'naive-ui';
import { $t } from '@/locales';
import { getServiceErrorMessage, unwrapServiceData } from '@/utils/service';
import {
  checkCollectorAccountHealth,
  clearCollectorLogs,
  deleteCollectorAccount,
  fetchCollectorAccounts,
  fetchCollectorControlCenter,
  fetchCollectorLogs,
  fetchCollectorTaskQueue,
  retryCollectorQueueTask,
  startCollectorModule,
  stopCollectorModule,
  stopCollectorQueueTask
} from '@/service/api/douyin';

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function useCollectorData(message: MessageApi, dialog: DialogApi) {
  const loading = ref(true);
  const silentRefreshing = ref(false);
  const controlCenter = ref<Api.Douyin.CollectorControlCenter | null>(null);
  const accounts = ref<Api.Douyin.CollectorAccount[]>([]);
  const logs = ref<Api.Douyin.CollectorLog[]>([]);
  const tasks = ref<Api.Douyin.UnifiedCollectorTask[]>([]);
  const dataLoadFailedCount = ref(0);
  const lastDataUpdatedAt = ref<number | null>(null);

  const moduleLoadingKeys = ref<Record<string, boolean>>({});
  const taskActionLoadingKey = ref<string | null>(null);
  const accountHealthLoadingId = ref<number | null>(null);
  const clearLogsLoading = ref(false);

  const accountSectionRef = ref<HTMLElement | null>(null);
  const logSectionRef = ref<HTMLElement | null>(null);
  const accountHighlight = ref(false);
  const logHighlight = ref(false);

  const logLevel = ref('all');
  const logTaskId = ref<number | null>(null);
  const logDetailVisible = ref(false);
  const selectedLog = ref<Api.Douyin.CollectorLog | null>(null);
  const taskDrawerVisible = ref(false);

  const loggedInAccountCount = computed(() =>
    accounts.value.filter(item => item.login_status === 'logged_in').length
  );
  const hasAvailableAccount = computed(() =>
    accounts.value.some(
      item =>
        item.login_status === 'logged_in' &&
        item.cookie_saved &&
        !['expired', 'missing'].includes(item.cookie_status)
    )
  );
  const collectionRunning = computed(() =>
    Boolean(controlCenter.value?.modules.find(item => item.key === 'data_refresh')?.processing_count)
  );
  const errorLogCount = computed(() => logs.value.filter(item => item.level === 'error').length);
  const shouldPoll = computed(() => {
    if (taskDrawerVisible.value || (controlCenter.value?.active_task_count || 0) > 0) return true;
    return Boolean(
      controlCenter.value?.modules.some(
        item => (item.mode === 'service' && item.enabled) || (item.mode === 'automatic' && item.pending_count > 0)
      )
    );
  });

  async function loadData(silent = false, includeAccounts = true) {
    if (silent) silentRefreshing.value = true;
    else loading.value = true;
    try {
      const results = await Promise.allSettled([
        fetchCollectorControlCenter(),
        includeAccounts ? fetchCollectorAccounts() : Promise.resolve(null),
        fetchCollectorLogs({
          limit: 200,
          level: logLevel.value === 'all' ? undefined : logLevel.value,
          task_id: logTaskId.value || undefined
        }),
        fetchCollectorTaskQueue(150)
      ]);
      const [centerResult, accountsResult, logsResult, tasksResult] = results;
      if (centerResult.status === 'fulfilled' && centerResult.value.data) controlCenter.value = centerResult.value.data;
      if (accountsResult.status === 'fulfilled' && accountsResult.value?.data) accounts.value = accountsResult.value.data;
      if (logsResult.status === 'fulfilled' && logsResult.value.data) logs.value = logsResult.value.data;
      if (tasksResult.status === 'fulfilled' && tasksResult.value.data) tasks.value = tasksResult.value.data;

      dataLoadFailedCount.value = results.filter((result, index) => {
        if (!includeAccounts && index === 1) return false;
        return result.status === 'rejected' || Boolean(result.value?.error);
      }).length;
      lastDataUpdatedAt.value = Date.now();
      if (dataLoadFailedCount.value && !silent) {
        message.warning(`${dataLoadFailedCount.value} 项状态暂时未更新，其余真实数据已正常展示`);
      }
    } catch (error) {
      dataLoadFailedCount.value = 4;
      if (!silent) message.error(errorText(error, '加载数据采集页面失败'));
    } finally {
      if (silent) silentRefreshing.value = false;
      else loading.value = false;
    }
  }

  async function applyModuleToggle(module: Api.Douyin.CollectorModuleStatus, enabled: boolean) {
    moduleLoadingKeys.value = { ...moduleLoadingKeys.value, [module.key]: true };
    try {
      const response = enabled
        ? await startCollectorModule(module.key)
        : await stopCollectorModule(module.key);
      const data = unwrapServiceData(response, `${module.label}${enabled ? '启动' : '停止'}失败`);
      message.success(data.message);
      await loadData(true);
    } catch (error) {
      message.error(errorText(error, `${module.label}${enabled ? '启动' : '停止'}失败`));
      await loadData(true);
    } finally {
      moduleLoadingKeys.value = { ...moduleLoadingKeys.value, [module.key]: false };
    }
  }

  function handleModuleToggle(module: Api.Douyin.CollectorModuleStatus, enabled: boolean) {
    if (enabled) {
      void applyModuleToggle(module, true);
      return;
    }
    const processingText = module.processing_count ? `当前正在处理 ${module.processing_count} 项。` : '';
    dialog.warning({
      title: `确认停止${module.label}`,
      content: `${processingText}关闭后不再创建新批次，当前任务会在安全检查点停止；专属 Worker、模型或浏览器会在不再被其他模块使用时退出，已完成数据不会删除。`,
      positiveText: '关闭并释放资源',
      negativeText: '继续运行',
      onPositiveClick: () => applyModuleToggle(module, false)
    });
  }

  function handleDataRefresh(_module: Api.Douyin.CollectorModuleStatus) {
    dialog.warning({
      title: '全部场次数据补齐刷新',
      content:
        '系统会检查全部主播和全部直播场次，补齐指标、评论、画像与流地址。刷新拥有浏览器优先权，实时监控会暂时交出登录会话，完成后自动恢复。',
      positiveText: '开始补齐刷新',
      negativeText: '取消',
      onPositiveClick: async () => {
        moduleLoadingKeys.value = { ...moduleLoadingKeys.value, data_refresh: true };
        try {
          const response = await startCollectorModule('data_refresh');
          message.success(unwrapServiceData(response, '全部场次数据补齐刷新启动失败').message);
          await loadData(true);
          taskDrawerVisible.value = true;
        } catch (error) {
          message.error(errorText(error, '全部场次数据补齐刷新启动失败'));
          await loadData(true);
        } finally {
          moduleLoadingKeys.value = { ...moduleLoadingKeys.value, data_refresh: false };
        }
      }
    });
  }

  function handleStopTask(task: Api.Douyin.UnifiedCollectorTask) {
    const content =
      task.task_type === 'collect_all'
        ? '停止后会保留已补齐的数据；实时监控将立即恢复。需要时可重新点击补齐刷新或在任务队列重试。'
        : ['knowledge_sync', 'dataease_sync'].includes(task.task_type)
          ? '这里只停止当前后台同步批次；源数据不会丢失，系统下一轮会自动继续处理尚未同步的场次。'
          : '这里只停止当前任务；已写入的真实数据和完成的音频分片会保留。ASR 开关仍开启时会继续处理下一场。';
    dialog.warning({
      title: `停止${task.task_label}`,
      content,
      positiveText: '停止任务',
      negativeText: '取消',
      onPositiveClick: async () => {
        taskActionLoadingKey.value = task.task_key;
        try {
          const response = await stopCollectorQueueTask(task);
          message.success(unwrapServiceData(response, '停止任务失败').message);
          await loadData(true);
        } catch (error) {
          message.error(errorText(error, '停止任务失败'));
        } finally {
          taskActionLoadingKey.value = null;
        }
      }
    });
  }

  async function handleRetryTask(task: Api.Douyin.UnifiedCollectorTask) {
    taskActionLoadingKey.value = task.task_key;
    try {
      const response = await retryCollectorQueueTask(task);
      message.success(unwrapServiceData(response, '重试任务失败').message);
      await loadData(true);
    } catch (error) {
      message.error(errorText(error, '重试任务失败'));
    } finally {
      taskActionLoadingKey.value = null;
    }
  }

  function scrollToSection(section: typeof accountSectionRef, highlight: typeof accountHighlight) {
    section.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    highlight.value = true;
    window.setTimeout(() => {
      highlight.value = false;
    }, 1800);
  }

  function setAccountSectionRef(element: Element | ComponentPublicInstance | null) {
    accountSectionRef.value = element as HTMLElement | null;
  }

  function setLogSectionRef(element: Element | ComponentPublicInstance | null) {
    logSectionRef.value = element as HTMLElement | null;
  }

  async function filterLogs(level: string) {
    logLevel.value = level;
    await loadData(true);
  }

  async function viewTaskLogs(task: Api.Douyin.UnifiedCollectorTask) {
    if (task.source === 'asr') {
      taskDrawerVisible.value = false;
      message.info('ASR 任务详情已包含主播、场次、分片进度与失败原因');
      return;
    }
    logTaskId.value = task.id;
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
      content: '只清空日志记录，不会删除账号、任务、主播或直播场次。运行中的任务仍会继续产生新日志。',
      positiveText: '确认清空日志',
      negativeText: $t('common.cancel'),
      onPositiveClick: async () => {
        clearLogsLoading.value = true;
        try {
          const response = await clearCollectorLogs();
          const count = unwrapServiceData(response, '清空采集日志失败').deleted_count || 0;
          logs.value = [];
          logDetailVisible.value = false;
          selectedLog.value = null;
          message.success(`已清空 ${count} 条采集日志`);
          await loadData(true);
        } catch (error) {
          message.error(errorText(error, '清空采集日志失败'));
        } finally {
          clearLogsLoading.value = false;
        }
      }
    });
  }

  async function handleAccountHealth(row: Api.Douyin.CollectorAccount) {
    accountHealthLoadingId.value = row.id;
    try {
      const response = await checkCollectorAccountHealth(row.id);
      const data = unwrapServiceData(response, '检查 Cookie 状态失败');
      if (data.valid) message.success(`${data.douyin_nickname || row.account_name || '采集账号'}：${data.message}`);
      else message.warning(data.message);
      await loadData(true);
    } catch (error) {
      message.error(errorText(error, '检查 Cookie 状态失败'));
    } finally {
      accountHealthLoadingId.value = null;
    }
  }

  async function handleDeleteAccount(accountId: number) {
    const account = accounts.value.find(item => item.id === accountId);
    dialog.warning({
      title: '删除采集账号',
      content: `确定删除“${account?.douyin_nickname || account?.account_name || `账号 #${accountId}`}”吗？Cookie 与浏览器指纹会被清空，后续必须重新扫码；历史直播数据不会删除。`,
      positiveText: '删除账号与登录状态',
      negativeText: $t('common.cancel'),
      onPositiveClick: async () => {
        try {
          const response = await deleteCollectorAccount(accountId);
          if (response.error) throw new Error(getServiceErrorMessage(response.error, '删除采集账号失败'));
          message.success('采集账号已删除');
          await loadData();
        } catch (error) {
          message.error(errorText(error, '删除采集账号失败'));
        }
      }
    });
  }

  function openLogDetail(log: Api.Douyin.CollectorLog) {
    selectedLog.value = log;
    logDetailVisible.value = true;
  }

  return {
    loading,
    silentRefreshing,
    controlCenter,
    accounts,
    logs,
    tasks,
    dataLoadFailedCount,
    lastDataUpdatedAt,
    moduleLoadingKeys,
    taskActionLoadingKey,
    accountHealthLoadingId,
    clearLogsLoading,
    accountSectionRef,
    logSectionRef,
    accountHighlight,
    logHighlight,
    setAccountSectionRef,
    setLogSectionRef,
    logLevel,
    logTaskId,
    logDetailVisible,
    selectedLog,
    taskDrawerVisible,
    loggedInAccountCount,
    hasAvailableAccount,
    collectionRunning,
    errorLogCount,
    shouldPoll,
    loadData,
    handleModuleToggle,
    handleDataRefresh,
    handleStopTask,
    handleRetryTask,
    filterLogs,
    viewTaskLogs,
    clearTaskLogFilter,
    handleClearLogs,
    handleAccountHealth,
    handleDeleteAccount,
    openLogDetail
  };
}
