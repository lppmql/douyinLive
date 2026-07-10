<script setup lang="ts">
import { ref, h, onMounted } from 'vue';
import { NTag, NButton, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { fetchLiveSessionData, fetchLiveSessions } from '@/service/api/douyin';

defineOptions({
  name: 'LiveSessions'
});

const message = useMessage();

const loading = ref(true);
const sessions = ref<Api.Douyin.LiveSession[]>([]);

async function loadSessions() {
  loading.value = true;
  try {
    const res = await fetchLiveSessions();
    if (res.data) {
      sessions.value = res.data;
    }
  } catch {
    message.error('加载直播场次失败');
  } finally {
    loading.value = false;
  }
}

/* ---------- 状态标签映射 ---------- */
const statusMap: Record<string, { type: 'success' | 'warning' | 'info' | 'default'; labelKey: string }> = {
  live: { type: 'success', labelKey: 'page.live-sessions.statusLive' },
  scheduled: { type: 'info', labelKey: 'page.live-sessions.statusScheduled' },
  ended: { type: 'default', labelKey: 'page.live-sessions.statusEnded' },
  finished: { type: 'default', labelKey: 'page.live-sessions.statusEnded' },
};

function fmtPercent(val: number): string {
  if (val === 0) return '-';
  return `${(val * 100).toFixed(1)}%`;
}

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

/* ---------- 详情抽屉 ---------- */
const showDrawer = ref(false);
const currentSession = ref<Api.Douyin.LiveSession | null>(null);
const detailLoading = ref(false);
const detailData = ref<Api.Douyin.LiveSessionDetail | null>(null);

async function openDetail(session: Api.Douyin.LiveSession) {
  currentSession.value = session;
  showDrawer.value = true;
  detailLoading.value = true;
  detailData.value = null;
  try {
    const res = await fetchLiveSessionData(session.id);
    detailData.value = res.data || null;
  } catch {
    message.error('加载场次详细采集数据失败');
  } finally {
    detailLoading.value = false;
  }
}

function fmtNumber(val: number | null | undefined): string {
  return Number(val || 0).toLocaleString();
}

const metricColumns = [
  {
    title: '采集时间',
    key: 'metric_time',
    width: 120,
    render(row: Api.Douyin.LiveMetric) { return fmtDateTime(row.metric_time); }
  },
  { title: '在线', key: 'online_count', width: 70, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.online_count) },
  { title: '曝光', key: 'exposure_count', width: 80, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.exposure_count) },
  { title: '进入', key: 'enter_count', width: 80, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.enter_count) },
  { title: '点赞', key: 'like_count', width: 80, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.like_count) },
  { title: '评论', key: 'comment_count', width: 80, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.comment_count) },
  { title: '关注', key: 'follow_count', width: 80, render: (row: Api.Douyin.LiveMetric) => fmtNumber(row.follow_count) }
];

const commentColumns = [
  {
    title: '时间',
    key: 'comment_time',
    width: 115,
    render(row: Api.Douyin.LiveComment) { return fmtDateTime(row.comment_time); }
  },
  { title: '用户', key: 'user_nickname', width: 105, ellipsis: { tooltip: true } },
  { title: '评论内容', key: 'comment_content', ellipsis: { tooltip: true } }
];

