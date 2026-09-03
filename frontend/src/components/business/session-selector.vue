<script setup lang="ts">
/**
 * 公共直播场次筛选器。
 *
 * 只负责统一交互和展示，不决定“哪些场次可用于转写/复盘/剪辑”；候选范围仍由
 * 各业务接口给出，避免公共组件吞掉页面原有规则。
 */
import { computed, h } from 'vue';
import type { SelectOption } from 'naive-ui';
import AnchorIdentity from './anchor-identity.vue';
import type {
  AnchorSelectorOption,
  SessionDateRange,
  SessionSelectorOption
} from '@/adapters/session-selector-adapter';
import {
  getShanghaiTodayCalendarTimestamp,
  shiftSelectorCalendarDate
} from '@/adapters/session-selector-adapter';

defineOptions({ name: 'SessionSelector' });

withDefaults(defineProps<{
  modelValue: number | null;
  options: SessionSelectorOption[];
  anchorOptions: AnchorSelectorOption[];
  anchorKey: string | null;
  dateRange: SessionDateRange;
  loading?: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  allowGlobal?: boolean;
  clearable?: boolean;
  sessionPlaceholder?: string;
}>(), {
  loading: false,
  loadingMore: false,
  hasMore: true,
  allowGlobal: false,
  clearable: true,
  sessionPlaceholder: '搜索主播、日期、场次编号或标题'
});

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
  'update:anchorKey': [value: string | null];
  'update:dateRange': [value: SessionDateRange];
  search: [keyword: string];
  loadMore: [];
  reset: [];
}>();

const todayStart = () => getShanghaiTodayCalendarTimestamp();

const dateShortcuts = computed(() => ({
  今天: () => [todayStart(), todayStart()] as [number, number],
  昨天: () => {
    const yesterday = shiftSelectorCalendarDate(todayStart(), -1);
    return [yesterday, yesterday] as [number, number];
  },
  '近 7 天': () => [shiftSelectorCalendarDate(todayStart(), -6), todayStart()] as [number, number],
  '近 30 天': () => [shiftSelectorCalendarDate(todayStart(), -29), todayStart()] as [number, number]
}));

function renderSessionLabel(option: SelectOption) {
  const item = option as SessionSelectorOption;
  return h('div', { class: 'flex min-w-0 items-center justify-between gap-12px py-2px' }, [
    h(AnchorIdentity, {
      class: 'min-w-0 max-w-220px flex-1',
      sessionId: item.sessionId,
      avatarUrl: item.avatarUrl,
      name: item.anchorName,
      nickname: item.anchorNickname,
      douyinId: item.douyinId,
      size: 28,
      dense: true
    }),
    h('span', { class: 'shrink-0 text-11px text-gray-400' }, item.metaLabel)
  ]);
}

function renderAnchorLabel(option: SelectOption) {
  const item = option as AnchorSelectorOption;
  return h(AnchorIdentity, {
    sessionId: item.sessionId,
    avatarUrl: item.avatarUrl,
    name: item.anchorName,
    nickname: item.anchorNickname,
    douyinId: item.douyinId,
    size: 26,
    dense: true
  });
}

function handleSessionScroll(event: Event) {
  const target = event.currentTarget as HTMLElement | null;
  if (!target) return;
  const distanceToBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  if (distanceToBottom <= 48) emit('loadMore');
}
</script>

<template>
  <div class="session-selector">
    <div class="session-selector__filters">
      <NSelect
        :value="anchorKey"
        clearable
        filterable
        :options="anchorOptions"
        :render-label="renderAnchorLabel"
        placeholder="全部主播"
        @update:value="value => emit('update:anchorKey', value as string | null)"
      />
      <NDatePicker
        :value="dateRange"
        type="daterange"
        clearable
        :shortcuts="dateShortcuts"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        @update:value="value => emit('update:dateRange', value as SessionDateRange)"
      />
      <NButton quaternary @click="emit('reset')">
        <template #icon><SvgIcon icon="mdi:filter-remove-outline" /></template>
        重置
      </NButton>
    </div>

    <div class="session-selector__main">
      <NButton
        v-if="allowGlobal"
        :type="modelValue === null ? 'primary' : 'default'"
        secondary
        @click="emit('update:modelValue', null)"
      >
        全部场次
      </NButton>
      <NSelect
        class="min-w-0 flex-1"
        :value="modelValue"
        :options="options"
        :render-label="renderSessionLabel"
        :loading="loading"
        filterable
        remote
        :reset-menu-on-options-change="false"
        :clearable="clearable"
        :placeholder="allowGlobal && modelValue === null ? '当前问答范围：全部知识库' : sessionPlaceholder"
        @scroll="handleSessionScroll"
        @search="keyword => emit('search', keyword)"
        @update:value="value => emit('update:modelValue', value as number | null)"
      >
        <template #action>
          <div class="w-full text-center text-12px text-gray-400">
            {{ loadingMore ? '正在加载更多场次…' : hasMore ? '向下滚动加载更多场次' : '已加载全部场次' }}
          </div>
        </template>
      </NSelect>
    </div>
  </div>
</template>

<style scoped>
.session-selector {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
}

.session-selector__filters {
  display: grid;
  grid-template-columns: minmax(160px, 0.65fr) minmax(250px, 1fr) auto;
  gap: 10px;
}

.session-selector__main {
  display: flex;
  min-width: 0;
  gap: 10px;
}

@media (max-width: 700px) {
  .session-selector__filters {
    grid-template-columns: 1fr;
  }

  .session-selector__main {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
