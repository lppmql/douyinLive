<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import { fetchLiveSessionData } from '@/service/api/douyin';
import MetricsChart from './modules/metrics-chart.vue';
import CommentGroups from './modules/comment-groups.vue';
import AiPanel from './modules/ai-panel.vue';

defineOptions({ name: 'LiveSessionDetail' });
const props = defineProps<{ id: string }>();
const router = useRouter();
const message = useMessage();
const loading = ref(false);
const detail = ref<Api.Douyin.LiveSessionDetail | null>(null);
const session = computed(() => detail.value?.session);

const profilesColumns: NaiveUI.TableColumn<Api.Douyin.LiveAudienceProfile>[] = [
  { title: '画像维度', key: 'dimension_type', width: 140 }, { title: '分布项', key: 'dimension_name' },
  { title: '占比', key: 'ratio', width: 120, render: row => `${Number(row.ratio).toFixed(1)}%` }
];

const kpis = computed(() => {
  const s = session.value;
  return s ? [
    ['累计观看', s.total_viewers, 'mdi:account-eye-outline'], ['峰值在线', s.peak_online_count, 'mdi:account-group-outline'],
    ['平均停留', `${Number(s.avg_watch_seconds || 0).toFixed(1)} 秒`, 'mdi:timer-outline'],
    ['评论总数', s.comments_count, 'mdi:comment-text-outline'], ['新增关注', s.new_followers, 'mdi:account-plus-outline'],
    ['有效线索', s.leads_count, 'mdi:target-account']
  ] : [];
});

function formatTime(value?: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'; }
function formatNumber(value?: number | null) { return Number(value || 0).toLocaleString(); }
async function load() {
  loading.value = true;
  try { detail.value = (await fetchLiveSessionData(Number(props.id))).data || null; }
  catch { message.error('直播场次详情加载失败'); }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <NSpin :show="loading">
    <NSpace vertical :size="16">
      <NCard :bordered="false" class="card-wrapper detail-hero">
        <div class="flex flex-wrap items-center justify-between gap-16px">
          <div class="flex min-w-0 items-center gap-16px">
            <NAvatar round :size="64" :src="session?.anchor_avatar_url || undefined" />
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-10px"><h2 class="m-0 truncate text-22px">{{ session?.anchor_name || '直播场次详情' }}</h2><NTag :type="session?.live_status === 'live' ? 'success' : 'default'" round :bordered="false">{{ session?.live_status === 'live' ? '直播中' : '已结束' }}</NTag></div>
              <div class="mt-6px truncate text-gray-500">{{ session?.session_title || '-' }}</div>
              <div class="mt-4px text-12px text-gray-400">抖音号 {{ session?.douyin_id || '-' }} · 场次 #{{ id }}</div>
            </div>
          </div>
          <NButton @click="router.push({ name: 'live-sessions' })">返回列表</NButton>
        </div>
      </NCard>

      <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:3 l:6" responsive="screen">
        <NGi v-for="item in kpis" :key="String(item[0])"><NCard :bordered="false" class="card-wrapper"><div class="flex items-center justify-between"><div><div class="text-13px text-gray-500">{{ item[0] }}</div><div class="mt-8px text-24px font-700">{{ typeof item[1] === 'number' ? formatNumber(item[1]) : item[1] }}</div></div><SvgIcon :icon="String(item[2])" class="text-28px text-primary" /></div></NCard></NGi>
      </NGrid>

      <NGrid :x-gap="16" :y-gap="16" cols="1 l:3" responsive="screen">
        <NGi span="1 l:2"><NCard :bordered="false" class="card-wrapper" title="场次信息"><NDescriptions bordered :column="2" size="small"><NDescriptionsItem label="开始时间">{{ formatTime(session?.live_start_time) }}</NDescriptionsItem><NDescriptionsItem label="结束时间">{{ formatTime(session?.live_end_time) }}</NDescriptionsItem><NDescriptionsItem label="平均在线">{{ formatNumber(session?.avg_online_count) }}</NDescriptionsItem><NDescriptionsItem label="看过人数">{{ formatNumber(session?.viewed_count) }}</NDescriptionsItem><NDescriptionsItem label="互动次数">{{ formatNumber(session?.interaction_count) }}</NDescriptionsItem><NDescriptionsItem label="私信人数">{{ formatNumber(session?.private_message_count) }}</NDescriptionsItem><NDescriptionsItem label="广告消耗">¥{{ Number(session?.ad_cost || 0).toFixed(2) }}</NDescriptionsItem><NDescriptionsItem label="详情状态">{{ session?.detail_collection_status || '-' }}</NDescriptionsItem></NDescriptions></NCard></NGi>
        <NGi><NCard :bordered="false" class="card-wrapper h-full" title="数据资产"><NList><NListItem><NThing title="分钟趋势" :description="`${detail?.metrics.length || 0} 条采样`" /></NListItem><NListItem><NThing title="直播评论" :description="`${detail?.comments.length || 0} 条去重评论`" /></NListItem><NListItem><NThing title="观众画像" :description="`${detail?.profiles.length || 0} 个分布项`" /></NListItem><NListItem><NThing title="直播流" :description="detail?.stream_url ? '已保存可用流地址' : '暂无可用流地址'" /></NListItem></NList></NCard></NGi>
      </NGrid>

      <NCard :bordered="false" class="card-wrapper">
        <NTabs type="line" animated>
          <NTabPane name="metrics" tab="分钟趋势"><MetricsChart :metrics="detail?.metrics || []" /></NTabPane>
          <NTabPane name="comments" :tab="`直播评论 (${detail?.comments.length || 0})`"><CommentGroups :comments="detail?.comments || []" /></NTabPane>
          <NTabPane name="profiles" :tab="`观众画像 (${detail?.profiles.length || 0})`"><NDataTable :columns="profilesColumns" :data="detail?.profiles || []" :pagination="{ pageSize: 20 }" size="small" /></NTabPane>
          <NTabPane name="ai" tab="AI 数据分析"><AiPanel :session-id="Number(id)" :detail="detail" /></NTabPane>
        </NTabs>
      </NCard>
    </NSpace>
  </NSpin>
</template>

<style scoped>
.detail-hero { background: linear-gradient(125deg, rgba(24,160,88,.1), rgba(32,128,240,.08)), radial-gradient(circle at 85% 20%, rgba(240,160,32,.14), transparent 32%); }
</style>
