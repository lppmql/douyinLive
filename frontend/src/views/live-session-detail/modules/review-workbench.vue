<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useReviewStore } from '@/store/modules/review';
import {
  fetchLiveSessionPage,
  fetchReviewWorkbench,
  generateSessionReview,
  updateReviewFindingStatus
} from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import MetricsChart from './metrics-chart.vue';
import ReviewVideoPlayer from './review-video-player.vue';
import ReviewTimeline from './review-timeline.vue';
import SessionComparison from './session-comparison.vue';
import AiPanel from './ai-panel.vue';

defineOptions({ name: 'LiveReviewWorkbench' });
const props = defineProps<{ sessionId: number; detail: Api.Douyin.LiveSessionDetail }>();
const emit = defineEmits<{ refreshDetail: [] }>();
const message = useMessage();
const reviewStore = useReviewStore();
const loading = ref(false);
const generating = ref(false);
const workbench = ref<Api.Douyin.ReviewWorkbench | null>(null);
const sessions = ref<Api.Douyin.LiveSessionListItem[]>([]);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const openFindingCount = computed(() => workbench.value?.findings.filter(item => item.status === 'open').length || 0);
const criticalCount = computed(
  () =>
    workbench.value?.findings.filter(item => item.severity === 'critical' && item.status !== 'dismissed').length || 0
);

async function loadWorkbench(autoGenerate = true) {
  loading.value = true;
  try {
    workbench.value = unwrapServiceData(await fetchReviewWorkbench(props.sessionId), '复盘工作台数据为空');
    if (autoGenerate && workbench.value && !workbench.value.findings.length) await generateReview();
  } catch (error) {
    message.error((error as { message?: string }).message || '复盘工作台加载失败');
  } finally {
    loading.value = false;
  }
}

async function generateReview() {
  generating.value = true;
  try {
    const reviewResult = unwrapServiceData(await generateSessionReview(props.sessionId), '复盘生成数据为空');
    workbench.value = reviewResult.workbench;
    emit('refreshDetail');
    message.success(`复盘已更新，共 ${reviewResult.finding_count || 0} 条真实证据`);
  } catch (error) {
    message.error((error as { message?: string }).message || '复盘生成失败');
  } finally {
    generating.value = false;
  }
}

async function updateFinding(item: Api.Douyin.ReviewFinding, status: Api.Douyin.ReviewFinding['status']) {
  try {
    const updatedFinding = unwrapServiceData(
      await updateReviewFindingStatus(props.sessionId, item.id, status),
      '复盘发现状态更新失败'
    );
    if (workbench.value) {
      const index = workbench.value.findings.findIndex(finding => finding.id === item.id);
      if (index >= 0) workbench.value.findings[index] = updatedFinding;
    }
    message.success('复盘发现状态已更新');
  } catch {
    message.error('状态更新失败');
  }
}

