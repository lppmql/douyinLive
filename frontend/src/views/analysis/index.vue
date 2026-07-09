<script setup lang="ts">
import { ref } from 'vue';
import { $t } from '@/locales';
import { useEcharts } from '@/hooks/common/echarts';
import type { ECOption } from '@/hooks/common/echarts';

defineOptions({
  name: 'Analysis'
});

/* ---------- Mock 数据 ---------- */
interface ScoreItem {
  key: string;
  label: string;
  value: number;
  color: string;
}

const scores = ref<ScoreItem[]>([
  { key: 'completeness', label: $t('page.analysis.completeness'), value: 82, color: '#667eea' },
  { key: 'interactivity', label: $t('page.analysis.interactivity'), value: 68, color: '#f093fb' },
  { key: 'leadGuidance', label: $t('page.analysis.leadGuidance'), value: 75, color: '#4facfe' },
  { key: 'overall', label: $t('page.analysis.overall'), value: 78, color: '#43e97b' }
]);

/* ---------- ECharts 趋势图 ---------- */
const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: {
    trigger: 'axis'
  },
  legend: {
    data: [
      $t('page.analysis.completeness'),
      $t('page.analysis.interactivity'),
      $t('page.analysis.leadGuidance'),
      $t('page.analysis.overall')
    ],
    top: '0'
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: ['07/03', '07/04', '07/05', '07/06', '07/07', '07/08', '07/09']
  },
  yAxis: {
    type: 'value',
    min: 0,
    max: 100
  },
  series: [
    {
      name: $t('page.analysis.completeness'),
      type: 'line',
      smooth: true,
      data: [75, 78, 80, 82, 79, 85, 82],
      itemStyle: { color: '#667eea' }
    },
    {
      name: $t('page.analysis.interactivity'),
      type: 'line',
      smooth: true,
      data: [60, 65, 62, 68, 70, 66, 68],
      itemStyle: { color: '#f093fb' }
    },
    {
      name: $t('page.analysis.leadGuidance'),
      type: 'line',
      smooth: true,
      data: [70, 72, 68, 75, 73, 78, 75],
      itemStyle: { color: '#4facfe' }
    },
    {
      name: $t('page.analysis.overall'),
      type: 'line',
      smooth: true,
      data: [72, 74, 73, 78, 76, 80, 78],
      itemStyle: { color: '#43e97b' }
    }
  ]
}));

/* ---------- 告警 ---------- */
interface AlertItem {
  key: string;
  title: string;
  desc: string;
  type: 'warning' | 'error' | 'info';
}

const alerts = ref<AlertItem[]>([
  { key: 'drop', title: $t('page.analysis.alertDrop'), desc: $t('page.analysis.alertDropDesc'), type: 'error' },
  { key: 'interact', title: $t('page.analysis.alertInteract'), desc: $t('page.analysis.alertInteractDesc'), type: 'warning' },
  { key: 'lead', title: $t('page.analysis.alertLead'), desc: $t('page.analysis.alertLeadDesc'), type: 'warning' }
]);

/* ---------- 优化建议 ---------- */
const suggestions = ref([
  $t('page.analysis.suggestion1'),
  $t('page.analysis.suggestion2'),
  $t('page.analysis.suggestion3')
]);
</script>

<template>
  <NSpace vertical :size="16">
    <!-- 评分卡片 -->
    <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
      <NGi v-for="item in scores" :key="item.key">
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="flex items-center justify-between mb-12px">
            <span class="text-13px text-gray-500">{{ item.label }}</span>
          </div>
          <div class="flex items-baseline gap-4px mb-8px">
            <span class="text-32px font-bold" :style="{ color: item.color }">{{ item.value }}</span>
            <span class="text-13px text-gray-400">{{ $t('page.analysis.score') }}</span>
          </div>
          <NProgress
            type="line"
            :percentage="item.value"
            :height="6"
            :border-radius="3"
            indicator-placement="inside"
            :color="item.color"
          />
        </NCard>
      </NGi>
    </NGrid>

    <!-- 趋势图 + 告警 -->
    <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
      <NGi span="2">
        <NCard :bordered="false" class="card-wrapper">
          <template #header>
            <span class="text-15px font-bold">{{ $t('page.analysis.trendTitle') }}</span>
          </template>
          <div ref="domRef" class="h-300px"></div>
        </NCard>
      </NGi>
      <NGi span="1">
        <NCard :bordered="false" class="card-wrapper">
          <template #header>
            <span class="text-15px font-bold">{{ $t('page.analysis.alertTitle') }}</span>
          </template>
          <NSpace vertical :size="12">
            <NAlert
              v-for="item in alerts"
              :key="item.key"
              :title="item.title"
              :type="item.type"
              closable
            >
              {{ item.desc }}
            </NAlert>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>

    <!-- 优化建议 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <span class="text-15px font-bold">{{ $t('page.analysis.suggestionTitle') }}</span>
      </template>
      <NSpace vertical :size="12">
        <div
          v-for="(item, index) in suggestions"
          :key="index"
          class="flex items-start gap-12px rounded-8px bg-gray-50 dark:bg-dark-300 p-12px"
        >
          <NBadge :value="index + 1" />
          <span class="text-14px leading-22px">{{ item }}</span>
        </div>
      </NSpace>
    </NCard>
  </NSpace>
</template>

<style scoped></style>
