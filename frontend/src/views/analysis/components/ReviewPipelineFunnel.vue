<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import {
  attributeLeadPair,
  fetchPendingLeadPairs,
  fetchReviewReadinessFunnel
} from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';

defineOptions({ name: 'ReviewPipelineFunnel' });

const message = useMessage();
const loading = ref(false);
const funnel = ref<Api.Douyin.ReviewReadinessFunnel | null>(null);
const pendingPairs = ref<Api.Douyin.PendingLeadPair[]>([]);
const selections = ref<Record<number, number | null>>({});
const savingPairId = ref<number | null>(null);

function fmt(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
}

async function load() {
  loading.value = true;
  try {
    const [funnelResponse, pairResponse] = await Promise.all([
      fetchReviewReadinessFunnel(),
      fetchPendingLeadPairs(10)
    ]);
    funnel.value = unwrapServiceData(funnelResponse, '数据闭环状态加载失败');
    pendingPairs.value = unwrapServiceData(pairResponse, '待归属客资加载失败');
  } catch (error) {
    message.error((error as { message?: string }).message || '数据闭环状态加载失败');
  } finally {
    loading.value = false;
  }
}

async function confirmAttribution(pair: Api.Douyin.PendingLeadPair) {
  const sessionId = selections.value[pair.id];
  if (!sessionId) return;
  savingPairId.value = pair.id;
  try {
    const result = unwrapServiceData(await attributeLeadPair(pair.id, sessionId), '客资归属失败');
    message.success(result.message);
    await load();
  } catch (error) {
    message.error((error as { message?: string }).message || '客资归属失败');
  } finally {
    savingPairId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <NCard :bordered="false" class="card-wrapper" title="数据闭环进度">
    <template #header-extra>
      <NButton text type="primary" :loading="loading" @click="load">刷新</NButton>
    </template>
    <NSpin :show="loading">
      <NGrid v-if="funnel" cols="2 s:4 l:7" responsive="screen" :x-gap="10" :y-gap="10">
        <NGi v-for="step in funnel.steps" :key="step.key">
          <NStatistic :label="step.label" :value="step.count" />
        </NGi>
      </NGrid>
      <NAlert v-if="funnel" class="mt-12px" type="info" :show-icon="false">
        已确认归属 {{ funnel.lead_attribution.attributed }}/{{ funnel.lead_attribution.total }} 条客资
        （{{ funnel.lead_attribution.rate }}%），待人工归属 {{ funnel.lead_attribution.pending }} 条。
      </NAlert>

      <NCollapse v-if="pendingPairs.length" class="mt-12px">
        <NCollapseItem :title="`待归属客资（当前展示 ${pendingPairs.length} 条）`">
          <div v-for="pair in pendingPairs" :key="pair.id" class="mb-10px rounded-8px border border-gray-200 p-12px dark:border-gray-700">
            <div class="flex flex-wrap items-center gap-8px text-13px">
              <NTag type="info" :bordered="false">{{ pair.anchor_name }}</NTag>
              <span>抖音号 {{ pair.douyin_id }}</span>
              <span>{{ pair.contact_type === 'phone' ? '手机号' : '微信号' }} {{ pair.contact_value }}</span>
              <span class="text-gray-400">{{ fmt(pair.converted_at) }} · 间隔 {{ pair.gap_seconds }} 秒</span>
            </div>
            <div class="mt-10px flex flex-wrap items-center gap-8px">
              <NSelect
                v-model:value="selections[pair.id]"
                class="w-420px max-w-full"
                placeholder="选择该抖音号评论过且位于承接窗口内的场次"
                :options="pair.candidate_sessions.map(item => ({
                  value: item.session_id,
                  label: `#${item.session_id} ${item.session_title || '未命名场次'} · ${fmt(item.live_start_time)}`
                }))"
                :disabled="!pair.candidate_sessions.length"
              />
              <NButton
                type="primary"
                :disabled="!selections[pair.id]"
                :loading="savingPairId === pair.id"
                @click="confirmAttribution(pair)"
              >
                确认归属
              </NButton>
              <NText v-if="!pair.candidate_sessions.length" depth="3">暂无该抖音号真实评论过且满足主播、时间窗口的候选场次</NText>
            </div>
          </div>
        </NCollapseItem>
      </NCollapse>
    </NSpin>
  </NCard>
</template>
