<script setup lang="ts">
import { computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useReviewStore } from '@/store/modules/review';

defineOptions({ name: 'ReviewTimeline' });
const props = defineProps<{
  sessionStart: string | null;
  metrics: Api.Douyin.LiveMetric[];
  comments: Api.Douyin.LiveComment[];
  segments: Api.Douyin.ReviewTranscriptSegment[];
  findings: Api.Douyin.ReviewFinding[];
  alerts: Api.Douyin.ReviewLiveAlert[];
}>();
const emit = defineEmits<{
  createAsset: [segment: Api.Douyin.ReviewTranscriptSegment];
  updateFinding: [finding: Api.Douyin.ReviewFinding, status: Api.Douyin.ReviewFinding['status']];
}>();

type EventKind = 'alert' | 'finding' | 'comment' | 'transcript' | 'metric';
interface TimelineEvent {
  key: string;
  kind: EventKind;
  second: number;
  endSecond: number;
  title: string;
  content: string;
  category?: string;
  severity?: Api.Douyin.ReviewFinding['severity'];
  findingId?: number;
  finding?: Api.Douyin.ReviewFinding;
  segment?: Api.Douyin.ReviewTranscriptSegment;
}

const reviewStore = useReviewStore();
const { currentSecond, selectedEvidenceId } = storeToRefs(reviewStore);
const enabledKinds = ref<EventKind[]>(['alert', 'finding', 'comment', 'transcript']);
const kindOptions: Array<{ label: string; value: EventKind }> = [
  { label: '实时告警', value: 'alert' },
  { label: '复盘发现', value: 'finding' },
  { label: '用户评论', value: 'comment' },
  { label: '主播话术', value: 'transcript' },
  { label: '指标采样', value: 'metric' }
];

function relativeSeconds(value: string | null) {
  if (!props.sessionStart || !value) return 0;
  return Math.max(0, (new Date(value).getTime() - new Date(props.sessionStart).getTime()) / 1000);
}

const events = computed<TimelineEvent[]>(() => {
  const items: TimelineEvent[] = [];
  props.alerts.forEach(item => {
    items.push({
      key: `alert-${item.key}`,
      kind: 'alert',
      second: item.start_seconds || 0,
      endSecond: (item.start_seconds || 0) + 30,
      title: item.title,
      content: item.description,
      category: '实时告警',
      severity: item.severity
    });
  });
  props.findings.forEach(item => {
    items.push({
      key: `finding-${item.id}`,
      kind: 'finding',
      second: item.start_seconds || 0,
      endSecond: item.end_seconds || item.start_seconds || 0,
      title: item.title,
      content: item.evidence_text || item.description || '场次级复盘结论',
      category: item.category,
      severity: item.severity,
      findingId: item.id,
      finding: item
    });
  });
  props.comments.forEach(item => {
    items.push({
      key: `comment-${item.id}`,
      kind: 'comment',
      second: relativeSeconds(item.comment_time),
      endSecond: relativeSeconds(item.comment_time) + 15,
      title: `${item.user_nickname || '匿名用户'}${item.is_high_intent ? ' · 筹备意向' : ''}`,
      content: item.comment_content || '-',
      category: item.keywords || undefined,
      severity: item.is_high_intent ? 'warning' : 'info'
    });
  });
  props.segments.forEach(item => {
    items.push({
      key: `transcript-${item.id}`,
      kind: 'transcript',
      second: item.segment_start,
      endSecond: item.segment_end,
      title: item.segment_type || '主播话术',
      content: item.text_content || '-',
      category: item.segment_type || undefined,
      segment: item
    });
  });
  props.metrics.forEach((item, index) => {
    const second = relativeSeconds(item.metric_time);
    items.push({
      key: `metric-${index}-${item.metric_time}`,
      kind: 'metric',
      second,
      endSecond: second + 60,
      title: `在线 ${item.online_count} · 进入 ${item.enter_count}`,
      content: `评论 ${item.comment_count}，关注 ${item.follow_count}，线索 ${item.clue_count}`
    });
  });
  return items.sort((a, b) => a.second - b.second || a.kind.localeCompare(b.kind));
});
const visibleEvents = computed(() => events.value.filter(item => enabledKinds.value.includes(item.kind)));

