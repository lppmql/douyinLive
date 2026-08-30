<script setup lang="ts">
import { computed } from 'vue';

defineOptions({ name: 'DashboardMetricGrid' });

const props = defineProps<{ summary: Api.Douyin.DashboardSummary }>();

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString('zh-CN');
}

function formatMoney(value: number) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

const metrics = computed(() => [
  {
    label: '直播场次',
    value: formatNumber(props.summary.session_count),
    helper: `${props.summary.anchor_count} 位主播 · 完整率 ${props.summary.detail_completion_rate}%`,
    icon: 'mdi:video-outline',
    tone: 'blue'
  },
  {
    label: '累计观看',
    value: formatNumber(props.summary.total_viewers),
    helper: `评论 ${formatNumber(props.summary.total_comments)} 条`,
    icon: 'mdi:account-eye-outline',
    tone: 'cyan'
  },
  {
    label: '站内私信',
    value: formatNumber(props.summary.total_private_messages),
    helper: `观看转私信 ${props.summary.private_message_rate}%`,
    icon: 'mdi:message-processing-outline',
    tone: 'purple'
  },
  {
    label: '确认留资',
    value: formatNumber(props.summary.total_leads),
    helper: `观看转留资 ${props.summary.lead_conversion_rate}%`,
    icon: 'mdi:account-check-outline',
    tone: 'green'
  },
  {
    label: '高意向评论',
    value: formatNumber(props.summary.high_intent_comment_count),
    helper: '开店预算、选址、品牌和避坑意向',
    icon: 'mdi:comment-alert-outline',
    tone: 'orange'
  },
  {
    label: '广告消耗',
    value: formatMoney(props.summary.total_ad_cost),
    helper: `平均线索成本 ${formatMoney(props.summary.average_lead_cost)}`,
    icon: 'mdi:cash-multiple',
    tone: 'red'
  },
  {
    label: '待办复盘',
    value: formatNumber(props.summary.open_review_action_count),
    helper: '待处理或进行中的改进行动',
    icon: 'mdi:clipboard-check-outline',
    tone: 'amber'
  },
  {
    label: '直播中',
    value: formatNumber(props.summary.live_session_count),
    helper: '当前筛选范围内正在直播的场次',
    icon: 'mdi:broadcast',
    tone: 'pink'
  }
]);
</script>

<template>
  <NGrid cols="2 s:4" responsive="screen" :x-gap="14" :y-gap="14">
    <NGi v-for="metric in metrics" :key="metric.label">
      <NCard :bordered="false" size="small" class="card-wrapper metric-card">
        <div class="flex items-start justify-between gap-12px">
          <div class="min-w-0">
            <div class="text-12px text-gray-400">{{ metric.label }}</div>
            <div class="mt-8px truncate text-24px font-700">{{ metric.value }}</div>
          </div>
          <div class="metric-icon" :class="`metric-icon--${metric.tone}`">
            <SvgIcon :icon="metric.icon" class="text-22px" />
          </div>
        </div>
        <div class="mt-10px truncate text-11px text-gray-400">{{ metric.helper }}</div>
      </NCard>
    </NGi>
  </NGrid>
</template>

<style scoped>
.metric-card {
  min-height: 126px;
}

.metric-icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: none;
  place-items: center;
  border-radius: 12px;
}

.metric-icon--blue { color: #2080f0; background: rgb(32 128 240 / 12%); }
.metric-icon--cyan { color: #08979c; background: rgb(8 151 156 / 12%); }
.metric-icon--purple { color: #722ed1; background: rgb(114 46 209 / 12%); }
.metric-icon--green { color: #18a058; background: rgb(24 160 88 / 12%); }
.metric-icon--orange { color: #f0a020; background: rgb(240 160 32 / 12%); }
.metric-icon--red { color: #d03050; background: rgb(208 48 80 / 12%); }
.metric-icon--amber { color: #d48806; background: rgb(212 136 6 / 12%); }
.metric-icon--pink { color: #d0308a; background: rgb(208 48 138 / 12%); }
</style>
