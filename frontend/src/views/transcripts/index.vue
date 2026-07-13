<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { NTag, NButton, useMessage } from 'naive-ui';
import { $t } from '@/locales';
import { useWebSocket } from '@vueuse/core';
import {
  fetchTranscriptSegments,
  fetchTranscriptFullText,
  fetchLiveSessions,
  fetchTranscriptTaskStatus,
  queueTranscript,
  queueTranscriptsByAnchor,
  runTranscriptAiPipeline
} from '@/service/api/douyin';

defineOptions({
  name: 'Transcripts'
});

const message = useMessage();

/* ---------- 数据 ---------- */
const sessions = ref<{ id: number; title: string }[]>([]);
const segments = ref<Api.Douyin.TranscriptSegment[]>([]);
const fullText = ref('');
const loading = ref(true);
const batchLoading = ref(false);
const selectedSessionId = ref<number | null>(null);
const taskSummary = ref({ queued: 0, processing: 0, completed: 0, failed: 0 });

/* ---------- WebSocket ---------- */
const wsUrl = computed(() => {
  const base = import.meta.env.VITE_SERVICE_BASE_URL || 'http://localhost:8000';
  const wsBase = base.replace(/^http/, 'ws');
  return selectedSessionId.value ? `${wsBase}/ws/transcript/${selectedSessionId.value}` : '';
});

const { status, data: wsData, open, close } = useWebSocket(wsUrl, {
  autoReconnect: { retries: 5, delay: 3000 },
  heartbeat: { message: 'ping', interval: 30000 },
});

const wsConnected = computed(() => status.value === 'OPEN');

// 监听 WebSocket 消息
watch(wsData, (msg) => {
  if (!msg) return;
  try {
    const result = JSON.parse(msg as string);
    if (result.text) {
      const seg: Api.Douyin.TranscriptSegment = {
        id: Date.now(),
        session_id: selectedSessionId.value || 0,
        segment_start: result.segment_start || 0,
        segment_end: result.segment_end || 0,
        text_content: result.text,
        segment_type: 'asr_realtime',
        asr_status: result.is_final ? 'completed' : 'processing',
        ai_score: null,
      };
      segments.value.push(seg);
    }
  } catch { /* ignore */ }
});

/* ---------- 方法 ---------- */
async function loadSessions() {
  try {
    const res = await fetchLiveSessions();
    if (res.data) {
      sessions.value = res.data.map((s: any) => {
        const date = s.live_start_time ? String(s.live_start_time).slice(0, 16).replace('T', ' ') : '时间未知';
        const minutes = Math.max(0, Math.round((s.live_duration_seconds || 0) / 60));
        return {
          id: s.id,
          title: `${s.anchor_name || '未知主播'} · ${date} · ${minutes}分钟 · #${s.id}`
        };
      });
    }
  } catch { /* ignore */ }
}

async function loadTaskSummary() {
  try {
    const res = await fetchTranscriptTaskStatus();
    if (res.data) taskSummary.value = res.data;
  } catch { /* 页面仍可使用单场转写 */ }
}

async function queueAnchorBatch() {
  batchLoading.value = true;
  try {
    const res = await queueTranscriptsByAnchor(1);
    const data = res.data;
    if (!data) throw new Error('批量任务响应为空');
    message.success(`已覆盖 ${data.anchor_count} 位主播，新建 ${data.created_count} 个真实转写任务`);
    await loadTaskSummary();
  } catch {
    message.error('批量排队失败，请确认已采集到真实直播流');
  } finally {
    batchLoading.value = false;
  }
}

async function selectSession(sessionId: number) {
  selectedSessionId.value = sessionId;
  loading.value = true;
  try {
    const [segRes, textRes] = await Promise.all([
      fetchTranscriptSegments(sessionId),
      fetchTranscriptFullText(sessionId).catch(() => ({ data: null })),
    ]);
    segments.value = segRes.data || [];
    fullText.value = (textRes.data as any)?.full_text || '';
  } catch {
    segments.value = [];
  } finally {
    loading.value = false;
  }
}

async function copyFullText() {
  const text = fullText.value || segments.value.map(s =>
    `[${s.segment_start.toFixed(1)}s] ${s.text_content}`
  ).join('\n');
  try {
    await navigator.clipboard.writeText(text);
    message.success($t('page.transcripts.copySuccess'));
  } catch {
    // fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    message.success($t('page.transcripts.copySuccess'));
  }
}

async function startTranscription() {
  if (!selectedSessionId.value) return;
  try {
    const res = await queueTranscript(selectedSessionId.value);
    const data = res.data;
    if (!data) throw new Error('转写任务响应为空');
    message.success(`转写任务已${data.created ? '创建' : '在队列中'}（${data.task_id}）`);
  } catch {
    message.error('该场次暂无可用直播流，请先重新采集');
  }
}

async function runAiPipeline() {
    if (!selectedSessionId.value) return;
  try {
    const res = await runTranscriptAiPipeline(selectedSessionId.value);
    const saved = (res.data?.transcript_saved ?? 0) + (res.data?.analysis_saved ?? 0);
    message.success(`AI 分析完成，知识库新增 ${saved} 条`);
  } catch {
    message.error('请先完成该场次的话术转写');
  }
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function getStatusType(status: string): 'success' | 'warning' | 'error' | 'info' {
  if (status === 'completed') return 'success';
  if (status === 'processing') return 'warning';
  if (status === 'failed') return 'error';
  return 'info';
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: $t('page.transcripts.statusPending'),
    processing: $t('page.transcripts.statusProcessing'),
    completed: $t('page.transcripts.statusCompleted'),
    failed: $t('page.transcripts.statusFailed'),
  };
  return map[status] || status;
}

