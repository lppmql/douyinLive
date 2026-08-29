<script setup lang="ts">
import { computed, ref } from 'vue';
import {
  NAlert,
  NButton,
  NEmpty,
  NInput,
  NModal,
  NProgress,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage
} from 'naive-ui';
import { clipSubtitleSrtUrl, clipVideoUrl, useClipData } from './composables/useClipData';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import SessionSelector from '@/components/business/session-selector.vue';
import ClipCard from './modules/ClipCard.vue';
import ClipEvidencePanel from './modules/ClipEvidencePanel.vue';

defineOptions({ name: 'Clip' });

const message = useMessage();

const clipData = useClipData(message);
const {
  loading,
  sessionLoading,
  overview,
  sessionOptions,
  actionLoading,
  errorMessage,
  selectedSessionId,
  selectorAnchorKey,
  selectorDateRange,
  selectorAnchorOptions
} = clipData;
const generateButtonText = computed(() =>
  overview.value?.clips.length ? '重新生成本场成片' : '生成本场成片'
);

/* ---------- 预览 ---------- */
const previewClip = ref<Api.Douyin.ClipClip | null>(null);
const previewVisible = computed(() => Boolean(previewClip.value));
const subtitleDrafts = ref<Api.Douyin.ClipSegment[]>([]);
const subtitlePrecisionText = computed(() => {
  const map = {
    funasr_exact: '逐字精确：字幕直接使用 FunASR 真实发音时间',
    funasr_aligned: '时间对齐：模型 token 已按真实发音时间比例映射到字幕文字',
    funasr_remapped: '纠错映射：行业词已修正并映射回原发音时间',
    segment_estimated: '片段估算：时间轴可能不同步，请在 FunASR 正常后重剪再确认发布'
  };
  return previewClip.value ? map[previewClip.value.subtitle_precision] : '';
});

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
  subtitleDrafts.value = clip.segments.map(segment => ({ ...segment }));
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

