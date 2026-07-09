<script setup lang="ts">
import { ref, h } from 'vue';
import { NTag, NButton } from 'naive-ui';
import { $t } from '@/locales';

defineOptions({
  name: 'LiveSessions'
});

/* ---------- Mock 数据 ---------- */
interface LiveSession {
  id: number;
  date: string;
  anchorName: string;
  startTime: string;
  endTime: string;
  duration: number;
  onlineUsers: number;
  viewCount: number;
  totalLeads: number;
  validLeads: number;
  newFollowers: number;
  trafficSource: { label: string; value: number }[];
  conversion: { step: string; count: number }[];
}

const sessions = ref<LiveSession[]>([
  {
    id: 1,
    date: '2026-07-09',
    anchorName: '主播小明',
    startTime: '14:00',
    endTime: '17:30',
    duration: 210,
    onlineUsers: 1256,
    viewCount: 8320,
    totalLeads: 328,
    validLeads: 225,
    newFollowers: 156,
    trafficSource: [
      { label: $t('page.live-sessions.sourceFollow'), value: 35 },
      { label: $t('page.live-sessions.sourceRecommend'), value: 40 },
      { label: $t('page.live-sessions.sourceSearch'), value: 15 },
      { label: $t('page.live-sessions.sourceOther'), value: 10 }
    ],
    conversion: [
      { step: $t('page.live-sessions.stepView'), count: 8320 },
      { step: $t('page.live-sessions.stepInteraction'), count: 2140 },
      { step: $t('page.live-sessions.stepLead'), count: 328 },
      { step: $t('page.live-sessions.stepValid'), count: 225 }
    ]
  },
  {
    id: 2,
    date: '2026-07-08',
    anchorName: '主播小红',
    startTime: '19:00',
    endTime: '22:00',
    duration: 180,
    onlineUsers: 2100,
    viewCount: 15320,
    totalLeads: 512,
    validLeads: 380,
    newFollowers: 320,
    trafficSource: [
      { label: $t('page.live-sessions.sourceFollow'), value: 28 },
      { label: $t('page.live-sessions.sourceRecommend'), value: 48 },
      { label: $t('page.live-sessions.sourceSearch'), value: 14 },
      { label: $t('page.live-sessions.sourceOther'), value: 10 }
    ],
    conversion: [
      { step: $t('page.live-sessions.stepView'), count: 15320 },
      { step: $t('page.live-sessions.stepInteraction'), count: 3890 },
      { step: $t('page.live-sessions.stepLead'), count: 512 },
      { step: $t('page.live-sessions.stepValid'), count: 380 }
    ]
  },
  {
    id: 3,
    date: '2026-07-07',
    anchorName: '主播小明',
    startTime: '10:00',
    endTime: '12:45',
    duration: 165,
    onlineUsers: 980,
    viewCount: 6200,
    totalLeads: 210,
    validLeads: 142,
    newFollowers: 98,
    trafficSource: [
      { label: $t('page.live-sessions.sourceFollow'), value: 30 },
      { label: $t('page.live-sessions.sourceRecommend'), value: 42 },
      { label: $t('page.live-sessions.sourceSearch'), value: 18 },
      { label: $t('page.live-sessions.sourceOther'), value: 10 }
    ],
    conversion: [
      { step: $t('page.live-sessions.stepView'), count: 6200 },
      { step: $t('page.live-sessions.stepInteraction'), count: 1580 },
      { step: $t('page.live-sessions.stepLead'), count: 210 },
      { step: $t('page.live-sessions.stepValid'), count: 142 }
    ]
  }
]);

const showDrawer = ref(false);
const currentSession = ref<LiveSession | null>(null);

function openDetail(session: LiveSession) {
  currentSession.value = session;
  showDrawer.value = true;
}