/* ---------- 生命周期 ---------- */
onMounted(() => {
  loadSessions();
  loadTaskSummary();
});

onUnmounted(() => {
  close();
});

// 当选中 session 变化时打开 WebSocket
watch(selectedSessionId, (newId) => {
  if (newId) {
    close();
    // 重新打开（useWebSocket 的 url 变化后自动重连）
    setTimeout(() => open(), 100);
  }
});

</script>

<template>
  <div>
    <!-- 选择场次 + 连接状态 -->
    <NCard :bordered="false" class="card-wrapper mb-16px">
      <NSpace justify="space-between" align="center">
        <NSpace :size="16" align="center">
          <SvgIcon icon="mdi:chat-text" class="text-22px" />
          <span class="text-16px font-bold">{{ $t('page.transcripts.title') }}</span>
          <NSelect
            v-model:value="selectedSessionId"
            :placeholder="$t('page.transcripts.selectSession')"
            :options="sessions.map(s => ({ label: s.title, value: s.id }))"
            style="width: 420px"
            size="small"
            @update:value="selectSession"
          />
        </NSpace>
        <NSpace :size="12">
          <NTag type="info" round size="small">排队 {{ taskSummary.queued }}</NTag>
          <NTag type="warning" round size="small">处理中 {{ taskSummary.processing }}</NTag>
          <NTag type="success" round size="small">完成 {{ taskSummary.completed }}</NTag>
          <NTag v-if="taskSummary.failed" type="error" round size="small">失败 {{ taskSummary.failed }}</NTag>
          <NTag :type="wsConnected ? 'success' : 'default'" round size="small">
            {{ wsConnected ? $t('page.transcripts.wsConnected') : $t('page.transcripts.wsDisconnected') }}
          </NTag>
          <NButton size="small" type="primary" secondary @click="copyFullText">
            <template #icon>
              <SvgIcon icon="mdi:content-copy" />
            </template>
            {{ $t('page.transcripts.copyFullText') }}
          </NButton>
          <NButton size="small" type="primary" @click="startTranscription" :disabled="!selectedSessionId">
            开始转写
          </NButton>
          <NButton size="small" type="primary" secondary :loading="batchLoading" @click="queueAnchorBatch">
            各主播增量转写
          </NButton>
          <NButton size="small" @click="runAiPipeline" :disabled="!selectedSessionId">
            AI 分析并入库
          </NButton>
        </NSpace>
      </NSpace>
    </NCard>

    <NGrid :x-gap="16" :y-gap="16" cols="1 m:3" responsive="screen">
      <!-- 分段列表 -->
      <NGi span="2">
        <NCard :bordered="false" class="card-wrapper" :title="$t('page.transcripts.title')">
          <div v-if="!selectedSessionId" class="py-40px text-center text-gray-400">
            {{ $t('page.transcripts.selectSession') }}
          </div>
          <NSpin v-else :show="loading">
            <NSpace vertical :size="12">
              <div
                v-for="item in segments"
                :key="item.id"
                class="flex items-start gap-16px rounded-8px p-12px"
                :class="[
                  item.asr_status === 'processing'
                    ? 'bg-primary-50 dark:bg-primary-900/20 border border-primary-300'
                    : 'bg-gray-50 dark:bg-dark-300'
                ]"
              >
                <div class="flex-shrink-0 w-50px text-13px text-gray-500 font-mono">
                  {{ formatTime(item.segment_start) }}
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-14px leading-22px mb-6px">{{ item.text_content }}</p>
                  <div class="flex items-center gap-8px">
                    <NTag :type="getStatusType(item.asr_status)" size="tiny">
                      {{ getStatusLabel(item.asr_status) }}
                    </NTag>
                    <span v-if="item.segment_end" class="text-12px text-gray-400">
                      {{ (item.segment_end - item.segment_start).toFixed(1) }}s
                    </span>
                  </div>
                </div>
              </div>

              <!-- 转写中状态 -->
              <div v-if="wsConnected && segments.length > 0" class="text-center py-8px">
                <NSpin :size="16" />
                <span class="ml-8px text-13px text-gray-400">
                  {{ $t('page.transcripts.transcribing') }}
                </span>
              </div>

              <div v-if="!loading && segments.length === 0" class="text-center py-40px text-gray-400">
                {{ $t('common.noData') }}
              </div>
            </NSpace>
          </NSpin>
        </NCard>
      </NGi>

      <!-- 时间轴 -->
      <NGi span="1">
        <NCard :bordered="false" class="card-wrapper" :title="$t('page.transcripts.timeline')">
          <div v-if="segments.length === 0" class="py-40px text-center text-gray-400">
            {{ $t('common.noData') }}
          </div>
          <div v-for="item in segments.slice().reverse().slice(0, 30)" :key="item.id" class="mb-12px">
            <div class="flex items-start gap-8px">
              <div class="flex-shrink-0 w-45px text-12px text-gray-400 font-mono">
                {{ formatTime(item.segment_start) }}
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-13px truncate">{{ item.text_content }}</p>
                <div class="mt-2px">
                  <NProgress
                    type="line"
                    :percentage="Math.min(item.segment_end - item.segment_start, 30) / 30 * 100"
                    :height="3"
                    :border-radius="2"
                    indicator-placement="inside"
                  />
                </div>
              </div>
            </div>
          </div>
        </NCard>
      </NGi>
    </NGrid>
  </div>
</template>

<style scoped></style>
