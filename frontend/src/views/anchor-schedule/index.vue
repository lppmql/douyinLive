<script setup lang="ts">
import { computed, h, onActivated, onBeforeUnmount, onMounted, ref } from 'vue';
import dayjs from 'dayjs';
import { NAvatar, NButton, NTag, useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import BusinessPageHeader from '@/components/business/page-header.vue';
import { fetchAnchorScheduleDashboard, getLiveSessionAvatarUrl } from '@/service/api/douyin';

defineOptions({ name: 'AnchorSchedule' });

const router = useRouter();
const message = useMessage();
const loading = ref(false);
const dashboard = ref<Api.Douyin.AnchorScheduleDashboard | null>(null);
const selectedTimestamp = ref(dayjs().startOf('day').valueOf());
const selectedAnchor = ref<string | null>(null);
const reminderDrawerVisible = ref(false);
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const selectedDate = computed(() => dayjs(selectedTimestamp.value).format('YYYY-MM-DD'));
const isToday = computed(() => selectedDate.value === dayjs().format('YYYY-MM-DD'));
const visibleRows = computed(() => {
  if (!selectedAnchor.value) return dashboard.value?.rows || [];
  return (dashboard.value?.rows || []).filter(item => item.source_anchor_name === selectedAnchor.value);
});

const statusMap: Record<
  Api.Douyin.AnchorScheduleStatus,
  { label: string; type: 'success' | 'warning' | 'error' | 'info' | 'default' }
> = {
  upcoming: { label: '未到时间', type: 'info' },
  live: { label: '直播中', type: 'success' },
  completed: { label: '已达标', type: 'success' },
  missing: { label: '缺少场次', type: 'error' },
  duration_short: { label: '时长不足', type: 'warning' }
};

function formatClock(value: string | null) {
  return value ? dayjs(value).format('HH:mm') : '-';
}

function formatDuration(seconds: number) {
  if (!seconds) return '0 分钟';
  return `${Math.round(seconds / 60)} 分钟`;
}

function getAnchorAvatarUrl(anchor: Api.Douyin.AnchorScheduleAnchor | undefined) {
  return anchor?.anchor_avatar_session_id ? getLiveSessionAvatarUrl(anchor.anchor_avatar_session_id) : undefined;
}

function setDateOffset(offset: number) {
  selectedTimestamp.value = dayjs().add(offset, 'day').startOf('day').valueOf();
  void loadSchedule();
}

function handleDateChange(value: number | null) {
  if (value === null) return;
  selectedTimestamp.value = value;
  selectedAnchor.value = null;
  void loadSchedule();
}

function toggleAnchor(anchorName: string) {
  selectedAnchor.value = selectedAnchor.value === anchorName ? null : anchorName;
}

function openSession(sessionId: number | null) {
  if (!sessionId) return;
  router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
}

async function loadSchedule(silent = false) {
  if (!silent) loading.value = true;
  try {
    const response = await fetchAnchorScheduleDashboard(selectedDate.value);
    if (response.data) dashboard.value = response.data;
  } catch {
    if (!silent) message.error('排班数据加载失败，请检查后端服务和数据库迁移');
  } finally {
    if (!silent) loading.value = false;
  }
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (isToday.value && document.visibilityState === 'visible') void loadSchedule(true);
  }, 60_000);
}

