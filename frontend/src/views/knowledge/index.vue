<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { NTag, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import {
  askKnowledge,
  fetchKnowledgeItems,
  fetchKnowledgeTimeSlices,
  fetchKnowledgeTimeSliceStatus,
  syncRecentKnowledge
} from '@/service/api/douyin';

defineOptions({ name: 'Knowledge' });

const message = useMessage();

/* ---------- 知识库列表 ---------- */
const items = ref<Api.Douyin.KnowledgeItem[]>([]);
const timeSlices = ref<Api.Douyin.KnowledgeTimeSlice[]>([]);
const sliceStatus = ref<Api.Douyin.KnowledgeTimeSliceStatus | null>(null);
const loading = ref(false);
const syncing = ref(false);

async function syncRecent() {
  syncing.value = true;
  try {
    const res = await syncRecentKnowledge(20);
    const data = res.data;
    message.success(
      `已同步 ${data?.session_count || 0} 场：新增时间片 ${data?.time_slices_created || 0} 个，更新 ${data?.time_slices_updated || 0} 个`
    );
    await loadItems();
  } catch {
    message.error('同步知识库失败');
  } finally {
    syncing.value = false;
  }
}

async function loadItems() {
  loading.value = true;
  try {
    const [itemsRes, slicesRes, statusRes] = await Promise.all([
      fetchKnowledgeItems(),
      fetchKnowledgeTimeSlices({ limit: 30 }),
      fetchKnowledgeTimeSliceStatus()
    ]);
    items.value = itemsRes.data || [];
    timeSlices.value = slicesRes.data || [];
    sliceStatus.value = statusRes.data || null;
  } catch {
    message.error('知识库加载失败');
  } finally {
    loading.value = false;
  }
}

onMounted(loadItems);

function formatOffset(seconds: number) {
  const value = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = value % 60;
  return [hours, minutes, secs].map(item => String(item).padStart(2, '0')).join(':');
}

/* ---------- 聊天 ---------- */
const question = ref('');
const chatting = ref(false);
const messages = ref<{ role: 'user' | 'ai'; content: string; sources?: Api.Douyin.KnowledgeSource[] }[]>([]);
const chatEndRef = ref<HTMLElement | null>(null);

async function sendQuestion() {
  const q = question.value.trim();
  if (!q) return;
  messages.value.push({ role: 'user', content: q });
  question.value = '';
  chatting.value = true;
  try {
    const res = await askKnowledge(q);
    messages.value.push({ role: 'ai', content: res.data?.answer || '暂无回答', sources: res.data?.sources || [] });
  } catch {
    messages.value.push({ role: 'ai', content: '请求失败，请稍后重试' });
  }
  chatting.value = false;
  setTimeout(() => chatEndRef.value?.scrollIntoView({ behavior: 'smooth' }), 100);
}
</script>

<template>
  <div>
    <NGrid :x-gap="16" :y-gap="16" cols="2 s:4" responsive="screen" class="mb-16px">
      <NGi>
        <NCard :bordered="false" size="small" class="card-wrapper h-full">
          <NStatistic label="知识时间片" :value="sliceStatus?.slice_count || 0">
            <template #suffix><span class="text-12px text-gray-400">个</span></template>
          </NStatistic>
          <p class="mb-0 mt-8px text-12px text-gray-500">覆盖 {{ sliceStatus?.session_count || 0 }} 场真实直播</p>
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" size="small" class="card-wrapper h-full">
          <NStatistic label="话术时间片" :value="sliceStatus?.transcript_slice_count || 0" />
          <p class="mb-0 mt-8px text-12px text-gray-500">每 {{ (sliceStatus?.slice_seconds || 300) / 60 }} 分钟建立检索块</p>
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" size="small" class="card-wrapper h-full">
          <NStatistic label="评论时间片" :value="sliceStatus?.comment_slice_count || 0" />
          <p class="mb-0 mt-8px text-12px text-gray-500">仅按平台时间精确绑定</p>
        </NCard>
      </NGi>
      <NGi>
        <NCard :bordered="false" size="small" class="card-wrapper h-full">
          <NStatistic label="指标时间片" :value="sliceStatus?.metric_slice_count || 0" />
          <p class="mb-0 mt-8px text-12px text-gray-500">未映射评论 {{ sliceStatus?.unmapped_comment_count || 0 }} 条</p>
        </NCard>
      </NGi>
    </NGrid>

    <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
      <!-- 知识库列表 -->
      <NGi span="1 m:2">
        <NCard :bordered="false" class="card-wrapper">
          <template #header>
            <div class="flex w-full items-center justify-between gap-12px">
              <NSpace><SvgIcon icon="mdi:book-open-variant" class="text-22px" /><span class="text-16px font-bold">{{ $t('page.knowledge.title') }}</span></NSpace>
              <NButton type="primary" secondary :loading="syncing" @click="syncRecent">
                <template #icon><SvgIcon icon="mdi:database-sync-outline" /></template>
                同步最近20场
              </NButton>
            </div>
          </template>
          <NAlert type="info" :show-icon="true" class="mb-12px">
            时间片只绑定有准确平台时间的数据；缺少时间的评论会单独计数，不会被错误分配到话术片段。
          </NAlert>
          <NSpin :show="loading">
            <NTabs type="line" animated>
              <NTabPane name="time-slices" tab="5分钟时间片">
                <NEmpty v-if="timeSlices.length === 0" class="py-40px" description="暂无知识时间片，请先同步" />
                <NSpace v-else vertical :size="12">
                  <NCard v-for="slice in timeSlices" :key="slice.id" size="small" embedded>
                    <div class="flex flex-wrap items-center justify-between gap-8px">
                      <div>
                        <strong>{{ slice.anchor_name || '未知主播' }}</strong>
                        <span class="ml-8px text-12px text-gray-500">场次 #{{ slice.session_id }}</span>
                      </div>
                      <NTag size="small" type="success">
                        {{ formatOffset(slice.slice_start_seconds) }} - {{ formatOffset(slice.slice_end_seconds) }}
                      </NTag>
                    </div>
                    <p class="my-8px text-12px text-gray-500">{{ slice.session_title || '未命名直播' }}</p>
                    <div class="grid grid-cols-3 gap-8px rounded-8px bg-gray-50 p-8px text-center text-12px dark:bg-dark-300">
                      <span>评论 {{ slice.comment_count }}</span>
                      <span>指标 {{ slice.metric_point_count }}</span>
                      <span>峰值在线 {{ slice.peak_online_count }}</span>
                    </div>
                    <p v-if="slice.transcript_text" class="line-clamp-4 mb-0 mt-8px whitespace-pre-wrap text-13px leading-22px">
                      {{ slice.transcript_text }}
                    </p>
                    <p v-else-if="slice.comments_text" class="line-clamp-4 mb-0 mt-8px whitespace-pre-wrap text-13px leading-22px">
                      {{ slice.comments_text }}
                    </p>
                  </NCard>
                </NSpace>
              </NTabPane>
              <NTabPane name="whole-session" tab="整场知识">
                <NEmpty v-if="items.length === 0" class="py-40px" description="知识库为空" />
                <NSpace v-else vertical :size="12">
                  <NCard v-for="item in items" :key="item.id" size="small" embedded>
                    <NSpace justify="space-between" align="center">
                      <strong>{{ item.title || `知识条目 #${item.id}` }}</strong>
                      <NTag size="small" type="info">{{ item.category || '未分类' }}</NTag>
                    </NSpace>
                    <p class="line-clamp-6 mt-8px whitespace-pre-wrap text-13px leading-22px text-gray-600">
                      {{ item.content || '暂无内容' }}
                    </p>
                  </NCard>
                </NSpace>
              </NTabPane>
            </NTabs>
          </NSpin>
        </NCard>
      </NGi>

      <!-- AI 聊天窗 -->
      <NGi span="1">
        <NCard :bordered="false" class="card-wrapper h-full m:sticky m:top-16px">
          <template #header>
            <NSpace>
              <SvgIcon icon="mdi:chat-question" class="text-18px" />
              <span class="text-15px font-bold">AI 助手</span>
            </NSpace>
          </template>

          <!-- 消息列表 -->
          <div ref="chatEndRef" class="h-400px overflow-y-auto mb-12px px-4px">
            <div v-if="messages.length === 0" class="flex flex-col items-center justify-center py-40px text-center">
              <SvgIcon icon="mdi:robot-outline" class="text-64px text-gray-300 dark:text-gray-600 mb-16px" />
              <p class="text-14px text-gray-500 mb-8px">{{ $t('page.knowledge.chatPlaceholder') }}</p>
              <p class="text-12px text-gray-400">{{ $t('page.knowledge.chatDesc') }}</p>
            </div>
            <div
              v-for="(msg, i) in messages"
              :key="i"
              class="mb-12px"
              :class="msg.role === 'user' ? 'text-right' : 'text-left'"
            >
              <NTag :type="msg.role === 'user' ? 'primary' : 'success'" size="small" class="mb-4px">
                {{ msg.role === 'user' ? '我' : 'AI' }}
              </NTag>
              <div
                :class="
                  msg.role === 'user'
                    ? 'rounded-8px p-10px inline-block max-w-90% text-left leading-22px text-13px bg-primary-light text-white'
                    : 'rounded-8px p-10px inline-block max-w-90% text-left leading-22px text-13px bg-gray-100 dark:bg-dark-300'
                "
              >
                {{ msg.content }}
                <div v-if="msg.sources?.length" class="mt-10px border-t border-gray-200/60 pt-8px text-11px text-gray-500">
                  <div class="mb-6px font-medium">引用来源</div>
                  <div
                    v-for="source in msg.sources"
                    :key="`${source.source_type}-${source.id}`"
                    class="mb-6px rounded-6px border border-gray-200/70 p-7px last:mb-0 dark:border-dark-100"
                  >
                    <div class="font-medium text-gray-700 dark:text-gray-200">{{ source.title || '未命名来源' }}</div>
                    <div v-if="source.source_types?.length" class="mt-3px">
                      {{ source.source_types.join(' + ') }}
                    </div>
                    <div v-if="source.excerpt" class="line-clamp-2 mt-3px text-gray-400">{{ source.excerpt }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入框 -->
          <NSpace>
            <NInput
              v-model:value="question"
              type="text"
              placeholder="输入问题..."
              :disabled="chatting"
              @keyup.enter="sendQuestion"
            />
            <NButton type="primary" :loading="chatting" @click="sendQuestion">发送</NButton>
          </NSpace>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped></style>