onMounted(async () => {
  reviewStore.initialize(props.sessionId);
  await loadWorkbench(false);
  // 后台静默加载场次列表（供跨场对比使用）
  fetchLiveSessionPage({ current: 1, size: 100 }).then(res => {
    sessions.value = res.data?.records || [];
  }).catch(() => {});
  if (props.detail.session.live_status === 'live') {
    pollTimer = setInterval(() => loadWorkbench(false), 15_000);
  }
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<template>
  <NSpin :show="loading && !workbench">
    <NSpace v-if="workbench" vertical :size="16">
      <NCard :bordered="false" class="card-wrapper" size="small">
        <div class="grid grid-cols-[180px_1fr_auto] items-center gap-16px lt-md:grid-cols-1">
          <div>
            <div class="text-12px text-gray-500">复盘数据可信度</div>
            <div class="mt-4px flex items-end gap-5px">
              <span class="text-31px font-800">{{ workbench.completeness.score }}</span>
              <span class="mb-4px text-13px text-gray-400">%</span>
            </div>
            <NProgress
              :percentage="workbench.completeness.score"
              :height="7"
              :status="
                workbench.completeness.score >= 85
                  ? 'success'
                  : workbench.completeness.score >= 60
                    ? 'default'
                    : 'warning'
              "
              :show-indicator="false"
            />
          </div>
          <div class="grid grid-cols-3 gap-8px sm:grid-cols-4 lg:grid-cols-7">
            <NTooltip v-for="item in (workbench.completeness.components || [])" :key="item.name">
              <template #trigger>
                <div
                  class="rounded-8px px-8px py-7px text-center"
                  :class="
                    item.status === 'complete'
                      ? 'bg-success-50 dark:bg-success-900/20'
                      : item.status === 'partial'
                        ? 'bg-warning-50 dark:bg-warning-900/20'
                        : 'bg-error-50 dark:bg-error-900/20'
                  "
                >
                  <div class="text-11px text-gray-500">{{ item.name }}</div>
                  <div class="mt-3px text-13px font-700">{{ item.score.toFixed(0) }}%</div>
                </div>
              </template>
              已采集 {{ item.captured }}，参考应有 {{ item.expected }}，权重 {{ item.weight }}%
            </NTooltip>
          </div>
          <div class="flex items-center gap-8px lt-md:justify-start">
            <NTag :type="criticalCount ? 'error' : 'success'" round :bordered="false">
              重点复核 {{ criticalCount }}
            </NTag>
            <NTag type="info" round :bordered="false">待判断 {{ openFindingCount }}</NTag>
          </div>
        </div>
      </NCard>

      <NAlert v-if="!workbench.completeness.analysis_ready" type="warning" show-icon :bordered="false">
        当前数据仍可回看，但不足以形成稳定AI结论。请优先补齐分钟指标、评论或ASR话术。
      </NAlert>

      <div class="grid grid-cols-1 items-start gap-16px md:grid-cols-[280px_minmax(0,1fr)]">
        <ReviewVideoPlayer
          :session-id="sessionId"
          :stream-url="detail.stream_url"
          :title="detail.session.session_title || '直播场次回放'"
          :duration-seconds="detail.session.live_duration_seconds || 0"
          :findings="workbench.findings || []"
        />
        <NCard title="统一复盘分析" :bordered="false" class="card-wrapper min-w-0">
          <template #header-extra>
            <NButton size="small" type="primary" :loading="generating" @click="generateReview">
              重新生成 AI 复盘
            </NButton>
          </template>
          <NTabs type="line" animated default-value="timeline">
            <NTabPane name="timeline" tab="统一时间轴" display-directive="if">
              <NAlert v-if="workbench.live_alerts?.length" type="warning" :bordered="false" class="mb-12px">
                当前有 {{ workbench.live_alerts?.length || 0 }} 条实时告警，已按发生时间合并到时间轴中。
              </NAlert>
              <ReviewTimeline
                :session-start="detail.session.live_start_time"
                :metrics="detail.metrics || []"
                :comments="detail.comments || []"
                :segments="workbench.transcript_segments || []"
                :findings="workbench.findings || []"
                :alerts="workbench.live_alerts || []"
                @update-finding="updateFinding"
              />
            </NTabPane>
            <NTabPane name="metrics" :tab="`分钟曲线 (${detail.metrics.length})`" display-directive="if">
              <MetricsChart :metrics="detail.metrics || []" />
            </NTabPane>
            <NTabPane name="ai" tab="AI 分析" display-directive="if">
              <AiPanel :session-id="sessionId" :detail="detail" />
            </NTabPane>
          </NTabs>
        </NCard>
      </div>

      <NCard title="跨场对比" :bordered="false" class="card-wrapper">
        <SessionComparison :session-id="sessionId" :sessions="sessions" />
      </NCard>
    </NSpace>

    <NResult v-else status="info" title="复盘工作台正在准备" description="请稍候，系统正在读取真实场次数据。" />
  </NSpin>
</template>
