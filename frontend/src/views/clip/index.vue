<script setup lang="ts">
import { computed, ref } from 'vue';
import {
  NAlert,
  NButton,
  NEmpty,
  NGi,
  NGrid,
  NInput,
  NModal,
  NProgress,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage
} from 'naive-ui';
import { useClipData, clipVideoUrl } from './composables/useClipData';
import ClipCard from './modules/ClipCard.vue';

defineOptions({ name: 'Clip' });

const message = useMessage();

const clipData = useClipData(message);
const { loading, overview, sessionOptions, actionLoading, errorMessage, selectedSessionId } = clipData;

/* ---------- 预览 ---------- */
const previewClip = ref<Api.Douyin.ClipClip | null>(null);
const previewVisible = computed(() => Boolean(previewClip.value));

/* ---------- 生成 / 重剪弹窗 ---------- */
const regenerateTarget = ref<Api.Douyin.ClipClip | null>(null);
const regenerateAllMode = ref(false);
const hintText = ref('');
const hintModalVisible = computed(() => regenerateAllMode.value || Boolean(regenerateTarget.value));

function openGenerateAll() {
  regenerateAllMode.value = true;
  regenerateTarget.value = null;
  hintText.value = '';
}

function openPreview(clip: Api.Douyin.ClipClip) {
  previewClip.value = clip;
  // 浏览器原生 video 依赖短时媒体 Cookie（30 分钟），打开预览前续期，避免播放 401
  void clipData.refreshMediaCookie();
}

const videoError = ref('');

function onVideoError() {
  videoError.value = '视频加载失败：媒体凭证可能已过期，请刷新页面后重试（或重新登录）';
}

function closePreview() {
  previewClip.value = null;
  videoError.value = '';
}

function openRegenerate(clip: Api.Douyin.ClipClip) {
  regenerateAllMode.value = false;
  regenerateTarget.value = clip;
  hintText.value = '';
}

function confirmHintAction() {
  if (regenerateAllMode.value) {
    void clipData.generateAll(hintText.value || undefined);
  } else if (regenerateTarget.value) {
    void clipData.regenerateOne(regenerateTarget.value.clip_order, hintText.value || undefined);
  }
  regenerateAllMode.value = false;
  regenerateTarget.value = null;
  hintText.value = '';
}

/* ---------- 复制文案 ---------- */
async function copyPublishContent(clip: Api.Douyin.ClipClip) {
  const topics = (clip.topics || []).map(t => `#${t}`).join(' ');
  const text = `标题：${clip.title || ''}\n\n${clip.description || ''}\n${topics}`.trim();
  try {
    await navigator.clipboard.writeText(text);
    message.success('标题/文案/话题已复制，可直接粘贴到抖音发布');
  } catch {
    message.error('复制失败，请手动选择复制');
  }
}

function fmtDateTime(val: string | null): string {
  if (!val) return '-';
  const d = new Date(val);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}
</script>

