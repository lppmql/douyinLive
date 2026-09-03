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
  /** replace 用于新筛选，append 用于滚动加载下一页。 */
  mode: 'replace' | 'append';
  offset: number;
  limit: number;
}

const SESSION_SELECTOR_PAGE_SIZE = 100;

/** 追加下一页并按业务主键去重，保留服务端的倒序排列。 */
export function appendUniqueSelectorPage<T>(
  current: T[],
  incoming: T[],
  getKey: (item: T) => number
): T[] {
  const existingKeys = new Set(current.map(getKey));
  const additions = incoming.filter(item => {
    const key = getKey(item);
    if (existingKeys.has(key)) return false;
    existingKeys.add(key);
    return true;
  });
  return [...current, ...additions];
}

export function useSessionSelectorFilters(
  onChange: (context: SessionSelectorChangeContext) => number | void | Promise<number | void>
) {
  const message = useMessage();
  const anchorKey = ref<string | null>(null);
  const dateRange = ref<SessionDateRange>(null);
  const searchKeyword = ref('');
  const anchors = ref<Api.Douyin.LiveSessionAnchorOption[]>([]);
  const hasMore = ref(true);
  const loadingMore = ref(false);
  let changeGeneration = 0;
  let nextOffset = SESSION_SELECTOR_PAGE_SIZE;

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

  function buildQuery(
    includeSessionId?: number | null,
    context?: SessionSelectorChangeContext
  ): SessionSelectorFilters {
    return {
      limit: context?.limit || SESSION_SELECTOR_PAGE_SIZE,
      offset: context?.offset || 0,
      search: searchKeyword.value.trim() || undefined,
      anchor_key: anchorKey.value || undefined,
      ...buildSelectorDateParams(dateRange.value),
      include_session_id: includeSessionId || undefined
    };
  }

  async function notifyChange() {
    const generation = ++changeGeneration;
    nextOffset = SESSION_SELECTOR_PAGE_SIZE;
    hasMore.value = true;
    const context: SessionSelectorChangeContext = {
      isCurrent: () => generation === changeGeneration,
      mode: 'replace',
      offset: 0,
      limit: SESSION_SELECTOR_PAGE_SIZE
    };
    const count = await onChange(context);
    if (context.isCurrent() && typeof count === 'number') {
      hasMore.value = count >= SESSION_SELECTOR_PAGE_SIZE;
    }
  }

  async function loadMore() {
    if (loadingMore.value || !hasMore.value) return;
    const generation = changeGeneration;
    const context: SessionSelectorChangeContext = {
      isCurrent: () => generation === changeGeneration,
      mode: 'append',
      offset: nextOffset,
      limit: SESSION_SELECTOR_PAGE_SIZE
    };
    loadingMore.value = true;
    try {
      const count = await onChange(context);
      if (!context.isCurrent() || typeof count !== 'number') return;
      nextOffset += SESSION_SELECTOR_PAGE_SIZE;
      hasMore.value = count >= SESSION_SELECTOR_PAGE_SIZE;
    } finally {
      loadingMore.value = false;
    }
  }

  function registerInitialPage(count: number) {
    nextOffset = SESSION_SELECTOR_PAGE_SIZE;
    hasMore.value = count >= SESSION_SELECTOR_PAGE_SIZE;
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
    hasMore,
    loadingMore,
    loadAnchors,
    registerInitialPage,
    buildQuery,
    updateAnchor,
    updateDateRange,
    search,
    loadMore,
    reset
  };
}
