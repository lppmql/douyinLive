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
  /** 失败任务数（用于显示警告条） */
  failedCount: number;
}>();

defineEmits<{
  /** 点击卡片 → 打开任务抽屉，传状态值用于预筛选 */
  openDrawer: [status: string];
}>();
</script>

<template>
  <!-- 4 张状态卡片 -->
  <div class="grid grid-cols-2 gap-12px lg:grid-cols-4">
    <button
      v-for="card in taskStatusCards"
      :key="card.status"
      type="button"
      class="business-clickable-card business-focus-ring status-card rounded-12px bg-white p-14px text-left dark:bg-dark sm:p-16px"
      :class="`status-card--${card.tone}`"
      @click="$emit('openDrawer', card.status)"
    >
      <div class="flex items-center justify-between gap-8px">
        <div>
          <div class="text-12px text-gray-500">{{ card.label }}</div>
          <div class="mt-5px text-26px font-800">{{ card.value }}</div>
        </div>
        <div class="status-icon flex-center rounded-10px p-8px">
          <SvgIcon :icon="card.icon" class="text-24px" />
        </div>
      </div>
      <div class="mt-8px text-11px text-gray-400">点击查看真实任务明细</div>
    </button>
  </div>

  <!-- 失败任务提醒 -->
  <NAlert v-if="failedCount" type="warning" :bordered="false" show-icon>
    有 {{ failedCount }} 场转写需要处理，不一定都是缺少 m3u8，也可能是回放过期或无有效语音。
    <NButton text type="warning" class="ml-8px" @click="$emit('openDrawer', 'failed')">
      查看具体场次和错误
    </NButton>
  </NAlert>
</template>

<style scoped>
.status-card {
  border: 1px solid rgba(128, 128, 128, 0.14);
  box-shadow: 0 8px 24px rgba(20, 35, 50, 0.05);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.status-card:hover,
.status-card:focus-visible {
  border-color: rgba(32, 128, 240, 0.45);
  box-shadow: 0 12px 30px rgba(20, 35, 50, 0.1);
  transform: translateY(-2px);
  outline: none;
}

.status-icon {
  background: rgba(var(--primary-color), 0.1);
  color: rgb(var(--primary-color));
}

.status-card--warning .status-icon {
  background: rgba(var(--warning-color), 0.12);
  color: rgb(var(--warning-color));
}

.status-card--success .status-icon {
  background: rgba(var(--success-color), 0.12);
  color: rgb(var(--success-color));
}

.status-card--error .status-icon {
  background: rgba(var(--error-color), 0.12);
  color: rgb(var(--error-color));
}
</style>
