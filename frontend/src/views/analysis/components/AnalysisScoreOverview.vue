<script setup lang="ts">
/**
 * 复盘总览 Tab
 *
 * 展示五维话术评分、优缺点、下一场执行动作、直播节奏计划、合规提醒。
 * 这是复盘页面最复杂的子组件，拆分后约 200 行。
 */

import { scorePercent, scoreStatus } from '@/utils/analysisHelpers';

defineOptions({ name: 'AnalysisScoreOverview' });

defineProps<{
  scoreResult: Api.Douyin.AiScoreResult | null;
  optimizeResult: Api.Douyin.AiOptimizationResult | null;
  scoreMetrics: Array<{
    key: string;
    label: string;
    value: number;
    max: number;
    icon: string;
  }>;
  improvementSuggestions: string[];
  nextLivePlan: Array<{
    stage?: string;
    action?: string;
    success_metric?: string;
  }>;
  complianceNotes: string[];
  actionStage: string;
  actionBusy: boolean;
  analysisReady: boolean;
}>();

defineEmits<{
  runScore: [];
  runOptimize: [];
  runFullReview: [];
}>();
</script>

<template>
  <NSpace vertical :size="16">
    <template v-if="scoreResult">
      <!-- 评分标题栏 -->
      <div class="section-heading">
        <div>
          <div class="text-16px font-700">五维话术评分</div>
          <div class="mt-3px text-12px text-gray-500">综合分满分 50 分，单项分满分 10 分</div>
        </div>
        <div class="flex flex-wrap gap-8px">
          <NButton
            size="small"
            secondary
            :loading="actionStage === 'score-only'"
            :disabled="actionBusy"
            @click="$emit('runScore')"
          >
            重新评分
          </NButton>
          <NButton
            size="small"
            secondary
            :loading="actionStage === 'optimize-only'"
            :disabled="actionBusy"
            @click="$emit('runOptimize')"
          >
            更新建议
          </NButton>
        </div>
      </div>

      <!-- 五维评分指标 -->
      <NGrid :x-gap="12" :y-gap="12" cols="1 s:2 m:3 xl:6" responsive="screen">
        <NGi v-for="item in scoreMetrics" :key="item.key">
          <div class="score-metric">
            <div class="flex items-center justify-between gap-8px">
              <div class="size-32px flex-center rounded-9px bg-primary-50 text-primary dark:bg-primary-900/25">
                <SvgIcon :icon="item.icon" class="text-18px" />
              </div>
              <span class="text-11px text-gray-400">满分 {{ item.max }}</span>
            </div>
            <div class="mt-12px text-12px text-gray-500">{{ item.label }}</div>
            <div class="mt-2px flex items-end gap-4px">
              <span class="text-26px font-800 leading-32px">{{ item.value }}</span>
              <span class="mb-3px text-11px text-gray-400">/ {{ item.max }}</span>
            </div>
            <NProgress
              class="mt-8px"
              :percentage="scorePercent(item.value, item.max)"
              :height="5"
              :show-indicator="false"
              :status="scoreStatus(item.value, item.max)"
            />
          </div>
        </NGi>
      </NGrid>

      <!-- 优缺点双栏 -->
      <NGrid :x-gap="14" :y-gap="14" cols="1 l:2" responsive="screen">
        <NGi>
          <NCard :bordered="false" class="insight-panel strength-panel" size="small">
            <template #header>
              <div class="flex items-center gap-8px">
                <SvgIcon icon="mdi:check-decagram-outline" class="text-20px text-success" />
                <span>值得保留</span>
                <NTag size="small" round :bordered="false" type="success">
                  {{ scoreResult.strengths.length }}
                </NTag>
              </div>
            </template>
            <div v-if="scoreResult.strengths.length" class="space-y-8px">
              <div
                v-for="(item, index) in scoreResult.strengths"
                :key="`${index}-${item}`"
                class="insight-item"
              >
                <span class="insight-index success-index">{{ index + 1 }}</span>
                <span>{{ item }}</span>
              </div>
            </div>
            <NEmpty v-else description="暂无明确优势证据" class="py-24px" />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="insight-panel weakness-panel" size="small">
            <template #header>
              <div class="flex items-center gap-8px">
                <SvgIcon icon="mdi:alert-circle-outline" class="text-20px text-warning" />
                <span>优先改进</span>
                <NTag size="small" round :bordered="false" type="warning">
                  {{ scoreResult.weaknesses.length }}
                </NTag>
              </div>
            </template>
            <div v-if="scoreResult.weaknesses.length" class="space-y-8px">
              <div
                v-for="(item, index) in scoreResult.weaknesses"
                :key="`${index}-${item}`"
                class="insight-item"
              >
                <span class="insight-index warning-index">{{ index + 1 }}</span>
                <span>{{ item }}</span>
              </div>
            </div>
            <NEmpty v-else description="暂无明确问题证据" class="py-24px" />
          </NCard>
        </NGi>
      </NGrid>

      <!-- 下一场可执行动作 -->
      <NCard :bordered="false" class="action-plan-panel" size="small">
        <template #header>
          <div>
            <div class="text-15px font-700">下一场可执行动作</div>
            <div class="mt-3px text-12px font-400 text-gray-500">
              围绕开场留人、避坑知识、资料钩子和站内私信承接
            </div>
          </div>
        </template>
        <NAlert v-if="optimizeResult?.summary" type="info" :bordered="false" class="mb-12px">
          {{ optimizeResult.summary }}
        </NAlert>
        <div v-if="improvementSuggestions.length" class="grid grid-cols-1 gap-8px l:grid-cols-2">
          <div v-for="(item, index) in improvementSuggestions" :key="`${index}-${item}`" class="action-item">
            <span class="action-number">{{ String(index + 1).padStart(2, '0') }}</span>
            <span>{{ item }}</span>
          </div>
        </div>
        <NEmpty v-else description="尚未生成下一场优化建议" class="py-28px">
          <template #extra>
            <NButton size="small" type="primary" @click="$emit('runOptimize')">生成优化建议</NButton>
          </template>
        </NEmpty>
      </NCard>

      <!-- 下一场直播节奏 -->
      <NCard
        v-if="nextLivePlan.length"
        :bordered="false"
        class="next-live-panel"
        size="small"
        title="下一场直播节奏"
      >
        <div class="grid grid-cols-1 gap-8px m:grid-cols-2 xl:grid-cols-3">
          <div v-for="(item, index) in nextLivePlan" :key="`${item.stage}-${index}`" class="next-live-item">
            <div class="flex items-center justify-between gap-8px">
              <NTag size="small" round :bordered="false" type="info">
                {{ item.stage || `阶段 ${index + 1}` }}
              </NTag>
              <span class="text-11px text-gray-400">{{ index + 1 }}/{{ nextLivePlan.length }}</span>
            </div>
            <div class="mt-8px text-13px font-600 leading-21px">{{ item.action || '待补充执行动作' }}</div>
            <div class="mt-8px border-t border-gray-100 pt-8px text-12px text-gray-500 dark:border-white/8">
              验证：{{ item.success_metric || '下一场人工记录结果' }}
            </div>
          </div>
        </div>
      </NCard>

      <!-- 合规人工复核 -->
      <NAlert v-if="complianceNotes.length" type="warning" show-icon :bordered="false">
        <template #header>合规人工复核</template>
        <div v-for="(item, index) in complianceNotes" :key="`${index}-${item}`">
          {{ index + 1 }}. {{ item }}
        </div>
      </NAlert>
    </template>

    <!-- 无评分时的空状态 -->
    <NResult
      v-else
      status="info"
      title="这个场次还没有 AI 评分"
      description="系统不会用其他场次或模拟内容填充。确认数据可信度达到可分析标准后，再生成完整复盘。"
    >
      <template #footer>
        <NButton type="primary" :disabled="!analysisReady" :loading="actionBusy" @click="$emit('runFullReview')">
          开始完整复盘
        </NButton>
      </template>
    </NResult>
  </NSpace>
