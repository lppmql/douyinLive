/**
 * 主播排班页面 — 全部状态管理
 *
 * 把 index.vue 中所有 ref、computed、异步操作、生命周期集中到这里，
 * index.vue 只负责布局 + 传 props 给子组件。
 *
 * 使用方式：
 * ```ts
 * const as = useAnchorSchedule();
 * onMounted(as.initializePage);
 * ```
 */
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue';
import dayjs from 'dayjs';
import { useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import { fetchAnchorScheduleDashboard } from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import { createColumns, type ColumnDependencies } from '@/adapters/anchor-schedule-adapter';

export function useAnchorSchedule() {
  const router = useRouter();
  const message = useMessage();

  // ========== 响应式状态 ==========

  const loading = ref(false);
  const dashboard = ref<Api.Douyin.AnchorScheduleDashboard | null>(null);
  const todayTimestamp = dayjs().startOf('day').valueOf();
  const selectedRange = ref<[number, number]>([todayTimestamp, todayTimestamp]);
  const selectedAnchor = ref<string | null>(null);
  const reminderDrawerVisible = ref(false);
  const loadError = ref('');
  let refreshTimer: ReturnType<typeof setInterval> | null = null;

  // ========== 计算属性 ==========

  const selectedStartDate = computed(() => dayjs(selectedRange.value[0]).format('YYYY-MM-DD'));
  const selectedEndDate = computed(() => dayjs(selectedRange.value[1]).format('YYYY-MM-DD'));

  /** 日期标签：同一天只显示一个日期，跨天显示范围 */
  const selectedDateLabel = computed(() =>
    selectedStartDate.value === selectedEndDate.value
      ? selectedStartDate.value
      : `${selectedStartDate.value} 至 ${selectedEndDate.value}`
  );

  /** 当前日期范围是否包含今天（决定是否开启自动刷新） */
  const includesToday = computed(() => {
    const today = dayjs().format('YYYY-MM-DD');
    return selectedStartDate.value <= today && selectedEndDate.value >= today;
  });

  /** 根据选中主播筛选后的排班行数据 */
  const visibleRows = computed(() => {
    if (!selectedAnchor.value) return dashboard.value?.rows || [];
    return (dashboard.value?.rows || []).filter(item => item.source_anchor_name === selectedAnchor.value);
  });

  /** 表格列定义（依赖 dashboard 和 openSession，通过适配器生成） */
  const columns = computed(() => {
    const deps: ColumnDependencies = {
      dashboard: dashboard.value,
      onOpenSession: openSession
    };
    return createColumns(deps);
  });

  // ========== 操作函数 ==========

  /** 跳转到场次详情页 */
  function openSession(sessionId: number | null) {
    if (!sessionId) return;
    router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
  }

  /** 设置日期偏移（-1=昨天, 0=今天），选中单天 */
  function setDateOffset(offset: number) {
    const timestamp = dayjs().add(offset, 'day').startOf('day').valueOf();
    selectedRange.value = [timestamp, timestamp];
    selectedAnchor.value = null;
    void loadSchedule();
  }

  /** 设置近 N 天范围（以今天为结束日期） */
  function setRecentDays(dayCount: number) {
    const endTimestamp = dayjs().startOf('day').valueOf();
    selectedRange.value = [
      dayjs(endTimestamp)
        .subtract(dayCount - 1, 'day')
        .valueOf(),
      endTimestamp
    ];
    selectedAnchor.value = null;
    void loadSchedule();
  }

  /** 日期选择器变更回调，校验范围不超过 31 天 */
  function handleDateChange(value: [number, number] | null) {
    if (value === null) return;
    if (dayjs(value[1]).diff(dayjs(value[0]), 'day') >= 31) {
      message.warning('单次最多查询连续 31 天，请缩短起止日期范围');
      return;
    }
    selectedRange.value = value;
    selectedAnchor.value = null;
    void loadSchedule();
  }

  /** 切换主播筛选（点击同一个主播取消筛选） */
  function toggleAnchor(anchorName: string) {
    selectedAnchor.value = selectedAnchor.value === anchorName ? null : anchorName;
  }

  /** 加载排班数据 */
  async function loadSchedule(silent = false) {
    if (!silent) loading.value = true;
    try {
      const response = await fetchAnchorScheduleDashboard(selectedStartDate.value, selectedEndDate.value);
      dashboard.value = unwrapServiceData(response, '排班数据加载失败，请检查后端服务和数据库迁移');
      loadError.value = '';
    } catch (error) {
      if (!silent) {
        loadError.value = error instanceof Error ? error.message : '排班数据加载失败，请检查后端服务和数据库迁移';
        message.error(loadError.value);
      }
    } finally {
      if (!silent) loading.value = false;
    }
  }

  /** 启动自动刷新（每 60 秒静默刷新，仅页面可见且包含今天时生效） */
  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      if (includesToday.value && document.visibilityState === 'visible') void loadSchedule(true);
    }, 60_000);
  }

  /** 停止自动刷新 */
  function stopAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
  }

  // ========== 生命周期 ==========

  onMounted(() => {
    void loadSchedule();
    startAutoRefresh();
  });

  onActivated(() => {
    if (!refreshTimer) {
      void loadSchedule(true);
      startAutoRefresh();
    }
  });

  onDeactivated(() => {
    stopAutoRefresh();
  });

  onBeforeUnmount(() => {
    stopAutoRefresh();
  });

  // ========== 返回全部状态和操作 ==========

  return {
    // 状态
    loading,
    loadError,
    dashboard,
    selectedRange,
    selectedAnchor,
    reminderDrawerVisible,
    // 计算属性
    selectedStartDate,
    selectedEndDate,
    selectedDateLabel,
    includesToday,
    visibleRows,
    columns,
    // 操作
    setDateOffset,
    setRecentDays,
    handleDateChange,
    toggleAnchor,
    openSession,
    loadSchedule
  };
}