function createColumns(): NaiveUI.TableColumn<Api.Douyin.AnchorScheduleRow>[] {
  return [
    {
      title: '主播',
      key: 'display_name',
      width: 210,
      fixed: 'left',
      render(row) {
        const anchor = dashboard.value?.anchors.find(item => item.source_anchor_name === row.source_anchor_name);
        const avatarUrl = getAnchorAvatarUrl(anchor);
        return h('div', { class: 'flex items-center gap-10px' }, [
          h(NAvatar, { round: true, size: 36, src: avatarUrl }, avatarUrl ? undefined : () => row.source_anchor_name[0]),
          h('div', { class: 'min-w-0' }, [
            h('div', { class: 'truncate font-600' }, row.display_name),
            h('div', { class: 'truncate text-12px text-gray-400' }, anchor?.actual_anchor_name || '等待匹配真实账号')
          ])
        ]);
      }
    },
    {
      title: '场次',
      key: 'session_index',
      width: 76,
      render: row => `第 ${row.session_index} 场`
    },
    {
      title: '直播间 / 网络',
      key: 'room_name',
      width: 165,
      render(row) {
        return h('div', [
          h('div', { class: 'font-500' }, row.room_name),
          h('div', { class: 'text-12px text-gray-400' }, row.network_name || '-')
        ]);
      }
    },
    {
      title: '计划时间',
      key: 'planned_start_time',
      width: 135,
      render: row => `${formatClock(row.planned_start_time)} - ${formatClock(row.planned_end_time)}`
    },
    {
      title: '标准时长',
      key: 'expected_duration_minutes',
      width: 90,
      render: row => `${row.expected_duration_minutes} 分钟`
    },
    {
      title: '实际开播',
      key: 'actual_start',
      width: 105,
      render: row => formatClock(row.actual_session?.live_start_time || null)
    },
    {
      title: '实际时长',
      key: 'actual_duration',
      width: 100,
      render: row => (row.actual_session ? formatDuration(row.actual_session.live_duration_seconds) : '-')
    },
    {
      title: '执行状态',
      key: 'status',
      width: 100,
      render(row) {
        const info = statusMap[row.status];
        return h(NTag, { type: info.type, size: 'small', round: true, bordered: false }, () => info.label);
      }
    },
    {
      title: '提醒',
      key: 'warnings',
      minWidth: 260,
      ellipsis: { tooltip: true },
      render(row) {
        if (!row.warnings.length) return row.status === 'upcoming' ? '等待计划时间' : '无异常';
        return h('span', { class: row.status === 'missing' ? 'text-error' : 'text-warning' }, row.warnings.join('；'));
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render(row) {
        return h(
          NButton,
          {
            text: true,
            type: 'primary',
            size: 'small',
            disabled: !row.actual_session,
            onClick: () => openSession(row.actual_session?.id || null)
          },
          () => '查看场次'
        );
      }
    }
  ];
}

const columns = createColumns();

onMounted(() => {
  void loadSchedule();
  startAutoRefresh();
});
onActivated(() => void loadSchedule(true));
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <NSpace vertical :size="16">
    <BusinessPageHeader
      title="主播排班"
      description="依据真实排班表核对每天的开播场次、80 分钟时长和开播整点；提醒只使用已采集直播场次，不会用模拟数据补齐。"
      icon="mdi:calendar-clock-outline"
      :status="dashboard ? `${dashboard.source_name} · ${dashboard.summary.planned_count} 场计划` : '正在读取排班'"
      :status-type="dashboard ? 'success' : 'info'"
    >
      <template #actions>
        <NButton secondary @click="setDateOffset(-1)">昨天</NButton>
        <NButton secondary @click="setDateOffset(0)">今天</NButton>
        <NDatePicker
          :value="selectedTimestamp"
          type="date"
          :clearable="false"
          class="w-150px"
          @update:value="handleDateChange"
        />
        <NButton type="primary" :loading="loading" @click="loadSchedule()">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新核对
        </NButton>
      </template>
      <div class="flex flex-wrap items-center gap-x-18px gap-y-6px text-12px text-gray-500">
        <span>标准时长：{{ dashboard?.rule.expected_duration_minutes || 80 }} 分钟/场</span>
        <span>文豪、大全：每天 4 场</span>
        <span>其他排班主播：每天 3 场</span>
        <span>
          跨整点：{{
            dashboard?.rule.cross_hour_definition || '实际开播须在计划时间所在自然小时内，提前或延后跨出均提醒'
          }}
        </span>
      </div>
    </BusinessPageHeader>

    <NAlert
      v-if="dashboard?.summary.reminder_count"
      type="warning"
      :bordered="false"
      show-icon
      class="cursor-pointer"
      @click="reminderDrawerVisible = true"
    >
      {{ selectedDate }} 共有 {{ dashboard.summary.reminder_count }} 条排班提醒：缺少
      {{ dashboard.summary.missing_count }} 场、时长不足 {{ dashboard.summary.duration_short_count }} 场、跨整点开播
      {{ dashboard.summary.cross_hour_count }} 场。点击查看明细。
    </NAlert>
    <NAlert v-else-if="dashboard" type="success" :bordered="false" show-icon>
      当前已到期班次没有发现异常；未来班次不会提前提示缺场。
    </NAlert>

    <NSpin :show="loading">
      <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
        <NGi>
          <NCard :bordered="false" class="schedule-kpi schedule-kpi-plan" size="small">
            <div class="text-13px text-gray-500">计划场次</div>
            <div class="mt-8px text-30px font-700">{{ dashboard?.summary.planned_count || 0 }}</div>
            <div class="mt-4px text-12px text-gray-400">5 位排班主播</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="schedule-kpi schedule-kpi-match" size="small">
            <div class="text-13px text-gray-500">已匹配真实场次</div>
            <div class="mt-8px text-30px font-700 text-success">{{ dashboard?.summary.matched_count || 0 }}</div>
            <div class="mt-4px text-12px text-gray-400">直播中 {{ dashboard?.summary.live_count || 0 }} 场</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="schedule-kpi schedule-kpi-duration" size="small">
            <div class="text-13px text-gray-500">80 分钟达标</div>
            <div class="mt-8px text-30px font-700">{{ dashboard?.summary.duration_compliant_count || 0 }}</div>
            <div class="mt-4px text-12px text-gray-400">已结束且时长达标</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard
            :bordered="false"
            class="schedule-kpi schedule-kpi-alert cursor-pointer"
            size="small"
            @click="reminderDrawerVisible = true"
          >
            <div class="text-13px text-gray-500">待处理提醒</div>
            <div class="mt-8px text-30px font-700 text-warning">{{ dashboard?.summary.reminder_count || 0 }}</div>
            <div class="mt-4px text-12px text-gray-400">点击查看提醒明细</div>
          </NCard>
        </NGi>
      </NGrid>
    </NSpin>

    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <div>
          <div class="text-16px font-700">主播完成度</div>
          <div class="mt-3px text-12px font-normal text-gray-400">点击主播卡片可筛选下方班次</div>
        </div>
      </template>
      <NGrid :x-gap="12" :y-gap="12" cols="1 s:2 m:5" responsive="screen">
        <NGi v-for="anchor in dashboard?.anchors || []" :key="anchor.source_anchor_name">
          <button
            type="button"
            class="anchor-card"
            :class="{ 'anchor-card-active': selectedAnchor === anchor.source_anchor_name }"
            @click="toggleAnchor(anchor.source_anchor_name)"
          >
            <div class="flex items-center gap-10px">
              <NAvatar v-if="getAnchorAvatarUrl(anchor)" round :size="40" :src="getAnchorAvatarUrl(anchor)" />
              <NAvatar v-else round :size="40">
                {{ anchor.source_anchor_name.slice(0, 1) }}
              </NAvatar>
              <div class="min-w-0 text-left">
                <div class="truncate text-14px font-700">{{ anchor.display_name }}</div>
                <div class="mt-2px truncate text-11px text-gray-400">{{ anchor.room_name }} · {{ anchor.network_name }}</div>
              </div>
            </div>
            <div class="mt-13px flex items-end justify-between">
              <div>
                <span class="text-24px font-700">{{ anchor.matched_count }}</span>
                <span class="text-12px text-gray-400"> / {{ anchor.expected_count }} 场</span>
              </div>
              <NTag v-if="anchor.warning_count" type="warning" size="small" round :bordered="false">
                {{ anchor.warning_count }} 条提醒
              </NTag>
              <NTag v-else type="success" size="small" round :bordered="false">正常</NTag>
            </div>
          </button>
        </NGi>
      </NGrid>
    </NCard>

    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <div class="flex flex-wrap items-center gap-10px">
          <span class="text-16px font-700">{{ selectedDate }} 班次明细</span>
          <NTag v-if="selectedAnchor" round closable @close="selectedAnchor = null">
            {{ selectedAnchor }}
          </NTag>
        </div>
      </template>
      <template #header-extra>
        <span class="text-12px text-gray-400">今天每 60 秒静默刷新</span>
      </template>
      <NDataTable
        :columns="columns"
        :data="visibleRows"
        :loading="loading"
        :row-key="row => row.id"
        :scroll-x="1450"
        :max-height="560"
        size="small"
        striped
      />
    </NCard>

    <NDrawer v-model:show="reminderDrawerVisible" :width="460" placement="right">
      <NDrawerContent title="排班提醒" closable>
        <NEmpty v-if="!dashboard?.reminders.length" description="当前没有已到期异常" />
        <NList v-else hoverable clickable>
          <NListItem
            v-for="(item, index) in dashboard.reminders"
            :key="`${item.anchor_name}-${item.session_index}-${index}`"
            @click="openSession(item.session_id)"
          >
            <template #prefix>
              <div
                class="size-36px flex-center rounded-10px"
                :class="item.severity === 'error' ? 'bg-error-50 text-error' : 'bg-warning-50 text-warning'"
              >
                <SvgIcon :icon="item.type === 'missing' ? 'mdi:calendar-alert' : 'mdi:clock-alert-outline'" />
              </div>
            </template>
            <div class="font-600">{{ item.anchor_name }} · 第 {{ item.session_index }} 场</div>
            <div class="mt-4px text-13px text-gray-500">{{ item.message }}</div>
            <div class="mt-5px text-11px text-gray-400">计划开播 {{ formatClock(item.planned_start_time) }}</div>
          </NListItem>
        </NList>
      </NDrawerContent>
    </NDrawer>
  </NSpace>
</template>

<style scoped>
.schedule-kpi {
  min-height: 116px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.9));
}

.schedule-kpi-plan {
  box-shadow: inset 4px 0 #2563eb;
}

.schedule-kpi-match {
  box-shadow: inset 4px 0 #16a34a;
}

.schedule-kpi-duration {
  box-shadow: inset 4px 0 #0f766e;
}

.schedule-kpi-alert {
  box-shadow: inset 4px 0 #f59e0b;
}

.anchor-card {
  width: 100%;
  min-height: 126px;
  padding: 14px;
  color: inherit;
  cursor: pointer;
  background: linear-gradient(150deg, rgba(248, 250, 252, 0.8), rgba(255, 255, 255, 0.98));
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  transition:
    border-color 180ms ease,
    transform 180ms ease,
    box-shadow 180ms ease;
}

.anchor-card:hover,
.anchor-card-active {
  border-color: rgba(37, 99, 235, 0.55);
  box-shadow: 0 10px 28px rgba(30, 64, 175, 0.1);
  transform: translateY(-2px);
}

:global(.dark) .schedule-kpi,
:global(.dark) .anchor-card {
  background: linear-gradient(145deg, rgba(31, 41, 55, 0.94), rgba(17, 24, 39, 0.96));
}

@media (max-width: 640px) {
  .anchor-card {
    min-height: 112px;
  }
}
</style>
