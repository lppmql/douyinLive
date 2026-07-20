<script setup lang="ts">
import { computed, h, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useIntervalFn, useWebSocket } from '@vueuse/core';
import type { SelectOption } from 'naive-ui';
import { useMessage } from 'naive-ui';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';
import BusinessPageHeader from '@/components/business/page-header.vue';
import {
  fetchLiveSessions,
  fetchTranscriptFullText,
  fetchTranscriptSegments,
  fetchTranscriptTasks,
  fetchTranscriptTaskStatus,
  getLiveSessionAvatarUrl,
  queueTranscript,
  queueTranscriptsByAnchor,
  runTranscriptAiPipeline
} from '@/service/api/douyin';
import { getServiceBaseURL, getWebSocketBaseURL, unwrapServiceData } from '@/utils/service';

defineOptions({ name: 'Transcripts' });

type TaskStatus = Api.Douyin.TranscriptTask['status'];
type DisplayStatus = TaskStatus | Api.Douyin.TranscriptSegment['asr_status'];
type SessionSelectOption = SelectOption & {
  anchorName: string;
  avatarUrl: string | null;
};

const router = useRouter();
const message = useMessage();
const sessions = ref<Api.Douyin.LiveSession[]>([]);
const tasks = ref<Api.Douyin.TranscriptTask[]>([]);
const segments = ref<Api.Douyin.TranscriptSegment[]>([]);
const fullText = ref('');
const selectedSessionId = ref<number | null>(null);
const taskSummary = ref<Record<TaskStatus, number>>({ queued: 0, processing: 0, completed: 0, failed: 0 });
const loading = ref(true);
const refreshing = ref(false);
const queueLoading = ref(false);
const batchLoading = ref(false);
const aiLoading = ref(false);
const taskDrawerVisible = ref(false);
const taskFilter = ref<TaskStatus | 'all'>('all');
const searchKeyword = ref('');
const categoryFilter = ref<string | null>(null);
const viewMode = ref<'segments' | 'full'>('segments');
const livePreview = ref('');
const visibleSegmentLimit = ref(80);
const loadError = ref('');
const pageActive = ref(true);

const selectedSession = computed(() => sessions.value.find(item => item.id === selectedSessionId.value) || null);
const selectedTask = computed(() => tasks.value.find(item => item.session_id === selectedSessionId.value) || null);
const activeTaskCount = computed(() => taskSummary.value.queued + taskSummary.value.processing);
const isHttpProxy = import.meta.env.DEV && import.meta.env.VITE_HTTP_PROXY === 'Y';
const { otherBaseURL } = getServiceBaseURL(import.meta.env, isHttpProxy);
const transcriptWsBaseURL = getWebSocketBaseURL(otherBaseURL.backend || window.location.origin);
const wsUrl = computed(() => {
  return selectedSessionId.value ? `${transcriptWsBaseURL}/ws/transcript/${selectedSessionId.value}` : '';
});
const {
  status: wsStatus,
  data: wsData,
  open,
  close
} = useWebSocket(wsUrl, {
  autoReconnect: { retries: 5, delay: 3000 },
  heartbeat: { message: 'ping', interval: 30000 }
});
const wsConnected = computed(() => wsStatus.value === 'OPEN');

