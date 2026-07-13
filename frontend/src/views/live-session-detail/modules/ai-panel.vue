<script setup lang="ts">
import { computed, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { detectAnomaly, detectHighIntent, optimizeSession, scoreSession } from '@/service/api/douyin';

defineOptions({ name: 'LiveSessionAiPanel' });
const props = defineProps<{ sessionId: number; detail: Api.Douyin.LiveSessionDetail | null }>();
const message = useMessage();
const action = ref('');
const results = ref<Record<string, unknown>>({});
const readiness = computed(() => props.detail ? [props.detail.metrics.length, props.detail.comments.length, props.detail.profiles.length, props.detail.stream_url].filter(Boolean).length * 25 : 0);

async function run(type: 'score' | 'anomaly' | 'optimize' | 'intent') {
  action.value = type;
  try {
    if (type === 'score') results.value.score = (await scoreSession(props.sessionId)).data?.result || {};
    if (type === 'anomaly') results.value.anomaly = (await detectAnomaly(props.sessionId)).data?.result || {};
    if (type === 'optimize') results.value.optimize = (await optimizeSession(props.sessionId)).data?.result || {};
    if (type === 'intent') results.value.intent = (await detectHighIntent(props.sessionId)).data || {};
    message.success('AI 分析完成');
  } catch (error) { message.error((error as { message?: string }).message || 'AI 分析失败，请检查模型配置和场次数据'); }
  finally { action.value = ''; }
}
function resultText(key: string) { return results.value[key] ? JSON.stringify(results.value[key], null, 2) : '尚未运行此项分析'; }
</script>

<template>
  <NSpace vertical :size="16">
    <NGrid :x-gap="14" :y-gap="14" cols="1 s:2 m:4" responsive="screen">
      <NGi><NStatistic label="分钟趋势" :value="detail?.metrics.length || 0"><template #suffix>条</template></NStatistic></NGi>
      <NGi><NStatistic label="评论语料" :value="detail?.comments.length || 0"><template #suffix>条</template></NStatistic></NGi>
      <NGi><NStatistic label="画像分布" :value="detail?.profiles.length || 0"><template #suffix>项</template></NStatistic></NGi>
      <NGi><div class="text-13px text-gray-500">数据完备度</div><div class="my-6px text-24px font-700">{{ readiness }}%</div><NProgress :percentage="readiness" :height="6" /></NGi>
    </NGrid>
    <NAlert v-if="readiness < 50" type="warning" show-icon>当前可分析数据较少，建议先执行刷新采集；ASR 未开启时，话术评分可能无法运行。</NAlert>
    <NSpace wrap><NButton type="primary" :loading="action === 'score'" @click="run('score')">话术质量评分</NButton><NButton type="warning" :loading="action === 'anomaly'" @click="run('anomaly')">数据异常检测</NButton><NButton type="success" :loading="action === 'optimize'" @click="run('optimize')">生成优化建议</NButton><NButton :loading="action === 'intent'" @click="run('intent')">识别高意向用户</NButton></NSpace>
    <NGrid :x-gap="14" :y-gap="14" cols="1 l:2" responsive="screen"><NGi v-for="item in [['score','话术评分'],['optimize','优化建议'],['anomaly','异常检测'],['intent','高意向用户']]" :key="item[0]"><NCard size="small" :title="item[1]" :bordered="true"><pre class="result-panel">{{ resultText(item[0]) }}</pre></NCard></NGi></NGrid>
  </NSpace>
</template>

<style scoped>.result-panel { min-height: 130px; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; border-radius: 8px; background: rgba(128,128,128,.08); padding: 12px; font-size: 13px; line-height: 1.7; }</style>
