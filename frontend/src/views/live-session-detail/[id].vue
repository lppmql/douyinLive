<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { useRouter } from 'vue-router';
import { fetchLiveSessionData, getLiveSessionVideoDownloadUrl } from '@/service/api/douyin';
import { unwrapServiceData } from '@/utils/service';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import SessionWorkflowNav from '@/components/business/session-workflow-nav.vue';
import CommentGroups from './modules/comment-groups.vue';
import ReviewWorkbench from './modules/review-workbench.vue';

defineOptions({ name: 'LiveSessionDetail' });
const props = defineProps<{ id: string }>();
const router = useRouter();
const message = useMessage();
const loading = ref(false);
const videoDownloading = ref(false);
const detail = ref<Api.Douyin.LiveSessionDetail | null>(null);
const loadError = ref('');
const session = computed(() => detail.value?.session);

const profilesColumns: NaiveUI.TableColumn<Api.Douyin.LiveAudienceProfile>[] = [
  { title: '画像维度', key: 'dimension_type', width: 140 },
  { title: '分布项', key: 'dimension_name' },
  { title: '占比', key: 'ratio', width: 120, render: row => `${Number(row.ratio).toFixed(1)}%` }
];

const kpis = computed(() => {
  const s = session.value;
  return s
    ? [
        ['累计观看', s.total_viewers, 'mdi:account-eye-outline'],
        ['峰值在线', s.peak_online_count, 'mdi:account-group-outline'],
        ['平均停留', `${Number(s.avg_watch_seconds || 0).toFixed(1)} 秒`, 'mdi:timer-outline'],
        ['评论总数', s.comments_count, 'mdi:comment-text-outline'],
        ['新增关注', s.new_followers, 'mdi:account-plus-outline'],
        ['有效线索', s.leads_count, 'mdi:target-account']
      ]
    : [];
});

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-';
}
function formatNumber(value?: number | null) {
  return Number(value || 0).toLocaleString();
}
function videoFilename() {
  const anchor = session.value?.anchor_name || '直播回放';
  return `${anchor}-场次${props.id}.mp4`.replace(/[\\/:*?"<>|]/g, '_');
}
async function copyStreamUrl() {
  if (!detail.value?.stream_url) return;
  await navigator.clipboard.writeText(detail.value.stream_url);
  message.success('m3u8 地址已复制');
}
async function downloadVideo() {
  if (!detail.value?.stream_url || videoDownloading.value) return;
  videoDownloading.value = true;
  try {
    const picker = (
      window as Window & {
        showSaveFilePicker?: (options: Record<string, unknown>) => Promise<{
          createWritable: () => Promise<WritableStream<Uint8Array>>;
        }>;
      }
    ).showSaveFilePicker;
    const url = getLiveSessionVideoDownloadUrl(Number(props.id));
    if (!picker) {
      const link = document.createElement('a');
      link.href = url;
      link.download = videoFilename();
      link.click();
      message.info('浏览器已开始下载，可在下载设置中选择保存位置');
      return;
    }

    const fileHandle = await picker({
      suggestedName: videoFilename(),
      types: [{ description: 'MP4 视频', accept: { 'video/mp4': ['.mp4'] } }]
    });
    const response = await fetch(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `下载请求失败 (${response.status})`);
    }
    if (!response.body) throw new Error('浏览器不支持流式写入');
    const writable = await fileHandle.createWritable();
    await response.body.pipeTo(writable);
    message.success('直播视频已保存到所选位置');
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    message.error(error instanceof Error ? error.message : '直播视频下载失败');
  } finally {
    videoDownloading.value = false;
  }
}
async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    detail.value = unwrapServiceData(await fetchLiveSessionData(Number(props.id)), '后台没有返回该场次的详情数据。');
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '直播场次详情加载失败';
    message.error(loadError.value);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <NSpace vertical :size="16" class="business-page" :aria-busy="loading">
    <div class="flex flex-wrap items-center justify-between gap-10px">
      <div class="flex min-w-0 flex-wrap items-center gap-10px text-12px text-gray-500">
        <NButton size="small" secondary @click="router.push({ name: 'live-sessions' })">
          <template #icon><SvgIcon icon="mdi:arrow-left" /></template>
          返回列表
        </NButton>
        <AnchorIdentity
          v-if="session"
          class="max-w-240px"
          :session-id="Number(id)"
          :avatar-url="session.anchor_avatar_url"
          :name="session.anchor_name"
          :nickname="session.anchor_nickname"
          :douyin-id="session.douyin_id"
          :size="30"
          dense
        />
        <span>场次 #{{ id }}</span>
        <span>详情状态：{{ session?.detail_collection_status || (loading ? '读取中' : '-') }}</span>
      </div>
      <NTag v-if="session" :type="session.live_status === 'live' ? 'success' : 'default'" :bordered="false" round>
        {{ session.live_status === 'live' ? '直播中' : '已结束' }}
      </NTag>
    </div>

    <SessionWorkflowNav :session-id="Number(id)" active="detail" />

    <NCard v-if="loading && !detail" :bordered="false" class="business-loading-panel card-wrapper">
      <NSkeleton text :repeat="2" />
      <NSkeleton class="mt-20px" height="240px" :sharp="false" />
      <div class="mt-16px grid grid-cols-2 gap-12px lt-sm:grid-cols-1">
        <NSkeleton height="96px" :sharp="false" />
        <NSkeleton height="96px" :sharp="false" />
      </div>
    </NCard>

    <NResult
      v-else-if="loadError"
      status="error"
      title="场次详情暂时无法读取"
      :description="loadError"
      class="card-wrapper bg-white py-36px dark:bg-dark"
    >
      <template #footer>
        <NSpace justify="center">
          <NButton @click="router.push({ name: 'live-sessions' })">返回场次列表</NButton>
          <NButton type="primary" :loading="loading" @click="load">重新加载</NButton>
        </NSpace>
      </template>
    </NResult>

    <template v-else-if="detail">
      <ReviewWorkbench v-if="detail" :session-id="Number(id)" :detail="detail" @refresh-detail="load" />

      <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:3 l:6" responsive="screen">
        <NGi v-for="item in kpis" :key="String(item[0])">
          <NCard :bordered="false" class="card-wrapper">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-13px text-gray-500">{{ item[0] }}</div>
                <div class="mt-8px text-24px font-700">
                  {{ typeof item[1] === 'number' ? formatNumber(item[1]) : item[1] }}
                </div>
              </div>
              <SvgIcon :icon="String(item[2])" class="text-28px text-primary" />
            </div>
          </NCard>
        </NGi>
      </NGrid>

      <NGrid :x-gap="16" :y-gap="16" cols="1 l:3" responsive="screen">
        <NGi span="1 l:2">
          <NCard :bordered="false" class="card-wrapper" title="场次信息">
            <NDescriptions bordered :column="2" size="small">
              <NDescriptionsItem label="开始时间">{{ formatTime(session?.live_start_time) }}</NDescriptionsItem>
              <NDescriptionsItem label="结束时间">{{ formatTime(session?.live_end_time) }}</NDescriptionsItem>
              <NDescriptionsItem label="平均在线">{{ formatNumber(session?.avg_online_count) }}</NDescriptionsItem>
              <NDescriptionsItem label="看过人数">{{ formatNumber(session?.viewed_count) }}</NDescriptionsItem>
              <NDescriptionsItem label="互动次数">{{ formatNumber(session?.interaction_count) }}</NDescriptionsItem>
              <NDescriptionsItem label="私信人数">{{ formatNumber(session?.private_message_count) }}</NDescriptionsItem>
              <NDescriptionsItem label="广告消耗">¥{{ Number(session?.ad_cost || 0).toFixed(2) }}</NDescriptionsItem>
              <NDescriptionsItem label="详情状态">{{ session?.detail_collection_status || '-' }}</NDescriptionsItem>
            </NDescriptions>
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" class="card-wrapper h-full" title="回放源与下载">
            <NAlert v-if="!detail?.stream_url" type="warning" :show-icon="true">
              尚未采集到 m3u8 地址，请先到“数据采集”刷新该场次。
            </NAlert>
            <div v-else class="flex h-full flex-col gap-12px">
              <NInput
                :value="detail.stream_url"
                readonly
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 3 }"
                placeholder="m3u8 原始地址"
              />
              <div class="flex flex-wrap gap-8px">
                <NButton secondary @click="copyStreamUrl">复制 m3u8</NButton>
                <NTooltip :disabled="session?.live_status !== 'live'">
                  <template #trigger>
                    <NButton
                      type="primary"
                      :loading="videoDownloading"
                      :disabled="session?.live_status === 'live'"
                      @click="downloadVideo"
                    >
                      下载 MP4
                    </NButton>
                  </template>
                  当前仍在直播，请下播后下载完整视频
                </NTooltip>
              </div>
              <div class="text-12px leading-20px text-gray-500">
                使用原码流低开销封装，同一时间仅下载 1 场；播放器已在上方复盘工作台中展示。
              </div>
            </div>
          </NCard>
        </NGi>
      </NGrid>

      <NCard :bordered="false" class="card-wrapper" title="评论与观众画像">
        <NTabs type="line" animated default-value="comments">
          <NTabPane name="comments" :tab="`直播评论 (${detail?.comments.length || 0})`" display-directive="if">
            <CommentGroups :comments="detail?.comments || []" />
          </NTabPane>
          <NTabPane name="profiles" :tab="`观众画像 (${detail?.profiles.length || 0})`" display-directive="if">
            <NDataTable
              :columns="profilesColumns"
              :data="detail?.profiles || []"
              :pagination="{ pageSize: 20 }"
              size="small"
            />
          </NTabPane>
        </NTabs>
      </NCard>
    </template>
  </NSpace>
</template>

<style scoped></style>
