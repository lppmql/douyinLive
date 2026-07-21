<script setup lang="ts">
/**
 * 主播排班页面 — 编排器
 *
 * 职责：组合子组件，不写业务逻辑。
 * 所有状态、计算属性、异步操作都在 useAnchorSchedule 中管理。
 */
import BusinessPageHeader from '@/components/business/page-header.vue';
import { useAnchorSchedule } from './composables/useAnchorSchedule';
import AnchorScheduleStatCards from './components/AnchorScheduleStatCards.vue';
import AnchorScheduleAnchorCards from './components/AnchorScheduleAnchorCards.vue';
import AnchorScheduleTable from './components/AnchorScheduleTable.vue';
import AnchorScheduleReminderDrawer from './components/AnchorScheduleReminderDrawer.vue';

defineOptions({ name: 'AnchorSchedule' });

// ── 从 composable 解构全部状态和操作 ──
// 注意：必须在 script setup 顶层解构，Vue 才会在模板中自动 unwrap ref
const as = useAnchorSchedule();

const {
  // 状态
  loading,
  loadError,
  dashboard,
  selectedRange,
  selectedAnchor,
  reminderDrawerVisible,
  // 计算属性
  selectedDateLabel,
  includesToday,
  visibleRows,
  columns,
  // 操作
  setDateOffset,
  setRecentDays,
  handleDateChange,
  toggleAnchor,
  openSession,
  loadSchedule
} = as;
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <!-- 页面头部：标题 + 日期控件 + 规则说明 -->
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

    <!-- 加载错误 -->
    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      排班核对数据未能更新：{{ loadError }}
      <NButton size="small" secondary :loading="loading" @click="loadSchedule()">重新加载</NButton>
    </NAlert>

    <!-- 提醒汇总横幅（有异常时显示） -->
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

    <!-- 1. KPI 统计卡片 -->
    <NSpin :show="loading">
      <AnchorScheduleStatCards
        :dashboard="dashboard"
        @open-reminder-drawer="reminderDrawerVisible = true"
      />
    </NSpin>

    <!-- 2. 主播完成度卡片 -->
    <AnchorScheduleAnchorCards
      :anchors="dashboard?.anchors || []"
      :selected-anchor="selectedAnchor"
      @toggle-anchor="toggleAnchor"
    />

    <!-- 3. 班次明细表格 -->
    <AnchorScheduleTable
      :columns="columns"
      :visible-rows="visibleRows"
      :loading="loading"
      :selected-date-label="selectedDateLabel"
      :selected-anchor="selectedAnchor"
      :includes-today="includesToday"
      @clear-anchor-filter="selectedAnchor = null"
    />

    <!-- 4. 提醒抽屉 -->
    <AnchorScheduleReminderDrawer
      :visible="reminderDrawerVisible"
      :reminders="dashboard?.reminders || []"
      @update:visible="reminderDrawerVisible = $event"
      @open-session="openSession"
    />
  </NSpace>
</template>
