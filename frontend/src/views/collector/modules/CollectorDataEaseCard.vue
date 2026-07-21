<!--
  DataEase 分析数据集卡片 — 从 collector/index.vue 拆分
  显示宽表同步覆盖情况，支持手动触发同步
-->
<script setup lang="ts">
import { NCard, NGi, NGrid, NButton, NTag, NProgress, NStatistic, NSpace } from 'naive-ui';
import { formatFullTime } from '../utils/collectorHelpers';

defineOptions({ name: 'CollectorDataEaseCard' });

defineProps<{
  /** DataEase 同步覆盖状态 */
  dataEaseStatus: Api.Douyin.DataEaseStatus | null;
  /** 同步操作加载中 */
  dataEaseSyncLoading: boolean;
}>();

const emit = defineEmits<{
  /** 触发增量同步 */
  (e: 'sync'): void;
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="DataEase 分析数据集">
    <template #header-extra>
      <NTag :type="dataEaseStatus?.pending_session_count ? 'warning' : 'success'" round size="small">
        {{
          dataEaseStatus?.pending_session_count
            ? `待同步 ${dataEaseStatus.pending_session_count} 场`
            : '数据已同步'
        }}
      </NTag>
    </template>
    <div class="flex flex-col gap-14px">
      <!-- 6 项统计指标 -->
      <NGrid cols="2 s:3 l:6" responsive="screen" :x-gap="12" :y-gap="12">
        <NGi><NStatistic label="完整场次" :value="dataEaseStatus?.source_session_count || 0" /></NGi>
        <NGi><NStatistic label="已同步场次" :value="dataEaseStatus?.synced_session_count || 0" /></NGi>
        <NGi><NStatistic label="分钟指标" :value="dataEaseStatus?.metric_row_count || 0" /></NGi>
        <NGi><NStatistic label="观众画像" :value="dataEaseStatus?.profile_row_count || 0" /></NGi>
        <NGi><NStatistic label="评论汇总" :value="dataEaseStatus?.comment_summary_count || 0" /></NGi>
        <NGi><NStatistic label="AI 汇总" :value="dataEaseStatus?.ai_summary_count || 0" /></NGi>
      </NGrid>
      <!-- 同步覆盖率进度条 -->
      <NProgress
        type="line"
        :percentage="dataEaseStatus?.coverage_rate || 0"
        :status="dataEaseStatus?.pending_session_count ? 'warning' : 'success'"
        indicator-placement="inside"
      />
      <div class="flex flex-wrap items-center justify-between gap-12px">
        <span class="text-12px text-gray-500">
          最后同步：{{ formatFullTime(dataEaseStatus?.last_synced_at || null) }}；DataEase 只读 MySQL 的 de_* 宽表。
        </span>
        <NSpace>
          <NButton
            size="small"
            type="primary"
            :loading="dataEaseSyncLoading"
            :disabled="!dataEaseStatus?.pending_session_count"
            @click="emit('sync')"
          >
            同步待更新数据
          </NButton>
          <NButton
            tag="a"
            href="http://localhost:8100"
            target="_blank"
            rel="noopener noreferrer"
            size="small"
            secondary
          >
            打开 DataEase
          </NButton>
        </NSpace>
      </div>
    </div>
  </NCard>
</template>
