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
  formatDate,
  formatDuration,
  getTranscriptFailureInfo
} from '@/utils/transcriptHelpers';
import { computed } from 'vue';
import { useAuthStore } from '@/store/modules/auth';
import type { TranscriptTaskFilter } from '../composables/useTranscriptWorkbench';

defineOptions({ name: 'TranscriptTaskDrawer' });

const authStore = useAuthStore();
/** 删除会清理技术任务数据，因此只给超级管理员显示。 */
const canDeleteTasks = computed(() => authStore.userInfo.roles.some(role => role === 'R_SUPER' || role === 'R_ADMIN'));
/** 转写是业务写操作，只读查看者不显示重试入口。 */
const canRetryTasks = computed(() =>
  authStore.userInfo.roles.some(role => ['R_SUPER', 'R_ADMIN', 'R_USER'].includes(role))
);

const props = defineProps<{
  visible: boolean;
  taskFilter: TranscriptTaskFilter;
  filteredTasks: Api.Douyin.TranscriptTask[];
  clearFailedLoading?: boolean;
  deletingTaskIds?: Set<number>;
  taskActionIds: Set<number>;
  asrRuntime: Api.Douyin.AsrControlStatus | null;
  dispatchPolicy: Api.Douyin.TranscriptDispatchPolicy | null;
}>();

defineEmits<{
  'update:visible': [value: boolean];
  'update:taskFilter': [value: TranscriptTaskFilter];
  selectTask: [task: Api.Douyin.TranscriptTask];
  openSessionDetail: [sessionId: number];
  /** 删除单条失败任务 */
  deleteTask: [task: Api.Douyin.TranscriptTask];
  /** 保留已完成分片并重试失败任务 */
  retryTask: [task: Api.Douyin.TranscriptTask];
  prioritizeTask: [task: Api.Douyin.TranscriptTask];
  releaseTaskPriority: [task: Api.Douyin.TranscriptTask];
  stopTask: [task: Api.Douyin.TranscriptTask];
  /** 一键清空全部失败任务 */
  clearFailedTasks: [];
}>();

function formatWaitingTime(task: Api.Douyin.TranscriptTask): string {
  if (task.status !== 'queued' || !task.created_at) return '';
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(task.created_at).getTime()) / 1000));
  if (seconds < 60) return `已等待 ${seconds} 秒`;
  if (seconds < 3600) return `已等待 ${Math.floor(seconds / 60)} 分钟`;
  return `已等待 ${(seconds / 3600).toFixed(1)} 小时`;
}