<template>
  <div class="clip-page">
    <!-- 顶部工具栏 -->
    <NAlert v-if="errorMessage" type="error" closable class="clip-page__alert" @close="errorMessage = ''">
      {{ errorMessage }}
    </NAlert>

    <div class="clip-page__toolbar">
      <NSelect
        v-model:value="selectedSessionId"
        class="clip-page__session-select"
        placeholder="搜索主播、日期或场次"
        filterable
        clearable
        :options="sessionOptions"
        :render-label="clipData.renderSessionLabel"
        :loading="loading"
        @update:value="value => clipData.loadOverview(value as number)"
      />
      <NButton type="primary" :loading="actionLoading" @click="openGenerateAll">
        生成/重新生成 5 条成片
      </NButton>
    </div>

    <!-- 任务进度 -->
    <NAlert v-if="overview?.task && clipData.isTaskRunning()" type="info" class="clip-page__alert">
      <div class="clip-page__task">
        <span>
          剪辑任务进行中：{{ overview.task.progress_stage || '' }}（{{
            overview.task.progress_message || '排队中'
          }}）
        </span>
        <NProgress
          type="line"
          :percentage="overview.task.progress_percent || 0"
          :height="6"
          processing
          class="clip-page__progress"
        />
      </div>
    </NAlert>

    <!-- 场次信息 -->
    <div v-if="overview" class="clip-page__session-info">
      <NText strong>{{ overview.session_title || '未知场次' }}</NText>
      <NSpace :size="12">
        <NTag size="small" :bordered="false" type="info">{{ overview.anchor_name || '未知主播' }}</NTag>
        <NTag size="small" :bordered="false" type="default">
          {{ fmtDateTime(overview.live_start_time) }}
        </NTag>
        <NTag size="small" :bordered="false" type="default">
          时长 {{ Math.floor((overview.live_duration_seconds || 0) / 60) }} 分钟
        </NTag>
      </NSpace>
    </div>

    <!-- 成片网格 -->
    <div class="clip-page__grid-area">
      <NSpin :show="loading">
        <NEmpty
          v-if="!loading && (!overview || overview.clips.length === 0)"
          description="该场次还没有成片，点击上方按钮生成；或换一场直播试试"
        />
        <NGrid v-else :cols="1" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
          <NGi v-for="clip in overview?.clips || []" :key="clip.id" span="24 s:12 m:8 l:6">
            <ClipCard
              :clip="clip"
              @preview="openPreview"
              @approve="clipData.approve(clip.id)"
              @discard="clipData.discard(clip.id)"
              @regenerate="openRegenerate"
            />
          </NGi>
        </NGrid>
      </NSpin>
    </div>

    <!-- 成片预览 -->
    <NModal
      :show="previewVisible"
      preset="card"
      class="clip-page__preview"
      :style="{ width: 'min(720px, 92vw)' }"
      :title="previewClip?.title || '成片预览'"
      @close="closePreview"
      @update:show="show => !show && closePreview()"
    >
      <div v-if="previewClip" class="clip-page__preview-body">
        <NAlert v-if="videoError" type="warning" class="clip-page__video-error">{{ videoError }}</NAlert>
        <video :src="clipVideoUrl(previewClip.id)" controls class="clip-page__video" @error="onVideoError" />
        <div class="clip-page__publish">
          <div class="clip-page__publish-row">
            <NText strong>标题</NText>
            <NText>{{ previewClip.title }}</NText>
          </div>
          <div class="clip-page__publish-row">
            <NText strong>文案</NText>
            <NText class="clip-page__publish-text">{{ previewClip.description }}</NText>
          </div>
          <div class="clip-page__publish-row">
            <NText strong>话题</NText>
            <NSpace :size="6">
              <NTag v-for="topic in previewClip.topics" :key="topic" size="small" round type="info">#{{ topic }}</NTag>
            </NSpace>
          </div>
          <div class="clip-page__publish-row">
            <NText strong>片段时间轴</NText>
            <NText>
              <template v-for="(seg, index) in previewClip.segments" :key="index">
                {{ seg.start.toFixed(0) }}s-{{ seg.end.toFixed(0) }}s<template v-if="index < previewClip.segments.length - 1">, </template>
              </template>
            </NText>
          </div>
          <NSpace class="clip-page__publish-actions">
            <NButton type="primary" @click="copyPublishContent(previewClip)">复制标题/文案/话题</NButton>
            <NButton
              v-if="previewClip.status === 'draft' && previewClip.video_path"
              ghost
              type="primary"
              @click="clipData.approve(previewClip.id)"
            >
              确认成片
            </NButton>
          </NSpace>
        </div>
      </div>
    </NModal>

    <!-- 生成 / 重剪弹窗 -->
    <NModal
      :show="hintModalVisible"
      preset="card"
      :title="regenerateAllMode ? '生成 AI 成片' : `重剪成片 #${regenerateTarget?.clip_order || ''}`"
      :style="{ width: 'min(480px, 92vw)' }"
      @update:show="show => !show && (regenerateAllMode = false, regenerateTarget = null)"
    >
      <div class="clip-page__hint">
        <NText depth="3">
          可选：输入你想要的选题方向（如「品牌避坑」「选址」「预算」），AI 会按你的要求重新选段；
          留空则由 AI 自主选题。
        </NText>
        <NInput v-model:value="hintText" type="textarea" :rows="3" placeholder="例如：讲一个加盟品牌被割韭菜的真实案例" />
        <NSpace justify="end" class="clip-page__hint-actions">
          <NButton @click="regenerateAllMode = false; regenerateTarget = null">取消</NButton>
          <NButton type="primary" :loading="actionLoading" @click="confirmHintAction">开始生成</NButton>
        </NSpace>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.clip-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.clip-page__alert {
  border-radius: 8px;
}

.clip-page__toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.clip-page__session-select {
  width: min(480px, 100%);
}

.clip-page__option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
  max-width: 460px;
}

.clip-page__option-main {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clip-page__option-sub {
  font-size: 12px;
  color: rgba(128, 128, 128, 0.9);
}

.clip-page__video-error {
  margin-bottom: 8px;
}

.clip-page__task {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.clip-page__progress {
  max-width: 480px;
}

.clip-page__session-info {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.clip-page__grid-area {
  min-height: 200px;
}

.clip-page__preview-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.clip-page__video {
  width: 100%;
  max-height: 420px;
  border-radius: 8px;
  background: #000;
}

.clip-page__publish {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.clip-page__publish-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  font-size: 13px;
}

.clip-page__publish-row > :first-child {
  min-width: 56px;
}

.clip-page__publish-text {
  white-space: pre-wrap;
  word-break: break-all;
}

.clip-page__publish-actions {
  margin-top: 6px;
}

.clip-page__hint {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.clip-page__hint-actions {
  margin-top: 4px;
}
</style>