/* ---------- 表格列 ---------- */
const columns = [
  { title: () => $t('page.live-sessions.date'), key: 'date', width: 110 },
  { title: () => $t('page.live-sessions.anchorName'), key: 'anchorName', width: 100 },
  { title: () => $t('page.live-sessions.startTime'), key: 'startTime', width: 90 },
  { title: () => $t('page.live-sessions.endTime'), key: 'endTime', width: 90 },
  {
    title: () => $t('page.live-sessions.duration'),
    key: 'duration',
    width: 80,
    render(row: LiveSession) {
      return `${row.duration}${$t('page.live-sessions.minutes')}`;
    }
  },
  { title: () => $t('page.live-sessions.onlineUsers'), key: 'onlineUsers', width: 100, sortable: true },
  { title: () => $t('page.live-sessions.totalLeads'), key: 'totalLeads', width: 90, sortable: true },
  {
    title: () => $t('page.live-sessions.validLeads'),
    key: 'validLeads',
    width: 100,
    sortable: true,
    render(row: LiveSession) {
      const rate = row.totalLeads > 0 ? ((row.validLeads / row.totalLeads) * 100).toFixed(1) : '0.0';
      return `${row.validLeads} (${rate}%)`;
    }
  },
  {
    title: () => $t('common.action'),
    key: 'actions',
    width: 80,
    render(row: LiveSession) {
      return h(
        NButton,
        { text: true, type: 'primary', onClick: () => openDetail(row) },
        { default: () => $t('common.detail') }
      );
    }
  }
];
</script>

<template>
  <NSpace vertical :size="16">
    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <NSpace>
          <SvgIcon icon="mdi:video-vintage" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('page.live-sessions.title') }}</span>
        </NSpace>
      </template>
      <NDataTable
        :columns="columns"
        :data="sessions"
        :bordered="false"
        :single-line="false"
        size="small"
        striped
      />
    </NCard>

    <!-- 详情抽屉 -->
    <NDrawer v-model:show="showDrawer" :width="480" placement="right">
      <NDrawerContent
        :title="`${$t('page.live-sessions.detailTitle')} - ${currentSession?.anchorName || ''}`"
        closable
      >
        <template v-if="currentSession">
          <NSpace vertical :size="20">
            <!-- 基础信息 -->
            <NCard :bordered="true" size="small" title="基础信息">
              <NDescriptions :column="2" size="small" bordered>
                <NDescriptionsItem :label="$t('page.live-sessions.date')">
                  {{ currentSession.date }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.anchorName')">
                  {{ currentSession.anchorName }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.startTime')">
                  {{ currentSession.startTime }}
                </NDescriptionsItem>
                <NDescriptionsItem :label="$t('page.live-sessions.endTime')">
                  {{ currentSession.endTime }}
                </NDescriptionsItem>
              </NDescriptions>
            </NCard>

            <!-- 流量来源 -->
            <NCard :bordered="true" size="small" :title="$t('page.live-sessions.trafficSource')">
              <NSpace vertical :size="12">
                <div
                  v-for="item in currentSession.trafficSource"
                  :key="item.label"
                  class="flex items-center gap-12px"
                >
                  <span class="w-60px text-13px text-gray-500">{{ item.label }}</span>
                  <NProgress
                    type="line"
                    :percentage="item.value"
                    :height="18"
                    :border-radius="4"
                    :fill-border-radius="4"
                    indicator-placement="inside"
                  />
                </div>
              </NSpace>
            </NCard>

            <!-- 转化漏斗 -->
            <NCard :bordered="true" size="small" :title="$t('page.live-sessions.conversion')">
              <div
                v-for="item in currentSession.conversion"
                :key="item.step"
                class="mb-8px flex items-center justify-between py-8px px-12px bg-gray-50 dark:bg-dark-300 rounded-8px"
              >
                <span class="text-13px">{{ item.step }}</span>
                <span class="text-14px font-bold text-primary">{{ item.count }}</span>
              </div>
            </NCard>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>
  </NSpace>
</template>

<style scoped></style>
