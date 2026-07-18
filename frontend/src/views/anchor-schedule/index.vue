<script setup lang="ts">
import { computed, h, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue';
import dayjs from 'dayjs';
import { NAvatar, NButton, NTag, useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import BusinessPageHeader from '@/components/business/page-header.vue';
import { fetchAnchorScheduleDashboard, getLiveSessionAvatarUrl } from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';

defineOptions({ name: 'AnchorSchedule' });

const router = useRouter();
const message = useMessage();
const loading = ref(false);
const dashboard = ref<Api.Douyin.AnchorScheduleDashboard | null>(null);
const todayTimestamp = dayjs().startOf('day').valueOf();
const selectedRange = ref<[number, number]>([todayTimestamp, todayTimestamp]);
const selectedAnchor = ref<string | null>(null);
const reminderDrawerVisible = ref(false);
const loadError = ref('');
let refreshTimer: ReturnType<typeof setInterval> | null = null;

const selectedStartDate = computed(() => dayjs(selectedRange.value[0]).format('YYYY-MM-DD'));
const selectedEndDate = computed(() => dayjs(selectedRange.value[1]).format('YYYY-MM-DD'));
const selectedDateLabel = computed(() =>
  selectedStartDate.value === selectedEndDate.value
    ? selectedStartDate.value
    : `${selectedStartDate.value} 至 ${selectedEndDate.value}`
);
const includesToday = computed(() => {
  const today = dayjs().format('YYYY-MM-DD');
  return selectedStartDate.value <= today && selectedEndDate.value >= today;
});
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
  duration_short: { label: '时长不足', type: 'warning' },
  invalid: { label: '无效场次', type: 'error' },
  extra: { label: '加场', type: 'info' }
};

function formatClock(value: string | null) {
  return value ? dayjs(value).format('HH:mm') : '-';
}

function formatDuration(seconds: number) {
  if (!seconds) return '0 分钟';
  const totalSeconds = Math.max(Math.floor(seconds), 0);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return remainingSeconds ? `${minutes} 分 ${remainingSeconds} 秒` : `${minutes} 分钟`;
}

function getAnchorAvatarUrl(anchor: Api.Douyin.AnchorScheduleAnchor | undefined) {
  return anchor?.anchor_avatar_session_id ? getLiveSessionAvatarUrl(anchor.anchor_avatar_session_id) : undefined;
}

function formatMissingSummary(anchor: Api.Douyin.AnchorScheduleAnchor) {
  if (!anchor.missing_count) return '缺场：无';
  const visibleDates = anchor.missing_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.missing_by_date.length - 2;
  return `缺场：${visibleDates}${remaining > 0 ? ` 等 ${anchor.missing_by_date.length} 天` : ''}`;
}

function formatMissingSessions(sessionIndexes: number[]) {
  return sessionIndexes.map(index => `第 ${index} 场`).join('、');
}

function formatInvalidSummary(anchor: Api.Douyin.AnchorScheduleAnchor) {
  if (!anchor.invalid_count) return '无效：无';
  const visibleDates = anchor.invalid_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.invalid_by_date.length - 2;
  return `无效：${visibleDates}${remaining > 0 ? ` 等 ${anchor.invalid_by_date.length} 天` : ''}`;
}

function formatInvalidSessions(item: Api.Douyin.AnchorScheduleAnchor['invalid_by_date'][number]) {
  return item.session_ids
    .map((_, index) => {
      const startTime = item.live_start_times[index];
      const extraLabel = item.extra_flags[index] ? '加场 · ' : '';
      return `${extraLabel}${startTime ? dayjs(startTime).format('HH:mm') : '时间未知'} · ${formatDuration(item.durations_seconds[index] || 0)}`;
    })
    .join('；');
}

function formatExtraSummary(anchor: Api.Douyin.AnchorScheduleAnchor) {
  if (!anchor.extra_count) return '加场：无';
  const visibleDates = anchor.extra_by_date
    .slice(0, 2)
    .map(item => `${dayjs(item.schedule_date).format('MM-DD')}（${item.count} 场）`)
    .join('、');
  const remaining = anchor.extra_by_date.length - 2;
  return `加场：${visibleDates}${remaining > 0 ? ` 等 ${anchor.extra_by_date.length} 天` : ''}`;
}

function formatExtraStartTimes(liveStartTimes: string[]) {
  return liveStartTimes.map(value => dayjs(value).format('HH:mm')).join('、');
}

function setDateOffset(offset: number) {
  const timestamp = dayjs().add(offset, 'day').startOf('day').valueOf();
  selectedRange.value = [timestamp, timestamp];
  selectedAnchor.value = null;
  void loadSchedule();
}

function setRecentDays(dayCount: number) {
  const endTimestamp = dayjs().startOf('day').valueOf();
  selectedRange.value = [
    dayjs(endTimestamp)
      .subtract(dayCount - 1, 'day')
      .valueOf(),
    endTimestamp
  ];
  selectedAnchor.value = null;
  void loadSchedule();
}

function handleDateChange(value: [number, number] | null) {
  if (value === null) return;
  if (dayjs(value[1]).diff(dayjs(value[0]), 'day') >= 31) {
    message.warning('单次最多查询连续 31 天，请缩短起止日期范围');
    return;
  }
  selectedRange.value = value;
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
    const response = await fetchAnchorScheduleDashboard(selectedStartDate.value, selectedEndDate.value);
    dashboard.value = unwrapServiceData(response, '排班数据加载失败，请检查后端服务和数据库迁移');
    loadError.value = '';
  } catch (error) {
    if (!silent) {
      loadError.value = error instanceof Error ? error.message : '排班数据加载失败，请检查后端服务和数据库迁移';
      message.error(loadError.value);
    }
  } finally {
    if (!silent) loading.value = false;
  }
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    if (includesToday.value && document.visibilityState === 'visible') void loadSchedule(true);
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
          h(
            NAvatar,
            { round: true, size: 36, src: avatarUrl },
            avatarUrl ? undefined : () => row.source_anchor_name[0]
          ),
          h('div', { class: 'min-w-0' }, [
            h('div', { class: 'truncate font-600' }, row.display_name),
            h('div', { class: 'truncate text-12px text-gray-400' }, anchor?.actual_anchor_name || '等待匹配真实账号')
          ])
        ]);
      }
    },
    {
      title: '日期',
      key: 'schedule_date',
      width: 112,
      render: row => dayjs(row.schedule_date).format('YYYY-MM-DD')
    },
    {
      title: '场次',
      key: 'session_index',
      width: 76,
      render: row => (row.is_extra ? `加场 ${row.extra_index}` : `第 ${row.session_index} 场`)
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
      render: row =>
        row.is_extra ? '计划外加场' : `${formatClock(row.planned_start_time)} - ${formatClock(row.planned_end_time)}`
    },
    {
      title: '标准时长',
      key: 'expected_duration_minutes',
      width: 90,
      render: row => (row.is_extra ? '-' : `${row.expected_duration_minutes} 分钟`)
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
        const label = row.is_extra && row.status === 'invalid' ? '无效加场' : info.label;
        return h(NTag, { type: info.type, size: 'small', round: true, bordered: false }, () => label);
      }
    },
    {
      title: '提醒',
      key: 'warnings',
      minWidth: 260,
      ellipsis: { tooltip: true },
      render(row) {
        if (row.is_extra && row.status !== 'invalid') {
          return h('span', { class: 'text-info' }, '超过当天规定场次，标记为加场');
        }
        if (!row.warnings.length) return row.status === 'upcoming' ? '等待计划时间' : '无异常';
        return h(
          'span',
          { class: ['missing', 'invalid'].includes(row.status) ? 'text-error' : 'text-warning' },
          row.warnings.join('；')
        );
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
onActivated(() => {
  if (!refreshTimer) {
    void loadSchedule(true);
    startAutoRefresh();
  }
});
onDeactivated(() => {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = null;
});
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <BusinessPageHeader
      title="主播排班"
      description="依据真实排班表核对每天的开播场次、有效时长和开播整点；提醒只使用已采集直播场次，不会用模拟数据补齐。"
      icon="mdi:calendar-clock-outline"
      :status="
        dashboard
          ? `${dashboard.source_name} · ${dashboard.day_count} 天 · ${dashboard.summary.planned_count} 场计划`
          : '正在读取排班'
      "
      :status-type="dashboard ? 'success' : 'info'"
    >
      <template #actions>
        <NButtonGroup>
          <NButton secondary @click="setDateOffset(-1)">昨天</NButton>
          <NButton secondary @click="setDateOffset(0)">今天</NButton>
          <NButton secondary @click="setRecentDays(7)">近 7 天</NButton>
        </NButtonGroup>
        <NDatePicker
          :value="selectedRange"
          type="daterange"
          :clearable="false"
          class="w-260px"
          @update:value="handleDateChange"
        />
        <NButton type="primary" :loading="loading" @click="loadSchedule()">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新核对
        </NButton>
      </template>
      <div class="flex flex-wrap items-center gap-x-18px gap-y-6px text-12px text-gray-500">
        <span>标准时长：{{ dashboard?.rule.expected_duration_minutes || 80 }} 分钟/场</span>
        <span>有效门槛：已结束场次至少 {{ dashboard?.rule.minimum_valid_duration_minutes || 45 }} 分钟</span>
        <span>文豪、大全：每天 4 场</span>
        <span>其他排班主播：每天 3 场</span>
        <span>
          跨整点：{{
            dashboard?.rule.cross_hour_definition || '实际开播须在计划时间所在自然小时内，提前或延后跨出均提醒'
          }}
        </span>
      </div>
    </BusinessPageHeader>

    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      排班核对数据未能更新：{{ loadError }}
      <template #action>
        <NButton size="small" secondary :loading="loading" @click="loadSchedule()">重新加载</NButton>
      </template>
    </NAlert>

    <NAlert
      v-if="dashboard?.summary.reminder_count"
      :type="dashboard.summary.invalid_count ? 'error' : 'warning'"
      :bordered="false"
      show-icon
      class="cursor-pointer"
      @click="reminderDrawerVisible = true"
    >
      {{ selectedDateLabel }} 共有 {{ dashboard.summary.reminder_count }} 条排班提醒：缺少
      {{ dashboard.summary.missing_count }} 场、无效 {{ dashboard.summary.invalid_count }} 场、时长不足
      {{ dashboard.summary.duration_short_count }} 场、跨整点开播
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
            <div class="mt-4px text-12px text-gray-400">5 位排班主播 · {{ dashboard?.day_count || 1 }} 天</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="schedule-kpi schedule-kpi-match" size="small">
            <div class="text-13px text-gray-500">已匹配真实场次</div>
            <div class="mt-8px text-30px font-700 text-success">{{ dashboard?.summary.matched_count || 0 }}</div>
            <div class="mt-4px text-12px text-gray-400">
              直播中 {{ dashboard?.summary.live_count || 0 }} 场 · 加场 {{ dashboard?.summary.extra_count || 0 }} 场 ·
              无效 {{ dashboard?.summary.invalid_count || 0 }} 场
            </div>
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
            class="business-clickable-card schedule-kpi schedule-kpi-alert"
            size="small"
            role="button"
            tabindex="0"
            aria-label="查看排班提醒明细"
            @click="reminderDrawerVisible = true"
            @keydown.enter="reminderDrawerVisible = true"
            @keydown.space.prevent="reminderDrawerVisible = true"
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
      <NGrid :x-gap="12" :y-gap="12" cols="1 s:2 l:3 xxl:5" responsive="screen">
        <NGi v-for="anchor in dashboard?.anchors || []" :key="anchor.source_anchor_name">
          <button
            type="button"
            class="anchor-card"
            :class="{ 'anchor-card-active': selectedAnchor === anchor.source_anchor_name }"
            :aria-pressed="selectedAnchor === anchor.source_anchor_name"
            @click="toggleAnchor(anchor.source_anchor_name)"
          >
            <div class="flex items-center gap-10px">
              <NAvatar v-if="getAnchorAvatarUrl(anchor)" round :size="40" :src="getAnchorAvatarUrl(anchor)" />
              <NAvatar v-else round :size="40">
                {{ anchor.source_anchor_name.slice(0, 1) }}
              </NAvatar>
              <div class="min-w-0 text-left">
                <div class="truncate text-14px font-700">{{ anchor.display_name }}</div>
                <div class="mt-2px truncate text-11px text-gray-400">
                  {{ anchor.room_name }} · {{ anchor.network_name }}
                </div>
              </div>
            </div>
            <div class="mt-13px flex items-end justify-between">
              <div>
                <span class="text-24px font-700">{{ anchor.matched_count }}</span>
                <span class="text-12px text-gray-400">/ {{ anchor.expected_count }} 场</span>
              </div>
              <NTag v-if="anchor.warning_count" type="warning" size="small" round :bordered="false">
                {{ anchor.warning_count }} 条提醒
              </NTag>
              <NTag v-else type="success" size="small" round :bordered="false">正常</NTag>
            </div>
            <NTooltip v-if="anchor.missing_count" placement="bottom" :delay="200">
              <template #trigger>
                <div class="mt-10px truncate text-left text-11px text-error">
                  {{ formatMissingSummary(anchor) }}
                </div>
              </template>
              <div class="max-h-240px overflow-y-auto py-2px">
                <div class="mb-6px font-600">缺少场次明细</div>
                <div v-for="item in anchor.missing_by_date" :key="item.schedule_date" class="py-2px text-12px">
                  {{ dayjs(item.schedule_date).format('YYYY-MM-DD') }}：缺 {{ item.count }} 场（{{
                    formatMissingSessions(item.session_indexes)
                  }}）
                </div>
              </div>
            </NTooltip>
            <div v-else class="mt-10px text-left text-11px text-success">缺场：无</div>
            <NTooltip v-if="anchor.invalid_count" placement="bottom" :delay="200">
              <template #trigger>
                <div class="mt-6px truncate text-left text-11px text-error">
                  {{ formatInvalidSummary(anchor) }}
                </div>
              </template>
              <div class="max-h-240px overflow-y-auto py-2px">
                <div class="mb-6px font-600">无效场次明细（不足 45 分钟）</div>
                <div v-for="item in anchor.invalid_by_date" :key="item.schedule_date" class="py-2px text-12px">
                  {{ dayjs(item.schedule_date).format('YYYY-MM-DD') }}：无效 {{ item.count }} 场（{{
                    formatInvalidSessions(item)
                  }}）
                </div>
              </div>
            </NTooltip>
            <div v-else class="mt-6px text-left text-11px text-success">无效：无</div>
            <NTooltip v-if="anchor.extra_count" placement="bottom" :delay="200">
              <template #trigger>
                <div class="mt-6px truncate text-left text-11px text-info">
                  {{ formatExtraSummary(anchor) }}
                </div>
              </template>
              <div class="max-h-240px overflow-y-auto py-2px">
                <div class="mb-6px font-600">加场明细</div>
                <div v-for="item in anchor.extra_by_date" :key="item.schedule_date" class="py-2px text-12px">
                  {{ dayjs(item.schedule_date).format('YYYY-MM-DD') }}：加 {{ item.count }} 场（开播
                  {{ formatExtraStartTimes(item.live_start_times) }}）
                </div>
              </div>
            </NTooltip>
            <div v-else class="mt-6px text-left text-11px text-gray-400">加场：无</div>
          </button>
        </NGi>
      </NGrid>
    </NCard>

    <NCard :bordered="false" class="card-wrapper">
      <template #header>
        <div class="flex flex-wrap items-center gap-10px">
          <span class="text-16px font-700">{{ selectedDateLabel }} 班次明细</span>
          <NTag v-if="selectedAnchor" round closable @close="selectedAnchor = null">
            {{ selectedAnchor }}
          </NTag>
        </div>
      </template>
      <template #header-extra>
        <span class="text-12px text-gray-400">
          {{ includesToday ? '范围包含今天，每 60 秒静默刷新' : '历史范围按需刷新' }}
        </span>
      </template>
      <div class="business-table-shell">
        <NDataTable
          :columns="columns"
          :data="visibleRows"
          :loading="loading"
          :row-key="row => `${row.schedule_date}-${row.id}`"
          :scroll-x="1560"
          :max-height="560"
          size="small"
          striped
        />
      </div>
    </NCard>

    <NDrawer v-model:show="reminderDrawerVisible" width="min(460px, 94vw)" placement="right">
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
                <SvgIcon
                  :icon="
                    item.type === 'missing'
                      ? 'mdi:calendar-alert'
                      : item.type === 'invalid'
                        ? 'mdi:close-octagon-outline'
                        : 'mdi:clock-alert-outline'
                  "
                />
              </div>
            </template>
            <div class="font-600">
              {{ item.anchor_name }} ·
              {{ item.is_extra ? `加场 ${item.session_index}` : `第 ${item.session_index} 场` }}
            </div>
            <div class="mt-4px text-13px text-gray-500">{{ item.message }}</div>
            <div class="mt-5px text-11px text-gray-400">
              {{ item.is_extra ? '实际开播' : '计划开播' }} {{ dayjs(item.schedule_date).format('MM-DD') }}
              {{ formatClock(item.planned_start_time) }}
            </div>
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
  min-height: 190px;
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
    min-height: 178px;
  }
}
</style>
