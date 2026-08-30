import { onMounted, ref } from 'vue';
import type { AnchorSelectorOption, SessionDateRange } from '@/adapters/session-selector-adapter';
import {
  buildAnchorSelectorOptions,
  buildSelectorDateParams,
  getShanghaiTodayCalendarTimestamp,
  shiftSelectorCalendarDate
} from '@/adapters/session-selector-adapter';
import { fetchDashboardOperations, fetchSessionAnchorOptions } from '@/service/api/douyin';

/**
 * 原生经营大屏的数据入口。
 *
 * 页面只消费这一份组合状态，筛选条件、并发请求和错误处理不会散落到多个卡片中。
 */
export function useDashboardData() {
  const today = getShanghaiTodayCalendarTimestamp();
  const loading = ref(false);
  const loadError = ref('');
  const anchorKey = ref<string | null>(null);
  const dateRange = ref<SessionDateRange>([shiftSelectorCalendarDate(today, -29), today]);
  const anchorOptions = ref<AnchorSelectorOption[]>([]);
  const dashboard = ref<Api.Douyin.DashboardOperations | null>(null);
  let dashboardRequestGeneration = 0;

  async function loadAnchorOptions() {
    const response = await fetchSessionAnchorOptions();
    if (response.data) {
      anchorOptions.value = buildAnchorSelectorOptions(response.data);
    }
    if (response.error) {
      loadError.value = `主播筛选加载失败：${response.error.message || '未知错误'}`;
    }
  }

  async function loadDashboard() {
    const requestGeneration = ++dashboardRequestGeneration;
    loading.value = true;
    loadError.value = '';
    const dateParams = buildSelectorDateParams(dateRange.value);
    try {
      const response = await fetchDashboardOperations(
        dateParams.start_date,
        dateParams.end_date,
        anchorKey.value || undefined
      );
      // 用户快速切换筛选时，较早请求可能更晚返回；旧响应不得覆盖当前口径。
      if (requestGeneration !== dashboardRequestGeneration) return;
      if (response.data) dashboard.value = response.data;
      if (response.error) {
        loadError.value = `经营数据加载失败：${response.error.message || '未知错误'}`;
      }
    } catch (error) {
      if (requestGeneration !== dashboardRequestGeneration) return;
      loadError.value = (error as { message?: string }).message || '经营数据加载失败';
    } finally {
      if (requestGeneration === dashboardRequestGeneration) loading.value = false;
    }
  }

  async function refresh() {
    await Promise.all([loadAnchorOptions(), loadDashboard()]);
  }

  function resetFilters() {
    const currentToday = getShanghaiTodayCalendarTimestamp();
    anchorKey.value = null;
    dateRange.value = [shiftSelectorCalendarDate(currentToday, -29), currentToday];
  }

  onMounted(refresh);

  return {
    loading,
    loadError,
    anchorKey,
    dateRange,
    anchorOptions,
    dashboard,
    loadDashboard,
    refresh,
    resetFilters
  };
}
