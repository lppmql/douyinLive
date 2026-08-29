<script setup lang="ts">
/**
 * 场次选择 + 操作工具栏
 *
 * 包含：
 * - 场次搜索下拉（带主播头像）
 * - 主播信息展示 + WebSocket 状态
 * - 操作按钮：复制全文 / 开始转写 / AI 分析并入库 / 更多操作
 * - 实时话术预览 + 转写失败提示
 */
import { computed } from 'vue';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import SessionSelector from '@/components/business/session-selector.vue';
import {
  formatDate,
  formatDuration,
  getStatusLabel,
  getStatusType,
  getTranscriptFailureInfo
} from '@/utils/transcriptHelpers';
import type { SessionSelectOption } from '@/adapters/transcript-adapter';
import type { AnchorSelectorOption, SessionDateRange } from '@/adapters/session-selector-adapter';

defineOptions({ name: 'TranscriptSessionControl' });

const props = defineProps<{
  /** 场次下拉选项列表 */
  sessionOptions: SessionSelectOption[];
  anchorOptions: AnchorSelectorOption[];
  anchorKey: string | null;
  dateRange: SessionDateRange;
  /** 当前选中场次 ID */
  selectedSessionId: number | null;
  /** 场次列表是否加载中 */
  loading: boolean;
  /** 当前选中场次对象 */
  selectedSession: Api.Douyin.LiveSessionListItem | null;
  /** 当前场次对应的转写任务 */
  selectedTask: Api.Douyin.TranscriptTask | null;
  /** 是否有话术内容 */
  hasContent: boolean;
  /** 正在发起转写 */
  queueLoading: boolean;
  /** 正在批量转写 */
  batchLoading: boolean;
  /** 正在 AI 分析 */
  aiLoading: boolean;
  /** 当前版本是否满足 AI 复盘门槛 */
  canRunAiPipeline: boolean;
  /** 当前页面实际展示的话术版本 */
  contentVersion: 'offline-final' | 'realtime-draft' | 'empty';
  /** 当前页面实际展示的话术版本文案 */
  contentVersionLabel: string;
  /** 实时话术预览文本 */
  livePreview: string;
  /** WebSocket 是否已连接 */
  wsConnected: boolean;
  /** 自动任务排序及当前人工独占状态 */
  dispatchPolicy: Api.Douyin.TranscriptDispatchPolicy | null;
  dispatchPolicyLoading: boolean;
  /** 模型与 Worker 的真实运行状态。 */
  asrRuntime: Api.Douyin.AsrControlStatus | null;
  runtimeActionLoading: boolean;
}>();

const emit = defineEmits<{
  'update:selectedSessionId': [value: number | null];
  'update:anchorKey': [value: string | null];
  'update:dateRange': [value: SessionDateRange];
  searchSessions: [keyword: string];
  resetFilters: [];
  startTranscription: [];
  runAiPipeline: [];
  copyFullText: [];
  queueAnchorBatch: [];
  openTaskDrawer: [status?: string];
  openSessionDetail: [sessionId: number];
  changeDispatchOrder: [value: Api.Douyin.TranscriptDispatchPolicy['order_mode']];
  restoreRuntime: [];
  releaseTaskPriority: [task: Api.Douyin.TranscriptTask];
  stopTask: [task: Api.Douyin.TranscriptTask];
}>();

const taskBusy = computed(() => ['queued', 'processing'].includes(props.selectedTask?.status || ''));
const manualPriorityActive = computed(
  () => taskBusy.value && props.selectedTask?.queue_source === 'manual' && !props.selectedTask.cancel_requested
);
const failureInfo = computed(() => getTranscriptFailureInfo(props.selectedTask?.error_message));
const canStartTranscription = computed(() => {
  if (!props.selectedSessionId) return false;
  if (taskBusy.value) return props.selectedTask?.queue_source !== 'manual';
  if (!props.selectedTask) return true;
  if (['failed', 'cancelled'].includes(props.selectedTask.status)) return true;
  return props.selectedTask.task_type === 'realtime' && props.selectedSession?.live_status !== 'live';
});
const transcriptionActionLabel = computed(() => {
  if (taskBusy.value && props.selectedTask?.queue_source === 'manual') return '人工优先中';
  if (taskBusy.value) return '优先转写本场';
  if (props.selectedTask?.status === 'failed') return failureInfo.value.actionLabel;
  if (props.selectedTask?.task_type === 'offline' && props.selectedTask.status === 'completed') return '终稿已完成';
  if (props.selectedTask?.task_type === 'realtime' && props.selectedSession?.live_status !== 'live')
    return '生成离线终稿';
  return props.selectedTask ? '重新转写' : '开始转写';
});
const versionTone = computed<'success' | 'warning' | 'default'>(() => {
  if (props.contentVersion === 'offline-final') return 'success';
  if (props.contentVersion === 'realtime-draft') return 'warning';
  return 'default';
});

