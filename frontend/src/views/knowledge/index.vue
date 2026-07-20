<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import AnchorAvatar from '@/components/business/anchor-avatar.vue';
import BusinessPageHeader from '@/components/business/page-header.vue';
import { unwrapServiceData } from '@/utils/service';
import {
  askKnowledge,
  fetchKnowledgeItemPage,
  fetchKnowledgeTimeSlicePage,
  fetchKnowledgeTimeSliceStatus,
  fetchLiveSessions,
  getLiveSessionAvatarUrl,
  syncRecentKnowledge
} from '@/service/api/douyin';

defineOptions({ name: 'Knowledge' });

type KnowledgeTab = 'time-slices' | 'whole-session';
type ChatMessage = {
  id: number;
  role: 'user' | 'ai';
  content: string;
  sources?: Api.Douyin.KnowledgeSource[];
  error?: boolean;
};

const router = useRouter();
const message = useMessage();
const sessions = ref<Api.Douyin.LiveSession[]>([]);
const items = ref<Api.Douyin.KnowledgeItem[]>([]);
const timeSlices = ref<Api.Douyin.KnowledgeTimeSlice[]>([]);
const sliceStatus = ref<Api.Douyin.KnowledgeTimeSliceStatus | null>(null);
const activeTab = ref<KnowledgeTab>('time-slices');
const initialLoading = ref(true);
const refreshing = ref(false);
const syncing = ref(false);
const sliceLoading = ref(false);
const itemLoading = ref(false);
const loadError = ref('');

const sliceFilters = reactive({
  keyword: '',
  anchorName: null as string | null,
  evidenceType: null as string | null
});
const slicePagination = reactive({ current: 1, size: 8, total: 0 });
const itemFilters = reactive({
  keyword: '',
  category: null as string | null,
  sourceType: null as string | null
});
const itemPagination = reactive({ current: 1, size: 8, total: 0 });

const evidenceTypeOptions = [
  { label: '全部证据', value: '' },
  { label: '真实话术', value: 'transcript' },
  { label: '用户评论', value: 'comments' },
  { label: '分钟指标', value: 'metrics' },
  { label: '高意向评论', value: 'high_intent' }
];
const categoryOptions = [
  { label: '全部分类', value: '' },
  { label: '直播数据', value: '直播数据' },
  { label: '互动评论', value: '互动评论' },
  { label: '优质话术', value: '优质话术' },
  { label: '分析结论', value: '分析结论' }
];
const sourceTypeOptions = [
  { label: '全部来源', value: '' },
  { label: '直播数据', value: 'live_data' },
  { label: '用户评论', value: 'comments' },
  { label: '主播话术', value: 'transcript' },
  { label: 'AI 分析', value: 'ai_analysis' }
];
const assistantCategoryOptions = categoryOptions.map(option => ({ ...option }));
const suggestedQuestions = [
  '哪些用户问题最适合引导私信领取资料？',
  '哪些选址避坑话术带来的互动更高？',
  '最近场次中用户最常问哪些开店预算问题？',
  '找出有明确地区和预算的高意向评论'
];
const followUpQuestions = [
  '对应哪些主播和场次？',
  '给出评论或话术原文证据',
  '不同场次之间有什么差异？',
  '整理成下一场可执行动作'
];

const sessionById = computed(() => new Map(sessions.value.map(session => [session.id, session])));
const anchorOptions = computed(() => {
  const names = new Set(
    sessions.value.map(session => session.anchor_name).filter((name): name is string => Boolean(name))
  );
  return Array.from(names)
    .sort((a, b) => a.localeCompare(b, 'zh-CN'))
    .map(name => ({ label: name, value: name }));
});
const summaryCards = computed(() => [
  {
    key: '',
    label: '知识时间片',
    value: sliceStatus.value?.slice_count || 0,
    hint: `覆盖 ${sliceStatus.value?.session_count || 0} 场真实直播`,
    icon: 'mdi:timeline-text-outline',
    tone: 'primary'
  },
  {
    key: 'transcript',
    label: '话术证据',
    value: sliceStatus.value?.transcript_slice_count || 0,
    hint: '可定位主播原话',
    icon: 'mdi:waveform',
    tone: 'success'
  },
  {
    key: 'comments',
    label: '评论证据',
    value: sliceStatus.value?.comment_slice_count || 0,
    hint: '按平台时间精确绑定',
    icon: 'mdi:comment-text-multiple-outline',
    tone: 'info'
  },
  {
    key: 'metrics',
    label: '指标证据',
    value: sliceStatus.value?.metric_slice_count || 0,
    hint: '包含在线人数变化',
    icon: 'mdi:chart-line',
    tone: 'warning'
  },
  {
    key: 'high_intent',
    label: '高意向片段',
    value: sliceStatus.value?.high_intent_slice_count || 0,
    hint: '优先用于私信承接复盘',
    icon: 'mdi:account-star-outline',
    tone: 'danger'
  }
]);

