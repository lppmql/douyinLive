<script setup lang="ts">
import { h } from 'vue';
import type { DataTableColumns } from 'naive-ui';
import { NButton } from 'naive-ui';
import { useRouterPush } from '@/hooks/common/router';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import { formatDuration, formatShortDateTime } from '@/utils/analysisHelpers';

defineOptions({ name: 'DashboardSessionTable' });

defineProps<{ data: Api.Douyin.DashboardSessionItem[] }>();

const { routerPushByKey } = useRouterPush(false);

function number(value: number) {
  return Number(value || 0).toLocaleString('zh-CN');
}

function money(value: number) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

const columns: DataTableColumns<Api.Douyin.DashboardSessionItem> = [
  {
    title: '主播',
    key: 'anchor_name',
    width: 180,
    fixed: 'left',
    render: row =>
      h(AnchorIdentity, {
        sessionId: row.id,
        avatarUrl: row.anchor_avatar_url,
        name: row.anchor_name,
        douyinId: row.douyin_id,
        size: 30,
        dense: true
      })
  },
  {
    title: '开播时间',
    key: 'live_start_time',
    width: 140,
    render: row => formatShortDateTime(row.live_start_time)
  },
  { title: '时长', key: 'live_duration_seconds', width: 90, render: row => formatDuration(row.live_duration_seconds) },
  { title: '观看', key: 'total_viewers', width: 90, align: 'right', render: row => number(row.total_viewers) },
  { title: '评论', key: 'total_comments', width: 80, align: 'right', render: row => number(row.total_comments) },
  { title: '私信', key: 'total_private_messages', width: 80, align: 'right', render: row => number(row.total_private_messages) },
  { title: '留资', key: 'total_leads', width: 80, align: 'right', render: row => number(row.total_leads) },
  { title: '线索成本', key: 'lead_cost', width: 105, align: 'right', render: row => money(row.lead_cost) },
  {
    title: '操作',
    key: 'actions',
    width: 90,
    fixed: 'right',
    render: row =>
      h(
        NButton,
        {
          size: 'small',
          text: true,
          type: 'primary',
          onClick: () => routerPushByKey('live-session-detail', { params: { id: String(row.id) } })
        },
        { default: () => '查看复盘' }
      )
  }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="最近场次经营明细">
    <template #header-extra>
      <NTag size="small" :bordered="false">最多显示 30 场</NTag>
    </template>
    <NDataTable
      v-if="data.length"
      :columns="columns"
      :data="data"
      :row-key="row => row.id"
      :bordered="false"
      :single-line="false"
      :scroll-x="1050"
      size="small"
      striped
    />
    <NEmpty v-else description="当前筛选范围暂无场次数据" class="py-60px" />
  </NCard>
</template>