const dispatchOrderOptions = [
  { label: '智能排序（推荐）', value: 'smart' },
  { label: '最新场次优先', value: 'latest' },
  { label: '最早排队优先', value: 'fifo' }
];

const moreActionOptions = computed(() => [
  { label: '补排昨日与今日自动任务', key: 'batch' },
  { label: '查看全部任务', key: 'tasks' },
  { label: '打开场次详情', key: 'detail', disabled: !props.selectedSessionId },
  {
    label: props.selectedTask?.cancel_requested ? '正在安全停止' : '安全停止本场任务',
    key: 'stop',
    disabled: !taskBusy.value || Boolean(props.selectedTask?.cancel_requested)
  }
]);

function handleMoreAction(key: string) {
  if (key === 'batch') return emit('queueAnchorBatch');
  if (key === 'tasks') return emit('openTaskDrawer');
  if (key === 'detail' && props.selectedSessionId) return emit('openSessionDetail', props.selectedSessionId);
  if (key === 'stop' && props.selectedTask) return emit('stopTask', props.selectedTask);
  return undefined;
}

</script>

<template>
  <NCard :bordered="false" class="card-wrapper transcript-workbench" title="场次话术工作台">
    <template #header-extra>
      <div class="flex items-center gap-8px">
        <NTag size="small" :type="versionTone" :bordered="false" round>{{ contentVersionLabel }}</NTag>
        <NTag size="small" :type="getStatusType(selectedTask?.status)" :bordered="false" round>
          {{ getStatusLabel(selectedTask?.status) }}
        </NTag>
      </div>
    </template>

    <div class="grid gap-16px xl:grid-cols-[minmax(0,1fr)_auto]">
      <div class="min-w-0">
        <div class="mb-8px flex items-center gap-8px text-12px font-600 text-gray-500">
          <span>选择直播场次</span>
          <NTag size="tiny" type="info" :bordered="false" round>默认最新</NTag>
        </div>
        <SessionSelector
          :model-value="selectedSessionId"
          :options="sessionOptions"
          :anchor-options="anchorOptions"
          :anchor-key="anchorKey"
          :date-range="dateRange"
          :loading="loading"
          :clearable="false"
          @update:model-value="emit('update:selectedSessionId', $event)"
          @update:anchor-key="emit('update:anchorKey', $event)"
          @update:date-range="emit('update:dateRange', $event)"
          @search="emit('searchSessions', $event)"
          @reset="emit('resetFilters')"
        />
        <div
          v-if="selectedSession"
          class="mt-12px flex flex-wrap items-center gap-x-12px gap-y-8px text-12px text-gray-500"
        >
          <AnchorIdentity
            class="max-w-240px"
            :session-id="selectedSession.id"
            :avatar-url="selectedSession.anchor_avatar_url"
            :name="selectedSession.anchor_name || '未知主播'"
            :nickname="selectedSession.anchor_nickname"
            :douyin-id="selectedSession.douyin_id"
            :size="32"
            dense
          />
          <span>{{ formatDate(selectedSession.live_start_time) }}</span>
          <span>{{ formatDuration(selectedSession.live_duration_seconds) }}</span>
          <NTooltip>
            <template #trigger>
              <NTag size="small" :type="wsConnected ? 'success' : 'default'" :bordered="false">
                {{ wsConnected ? '实时通道已连接' : '实时通道待命' }}
              </NTag>
            </template>
            只有实时任务执行时才接收新片段，离线状态不影响阅读已保存话术。
          </NTooltip>
        </div>
      </div>

      <div class="business-toolbar__actions self-end">
        <NButton secondary :disabled="!selectedSessionId || !hasContent" @click="emit('copyFullText')">
          <template #icon><SvgIcon icon="mdi:content-copy" /></template>
          复制当前版本
        </NButton>
        <NButton
          v-if="manualPriorityActive && selectedTask"
          type="warning"
          secondary
          :loading="queueLoading"
          @click="emit('releaseTaskPriority', selectedTask)"
        >
          取消人工优先
        </NButton>
        <NButton
          v-else
          type="primary"
          secondary
          :disabled="!canStartTranscription"
          :loading="queueLoading"
          @click="emit('startTranscription')"
        >
          {{ transcriptionActionLabel }}
        </NButton>
        <NTooltip :disabled="canRunAiPipeline">
          <template #trigger>
            <span>
              <NButton
                type="primary"
                :disabled="!canRunAiPipeline"
                :loading="aiLoading"
                @click="emit('runAiPipeline')"
              >
                生成复盘并入库
              </NButton>
            </span>
          </template>
          需要先完成下播后的离线终稿，避免用实时初稿生成错误结论。
        </NTooltip>
        <NDropdown
          trigger="click"
          :options="moreActionOptions"
          @select="handleMoreAction"
        >
          <NButton quaternary :loading="batchLoading" aria-label="更多话术操作">
            <SvgIcon icon="mdi:dots-horizontal" />
          </NButton>
        </NDropdown>
      </div>
    </div>

    <NAlert
      v-if="asrRuntime && !asrRuntime.worker_healthy"
      class="mt-16px"
      type="error"
      :bordered="false"
      show-icon
      aria-live="assertive"
    >
      <template #header>转写服务没有有效心跳</template>
      {{ asrRuntime.message || '当前任务会保留在队列，恢复 Worker 后从断点继续。' }}
      <NButton
        text
        type="error"
        class="ml-8px"
        :loading="runtimeActionLoading"
        @click="emit('restoreRuntime')"
      >
        立即恢复
      </NButton>
    </NAlert>

    <div
      class="mt-16px grid items-center gap-12px rounded-10px bg-gray-50 px-14px py-12px dark:bg-white/4 md:grid-cols-[minmax(0,1fr)_250px]"
    >
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-8px text-13px font-600">
          <span>自动转写：{{ dispatchPolicy?.auto_scope_description || '正在读取自动范围' }}</span>
          <NTag v-if="dispatchPolicy?.manual_active" size="tiny" type="warning" :bordered="false">
            人工场次 #{{ dispatchPolicy.manual_session_id }} 独占中
          </NTag>
        </div>
        <div class="mt-4px text-11px leading-18px text-gray-400">
          手动点击“优先转写本场”后，其他任务会在当前约 2 分钟分片结束时保存断点并暂停，人工任务结束后自动恢复。
        </div>
      </div>
      <NSelect
        :value="dispatchPolicy?.order_mode || 'smart'"
        :options="dispatchOrderOptions"
        :loading="dispatchPolicyLoading"
        aria-label="自动转写排序"
        @update:value="value => emit('changeDispatchOrder', value)"
      />
    </div>

    <div v-if="selectedTask && taskBusy && selectedTask.total_chunks > 0" class="mt-16px" aria-live="polite">
      <div class="mb-5px flex items-center justify-between text-12px text-gray-500">
        <span>{{ selectedTask.task_type === 'offline' ? '离线终稿进度' : '实时话术窗口' }}</span>
        <span>{{ selectedTask.completed_chunks }} / {{ selectedTask.total_chunks }} 分片</span>
      </div>
      <NProgress
        type="line"
        :percentage="selectedTask.progress_percent"
        :height="8"
        :show-indicator="false"
        processing
      />
    </div>

    <NAlert
      v-if="selectedTask?.status === 'failed'"
      class="mt-16px"
      type="error"
      :bordered="false"
      show-icon
      aria-live="assertive"
    >
      <template #header>{{ failureInfo.title }}</template>
      <div>{{ failureInfo.hint }}</div>
      <details class="mt-8px text-12px text-gray-500">
        <summary class="cursor-pointer">查看技术详情</summary>
        <div class="mt-6px break-all">{{ selectedTask.error_message || '后台未记录具体错误' }}</div>
      </details>
    </NAlert>

    <NAlert v-if="livePreview" class="mt-16px" type="info" :bordered="false" show-icon aria-live="polite">
      <template #header>正在接收实时话术</template>
      {{ livePreview }}
    </NAlert>
  </NCard>
</template>

<style scoped>
.transcript-workbench {
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--primary-color) 14%, transparent);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--primary-color) 5%, transparent), transparent 38%), var(--n-color);
}

@media (max-width: 767px) {
  .business-toolbar__actions {
    align-items: stretch;
  }
}
</style>
