<script setup lang="ts">
/**
 * 转写任务状态卡片
 *
 * 4 张可点击卡片：等待转写 / 正在转写 / 转写完成 / 需要处理。
 * 点击卡片会打开任务抽屉并按对应状态预筛选。
 */
import type { TaskStatusCard } from '@/adapters/transcript-adapter';

defineOptions({ name: 'TranscriptTaskCards' });

defineProps<{
  /** 4 张卡片的数据配置 */
  taskStatusCards: TaskStatusCard[];
  /** 失败和已暂停任务总数。 */
  attentionCount: number;
  /** ASR 模型与 Worker 的真实运行状态。 */
  asrRuntime: Api.Douyin.AsrControlStatus | null;
  runtimeActionLoading: boolean;
}>();

defineEmits<{
  /** 点击卡片 → 打开任务抽屉，传状态值用于预筛选 */
  openDrawer: [status: string];
  restoreRuntime: [];
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" size="small" title="全部转写任务">
    <template #header-extra>
      <div class="flex items-center gap-10px">
        <NTag
          v-if="asrRuntime"
          size="small"
          :type="asrRuntime.worker_healthy ? 'success' : 'error'"
          :bordered="false"
          round
        >
          {{ asrRuntime.worker_healthy ? '转写服务正常' : '转写服务异常' }}
        </NTag>
        <NButton text type="primary" @click="$emit('openDrawer', 'all')">查看任务明细</NButton>
      </div>
    </template>
    <div class="grid grid-cols-2 gap-8px lg:grid-cols-4">
      <button
        v-for="card in taskStatusCards"
        :key="card.status"
        type="button"
        class="business-focus-ring queue-item flex items-center gap-10px rounded-10px px-12px py-10px text-left"
        :class="`queue-item--${card.tone}`"
        @click="$emit('openDrawer', card.status)"
      >
        <div class="status-icon flex-center shrink-0 rounded-8px p-7px">
          <SvgIcon :icon="card.icon" class="text-20px" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-8px">
            <span class="truncate text-12px text-gray-500">{{ card.label }}</span>
            <strong class="text-20px">{{ card.value }}</strong>
          </div>
          <div class="mt-2px truncate text-11px text-gray-400">
            {{ card.status === 'processing' && card.maxProgress != null ? `最高进度 ${card.maxProgress}%` : '点击筛选查看' }}
          </div>
        </div>
      </button>
    </div>
    <NAlert v-if="asrRuntime && !asrRuntime.worker_healthy" class="mt-10px" type="error" :bordered="false" show-icon>
      <template #header>转写 Worker 没有有效心跳</template>
      {{ asrRuntime.message || '排队任务暂时不会推进，系统正在自动恢复。' }}
      <NButton
        text
        type="error"
        class="ml-8px"
        :loading="runtimeActionLoading"
        @click="$emit('restoreRuntime')"
      >
        立即恢复
      </NButton>
    </NAlert>
    <NAlert v-if="attentionCount" class="mt-10px" type="warning" :bordered="false" show-icon>
      {{ attentionCount }} 场已暂停或失败；已完成话术和分片均已保留。
      <NButton text type="warning" class="ml-8px" @click="$emit('openDrawer', 'attention')">立即处理</NButton>
    </NAlert>
  </NCard>
</template>

<style scoped>
.queue-item {
  border: 1px solid rgba(128, 128, 128, 0.14);
  background: rgba(128, 128, 128, 0.035);
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.queue-item:hover,
.queue-item:focus-visible {
  border-color: rgba(32, 128, 240, 0.45);
  background: rgba(32, 128, 240, 0.05);
  outline: none;
}

.status-icon {
  background: rgba(var(--primary-color), 0.1);
  color: rgb(var(--primary-color));
}

.queue-item--warning .status-icon {
  background: rgba(var(--warning-color), 0.12);
  color: rgb(var(--warning-color));
}

.queue-item--success .status-icon {
  background: rgba(var(--success-color), 0.12);
  color: rgb(var(--success-color));
}

.queue-item--error .status-icon {
  background: rgba(var(--error-color), 0.12);
  color: rgb(var(--error-color));
}
</style>
