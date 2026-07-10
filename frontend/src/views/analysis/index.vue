<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useMessage, useDialog } from 'naive-ui';
import { $t } from '@/locales';
import { useEcharts } from '@/hooks/common/echarts';
import { fetchLiveSessions, scoreSession, optimizeSession, fetchPrompts } from '@/service/api/douyin';

defineOptions({ name: 'Analysis' });

const message = useMessage();
const dialog = useDialog();

/* ---------- 场次选择 ---------- */
const sessions = ref<Api.Douyin.LiveSession[]>([]);
const selectedSession = ref<number | null>(null);

onMounted(async () => {
  try {
    sessions.value = await fetchLiveSessions();
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
    scoreResult.value = res.result as unknown as Api.Douyin.AiScoreResult;
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
    optimizeResult.value = res.result as { suggestions?: string[]; summary?: string };
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
          :placeholder="$t('page.analysis.selectSession')"
          :options="sessions.map(s => ({ label: `${s.sessionTitle || '场次'}#${s.id}`, value: s.id }))"
          style="width: 280px"
          clearable
        />
        <NButton type="primary" :loading="loadingScore" @click="runScore">
          {{ $t('page.analysis.runScore') }}
        </NButton>
        <NButton :loading="loadingOptimize" @click="runOptimize">
          {{ $t('page.analysis.runOptimize') }}
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
          <template #header><span class="text-15px font-bold">{{ $t('page.analysis.strengths') }}</span></template>
          <ul class="list-disc pl-20px">
            <li v-for="(s, i) in scoreResult.strengths" :key="i">{{ s }}</li>
          </ul>
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" class="card-wrapper">
          <template #header><span class="text-15px font-bold">{{ $t('page.analysis.weaknesses') }}</span></template>
          <ul class="list-disc pl-20px">
            <li v-for="(w, i) in scoreResult.weaknesses" :key="i">{{ w }}</li>
          </ul>
        </NCard>
      </NGi>
    </NGrid>

    <!-- 优化建议 -->
    <NCard v-if="optimizeResult" :bordered="false" class="card-wrapper">
      <template #header><span class="text-15px font-bold">{{ $t('page.analysis.suggestionTitle') }}</span></template>
      <NSpace vertical :size="12">
        <div v-for="(item, index) in optimizeResult.suggestions" :key="index"
          class="flex items-start gap-12px rounded-8px bg-gray-50 dark:bg-dark-300 p-12px">
          <NBadge :value="index + 1" />
          <span class="text-14px leading-22px">{{ item }}</span>
        </div>
      </NSpace>
    </NCard>
  </NSpace>
</template>

<style scoped></style>
