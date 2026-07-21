<script setup lang="ts">
/**
 * 主播完成度卡片网格
 *
 * 展示每位排班主播的完成度卡片，包含：
 * - 头像、名称、直播间/网络信息
 * - 已完成场次 / 计划场次
 * - 缺场、无效、加场的摘要和 tooltip 明细
 * - 点击卡片可筛选下方班次表格
 */
import dayjs from 'dayjs';
import { NAvatar, NTag, NTooltip } from 'naive-ui';
import {
  getAnchorAvatarUrl,
  formatMissingSummary,
  formatMissingSessions,
  formatInvalidSummary,
  formatInvalidSessions,
  formatExtraSummary,
  formatExtraStartTimes
} from '@/utils/anchorScheduleHelpers';

defineOptions({ name: 'AnchorScheduleAnchorCards' });

defineProps<{
  /** 主播列表 */
  anchors: Api.Douyin.AnchorScheduleAnchor[];
  /** 当前选中的主播名（高亮对应卡片） */
  selectedAnchor: string | null;
}>();

defineEmits<{
  /** 点击主播卡片切换筛选 */
  toggleAnchor: [anchorName: string];
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper">
    <template #header>
      <div>
        <div class="text-16px font-700">主播完成度</div>
        <div class="mt-3px text-12px font-normal text-gray-400">点击主播卡片可筛选下方班次</div>
      </div>
    </template>
    <NGrid :x-gap="12" :y-gap="12" cols="1 s:2 l:3 xxl:5" responsive="screen">
      <NGi v-for="anchor in anchors" :key="anchor.source_anchor_name">
        <button
          type="button"
          class="anchor-card business-focus-ring business-active-press"
          :class="{ 'anchor-card-active': selectedAnchor === anchor.source_anchor_name }"
          :aria-pressed="selectedAnchor === anchor.source_anchor_name"
          @click="$emit('toggleAnchor', anchor.source_anchor_name)"
        >
          <!-- 头像 + 主播信息 -->
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
          <!-- 完成度数字 + 提醒标签 -->
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
          <!-- 缺场摘要 + tooltip 明细 -->
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
          <!-- 无效场次摘要 + tooltip 明细 -->
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
          <!-- 加场摘要 + tooltip 明细 -->
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
</template>

<style scoped>
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

:global(.dark) .anchor-card {
  background: linear-gradient(145deg, rgba(31, 41, 55, 0.94), rgba(17, 24, 39, 0.96));
}

@media (max-width: 640px) {
  .anchor-card {
    min-height: 178px;
  }
}
</style>