const taskStatusCards = computed(() => [
  {
    status: 'queued' as const,
    label: '等待转写',
    value: taskSummary.value.queued,
    icon: 'mdi:clock-outline',
    tone: 'info'
  },
  {
    status: 'processing' as const,
    label: '正在转写',
    value: taskSummary.value.processing,
    icon: 'mdi:waveform',
    tone: 'warning'
  },
  {
    status: 'completed' as const,
    label: '转写完成',
    value: taskSummary.value.completed,
    icon: 'mdi:check-circle-outline',
    tone: 'success'
  },
  {
    status: 'failed' as const,
    label: '需要处理',
    value: taskSummary.value.failed,
    icon: 'mdi:alert-circle-outline',
    tone: 'error'
  }
]);
const taskBySession = computed(() => new Map(tasks.value.map(item => [item.session_id, item])));
const sessionOptions = computed(() =>
  sessions.value.map(session => {
    const task = taskBySession.value.get(session.id);
    const date = session.live_start_time ? formatDate(session.live_start_time) : '时间未知';
    return {
      value: session.id,
      label: `${session.anchor_name || '未知主播'} · ${date} · ${formatDuration(session.live_duration_seconds)} · ${getStatusLabel(task?.status)}`,
      anchorName: session.anchor_name || '未知主播',
      avatarUrl: session.anchor_avatar_url ? getLiveSessionAvatarUrl(session.id) : null
    } satisfies SessionSelectOption;
  })
);
const categoryStats = computed(() => {
  const counts = new Map<string, number>();
  segments.value.forEach(item => {
    const category = item.segment_type || '未分类';
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, count]) => ({
      name,
      count,
      percent: segments.value.length ? (count / segments.value.length) * 100 : 0
    }))
    .sort((a, b) => b.count - a.count);
});
const categoryOptions = computed(() => [
  { label: '全部分类', value: '' },
  ...categoryStats.value.map(item => ({ label: `${item.name} (${item.count})`, value: item.name }))
]);
const filteredSegments = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase();
  return segments.value.filter(item => {
    const matchesCategory = !categoryFilter.value || (item.segment_type || '未分类') === categoryFilter.value;
    const matchesKeyword = !keyword || item.text_content.toLowerCase().includes(keyword);
    return matchesCategory && matchesKeyword;
  });
});
const visibleSegments = computed(() => filteredSegments.value.slice(0, visibleSegmentLimit.value));
const totalCharacters = computed(() => segments.value.reduce((total, item) => total + item.text_content.length, 0));
const transcribedSeconds = computed(() => Math.max(0, ...segments.value.map(item => item.segment_end || 0)));
const coveragePercent = computed(() => {
  const duration = selectedSession.value?.live_duration_seconds || 0;
  return duration ? Math.min(100, (transcribedSeconds.value / duration) * 100) : 0;
});
const averageAiScore = computed(() => {
  const scores = segments.value.map(item => item.ai_score).filter((value): value is number => value !== null);
  return scores.length ? scores.reduce((total, value) => total + value, 0) / scores.length : null;
});
const filteredTasks = computed(() =>
  taskFilter.value === 'all' ? tasks.value : tasks.value.filter(item => item.status === taskFilter.value)
);

