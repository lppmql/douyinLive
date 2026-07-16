<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { TagProps } from 'naive-ui';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import BusinessPageHeader from '@/components/business/page-header.vue';
import {
  fetchAnalysisReports,
  fetchLiveSessions,
  fetchReviewWorkbench,
  generateSessionReview,
  optimizeSession,
  scoreSession
} from '@/service/api/douyin';

defineOptions({ name: 'Analysis' });

type ActionStage = '' | 'evidence' | 'score' | 'optimize' | 'score-only' | 'optimize-only';

const router = useRouter();
const message = useMessage();
const sessions = ref<Api.Douyin.LiveSession[]>([]);
const selectedSessionId = ref<number | null>(null);
const workbench = ref<Api.Douyin.ReviewWorkbench | null>(null);
const sessionReports = ref<Api.Douyin.AnalysisReport[]>([]);
const scoreResult = ref<Api.Douyin.AiScoreResult | null>(null);
const optimizeResult = ref<Api.Douyin.AiOptimizationResult | null>(null);
const loading = ref(true);
const contextLoading = ref(false);
const refreshing = ref(false);
const actionStage = ref<ActionStage>('');
const activeTab = ref<'overview' | 'evidence' | 'history'>('overview');
let contextRequestId = 0;

const selectedSession = computed(
  () => sessions.value.find(item => item.id === selectedSessionId.value) || null
);
const analysisReady = computed(() => Boolean(workbench.value?.completeness.analysis_ready));
const coveredDomainCount = computed(
  () => workbench.value?.domain_coverage.filter(item => item.covered).length || 0
);
const openFindingCount = computed(
  () => workbench.value?.findings.filter(item => item.status === 'open').length || 0
);
const latestReport = computed(() => sessionReports.value[0] || null);
const actionBusy = computed(() => Boolean(actionStage.value));

const sessionOptions = computed(() =>
  sessions.value.map(session => ({
    value: session.id,
    label: `${session.anchor_name || '未知主播'} · ${formatDate(session.live_start_time)} · ${formatDuration(session.live_duration_seconds)} · ${session.live_status === 'live' ? '直播中' : '已结束'}`
  }))
);

const scoreMetrics = computed(() => {
  if (!scoreResult.value) return [];
  const result = scoreResult.value;
  const metrics = [
    { key: 'knowledge', label: '知识价值', value: result.knowledge_value_score, max: 10, icon: 'mdi:book-open-page-variant-outline' },
    { key: 'completeness', label: '内容完整', value: result.completeness_score, max: 10, icon: 'mdi:format-list-checks' },
    { key: 'interaction', label: '问题互动', value: result.interactivity_score, max: 10, icon: 'mdi:comment-question-outline' },
    { key: 'lead', label: '私信承接', value: result.lead_guidance_score, max: 10, icon: 'mdi:message-arrow-right-outline' },
    { key: 'affinity', label: '表达亲和', value: result.affinity_score, max: 10, icon: 'mdi:account-heart-outline' },
    { key: 'total', label: '综合得分', value: result.total_score, max: 50, icon: 'mdi:chart-areaspline' }
  ];
  return metrics.filter(item => typeof item.value === 'number') as Array<{
    key: string;
    label: string;
    value: number;
    max: number;
    icon: string;
  }>;
});

const improvementSuggestions = computed(() => {
  const optimizationSuggestions = stringArray(optimizeResult.value?.suggestions);
  if (optimizationSuggestions.length) return optimizationSuggestions;
  return scoreResult.value?.suggestions || [];
});

const nextLivePlan = computed(() =>
  Array.isArray(optimizeResult.value?.next_live_plan) ? optimizeResult.value.next_live_plan : []
);

const complianceNotes = computed(() => stringArray(optimizeResult.value?.compliance_notes));

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())) : [];
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function parseScoreReport(report?: Api.Douyin.AnalysisReport): Api.Douyin.AiScoreResult | null {
  const content = report?.report_content;
  if (!content || typeof content.total_score !== 'number') return null;
  return {
    completeness_score: numberValue(content.completeness_score),
    interactivity_score: numberValue(content.interactivity_score),
    lead_guidance_score: numberValue(content.lead_guidance_score),
    affinity_score: typeof content.affinity_score === 'number' ? content.affinity_score : undefined,
    knowledge_value_score: typeof content.knowledge_value_score === 'number' ? content.knowledge_value_score : undefined,
    total_score: numberValue(content.total_score),
    strengths: stringArray(content.strengths),
    weaknesses: stringArray(content.weaknesses),
    suggestions: stringArray(content.suggestions),
    evidence: Array.isArray(content.evidence)
      ? content.evidence.filter(
          (item): item is Api.Douyin.AiScoreEvidence =>
            Boolean(item) && typeof item === 'object' && typeof (item as Record<string, unknown>).quote === 'string'
        )
      : []
  };
}