function blockedReason(task: Api.Douyin.TranscriptTask): string {
  if (task.cancel_requested) return '正在等待当前音频安全点后停止';
  if (task.status !== 'queued') return '';
  if (!props.asrRuntime?.worker_healthy) return '转写 Worker 无有效心跳，等待自动恢复';
  if (task.queue_source === 'auto' && props.dispatchPolicy?.manual_active) {
    return `等待人工优先场次 #${props.dispatchPolicy.manual_session_id} 完成`;
  }
  return task.queue_position ? `当前排队第 ${task.queue_position} 位` : '等待可用转写通道';
}

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
        <NRadioGroup
          :value="taskFilter"
          size="small"
          @update:value="(val: string) => $emit('update:taskFilter', val as TranscriptTaskFilter)"
        >
          <NRadioButton value="all">全部</NRadioButton>
          <NRadioButton value="queued">等待</NRadioButton>
          <NRadioButton value="processing">处理中</NRadioButton>
          <NRadioButton value="completed">完成</NRadioButton>
          <NRadioButton value="attention">暂停/失败</NRadioButton>
        </NRadioGroup>
        <span class="text-12px text-gray-500">{{ filteredTasks.length }} 个真实任务</span>
      </div>

      <NAlert v-if="asrRuntime && !asrRuntime.worker_healthy" type="error" :bordered="false" class="mb-12px">
        <template #header>任务队列暂时无法推进</template>
        {{ asrRuntime.message }}
      </NAlert>

      <!-- 清空失败和暂停任务（仅筛选到“暂停/失败”时显示） -->
      <div v-if="canDeleteTasks && taskFilter === 'attention' && filteredTasks.length > 0" class="mb-12px">
        <NButton type="error" size="small" :loading="clearFailedLoading" @click="$emit('clearFailedTasks')">
          清空暂停/失败任务（{{ filteredTasks.length }} 条）
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
                <NTag v-if="task.queue_source === 'manual'" size="tiny" type="warning" :bordered="false">人工独占</NTag>
                <NTag v-if="task.cancel_requested" size="tiny" type="error" :bordered="false">停止中</NTag>
                <NTag v-if="task.status === 'queued' && task.queue_position" size="tiny" :bordered="false">
                  排队第 {{ task.queue_position }} 位
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
                <span v-if="formatWaitingTime(task)">{{ formatWaitingTime(task) }}</span>
              </div>
              <div
                v-if="blockedReason(task)"
                class="mt-7px rounded-6px bg-gray-50 px-8px py-5px text-11px text-gray-500 dark:bg-white/5"
              >
                {{ blockedReason(task) }}
              </div>
              <!-- 转写进度条（仅处理中的任务显示） -->
              <div v-if="task.status === 'processing' && task.total_chunks > 0" class="mt-8px">
                <div class="mb-3px flex items-center justify-between text-11px text-gray-500">
                  <span>{{ task.task_type === 'realtime' ? '实时窗口' : '转写进度' }}</span>
                  <span v-if="task.task_type === 'realtime'">已处理 {{ task.completed_chunks }} 个两分钟窗口</span>
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
                v-if="canRetryTasks && ['queued', 'processing'].includes(task.status) && task.queue_source === 'auto'"
                size="tiny"
                type="warning"
                secondary
                :loading="taskActionIds.has(task.id)"
                @click="$emit('prioritizeTask', task)"
              >
                人工优先
              </NButton>
              <NButton
                v-if="canRetryTasks && ['queued', 'processing'].includes(task.status) && task.queue_source === 'manual'"
                size="tiny"
                type="warning"
                secondary
                :loading="taskActionIds.has(task.id)"
                @click="$emit('releaseTaskPriority', task)"
              >
                取消优先
              </NButton>
              <NButton
                v-if="canRetryTasks && ['queued', 'processing'].includes(task.status)"
                size="tiny"
                type="error"
                secondary
                :disabled="task.cancel_requested"
                :loading="taskActionIds.has(task.id)"
                @click="$emit('stopTask', task)"
              >
                {{ task.cancel_requested ? '停止中' : '安全停止' }}
              </NButton>
              <NButton
                v-if="canRetryTasks && (task.status === 'failed' || task.status === 'cancelled')"
                size="tiny"
                type="primary"
                secondary
                :loading="taskActionIds.has(task.id)"
                @click="$emit('retryTask', task)"
              >
                断点重试
              </NButton>
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
          </div>
          <!-- 转写错误 -->
          <NAlert
            v-if="task.error_message"
            :type="['failed', 'cancelled'].includes(task.status) ? 'error' : 'info'"
            :bordered="false"
            class="mt-10px"
          >
            <template #header>
              {{
                ['failed', 'cancelled'].includes(task.status)
                  ? getTranscriptFailureInfo(task.error_message).title
                  : '调度说明'
              }}
            </template>
            <div v-if="['failed', 'cancelled'].includes(task.status)">
              {{ getTranscriptFailureInfo(task.error_message).hint }}
            </div>
            <div class="mt-8px flex flex-wrap items-center gap-10px">
              <details class="min-w-0 flex-1 text-11px text-gray-500">
                <summary class="cursor-pointer">技术详情</summary>
                <div class="mt-5px break-all">{{ task.error_message }}</div>
              </details>
              <NButton text type="error" @click="$emit('openSessionDetail', task.session_id)">检查场次回放</NButton>
            </div>
          </NAlert>
        </NCard>
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