function formatTime(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = Math.floor(seconds % 60);
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

function formatDuration(seconds: number) {
  if (!seconds) return '时长未知';
  return seconds >= 3600 ? `${(seconds / 3600).toFixed(1)}小时` : `${Math.round(seconds / 60)}分钟`;
}

function formatDate(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function getStatusLabel(status?: DisplayStatus) {
  if (!status) return '未转写';
  return { queued: '等待中', pending: '待处理', processing: '转写中', completed: '已完成', failed: '失败' }[status];
}

function getStatusType(status?: DisplayStatus): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (!status) return 'default';
  return { queued: 'info', pending: 'info', processing: 'warning', completed: 'success', failed: 'error' }[status] as
    | 'success'
    | 'warning'
    | 'error'
    | 'info';
}

function getPostprocessLabel(status: Api.Douyin.TranscriptTask['postprocess_status']) {
  return { pending: '待复盘', processing: '复盘入库中', completed: '已复盘入库', failed: '复盘入库失败' }[status];
}

function getPostprocessType(status: Api.Douyin.TranscriptTask['postprocess_status']) {
  return { pending: 'info', processing: 'warning', completed: 'success', failed: 'error' }[status] as
    | 'info'
    | 'warning'
    | 'success'
    | 'error';
}

function getSessionStartTimestamp(value: string | null) {
  const timestamp = value ? Date.parse(value) : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function sortSessionsByLatest(items: Api.Douyin.LiveSession[]) {
  return [...items].sort((a, b) => {
    const timeDifference = getSessionStartTimestamp(b.live_start_time) - getSessionStartTimestamp(a.live_start_time);
    return timeDifference || b.id - a.id;
  });
}

function renderSessionLabel(option: SelectOption) {
  const sessionOption = option as SessionSelectOption;
  return h('div', { class: 'flex min-w-0 items-center gap-8px' }, [
    h(AnchorAvatar, { size: 26, src: sessionOption.avatarUrl || undefined, name: sessionOption.anchorName }),
    h('span', { class: 'min-w-0 flex-1 truncate' }, String(sessionOption.label || ''))
  ]);
}

function getSessionAvatarUrl(session: Api.Douyin.LiveSession) {
  return session.anchor_avatar_url ? getLiveSessionAvatarUrl(session.id) : undefined;
}

async function loadSessions() {
  const response = await fetchLiveSessions();
  sessions.value = sortSessionsByLatest(unwrapServiceData(response, '直播场次读取失败'));
}

async function loadTaskData() {
  const [summaryResponse, taskResponse] = await Promise.all([fetchTranscriptTaskStatus(), fetchTranscriptTasks()]);
  taskSummary.value = unwrapServiceData(summaryResponse, '话术任务汇总读取失败');
  tasks.value = unwrapServiceData(taskResponse, '话术任务读取失败');
}

async function loadTranscript(sessionId: number, silent = false) {
  selectedSessionId.value = sessionId;
  if (!silent) loading.value = true;
  livePreview.value = '';
  try {
    const [segmentResponse, textResponse] = await Promise.all([
      fetchTranscriptSegments(sessionId),
      fetchTranscriptFullText(sessionId).catch(() => ({ data: null }))
    ]);
    segments.value = unwrapServiceData(segmentResponse, '话术分段读取失败');
    fullText.value = textResponse.data?.full_text || '';
  } catch (error) {
    segments.value = [];
    fullText.value = '';
    if (!silent) message.error(error instanceof Error ? error.message : '话术数据加载失败，请稍后重试');
  } finally {
    loading.value = false;
  }
}

async function initializePage() {
  loading.value = true;
  loadError.value = '';
  try {
    await Promise.all([loadSessions(), loadTaskData()]);
    const latestSession = sessions.value[0];
    if (latestSession) await loadTranscript(latestSession.id);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '主播话术页面加载失败';
    message.error(loadError.value);
  } finally {
    loading.value = false;
  }
}

async function refreshPage() {
  refreshing.value = true;
  try {
    await Promise.all([loadSessions(), loadTaskData()]);
    if (selectedSessionId.value) await loadTranscript(selectedSessionId.value, true);
    loadError.value = '';
    message.success('话术任务与内容已刷新');
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '刷新失败，请检查后端服务';
    message.error(loadError.value);
  } finally {
    refreshing.value = false;
  }
}

async function startTranscription() {
  if (!selectedSessionId.value) return;
  queueLoading.value = true;
  try {
    const response = await queueTranscript(selectedSessionId.value);
    const data = unwrapServiceData(response, '转写任务响应为空');
    message.success(`任务已${data.created ? '创建' : '在队列中'}，编号 ${data.task_id}`);
    await loadTaskData();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '该场次暂无可用回放，请先刷新采集或检查 m3u8');
  } finally {
    queueLoading.value = false;
  }
}

async function queueAnchorBatch() {
  batchLoading.value = true;
  try {
    const response = await queueTranscriptsByAnchor(1);
    const data = unwrapServiceData(response, '批量任务响应为空');
    message.success(`检查 ${data.anchor_count} 位主播，新建 ${data.created_count} 个任务`);
    await loadTaskData();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '增量转写失败，请确认已采集真实回放');
  } finally {
    batchLoading.value = false;
  }
}