function formatSecond(value: number) {
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = Math.floor(value % 60);
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}
function kindIcon(kind: EventKind) {
  return {
    finding: 'mdi:lightbulb-alert-outline',
    alert: 'mdi:alert-decagram-outline',
    comment: 'mdi:comment-account-outline',
    transcript: 'mdi:text-box-outline',
    metric: 'mdi:chart-timeline-variant'
  }[kind];
}
function findingStatusLabel(status: Api.Douyin.ReviewFinding['status']) {
  return {
    open: '待判断',
    confirmed: '已确认',
    dismissed: '已忽略',
    resolved: '已解决'
  }[status];
}
function isActive(item: TimelineEvent) {
  return (
    (item.findingId && selectedEvidenceId.value === item.findingId) ||
    (currentSecond.value >= item.second && currentSecond.value <= Math.max(item.endSecond, item.second + 5))
  );
}
</script>

<template>
  <div>
    <div class="mb-12px flex flex-wrap items-center justify-between gap-10px">
      <NCheckboxGroup v-model:value="enabledKinds">
        <NSpace wrap :size="10">
          <NCheckbox v-for="item in kindOptions" :key="item.value" :value="item.value" :label="item.label" />
        </NSpace>
      </NCheckboxGroup>
      <NTag round :bordered="false" type="info">{{ visibleEvents.length }} 个真实节点</NTag>
    </div>

    <NEmpty v-if="!visibleEvents.length" description="暂无可展示的复盘时间轴数据" class="py-50px" />
    <NVirtualList v-else :items="visibleEvents" :item-size="92" item-resizable class="h-560px pr-6px lt-sm:h-420px">
      <template #default="{ item }">
        <div
          role="button"
          tabindex="0"
          class="timeline-item mb-8px w-full flex items-start gap-12px rounded-10px px-12px py-10px text-left"
          :class="{ 'timeline-item--active': isActive(item) }"
          @click="reviewStore.seekTo(item.second, item.findingId)"
          @keydown.enter="reviewStore.seekTo(item.second, item.findingId)"
        >
          <div class="time-chip shrink-0 rounded-6px px-7px py-4px text-11px font-700">
            {{ formatSecond(item.second) }}
          </div>
          <SvgIcon :icon="kindIcon(item.kind)" class="mt-2px shrink-0 text-20px text-primary" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-8px">
              <span class="text-13px font-700">{{ item.title }}</span>
              <NTag v-if="item.category" size="tiny" round :bordered="false">{{ item.category }}</NTag>
              <NTag v-if="item.severity === 'critical'" size="tiny" type="error">重点复核</NTag>
              <NTag v-else-if="item.severity === 'warning'" size="tiny" type="warning">机会/风险</NTag>
              <NTag v-if="item.finding" size="tiny" :bordered="false">
                {{ findingStatusLabel(item.finding.status) }}
              </NTag>
            </div>
            <div class="mt-4px line-clamp-2 text-12px leading-19px text-gray-500">{{ item.content }}</div>
          </div>
          <NDropdown
            v-if="item.finding"
            trigger="click"
            :options="[
              { label: '确认问题', key: 'confirmed' },
              { label: '标记已解决', key: 'resolved' },
              { label: '忽略本条', key: 'dismissed' }
            ]"
            @select="value => emit('updateFinding', item.finding!, value)"
          >
            <NButton text size="tiny" class="shrink-0" @click.stop>
              <SvgIcon icon="mdi:dots-horizontal" />
            </NButton>
          </NDropdown>
          <NButton
            v-if="item.segment"
            size="tiny"
            secondary
            class="shrink-0"
            @click.stop="emit('createAsset', item.segment)"
          >
            收录话术
          </NButton>
        </div>
      </template>
    </NVirtualList>
  </div>
</template>

<style scoped>
.timeline-item {
  border: 1px solid rgba(128, 128, 128, 0.14);
  background: rgba(128, 128, 128, 0.035);
  transition: 0.2s ease;
}
.timeline-item:hover,
.timeline-item--active {
  border-color: rgba(32, 128, 240, 0.55);
  background: rgba(32, 128, 240, 0.08);
}
.time-chip {
  background: rgba(32, 128, 240, 0.12);
  color: rgb(32, 128, 240);
}
</style>