function parseOptimizationReport(report?: Api.Douyin.AnalysisReport): Api.Douyin.AiOptimizationResult | null {
  const content = report?.report_content;
  if (!content) return null;
  const result = content as Api.Douyin.AiOptimizationResult;
  if (stringArray(result.suggestions).length) return result;
  const fallback = Object.entries(content)
    .filter(([key, value]) => key !== 'summary' && typeof value === 'string' && Boolean(value.trim()))
    .map(([key, value]) => `${key}：${value}`);
  return { ...result, suggestions: fallback };
}

function restoreSavedReports(reports: Api.Douyin.AnalysisReport[]) {
  scoreResult.value = parseScoreReport(reports.find(item => item.report_type === 'speech_score'));
  optimizeResult.value = parseOptimizationReport(reports.find(item => item.report_type === 'optimization'));
}

function formatDate(value: string | null) {
  if (!value) return '时间未知';
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatFullDate(value: string | null | undefined) {
  if (!value) return '-';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function formatDuration(seconds: number) {
  if (!seconds) return '时长未知';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}小时${minutes}分` : `${minutes}分钟`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value || 0);
}

function scorePercent(value: number, max: number) {
  return Math.min(100, Math.max(0, (value / max) * 100));
}

function scoreStatus(value: number, max: number): 'success' | 'warning' | 'error' | 'default' {
  const percentage = scorePercent(value, max);
  if (percentage >= 80) return 'success';
  if (percentage < 50) return 'error';
  if (percentage < 70) return 'warning';
  return 'default';
}

function scoreLevel(value: number | undefined) {
  if (typeof value !== 'number') return '待生成';
  if (value >= 40) return '表现优秀';
  if (value >= 30) return '基础可用';
  if (value >= 20) return '需要优化';
  return '优先整改';
}

function readinessType(): TagProps['type'] {
  const score = workbench.value?.completeness.score || 0;
  if (score >= 85) return 'success';
  if (score >= 60) return 'warning';
  return 'error';
}

function findingType(item: Api.Douyin.ReviewFinding): TagProps['type'] {
  if (item.severity === 'critical') return 'error';
  if (item.severity === 'warning') return 'warning';
  return 'info';
}

function findingLabel(item: Api.Douyin.ReviewFinding) {
  return { critical: '重点风险', warning: '需要关注', info: '运营观察' }[item.severity] || '运营观察';
}

function reportTypeMeta(type: string): { label: string; tag: TagProps['type']; icon: string } {
  const mapping: Record<string, { label: string; tag: TagProps['type']; icon: string }> = {
    speech_score: { label: '话术评分', tag: 'success', icon: 'mdi:chart-box-outline' },
    optimization: { label: '优化建议', tag: 'info', icon: 'mdi:lightbulb-on-outline' },
    anomaly: { label: '异常检测', tag: 'warning', icon: 'mdi:alert-decagram-outline' },
    trend: { label: '趋势分析', tag: 'default', icon: 'mdi:chart-timeline-variant' }
  };
  return mapping[type] || { label: type, tag: 'default', icon: 'mdi:file-document-outline' };
}

function reportSummary(report: Api.Douyin.AnalysisReport) {
  if (report.report_type === 'speech_score') {
    const total = report.report_content?.total_score;
    return typeof total === 'number' ? `综合得分 ${total}/50` : report.summary || '评分报告已保存';
  }
  const summary = report.report_content?.summary;
  return (typeof summary === 'string' && summary.trim()) || report.summary || '报告内容已保存，可重新生成获得最新结论。';
}

function actionStageLabel() {
  if (!actionStage.value) return '';
  const labels: Record<Exclude<ActionStage, ''>, string> = {
    evidence: '正在提取真实证据与运营发现…',
    score: '正在评价知识价值、互动和私信承接…',
    optimize: '正在生成下一场可验证动作…',
    'score-only': '正在重新计算话术评分…',
    'optimize-only': '正在更新优化建议…'
  };
  return labels[actionStage.value];
}

async function loadSessionContext(sessionId: number, silent = false) {
  const requestId = ++contextRequestId;
  if (!silent) contextLoading.value = true;
  try {
    const [workbenchResponse, reportsResponse] = await Promise.all([
      fetchReviewWorkbench(sessionId),
      fetchAnalysisReports({ sessionId, limit: 100 })
    ]);
    if (requestId !== contextRequestId) return;
    workbench.value = workbenchResponse.data || null;
    sessionReports.value = reportsResponse.data || [];
    restoreSavedReports(sessionReports.value);
  } catch (error) {
    if (requestId !== contextRequestId) return;
    workbench.value = null;
    sessionReports.value = [];
    scoreResult.value = null;
    optimizeResult.value = null;
    if (!silent) message.error((error as { message?: string }).message || '复盘上下文加载失败');
  } finally {
    if (requestId === contextRequestId) contextLoading.value = false;
  }
}

async function initializePage() {
  loading.value = true;
  try {
    const [sessionsResponse, reportsResponse] = await Promise.all([
      fetchLiveSessions(),
      fetchAnalysisReports({ limit: 500 })
    ]);
    sessions.value = sessionsResponse.data || [];
    const reports = reportsResponse.data || [];
    const reportSessionIds = new Set(reports.map(item => item.session_id));
    const preferred =
      sessions.value.find(item => item.live_status !== 'live' && reportSessionIds.has(item.id)) ||
      sessions.value.find(item => item.live_status !== 'live' && item.detail_collection_status === 'complete') ||
      sessions.value[0];
    selectedSessionId.value = preferred?.id || null;
    if (preferred) await loadSessionContext(preferred.id);
  } catch (error) {
    message.error((error as { message?: string }).message || 'AI 复盘页面加载失败');
  } finally {
    loading.value = false;
  }
}

async function changeSession(value: number | null) {
  selectedSessionId.value = value;
  workbench.value = null;
  sessionReports.value = [];
  scoreResult.value = null;
  optimizeResult.value = null;
  if (value) await loadSessionContext(value);
}

async function refreshPage() {
  if (!selectedSessionId.value) return;
  refreshing.value = true;
  try {
    const response = await fetchLiveSessions();
    sessions.value = response.data || [];
    await loadSessionContext(selectedSessionId.value, true);
    message.success('已刷新真实场次和分析报告');
  } finally {
    refreshing.value = false;
  }
}

async function runFullReview() {
  const sessionId = selectedSessionId.value;
  if (!sessionId) return message.warning('请先选择直播场次');
  if (!analysisReady.value) return message.warning('当前数据不足，请先补齐分钟指标、评论或话术');
  try {
    actionStage.value = 'evidence';
    const findingsResponse = await generateSessionReview(sessionId);
    if (findingsResponse.data?.workbench) workbench.value = findingsResponse.data.workbench;
    actionStage.value = 'score';
    const scoreResponse = await scoreSession(sessionId);
    if (scoreResponse.data?.result) scoreResult.value = scoreResponse.data.result;
    actionStage.value = 'optimize';
    const optimizeResponse = await optimizeSession(sessionId);
    if (optimizeResponse.data?.result) optimizeResult.value = optimizeResponse.data.result;
    await loadSessionContext(sessionId, true);
    activeTab.value = 'overview';
    message.success('完整复盘已生成，报告已保存');
  } catch (error) {
    message.error((error as { message?: string }).message || '复盘生成中断，已完成的结果仍会保留');
  } finally {
    actionStage.value = '';
  }
}

async function runScore() {
  if (!selectedSessionId.value) return;
  actionStage.value = 'score-only';
  try {
    const response = await scoreSession(selectedSessionId.value);
    if (response.data?.result) scoreResult.value = response.data.result;
    await loadSessionContext(selectedSessionId.value, true);
    message.success('话术评分已更新');
  } catch (error) {
    message.error((error as { message?: string }).message || '话术评分失败');
  } finally {
    actionStage.value = '';
  }
}

async function runOptimize() {
  if (!selectedSessionId.value) return;
  actionStage.value = 'optimize-only';
  try {
    const response = await optimizeSession(selectedSessionId.value);
    if (response.data?.result) optimizeResult.value = response.data.result;
    await loadSessionContext(selectedSessionId.value, true);
    message.success('下一场优化建议已更新');
  } catch (error) {
    message.error((error as { message?: string }).message || '优化建议生成失败');
  } finally {
    actionStage.value = '';
  }
}

function openSessionDetail() {
  if (!selectedSessionId.value) return;
  router.push({ name: 'live-session-detail', params: { id: String(selectedSessionId.value) } });
}

function openTranscripts() {
  router.push({ name: 'transcripts' });
}

onMounted(initializePage);
</script>

<template>
  <NSpin :show="loading">
    <NSpace vertical :size="16" class="analysis-page">
      <BusinessPageHeader
        title="零食店避坑直播 AI 复盘"
        description="把真实场次指标、评论、ASR 话术和历史报告放进同一套复盘流程，定位知识价值、资料钩子与站内私信承接问题。"
        icon="mdi:chart-box-outline"
        eyebrow="证据化运营复盘"
        :status="selectedSession ? `${selectedSession.anchor_name} · ${scoreLevel(scoreResult?.total_score)}` : '请选择场次'"
        :status-type="scoreResult ? 'success' : selectedSession ? 'warning' : 'default'"
      >
        <template #actions>
          <NButton secondary :loading="refreshing" :disabled="!selectedSessionId" @click="refreshPage">
            <template #icon><SvgIcon icon="mdi:refresh" /></template>
            刷新数据
          </NButton>
          <NButton type="primary" ghost :disabled="!selectedSessionId" @click="openSessionDetail">
            <template #icon><SvgIcon icon="mdi:open-in-new" /></template>
            查看场次详情
          </NButton>
        </template>
        <div class="flex flex-wrap gap-x-18px gap-y-6px text-12px text-gray-500">
          <span>真实数据可信度决定结论强度</span>
          <span>综合评分满分 50 分，单项满分 10 分</span>
          <span>所有建议均保留场次与报告来源</span>
        </div>
      </BusinessPageHeader>

      <NCard :bordered="false" class="card-wrapper session-control-card">
        <div class="grid grid-cols-[minmax(0,1.45fr)_minmax(280px,0.65fr)] gap-20px lt-lg:grid-cols-1">
          <div class="min-w-0">
            <div class="mb-8px flex items-center justify-between gap-12px">
              <div>
                <div class="text-15px font-700">选择复盘场次</div>
                <div class="mt-3px text-12px text-gray-500">默认优先打开已经生成过真实报告的已结束场次</div>
              </div>
              <NTag v-if="sessions.length" round :bordered="false" type="info">{{ sessions.length }} 场可选</NTag>
            </div>
            <NSelect
              :value="selectedSessionId"
              filterable
              clearable
              :options="sessionOptions"
              placeholder="按主播、日期或状态搜索直播场次"
              :loading="loading"
              @update:value="changeSession"
            />
            <div v-if="selectedSession" class="mt-14px flex min-w-0 items-center gap-12px">
              <NAvatar round :size="42" :src="selectedSession.anchor_avatar_url || undefined">
                {{ selectedSession.anchor_name?.slice(0, 1) || '播' }}
              </NAvatar>
              <div class="min-w-0 flex-1">
                <div class="truncate text-14px font-700">{{ selectedSession.session_title || '未命名直播场次' }}</div>
                <div class="mt-4px flex flex-wrap items-center gap-x-12px gap-y-4px text-12px text-gray-500">
                  <span>{{ selectedSession.anchor_name }}</span>
                  <span>{{ formatFullDate(selectedSession.live_start_time) }}</span>
                  <span>{{ formatDuration(selectedSession.live_duration_seconds) }}</span>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap gap-6px lt-sm:hidden">
                <NTag :type="selectedSession.live_status === 'live' ? 'error' : 'default'" round size="small" :bordered="false">
                  {{ selectedSession.live_status === 'live' ? '直播中' : '已结束' }}
                </NTag>
                <NTag :type="readinessType()" round size="small" :bordered="false">
                  可信度 {{ workbench?.completeness.score || 0 }}%
                </NTag>
              </div>
            </div>
          </div>

          <div class="review-launch-panel">
            <div class="flex items-start gap-10px">
              <div class="size-38px flex-center shrink-0 rounded-11px bg-primary-100 text-primary dark:bg-primary-900/35">
                <SvgIcon icon="mdi:auto-fix" class="text-21px" />
              </div>
              <div>
                <div class="text-14px font-700">生成完整复盘</div>
                <div class="mt-3px text-12px leading-19px text-gray-500">依次提取证据、更新评分、生成下一场动作</div>
              </div>
            </div>
            <NTooltip :disabled="analysisReady || !selectedSessionId">
              <template #trigger>
                <span class="mt-14px block">
                  <NButton
                    type="primary"
                    size="large"
                    block
                    :loading="actionBusy"
                    :disabled="!selectedSessionId || !analysisReady || actionBusy"
                    @click="runFullReview"
                  >
                    {{ scoreResult ? '重新生成完整复盘' : '开始完整复盘' }}
                  </NButton>
                </span>
              </template>
              当前数据不足，请先补齐分钟指标、评论或 ASR 话术
            </NTooltip>
            <div class="mt-9px min-h-18px text-12px" :class="actionBusy ? 'text-primary' : 'text-gray-400'">
              {{ actionStageLabel() || (latestReport ? `最近报告 ${formatFullDate(latestReport.created_at)}` : '尚未生成分析报告') }}
            </div>
          </div>
        </div>
      </NCard>

      <NAlert v-if="selectedSessionId && workbench && !analysisReady" type="warning" show-icon :bordered="false">
        <template #header>当前数据不足以形成稳定 AI 结论</template>
        数据可以回看，但请先补齐分钟指标、评论或 ASR 话术后再运行完整复盘。
        <NButton text type="primary" class="ml-6px" @click="openTranscripts">前往主播话术</NButton>
      </NAlert>

      <NGrid v-if="selectedSession" :x-gap="14" :y-gap="14" cols="1 s:2 m:4" responsive="screen">
        <NGi>
          <NCard :bordered="false" class="card-wrapper metric-summary-card score-card" size="small">
            <div class="flex items-start justify-between gap-10px">
              <NStatistic label="综合评分" :value="scoreResult?.total_score ?? 0">
                <template #suffix><span class="text-13px text-gray-400">/ 50</span></template>
              </NStatistic>
              <SvgIcon icon="mdi:chart-areaspline" class="text-25px text-primary" />
            </div>
            <div class="mt-8px text-12px text-gray-500">{{ scoreLevel(scoreResult?.total_score) }}</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
            <div class="flex items-start justify-between gap-10px">
              <NStatistic label="数据可信度" :value="workbench?.completeness.score || 0" :precision="1" suffix="%" />
              <SvgIcon icon="mdi:database-check-outline" class="text-25px text-success" />
            </div>
            <NProgress
              class="mt-9px"
              :percentage="workbench?.completeness.score || 0"
              :height="6"
              :show-indicator="false"
              :status="workbench?.completeness.score && workbench.completeness.score >= 85 ? 'success' : 'warning'"
            />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
            <div class="flex items-start justify-between gap-10px">
              <NStatistic label="站内私信" :value="formatNumber(selectedSession.private_message_count)" />
              <SvgIcon icon="mdi:message-text-outline" class="text-25px text-warning" />
            </div>
            <div class="mt-8px text-12px text-gray-500">评论 {{ formatNumber(selectedSession.comments_count) }} 条</div>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="card-wrapper metric-summary-card" size="small">
            <div class="flex items-start justify-between gap-10px">
              <NStatistic label="场景线索" :value="formatNumber(selectedSession.scene_leads_count)" />
              <SvgIcon icon="mdi:account-arrow-right-outline" class="text-25px text-error" />
            </div>
            <div class="mt-8px text-12px text-gray-500">待处理发现 {{ openFindingCount }} 条</div>
          </NCard>
        </NGi>
      </NGrid>

      <NCard v-if="selectedSessionId" :bordered="false" class="card-wrapper content-card">
        <NTabs v-model:value="activeTab" type="line" animated>
          <NTabPane name="overview" tab="复盘总览">
            <NSpin :show="contextLoading">
              <NSpace vertical :size="16">
                <template v-if="scoreResult">
                  <div class="section-heading">
                    <div>
                      <div class="text-16px font-700">五维话术评分</div>
                      <div class="mt-3px text-12px text-gray-500">综合分满分 50 分，单项分满分 10 分</div>
                    </div>
                    <div class="flex flex-wrap gap-8px">
                      <NButton size="small" secondary :loading="actionStage === 'score-only'" :disabled="actionBusy" @click="runScore">
                        重新评分
                      </NButton>
                      <NButton size="small" secondary :loading="actionStage === 'optimize-only'" :disabled="actionBusy" @click="runOptimize">
                        更新建议
                      </NButton>
                    </div>
                  </div>

                  <NGrid :x-gap="12" :y-gap="12" cols="1 s:2 m:3 xl:6" responsive="screen">
                    <NGi v-for="item in scoreMetrics" :key="item.key">
                      <div class="score-metric">
                        <div class="flex items-center justify-between gap-8px">
                          <div class="size-32px flex-center rounded-9px bg-primary-50 text-primary dark:bg-primary-900/25">
                            <SvgIcon :icon="item.icon" class="text-18px" />
                          </div>
                          <span class="text-11px text-gray-400">满分 {{ item.max }}</span>
                        </div>
                        <div class="mt-12px text-12px text-gray-500">{{ item.label }}</div>
                        <div class="mt-2px flex items-end gap-4px">
                          <span class="text-26px font-800 leading-32px">{{ item.value }}</span>
                          <span class="mb-3px text-11px text-gray-400">/ {{ item.max }}</span>
                        </div>
                        <NProgress
                          class="mt-8px"
                          :percentage="scorePercent(item.value, item.max)"
                          :height="5"
                          :show-indicator="false"
                          :status="scoreStatus(item.value, item.max)"
                        />
                      </div>
                    </NGi>
                  </NGrid>

                  <NGrid :x-gap="14" :y-gap="14" cols="1 l:2" responsive="screen">
                    <NGi>
                      <NCard :bordered="false" class="insight-panel strength-panel" size="small">
                        <template #header>
                          <div class="flex items-center gap-8px">
                            <SvgIcon icon="mdi:check-decagram-outline" class="text-20px text-success" />
                            <span>值得保留</span>
                            <NTag size="small" round :bordered="false" type="success">{{ scoreResult.strengths.length }}</NTag>
                          </div>
                        </template>
                        <div v-if="scoreResult.strengths.length" class="space-y-8px">
                          <div v-for="(item, index) in scoreResult.strengths" :key="`${index}-${item}`" class="insight-item">
                            <span class="insight-index success-index">{{ index + 1 }}</span>
                            <span>{{ item }}</span>
                          </div>
                        </div>
                        <NEmpty v-else description="暂无明确优势证据" class="py-24px" />
                      </NCard>
                    </NGi>
                    <NGi>
                      <NCard :bordered="false" class="insight-panel weakness-panel" size="small">
                        <template #header>
                          <div class="flex items-center gap-8px">
                            <SvgIcon icon="mdi:alert-circle-outline" class="text-20px text-warning" />
                            <span>优先改进</span>
                            <NTag size="small" round :bordered="false" type="warning">{{ scoreResult.weaknesses.length }}</NTag>
                          </div>
                        </template>
                        <div v-if="scoreResult.weaknesses.length" class="space-y-8px">
                          <div v-for="(item, index) in scoreResult.weaknesses" :key="`${index}-${item}`" class="insight-item">
                            <span class="insight-index warning-index">{{ index + 1 }}</span>
                            <span>{{ item }}</span>
                          </div>
                        </div>
                        <NEmpty v-else description="暂无明确问题证据" class="py-24px" />
                      </NCard>
                    </NGi>
                  </NGrid>

                  <NCard :bordered="false" class="action-plan-panel" size="small">
                    <template #header>
                      <div>
                        <div class="text-15px font-700">下一场可执行动作</div>
                        <div class="mt-3px text-12px font-400 text-gray-500">围绕开场留人、避坑知识、资料钩子和站内私信承接</div>
                      </div>
                    </template>
                    <NAlert v-if="optimizeResult?.summary" type="info" :bordered="false" class="mb-12px">
                      {{ optimizeResult.summary }}
                    </NAlert>
                    <div v-if="improvementSuggestions.length" class="grid grid-cols-1 gap-9px l:grid-cols-2">
                      <div v-for="(item, index) in improvementSuggestions" :key="`${index}-${item}`" class="action-item">
                        <span class="action-number">{{ String(index + 1).padStart(2, '0') }}</span>
                        <span>{{ item }}</span>
                      </div>
                    </div>
                    <NEmpty v-else description="尚未生成下一场优化建议" class="py-28px">
                      <template #extra><NButton size="small" type="primary" @click="runOptimize">生成优化建议</NButton></template>
                    </NEmpty>
                  </NCard>

                  <NCard v-if="nextLivePlan.length" :bordered="false" class="next-live-panel" size="small" title="下一场直播节奏">
                    <div class="grid grid-cols-1 gap-9px m:grid-cols-2 xl:grid-cols-3">
                      <div v-for="(item, index) in nextLivePlan" :key="`${item.stage}-${index}`" class="next-live-item">
                        <div class="flex items-center justify-between gap-8px">
                          <NTag size="small" round :bordered="false" type="info">{{ item.stage || `阶段 ${index + 1}` }}</NTag>
                          <span class="text-11px text-gray-400">{{ index + 1 }}/{{ nextLivePlan.length }}</span>
                        </div>
                        <div class="mt-9px text-13px font-600 leading-21px">{{ item.action || '待补充执行动作' }}</div>
                        <div class="mt-7px border-t border-gray-100 pt-7px text-12px text-gray-500 dark:border-white/8">
                          验证：{{ item.success_metric || '下一场人工记录结果' }}
                        </div>
                      </div>
                    </div>
                  </NCard>

                  <NAlert v-if="complianceNotes.length" type="warning" show-icon :bordered="false">
                    <template #header>合规人工复核</template>
                    <div v-for="(item, index) in complianceNotes" :key="`${index}-${item}`">{{ index + 1 }}. {{ item }}</div>
                  </NAlert>
                </template>

                <NResult
                  v-else
                  status="info"
                  title="这个场次还没有 AI 评分"
                  description="系统不会用其他场次或模拟内容填充。确认数据可信度达到可分析标准后，再生成完整复盘。"
                >
                  <template #footer>
                    <NButton type="primary" :disabled="!analysisReady" :loading="actionBusy" @click="runFullReview">开始完整复盘</NButton>
                  </template>
                </NResult>
              </NSpace>
            </NSpin>
          </NTabPane>

          <NTabPane name="evidence" :tab="`证据与发现 (${workbench?.findings.length || 0})`">
            <NSpin :show="contextLoading">
              <NSpace vertical :size="16">
                <NCard :bordered="false" class="evidence-coverage-panel" size="small">
                  <div class="section-heading">
                    <div>
                      <div class="text-15px font-700">避坑知识与转化链路覆盖</div>
                      <div class="mt-3px text-12px text-gray-500">根据真实 ASR 话术关键词统计，不根据标题猜测</div>
                    </div>
                    <NTag round :bordered="false" :type="coveredDomainCount >= 6 ? 'success' : 'warning'">
                      已覆盖 {{ coveredDomainCount }}/{{ workbench?.domain_coverage.length || 0 }}
                    </NTag>
                  </div>
                  <div class="mt-14px flex flex-wrap gap-8px">
                    <NTooltip v-for="item in workbench?.domain_coverage || []" :key="item.category">
                      <template #trigger>
                        <NTag :type="item.covered ? 'success' : 'default'" round :bordered="false">
                          {{ item.category }} · {{ item.segment_count }} 段
                        </NTag>
                      </template>
                      {{ item.covered ? `首次出现于 ${Math.round(item.first_seconds || 0)} 秒` : '真实话术中暂未识别到该主题' }}
                    </NTooltip>
                  </div>
                </NCard>

                <div v-if="workbench?.findings.length" class="grid grid-cols-1 gap-10px l:grid-cols-2">
                  <div v-for="item in workbench.findings" :key="item.id" class="finding-card">
                    <div class="flex items-start justify-between gap-12px">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-7px">
                          <NTag size="small" round :bordered="false" :type="findingType(item)">{{ findingLabel(item) }}</NTag>
                          <span class="text-12px text-gray-400">{{ item.category }}</span>
                        </div>
                        <div class="mt-8px text-14px font-700 leading-22px">{{ item.title }}</div>
                      </div>
                      <span v-if="item.start_seconds !== null" class="shrink-0 font-mono text-11px text-primary">
                        {{ Math.floor(item.start_seconds / 60) }}:{{ String(Math.floor(item.start_seconds % 60)).padStart(2, '0') }}
                      </span>
                    </div>
                    <p v-if="item.description" class="mb-0 mt-7px text-12px leading-20px text-gray-500">{{ item.description }}</p>
                    <div v-if="item.evidence_text" class="mt-9px rounded-8px bg-gray-50 px-10px py-8px text-12px leading-20px dark:bg-dark-300">
                      {{ item.evidence_text }}
                    </div>
                  </div>
                </div>
                <NEmpty v-else description="尚未生成结构化复盘发现" class="py-42px">
                  <template #extra>
                    <NButton type="primary" :disabled="!analysisReady" :loading="actionBusy" @click="runFullReview">提取证据并生成复盘</NButton>
                  </template>
                </NEmpty>

                <NCard v-if="scoreResult?.evidence?.length" :bordered="false" size="small" title="AI 评分引用的话术证据">
                  <div class="grid grid-cols-1 gap-9px l:grid-cols-2">
                    <div v-for="(item, index) in scoreResult.evidence" :key="`${item.start_seconds}-${index}`" class="quote-card">
                      <div class="flex items-center justify-between gap-8px">
                        <NTag size="small" round :bordered="false" type="info">{{ item.category }}</NTag>
                        <span v-if="item.start_seconds !== null" class="font-mono text-11px text-gray-400">{{ Math.round(item.start_seconds) }} 秒</span>
                      </div>
                      <div class="mt-8px text-12px leading-20px">“{{ item.quote }}”</div>
                    </div>
                  </div>
                </NCard>
              </NSpace>
            </NSpin>
          </NTabPane>

          <NTabPane name="history" :tab="`历史报告 (${sessionReports.length})`">
            <NList v-if="sessionReports.length" hoverable clickable class="report-list">
              <NListItem v-for="report in sessionReports" :key="report.id">
                <NThing :title="report.report_title || reportTypeMeta(report.report_type).label" :description="reportSummary(report)">
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
                      <span class="text-11px text-gray-400">{{ formatFullDate(report.created_at) }}</span>
                    </div>
                  </template>
                </NThing>
              </NListItem>
            </NList>
            <NEmpty v-else description="当前场次还没有保存的分析报告" class="py-50px" />
          </NTabPane>
        </NTabs>
      </NCard>

      <NResult v-if="!loading && !sessions.length" status="warning" title="暂无可复盘场次" description="请先完成真实直播场次采集。" />
    </NSpace>
  </NSpin>
</template>

<style scoped>
.analysis-page {
  --analysis-line: rgba(148, 163, 184, 0.18);
}

.session-control-card {
  background:
    radial-gradient(circle at 92% 8%, rgba(37, 99, 235, 0.08), transparent 32%),
    var(--n-color);
}

.review-launch-panel {
  border: 1px solid var(--analysis-line);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.7);
  padding: 15px;
}

.metric-summary-card {
  min-height: 116px;
  border: 1px solid transparent;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.metric-summary-card:hover {
  border-color: rgba(37, 99, 235, 0.2);
  transform: translateY(-1px);
}

.score-card {
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.09), transparent 65%),
    var(--n-color);
}

.content-card :deep(.n-card__content) {
  padding-top: 10px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.score-metric {
  min-height: 146px;
  border: 1px solid var(--analysis-line);
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(248, 250, 252, 0.86), rgba(255, 255, 255, 0.55));
  padding: 13px;
}

.insight-panel,
.action-plan-panel,
.next-live-panel,
.evidence-coverage-panel {
  border: 1px solid var(--analysis-line);
  border-radius: 12px;
}

.strength-panel {
  background: linear-gradient(145deg, rgba(16, 185, 129, 0.045), transparent 68%), var(--n-color);
}

.weakness-panel {
  background: linear-gradient(145deg, rgba(245, 158, 11, 0.055), transparent 68%), var(--n-color);
}

.insight-item,
.action-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-radius: 9px;
  background: rgba(248, 250, 252, 0.82);
  padding: 9px 10px;
  font-size: 13px;
  line-height: 21px;
}

.insight-index,
.action-number {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
}

.success-index {
  background: rgba(16, 185, 129, 0.12);
  color: rgb(5, 150, 105);
}

.warning-index {
  background: rgba(245, 158, 11, 0.13);
  color: rgb(217, 119, 6);
}

.action-number {
  background: rgba(37, 99, 235, 0.1);
  color: rgb(37, 99, 235);
}

.next-live-item,
.finding-card,
.quote-card {
  border: 1px solid var(--analysis-line);
  border-radius: 11px;
  background: rgba(248, 250, 252, 0.58);
  padding: 12px;
}

.report-list {
  border-radius: 12px;
  overflow: hidden;
}

:global(.dark) .review-launch-panel,
:global(.dark) .score-metric,
:global(.dark) .insight-item,
:global(.dark) .action-item,
:global(.dark) .next-live-item,
:global(.dark) .finding-card,
:global(.dark) .quote-card {
  background: rgba(255, 255, 255, 0.035);
}

@media (max-width: 640px) {
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