/* ---------- 表格列 ---------- */
const columns = [
  {
    title: () => $t('page.live-sessions.anchorName'),
    key: 'anchor_name',
    width: 100,
    ellipsis: { tooltip: true }
  },
  {
    title: () => $t('page.live-sessions.sessionTitle'),
    key: 'session_title',
    width: 140,
    ellipsis: { tooltip: true },
    render(row: Api.Douyin.LiveSession) {
      return row.session_title || '-';
    }
  },
  {
    title: () => $t('page.live-sessions.sessionStatus'),
    key: 'live_status',
    width: 80,
    render(row: Api.Douyin.LiveSession) {
      const info = statusMap[row.live_status] || { type: 'default' as const, labelKey: 'page.live-sessions.statusEnded' as const };
      return h(NTag, { type: info.type as any, size: 'small', round: true }, { default: () => $t(info.labelKey as any) });
    }
  },
  {
    title: () => $t('page.live-sessions.startTime'),
    key: 'live_start_time',
    width: 110,
    render(row: Api.Douyin.LiveSession) { return fmtDateTime(row.live_start_time); }
  },
  {
    title: () => $t('page.live-sessions.endTime'),
    key: 'live_end_time',
    width: 110,
    render(row: Api.Douyin.LiveSession) { return fmtDateTime(row.live_end_time); }
  },
  {
    title: () => $t('page.live-sessions.duration'),
    key: 'live_duration_seconds',
    width: 80,
    render(row: Api.Douyin.LiveSession) { return fmtSeconds(row.live_duration_seconds); }
  },
  {
    title: () => $t('page.live-sessions.onlineUsers'),
    key: 'peak_online_count',
    width: 90,
    sortable: true,
    render(row: Api.Douyin.LiveSession) { return row.peak_online_count || 0; }
  },
  {
    title: () => $t('page.live-sessions.newFollowers'),
    key: 'new_followers',
    width: 90,
    render(row: Api.Douyin.LiveSession) { return row.new_followers || 0; }
  },
  {
    title: () => $t('page.live-sessions.commentsCount'),
    key: 'comments_count',
    width: 80,
    render(row: Api.Douyin.LiveSession) { return row.comments_count || 0; }
  },
  {
    title: () => $t('page.live-sessions.leads'),
    key: 'leads_count',
    width: 80,
    sortable: true,
    render(row: Api.Douyin.LiveSession) { return row.leads_count || 0; }
  },
  {
    title: () => $t('common.action'),
    key: 'actions',
    width: 80,
    render(row: Api.Douyin.LiveSession) {
      return h(
        NButton,
        { text: true, type: 'primary', size: 'tiny', onClick: () => openDetail(row) },
        { default: () => $t('page.live-sessions.detail') }
      );
    }
  }
];

onMounted(() => {
  loadSessions();
});
</script>

