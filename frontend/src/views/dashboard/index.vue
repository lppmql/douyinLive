<script setup lang="ts">
import { computed } from 'vue';
import { useThemeStore } from '@/store/modules/theme';
import { $t } from '@/locales';

defineOptions({
  name: 'Dashboard'
});

interface KpiItem {
  key: string;
  title: string;
  value: string;
  unit: string;
  color: { start: string; end: string };
  icon: string;
}

const themeStore = useThemeStore();

const kpiData = computed<KpiItem[]>(() => [
  {
    key: 'todayLeads',
    title: $t('page.dashboard.todayLeads'),
    value: '328',
    unit: $t('page.dashboard.unitPeople'),
    color: { start: '#667eea', end: '#764ba2' },
    icon: 'mdi:account-plus'
  },
  {
    key: 'onlineUsers',
    title: $t('page.dashboard.onlineUsers'),
    value: '1,256',
    unit: $t('page.dashboard.unitPeople'),
    color: { start: '#f093fb', end: '#f5576c' },
    icon: 'mdi:account-group'
  },
  {
    key: 'validLeadRate',
    title: $t('page.dashboard.validLeadRate'),
    value: '68.5',
    unit: '%',
    color: { start: '#4facfe', end: '#00f2fe' },
    icon: 'mdi:percent'
  },
  {
    key: 'leadCost',
    title: $t('page.dashboard.leadCost'),
    value: '12.8',
    unit: $t('page.dashboard.unitYuan'),
    color: { start: '#43e97b', end: '#38f9d7' },
    icon: 'mdi:currency-cny'
  }
]);

function getGradientColor(color: KpiItem['color']) {
  return `linear-gradient(135deg, ${color.start}, ${color.end})`;
}
</script>

<template>
  <NSpace vertical :size="16">
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace>
          <SvgIcon icon="mdi:monitor-dashboard" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('route.dashboard') }}</span>
        </NSpace>
      </template>
      <NResult
        status="info"
        :title="$t('page.dashboard.placeholder')"
        :description="$t('page.dashboard.placeholderDesc')"
      >
        <template #icon>
          <SvgIcon icon="mdi:chart-box-outline" class="text-64px text-primary" />
        </template>
      </NResult>
    </NCard>

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
            <span class="text-32px font-bold">{{ item.value }}</span>
            <span class="text-13px opacity-75">{{ item.unit }}</span>
          </div>
        </div>
      </NGi>
    </NGrid>
  </NSpace>
</template>

<style scoped></style>
