<script setup lang="ts">
/**
 * 复盘统计卡片网格
 *
 * 显示 4 张指标卡片：综合评分、数据可信度、站内私信、场景线索
 * 纯展示组件，不包含任何业务逻辑
 */

defineOptions({ name: 'AnalysisStatCards' });

defineProps<{
  scoreResult: Api.Douyin.AiScoreResult | null;
  workbench: Api.Douyin.ReviewWorkbench | null;
  selectedSession: Api.Douyin.LiveSession | null;
  openFindingCount: number;
}>();

/** 数字加千分位逗号 */
function fmt(n: number): string {
  return new Intl.NumberFormat('zh-CN').format(n || 0);
}

/** 综合分 → 文字评级 */
function level(totalScore: number | undefined): string {
  if (typeof totalScore !== 'number') return '待生成';
  if (totalScore >= 40) return '表现优秀';
  if (totalScore >= 30) return '基础可用';
  if (totalScore >= 20) return '需要优化';
  return '优先整改';
}
</script>

<template>
  <NGrid v-if="selectedSession" :x-gap="14" :y-gap="14" cols="1 s:2 m:4" responsive="screen">
    <NGi>
      <NCard :bordered="false" class="card-wrapper metric-summary-card score-card" size="small">
        <div class="flex items-start justify-between gap-10px">
          <NStatistic label="综合评分" :value="scoreResult?.total_score ?? 0">
            <template #suffix><span class="text-13px text-gray-400">/ 50</span></template>
          </NStatistic>
          <SvgIcon icon="mdi:chart-areaspline" class="text-25px text-primary" />
        </div>
        <div class="mt-8px text-12px text-gray-500">{{ level(scoreResult?.total_score) }}</div>
      </NCard>
    </NGi>
    <NGi>
      <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
        <div class="flex items-start justify-between gap-10px">
          <NStatistic label="数据可信度" :value="workbench?.completeness.score || 0" :precision="1" suffix="%" />
          <SvgIcon icon="mdi:database-check-outline" class="text-25px text-success" />
        </div>
        <NProgress
          class="mt-8px"
          :percentage="workbench?.completeness.score || 0"
          :height="6"
          :show-indicator="false"
          :status="workbench?.completeness.score && workbench.completeness.score >= 85 ? 'success' : 'warning'"
        />
      </NCard>
    </NGi>
    <NGi>
      <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
        <div class="flex items-start justify-between gap-10px">
          <NStatistic label="站内私信" :value="fmt(selectedSession?.private_message_count ?? 0)" />
          <SvgIcon icon="mdi:message-text-outline" class="text-25px text-warning" />
        </div>
        <div class="mt-8px text-12px text-gray-500">评论 {{ fmt(selectedSession?.comments_count ?? 0) }} 条</div>
      </NCard>
    </NGi>
    <NGi>
      <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
        <div class="flex items-start justify-between gap-10px">
          <NStatistic label="场景线索" :value="fmt(selectedSession?.scene_leads_count ?? 0)" />
          <SvgIcon icon="mdi:account-arrow-right-outline" class="text-25px text-error" />
        </div>
        <div class="mt-8px text-12px text-gray-500">待处理发现 {{ openFindingCount }} 条</div>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped>
.metric-summary-card {
  min-height: 116px;
  border: 1px solid transparent;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease;
}

.metric-summary-card:hover {
  border-color: rgba(37, 99, 235, 0.2);
  transform: translateY(-1px);
}

.score-card {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.09), transparent 65%), var(--n-color);
}
</style>
