<script setup lang="ts">
import { h, reactive } from 'vue';
import { NTag, NButton, NAvatar } from 'naive-ui';
import { useRouter } from 'vue-router';
import { $t } from '@/locales';
import { fetchLiveSessionPage } from '@/service/api/douyin';
import { defaultTransform, useNaivePaginatedTable } from '@/hooks/common/table';
import TableHeaderOperation from '@/components/advanced/table-header-operation.vue';
import BusinessPageHeader from '@/components/business/page-header.vue';

defineOptions({
  name: 'LiveSessions'
});

const router = useRouter();

const searchForm = reactive({
  anchorName: '',
  liveStatus: null as string | null,
  detailStatus: null as string | null
});
const searchParams = reactive({
  current: 1,
  size: 10,
  anchor_name: undefined as string | undefined,
  live_status: undefined as string | undefined,
  detail_status: undefined as string | undefined
});

/* ---------- 状态标签映射 ---------- */
const statusMap: Record<string, { type: 'success' | 'warning' | 'info' | 'default'; labelKey: string }> = {
  live: { type: 'success', labelKey: 'page.live-sessions.statusLive' },
  scheduled: { type: 'info', labelKey: 'page.live-sessions.statusScheduled' },
  ended: { type: 'default', labelKey: 'page.live-sessions.statusEnded' },
  finished: { type: 'default', labelKey: 'page.live-sessions.statusEnded' }
};

function fmtSeconds(val: number): string {
  if (!val) return '-';
  const hh = Math.floor(val / 3600);
  const mm = Math.floor((val % 3600) / 60);
  if (hh > 0) {
    return `${hh}${$t('page.live-sessions.hours')}${mm}${$t('page.live-sessions.minutes')}`;
  }
  return `${mm}${$t('page.live-sessions.minutes')}`;
}

