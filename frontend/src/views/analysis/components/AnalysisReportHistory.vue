<script setup lang="ts">
/**
 * 历史报告列表
 *
 * 显示当前场次已保存的所有 AI 分析报告（话术评分 / 优化建议 / 异常检测 / 趋势分析）
 */

import { reportTypeMeta, reportSummary, formatFullDateTime } from '@/utils/analysisHelpers';

defineOptions({ name: 'AnalysisReportHistory' });

defineProps<{
  sessionReports: Api.Douyin.AnalysisReport[];
}>();
</script>

<template>
  <NList v-if="sessionReports.length" hoverable clickable class="report-list">
    <NListItem v-for="report in sessionReports" :key="report.id">
      <NThing
        :title="report.report_title || reportTypeMeta(report.report_type).label"
        :description="reportSummary(report)"
      >
        <template #avatar>
          <div class="size-38px flex-center rounded-10px bg-primary-50 text-primary dark:bg-primary-900/25">
            <SvgIcon :icon="reportTypeMeta(report.report_type).icon" class="text-20px" />
          </div>
        </template>
        <template #header-extra>
          <div class="flex items-center gap-8px">
            <NTag size="small" round :bordered="false" :type="reportTypeMeta(report.report_type).tag">
              {{ reportTypeMeta(report.report_type).label }}
            </NTag>
            <span class="text-11px text-gray-400">{{ formatFullDateTime(report.created_at) }}</span>
          </div>
        </template>
      </NThing>
    </NListItem>
  </NList>
  <NEmpty v-else description="当前场次还没有保存的分析报告" class="py-50px" />
</template>

<style scoped>
.report-list {
  border-radius: 12px;
  overflow: hidden;
}
</style>
