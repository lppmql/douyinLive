<script setup lang="ts">
defineOptions({ name: 'LiveConversionOverview' });
defineProps<{
  summary: Api.Douyin.ConversionSummary;
  hooks: Api.Douyin.HookEvent[];
  coverage: Api.Douyin.SessionDataCoverage;
}>();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="钩子与客资转化">
    <NAlert type="info" :show-icon="true" class="mb-16px">
      客资只按公开抖音号精确标注到用户；“钩子关联客资”表示客资在钩子后 30 分钟内产生，不代表确定因果。
    </NAlert>
    <NAlert v-if="coverage.analysis_truncated" type="warning" :show-icon="true" class="mb-16px">
      本场共采集 {{ coverage.comment_count }} 条评论；为保证页面性能，用户分析使用最近
      {{ coverage.analysis_comment_count }} 条样本，较早评论仍保留在数据库中。
    </NAlert>
    <NGrid :x-gap="12" :y-gap="12" cols="2 s:4 l:8" responsive="screen">
      <NGi><NStatistic label="下钩子次数" :value="summary.hook_count" /></NGi>
      <NGi><NStatistic label="有效钩子" :value="summary.effective_hook_count" /></NGi>
      <NGi><NStatistic label="强钩子" :value="summary.strong_hook_count || 0" /></NGi>
      <NGi><NStatistic label="待补完整" :value="summary.incomplete_hook_count || 0" /></NGi>
      <NGi><NStatistic label="本场客资" :value="summary.session_lead_count" /></NGi>
      <NGi><NStatistic label="时间窗关联客资" :value="summary.hook_window_lead_count" /></NGi>
      <NGi><NStatistic label="精确匹配用户" :value="summary.exact_matched_user_count" /></NGi>
      <NGi><NStatistic :label="coverage.analysis_truncated ? '样本评论用户' : '评论用户'" :value="summary.comment_user_count" /></NGi>
    </NGrid>
    <NAlert type="success" :show-icon="true" class="mt-16px">
      {{ hooks.length ? `已将 ${hooks.length} 个钩子或铺垫节点合并到上方“统一时间轴”，可按“转化钩子”筛选并点击回看。` : '真实话术中暂未识别到钩子或钩子铺垫。' }}
    </NAlert>
    <NDivider title-placement="left">用户身份采集覆盖</NDivider>
    <NGrid :x-gap="16" :y-gap="10" cols="1 s:2" responsive="screen">
      <NGi>
        <div class="mb-6px flex justify-between text-12px"><span>头像</span><span>{{ coverage.avatar_user_count }}/{{ coverage.comment_user_count }}</span></div>
        <NProgress type="line" :percentage="coverage.avatar_coverage_percent" :height="8" />
      </NGi>
      <NGi>
        <div class="mb-6px flex justify-between text-12px"><span>公开抖音号</span><span>{{ coverage.douyin_id_user_count }}/{{ coverage.comment_user_count }}</span></div>
        <NProgress type="line" :percentage="coverage.douyin_id_coverage_percent" :height="8" />
      </NGi>
    </NGrid>
    <div class="mt-10px text-12px text-gray-500">平台未返回的身份字段保持为空，不使用 sec_uid 冒充公开抖音号。</div>
  </NCard>
</template>
