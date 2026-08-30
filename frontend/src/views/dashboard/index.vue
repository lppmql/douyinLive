<script setup lang="ts">
import { watch } from 'vue';
import DashboardAnchorTable from './modules/DashboardAnchorTable.vue';
import DashboardFilter from './modules/DashboardFilter.vue';
import DashboardFunnel from './modules/DashboardFunnel.vue';
import DashboardMetricGrid from './modules/DashboardMetricGrid.vue';
import DashboardSessionTable from './modules/DashboardSessionTable.vue';
import DashboardTrendChart from './modules/DashboardTrendChart.vue';
import { useDashboardData } from './composables/useDashboardData';

defineOptions({ name: 'Dashboard' });

const {
  loading,
  loadError,
  anchorKey,
  dateRange,
  anchorOptions,
  dashboard,
  loadDashboard,
  refresh,
  resetFilters
} = useDashboardData();

watch([anchorKey, dateRange], loadDashboard, { deep: true });
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <DashboardFilter
      v-model:anchor-key="anchorKey"
      v-model:date-range="dateRange"
      :anchor-options="anchorOptions"
      :loading="loading"
      @refresh="loadDashboard"
      @reset="resetFilters"
    />

    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      <NFlex justify="space-between" align="center">
        <span>{{ loadError }}</span>
        <NButton size="small" secondary :loading="loading" @click="refresh">重新加载</NButton>
      </NFlex>
    </NAlert>

    <NSpin :show="loading && !dashboard">
      <NSpace v-if="dashboard" vertical :size="16">
        <DashboardMetricGrid :summary="dashboard.summary" />

        <NGrid cols="1 l:5" responsive="screen" :x-gap="16" :y-gap="16">
          <NGi span="1 l:3">
            <DashboardTrendChart :data="dashboard.trend" />
          </NGi>
          <NGi span="1 l:2">
            <DashboardFunnel :data="dashboard.funnel" />
          </NGi>
        </NGrid>

        <DashboardAnchorTable :data="dashboard.anchors" />
        <DashboardSessionTable :data="dashboard.recent_sessions" />
      </NSpace>

      <NCard v-else-if="!loading" :bordered="false" class="card-wrapper">
        <NEmpty description="当前筛选范围暂无真实直播数据" class="py-70px">
          <template #extra>
            <NButton type="primary" secondary @click="refresh">重新加载</NButton>
          </template>
        </NEmpty>
      </NCard>
    </NSpin>
  </NSpace>
</template>