async function loadOverview() {
  const [statusResponse, sessionResponse] = await Promise.all([fetchKnowledgeTimeSliceStatus(), fetchLiveSessions()]);
  sliceStatus.value = unwrapServiceData(statusResponse, '知识库覆盖状态读取失败');
  sessions.value = unwrapServiceData(sessionResponse, '直播场次读取失败');
}

async function loadTimeSlices() {
  sliceLoading.value = true;
  try {
    const response = await fetchKnowledgeTimeSlicePage({
      current: slicePagination.current,
      size: slicePagination.size,
      keyword: sliceFilters.keyword.trim() || undefined,
      anchor_name: sliceFilters.anchorName || undefined,
      evidence_type: sliceFilters.evidenceType || undefined
    });
    const page = unwrapServiceData(response, '时间片证据读取失败');
    timeSlices.value = page.records;
    slicePagination.total = page.total;
  } finally {
    sliceLoading.value = false;
  }
}

async function loadKnowledgeItems() {
  itemLoading.value = true;
  try {
    const response = await fetchKnowledgeItemPage({
      current: itemPagination.current,
      size: itemPagination.size,
      keyword: itemFilters.keyword.trim() || undefined,
      category: itemFilters.category || undefined,
      source_type: itemFilters.sourceType || undefined
    });
    const page = unwrapServiceData(response, '整场知识读取失败');
    items.value = page.records;
    itemPagination.total = page.total;
  } finally {
    itemLoading.value = false;
  }
}

async function loadPage() {
  initialLoading.value = true;
  loadError.value = '';
  try {
    await Promise.all([loadOverview(), loadTimeSlices(), loadKnowledgeItems()]);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '知识库加载失败，请检查后端服务';
    message.error(loadError.value);
  } finally {
    initialLoading.value = false;
  }
}

async function refreshPage() {
  refreshing.value = true;
  try {
    await Promise.all([loadOverview(), loadTimeSlices(), loadKnowledgeItems()]);
    loadError.value = '';
    message.success('知识证据与覆盖状态已刷新');
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '知识库刷新失败';
    message.error(loadError.value);
  } finally {
    refreshing.value = false;
  }
}

async function syncRecent() {
  syncing.value = true;
  try {
    const response = await syncRecentKnowledge(20);
    const data = unwrapServiceData(response, '同步知识库失败');
    message.success(
      `已同步 ${data.session_count || 0} 场，新增 ${data.time_slices_created || 0} 个时间片，更新 ${data.time_slices_updated || 0} 个`
    );
    slicePagination.current = 1;
    itemPagination.current = 1;
    await Promise.all([loadOverview(), loadTimeSlices(), loadKnowledgeItems()]);
  } catch {
    message.error('同步知识库失败，请稍后重试');
  } finally {
    syncing.value = false;
  }
}

function applySliceFilters() {
  slicePagination.current = 1;
  void loadTimeSlices();
}

function resetSliceFilters() {
  sliceFilters.keyword = '';
  sliceFilters.anchorName = null;
  sliceFilters.evidenceType = null;
  applySliceFilters();
}

function applyItemFilters() {
  itemPagination.current = 1;
  void loadKnowledgeItems();
}

function resetItemFilters() {
  itemFilters.keyword = '';
  itemFilters.category = null;
  itemFilters.sourceType = null;
  applyItemFilters();
}

