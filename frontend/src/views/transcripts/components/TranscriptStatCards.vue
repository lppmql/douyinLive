<script setup lang="ts">
/**
 * 话术统计卡片
 *
 * 4 张概览卡片：片段数 / 总字数 / 时间覆盖率 / 平均 AI 评分。
 * 只有选中场次时才显示。
 */
defineOptions({ name: 'TranscriptStatCards' });

defineProps<{
  /** 是否显示（选中场次后为 true） */
  visible: boolean;
  /** 话术片段数 */
  segmentCount: number;
  /** 话术总字数 */
  totalCharacters: number;
  /** 时间覆盖率（%） */
  coveragePercent: number;
  /** 平均 AI 评分 */
  averageAiScore: number | null;
}>();
</script>

<template>
  <div v-if="visible" class="grid grid-cols-2 gap-12px lg:grid-cols-4">
    <NCard size="small" :bordered="false" class="card-wrapper">
      <NStatistic label="真实话术片段" :value="segmentCount" suffix="段" />
    </NCard>
    <NCard size="small" :bordered="false" class="card-wrapper">
      <NStatistic label="有效话术字数" :value="totalCharacters" suffix="字" />
    </NCard>
    <NCard size="small" :bordered="false" class="card-wrapper">
      <NStatistic label="时间覆盖率" :value="coveragePercent" :precision="1" suffix="%" />
    </NCard>
    <NCard size="small" :bordered="false" class="card-wrapper">
      <NStatistic label="平均 AI 评分" :value="averageAiScore ?? 0" :precision="1" suffix="分" />
    </NCard>
  </div>
</template>
