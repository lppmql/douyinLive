<script setup lang="ts">
import { watch } from 'vue';
import { useEcharts } from '@/hooks/common/echarts';

defineOptions({ name: 'DashboardTrendChart' });

const props = defineProps<{ data: Api.Douyin.DashboardTrendPoint[] }>();

const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  legend: { top: 4, data: ['观看人数', '站内私信', '确认留资'] },
  grid: { left: 16, right: 20, top: 48, bottom: 18, containLabel: true },
  xAxis: { type: 'category', boundaryGap: false, data: [] as string[] },
  yAxis: [
    { type: 'value', minInterval: 1, splitLine: { lineStyle: { type: 'dashed', opacity: 0.4 } } },
    { type: 'value', minInterval: 1, splitLine: { show: false } }
  ],
  series: [] as any[]
}));

function refreshChart() {
  updateOptions(options => {
    options.xAxis.data = props.data.map(item => item.date_key.slice(5));
    options.series = [
      {
        name: '观看人数',
        type: 'line',
        smooth: true,
        symbol: 'none',
        color: '#2080f0',
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.08 },
        data: props.data.map(item => item.total_viewers)
      },
      {
        name: '站内私信',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        color: '#722ed1',
        data: props.data.map(item => item.total_private_messages)
      },
      {
        name: '确认留资',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        color: '#18a058',
        data: props.data.map(item => item.total_leads)
      }
    ];
    return options;
  });
}

watch(() => props.data, refreshChart, { deep: true, immediate: true });
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="经营趋势">
    <template #header-extra>
      <NTag size="small" type="info" :bordered="false">按开播日期汇总</NTag>
    </template>
    <NEmpty v-if="!data.length" description="当前筛选范围暂无趋势数据" class="py-60px" />
    <div v-else ref="domRef" class="h-340px w-full overflow-hidden lt-sm:h-280px"></div>
  </NCard>
</template>
