<script setup lang="ts">
import { computed } from 'vue';
import { NAlert, NCard, NGrid, NGi, NStatistic, NTag, NText } from 'naive-ui';

defineOptions({ name: 'ClipEvidencePanel' });

const props = defineProps<{ clip: Api.Douyin.ClipClip }>();

const evidenceSegments = computed(() => props.clip.selection_evidence?.segments || []);
const totals = computed(() =>
  evidenceSegments.value.reduce(
    (result, item) => ({
      comments: result.comments + Number(item.comment_count || 0),
      intent: result.intent + Number(item.high_intent_comment_count || 0),
      hooks: result.hooks + Number(item.hook_count || 0),
      leads: result.leads + Number(item.related_lead_count || 0),
      leadsAfter5m: result.leadsAfter5m + Number(item.lead_after_5m_count || 0)
    }),
    { comments: 0, intent: 0, hooks: 0, leads: 0, leadsAfter5m: 0 }
  )
);
</script>

<template>
  <NCard size="small" title="选段证据" :bordered="true">
    <NGrid :cols="10" :x-gap="8" responsive="screen" item-responsive>
      <NGi span="5 m:2"><NStatistic label="综合信号" :value="clip.selection_evidence?.signal_score || 0" /></NGi>
      <NGi span="5 m:2"><NStatistic label="附近评论" :value="totals.comments" /></NGi>
      <NGi span="5 m:2"><NStatistic label="高意向评论" :value="totals.intent" /></NGi>
      <NGi span="5 m:2"><NStatistic label="正式钩子/归属客资" :value="`${totals.hooks}/${totals.leads}`" /></NGi>
      <NGi span="5 m:2"><NStatistic label="片段后 5 分钟客资" :value="totals.leadsAfter5m" /></NGi>
    </NGrid>
    <div v-if="evidenceSegments.length" class="mt-12px flex flex-wrap gap-6px">
      <template v-for="(item, index) in evidenceSegments" :key="item.transcript_segment_id || index">
        <NTag v-for="hookType in item.hook_types || []" :key="`${index}-${hookType}`" size="small" type="info">
          {{ hookType }}
        </NTag>
      </template>
    </div>
    <NAlert v-if="totals.leads || totals.leadsAfter5m" type="info" :bordered="false" class="mt-12px">
      <NText depth="3">归属客资与片段后 5 分钟客资都只表示真实时间窗关联，不代表确定因果。</NText>
    </NAlert>
  </NCard>
</template>
