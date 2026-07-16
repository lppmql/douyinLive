<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { useEcharts } from '@/hooks/common/echarts';
import { fetchSessionComparison } from '@/service/api/douyin';

defineOptions({ name: 'SessionComparison' });
const props = defineProps<{ sessionId: number; sessions: Api.Douyin.LiveSessionListItem[] }>();
const message = useMessage();
const loading = ref(false);
const selectedId = ref<number | null>(null);
const comparison = ref<Api.Douyin.SessionComparison | null>(null);
const options = computed(() =>
  props.sessions
    .filter(item => item.id !== props.sessionId)
    .map(item => ({
      value: item.id,
      label: `${item.anchor_name || '未知主播'} · ${(item.live_start_time || '').slice(0, 16).replace('T', ' ')} · #${item.id}`
    }))
);

const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 4, data: ['当前场次在线', '对比场次在线'] },
  grid: { left: 20, right: 24, top: 46, bottom: 22, containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, name: '开播分钟', data: [] as number[] },
  yAxis: { type: 'value', minInterval: 1 },
  series: [] as any[]
}));

function refreshChart() {
  if (!comparison.value) return;
  const maxMinute = Math.max(
    ...comparison.value.current_series.map(item => item.minute),
    ...comparison.value.baseline_series.map(item => item.minute),
    0
  );
  const minutes = Array.from({ length: maxMinute + 1 }, (_, index) => index);
  const currentMap = new Map(comparison.value.current_series.map(item => [item.minute, item.online_count]));
  const baselineMap = new Map(comparison.value.baseline_series.map(item => [item.minute, item.online_count]));
  updateOptions(optionsValue => {
    optionsValue.xAxis.data = minutes;
    optionsValue.series = [
      {
        name: '当前场次在线',
        type: 'line',
        smooth: true,
        symbol: 'none',
        color: '#2080f0',
        data: minutes.map(minute => currentMap.get(minute) ?? null)
      },
      {
        name: '对比场次在线',
        type: 'line',
        smooth: true,
        symbol: 'none',
        color: '#f0a020',
        data: minutes.map(minute => baselineMap.get(minute) ?? null)
      }
    ];
    return optionsValue;
  });
}

async function loadComparison() {
  loading.value = true;
  try {
    comparison.value = (await fetchSessionComparison(props.sessionId, selectedId.value || undefined)).data || null;
    if (comparison.value && !selectedId.value) selectedId.value = comparison.value.baseline.id;
    refreshChart();
  } catch (error) {
    comparison.value = null;
    message.warning((error as { message?: string }).message || '暂无可对比的历史场次');
  } finally {
    loading.value = false;
  }
}

function formatValue(item: Api.Douyin.ComparisonDimension) {
  return item.key.includes('rate') ? `${(item.current * 100).toFixed(2)}%` : item.current.toLocaleString();
}
function formatDelta(item: Api.Douyin.ComparisonDimension) {
  if (item.delta_rate === null) return item.delta > 0 ? '对比场为0' : '持平';
  const value = item.delta_rate * 100;
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

onMounted(loadComparison);
watch(selectedId, (value, oldValue) => {
  if (value && oldValue && value !== oldValue) loadComparison();
});
</script>

<template>
  <NSpin :show="loading">
    <div class="mb-14px flex flex-wrap items-center justify-between gap-12px">
      <div>
        <div class="text-15px font-700">跨场复盘验证</div>
        <div class="mt-3px text-12px text-gray-400">默认与同主播上一场对比，也可选择其他真实场次</div>
      </div>
      <NSelect v-model:value="selectedId" filterable :options="options" class="w-460px max-w-full" />
    </div>

    <NEmpty v-if="!comparison" description="当前没有可比较的历史场次" class="py-50px" />
    <template v-else>
      <NAlert type="info" :bordered="false" class="mb-14px">{{ comparison.comparison_note }}</NAlert>
      <div class="mb-14px grid grid-cols-2 gap-10px text-12px lt-sm:grid-cols-1">
        <div class="rounded-9px bg-primary-50 p-10px dark:bg-primary-900/20">
          <div class="font-700">当前：#{{ comparison.current.id }} {{ comparison.current.anchor_name }}</div>
          <div class="mt-4px text-gray-500">完整度 {{ comparison.current.completeness }}%</div>
        </div>
        <div class="rounded-9px bg-warning-50 p-10px dark:bg-warning-900/20">
          <div class="font-700">对比：#{{ comparison.baseline.id }} {{ comparison.baseline.anchor_name }}</div>
          <div class="mt-4px text-gray-500">完整度 {{ comparison.baseline.completeness }}%</div>
        </div>
      </div>
      <NGrid :x-gap="10" :y-gap="10" cols="2 s:4 l:8" responsive="screen">
        <NGi v-for="item in comparison.dimensions" :key="item.key">
          <div class="h-full rounded-9px border border-gray-200/70 p-10px dark:border-gray-700">
            <div class="text-11px text-gray-400">{{ item.label }}</div>
            <div class="mt-5px text-17px font-700">{{ formatValue(item) }}</div>
            <div class="mt-3px text-11px" :class="item.delta >= 0 ? 'text-success' : 'text-error'">
              {{ formatDelta(item) }}
            </div>
          </div>
        </NGi>
      </NGrid>
      <div ref="domRef" class="mt-16px h-340px w-full"></div>
    </template>
  </NSpin>
</template>
