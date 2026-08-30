<script setup lang="ts">
import { h } from 'vue';
import type { DataTableColumns } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';

defineOptions({ name: 'DashboardAnchorTable' });

defineProps<{ data: Api.Douyin.AnchorSummaryItem[] }>();

function number(value: number) {
  return Number(value || 0).toLocaleString('zh-CN');
}

function money(value: number) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

const columns: DataTableColumns<Api.Douyin.AnchorSummaryItem> = [
  {
    title: '主播',
    key: 'anchor_name',
    width: 190,
    fixed: 'left',
    render: row =>
      h(AnchorIdentity, {
        sessionId: row.anchor_avatar_session_id,
        avatarUrl: row.anchor_avatar_url,
        name: row.anchor_name,
        douyinId: row.douyin_id,
        size: 32
      })
  },
  { title: '场次', key: 'session_count', width: 70, align: 'right' },
  { title: '观看', key: 'total_viewers', width: 90, align: 'right', render: row => number(row.total_viewers) },
  { title: '评论', key: 'total_comments', width: 80, align: 'right', render: row => number(row.total_comments) },
  {
    title: '私信',
    key: 'total_private_messages',
    width: 80,
    align: 'right',
    render: row => number(row.total_private_messages)
  },
  { title: '留资', key: 'total_leads', width: 80, align: 'right', render: row => number(row.total_leads) },
  { title: '新增粉丝', key: 'total_new_followers', width: 90, align: 'right', render: row => number(row.total_new_followers) },
  { title: '广告消耗', key: 'total_ad_cost', width: 110, align: 'right', render: row => money(row.total_ad_cost) }
];
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="主播经营排行">
    <template #header-extra>
      <NTag size="small" type="info" :bordered="false">按确认留资优先排序</NTag>
    </template>
    <NDataTable
      v-if="data.length"
      :columns="columns"
      :data="data"
      :bordered="false"
      :single-line="false"
      :scroll-x="800"
      size="small"
      striped
    />
    <NEmpty v-else description="当前筛选范围暂无主播数据" class="py-60px" />
  </NCard>
</template>