async function runAiPipeline() {
  if (!selectedSessionId.value || !segments.value.length) return;
  aiLoading.value = true;
  try {
    const response = await runTranscriptAiPipeline(selectedSessionId.value);
    const data = unwrapServiceData(response, 'AI 分析没有返回处理结果');
    const saved =
      data.live_data_saved + data.comments_saved + data.transcript_saved + data.analysis_saved + data.review_saved;
    message.success(`AI 复盘完成，知识库新增或更新 ${saved} 条真实数据`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : 'AI 分析失败，请确认本场已有完整话术');
  } finally {
    aiLoading.value = false;
  }
}

async function copyText(text: string, successMessage: string) {
  if (!text) return message.warning('当前没有可复制的话术');
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  }
  message.success(successMessage);
}

function copyFullText() {
  const text =
    fullText.value || segments.value.map(item => `[${formatTime(item.segment_start)}] ${item.text_content}`).join('\n');
  return copyText(text, '完整话术已复制');
}

async function jumpToSegment(segment: Api.Douyin.TranscriptSegment) {
  viewMode.value = 'segments';
  searchKeyword.value = '';
  categoryFilter.value = null;
  await nextTick();
  const segmentIndex = segments.value.findIndex(item => item.id === segment.id);
  visibleSegmentLimit.value = Math.max(80, segmentIndex + 1);
  await nextTick();
  document.getElementById(`transcript-segment-${segment.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function openTaskDrawer(status: TaskStatus | 'all' = 'all') {
  taskFilter.value = status;
  taskDrawerVisible.value = true;
}

function selectTask(task: Api.Douyin.TranscriptTask) {
  taskDrawerVisible.value = false;
  void loadTranscript(task.session_id);
}

function openSessionDetail(sessionId: number) {
  void router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
}

const { pause: pausePolling, resume: resumePolling } = useIntervalFn(
  async () => {
    if (!pageActive.value || document.visibilityState !== 'visible') return;
    await loadTaskData();
    if (selectedSessionId.value) await loadTranscript(selectedSessionId.value, true);
  },
  5000,
  { immediate: false }
);

watch(activeTaskCount, count => (count && pageActive.value ? resumePolling() : pausePolling()), { immediate: true });
watch([selectedSessionId, searchKeyword, categoryFilter], () => {
  visibleSegmentLimit.value = 80;
});
watch(selectedSessionId, sessionId => {
  close();
  if (sessionId) setTimeout(() => open(), 100);
});
watch(wsData, value => {
  if (!value || value === 'pong') return;
  try {
    const result = JSON.parse(String(value));
    if (result.type === 'pong') return;
    if (result.text) livePreview.value = result.text;
    if (result.is_final && selectedSessionId.value) void loadTranscript(selectedSessionId.value, true);
  } catch {
    // 非 JSON 心跳不影响页面。
  }
});

onMounted(initializePage);
onActivated(() => {
  pageActive.value = true;
  if (activeTaskCount.value) resumePolling();
  if (selectedSessionId.value) setTimeout(() => open(), 100);
});
onDeactivated(() => {
  pageActive.value = false;
  pausePolling();
  close();
});
onUnmounted(() => {
  pageActive.value = false;
  pausePolling();
  close();
});
</script>

<template>
  <NSpace vertical :size="16" class="business-page">
    <BusinessPageHeader
      title="主播话术"
      description="查看真实直播 ASR 话术、转写覆盖和内容结构，快速定位开店避坑知识、资料钩子与私信承接证据。"
      icon="mdi:account-voice"
      :status="activeTaskCount ? `${activeTaskCount} 个任务运行中` : 'ASR 队列空闲'"
      :status-type="taskSummary.failed ? 'warning' : activeTaskCount ? 'info' : 'success'"
    >
      <template #actions>
        <NButton secondary :loading="refreshing" @click="refreshPage">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新数据
        </NButton>
      </template>
      <div class="flex flex-wrap items-center gap-x-16px gap-y-6px text-12px text-gray-500">
        <span>选择真实场次</span>
        <span>查看分段与覆盖</span>
        <span>定位高价值话术</span>
        <span>分析并同步知识库</span>
      </div>
    </BusinessPageHeader>

    <NAlert v-if="loadError" type="warning" :bordered="false" show-icon>
      主播话术数据未能完整更新：{{ loadError }}
      <NButton size="small" secondary :loading="loading || refreshing" @click="initializePage">重新加载</NButton>
    </NAlert>

    <div class="grid grid-cols-2 gap-12px lg:grid-cols-4">
      <button
        v-for="card in taskStatusCards"
        :key="card.status"
        type="button"
        class="business-clickable-card business-focus-ring status-card rounded-12px bg-white p-14px text-left dark:bg-dark sm:p-16px"
        :class="`status-card--${card.tone}`"
        @click="openTaskDrawer(card.status)"
      >
        <div class="flex items-center justify-between gap-8px">
          <div>
            <div class="text-12px text-gray-500">{{ card.label }}</div>
            <div class="mt-5px text-26px font-800">{{ card.value }}</div>
          </div>
          <div class="status-icon flex-center rounded-10px p-8px"><SvgIcon :icon="card.icon" class="text-24px" /></div>
        </div>
        <div class="mt-8px text-11px text-gray-400">点击查看真实任务明细</div>
      </button>
    </div>

    <NAlert v-if="taskSummary.failed" type="warning" :bordered="false" show-icon>
      有 {{ taskSummary.failed }} 场转写需要处理，不一定都是缺少 m3u8，也可能是回放过期或无有效语音。
      <NButton text type="warning" class="ml-8px" @click="openTaskDrawer('failed')">查看具体场次和错误</NButton>
    </NAlert>

    <NCard :bordered="false" class="card-wrapper">
      <div class="business-toolbar">
        <div class="min-w-0 flex-1">
          <div class="mb-8px flex items-center gap-8px text-12px font-600 text-gray-500">
            <span>当前复盘场次</span>
            <NTag size="tiny" type="info" :bordered="false" round>默认最新</NTag>
          </div>
          <NSelect
            v-model:value="selectedSessionId"
            size="large"
            filterable
            :options="sessionOptions"
            :render-label="renderSessionLabel"
            placeholder="搜索主播、日期或场次"
            @update:value="loadTranscript"
          />
          <div v-if="selectedSession" class="mt-10px flex flex-wrap items-center gap-8px text-12px text-gray-500">
            <AnchorAvatar
              :size="28"
              :src="getSessionAvatarUrl(selectedSession)"
              :name="selectedSession.anchor_name || '未知主播'"
            />
            <strong class="text-gray-700 dark:text-gray-200">{{ selectedSession.anchor_name || '未知主播' }}</strong>
            <span>{{ formatDate(selectedSession.live_start_time) }}</span>
            <span>{{ formatDuration(selectedSession.live_duration_seconds) }}</span>
            <NTag size="small" :type="getStatusType(selectedTask?.status)" :bordered="false">
              {{ getStatusLabel(selectedTask?.status) }}
            </NTag>
            <NTooltip>
              <template #trigger>
                <NTag size="small" :type="wsConnected ? 'success' : 'default'" :bordered="false">
                  {{ wsConnected ? '实时连接正常' : '实时连接待命' }}
                </NTag>
              </template>
              只有任务正在转写时才会持续收到实时片段，离线状态不影响查看已保存话术。
            </NTooltip>
          </div>
        </div>
        <div class="business-toolbar__actions">
          <NButton secondary :disabled="!selectedSessionId || (!segments.length && !fullText)" @click="copyFullText">
            <template #icon><SvgIcon icon="mdi:content-copy" /></template>
            复制全文
          </NButton>
          <NButton
            type="primary"
            secondary
            :disabled="!selectedSessionId"
            :loading="queueLoading"
            @click="startTranscription"
          >
            {{ selectedTask ? '重新转写' : '开始转写' }}
          </NButton>
          <NButton type="primary" :disabled="!segments.length" :loading="aiLoading" @click="runAiPipeline">
            AI 分析并入库
          </NButton>
          <NDropdown
            trigger="click"
            :options="[
              { label: '各主播增量转写', key: 'batch' },
              { label: '查看全部任务', key: 'tasks' },
              { label: '打开场次详情', key: 'detail', disabled: !selectedSessionId }
            ]"
            @select="
              key =>
                key === 'batch'
                  ? queueAnchorBatch()
                  : key === 'tasks'
                    ? openTaskDrawer()
                    : selectedSessionId && openSessionDetail(selectedSessionId)
            "
          >
            <NButton quaternary :loading="batchLoading"><SvgIcon icon="mdi:dots-horizontal" /></NButton>
          </NDropdown>
        </div>
      </div>
    </NCard>

    <NAlert v-if="selectedTask?.status === 'failed'" type="error" :bordered="false" show-icon>
      本场最近一次转写失败：{{ selectedTask.error_message || '后台未记录具体错误' }}
      <NButton text type="error" class="ml-8px" @click="openSessionDetail(selectedTask.session_id)">
        检查场次回放
      </NButton>
    </NAlert>
    <NAlert v-if="livePreview" type="info" :bordered="false" show-icon>
      <template #header>正在接收实时话术</template>
      {{ livePreview }}
    </NAlert>

    <div v-if="selectedSessionId" class="grid grid-cols-2 gap-12px lg:grid-cols-4">
      <NCard size="small" :bordered="false" class="card-wrapper">
        <NStatistic label="真实话术片段" :value="segments.length" suffix="段" />
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

    <NGrid :x-gap="16" :y-gap="16" cols="1 xl:3" responsive="screen">
      <NGi span="1 xl:2">
        <NCard title="真实话术内容" :bordered="false" class="card-wrapper">
          <template #header-extra>
            <NRadioGroup v-model:value="viewMode" size="small">
              <NRadioButton value="segments">分段阅读</NRadioButton>
              <NRadioButton value="full">全文阅读</NRadioButton>
            </NRadioGroup>
          </template>
          <NEmpty v-if="!selectedSessionId" description="请选择一个直播场次" class="py-70px" />
          <NSpin v-else :show="loading">
            <template v-if="viewMode === 'segments'">
              <div class="mb-14px grid gap-10px sm:grid-cols-[minmax(0,1fr)_220px]">
                <NInput v-model:value="searchKeyword" clearable placeholder="搜索真实话术内容">
                  <template #prefix><SvgIcon icon="mdi:magnify" /></template>
                </NInput>
                <NSelect
                  :value="categoryFilter || ''"
                  :options="categoryOptions"
                  @update:value="value => (categoryFilter = value || null)"
                />
              </div>
              <div class="mb-10px flex items-center justify-between text-12px text-gray-500">
                <span>显示 {{ filteredSegments.length }} / {{ segments.length }} 个真实片段</span>
                <span>已覆盖到 {{ formatTime(transcribedSeconds) }}</span>
              </div>
              <NEmpty v-if="!filteredSegments.length" description="没有符合条件的话术片段" class="py-70px" />
              <div v-else class="transcript-list h-620px space-y-10px overflow-y-auto pr-6px lt-sm:h-500px">
                <article
                  v-for="item in visibleSegments"
                  :id="`transcript-segment-${item.id}`"
                  :key="item.id"
                  class="segment-card rounded-10px p-13px"
                >
                  <div class="flex items-start gap-12px">
                    <button
                      type="button"
                      class="time-button shrink-0 rounded-7px px-8px py-4px font-mono text-12px font-700"
                      @click="jumpToSegment(item)"
                    >
                      {{ formatTime(item.segment_start) }}
                    </button>
                    <div class="min-w-0 flex-1">
                      <p class="whitespace-pre-wrap text-14px leading-23px">
                        {{ item.text_content || '该片段没有识别出有效文字' }}
                      </p>
                      <div class="mt-8px flex flex-wrap items-center gap-8px">
                        <NTag size="tiny" :bordered="false">{{ item.segment_type || '未分类' }}</NTag>
                        <NTag size="tiny" :type="getStatusType(item.asr_status)" :bordered="false">
                          {{ getStatusLabel(item.asr_status) }}
                        </NTag>
                        <span class="text-11px text-gray-400">
                          {{ Math.max(0, item.segment_end - item.segment_start).toFixed(1) }} 秒
                        </span>
                        <span v-if="item.ai_score !== null" class="text-11px text-gray-400">
                          AI {{ item.ai_score.toFixed(1) }} 分
                        </span>
                      </div>
                    </div>
                    <NButton text class="shrink-0" @click="copyText(item.text_content, '该段话术已复制')">
                      <SvgIcon icon="mdi:content-copy" />
                    </NButton>
                  </div>
                </article>
                <div v-if="visibleSegments.length < filteredSegments.length" class="py-6px text-center">
                  <NButton secondary @click="visibleSegmentLimit += 80">
                    再加载 {{ Math.min(80, filteredSegments.length - visibleSegments.length) }} 段
                  </NButton>
                </div>
              </div>
            </template>
            <template v-else>
              <NEmpty v-if="!fullText && !segments.length" description="本场尚未生成完整话术" class="py-70px" />
              <NScrollbar v-else class="h-680px lt-sm:h-500px">
                <div class="full-text whitespace-pre-wrap rounded-10px p-18px text-14px leading-26px">
                  {{
                    fullText ||
                      segments.map(item => `[${formatTime(item.segment_start)}] ${item.text_content}`).join('\n\n')
                  }}
                </div>
              </NScrollbar>
            </template>
          </NSpin>
        </NCard>
      </NGi>

      <NGi span="1">
        <NSpace vertical :size="16">
          <NCard title="本场话术结构" :bordered="false" class="card-wrapper">
            <NEmpty v-if="!categoryStats.length" description="暂无可统计的真实分类" class="py-36px" />
            <div v-else class="space-y-13px">
              <button
                v-for="item in categoryStats"
                :key="item.name"
                type="button"
                class="w-full text-left"
                @click="
                  categoryFilter = item.name;
                  viewMode = 'segments';
                "
              >
                <div class="mb-5px flex items-center justify-between gap-10px text-12px">
                  <span class="truncate font-600">{{ item.name }}</span>
                  <span class="shrink-0 text-gray-400">{{ item.count }} 段</span>
                </div>
                <NProgress :percentage="item.percent" :show-indicator="false" :height="6" />
              </button>
            </div>
          </NCard>

          <NCard title="时间导航" :bordered="false" class="card-wrapper">
            <template #header-extra>
              <NTag size="small" :bordered="false">{{ segments.length }} 个节点</NTag>
            </template>
            <NEmpty v-if="!segments.length" description="暂无时间节点" class="py-36px" />
            <NVirtualList v-else :items="segments" :item-size="64" item-resizable class="h-370px pr-5px">
              <template #default="{ item }">
                <button
                  type="button"
                  class="timeline-link mb-8px w-full flex items-start gap-8px rounded-8px p-8px text-left"
                  @click="jumpToSegment(item)"
                >
                  <span class="shrink-0 font-mono text-11px font-700 text-primary">
                    {{ formatTime(item.segment_start) }}
                  </span>
                  <span class="line-clamp-2 text-12px leading-18px text-gray-500">
                    {{ item.text_content || '无有效文字' }}
                  </span>
                </button>
              </template>
            </NVirtualList>
          </NCard>
        </NSpace>
      </NGi>
    </NGrid>

    <NDrawer v-model:show="taskDrawerVisible" width="min(620px, 94vw)" placement="right">
      <NDrawerContent title="话术转写任务" closable>
        <div class="mb-14px flex flex-wrap items-center justify-between gap-10px">
          <NRadioGroup v-model:value="taskFilter" size="small">
            <NRadioButton value="all">全部</NRadioButton>
            <NRadioButton value="queued">等待</NRadioButton>
            <NRadioButton value="processing">处理中</NRadioButton>
            <NRadioButton value="completed">完成</NRadioButton>
            <NRadioButton value="failed">失败</NRadioButton>
          </NRadioGroup>
          <span class="text-12px text-gray-500">{{ filteredTasks.length }} 个真实任务</span>
        </div>
        <NEmpty v-if="!filteredTasks.length" description="该状态下暂无任务" class="py-60px" />
        <div v-else class="space-y-10px">
          <NCard v-for="task in filteredTasks" :key="task.id" size="small" :bordered="true">
            <div class="flex items-start justify-between gap-12px">
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-8px">
                  <strong class="text-14px">{{ task.anchor_name }}</strong>
                  <NTag size="tiny" :type="getStatusType(task.status)" :bordered="false">
                    {{ getStatusLabel(task.status) }}
                  </NTag>
                  <NTag
                    v-if="task.status === 'completed'"
                    size="tiny"
                    :type="getPostprocessType(task.postprocess_status)"
                    :bordered="false"
                  >
                    {{ getPostprocessLabel(task.postprocess_status) }}
                  </NTag>
                  <span class="text-11px text-gray-400">任务 #{{ task.id }}</span>
                </div>
                <div class="mt-5px truncate text-12px text-gray-500">{{ task.session_title }}</div>
                <div class="mt-5px flex flex-wrap gap-x-12px gap-y-4px text-11px text-gray-400">
                  <span>{{ formatDate(task.live_start_time) }}</span>
                  <span>{{ formatDuration(task.live_duration_seconds) }}</span>
                  <span>{{ task.segment_count }} 个分段</span>
                  <span v-if="task.retry_count">已尝试 {{ task.retry_count }}/{{ task.max_retries }} 次</span>
                </div>
              </div>
              <NButton size="tiny" secondary @click="selectTask(task)">查看话术</NButton>
            </div>
            <NAlert v-if="task.error_message" type="error" :bordered="false" class="mt-10px">
              {{ task.error_message }}
              <NButton text type="error" class="ml-6px" @click="openSessionDetail(task.session_id)">检查回放</NButton>
            </NAlert>
            <NAlert v-if="task.postprocess_error" type="warning" :bordered="false" class="mt-10px">
              {{ task.postprocess_error }}
            </NAlert>
          </NCard>
        </div>
      </NDrawerContent>
    </NDrawer>
  </NSpace>
</template>

<style scoped>
.status-card {
  border: 1px solid rgba(128, 128, 128, 0.14);
  box-shadow: 0 8px 24px rgba(20, 35, 50, 0.05);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}
.status-card:hover,
.status-card:focus-visible {
  border-color: rgba(32, 128, 240, 0.45);
  box-shadow: 0 12px 30px rgba(20, 35, 50, 0.1);
  transform: translateY(-2px);
  outline: none;
}
.status-icon,
.time-button {
  background: rgba(var(--primary-color), 0.1);
  color: rgb(var(--primary-color));
}
.status-card--warning .status-icon {
  background: rgba(var(--warning-color), 0.12);
  color: rgb(var(--warning-color));
}
.status-card--success .status-icon {
  background: rgba(var(--success-color), 0.12);
  color: rgb(var(--success-color));
}
.status-card--error .status-icon {
  background: rgba(var(--error-color), 0.12);
  color: rgb(var(--error-color));
}
.segment-card,
.full-text {
  border: 1px solid var(--border-color, rgba(128, 128, 128, 0.14));
  background: rgba(128, 128, 128, 0.035);
}
.segment-card {
  scroll-margin-top: 24px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}
.segment-card:hover {
  border-color: rgba(32, 128, 240, 0.38);
  background: rgba(32, 128, 240, 0.045);
}
.timeline-link:hover {
  background: rgba(32, 128, 240, 0.08);
}
</style>
