<!--
  日志详情弹窗 — 从 collector/index.vue 拆分
  展示单条采集日志的完整信息（时间、级别、阶段、消息、结构化 JSON）
-->
<script setup lang="ts">
import { NModal, NDescriptions, NDescriptionsItem } from 'naive-ui';
import { formatFullTime, getStageLabel, getLogPayload, getLogSummary } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorLogDetailModal' });

defineProps<{
  /** 弹窗是否可见 */
  visible: boolean;
  /** 要展示的日志（null 时不渲染内容） */
  log: Api.Douyin.CollectorLog | null;
}>();

const emit = defineEmits<{
  /** 关闭弹窗 */
  (e: 'update:visible', value: boolean): void;
}>();

</script>

<template>
  <NModal
    :show="visible"
    preset="card"
    title="采集日志详情"
    class="w-720px max-w-[calc(100vw-32px)]"
    @update:show="(val: boolean) => emit('update:visible', val)"
  >
    <template v-if="log">
      <NDescriptions :column="2" bordered label-placement="left" size="small">
        <NDescriptionsItem label="日志 ID">#{{ log.id }}</NDescriptionsItem>
        <NDescriptionsItem label="任务 ID">
          {{ log.task_id ? `#${log.task_id}` : '-' }}
        </NDescriptionsItem>
        <NDescriptionsItem label="时间">{{ formatFullTime(log.created_at) }}</NDescriptionsItem>
        <NDescriptionsItem label="级别">{{ log.level.toUpperCase() }}</NDescriptionsItem>
        <NDescriptionsItem label="阶段">{{ getStageLabel(getLogPayload(log).stage) }}</NDescriptionsItem>
        <NDescriptionsItem label="数据摘要">{{ getLogSummary(log) }}</NDescriptionsItem>
        <NDescriptionsItem label="消息" :span="2">{{ log.message || '-' }}</NDescriptionsItem>
      </NDescriptions>
      <div class="mt-16px">
        <div class="mb-8px font-600">结构化数据</div>
        <pre
          class="max-h-360px overflow-auto whitespace-pre-wrap rounded-8px bg-gray-100 p-12px text-12px dark:bg-white/5"
        >{{ JSON.stringify(getLogPayload(log), null, 2) }}</pre>
      </div>
    </template>
    <template v-else>
      <!-- 没有选中日志时显示空状态 -->
      <div class="flex-center py-40px text-gray-400">未选择日志</div>
    </template>
  </NModal>
</template>