function fmtDateTime(val: string | null): string {
  if (!val) return '-';
  const d = new Date(val);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

const detailStatusMap: Record<string, { type: 'success' | 'warning' | 'info' | 'error'; label: string }> = {
  complete: { type: 'success', label: '详情完整' },
  retryable: { type: 'warning', label: '待重试' },
  unavailable: { type: 'error', label: '平台不可回放' },
  pending: { type: 'info', label: '待采集' }
};

function renderDetailStatus(row: Api.Douyin.LiveSessionListItem) {
  const info = detailStatusMap[row.detail_collection_status] || detailStatusMap.pending;
  return h(
    NTag,
    {
      type: info.type,
      size: 'small',
      round: true,
      bordered: false,
      title: row.detail_collection_error || undefined
    },
    { default: () => info.label }
  );
}

function openDetail(session: Api.Douyin.LiveSessionListItem) {
  router.push({ name: 'live-session-detail', params: { id: String(session.id) } });
}

function displayCollectedNumber(row: Api.Douyin.LiveSessionListItem, value: number): number | string {
  return value || (row.detail_collection_status === 'complete' ? 0 : '-');
}

/* ---------- 表格列 ---------- */
function createColumns(): NaiveUI.TableColumn<Api.Douyin.LiveSessionListItem>[] {
  return [
    {
      title: () => $t('page.live-sessions.anchorName'),
      key: 'anchor_name',
      width: 220,
      fixed: 'left',
      render(row: Api.Douyin.LiveSessionListItem) {
        return h('div', { class: 'flex items-center gap-8px min-w-0' }, [
          h(
            NAvatar,
            {
              round: true,
              size: 34,
              src: row.anchor_avatar_url || undefined,
              objectFit: 'cover',
              renderFallback: () => row.anchor_name?.slice(0, 1) || '主'
            }
          ),
          h('div', { class: 'min-w-0' }, [
            h('div', { class: 'truncate font-600' }, row.anchor_name || '-'),
            h('div', { class: 'truncate text-12px text-gray-400' }, row.douyin_id || row.anchor_nickname || '-')
          ])
        ]);
      }
    },
    {
      title: () => $t('page.live-sessions.sessionTitle'),
      key: 'session_title',
      width: 140,
      ellipsis: { tooltip: true },
      render(row: Api.Douyin.LiveSessionListItem) {
        return row.session_title || '-';
      }
    },
    {
      title: () => $t('page.live-sessions.sessionStatus'),
      key: 'live_status',
      width: 80,
      render(row: Api.Douyin.LiveSessionListItem) {
        const info = statusMap[row.live_status] || {
          type: 'default' as const,
          labelKey: 'page.live-sessions.statusEnded' as const
        };
        return h(
          NTag,
          { type: info.type as any, size: 'small', round: true },
          { default: () => $t(info.labelKey as any) }
        );
      }
    },
    {
      title: '详情采集',
      key: 'detail_collection_status',
      width: 105,
      render(row: Api.Douyin.LiveSessionListItem) {
        return renderDetailStatus(row);
      }
    },
    {
      title: () => $t('page.live-sessions.startTime'),
      key: 'live_start_time',
      width: 110,
      render(row: Api.Douyin.LiveSessionListItem) {
        return fmtDateTime(row.live_start_time);
      }
    },
    {
      title: () => $t('page.live-sessions.endTime'),
      key: 'live_end_time',
      width: 110,
      render(row: Api.Douyin.LiveSessionListItem) {
        return fmtDateTime(row.live_end_time);
      }
    },
    {
      title: () => $t('page.live-sessions.duration'),
      key: 'live_duration_seconds',
      width: 80,
      render(row: Api.Douyin.LiveSessionListItem) {
        return fmtSeconds(row.live_duration_seconds);
      }
    },
    {
      title: () => $t('page.live-sessions.onlineUsers'),
      key: 'peak_online_count',
      width: 90,
      render(row: Api.Douyin.LiveSessionListItem) {
        return displayCollectedNumber(row, row.peak_online_count);
      }
    },
    {
      title: () => $t('page.live-sessions.newFollowers'),
      key: 'new_followers',
      width: 90,
      render(row: Api.Douyin.LiveSessionListItem) {
        return displayCollectedNumber(row, row.new_followers);
      }
    },
    {
      title: () => $t('page.live-sessions.commentsCount'),
      key: 'comments_count',
      width: 80,
      render(row: Api.Douyin.LiveSessionListItem) {
        return displayCollectedNumber(row, row.comments_count);
      }
    },
    {
      title: () => $t('page.live-sessions.leads'),
      key: 'leads_count',
      width: 80,
      render(row: Api.Douyin.LiveSessionListItem) {
        return displayCollectedNumber(row, row.leads_count);
      }
    },
    {
      title: () => $t('common.action'),
      key: 'actions',
      width: 80,
      fixed: 'right',
      render(row: Api.Douyin.LiveSessionListItem) {
        return h(NButton, { text: true, type: 'primary', size: 'tiny', onClick: () => openDetail(row) }, () => '详情');
      }
    }
  ];
}

const {
  loading,
  data: sessions,
  columns,
  columnChecks,
  mobilePagination,
  scrollX,
  getData,
  getDataByPage
} = useNaivePaginatedTable({
  api: () => fetchLiveSessionPage(searchParams),
  transform: response => defaultTransform(response),
  onPaginationParamsChange: ({ page, pageSize }) => {
    searchParams.current = page || 1;
    searchParams.size = pageSize || 10;
  },
  defaultPageSize: 10,
  paginationProps: { pageSizes: [10, 20, 50, 100] },
  columns: createColumns
});

async function handleSearch() {
  searchParams.anchor_name = searchForm.anchorName.trim() || undefined;
  searchParams.live_status = searchForm.liveStatus || undefined;
  searchParams.detail_status = searchForm.detailStatus || undefined;
  await getDataByPage(1);
}

async function handleReset() {
  searchForm.anchorName = '';
  searchForm.liveStatus = null;
  searchForm.detailStatus = null;
  searchParams.anchor_name = undefined;
  searchParams.live_status = undefined;
  searchParams.detail_status = undefined;
  await getDataByPage(1);
}
</script>

<template>
  <NSpace vertical :size="16">
    <BusinessPageHeader
      title="直播场次"
      description="查询全部真实直播记录，优先处理“待采集/待重试”的场次；表格中的短横线表示尚未采到，0 表示平台返回的真实零值。"
      icon="mdi:video-vintage"
      :status="`数据库共 ${mobilePagination.itemCount || 0} 场`"
      status-type="info"
    >
      <template #actions>
        <NButton type="primary" @click="router.push({ name: 'collector' })">
          <template #icon><SvgIcon icon="mdi:database-sync-outline" /></template>
          去补齐数据
        </NButton>
      </template>
      <div class="flex flex-wrap gap-x-18px gap-y-6px text-12px text-gray-500">
        <span>主播列与操作列固定</span>
        <span>默认每页 10 场</span>
        <span>表格内可上下、左右滚动</span>
      </div>
    </BusinessPageHeader>

    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <div class="flex flex-wrap items-center justify-between gap-12px">
          <NSpace align="center">
            <SvgIcon icon="mdi:video-vintage" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.live-sessions.title') }}</span>
          </NSpace>
          <NTag type="info" round :bordered="false">共 {{ mobilePagination.itemCount || 0 }} 场</NTag>
        </div>
      </template>

      <NAlert class="mb-14px" type="info" :bordered="false" show-icon>
        建议先筛选“详情待采集”或“待重试”。详情完整后，评论、分钟趋势和 AI 分析才具备可靠的数据基础。
      </NAlert>

      <div class="mb-16px flex flex-wrap items-center justify-between gap-12px">
        <NSpace wrap>
          <NInput
            v-model:value="searchForm.anchorName"
            clearable
            placeholder="搜索主播昵称"
            class="w-200px lt-sm:w-full"
            @keyup.enter="handleSearch"
          />
          <NSelect
            v-model:value="searchForm.liveStatus"
            clearable
            placeholder="直播状态"
            class="w-140px"
            :options="[
              { label: '直播中', value: 'live' },
              { label: '已结束', value: 'finished' },
              { label: '待直播', value: 'scheduled' }
            ]"
          />
          <NSelect
            v-model:value="searchForm.detailStatus"
            clearable
            placeholder="详情状态"
            class="w-140px"
            :options="[
              { label: '详情完整', value: 'complete' },
              { label: '待采集', value: 'pending' },
              { label: '待重试', value: 'retryable' },
              { label: '不可回放', value: 'unavailable' }
            ]"
          />
          <NButton type="primary" @click="handleSearch">查询</NButton>
          <NButton @click="handleReset">重置</NButton>
        </NSpace>
        <TableHeaderOperation
          v-model:columns="columnChecks"
          :loading="loading"
          :show-crud-actions="false"
          @refresh="getData"
        />
      </div>

      <NDataTable
        :loading="loading"
        :columns="columns"
        :data="sessions"
        :pagination="mobilePagination"
        :scroll-x="scrollX"
        :max-height="460"
        :row-key="row => row.id"
        :bordered="false"
        :single-line="false"
        :empty-text="$t('page.live-sessions.noData')"
        remote
        size="small"
        striped
      />
    </NCard>
  </NSpace>
</template>

<style scoped></style>
