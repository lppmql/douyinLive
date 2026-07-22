<!-- 采集日志表格 — 从 collector/index.vue 拆分 -->
<script setup lang="ts">
import { h } from 'vue';
import { NButton, NCard, NDataTable, NTag, NRadioGroup, NRadioButton, NSpace } from 'naive-ui';
import { $t } from '@/locales';
import { formatLogTime, formatFullTime, getStageLabel, getLogPayload, getLogSummary } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorLogTable' });

const props = defineProps<{
  loading: boolean;
  silentRefreshing: boolean;
  clearLogsLoading: boolean;
  logs: Api.Douyin.CollectorLog[];
  logLevel: string;
  logTaskId: number | null;
  /** 当前毫秒时间戳，驱动相对时间显示（"刚刚"/"X 分钟前"） */
  now: number;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'clear'): void;
  (e: 'filter', level: string): void;
  (e: 'clearTaskFilter'): void;
  /** 点击"查看"按钮打开日志详情弹窗 */
  (e: 'openDetail', log: Api.Douyin.CollectorLog): void;
}>();

function getLogRowKey(row: Api.Douyin.CollectorLog) {
  return row.id;
}

/* ===== 表格列定义（原来在父组件 index.vue 中，搬到这里管理） ===== */

const logColumns = [
  {
    title: () => $t('page.collector.logTime'),
    key: 'created_at',
    width: 150,
    render(row: Api.Douyin.CollectorLog) {
      return h('span', { title: formatFullTime(row.created_at) }, formatLogTime(row.created_at, props.now));
    }
  },
  {
    title: '任务',
    key: 'task_id',
    width: 90,
    render(row: Api.Douyin.CollectorLog) {
      return row.task_id ? `#${row.task_id}` : '-';
    }
  },
  {
    title: '阶段',
    key: 'stage',
    width: 100,
    render(row: Api.Douyin.CollectorLog) {
      return getStageLabel(getLogPayload(row).stage);
    }
  },
  {
    title: () => $t('page.collector.logLevel'),
    key: 'level',
    width: 80,
    render(row: { level: string }) {
      const typeMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
        info: 'info',
        warn: 'warning',
        error: 'error'
      };
      return h(NTag, { type: typeMap[row.level] || 'info', size: 'small' }, { default: () => row.level.toUpperCase() });
    }
  },
  { title: () => $t('page.collector.logMessage'), key: 'message', minWidth: 300, ellipsis: { tooltip: true } },
  {
    title: '数据摘要',
    key: 'summary',
    minWidth: 240,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.CollectorLog) {
      return getLogSummary(row);
    }
  },
  {
    title: '详情',
    key: 'detail',
    width: 70,
    fixed: 'right' as const,
    render(row: Api.Douyin.CollectorLog) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'tiny', onClick: () => emit('openDetail', row) },
        { default: () => '查看' }
      );
    }
  }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" :title="$t('page.collector.logTitle')">
    <template #header-extra>
      <NSpace wrap>
        <NTag v-if="logTaskId" type="primary" closable @close="emit('clearTaskFilter')">
          仅任务 #{{ logTaskId }}
        </NTag>
        <NRadioGroup :value="logLevel" size="small" @update:value="(v: string) => emit('filter', v)">
          <NRadioButton value="all">全部</NRadioButton>
          <NRadioButton value="info">信息</NRadioButton>
          <NRadioButton value="warn">警告</NRadioButton>
          <NRadioButton value="error">异常</NRadioButton>
        </NRadioGroup>
        <NButton size="small" :loading="loading || silentRefreshing" @click="emit('refresh')">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          {{ $t('common.refresh') }}
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
        :row-key="getLogRowKey"
        :scroll-x="1260"
        flex-height
        :bordered="false"
        size="small"
      />
    </div>
  </NCard>
</template>

<!--
  样式说明：NDataTable 使用 flex-height 模式，高度由容器决定。
  这个 scoped CSS 必须写在子组件自己这里，不能依赖父组件 index.vue 的 scoped 样式，
  因为 Vue 3 的 scoped CSS 不会穿透到子组件内部元素。
  （父组件的 data-v-xxx 属性只加到子组件根元素 NCard 上）
-->
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
