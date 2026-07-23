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
import { h } from 'vue';
import type { SelectOption } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import {
  formatDate,
  formatDuration,
  getStatusLabel,
  getStatusType
} from '@/utils/transcriptHelpers';
import type { SessionSelectOption } from '@/adapters/transcript-adapter';

defineOptions({ name: 'TranscriptSessionControl' });

defineProps<{
  /** 场次下拉选项列表 */
  sessionOptions: SessionSelectOption[];
  /** 当前选中场次 ID */
  selectedSessionId: number | null;
  /** 场次列表是否加载中 */
  loading: boolean;
  /** 当前选中场次对象 */
  selectedSession: Api.Douyin.LiveSession | null;
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
  /** 实时话术预览文本 */
  livePreview: string;
  /** WebSocket 是否已连接 */
  wsConnected: boolean;
}>();

defineEmits<{
  'update:selectedSessionId': [value: number];
  startTranscription: [];
  runAiPipeline: [];
  copyFullText: [];
  queueAnchorBatch: [];
  openTaskDrawer: [status?: string];
  openSessionDetail: [sessionId: number];
}>();

/** 渲染场次下拉选项（带主播头像） */
function renderSessionLabel(option: SelectOption) {
  const sessionOption = option as SessionSelectOption;
  return h('div', { class: 'flex min-w-0 items-center justify-between gap-12px py-2px' }, [
    h(AnchorIdentity, {
      class: 'min-w-0 max-w-180px flex-1',
      sessionId: sessionOption.sessionId,
      avatarUrl: sessionOption.avatarUrl,
      name: sessionOption.anchorName,
      nickname: sessionOption.anchorNickname,
      douyinId: sessionOption.douyinId,
      size: 28,
      dense: true
    }),
    h('span', { class: 'shrink-0 text-11px text-gray-400' }, sessionOption.metaLabel)
  ]);
}
</script>

<template>
  <!-- 场次选择 + 工具栏 -->
  <NCard :bordered="false" class="card-wrapper">
    <div class="business-toolbar">
      <!-- 左侧：场次选择 -->
      <div class="min-w-0 flex-1">
        <div class="mb-8px flex items-center gap-8px text-12px font-600 text-gray-500">
          <span>当前复盘场次</span>
          <NTag size="tiny" type="info" :bordered="false" round>默认最新</NTag>
        </div>
        <NSelect
          :value="selectedSessionId"
          size="large"
          filterable
          :options="sessionOptions"
          :render-label="renderSessionLabel"
          :loading="loading"
          placeholder="搜索主播、日期或场次"
          @update:value="(val: number) => $emit('update:selectedSessionId', val)"
        />
        <!-- 当前场次信息 -->
        <div v-if="selectedSession" class="mt-10px flex flex-wrap items-center gap-8px text-12px text-gray-500">
          <AnchorIdentity
            class="max-w-220px"
            :session-id="selectedSession.id"
            :avatar-url="selectedSession.anchor_avatar_url"
            :name="selectedSession.anchor_name || '未知主播'"
            :nickname="selectedSession.anchor_nickname"
            :douyin-id="selectedSession.douyin_id"
            :size="30"
            dense
          />
          <span>{{ formatDate(selectedSession.live_start_time) }}</span>
          <span>{{ formatDuration(selectedSession.live_duration_seconds) }}</span>
          <NTag size="small" :type="getStatusType(selectedTask?.status)" :bordered="false">
            {{ getStatusLabel(selectedTask?.status) }}
          </NTag>
          <NTooltip>
            <template #trigger>
              <NTag size="small" :type="wsConnected ? 'success' : 'default'" :bordered="false">
                {{ wsConnected ? '实时连接正常' : '实时连接待命' }}
              </NTag>
            </template>
            只有任务正在转写时才会持续收到实时片段，离线状态不影响查看已保存话术。
          </NTooltip>
        </div>
      </div>

      <!-- 右侧：操作按钮 -->
      <div class="business-toolbar__actions">
        <NButton secondary :disabled="!selectedSessionId || !hasContent" @click="$emit('copyFullText')">
          <template #icon><SvgIcon icon="mdi:content-copy" /></template>
          复制全文
        </NButton>
        <NButton
          type="primary"
          secondary
          :disabled="!selectedSessionId"
          :loading="queueLoading"
          @click="$emit('startTranscription')"
        >
          {{ selectedTask ? '重新转写' : '开始转写' }}
        </NButton>
        <NButton type="primary" :disabled="!hasContent" :loading="aiLoading" @click="$emit('runAiPipeline')">
          AI 分析并入库
        </NButton>
        <NDropdown
          trigger="click"
          :options="[
            { label: '各主播增量转写', key: 'batch' },
            { label: '查看全部任务', key: 'tasks' },
            { label: '打开场次详情', key: 'detail', disabled: !selectedSessionId }
          ]"
          @select="
            key =>
              key === 'batch'
                ? $emit('queueAnchorBatch')
                : key === 'tasks'
                  ? $emit('openTaskDrawer')
                  : selectedSessionId && $emit('openSessionDetail', selectedSessionId)
          "
        >
          <NButton quaternary :loading="batchLoading"><SvgIcon icon="mdi:dots-horizontal" /></NButton>
        </NDropdown>
      </div>
    </div>
  </NCard>

  <!-- 转写失败提醒 -->
  <NAlert v-if="selectedTask?.status === 'failed'" type="error" :bordered="false" show-icon>
    本场最近一次转写失败：{{ selectedTask.error_message || '后台未记录具体错误' }}
    <NButton text type="error" class="ml-8px" @click="$emit('openSessionDetail', selectedTask.session_id)">
      检查场次回放
    </NButton>
  </NAlert>

  <!-- 实时话术预览 -->
  <NAlert v-if="livePreview" type="info" :bordered="false" show-icon>
    <template #header>正在接收实时话术</template>
    {{ livePreview }}
  </NAlert>
</template>
