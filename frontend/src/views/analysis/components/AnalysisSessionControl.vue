<script setup lang="ts">
/**
 * 场次选择控制卡片
 *
 * 包含场次搜索下拉、主播信息展示、数据可信度标签、复盘启动面板。
 * 所有业务逻辑已在 composable 中处理，本组件只负责渲染。
 */

import AnchorIdentity from '@/components/business/anchor-identity.vue';
import SessionSelector from '@/components/business/session-selector.vue';
import type {
  AnchorSelectorOption,
  SessionDateRange,
  SessionSelectorOption
} from '@/adapters/session-selector-adapter';
import {
  readinessTagType,
  formatFullDateTime,
  formatDuration,
  actionStageLabel
} from '@/utils/analysisHelpers';

defineOptions({ name: 'AnalysisSessionControl' });

defineProps<{
  sessions: Api.Douyin.LiveSessionListItem[];
  selectedSessionId: number | null;
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  sessionOptions: SessionSelectorOption[];
  anchorOptions: AnchorSelectorOption[];
  anchorKey: string | null;
  dateRange: SessionDateRange;
  selectedSession: Api.Douyin.LiveSession | null;
  actionBusy: boolean;
  actionStage: string;
  latestReport: Api.Douyin.AnalysisReport | null;
  analysisReady: boolean;
  workbench: Api.Douyin.ReviewWorkbench | null;
}>();

defineEmits<{
  'update:selectedSessionId': [value: number | null];
  'update:anchorKey': [value: string | null];
  'update:dateRange': [value: SessionDateRange];
  searchSessions: [keyword: string];
  loadMoreSessions: [];
  resetFilters: [];
  runFullReview: [];
}>();

</script>

<template>
  <NCard :bordered="false" class="card-wrapper session-control-card">
    <div class="grid grid-cols-[minmax(0,1.45fr)_minmax(280px,0.65fr)] gap-20px lt-lg:grid-cols-1">
      <!-- 左侧：场次搜索 -->
      <div class="min-w-0">
        <div class="mb-8px flex items-center justify-between gap-12px">
          <div>
            <div class="text-15px font-700">选择复盘场次</div>
            <div class="mt-3px text-12px text-gray-500">默认打开最近开播的场次，可搜索切换历史场次</div>
          </div>
          <NTag v-if="sessions.length" round :bordered="false" type="info">{{ sessions.length }} 场可选</NTag>
        </div>
        <SessionSelector
          :model-value="selectedSessionId"
          :options="sessionOptions"
          :anchor-options="anchorOptions"
          :anchor-key="anchorKey"
          :date-range="dateRange"
          :loading="loading"
          :loading-more="loadingMore"
          :has-more="hasMore"
          @update:model-value="$emit('update:selectedSessionId', $event)"
          @update:anchor-key="$emit('update:anchorKey', $event)"
          @update:date-range="$emit('update:dateRange', $event)"
          @search="$emit('searchSessions', $event)"
          @load-more="$emit('loadMoreSessions')"
          @reset="$emit('resetFilters')"
        />
        <div v-if="selectedSession" class="mt-14px flex min-w-0 items-center gap-12px">
          <AnchorIdentity
            class="max-w-220px"
            :session-id="selectedSession.id"
            :avatar-url="selectedSession.anchor_avatar_url"
            :name="selectedSession.anchor_name"
            :nickname="selectedSession.anchor_nickname"
            :douyin-id="selectedSession.douyin_id"
            :size="42"
          />
          <div class="min-w-0 flex-1">
            <div class="truncate text-14px font-700">{{ selectedSession.session_title || '未命名直播场次' }}</div>
            <div class="mt-4px flex flex-wrap items-center gap-x-12px gap-y-4px text-12px text-gray-500">
              <span>{{ formatFullDateTime(selectedSession.live_start_time) }}</span>
              <span>{{ formatDuration(selectedSession.live_duration_seconds) }}</span>
            </div>
          </div>
          <div class="flex shrink-0 flex-wrap gap-8px lt-sm:hidden">
            <NTag
              :type="selectedSession.live_status === 'live' ? 'error' : 'default'"
              round
              size="small"
              :bordered="false"
            >
              {{ selectedSession.live_status === 'live' ? '直播中' : '已结束' }}
            </NTag>
            <NTag :type="readinessTagType(workbench?.completeness.score)" round size="small" :bordered="false">
              可信度 {{ workbench?.completeness.score || 0 }}%
            </NTag>
          </div>
        </div>
      </div>

      <!-- 右侧：启动面板 -->
      <div class="review-launch-panel">
        <div class="flex items-start gap-10px">
          <div class="size-38px flex-center shrink-0 rounded-11px bg-primary-100 text-primary dark:bg-primary-900/35">
            <SvgIcon icon="mdi:auto-fix" class="text-21px" />
          </div>
          <div>
            <div class="text-14px font-700">生成完整复盘</div>
            <div class="mt-3px text-12px leading-19px text-gray-500">一次生成用户意图、主播回应、钩子转化与下一场建议</div>
          </div>
        </div>
        <NTooltip :disabled="analysisReady || !selectedSessionId">
          <template #trigger>
            <span class="mt-14px block">
              <NButton
                type="primary"
                size="large"
                block
                :loading="actionBusy"
                :disabled="!selectedSessionId || !analysisReady || actionBusy"
                @click="$emit('runFullReview')"
              >
                {{ workbench?.unified_ai_review ? '重新生成完整复盘' : '开始完整复盘' }}
              </NButton>
            </span>
          </template>
          当前数据不足，请先补齐分钟指标、评论或 ASR 话术
        </NTooltip>
        <div class="mt-8px min-h-18px text-12px" :class="actionBusy ? 'text-primary' : 'text-gray-400'">
          {{
            actionStageLabel(actionStage) ||
              (latestReport ? `最近报告 ${formatFullDateTime(latestReport.created_at)}` : '尚未生成分析报告')
          }}
        </div>
      </div>
    </div>
  </NCard>
</template>

<style scoped>
.session-control-card {
  background: radial-gradient(circle at 92% 8%, rgba(37, 99, 235, 0.08), transparent 32%), var(--n-color);
}

.review-launch-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.7);
  padding: 15px;
}

:global(.dark) .review-launch-panel {
  background: rgba(255, 255, 255, 0.06);
}
</style>