async function selectSummaryEvidence(evidenceType: string) {
  activeTab.value = 'time-slices';
  sliceFilters.evidenceType = evidenceType || null;
  applySliceFilters();
  await nextTick();
  document.querySelector('.evidence-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function changeSlicePage(current: number) {
  slicePagination.current = current;
  void loadTimeSlices();
}

function changeSlicePageSize(size: number) {
  slicePagination.size = size;
  slicePagination.current = 1;
  void loadTimeSlices();
}

function changeItemPage(current: number) {
  itemPagination.current = current;
  void loadKnowledgeItems();
}

function changeItemPageSize(size: number) {
  itemPagination.size = size;
  itemPagination.current = 1;
  void loadKnowledgeItems();
}

function formatOffset(seconds: number) {
  const value = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = value % 60;
  return [hours, minutes, secs].map(item => String(item).padStart(2, '0')).join(':');
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function parseStoredDate(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasTimezone ? value : `${value}Z`);
}

function formatStoredDateTime(value: string | null | undefined) {
  if (!value) return '-';
  return parseStoredDate(value).toLocaleString('zh-CN', { hour12: false });
}

function formatRelativeTime(value: string | null | undefined) {
  if (!value) return '尚未同步';
  const diff = Date.now() - parseStoredDate(value).getTime();
  if (diff < 60_000) return '刚刚更新';
  if (diff < 3_600_000) return `${Math.max(1, Math.floor(diff / 60_000))} 分钟前更新`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前更新`;
  return formatStoredDateTime(value);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0);
}

function getSessionAvatar(sessionId: number) {
  const session = sessionById.value.get(sessionId);
  return session?.anchor_avatar_url ? getLiveSessionAvatarUrl(sessionId) : undefined;
}

function openSession(sessionId: number | null | undefined) {
  if (!sessionId) return;
  void router.push({ name: 'live-session-detail', params: { id: String(sessionId) } });
}

function sourceTypeLabel(sourceType: string | null | undefined) {
  const labels: Record<string, string> = {
    live_data: '直播数据',
    comments: '用户评论',
    transcript: '主播话术',
    ai_analysis: 'AI 分析',
    time_slice: '知识时间片'
  };
  return labels[sourceType || ''] || sourceType || '未知来源';
}

function sourceTimeLabel(source: Api.Douyin.KnowledgeSource) {
  if (source.time_range) return source.time_range;
  if (typeof source.slice_start_seconds === 'number') {
    return `${formatOffset(source.slice_start_seconds)} - ${formatOffset(source.slice_end_seconds || source.slice_start_seconds)}`;
  }
  return '';
}

async function copyText(content: string) {
  await navigator.clipboard.writeText(content);
  message.success('内容已复制');
}

const question = ref('');
const assistantCategory = ref<string | null>(null);
const chatting = ref(false);
const messages = ref<ChatMessage[]>([]);
const chatEndRef = ref<HTMLElement | null>(null);
const conversationTurnCount = computed(() => messages.value.filter(item => item.role === 'user').length);
let messageId = 0;

async function scrollChatToEnd() {
  await nextTick();
  chatEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

async function sendQuestion(preset?: string) {
  const content = (preset || question.value).trim();
  if (!content || chatting.value) return;
  const history = messages.value
    .filter(item => !item.error)
    .slice(-8)
    .map<Api.Douyin.KnowledgeChatHistory>(item => ({
      role: item.role === 'ai' ? 'assistant' : 'user',
      content:
        item.role === 'ai' && item.sources?.length
          ? `${item.content}\n引用场次：${Array.from(
              new Set(item.sources.map(source => source.session_id).filter((id): id is number => Boolean(id)))
            )
              .map(id => `场次${id}`)
              .join('、')}`
          : item.content
    }));
  messages.value.push({ id: ++messageId, role: 'user', content });
  question.value = '';
  chatting.value = true;
  await scrollChatToEnd();

  try {
    const response = await askKnowledge(content, assistantCategory.value || undefined, history);
    const answer = unwrapServiceData(response, '知识检索请求失败');
    messages.value.push({
      id: ++messageId,
      role: 'ai',
      content: answer.answer || '当前真实知识库没有返回可用结论。',
      sources: answer.sources || []
    });
  } catch (error) {
    messages.value.push({
      id: ++messageId,
      role: 'ai',
      content: error instanceof Error ? error.message : '知识检索请求失败，请确认 AI 服务状态后重试。',
      error: true
    });
  } finally {
    chatting.value = false;
    await scrollChatToEnd();
  }
}

function handleQuestionKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  void sendQuestion();
}

function clearConversation() {
  messages.value = [];
  message.success('本次问答已清空');
}

onMounted(loadPage);
</script>

<template>
  <div class="knowledge-page business-page">
    <BusinessPageHeader
      class="order-1"
      title="直播经营知识库"
      description="把真实场次拆成可检索证据，统一关联主播话术、用户评论和分钟指标，为零食店避坑直播复盘提供可追溯依据。"
      icon="mdi:book-open-page-variant-outline"
      :status="`覆盖 ${sliceStatus?.session_count || 0} 场直播`"
      :status-type="sliceStatus?.session_count ? 'success' : 'warning'"
    >
      <template #actions>
        <NButton secondary :loading="refreshing" @click="refreshPage">
          <template #icon><SvgIcon icon="mdi:refresh" /></template>
          刷新证据
        </NButton>
        <NButton type="primary" :loading="syncing" @click="syncRecent">
          <template #icon><SvgIcon icon="mdi:database-sync-outline" /></template>
          同步最近 20 场
        </NButton>
      </template>
      <div class="flex flex-wrap gap-x-18px gap-y-6px text-12px text-gray-500">
        <span>固定 {{ (sliceStatus?.slice_seconds || 300) / 60 }} 分钟证据窗口</span>
        <span>整场知识 {{ formatNumber(sliceStatus?.knowledge_item_count || 0) }} 条</span>
        <span>{{ formatRelativeTime(sliceStatus?.latest_updated_at) }}</span>
      </div>
    </BusinessPageHeader>

    <NAlert v-if="loadError" class="order-2" type="warning" :bordered="false" show-icon>
      知识证据未能完整更新：{{ loadError }}
      <template #action>
        <NButton size="small" secondary :loading="initialLoading || refreshing" @click="loadPage">重新加载</NButton>
      </template>
    </NAlert>

    <div class="order-3 grid grid-cols-2 gap-12px xl:grid-cols-5">
      <button
        v-for="card in summaryCards"
        :key="card.key"
        type="button"
        class="business-clickable-card summary-card"
        :class="[
          `summary-card--${card.tone}`,
          { 'summary-card--active': (sliceFilters.evidenceType || '') === card.key }
        ]"
        :aria-pressed="(sliceFilters.evidenceType || '') === card.key"
        @click="selectSummaryEvidence(card.key)"
      >
        <div class="flex items-start justify-between gap-8px">
          <div>
            <div class="text-12px text-gray-500">{{ card.label }}</div>
            <div class="mt-5px text-26px font-800 tracking-tight">{{ formatNumber(card.value) }}</div>
          </div>
          <span class="summary-card__icon"><SvgIcon :icon="card.icon" class="text-21px" /></span>
        </div>
        <div class="mt-8px truncate text-left text-11px text-gray-400">{{ card.hint }}</div>
      </button>
    </div>

    <NAlert v-if="sliceStatus?.unmapped_comment_count" class="order-4" type="warning" :bordered="false" show-icon>
      有 {{ sliceStatus.unmapped_comment_count }} 条评论缺少可靠平台时间，系统已单独保留，不会错误绑定到话术片段。
    </NAlert>

    <div class="contents">
      <NCard :bordered="false" class="card-wrapper evidence-card order-5">
        <template #header>
          <div>
            <div class="text-16px font-800">真实证据库</div>
            <div class="mt-3px text-12px font-normal text-gray-500">搜索、筛选并回到原直播场次核对上下文</div>
          </div>
        </template>
        <template #header-extra>
          <NTag round :bordered="false" type="info">
            {{
              activeTab === 'time-slices'
                ? `${formatNumber(slicePagination.total)} 个时间片`
                : `${formatNumber(itemPagination.total)} 条知识`
            }}
          </NTag>
        </template>

        <NTabs v-model:value="activeTab" type="line" animated>
          <NTabPane name="time-slices" tab="时间片证据">
            <div
              class="mb-14px grid grid-cols-[minmax(220px,1fr)_190px_170px_auto] gap-8px lt-lg:grid-cols-2 lt-sm:grid-cols-1"
            >
              <NInput
                v-model:value="sliceFilters.keyword"
                clearable
                placeholder="搜索主播、标题、话术或评论"
                @keyup.enter="applySliceFilters"
              >
                <template #prefix><SvgIcon icon="mdi:magnify" /></template>
              </NInput>
              <NSelect
                v-model:value="sliceFilters.anchorName"
                clearable
                filterable
                :options="anchorOptions"
                placeholder="全部主播"
              />
              <NSelect
                v-model:value="sliceFilters.evidenceType"
                clearable
                :options="evidenceTypeOptions"
                placeholder="全部证据"
              />
              <div class="flex gap-8px">
                <NButton type="primary" secondary @click="applySliceFilters">查询</NButton>
                <NButton quaternary @click="resetSliceFilters">重置</NButton>
              </div>
            </div>

            <NSpin :show="initialLoading || sliceLoading">
              <NEmpty v-if="!timeSlices.length && !sliceLoading" class="py-56px" description="没有符合条件的真实时间片">
                <template #extra><NButton secondary @click="resetSliceFilters">清除筛选</NButton></template>
              </NEmpty>
              <div v-else class="flex flex-col gap-10px">
                <article v-for="slice in timeSlices" :key="slice.id" class="evidence-item">
                  <div class="flex flex-wrap items-start justify-between gap-10px">
                    <div class="flex min-w-0 items-center gap-10px">
                      <AnchorAvatar
                        :size="38"
                        :src="getSessionAvatar(slice.session_id)"
                        :name="slice.anchor_name || '未知主播'"
                      />
                      <div class="min-w-0">
                        <div class="truncate text-14px font-700">{{ slice.anchor_name || '未知主播' }}</div>
                        <div class="mt-2px truncate text-12px text-gray-500">
                          {{ slice.session_title || '未命名直播' }} · 场次 #{{ slice.session_id }}
                        </div>
                      </div>
                    </div>
                    <div class="flex flex-wrap items-center justify-end gap-8px">
                      <NTag v-if="slice.transcript_text" size="small" round :bordered="false" type="success">话术</NTag>
                      <NTag v-if="slice.comment_count" size="small" round :bordered="false" type="info">评论</NTag>
                      <NTag v-if="slice.metric_point_count" size="small" round :bordered="false" type="warning">
                        指标
                      </NTag>
                      <NTag v-if="slice.high_intent_comment_count" size="small" round :bordered="false" type="error">
                        高意向 {{ slice.high_intent_comment_count }}
                      </NTag>
                      <NTag size="small" round>
                        {{ formatOffset(slice.slice_start_seconds) }} - {{ formatOffset(slice.slice_end_seconds) }}
                      </NTag>
                    </div>
                  </div>

                  <div class="mt-10px grid grid-cols-4 gap-8px lt-sm:grid-cols-2">
                    <div class="metric-chip">
                      <span>评论</span>
                      <strong>{{ slice.comment_count }}</strong>
                    </div>
                    <div class="metric-chip">
                      <span>采样点</span>
                      <strong>{{ slice.metric_point_count }}</strong>
                    </div>
                    <div class="metric-chip">
                      <span>平均在线</span>
                      <strong>{{ Math.round(slice.avg_online_count) }}</strong>
                    </div>
                    <div class="metric-chip">
                      <span>峰值在线</span>
                      <strong>{{ slice.peak_online_count }}</strong>
                    </div>
                  </div>

                  <div v-if="slice.transcript_text" class="evidence-block mt-10px">
                    <div class="mb-4px flex items-center gap-5px text-11px font-700 text-green-600">
                      <SvgIcon icon="mdi:waveform" />
                      主播原话
                    </div>
                    <p class="line-clamp-3 m-0 whitespace-pre-wrap text-13px leading-21px">
                      {{ slice.transcript_text }}
                    </p>
                  </div>
                  <div v-if="slice.comments_text" class="evidence-block mt-8px">
                    <div class="mb-4px flex items-center gap-5px text-11px font-700 text-blue-600">
                      <SvgIcon icon="mdi:comment-text-outline" />
                      用户评论
                    </div>
                    <p class="line-clamp-2 m-0 whitespace-pre-wrap text-13px leading-21px">{{ slice.comments_text }}</p>
                  </div>
                  <div v-if="!slice.transcript_text && !slice.comments_text" class="mt-10px text-12px text-gray-400">
                    本时间片只有分钟指标证据，没有可展示的话术或评论原文。
                  </div>

                  <div
                    class="mt-10px flex items-center justify-between gap-10px border-t border-gray-100 pt-8px dark:border-dark-100"
                  >
                    <span class="text-11px text-gray-400">平台时间 {{ formatDateTime(slice.slice_start_time) }}</span>
                    <NButton text type="primary" size="small" @click="openSession(slice.session_id)">
                      查看原场次
                      <template #icon><SvgIcon icon="mdi:open-in-new" /></template>
                    </NButton>
                  </div>
                </article>
              </div>
            </NSpin>

            <div v-if="slicePagination.total" class="mt-16px flex justify-end overflow-x-auto pb-2px">
              <NPagination
                :page="slicePagination.current"
                :page-size="slicePagination.size"
                :item-count="slicePagination.total"
                :page-sizes="[8, 15, 30]"
                show-size-picker
                :prefix="({ itemCount }) => `共 ${itemCount} 个时间片`"
                @update:page="changeSlicePage"
                @update:page-size="changeSlicePageSize"
              />
            </div>
          </NTabPane>

          <NTabPane name="whole-session" tab="整场知识">
            <div
              class="mb-14px grid grid-cols-[minmax(220px,1fr)_160px_160px_auto] gap-8px lt-lg:grid-cols-2 lt-sm:grid-cols-1"
            >
              <NInput
                v-model:value="itemFilters.keyword"
                clearable
                placeholder="搜索标题或知识内容"
                @keyup.enter="applyItemFilters"
              >
                <template #prefix><SvgIcon icon="mdi:magnify" /></template>
              </NInput>
              <NSelect
                v-model:value="itemFilters.category"
                clearable
                :options="categoryOptions"
                placeholder="全部分类"
              />
              <NSelect
                v-model:value="itemFilters.sourceType"
                clearable
                :options="sourceTypeOptions"
                placeholder="全部来源"
              />
              <div class="flex gap-8px">
                <NButton type="primary" secondary @click="applyItemFilters">查询</NButton>
                <NButton quaternary @click="resetItemFilters">重置</NButton>
              </div>
            </div>

            <NSpin :show="initialLoading || itemLoading">
              <NEmpty v-if="!items.length && !itemLoading" class="py-56px" description="没有符合条件的整场知识" />
              <div v-else class="grid grid-cols-2 gap-10px lt-lg:grid-cols-1">
                <article v-for="item in items" :key="item.id" class="knowledge-item">
                  <div class="flex items-start justify-between gap-8px">
                    <div class="min-w-0">
                      <div class="line-clamp-2 text-14px font-700">{{ item.title || `知识条目 #${item.id}` }}</div>
                      <div class="mt-4px text-11px text-gray-400">{{ formatStoredDateTime(item.created_at) }}</div>
                    </div>
                    <NTag size="small" round :bordered="false" type="info">{{ item.category || '未分类' }}</NTag>
                  </div>
                  <p
                    class="line-clamp-5 mb-0 mt-10px whitespace-pre-wrap text-13px leading-21px text-gray-600 dark:text-gray-300"
                  >
                    {{ item.content || '暂无真实内容' }}
                  </p>
                  <div
                    class="mt-10px flex items-center justify-between border-t border-gray-100 pt-8px dark:border-dark-100"
                  >
                    <span class="text-11px text-gray-400">{{ sourceTypeLabel(item.source_type) }}</span>
                    <NButton
                      v-if="item.session_id"
                      text
                      type="primary"
                      size="small"
                      @click="openSession(item.session_id)"
                    >
                      查看场次
                    </NButton>
                  </div>
                </article>
              </div>
            </NSpin>

            <div v-if="itemPagination.total" class="mt-16px flex justify-end overflow-x-auto pb-2px">
              <NPagination
                :page="itemPagination.current"
                :page-size="itemPagination.size"
                :item-count="itemPagination.total"
                :page-sizes="[8, 15, 30]"
                show-size-picker
                :prefix="({ itemCount }) => `共 ${itemCount} 条知识`"
                @update:page="changeItemPage"
                @update:page-size="changeItemPageSize"
              />
            </div>
          </NTabPane>
        </NTabs>
      </NCard>

      <NCard :bordered="false" class="card-wrapper assistant-card order-2">
        <template #header>
          <div>
            <div class="flex items-center gap-8px text-16px font-800">
              <SvgIcon icon="mdi:message-processing-outline" class="text-primary" />
              知识库自由问答
            </div>
            <div class="mt-3px text-12px font-normal text-gray-500">
              连续追问真实话术、评论、指标与复盘结论，每条回答都能回到原场次核验
            </div>
          </div>
        </template>
        <template #header-extra>
          <NButton v-if="messages.length" secondary size="small" @click="clearConversation">
            <template #icon><SvgIcon icon="mdi:message-plus-outline" /></template>
            新对话
          </NButton>
        </template>

        <aside class="assistant-sidebar">
          <div class="assistant-context">
            <div class="flex items-center justify-between gap-8px">
              <span class="text-12px font-700">本次检索范围</span>
              <NTag size="small" round :bordered="false" type="success">
                {{ sliceStatus?.session_count || 0 }} 场可追溯
              </NTag>
            </div>
            <NSelect
              v-model:value="assistantCategory"
              class="mt-8px"
              clearable
              :options="assistantCategoryOptions"
              placeholder="全部知识分类"
            />
            <div class="mt-8px grid grid-cols-2 gap-8px text-11px text-gray-500">
              <span>{{ formatNumber(sliceStatus?.transcript_slice_count || 0) }} 个话术片段</span>
              <span>{{ formatNumber(sliceStatus?.comment_slice_count || 0) }} 个评论片段</span>
              <span>{{ formatNumber(sliceStatus?.metric_slice_count || 0) }} 个指标片段</span>
              <span>{{ formatNumber(sliceStatus?.knowledge_item_count || 0) }} 条整场知识</span>
            </div>
          </div>

          <div class="mt-14px">
            <div class="flex items-center justify-between gap-8px">
              <div class="text-12px font-700">{{ messages.length ? '继续追问' : '推荐提问' }}</div>
              <span v-if="messages.length" class="text-11px text-gray-400">已问 {{ conversationTurnCount }} 轮</span>
            </div>
            <div class="mt-8px grid gap-8px">
              <button
                v-for="prompt in messages.length ? followUpQuestions : suggestedQuestions"
                :key="prompt"
                type="button"
                class="question-prompt business-focus-ring"
                :disabled="chatting"
                @click="sendQuestion(prompt)"
              >
                <SvgIcon icon="mdi:arrow-top-right" class="mt-2px shrink-0 text-primary" />
                <span>{{ prompt }}</span>
              </button>
            </div>
          </div>
          <NAlert class="mt-14px" type="info" :bordered="false" show-icon>
            回答只使用已同步的真实数据；证据不足时不会猜测。
          </NAlert>
        </aside>

        <section class="assistant-main">
          <NScrollbar class="chat-scroll">
            <div class="min-h-320px pr-8px">
              <div v-if="!messages.length" class="chat-welcome">
                <span class="chat-welcome__icon"><SvgIcon icon="mdi:database-search-outline" /></span>
                <div class="mt-12px text-18px font-800">从真实直播数据里找答案</div>
                <p class="mb-0 mt-8px max-w-520px text-center text-13px leading-22px text-gray-500">
                  可以直接询问主播话术、用户评论、开店地区与预算、高意向线索、分钟趋势或跨场次差异，也可以在回答后继续追问“对应哪些场次”。
                </p>
                <NTag class="mt-12px" round :bordered="false" type="success">已连接真实知识证据</NTag>
              </div>
              <div v-for="chatMessage in messages" :key="chatMessage.id" class="mb-12px">
                <div :class="chatMessage.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
                  <div
                    class="chat-bubble"
                    :class="[
                      chatMessage.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--ai',
                      { 'chat-bubble--error': chatMessage.error }
                    ]"
                  >
                    <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
                    <div v-if="chatMessage.role === 'ai' && !chatMessage.error" class="mt-8px flex justify-end">
                      <NButton text size="tiny" @click="copyText(chatMessage.content)">
                        <template #icon><SvgIcon icon="mdi:content-copy" /></template>
                        复制
                      </NButton>
                    </div>
                  </div>
                </div>

                <NCollapse v-if="chatMessage.sources?.length" class="source-collapse" arrow-placement="right">
                  <NCollapseItem :title="`查看 ${chatMessage.sources.length} 条真实来源`" :name="chatMessage.id">
                    <div class="grid grid-cols-2 gap-8px lt-lg:grid-cols-1">
                      <button
                        v-for="source in chatMessage.sources"
                        :key="`${source.source_type}-${source.id}`"
                        type="button"
                        class="source-card"
                        :disabled="!source.session_id"
                        @click="openSession(source.session_id)"
                      >
                        <div class="flex items-start justify-between gap-8px">
                          <div class="min-w-0 text-left">
                            <div class="truncate text-12px font-700">{{ source.title || '未命名来源' }}</div>
                            <div class="mt-2px text-11px text-gray-400">
                              {{ source.anchor_name || sourceTypeLabel(source.source_type) }}
                              <span v-if="sourceTimeLabel(source)">· {{ sourceTimeLabel(source) }}</span>
                            </div>
                          </div>
                          <SvgIcon
                            v-if="source.session_id"
                            icon="mdi:open-in-new"
                            class="mt-1px shrink-0 text-primary"
                          />
                        </div>
                        <div
                          v-if="source.excerpt"
                          class="line-clamp-2 mt-5px text-left text-11px leading-18px text-gray-500"
                        >
                          {{ source.excerpt }}
                        </div>
                      </button>
                    </div>
                  </NCollapseItem>
                </NCollapse>
              </div>

              <div v-if="chatting" class="mb-12px flex justify-start">
                <div class="chat-bubble chat-bubble--ai flex items-center gap-8px text-gray-500">
                  <NSpin :size="14" />
                  正在检索真实话术、评论和指标…
                </div>
              </div>
              <div ref="chatEndRef" />
            </div>
          </NScrollbar>

          <div class="chat-composer">
            <div class="mb-8px flex items-center justify-between gap-8px">
              <span class="flex items-center gap-5px text-12px font-700">
                <SvgIcon icon="mdi:pencil-outline" class="text-primary" />
                在这里输入你的问题
              </span>
              <span class="text-11px text-gray-400">Enter 发送</span>
            </div>
            <NInput
              v-model:value="question"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              maxlength="500"
              show-count
              placeholder="输入复盘问题，Enter 发送，Shift+Enter 换行"
              :disabled="chatting"
              @keydown="handleQuestionKeydown"
            />
            <div class="mt-8px flex items-center justify-between gap-8px">
              <span class="text-11px text-gray-400">回答会附带场次与时间片来源</span>
              <NButton
                type="primary"
                :loading="chatting"
                :disabled="!question.trim() || chatting"
                @click="sendQuestion()"
              >
                <template #icon><SvgIcon icon="mdi:send" /></template>
                发送
              </NButton>
            </div>
          </div>
        </section>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.summary-card {
  --summary-tone: rgb(var(--primary-color));
  border: 1px solid transparent;
  border-radius: 14px;
  background: var(--card-color);
  padding: 15px;
  text-align: left;
  box-shadow: 0 5px 18px rgb(15 23 42 / 4%);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.summary-card:hover,
.summary-card--active {
  border-color: color-mix(in srgb, var(--summary-tone) 42%, transparent);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--summary-tone) 12%, transparent);
  transform: translateY(-2px);
}

