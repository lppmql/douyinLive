<script setup lang="ts">
import { h } from 'vue';
import type { VNodeChild } from 'vue';
import { NAlert, NButton, NDataTable, NDrawer, NDrawerContent, NSpace, NTag } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import { formatFullTime, formatLogTime, getStageLabel } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorTaskDrawer' });

const props = defineProps<{
  visible: boolean;
  tasks: Api.Douyin.UnifiedCollectorTask[];
  now: number;
  actionLoadingKey: string | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'viewLogs', task: Api.Douyin.UnifiedCollectorTask): void;
  (e: 'stop', task: Api.Douyin.UnifiedCollectorTask): void;
  (e: 'retry', task: Api.Douyin.UnifiedCollectorTask): void;
}>();

function statusInfo(status: string) {
  const states: Record<string, { label: string; type: 'default' | 'info' | 'warning' | 'success' | 'error' }> = {
    pending: { label: '等待执行', type: 'info' },
    queued: { label: '等待转写', type: 'info' },
    running: { label: '正在执行', type: 'warning' },
    processing: { label: '正在转写', type: 'warning' },
    completed: { label: '已完成', type: 'success' },
    failed: { label: '执行失败', type: 'error' },
    cancelled: { label: '已停止', type: 'default' }
  };
  return states[status] || { label: status, type: 'default' as const };
}

const taskColumns = [
  {
    title: '任务',
    key: 'task_label',
    width: 185,
    fixed: 'left' as const,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      return h('div', { class: 'min-w-0' }, [
        h('div', { class: 'truncate text-13px font-600' }, `${row.task_label} #${row.id}`),
        h('div', { class: 'mt-3px text-11px text-gray-400' }, row.source === 'asr' ? 'ASR 自适应处理' : '采集处理队列')
      ]);
    }
  },
  {
    title: '主播 / 场次',
    key: 'session',
    width: 190,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      if (!row.session_id) return '-';
      return h('div', { class: 'min-w-0' }, [
        h(AnchorIdentity, {
          sessionId: row.session_id,
          avatarUrl: row.anchor_avatar_url,
          name: row.anchor_name,
          nickname: row.anchor_nickname,
          douyinId: row.douyin_id,
          size: 30,
          dense: true
        }),
        h('div', { class: 'mt-3px truncate text-11px text-gray-400', title: row.session_title || '' }, row.session_title || `场次 #${row.session_id}`)
      ]);
    }
  },
  {
    title: '状态',
    key: 'status',
    width: 105,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      const state = statusInfo(row.status);
      return h(NTag, { type: state.type, size: 'small', round: true, bordered: false }, { default: () => state.label });
    }
  },
  {
    title: '执行进度',
    key: 'progress_percent',
    width: 255,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      return h('div', { class: 'min-w-0' }, [
        h('div', { class: 'text-12px font-500 tabular-nums' }, `${row.progress_percent}% · ${row.progress_current}/${row.progress_total}`),
        h('div', { class: 'mt-3px truncate text-11px text-gray-500', title: row.progress_message || '' }, `${getStageLabel(row.progress_stage)} · ${row.progress_message || '-'}`),
        row.task_type === 'collect_all'
          ? h('div', { class: 'mt-3px text-11px text-primary' }, `主播 ${row.collected_anchor_count} 位 · 场次 ${row.collected_session_count} 场 · 补齐 ${row.refreshed_detail_count} 场`)
          : null
      ]);
    }
  },
  {
    title: '时间 / 心跳',
    key: 'started_at',
    width: 190,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      return h('div', { class: 'text-11px' }, [
        h('div', {}, formatFullTime(row.started_at || row.created_at)),
        h('div', { class: 'mt-3px text-gray-400' }, `心跳 ${row.heartbeat_at ? formatLogTime(row.heartbeat_at, props.now) : '-'} · 第 ${row.retry_count} 次`)
      ]);
    }
  },
  {
    title: '结果 / 失败原因',
    key: 'error_message',
    minWidth: 220,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.UnifiedCollectorTask) {
      return row.error_message || row.progress_message || '-';
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: 190,
    fixed: 'right' as const,
    render(row: Api.Douyin.UnifiedCollectorTask) {
      const loading = props.actionLoadingKey === row.task_key;
      const actions: VNodeChild[] = [];
      if (row.can_stop) {
        actions.push(h(
          NButton,
          { text: true, type: 'error', size: 'small', loading, onClick: () => emit('stop', row) },
          { default: () => '停止' }
        ));
      }
      if (row.can_retry) {
        actions.push(h(
          NButton,
          { text: true, type: 'warning', size: 'small', loading, onClick: () => emit('retry', row) },
          { default: () => '重试' }
        ));
      }
      actions.push(h(
        NButton,
        { text: true, type: 'primary', size: 'small', onClick: () => emit('viewLogs', row) },
        { default: () => '查看信息' }
      ));
      return h(NSpace, { size: 12, wrap: false }, { default: () => actions });
    }
  }
];
</script>

<template>
  <NDrawer
    :show="visible"
    width="min(960px, 96vw)"
    placement="right"
    @update:show="value => emit('update:visible', value)"
  >
    <NDrawerContent title="采集任务队列" closable>
      <NAlert class="mb-14px" type="info" :bordered="false" show-icon>
        补齐刷新优先执行，ASR 按电脑资源处理最新场次，知识库与 DataEase 自动同步。“停止”只结束当前任务，关闭监控或 ASR 开关才会释放对应资源。
      </NAlert>
      <div class="business-table-shell">
        <NDataTable
          :columns="taskColumns"
          :data="tasks"
          :row-key="row => row.task_key"
          :scroll-x="1340"
          max-height="calc(100vh - 190px)"
          :bordered="false"
          :single-line="false"
          size="small"
          striped
          empty-text="当前没有任务记录"
        />
      </div>
    </NDrawerContent>
  </NDrawer>
</template>
