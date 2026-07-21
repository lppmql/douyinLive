<script setup lang="ts">
/**
 * 证据与发现 Tab
 *
 * 展示：
 * 1. 避坑知识/转化链路领域覆盖情况
 * 2. 结构化复盘发现卡片（重点风险 / 需要关注 / 运营观察）
 * 3. AI 评分引用的话术证据
 */

import { findingTagType, findingLabel } from '@/utils/analysisHelpers';

defineOptions({ name: 'AnalysisEvidence' });

defineProps<{
  workbench: Api.Douyin.ReviewWorkbench | null;
  scoreResult: Api.Douyin.AiScoreResult | null;
  coveredDomainCount: number;
  analysisReady: boolean;
  actionBusy: boolean;
}>();

defineEmits<{
  runFullReview: [];
}>();
</script>

<template>
  <NSpace vertical :size="16">
    <!-- 避坑知识覆盖 -->
    <NCard :bordered="false" class="evidence-coverage-panel" size="small">
      <div class="section-heading">
        <div>
          <div class="text-15px font-700">避坑知识与转化链路覆盖</div>
          <div class="mt-3px text-12px text-gray-500">根据真实 ASR 话术关键词统计，不根据标题猜测</div>
        </div>
        <NTag round :bordered="false" :type="coveredDomainCount >= 6 ? 'success' : 'warning'">
          已覆盖 {{ coveredDomainCount }}/{{ workbench?.domain_coverage.length || 0 }}
        </NTag>
      </div>
      <div class="mt-14px flex flex-wrap gap-8px">
        <NTooltip v-for="item in workbench?.domain_coverage || []" :key="item.category">
          <template #trigger>
            <NTag :type="item.covered ? 'success' : 'default'" round :bordered="false">
              {{ item.category }} · {{ item.segment_count }} 段
            </NTag>
          </template>
          {{
            item.covered
              ? `首次出现于 ${Math.round(item.first_seconds || 0)} 秒`
              : '真实话术中暂未识别到该主题'
          }}
        </NTooltip>
      </div>
    </NCard>

    <!-- 复盘发现卡片 -->
    <div v-if="workbench?.findings.length" class="grid grid-cols-1 gap-10px l:grid-cols-2">
      <div v-for="item in workbench.findings" :key="item.id" class="finding-card">
        <div class="flex items-start justify-between gap-12px">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-8px">
              <NTag size="small" round :bordered="false" :type="findingTagType(item.severity)">
                {{ findingLabel(item.severity) }}
              </NTag>
              <span class="text-12px text-gray-400">{{ item.category }}</span>
            </div>
            <div class="mt-8px text-14px font-700 leading-22px">{{ item.title }}</div>
          </div>
          <span v-if="item.start_seconds !== null" class="shrink-0 font-mono text-11px text-primary">
            {{ Math.floor(item.start_seconds / 60) }}:{{
              String(Math.floor(item.start_seconds % 60)).padStart(2, '0')
            }}
          </span>
        </div>
        <p v-if="item.description" class="mb-0 mt-8px text-12px leading-20px text-gray-500">
          {{ item.description }}
        </p>
        <div
          v-if="item.evidence_text"
          class="mt-8px rounded-8px bg-gray-50 px-10px py-8px text-12px leading-20px dark:bg-dark-300"
        >
          {{ item.evidence_text }}
        </div>
      </div>
    </div>
    <NEmpty v-else description="尚未生成结构化复盘发现" class="py-42px">
      <template #extra>
        <NButton type="primary" :disabled="!analysisReady" :loading="actionBusy" @click="$emit('runFullReview')">
          提取证据并生成复盘
        </NButton>
      </template>
    </NEmpty>

    <!-- AI 评分引用的话术证据 -->
    <NCard v-if="scoreResult?.evidence?.length" :bordered="false" size="small" title="AI 评分引用的话术证据">
      <div class="grid grid-cols-1 gap-8px l:grid-cols-2">
        <div
          v-for="(item, index) in scoreResult.evidence"
          :key="`${item.start_seconds}-${index}`"
          class="quote-card"
        >
          <div class="flex items-center justify-between gap-8px">
            <NTag size="small" round :bordered="false" type="info">{{ item.category }}</NTag>
            <span v-if="item.start_seconds !== null" class="font-mono text-11px text-gray-400">
              {{ Math.round(item.start_seconds) }} 秒
            </span>
          </div>
          <div class="mt-8px text-12px leading-20px">"{{ item.quote }}"</div>
        </div>
      </div>
    </NCard>
  </NSpace>
</template>

<style scoped>
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.evidence-coverage-panel {
  border: 1px solid var(--analysis-line);
  border-radius: 12px;
}

.finding-card,
.quote-card {
  border: 1px solid var(--analysis-line);
  border-radius: 11px;
  background: rgba(248, 250, 252, 0.58);
  padding: 12px;
}

:global(.dark) .finding-card,
:global(.dark) .quote-card {
  background: rgba(255, 255, 255, 0.06);
}

@media (max-width: 640px) {
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
