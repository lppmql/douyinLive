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
  formatDuration,
  getTranscriptFailureInfo
} from '@/utils/transcriptHelpers';
import { computed } from 'vue';
import { useAuthStore } from '@/store/modules/auth';

defineOptions({ name: 'TranscriptTaskDrawer' });

type TaskStatus = Api.Douyin.TranscriptTask['status'];
const authStore = useAuthStore();
/** 删除会清理技术任务数据，因此只给超级管理员显示。 */
const canDeleteTasks = computed(() =>
  authStore.userInfo.roles.some(role => role === 'R_SUPER' || role === 'R_ADMIN')
);
/** 转写是业务写操作，只读查看者不显示重试入口。 */
const canRetryTasks = computed(() =>
  authStore.userInfo.roles.some(role => ['R_SUPER', 'R_ADMIN', 'R_USER'].includes(role))
);

defineProps<{
  /** 抽屉是否可见 */
  visible: boolean;
  /** 当前筛选状态 */
  taskFilter: TaskStatus | 'all';
  /** 筛选后的任务列表 */
  filteredTasks: Api.Douyin.TranscriptTask[];
  /** 是否正在清空全部失败任务 */
  clearFailedLoading?: boolean;
  /** 正在删除中的任务 ID 集合 */
  deletingTaskIds?: Set<number>;
}>();

defineEmits<{
  'update:visible': [value: boolean];
  'update:taskFilter': [value: TaskStatus | 'all'];
  selectTask: [task: Api.Douyin.TranscriptTask];
  openSessionDetail: [sessionId: number];
  /** 删除单条失败任务 */
  deleteTask: [task: Api.Douyin.TranscriptTask];
  /** 保留已完成分片并重试失败任务 */
  retryTask: [task: Api.Douyin.TranscriptTask];
  /** 一键清空全部失败任务 */
  clearFailedTasks: [];
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

      <!-- 清空全部失败任务（仅筛选到「失败」tab 时显示） -->
      <div v-if="canDeleteTasks && taskFilter === 'failed' && filteredTasks.length > 0" class="mb-12px">
        <NButton
          type="error"
          size="small"
          :loading="clearFailedLoading"
          @click="$emit('clearFailedTasks')"
        >
          清空全部失败任务（{{ filteredTasks.length }} 条）
        </NButton>
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
                <NTag size="tiny" type="info" :bordered="false">
                  {{ task.task_type === 'realtime' ? '实时滚动转写' : '结束后转写' }}
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
              <!-- 转写进度条（仅处理中的任务显示） -->
              <div v-if="task.status === 'processing' && task.total_chunks > 0" class="mt-8px">
                <div class="mb-3px flex items-center justify-between text-11px text-gray-500">
                  <span>{{ task.task_type === 'realtime' ? '实时窗口' : '转写进度' }}</span>
                  <span v-if="task.task_type === 'realtime'">
                    已处理 {{ task.completed_chunks }} 个两分钟窗口
                  </span>
                  <span v-else>
                    {{ task.completed_chunks }} / {{ task.total_chunks }} 分片（{{ task.progress_percent }}%）
                  </span>
                </div>
                <NProgress
                  v-if="task.task_type !== 'realtime'"
                  :percentage="task.progress_percent"
                  :height="6"
                  :border-radius="3"
                  color="#f0a020"
                  :show-indicator="false"
                />
              </div>
            </div>
            <div class="flex shrink-0 flex-col gap-6px">
              <NButton size="tiny" secondary @click="$emit('selectTask', task)">查看话术</NButton>
              <NButton
                v-if="canRetryTasks && (task.status === 'failed' || task.status === 'cancelled')"
                size="tiny"
                type="primary"
                secondary
                @click="$emit('retryTask', task)"
              >
                断点重试
              </NButton>
            </div>
            <!-- 失败/已取消任务显示删除按钮 -->
            <NButton
              v-if="canDeleteTasks && (task.status === 'failed' || task.status === 'cancelled')"
              size="tiny"
              type="error"
              :loading="deletingTaskIds?.has(task.id)"
              @click="$emit('deleteTask', task)"
            >
              删除
            </NButton>
          </div>
          <!-- 转写错误 -->
          <NAlert v-if="task.error_message" type="error" :bordered="false" class="mt-10px">
            <template #header>{{ getTranscriptFailureInfo(task.error_message).title }}</template>
            <div>{{ getTranscriptFailureInfo(task.error_message).hint }}</div>
            <div class="mt-8px flex flex-wrap items-center gap-10px">
              <details class="min-w-0 flex-1 text-11px text-gray-500">
                <summary class="cursor-pointer">技术详情</summary>
                <div class="mt-5px break-all">{{ task.error_message }}</div>
              </details>
              <NButton text type="error" @click="$emit('openSessionDetail', task.session_id)">检查场次回放</NButton>
            </div>
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
