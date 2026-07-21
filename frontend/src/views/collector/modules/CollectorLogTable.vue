<!--
  采集日志表格 — 从 collector/index.vue 拆分
-->
<script setup lang="ts">
import { NButton, NCard, NDataTable, NTag, NRadioGroup, NRadioButton, NSpace } from 'naive-ui';
import { $t } from '@/locales';
import type { DataTableColumn } from 'naive-ui';

defineOptions({ name: 'CollectorLogTable' });

defineProps<{
  loading: boolean;
  silentRefreshing: boolean;
  clearLogsLoading: boolean;
  logs: Api.Douyin.CollectorLog[];
  logColumns: DataTableColumn<Api.Douyin.CollectorLog>[];
  logLevel: string;
  logTaskId: number | null;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'clear'): void;
  (e: 'filter', level: string): void;
  (e: 'clearTaskFilter'): void;
}>();

function getLogRowKey(row: Api.Douyin.CollectorLog) {
  return row.id;
}
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