</template>

<style scoped>
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.score-metric {
  min-height: 146px;
  border: 1px solid var(--analysis-line);
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(248, 250, 252, 0.86), rgba(255, 255, 255, 0.55));
  padding: 13px;
}

.insight-panel,
.action-plan-panel,
.next-live-panel {
  border: 1px solid var(--analysis-line);
  border-radius: 12px;
}

.strength-panel {
  background: linear-gradient(145deg, rgba(16, 185, 129, 0.045), transparent 68%), var(--n-color);
}

.weakness-panel {
  background: linear-gradient(145deg, rgba(245, 158, 11, 0.055), transparent 68%), var(--n-color);
}

.insight-item,
.action-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-radius: 9px;
  background: rgba(248, 250, 252, 0.82);
  padding: 9px 10px;
  font-size: 13px;
  line-height: 21px;
}

.insight-index,
.action-number {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
}

.success-index {
  background: rgba(var(--success-color), 0.12);
  color: rgb(var(--success-color));
}

.warning-index {
  background: rgba(var(--warning-color), 0.13);
  color: rgb(var(--warning-color));
}

.action-number {
  background: rgba(var(--primary-color), 0.1);
  color: rgb(var(--primary-color));
}

.next-live-item {
  border: 1px solid var(--analysis-line);
  border-radius: 11px;
  background: rgba(248, 250, 252, 0.58);
  padding: 12px;
}

:global(.dark) .score-metric,
:global(.dark) .insight-item,
:global(.dark) .action-item,
:global(.dark) .next-live-item {
  background: rgba(255, 255, 255, 0.06);
}

@media (max-width: 640px) {
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
