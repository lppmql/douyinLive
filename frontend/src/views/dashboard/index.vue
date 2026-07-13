<script setup lang="ts">
import { ref, computed } from 'vue';
import { useThemeStore } from '@/store/modules/theme';
import CountTo from '@/components/custom/count-to.vue';
import { $t } from '@/locales';

defineOptions({
  name: 'Dashboard'
});

interface KpiItem {
  key: string;
  title: string;
  endValue: number;
  decimals?: number;
  suffix: string;
  color: { start: string; end: string };
  icon: string;
}

const themeStore = useThemeStore();

const kpiData = computed<KpiItem[]>(() => [
  {
    key: 'todayLeads',
    title: $t('page.dashboard.todayLeads'),
    endValue: 328,
    suffix: ' 人',
    color: { start: '#667eea', end: '#764ba2' },
    icon: 'mdi:account-plus'
  },
  {
    key: 'onlineUsers',
    title: $t('page.dashboard.onlineUsers'),
    endValue: 1256,
    suffix: ' 人',
    color: { start: '#f093fb', end: '#f5576c' },
    icon: 'mdi:account-group'
  },
  {
    key: 'validLeadRate',
    title: $t('page.dashboard.validLeadRate'),
    endValue: 68.5,
    decimals: 1,
    suffix: '%',
    color: { start: '#4facfe', end: '#00f2fe' },
    icon: 'mdi:percent'
  },
  {
    key: 'leadCost',
    title: $t('page.dashboard.leadCost'),
    endValue: 12.8,
    decimals: 1,
    suffix: ' 元',
    color: { start: '#43e97b', end: '#38f9d7' },
    icon: 'mdi:currency-cny'
  }
]);

// DataEase 大屏嵌入 URL（配置完成后填入）
const dataeaseUrl = ref('');

function getGradientColor(color: KpiItem['color']) {
  return `linear-gradient(135deg, ${color.start}, ${color.end})`;
}
</script>

<template>
  <NSpace vertical :size="16">
    <!-- Mock KPI 卡片 -->
    <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
      <NGi v-for="item in kpiData" :key="item.key">
        <div
          class="rounded-12px p-20px text-white flex flex-col gap-12px"
          :style="{ background: getGradientColor(item.color), borderRadius: themeStore.themeRadius + 'px' }"
        >
          <div class="flex items-center justify-between">
            <span class="text-14px opacity-85">{{ item.title }}</span>
            <SvgIcon :icon="item.icon" class="text-24px opacity-85" />
          </div>
          <div class="flex items-baseline gap-4px">
            <span class="text-32px font-bold">
              <CountTo :end-value="item.endValue" :decimals="item.decimals ?? 0" :duration="2500" />
            </span>
            <span class="text-13px opacity-75">{{ item.suffix }}</span>
          </div>
        </div>
      </NGi>
    </NGrid>

    <!-- DataEase 大屏嵌入区域 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace>
          <SvgIcon icon="mdi:monitor-dashboard" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('route.dashboard') }}</span>
        </NSpace>
      </template>

      <!-- 已配置嵌入 URL -->
      <div v-if="dataeaseUrl" class="dataease-iframe-wrapper">
        <iframe
          :src="dataeaseUrl"
          width="100%"
          height="800"
          frameborder="0"
          allowfullscreen
          class="rounded-8px"
        />
      </div>

      <!-- 未配置占位 -->
      <div v-else>
        <NResult
          status="info"
          :title="$t('page.dashboard.placeholder')"
          :description="$t('page.dashboard.placeholderDesc')"
        >
          <template #icon>
            <SvgIcon icon="mdi:chart-box-outline" class="text-64px text-primary" />
          </template>
          <template #footer>
            <NButton type="primary" secondary @click="dataeaseUrl = 'http://localhost:8100'">
              <template #icon>
                <SvgIcon icon="mdi:open-in-new" />
              </template>
              打开 DataEase 配置
            </NButton>
          </template>
        </NResult>
      </div>
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
