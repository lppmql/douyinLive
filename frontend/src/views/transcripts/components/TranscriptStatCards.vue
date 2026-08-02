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
  /** 时间覆盖展示；时长未知时显示真实转写位置 */
  coverageLabel: string;
  /** 平均 AI 评分 */
  averageAiScore: number | null;
  /** 当前话术版本 */
  contentVersionLabel: string;
  /** 页面隐藏的实时重复短片段数量 */
  hiddenDuplicateCount: number;
}>();
</script>

<template>
  <NCard v-if="visible" size="small" :bordered="false" class="card-wrapper">
    <NGrid :x-gap="16" :y-gap="14" cols="2 m:4" responsive="screen">
      <NGi>
        <NStatistic label="可读话术片段" :value="segmentCount" suffix="段" />
        <div v-if="hiddenDuplicateCount" class="mt-3px text-11px text-gray-400">
          已隐藏 {{ hiddenDuplicateCount }} 个实时重复短片段
        </div>
      </NGi>
      <NGi><NStatistic label="有效话术字数" :value="totalCharacters" suffix="字" /></NGi>
      <NGi>
        <NStatistic label="话术覆盖" :value="coverageLabel" />
        <div class="mt-3px text-11px text-gray-400">{{ contentVersionLabel }}</div>
      </NGi>
      <NGi>
        <NStatistic label="平均 AI 评分" :value="averageAiScore == null ? '待分析' : averageAiScore.toFixed(1)" />
        <div class="mt-3px text-11px text-gray-400">
          {{ averageAiScore == null ? '完成离线终稿后生成复盘' : '基于当前已评分片段' }}
        </div>
      </NGi>
    </NGrid>
  </NCard>
</template>
