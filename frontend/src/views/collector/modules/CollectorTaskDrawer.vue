<!--
  任务队列抽屉 — 从 collector/index.vue 拆分
  展示采集任务列表（类型、状态、进度、时间、失败原因），支持按任务查看日志
-->
<script setup lang="ts">
import { h } from 'vue';
import { NDrawer, NDrawerContent, NDataTable, NButton, NTag, NAlert } from 'naive-ui';
import { formatFullTime, formatLogTime, getStageLabel } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorTaskDrawer' });

const props = defineProps<{
  /** 抽屉是否可见 */
  visible: boolean;
  /** 任务列表 */
  tasks: Api.Douyin.CollectorTask[];
  /** 当前毫秒时间戳（驱动相对时间显示） */
  now: number;
}>();

const emit = defineEmits<{
  /** 关闭抽屉 */
  (e: 'update:visible', value: boolean): void;
  /** 查看某任务的日志 */
  (e: 'viewLogs', taskId: number): void;
}>();

/** 活跃任务数（pending + running） */
function activeTaskCount(): number {
  return props.tasks.filter(item => ['pending', 'running'].includes(item.status)).length;
}

/** 任务行 key */
function getTaskRowKey(row: Api.Douyin.CollectorTask) {
  return row.id;
}

/** 任务表格列定义 */
const taskColumns = [
  { title: '任务 ID', key: 'id', width: 90 },
  {
    title: '任务类型',
    key: 'task_type',
    minWidth: 120,
    render(row: Api.Douyin.CollectorTask) {
      const labels: Record<string, string> = {
        collect_all: '刷新数据采集',
        login: '扫码登录',
        metrics: '指标采集',
        comments: '评论采集',
        leads: '留资采集',
        profile: '画像采集',
        live_detail: '实时场次采集'
      };
      return labels[row.task_type] || row.task_type;
    }
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render(row: Api.Douyin.CollectorTask) {
      const states: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'error' }> = {
        pending: { label: '排队中', type: 'info' },
        running: { label: '运行中', type: 'warning' },
        completed: { label: '已完成', type: 'success' },
        failed: { label: '失败', type: 'error' }
      };
      const state = states[row.status] || { label: row.status, type: 'info' as const };
      return h(NTag, { type: state.type, size: 'small', round: true }, { default: () => state.label });
    }
  },
  {
    title: '进度',
    key: 'progress_percent',
    width: 210,
    render(row: Api.Douyin.CollectorTask) {
      return h('div', { class: 'flex flex-col gap-4px' }, [
        h('span', { class: 'text-12px' }, `${row.progress_percent || 0}% · ${getStageLabel(row.progress_stage)}`),
        h('span', { class: 'text-11px text-gray-500' }, row.progress_message || '-'),
        row.task_type === 'collect_all'
          ? h(
              'span',
              { class: 'text-11px text-primary' },
              `主播 ${row.collected_anchor_count || 0} 位 · 场次 ${row.collected_session_count || 0} 场`
            )
          : null
      ]);
    }
  },
  {
    title: '开始时间',
    key: 'started_at',
    width: 180,
    render(row: Api.Douyin.CollectorTask) {
      return formatFullTime(row.started_at);
    }
  },
  {
    title: '执行信息',
    key: 'trace_id',
    width: 210,
    render(row: Api.Douyin.CollectorTask) {
      const trace = row.trace_id ? row.trace_id.slice(0, 12) : '-';
      const heartbeat = row.heartbeat_at ? formatLogTime(row.heartbeat_at, props.now) : '-';
      return h('div', { class: 'flex flex-col gap-4px text-11px' }, [
        h('span', { class: 'font-mono text-gray-600', title: row.trace_id || '' }, `Trace ${trace}`),
        h(
          'span',
          { class: 'text-gray-500' },
          `心跳 ${heartbeat} · 执行 ${row.retry_count || 0}/${row.max_retries || 0}`
        )
      ]);
    }
  },
  { title: '失败原因', key: 'error_message', minWidth: 220, ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: 'action',
    width: 90,
    render(row: Api.Douyin.CollectorTask) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'tiny', onClick: () => emit('viewLogs', row.id) },
        { default: () => '查看日志' }
      );
    }
  }
];
</script>

<template>
  <NDrawer
    :show="visible"
    width="560px"
    placement="right"
    @update:show="(val: boolean) => emit('update:visible', val)"
  >
    <NDrawerContent title="采集任务队列" closable>
      <div class="mb-12px flex justify-end">
        <NTag :type="activeTaskCount() ? 'warning' : 'success'" round size="small">
          {{ activeTaskCount() ? `${activeTaskCount()} 个运行中` : '当前空闲' }}
        </NTag>
      </div>
      <NAlert class="mb-16px" type="info" :bordered="false">
        任务运行期间页面每 5 秒静默刷新；任务结束后自动停止高频请求。
      </NAlert>
      <NDataTable
        :columns="taskColumns"
        :data="tasks"
        :row-key="getTaskRowKey"
        :scroll-x="920"
        :bordered="false"
        size="small"
      />
    </NDrawerContent>
  </NDrawer>
</template>
