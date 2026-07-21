<script setup lang="ts">
/**
 * 排班统计卡片
 *
 * 展示 4 张 KPI 卡片：计划场次、已匹配真实场次、达标场次、待处理提醒。
 * 使用 NGrid 响应式布局：手机 1 列、小平板 2 列、桌面 4 列。
 */
defineOptions({ name: 'AnchorScheduleStatCards' });

defineProps<{
  /** 仪表盘数据（null 时显示 0） */
  dashboard: Api.Douyin.AnchorScheduleDashboard | null;
}>();

defineEmits<{
  /** 点击"待处理提醒"卡片时触发，打开提醒抽屉 */
  openReminderDrawer: [];
}>();
</script>

<template>
  <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
    <!-- 计划场次 -->
    <NGi>
      <NCard :bordered="false" class="schedule-kpi schedule-kpi-plan" size="small">
        <div class="text-13px text-gray-500">计划场次</div>
        <div class="mt-8px text-30px font-700">{{ dashboard?.summary.planned_count || 0 }}</div>
        <div class="mt-4px text-12px text-gray-400">5 位排班主播 · {{ dashboard?.day_count || 1 }} 天</div>
      </NCard>
    </NGi>
    <!-- 已匹配真实场次 -->
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
    <!-- 80 分钟达标 -->
    <NGi>
      <NCard :bordered="false" class="schedule-kpi schedule-kpi-duration" size="small">
        <div class="text-13px text-gray-500">80 分钟达标</div>
        <div class="mt-8px text-30px font-700">{{ dashboard?.summary.duration_compliant_count || 0 }}</div>
        <div class="mt-4px text-12px text-gray-400">已结束且时长达标</div>
      </NCard>
    </NGi>
    <!-- 待处理提醒（可点击） -->
    <NGi>
      <NCard
        :bordered="false"
        class="business-clickable-card schedule-kpi schedule-kpi-alert"
        size="small"
        role="button"
        tabindex="0"
        aria-label="查看排班提醒明细"
        @click="$emit('openReminderDrawer')"
        @keydown.enter="$emit('openReminderDrawer')"
        @keydown.space.prevent="$emit('openReminderDrawer')"
      >
        <div class="text-13px text-gray-500">待处理提醒</div>
        <div class="mt-8px text-30px font-700 text-warning">{{ dashboard?.summary.reminder_count || 0 }}</div>
        <div class="mt-4px text-12px text-gray-400">点击查看提醒明细</div>
      </NCard>
    </NGi>
  </NGrid>
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

:global(.dark) .schedule-kpi {
  background: linear-gradient(145deg, rgba(31, 41, 55, 0.94), rgba(17, 24, 39, 0.96));
}
</style>
