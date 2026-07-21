<script setup lang="ts">
/**
 * 任务抽屉
 *
 * 右侧滑出抽屉，显示转写任务列表。
 * 支持按状态筛选（全部 / 等待 / 处理中 / 完成 / 失败）。
 * 点击任务可切换到对应场次查看话术。
 */
import {
  getStatusLabel,
  getStatusType,
  getPostprocessLabel,
  getPostprocessType,
  formatDate,
  formatDuration
} from '@/utils/transcriptHelpers';

defineOptions({ name: 'TranscriptTaskDrawer' });

type TaskStatus = Api.Douyin.TranscriptTask['status'];

defineProps<{
  /** 抽屉是否可见 */
  visible: boolean;
  /** 当前筛选状态 */
  taskFilter: TaskStatus | 'all';
  /** 筛选后的任务列表 */
  filteredTasks: Api.Douyin.TranscriptTask[];
}>();

defineEmits<{
  'update:visible': [value: boolean];
  'update:taskFilter': [value: TaskStatus | 'all'];
  selectTask: [task: Api.Douyin.TranscriptTask];
  openSessionDetail: [sessionId: number];
}>();
</script>

<template>
  <NDrawer
    :show="visible"
    width="min(620px, 94vw)"
    placement="right"
    @update:show="(val: boolean) => $emit('update:visible', val)"
  >
    <NDrawerContent title="话术转写任务" closable>
      <!-- 状态筛选 -->
      <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
        <NRadioGroup :value="taskFilter" size="small" @update:value="(val: string) => $emit('update:taskFilter', val as TaskStatus | 'all')">
          <NRadioButton value="all">全部</NRadioButton>
          <NRadioButton value="queued">等待</NRadioButton>
          <NRadioButton value="processing">处理中</NRadioButton>
          <NRadioButton value="completed">完成</NRadioButton>
          <NRadioButton value="failed">失败</NRadioButton>
        </NRadioGroup>
        <span class="text-12px text-gray-500">{{ filteredTasks.length }} 个真实任务</span>
      </div>

      <!-- 空状态 -->
      <NEmpty v-if="!filteredTasks.length" description="该状态下暂无任务" class="py-60px" />

      <!-- 任务列表 -->
      <div v-else class="space-y-10px">
        <NCard v-for="task in filteredTasks" :key="task.id" size="small" :bordered="true">
          <div class="flex items-start justify-between gap-12px">
            <div class="min-w-0 flex-1">
              <!-- 主播 + 状态标签 -->
              <div class="flex flex-wrap items-center gap-8px">
                <strong class="text-14px">{{ task.anchor_name }}</strong>
                <NTag size="tiny" :type="getStatusType(task.status)" :bordered="false">
                  {{ getStatusLabel(task.status) }}
                </NTag>
                <NTag
                  v-if="task.status === 'completed'"
                  size="tiny"
                  :type="getPostprocessType(task.postprocess_status)"
                  :bordered="false"
                >
                  {{ getPostprocessLabel(task.postprocess_status) }}
                </NTag>
                <span class="text-11px text-gray-400">任务 #{{ task.id }}</span>
              </div>
              <!-- 场次标题 -->
              <div class="mt-5px truncate text-12px text-gray-500">{{ task.session_title }}</div>
              <!-- 详情 -->
              <div class="mt-5px flex flex-wrap gap-x-12px gap-y-4px text-11px text-gray-400">
                <span>{{ formatDate(task.live_start_time) }}</span>
                <span>{{ formatDuration(task.live_duration_seconds) }}</span>
                <span>{{ task.segment_count }} 个分段</span>
                <span v-if="task.retry_count">已尝试 {{ task.retry_count }}/{{ task.max_retries }} 次</span>
              </div>
            </div>
            <NButton size="tiny" secondary @click="$emit('selectTask', task)">查看话术</NButton>
          </div>
          <!-- 转写错误 -->
          <NAlert v-if="task.error_message" type="error" :bordered="false" class="mt-10px">
            {{ task.error_message }}
            <NButton text type="error" class="ml-6px" @click="$emit('openSessionDetail', task.session_id)">
              检查回放
            </NButton>
          </NAlert>
          <!-- 复盘入库错误 -->
          <NAlert v-if="task.postprocess_error" type="warning" :bordered="false" class="mt-10px">
            {{ task.postprocess_error }}
          </NAlert>
        </NCard>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
