<script setup lang="ts">
import { h } from 'vue';
import { NButton, NCard, NDataTable, NRadioButton, NRadioGroup, NSpace, NTag } from 'naive-ui';
import { getCollectorLogDetailPreview } from '../adapters/collector-log-adapter';
import { formatFullTime, formatLogTime, getStageLabel } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorLogTable' });

const props = defineProps<{
  loading: boolean;
  silentRefreshing: boolean;
  clearLogsLoading: boolean;
  logs: Api.Douyin.CollectorLog[];
  logLevel: string;
  logTaskId: number | null;
  now: number;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'clear'): void;
  (e: 'filter', level: string): void;
  (e: 'clearTaskFilter'): void;
  (e: 'openDetail', log: Api.Douyin.CollectorLog): void;
}>();

function levelInfo(level: string) {
  const states: Record<string, { label: string; type: 'info' | 'warning' | 'error' }> = {
    info: { label: '信息', type: 'info' },
    warn: { label: '警告', type: 'warning' },
    error: { label: '异常', type: 'error' }
  };
  return states[level] || states.info;
}

const logColumns = [
  {
    title: '产生时间',
    key: 'created_at',
    width: 145,
    render(row: Api.Douyin.CollectorLog) {
      return h('span', { title: formatFullTime(row.created_at) }, formatLogTime(row.created_at, props.now));
    }
  },
  {
    title: '主播 / 直播场次',
    key: 'anchor_name',
    width: 230,
    render(row: Api.Douyin.CollectorLog) {
      if (!row.anchor_name && !row.session_id) return '-';
      return h('div', { class: 'min-w-0' }, [
        h('div', { class: 'truncate text-12px font-600', title: row.anchor_name || '' }, row.anchor_name || '未知主播'),
        h(
          'div',
          { class: 'mt-3px truncate text-11px text-gray-400', title: row.session_title || '' },
          row.session_title || (row.session_id ? `场次 #${row.session_id}` : '-')
        )
      ]);
    }
  },
  {
    title: '任务 / 阶段',
    key: 'stage',
    width: 145,
    render(row: Api.Douyin.CollectorLog) {
      return h('div', { class: 'text-11px' }, [
        h('div', {}, row.task_id ? `任务 #${row.task_id}` : row.task_type || '系统日志'),
        h('div', { class: 'mt-3px text-gray-400' }, getStageLabel(row.stage))
      ]);
    }
  },
  {
    title: '级别',
    key: 'level',
    width: 78,
    render(row: Api.Douyin.CollectorLog) {
      const state = levelInfo(row.level);
      return h(NTag, { type: state.type, size: 'small', bordered: false }, { default: () => state.label });
    }
  },
  {
    title: '采集消息',
    key: 'message',
    minWidth: 330,
    ellipsis: { tooltip: true }
  },
  {
    title: '数据详情',
    key: 'data_details',
    minWidth: 320,
    ellipsis: { tooltip: true },
    render: (row: Api.Douyin.CollectorLog) => getCollectorLogDetailPreview(row)
  },
  {
    title: '操作',
    key: 'detail',
    width: 92,
    fixed: 'right' as const,
    render(row: Api.Douyin.CollectorLog) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'small', onClick: () => emit('openDetail', row) },
        { default: () => '查看详情' }
      );
    }
  }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="采集日志">
    <template #header-extra>
      <NSpace align="center" wrap>
        <NTag v-if="logTaskId" type="primary" closable :bordered="false" @close="emit('clearTaskFilter')">
          仅任务 #{{ logTaskId }}
        </NTag>
        <NRadioGroup :value="logLevel" size="small" @update:value="value => emit('filter', value)">
          <NRadioButton value="all">全部</NRadioButton>
          <NRadioButton value="info">信息</NRadioButton>
          <NRadioButton value="warn">警告</NRadioButton>
          <NRadioButton value="error">异常</NRadioButton>
        </NRadioGroup>
        <NButton size="small" :loading="loading || silentRefreshing" @click="emit('refresh')">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新
        </NButton>
        <NButton size="small" type="error" secondary :loading="clearLogsLoading" @click="emit('clear')">
          <template #icon><SvgIcon icon="mdi:delete-sweep-outline" /></template>
          清空日志
        </NButton>
      </NSpace>
    </template>
    <div class="business-table-shell">
      <NDataTable
        class="collector-log-table"
        :loading="loading"
        :columns="logColumns"
        :data="logs"
        :row-key="row => row.id"
        :scroll-x="1370"
        flex-height
        :bordered="false"
        :single-line="false"
        size="small"
        striped
        empty-text="暂无符合条件的采集日志"
      />
    </div>
  </NCard>
</template>

<style scoped>
.collector-log-table {
  height: 420px;
}

@media (max-width: 640px) {
  .collector-log-table {
    height: 360px;
  }
}
</style>