<template>
  <NSpace vertical :size="16">
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace justify="space-between" align="center">
          <NSpace>
            <SvgIcon icon="mdi:video-vintage" class="text-22px" />
            <span class="text-16px font-bold">{{ $t('page.live-sessions.title') }}</span>
          </NSpace>
          <NButton size="small" secondary @click="loadSessions">
            <template #icon>
              <SvgIcon icon="mdi:refresh" />
            </template>
            {{ $t('page.live-sessions.refresh') }}
          </NButton>
        </NSpace>
      </template>

      <div v-if="loading" class="flex justify-center py-40px">
        <NSpin :stroke-width="12" :size="24" />
        <span class="ml-12px text-gray-400">{{ $t('page.live-sessions.loading') }}</span>
      </div>

      <NDataTable
        v-else
        :columns="columns"
        :data="sessions"
        :bordered="false"
        :single-line="false"
        size="small"
        striped
        :empty-text="$t('page.live-sessions.noData')"
      />
    </NCard>

    <!-- 详情抽屉 -->
    <NDrawer v-model:show="showDrawer" :width="720" placement="right">
      <NDrawerContent
        :title="`${$t('page.live-sessions.detailTitle')} - ${currentSession?.anchor_name || ''}`"
        closable
      >
        <template v-if="currentSession">
          <NSpace vertical :size="16">
            <!-- 基本信息 -->
            <NCard :bordered="true" size="small" :title="$t('page.live-sessions.basicInfo')">
              <NDescriptions :column="2" size="small" bordered>
                <NDescriptionsItem :label="$t('page.live-sessions.anchorName')">
                  {{ currentSession.anchor_name }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.sessionTitle')">
                  {{ currentSession.session_title || '-' }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.sessionStatus')">
                  <NTag
                    :type="(statusMap[currentSession.live_status] || { type: 'default' }).type as any"
                    size="small"
                    round
                  >
                    {{ $t(((statusMap[currentSession.live_status] || { type: 'default', labelKey: 'page.live-sessions.statusEnded' }).labelKey) as any) }}
                  </NTag>
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('common.detail')">
                  <a
                    v-if="currentSession.dashboard_url"
                    :href="currentSession.dashboard_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-primary"
                  >{{ $t('page.live-sessions.dashboardLink') }}</a>
                  <span v-else>-</span>
                </NDescriptionsItem>
              </NDescriptions>
            </NCard>

            <!-- 时间信息 -->
            <NCard :bordered="true" size="small" :title="$t('page.live-sessions.timeInfo')">
              <NDescriptions :column="2" size="small" bordered>
                <NDescriptionsItem :label="$t('page.live-sessions.startTime')">
                  {{ fmtDateTime(currentSession.live_start_time) }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.endTime')">
                  {{ fmtDateTime(currentSession.live_end_time) }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.duration')">
                  {{ fmtSeconds(currentSession.live_duration_seconds) }}
                </NDescriptionsItem>
              </NDescriptions>
            </NCard>

            <!-- 核心指标 -->
            <NCard :bordered="true" size="small" :title="$t('page.live-sessions.coreMetrics')">
              <NDescriptions :column="2" size="small" bordered>
                <NDescriptionsItem :label="$t('page.live-sessions.viewCount')">
                  {{ currentSession.total_viewers || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.onlineUsers')">
                  {{ currentSession.peak_online_count || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.newFollowers')">
                  {{ currentSession.new_followers || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.commentsCount')">
                  {{ currentSession.comments_count || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.leads')">
                  {{ currentSession.leads_count || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.adCost')">
                  {{ currentSession.ad_cost || 0 }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.exposureEnterRate')">
                  {{ fmtPercent(currentSession.exposure_enter_rate) }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.commentRate')">
                  {{ fmtPercent(currentSession.comment_rate) }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.interactionRate')">
                  {{ fmtPercent(currentSession.interaction_rate) }}
                </NDescriptionsItem>
              </NDescriptions>
            </NCard>

            <NCard :bordered="true" size="small" title="直播流信息（用于后续话术采集）">
              <NDescriptions :column="1" size="small" bordered>
                <NDescriptionsItem label="可用流地址">
                  <a
                    v-if="detailData?.stream_url"
                    :href="detailData.stream_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="block max-w-580px truncate text-primary"
                    :title="detailData.stream_url"
                  >{{ detailData.stream_url }}</a>
                  <span v-else>本场暂未采集到可用直播流</span>
                </NDescriptionsItem>
                <NDescriptionsItem label="已保存流源版本">
                  {{ detailData?.stream_source_count || 0 }}
                </NDescriptionsItem>
              </NDescriptions>
            </NCard>

            <NCard :bordered="true" size="small" title="大屏分钟趋势数据">
              <template #header-extra>
                <span class="text-12px text-gray-400">{{ detailData?.metrics.length || 0 }} 条</span>
              </template>
              <NSpin v-if="detailLoading" size="small" />
              <NEmpty v-else-if="!detailData?.metrics.length" size="small" description="本场暂无分钟趋势数据" />
              <NDataTable
                v-else
                :columns="metricColumns"
                :data="detailData.metrics"
                :max-height="320"
                :pagination="{ pageSize: 20 }"
                :bordered="false"
                size="small"
              />
            </NCard>

            <NCard :bordered="true" size="small" title="本场直播评论">
              <template #header-extra>
                <span class="text-12px text-gray-400">已展示 {{ detailData?.comments.length || 0 }} 条</span>
              </template>
              <NSpin v-if="detailLoading" size="small" />
              <NEmpty v-else-if="!detailData?.comments.length" size="small" description="本场暂无已采集评论" />
              <NDataTable
                v-else
                :columns="commentColumns"
                :data="detailData.comments"
                :max-height="360"
                :pagination="{ pageSize: 20 }"
                :bordered="false"
                size="small"
              />
            </NCard>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </NSpace>
</template>

<style scoped></style>
