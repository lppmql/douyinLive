/** 公共场次筛选状态：统一主播、日期、远程搜索和重置行为。 */
import { computed, ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { useMessage } from 'naive-ui';
import {
  buildAnchorSelectorOptions,
  buildSelectorDateParams,
  type SessionDateRange
} from '@/adapters/session-selector-adapter';
import {
  fetchSessionAnchorOptions,
  type SessionSelectorFilters
} from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';

export interface SessionSelectorChangeContext {
  /** 只有最近一次筛选仍返回 true；页面据此丢弃过期响应。 */
  isCurrent: () => boolean;
}

export function useSessionSelectorFilters(
  onChange: (context: SessionSelectorChangeContext) => void | Promise<void>
) {
  const message = useMessage();
  const anchorKey = ref<string | null>(null);
  const dateRange = ref<SessionDateRange>(null);
  const searchKeyword = ref('');
  const anchors = ref<Api.Douyin.LiveSessionAnchorOption[]>([]);
  let changeGeneration = 0;

  const anchorOptions = computed(() => buildAnchorSelectorOptions(anchors.value));

  async function loadAnchors() {
    try {
      const response = await fetchSessionAnchorOptions();
      anchors.value = unwrapServiceData(response, '主播筛选项读取失败');
    } catch (error) {
      anchors.value = [];
      console.error('[session-selector] 主播筛选项读取失败:', error);
      message.warning('主播列表暂时不可用，仍可按日期或关键词选择场次');
    }
  }

  function buildQuery(includeSessionId?: number | null): SessionSelectorFilters {
    return {
      limit: 50,
      search: searchKeyword.value.trim() || undefined,
      anchor_key: anchorKey.value || undefined,
      ...buildSelectorDateParams(dateRange.value),
      include_session_id: includeSessionId || undefined
    };
  }

  async function notifyChange() {
    const generation = ++changeGeneration;
    await onChange({ isCurrent: () => generation === changeGeneration });
  }

  async function updateAnchor(value: string | null) {
    anchorKey.value = value;
    await notifyChange();
  }

  async function updateDateRange(value: SessionDateRange) {
    dateRange.value = value;
    await notifyChange();
  }

  const search = useDebounceFn(async (keyword: string) => {
    searchKeyword.value = keyword;
    await notifyChange();
  }, 300);

  async function reset() {
    anchorKey.value = null;
    dateRange.value = null;
    searchKeyword.value = '';
    await notifyChange();
  }

  return {
    anchorKey,
    dateRange,
    searchKeyword,
    anchorOptions,
    loadAnchors,
    buildQuery,
    updateAnchor,
    updateDateRange,
    search,
    reset
  };
}
