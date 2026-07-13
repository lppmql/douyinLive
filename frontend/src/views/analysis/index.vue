<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { fetchLiveSessions, scoreSession, optimizeSession } from '@/service/api/douyin';

defineOptions({ name: 'Analysis' });

const message = useMessage();

/* ---------- 场次选择 ---------- */
interface SessionOption { id: number; label: string }

const sessions = ref<SessionOption[]>([]);
const selectedSession = ref<number | null>(null);

onMounted(async () => {
  try {
    const res = await fetchLiveSessions();
    const list = (res as unknown as { data: { id: number; session_title: string }[] }).data || [];
    sessions.value = list.map((s: { id: number; session_title: string }) => ({
      id: s.id,
      label: s.session_title ? `#${s.id} ${s.session_title}` : `#${s.id}`
    }));
    if (sessions.value.length) selectedSession.value = sessions.value[0].id;
  } catch { /* ignore */ }
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
  } catch { /* ignore */ }
  loadingOptimize.value = false;
}
</script>

<template>
  <NSpace vertical :size="16">
    <!-- 控制栏 -->
    <NCard :bordered="false" class="card-wrapper" size="small">
      <NSpace align="center" wrap>
        <NSelect
          v-model:value="selectedSession"
          placeholder="选择直播场次"
          :options="sessions"
          style="width: 280px"
          clearable
        />
        <NButton type="primary" :loading="loadingScore" @click="runScore">
          话术评分
        </NButton>
        <NButton :loading="loadingOptimize" @click="runOptimize">
          优化建议
        </NButton>
      </NSpace>
    </NCard>

    <!-- 评分卡片 -->
    <NGrid v-if="scoreResult" :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen">
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.completeness') }}</div>
          <div class="text-32px font-bold" style="color:#667eea">{{ scoreResult.completeness_score }}</div>
          <NProgress type="line" :percentage="scoreResult.completeness_score * 10" :height="6" color="#667eea" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.interactivity') }}</div>
          <div class="text-32px font-bold" style="color:#f093fb">{{ scoreResult.interactivity_score }}</div>
          <NProgress type="line" :percentage="scoreResult.interactivity_score * 10" :height="6" color="#f093fb" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.leadGuidance') }}</div>
          <div class="text-32px font-bold" style="color:#4facfe">{{ scoreResult.lead_guidance_score }}</div>
          <NProgress type="line" :percentage="scoreResult.lead_guidance_score * 10" :height="6" color="#4facfe" />
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper" size="small">
          <div class="text-13px text-gray-500 mb-8px">{{ $t('page.analysis.overall') }}</div>
          <div class="text-32px font-bold" style="color:#43e97b">{{ scoreResult.total_score }}</div>
          <NProgress type="line" :percentage="scoreResult.total_score * 10" :height="6" color="#43e97b" />
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
