<script setup lang="ts">
import { computed } from 'vue';
import { NGi, NGrid, NStatistic, NTag } from 'naive-ui';

defineOptions({ name: 'CollectorResourceOverview' });

const props = defineProps<{
  usage: Api.Douyin.ComputerResourceUsage | null;
}>();

const pressureMeta = computed(() => {
  const level = props.usage?.pressure_level || 'normal';
  if (level === 'critical') return { label: '资源紧张', type: 'error' as const };
  if (level === 'high') return { label: '资源偏高', type: 'warning' as const };
  return { label: '资源正常', type: 'success' as const };
});

const visibleComponents = computed(() =>
  (props.usage?.components || []).filter(item => item.running || item.memory_bytes > 0)
);

function formatBytes(value: number | null | undefined): string {
  const bytes = Math.max(0, Number(value || 0));
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}
</script>

<template>
  <div class="resource-overview">
    <div class="mb-10px flex flex-wrap items-start justify-between gap-8px">
      <div>
        <div class="flex items-center gap-7px text-13px font-600">
          <SvgIcon icon="mdi:memory" class="text-18px text-primary" />
          电脑资源占用
          <NTag size="tiny" round :bordered="false" :type="pressureMeta.type">{{ pressureMeta.label }}</NTag>
        </div>
        <div class="mt-3px text-11px text-gray-400">
          {{ usage?.pressure_message || '正在读取操作系统真实资源数据' }}
        </div>
      </div>
      <div class="text-11px text-gray-400">关闭不用的开关会释放对应进程和模型内存</div>
    </div>

    <NGrid cols="2 s:4" responsive="screen" :x-gap="10" :y-gap="10">
      <NGi>
        <div class="resource-stat">
          <NStatistic label="整机 CPU" :value="usage?.cpu_percent || 0" :precision="1">
            <template #suffix>%</template>
          </NStatistic>
        </div>
      </NGi>
      <NGi>
        <div class="resource-stat">
          <NStatistic label="整机内存" :value="usage?.memory_percent || 0" :precision="1">
            <template #suffix>%</template>
          </NStatistic>
          <div class="mt-2px text-10px text-gray-400">
            {{ formatBytes(usage?.memory_used_bytes) }} / {{ formatBytes(usage?.memory_total_bytes) }}
          </div>
        </div>
      </NGi>
      <NGi>
        <div class="resource-stat">
          <NStatistic label="本项目内存" :value="formatBytes(usage?.app_memory_bytes)" />
        </div>
      </NGi>
      <NGi>
        <div class="resource-stat">
          <NStatistic label="磁盘可用" :value="formatBytes(usage?.disk_free_bytes)" />
          <div class="mt-2px text-10px text-gray-400">已使用 {{ usage?.disk_used_percent || 0 }}%</div>
        </div>
      </NGi>
    </NGrid>

    <div class="mt-9px flex flex-wrap gap-6px">
      <NTag
        v-for="component in visibleComponents"
        :key="component.key"
        size="small"
        :bordered="false"
        :type="component.running ? 'info' : 'default'"
      >
        {{ component.label }} · {{ formatBytes(component.memory_bytes) }} · CPU {{ component.cpu_percent.toFixed(1) }}%
      </NTag>
      <span v-if="!visibleComponents.length" class="text-11px text-gray-400">暂无采集子进程运行</span>
    </div>
  </div>
</template>

<style scoped>
.resource-overview {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  background: linear-gradient(120deg, rgb(14 116 144 / 5%), transparent 58%), var(--n-color);
}

.resource-stat {
  min-height: 70px;
  padding: 9px 11px;
  border: 1px solid color-mix(in srgb, var(--n-border-color) 72%, transparent);
  border-radius: 8px;
  background: rgb(255 255 255 / 48%);
}

:global(.dark) .resource-stat {
  background: rgb(255 255 255 / 3%);
}
</style>
