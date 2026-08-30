<script setup lang="ts">
import { h } from 'vue';
import type { SelectOption } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import type { AnchorSelectorOption, SessionDateRange } from '@/adapters/session-selector-adapter';
import {
  getShanghaiTodayCalendarTimestamp,
  shiftSelectorCalendarDate
} from '@/adapters/session-selector-adapter';

defineOptions({ name: 'DashboardFilter' });

defineProps<{
  anchorKey: string | null;
  dateRange: SessionDateRange;
  anchorOptions: AnchorSelectorOption[];
  loading: boolean;
}>();

const emit = defineEmits<{
  'update:anchorKey': [value: string | null];
  'update:dateRange': [value: SessionDateRange];
  refresh: [];
  reset: [];
}>();

const todayStart = () => getShanghaiTodayCalendarTimestamp();
const shortcuts = {
  今天: () => [todayStart(), todayStart()] as [number, number],
  昨天: () => {
    const yesterday = shiftSelectorCalendarDate(todayStart(), -1);
    return [yesterday, yesterday] as [number, number];
  },
  '近 7 天': () => [shiftSelectorCalendarDate(todayStart(), -6), todayStart()] as [number, number],
  '近 30 天': () => [shiftSelectorCalendarDate(todayStart(), -29), todayStart()] as [number, number]
};

function renderAnchorLabel(option: SelectOption) {
  const item = option as AnchorSelectorOption;
  return h(AnchorIdentity, {
    sessionId: item.sessionId,
    avatarUrl: item.avatarUrl,
    name: item.anchorName,
    nickname: item.anchorNickname,
    douyinId: item.douyinId,
    size: 28,
    dense: true
  });
}
</script>

<template>
  <NCard :bordered="false" size="small" class="card-wrapper">
    <div class="dashboard-filter">
      <div>
        <div class="text-18px font-600">零食店直播经营大屏</div>
        <div class="mt-4px text-12px text-gray-400">真实场次 · 站内私信 · 确认留资</div>
      </div>
      <NSelect
        class="min-w-180px"
        :value="anchorKey"
        :options="anchorOptions"
        :render-label="renderAnchorLabel"
        clearable
        filterable
        placeholder="全部主播"
        @update:value="value => emit('update:anchorKey', value as string | null)"
      />
      <NDatePicker
        class="min-w-260px"
        :value="dateRange"
        type="daterange"
        clearable
        :shortcuts="shortcuts"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        @update:value="value => emit('update:dateRange', value as SessionDateRange)"
      />
      <NSpace :wrap="false">
        <NButton quaternary @click="emit('reset')">
          <template #icon><SvgIcon icon="mdi:filter-remove-outline" /></template>
          重置
        </NButton>
        <NButton type="primary" :loading="loading" @click="emit('refresh')">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新
        </NButton>
      </NSpace>
    </div>
  </NCard>
</template>

<style scoped>
.dashboard-filter {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 0.7fr) minmax(260px, 0.9fr) auto;
  align-items: center;
  gap: 12px;
}

@media (max-width: 900px) {
  .dashboard-filter {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 600px) {
  .dashboard-filter {
    grid-template-columns: 1fr;
  }
}
</style>