async function rerenderCurrentSubtitle() {
  if (!previewClip.value) return;
  const queued = await clipData.rerenderSubtitle(previewClip.value.id, subtitleDrafts.value);
  if (queued) closePreview();
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
      <SessionSelector
        :model-value="selectedSessionId"
        class="clip-page__session-select"
        :options="sessionOptions"
        :anchor-options="selectorAnchorOptions"
        :anchor-key="selectorAnchorKey"
        :date-range="selectorDateRange"
        :loading="sessionLoading"
        @search="clipData.searchSessionOptions"
        @update:model-value="value => clipData.loadOverview(value)"
        @update:anchor-key="clipData.updateSelectorAnchor"
        @update:date-range="clipData.updateSelectorDateRange"
        @reset="clipData.resetSelectorFilters"
      />
      <NButton type="primary" :loading="actionLoading" :disabled="!selectedSessionId" @click="openGenerateAll">
        {{ generateButtonText }}
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
      <AnchorIdentity
        :session-id="overview.session_id"
        :avatar-url="overview.anchor_avatar_url"
        :name="overview.anchor_name || '未知主播'"
        :nickname="overview.anchor_nickname"
        :douyin-id="overview.douyin_id"
        :size="32"
      />
      <div class="clip-page__session-info-text">
        <NText strong>{{ overview.session_title || '未知场次' }}</NText>
        <NSpace :size="12">
          <NTag size="small" :bordered="false" type="default">
            {{ fmtDateTime(overview.live_start_time) }}
          </NTag>
          <NTag size="small" :bordered="false" type="default">
            时长 {{ Math.floor((overview.live_duration_seconds || 0) / 60) }} 分钟
          </NTag>
        </NSpace>
      </div>
    </div>

    <!-- 成片网格 -->
    <div class="clip-page__grid-area">
      <NSpin :show="loading">
        <NEmpty
          v-if="!loading && (!overview || overview.clips.length === 0)"
          description="该场次还没有成片，点击上方按钮生成；或换一场直播试试"
        />
        <div v-else class="clip-page__card-grid">
          <ClipCard
            v-for="clip in overview?.clips || []"
            :key="clip.id"
            :clip="clip"
            @preview="openPreview"
            @approve="clipData.approve(clip.id)"
            @discard="clipData.discard(clip.id)"
            @regenerate="openRegenerate"
          />
        </div>
      </NSpin>
    </div>

    <!-- 成片预览 -->
    <NModal
      :show="previewVisible"
      preset="card"
      class="clip-page__preview"
      :style="{ width: 'min(560px, 92vw)' }"
      :title="previewClip?.title || '成片预览'"
      @close="closePreview"
      @update:show="show => !show && closePreview()"
    >
      <div v-if="previewClip" class="clip-page__preview-body">
        <NAlert v-if="videoError" type="warning" class="clip-page__video-error">{{ videoError }}</NAlert>
        <div class="clip-page__video-wrap">
          <video
            :src="clipVideoUrl(previewClip.id)"
            controls
            class="clip-page__video"
            @error="onVideoError"
          />
        </div>
        <div class="clip-page__publish">
          <NAlert
            :type="previewClip.subtitle_precision === 'segment_estimated' ? 'warning' : 'success'"
            :bordered="false"
          >
            {{ subtitlePrecisionText }} · 当前成片 v{{ previewClip.render_version }}
          </NAlert>
          <ClipEvidencePanel :clip="previewClip" />
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
          <div class="clip-page__subtitle-editor">
            <NText strong>字幕校对</NText>
            <NText depth="3" class="clip-page__subtitle-help">
              这里只改字幕文字，不改变画面时间；需要换画面请使用“重剪”。
            </NText>
            <div v-for="segment in subtitleDrafts" :key="`${segment.start}-${segment.end}`" class="clip-page__subtitle-row">
              <NTag size="small" :bordered="false">
                {{ segment.start.toFixed(1) }}s-{{ segment.end.toFixed(1) }}s
              </NTag>
              <NInput v-model:value="segment.text" type="textarea" autosize maxlength="5000" show-count />
            </div>
          </div>
          <NSpace class="clip-page__publish-actions">
            <NButton type="primary" @click="copyPublishContent(previewClip)">复制标题/文案/话题</NButton>
            <NButton
              v-if="previewClip.subtitle_srt_path"
              tag="a"
              :href="clipSubtitleSrtUrl(previewClip.id)"
              target="_blank"
              rel="noopener noreferrer"
              secondary
            >
              下载 SRT
            </NButton>
            <NButton
              :disabled="!previewClip.can_rerender_subtitle"
              :loading="actionLoading"
              secondary
              type="info"
              @click="rerenderCurrentSubtitle"
            >
              仅重制字幕
            </NButton>
            <NButton
              v-if="previewClip.status === 'draft' && previewClip.video_path"
              :disabled="previewClip.subtitle_precision === 'segment_estimated'"
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
  width: min(760px, 100%);
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

.clip-page__session-info-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.clip-page__grid-area {
  min-height: 200px;
}

/* 成片卡片：大屏固定一行 5 个竖版卡片，窄屏自动降列 */
.clip-page__card-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 1280px) {
  .clip-page__card-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 1024px) {
  .clip-page__card-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .clip-page__card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.clip-page__preview-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.clip-page__video-wrap {
  /* 竖屏 9:16 预览：固定高度 + 视频按比例居中（左右黑边），不拉伸变形 */
  height: min(52vh, 460px);
  background: #000;
  border-radius: 8px;
  display: flex;
  justify-content: center;
  overflow: hidden;
}

.clip-page__video {
  height: 100%;
  aspect-ratio: 9 / 16;
  max-width: 100%;
  object-fit: contain; /* 极窄视口下防止纵向拉伸变形 */
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

.clip-page__subtitle-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 4px;
}

.clip-page__subtitle-help {
  font-size: 12px;
}

.clip-page__subtitle-row {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

@media (max-width: 560px) {
  .clip-page__subtitle-row {
    grid-template-columns: 1fr;
  }
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