.summary-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 11px;
  color: var(--summary-tone);
  background: color-mix(in srgb, var(--summary-tone) 12%, transparent);
}

.summary-card--success {
  --summary-tone: rgb(var(--success-color));
}
.summary-card--info {
  --summary-tone: rgb(var(--primary-color));
}
.summary-card--warning {
  --summary-tone: rgb(var(--warning-color));
}
.summary-card--danger {
  --summary-tone: rgb(var(--error-color));
}

.assistant-card :deep(.n-card-content) {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
  padding-top: 8px;
}

.assistant-sidebar {
  grid-column: 2;
  grid-row: 1;
}

.assistant-main {
  display: flex;
  grid-column: 1;
  grid-row: 1;
  height: 410px;
  min-width: 0;
  flex-direction: column;
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 14px;
  background: color-mix(in srgb, var(--card-color) 97%, rgb(var(--primary-color)) 3%);
  overflow: hidden;
}

.chat-scroll {
  min-height: 0;
  flex: 1;
  padding: 16px 12px 8px 16px;
}

.chat-welcome {
  display: flex;
  min-height: 310px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 28px 18px;
}

.chat-welcome__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 58px;
  height: 58px;
  border-radius: 18px;
  color: rgb(var(--primary-color));
  background: linear-gradient(135deg, rgb(var(--primary-color) / 15%), rgb(24 160 88 / 10%));
  font-size: 28px;
}

