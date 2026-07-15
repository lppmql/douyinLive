<script setup lang="ts">
import { computed, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { detectAnomaly, detectHighIntent, optimizeSession, scoreSession } from '@/service/api/douyin';

defineOptions({ name: 'LiveSessionAiPanel' });
const props = defineProps<{ sessionId: number; detail: Api.Douyin.LiveSessionDetail | null }>();
const message = useMessage();
const action = ref('');
const results = ref<Record<string, unknown>>({});
const readiness = computed(() =>
  props.detail
    ? [
        props.detail.metrics.length,
        props.detail.comments.length,
        props.detail.profiles.length,
        props.detail.stream_url
      ].filter(Boolean).length * 25
    : 0
);

async function run(type: 'score' | 'anomaly' | 'optimize' | 'intent') {
  action.value = type;
  try {
    if (type === 'score') results.value.score = (await scoreSession(props.sessionId)).data?.result || {};
    if (type === 'anomaly') results.value.anomaly = (await detectAnomaly(props.sessionId)).data?.result || {};
    if (type === 'optimize') results.value.optimize = (await optimizeSession(props.sessionId)).data?.result || {};
    if (type === 'intent') results.value.intent = (await detectHighIntent(props.sessionId)).data || {};
    message.success('AI 分析完成');
  } catch (error) {
    message.error((error as { message?: string }).message || 'AI 分析失败，请检查模型配置和场次数据');
  } finally {
    action.value = '';
  }
}
function resultObject(key: string): Record<string, unknown> {
  const value = results.value[key];
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function primitiveEntries(key: string) {
  return Object.entries(resultObject(key)).filter(([, value]) => value === null || ['string', 'number', 'boolean'].includes(typeof value));
}
function arrayEntries(key: string) {
  return Object.entries(resultObject(key)).filter(([, value]) => Array.isArray(value));
}
function objectEntries(key: string) {
  return Object.entries(resultObject(key)).filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value));
}
function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}：${valueText(item)}`)
      .join('；');
  }
  return String(value);
}
</script>

<template>
  <NSpace vertical :size="16">
    <NGrid :x-gap="14" :y-gap="14" cols="1 s:2 m:4" responsive="screen">
      <NGi>
        <NStatistic label="分钟趋势" :value="detail?.metrics.length || 0"><template #suffix>条</template></NStatistic>
      </NGi>
      <NGi>
        <NStatistic label="评论语料" :value="detail?.comments.length || 0"><template #suffix>条</template></NStatistic>
      </NGi>
      <NGi>
        <NStatistic label="画像分布" :value="detail?.profiles.length || 0"><template #suffix>项</template></NStatistic>
      </NGi>
      <NGi>
        <div class="text-13px text-gray-500">数据完备度</div>
        <div class="my-6px text-24px font-700">{{ readiness }}%</div>
        <NProgress :percentage="readiness" :height="6" />
      </NGi>
    </NGrid>
    <NAlert v-if="readiness < 50" type="warning" show-icon>
      当前可分析数据较少，建议先执行刷新采集；ASR 未开启时，话术评分可能无法运行。
    </NAlert>
    <NSpace wrap>
      <NButton type="primary" :loading="action === 'score'" @click="run('score')">话术质量评分</NButton>
      <NButton type="warning" :loading="action === 'anomaly'" @click="run('anomaly')">数据异常检测</NButton>
      <NButton type="success" :loading="action === 'optimize'" @click="run('optimize')">生成优化建议</NButton>
      <NButton :loading="action === 'intent'" @click="run('intent')">识别高意向用户</NButton>
    </NSpace>
    <NGrid :x-gap="14" :y-gap="14" cols="1 l:2" responsive="screen">
      <NGi
        v-for="item in [
          ['score', '话术评分'],
          ['optimize', '优化建议'],
          ['anomaly', '异常检测'],
          ['intent', '高意向用户']
        ]"
        :key="item[0]"
      >
        <NCard size="small" :title="item[1]" :bordered="true">
          <NEmpty v-if="!results[item[0]]" description="尚未运行此项分析" class="py-26px" />
          <NSpace v-else vertical :size="12">
            <NDescriptions v-if="primitiveEntries(item[0]).length" :column="1" bordered size="small">
              <NDescriptionsItem v-for="entry in primitiveEntries(item[0])" :key="entry[0]" :label="entry[0]">
                {{ valueText(entry[1]) }}
              </NDescriptionsItem>
            </NDescriptions>
            <div v-for="entry in arrayEntries(item[0])" :key="entry[0]">
              <div class="mb-6px text-13px font-700">{{ entry[0] }}</div>
              <NList bordered size="small">
                <NListItem v-for="(value, index) in entry[1]" :key="index">{{ valueText(value) }}</NListItem>
              </NList>
            </div>
            <NCollapse v-if="objectEntries(item[0]).length">
              <NCollapseItem v-for="entry in objectEntries(item[0])" :key="entry[0]" :title="entry[0]">
                <div class="rounded-8px bg-gray-50 p-10px text-12px leading-20px dark:bg-dark-300">{{ valueText(entry[1]) }}</div>
              </NCollapseItem>
            </NCollapse>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>
  </NSpace>
</template>

<style scoped></style>
