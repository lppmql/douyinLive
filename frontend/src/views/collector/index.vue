<script setup lang="ts">
import { ref, h } from 'vue';
import { NTag } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({
  name: 'Collector'
});

/* ---------- Mock 数据 ---------- */
const collectorStatus = ref({
  connected: true,
  connectTime: '2026-07-09 09:30:00',
  accountName: '采集账号_01'
});

const accounts = ref([
  { id: 1, name: '采集账号_01', douyinId: 'dy123456', status: 'valid', lastLogin: '2026-07-09 09:30' },
  { id: 2, name: '采集账号_02', douyinId: 'dy789012', status: 'expired', lastLogin: '2026-07-08 15:20' },
  { id: 3, name: '采集账号_03', douyinId: 'dy345678', status: 'valid', lastLogin: '2026-07-09 08:10' }
]);

const logs = ref([
  { id: 1, time: '2026-07-09 10:30:00', level: 'info', message: '开始采集直播场次数据' },
  { id: 2, time: '2026-07-09 10:30:05', level: 'info', message: '成功获取直播间信息' },
  { id: 3, time: '2026-07-09 10:31:00', level: 'warn', message: '评论接口响应超时，降级为 DOM 解析' },
  { id: 4, time: '2026-07-09 10:32:00', level: 'error', message: '直播间已结束，停止采集' },
  { id: 5, time: '2026-07-09 10:32:05', level: 'info', message: '采集任务完成，共采集 1,256 条数据' }
]);

/* ---------- 表格列 ---------- */
const accountColumns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: () => $t('page.collector.accountName'), key: 'name' },
  { title: () => $t('page.collector.douyinId'), key: 'douyinId' },
  {
    title: () => $t('page.collector.loginStatus'),
    key: 'status',
    render(row: { status: string }) {
      const type = row.status === 'valid' ? 'success' : 'error';
      const label = row.status === 'valid' ? $t('page.collector.statusValid') : $t('page.collector.statusExpired');
      return h(NTag, { type, size: 'small' }, { default: () => label });
    }
  },
  { title: () => $t('page.collector.lastLogin'), key: 'lastLogin' }
];

const logColumns = [
  { title: () => $t('page.collector.logTime'), key: 'time', width: 180 },
  {
    title: () => $t('page.collector.logLevel'),
    key: 'level',
    width: 80,
    render(row: { level: string }) {
      let type: 'success' | 'warning' | 'error' | 'info' = 'info';
      if (row.level === 'error') type = 'error';
      else if (row.level === 'warn') type = 'warning';
      return h(NTag, { type, size: 'small' }, { default: () => row.level.toUpperCase() });
    }
  },
  { title: () => $t('page.collector.logMessage'), key: 'message' }
];
</script>

<template>
  <NSpace vertical :size="16">
    <!-- 采集器状态 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace>
          <SvgIcon icon="mdi:cloud-upload" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('page.collector.statusTitle') }}</span>
        </NSpace>
      </template>
      <NSpace align="center" :size="24">
        <NTag :type="collectorStatus.connected ? 'success' : 'error'" round size="large">
          {{ collectorStatus.connected ? $t('page.collector.connected') : $t('page.collector.disconnected') }}
        </NTag>
        <span class="text-13px text-gray-500">
          {{ $t('page.collector.connectTime') }}：{{ collectorStatus.connectTime }}
        </span>
      </NSpace>
    </NCard>

    <!-- 账号列表 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <span class="text-15px font-bold">{{ $t('page.collector.accountList') }}</span>
      </template>
      <NDataTable
        :columns="accountColumns"
        :data="accounts"
        :bordered="false"
        :single-line="false"
        size="small"
      />
    </NCard>

    <!-- 采集日志 -->
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <span class="text-15px font-bold">{{ $t('page.collector.logTitle') }}</span>
      </template>
      <NDataTable
        :columns="logColumns"
        :data="logs"
        :bordered="false"
        :single-line="false"
        size="small"
      />
    </NCard>
  </NSpace>
</template>

<style scoped></style>
