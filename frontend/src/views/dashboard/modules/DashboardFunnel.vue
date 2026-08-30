<script setup lang="ts">
import { computed } from 'vue';

defineOptions({ name: 'DashboardFunnel' });

const props = defineProps<{ data: Api.Douyin.DashboardFunnelStep[] }>();

const firstValue = computed(() => Number(props.data[0]?.value || 0));

function relativeRate(value: number) {
  return firstValue.value ? Math.min(100, Number(((value / firstValue.value) * 100).toFixed(2))) : 0;
}
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="私信留资转化漏斗">
    <template #header-extra>
      <NTag size="small" type="success" :bordered="false">业务目标：主动私信留资</NTag>
    </template>
    <NEmpty v-if="!data.length" description="当前筛选范围暂无漏斗数据" class="py-60px" />
    <NSpace v-else vertical :size="18">
      <div v-for="(step, index) in data" :key="step.label" class="funnel-step">
        <div class="mb-6px flex items-center justify-between gap-12px">
          <div class="flex items-center gap-8px">
            <NTag size="small" round :bordered="false" :type="index === data.length - 1 ? 'success' : 'info'">
              {{ index + 1 }}
            </NTag>
            <span class="font-500">{{ step.label }}</span>
          </div>
          <div class="text-right">
            <span class="text-16px font-700">{{ step.value.toLocaleString('zh-CN') }}</span>
            <span class="ml-8px text-11px text-gray-400">
              {{ index === 0 ? '起始规模' : `上步转化 ${step.step_rate}%` }}
            </span>
          </div>
        </div>
        <NProgress
          type="line"
          :percentage="relativeRate(step.value)"
          :height="10"
          :border-radius="5"
          :show-indicator="false"
          :status="index === data.length - 1 ? 'success' : 'default'"
        />
      </div>
    </NSpace>
  </NCard>
</template>

<style scoped>
.funnel-step {
  min-width: 0;
}
</style>