.chat-composer {
  position: relative;
  z-index: 1;
  flex: none;
  border-top: 1px solid rgb(148 163 184 / 14%);
  background: var(--card-color);
  padding: 12px 14px 14px;
}

.evidence-item,
.knowledge-item {
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 12px;
  background: color-mix(in srgb, var(--card-color) 95%, rgb(var(--primary-color)) 5%);
  padding: 13px;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.evidence-item:hover,
.knowledge-item:hover {
  border-color: rgb(var(--primary-color) / 26%);
  box-shadow: 0 8px 24px rgb(15 23 42 / 5%);
}

.metric-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  border-radius: 8px;
  background: rgb(148 163 184 / 8%);
  padding: 7px 9px;
  font-size: 11px;
  color: rgb(100 116 139);
}

.metric-chip strong {
  color: var(--text-color-1);
  font-size: 13px;
}

.evidence-block {
  border-left: 3px solid rgb(var(--primary-color) / 36%);
  border-radius: 0 8px 8px 0;
  background: rgb(148 163 184 / 7%);
  padding: 8px 10px;
}

.assistant-context {
  border: 1px solid rgb(var(--primary-color) / 14%);
  border-radius: 11px;
  background: linear-gradient(135deg, rgb(var(--primary-color) / 8%), rgb(32 128 240 / 4%));
  padding: 11px;
}

