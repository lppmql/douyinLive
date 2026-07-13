<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import { detectAnomaly, detectHighIntent, fetchLiveSessionData, optimizeSession, scoreSession } from '@/service/api/douyin';

defineOptions({ name: 'LiveSessionAiAnalysis' });
const props = defineProps<{ id: string }>();
const router = useRouter();
const message = useMessage();
const detail = ref<Api.Douyin.LiveSessionDetail | null>(null);
const loading = ref(false);
const action = ref('');
const results = ref<Record<string, unknown>>({});
const sessionId = computed(() => Number(props.id));
const readiness = computed(() => detail.value ? [detail.value.metrics.length, detail.value.comments.length, detail.value.profiles.length, detail.value.stream_url].filter(Boolean).length * 25 : 0);

async function load() {
  loading.value = true;
  try { detail.value = (await fetchLiveSessionData(sessionId.value)).data || null; }
  catch { message.error('场次分析数据加载失败'); }
  finally { loading.value = false; }
}
async function run(type: 'score' | 'anomaly' | 'optimize' | 'intent') {
  action.value = type;
  try {
    if (type === 'score') results.value.score = (await scoreSession(sessionId.value)).data?.result || {};
    if (type === 'anomaly') results.value.anomaly = (await detectAnomaly(sessionId.value)).data?.result || {};
    if (type === 'optimize') results.value.optimize = (await optimizeSession(sessionId.value)).data?.result || {};
    if (type === 'intent') results.value.intent = (await detectHighIntent(sessionId.value)).data || {};
    message.success('AI 分析完成');
  } catch (error) { message.error((error as { message?: string }).message || 'AI 分析失败，请检查模型配置和场次数据'); }
  finally { action.value = ''; }
}
function resultText(key: string) { return results.value[key] ? JSON.stringify(results.value[key], null, 2) : '尚未运行此项分析'; }
onMounted(load);
</script>

<template>
  <NSpin :show="loading">
    <NSpace vertical :size="16">
      <NCard :bordered="false" class="card-wrapper ai-hero"><div class="flex flex-wrap items-center justify-between gap-16px"><div><div class="flex items-center gap-10px"><SvgIcon icon="mdi:creation-outline" class="text-28px text-primary" /><h2 class="m-0 text-22px">直播数据 AI 分析</h2></div><div class="mt-6px text-gray-500">{{ detail?.session.anchor_name || '-' }} · {{ detail?.session.session_title || `场次 #${id}` }}</div></div><NSpace wrap><NButton @click="router.push({ name: 'live-sessions' })">返回列表</NButton><NButton @click="router.push({ name: 'live-session-detail', params: { id } })">查看详情</NButton></NSpace></div></NCard>
      <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:4" responsive="screen"><NGi><NCard :bordered="false" class="card-wrapper"><NStatistic label="分钟趋势" :value="detail?.metrics.length || 0"><template #suffix>条</template></NStatistic></NCard></NGi><NGi><NCard :bordered="false" class="card-wrapper"><NStatistic label="评论语料" :value="detail?.comments.length || 0"><template #suffix>条</template></NStatistic></NCard></NGi><NGi><NCard :bordered="false" class="card-wrapper"><NStatistic label="画像分布" :value="detail?.profiles.length || 0"><template #suffix>项</template></NStatistic></NCard></NGi><NGi><NCard :bordered="false" class="card-wrapper"><div class="text-13px text-gray-500">数据完备度</div><div class="my-8px text-24px font-700">{{ readiness }}%</div><NProgress :percentage="readiness" :height="6" /></NCard></NGi></NGrid>
      <NAlert v-if="readiness < 50" type="warning" show-icon>当前可分析数据较少，建议先执行刷新采集；ASR 未开启时，话术评分可能无法运行。</NAlert>
      <NCard :bordered="false" class="card-wrapper" title="分析工作台"><NSpace wrap><NButton type="primary" :loading="action === 'score'" @click="run('score')">话术质量评分</NButton><NButton type="warning" :loading="action === 'anomaly'" @click="run('anomaly')">数据异常检测</NButton><NButton type="success" :loading="action === 'optimize'" @click="run('optimize')">生成优化建议</NButton><NButton :loading="action === 'intent'" @click="run('intent')">识别高意向用户</NButton></NSpace></NCard>
      <NGrid :x-gap="16" :y-gap="16" cols="1 l:2" responsive="screen"><NGi v-for="item in [['score','话术评分'],['optimize','优化建议'],['anomaly','异常检测'],['intent','高意向用户']]" :key="item[0]"><NCard :bordered="false" class="card-wrapper h-full" :title="item[1]"><pre class="result-panel">{{ resultText(item[0]) }}</pre></NCard></NGi></NGrid>
    </NSpace>
  </NSpin>
</template>

<style scoped>.ai-hero { background: linear-gradient(120deg, rgba(32,128,240,.1), rgba(24,160,88,.08)), radial-gradient(circle at 80% 10%, rgba(240,160,32,.16), transparent 30%); }.result-panel { min-height: 150px; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; border-radius: 10px; background: rgba(128,128,128,.08); padding: 14px; font-size: 13px; line-height: 1.7; }</style>
