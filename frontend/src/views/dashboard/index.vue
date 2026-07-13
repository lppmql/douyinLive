<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import CountTo from '@/components/custom/count-to.vue';
import { $t } from '@/locales';
import { fetchDashboardSummary } from '@/service/api/douyin';

defineOptions({
  name: 'Dashboard'
});

interface KpiItem {
  key: string;
  title: string;
  endValue: number;
  decimals?: number;
  suffix: string;
  icon: string;
  iconClass: string;
  description: string;
}

const message = useMessage();
const loading = ref(false);
const summary = ref<Api.Douyin.DashboardSummary | null>(null);

async function loadSummary() {
  loading.value = true;
  try {
    const response = await fetchDashboardSummary();
    if (response.data) summary.value = response.data;
  } catch {
    message.error('经营数据加载失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadSummary);

const kpiData = computed<KpiItem[]>(() => [
  {
    key: 'anchors',
    title: '已采集主播',
    endValue: summary.value?.anchor_count || 0,
    suffix: ' 位',
    icon: 'mdi:account-multiple-check-outline',
    iconClass: 'bg-primary-100 text-primary dark:bg-primary-900/30',
    description: `直播中 ${summary.value?.live_session_count || 0} 场`
  },
  {
    key: 'sessions',
    title: '直播场次',
    endValue: summary.value?.session_count || 0,
    suffix: ' 场',
    icon: 'mdi:video-check-outline',
    iconClass: 'bg-success-100 text-success dark:bg-success-900/30',
    description: `累计观看 ${(summary.value?.total_viewers || 0).toLocaleString()} 人`
  },
  {
    key: 'completeness',
    title: '场次详情完整率',
    endValue: summary.value?.detail_completion_rate || 0,
    decimals: 1,
    suffix: '%',
    icon: 'mdi:database-check-outline',
    iconClass: 'bg-warning-100 text-warning dark:bg-warning-900/30',
    description: `完整 ${summary.value?.detail_complete_count || 0} 场`
  },
  {
    key: 'leads',
    title: '累计线索',
    endValue: summary.value?.total_leads || 0,
    suffix: ' 条',
    icon: 'mdi:account-arrow-right-outline',
    iconClass: 'bg-error-100 text-error dark:bg-error-900/30',
    description: `平均成本 ¥${(summary.value?.average_lead_cost || 0).toFixed(2)}`
  }
]);

const dataeaseUrl = ref(import.meta.env.VITE_DATAEASE_URL || '');
</script>

<template>
  <NSpace vertical :size="16">
    <NSpin :show="loading">
      <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
        <NGi v-for="item in kpiData" :key="item.key">
          <NCard :bordered="false" class="card-wrapper h-full" size="small">
            <div class="flex items-start justify-between gap-12px">
              <div class="min-w-0">
                <div class="text-13px text-gray-500">{{ item.title }}</div>
                <div class="mt-8px flex items-baseline gap-4px">
                  <span class="text-28px font-700">
                    <CountTo :end-value="item.endValue" :decimals="item.decimals ?? 0" :duration="1200" />
                  </span>
                  <span class="text-13px text-gray-500">{{ item.suffix }}</span>
                </div>
                <div class="mt-8px text-12px text-gray-400">{{ item.description }}</div>
              </div>
              <div class="size-44px flex-center shrink-0 rounded-12px" :class="item.iconClass">
                <SvgIcon :icon="item.icon" class="text-24px" />
              </div>
            </div>
          </NCard>
        </NGi>
      </NGrid>
    </NSpin>

    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <div class="flex flex-wrap items-center justify-between gap-12px">
          <NSpace align="center">
            <SvgIcon icon="mdi:chart-donut" class="text-22px text-primary" />
            <span class="text-16px font-bold">经营数据概览</span>
          </NSpace>
          <NButton size="small" :loading="loading" @click="loadSummary">
            <template #icon><SvgIcon icon="mdi:refresh" /></template>
            刷新
          </NButton>
        </div>
      </template>
      <NDescriptions label-placement="top" :column="4" bordered size="small" responsive="screen">
        <NDescriptionsItem label="累计评论">{{ (summary?.total_comments || 0).toLocaleString() }}</NDescriptionsItem>
        <NDescriptionsItem label="累计投放">¥{{ (summary?.total_ad_cost || 0).toLocaleString() }}</NDescriptionsItem>
        <NDescriptionsItem label="平均线索成本">¥{{ (summary?.average_lead_cost || 0).toFixed(2) }}</NDescriptionsItem>
        <NDescriptionsItem label="监控中场次">{{ summary?.live_session_count || 0 }} 场</NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <!-- DataEase 大屏嵌入区域 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace>
          <SvgIcon icon="mdi:monitor-dashboard" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('route.dashboard') }}</span>
        </NSpace>
      </template>

      <div v-if="dataeaseUrl" class="dataease-iframe-wrapper">
        <iframe :src="dataeaseUrl" width="100%" height="800" frameborder="0" allowfullscreen class="rounded-8px" />
      </div>

      <NResult
        v-else
        status="info"
        :title="$t('page.dashboard.placeholder')"
        :description="$t('page.dashboard.placeholderDesc')"
      >
        <template #icon>
          <SvgIcon icon="mdi:chart-box-outline" class="text-64px text-primary" />
        </template>
        <template #footer>
          <NButton
            tag="a"
            href="http://localhost:8100"
            target="_blank"
            rel="noopener noreferrer"
            type="primary"
            secondary
          >
            <template #icon><SvgIcon icon="mdi:open-in-new" /></template>
            打开 DataEase
          </NButton>
        </template>
      </NResult>
    </NCard>
  </NSpace>
</template>

<style scoped>
.dataease-iframe-wrapper {
  width: 100%;
  overflow: hidden;
  border-radius: 8px;
}
</style>