.question-prompt {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  width: 100%;
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 9px;
  background: transparent;
  padding: 8px 9px;
  text-align: left;
  color: var(--text-color-2);
  font-size: 12px;
  line-height: 18px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.question-prompt:hover {
  border-color: rgb(var(--primary-color) / 34%);
  background: rgb(var(--primary-color) / 6%);
}

.chat-bubble {
  max-width: 92%;
  border-radius: 12px;
  padding: 9px 11px;
  font-size: 13px;
  line-height: 21px;
}

.chat-bubble--user {
  border-bottom-right-radius: 4px;
  background: rgb(var(--primary-color));
  color: white;
}

.chat-bubble--ai {
  border-bottom-left-radius: 4px;
  background: rgb(148 163 184 / 11%);
  color: var(--text-color-1);
}

.chat-bubble--error {
  background: rgb(208 48 80 / 9%);
  color: #d03050;
}

.source-card {
  width: 100%;
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 9px;
  background: var(--card-color);
  padding: 8px 9px;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.source-card:not(:disabled):hover {
  border-color: rgb(var(--primary-color) / 32%);
  background: rgb(var(--primary-color) / 4%);
}

.source-collapse {
  margin-top: 7px;
  border-radius: 10px;
  background: rgb(148 163 184 / 6%);
  padding: 0 10px;
}

.source-collapse :deep(.n-collapse-item__header-main) {
  color: rgb(var(--primary-color));
  font-size: 12px;
  font-weight: 700;
}

@media (max-width: 1024px) {
  .assistant-card :deep(.n-card-content) {
    grid-template-columns: 1fr;
  }

  .assistant-sidebar,
  .assistant-main {
    grid-column: 1;
  }

  .assistant-main {
    grid-row: 1;
  }

  .assistant-sidebar {
    grid-row: 2;
  }
}

@media (min-width: 1025px) and (max-height: 800px) {
  .assistant-sidebar,
  .assistant-main {
    height: 270px;
  }

  .assistant-sidebar {
    overflow-y: auto;
    padding-right: 4px;
  }

  .chat-welcome {
    min-height: 230px;
  }
}

@media (max-width: 640px) {
  .summary-card {
    padding: 12px;
  }

  .assistant-main {
    height: min(560px, calc(100vh - 150px));
  }

  .chat-scroll {
    padding: 12px 8px 6px 12px;
  }

  .chat-composer {
    padding: 10px 11px 12px;
  }
}
</style>
