<script setup lang="ts">
import { computed, watch } from 'vue';
import { useEcharts } from '@/hooks/common/echarts';

defineOptions({ name: 'LiveMetricsChart' });
const props = defineProps<{ metrics: Api.Douyin.LiveMetric[] }>();
const selected = defineModel<string[]>('selected', { default: ['online_count', 'enter_count', 'comment_count', 'clue_count'] });

const indicators = [
  { label: '在线人数', value: 'online_count', color: '#2080f0' },
  { label: '进入人数', value: 'enter_count', color: '#18a058' },
  { label: '曝光人数', value: 'exposure_count', color: '#f0a020' },
  { label: '点赞数', value: 'like_count', color: '#d0308a' },
  { label: '评论数', value: 'comment_count', color: '#8a2be2' },
  { label: '关注数', value: 'follow_count', color: '#08979c' },
  { label: '线索数', value: 'clue_count', color: '#d03050' }
] as const;

const activeIndicators = computed(() => indicators.filter(item => selected.value.includes(item.value)));
const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  legend: { top: 4, data: [] as string[] },
  grid: { left: 16, right: 24, top: 48, bottom: 20, containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, data: [] as string[] },
  yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { type: 'dashed', opacity: 0.45 } } },
  series: [] as any[]
}));

function refreshChart() {
  updateOptions(options => {
    options.xAxis.data = props.metrics.map(item => new Date(item.metric_time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
    options.legend = { top: 4, data: activeIndicators.value.map(item => item.label) };
    options.series = activeIndicators.value.map(item => ({
      name: item.label,
      type: 'line',
      smooth: true,
      symbol: 'none',
      sampling: 'lttb',
      color: item.color,
      lineStyle: { width: 2 },
      areaStyle: item.value === 'online_count' ? { opacity: 0.08 } : undefined,
      data: props.metrics.map(metric => Number(metric[item.value] || 0))
    }));
    return options;
  });
}

watch([() => props.metrics, selected], refreshChart, { deep: true, immediate: true });
</script>

<template>
  <div>
    <div class="mb-12px flex flex-wrap items-center justify-between gap-12px">
      <NCheckboxGroup v-model:value="selected">
        <NSpace wrap :size="12">
          <NCheckbox v-for="item in indicators" :key="item.value" :value="item.value" :label="item.label" />
        </NSpace>
      </NCheckboxGroup>
      <NTag type="info" :bordered="false" round>{{ metrics.length }} 个采样点</NTag>
    </div>
    <NEmpty v-if="!metrics.length" description="暂无分钟趋势数据" class="py-60px" />
    <div v-else ref="domRef" class="h-380px w-full overflow-hidden lt-sm:h-300px"></div>
  </div>
</template>
