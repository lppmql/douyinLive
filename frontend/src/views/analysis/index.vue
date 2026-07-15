<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useMessage } from 'naive-ui';
import { $t } from '@/locales';
import BusinessPageHeader from '@/components/business/page-header.vue';
import { fetchLiveSessions, scoreSession, optimizeSession } from '@/service/api/douyin';

defineOptions({ name: 'Analysis' });

const message = useMessage();

/* ---------- 场次选择 ---------- */
interface SessionOption {
  value: number;
  label: string;
}

const sessions = ref<SessionOption[]>([]);
const selectedSession = ref<number | null>(null);

onMounted(async () => {
  try {
    const res = await fetchLiveSessions();
    const list = (res as unknown as { data: { id: number; session_title: string }[] }).data || [];
    sessions.value = list.map((s: { id: number; session_title: string }) => ({
      value: s.id,
      label: s.session_title ? `#${s.id} ${s.session_title}` : `#${s.id}`
    }));
    if (sessions.value.length) selectedSession.value = sessions.value[0].value;
  } catch {
    message.error('直播场次加载失败');
  }
});

/* ---------- 评分结果 ---------- */
const loadingScore = ref(false);
const scoreResult = ref<Api.Douyin.AiScoreResult | null>(null);

async function runScore() {
  if (!selectedSession.value) return message.warning('请选择直播场次');
  loadingScore.value = true;
  scoreResult.value = null;
  try {
    const res = await scoreSession(selectedSession.value);
    const data = (res as unknown as { data: { result: Api.Douyin.AiScoreResult } }).data;
    scoreResult.value = data.result;
    message.success('话术评分完成');
  } catch (e: unknown) {
    const msg = (e as { message?: string })?.message || '评分失败';
    message.error(msg);
  }
  loadingScore.value = false;
}

/* ---------- 优化建议 ---------- */
const loadingOptimize = ref(false);
const optimizeResult = ref<{ suggestions?: string[]; summary?: string } | null>(null);

async function runOptimize() {
  if (!selectedSession.value) return;
  loadingOptimize.value = true;
  try {
    const res = await optimizeSession(selectedSession.value);
    const data = (res as unknown as { data: { result: { suggestions?: string[]; summary?: string } } }).data;
    optimizeResult.value = data.result;
    message.success('优化建议生成完成');
  } catch {
    message.error('优化建议生成失败');
  }
  loadingOptimize.value = false;
}
</script>

<template>
  <NSpace vertical :size="16">
    <BusinessPageHeader
      title="AI 经营分析"
      description="基于已采集的真实场次、评论和 ASR 话术生成评分与优化建议，不会为缺失数据编造结论。"
      icon="mdi:chart-box-outline"
      :status="selectedSession ? `已选择场次 #${selectedSession}` : '请先选择场次'"
      :status-type="selectedSession ? 'success' : 'warning'"
    >
      <div class="flex flex-wrap gap-x-18px gap-y-6px text-12px text-gray-500">
        <span>1. 选择已有话术的场次</span>
        <span>2. 运行话术评分</span>
        <span>3. 生成可执行优化建议</span>
      </div>
    </BusinessPageHeader>

    <!-- 控制栏 -->
    <NCard :bordered="false" class="card-wrapper" size="small">
      <NSpace align="center" wrap>
        <NSelect
          v-model:value="selectedSession"
          placeholder="选择直播场次"
          :options="sessions"
          class="w-420px max-w-full"
          clearable
        />
        <NButton type="primary" :loading="loadingScore" @click="runScore">话术评分</NButton>
        <NButton :loading="loadingOptimize" @click="runOptimize">优化建议</NButton>
      </NSpace>
    </NCard>

    <NCard v-if="!scoreResult && !optimizeResult" :bordered="false" class="card-wrapper">
      <NEmpty description="选择直播场次后运行分析">
        <template #icon><SvgIcon icon="mdi:robot-outline" class="text-58px text-primary" /></template>
        <template #extra>
          <div class="max-w-520px text-center text-13px leading-21px text-gray-500">
            如果按钮执行失败，请先进入场次详情确认已有评论、分钟指标和 ASR 话术；缺失数据会直接提示，不会生成虚假结果。
          </div>
        </template>
      </NEmpty>
    </NCard>

    <!-- 评分卡片 -->
    <NGrid v-if="scoreResult" :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.completeness') }}</div>
          <div class="text-32px font-bold text-primary">{{ scoreResult.completeness_score }}</div>
          <NProgress type="line" :percentage="scoreResult.completeness_score * 10" :height="6" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.interactivity') }}</div>
          <div class="text-32px font-bold text-success">{{ scoreResult.interactivity_score }}</div>
          <NProgress type="line" status="success" :percentage="scoreResult.interactivity_score * 10" :height="6" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.leadGuidance') }}</div>
          <div class="text-32px font-bold text-warning">{{ scoreResult.lead_guidance_score }}</div>
          <NProgress type="line" status="warning" :percentage="scoreResult.lead_guidance_score * 10" :height="6" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.overall') }}</div>
          <div class="text-32px font-bold text-error">{{ scoreResult.total_score }}</div>
          <NProgress type="line" status="error" :percentage="scoreResult.total_score * 10" :height="6" />
        </NCard>
      </NGi>
    </NGrid>

    <!-- 评分详情 -->
    <NGrid v-if="scoreResult" :x-gap="16" :y-gap="16" cols="1 m:2" responsive="screen">
      <NGi>
        <NCard :bordered="false" class="card-wrapper">
          <template #header><span class="text-15px font-bold">优势</span></template>
          <ul class="list-disc pl-20px">
            <li v-for="(s, i) in scoreResult.strengths" :key="i">{{ s }}</li>
            <li v-if="!scoreResult.strengths.length" class="text-gray-400">暂无</li>
          </ul>
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper">
          <template #header><span class="text-15px font-bold">不足</span></template>
          <ul class="list-disc pl-20px">
            <li v-for="(w, i) in scoreResult.weaknesses" :key="i">{{ w }}</li>
            <li v-if="!scoreResult.weaknesses.length" class="text-gray-400">暂无</li>
          </ul>
        </NCard>
      </NGi>
    </NGrid>

    <!-- 优化建议 -->
    <NCard v-if="optimizeResult" :bordered="false" class="card-wrapper">
      <template #header><span class="text-15px font-bold">优化建议</span></template>
      <NSpace vertical :size="12">
        <div
          v-for="(item, index) in optimizeResult.suggestions"
          :key="index"
          class="flex items-start gap-12px rounded-8px bg-gray-50 dark:bg-dark-300 p-12px"
        >
          <NBadge :value="index + 1" />
          <span class="text-14px leading-22px">{{ item }}</span>
        </div>
        <div v-if="!optimizeResult.suggestions?.length" class="text-gray-400 py-20px text-center">暂无优化建议</div>
      </NSpace>
    </NCard>
  </NSpace>
</template>

<style scoped></style>
