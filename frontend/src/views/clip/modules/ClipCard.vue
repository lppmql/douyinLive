<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NCard, NImage, NSpace, NTag, NText } from 'naive-ui';
import { clipCoverUrl } from '../composables/useClipData';

defineOptions({ name: 'ClipCard' });

const props = defineProps<{
  clip: Api.Douyin.ClipClip;
}>();

const emit = defineEmits<{
  (e: 'preview', clip: Api.Douyin.ClipClip): void;
  (e: 'approve', clip: Api.Douyin.ClipClip): void;
  (e: 'discard', clip: Api.Douyin.ClipClip): void;
  (e: 'regenerate', clip: Api.Douyin.ClipClip): void;
}>();

const statusInfo = computed(() => {
  const map: Record<string, { type: 'success' | 'warning' | 'info' | 'error' | 'default'; label: string }> = {
    draft: { type: 'warning', label: '待确认' },
    approved: { type: 'success', label: '已确认' },
    discarded: { type: 'default', label: '已丢弃' },
    failed: { type: 'error', label: '生成失败' }
  };
  return map[props.clip.status] || map.draft;
});

const durationText = computed(() => {
  const seconds = props.clip.duration_seconds;
  if (!seconds) return '-';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
});

const precisionInfo = computed(() => {
  const map = {
    funasr_exact: { type: 'success' as const, label: '逐字精确' },
    funasr_aligned: { type: 'info' as const, label: '时间对齐' },
    funasr_remapped: { type: 'info' as const, label: '纠错映射' },
    segment_estimated: { type: 'warning' as const, label: '片段估算' }
  };
  return map[props.clip.subtitle_precision] || map.segment_estimated;
});
</script>

<template>
  <NCard
    :bordered="true"
    class="clip-card"
    :class="{ 'clip-card--disabled': clip.status === 'discarded' }"
    size="small"
  >
    <div class="clip-card__cover" role="button" tabindex="0" @click="emit('preview', clip)" @keydown.enter="emit('preview', clip)">
      <NImage
        v-if="clip.cover_path"
        :src="clipCoverUrl(clip.id)"
        object-fit="cover"
        width="100%"
        height="100%"
        :show-toolbar="false"
        preview-disabled
      />
      <div v-else class="clip-card__cover-placeholder">暂未生成封面</div>
      <div class="clip-card__duration">{{ durationText }}</div>
      <div class="clip-card__order">#{{ clip.clip_order }}</div>
    </div>

    <div class="clip-card__body">
      <NText class="clip-card__title" :depth="clip.status === 'discarded' ? 3 : 1" strong>
        {{ clip.title || `成片 ${clip.clip_order}` }}
      </NText>
      <div class="clip-card__topics">
        <NTag v-for="topic in clip.topics.slice(0, 3)" :key="topic" size="small" round :bordered="false" type="info">
          #{{ topic }}
        </NTag>
      </div>
      <div class="clip-card__footer">
        <NTag size="small" round :bordered="false" :type="statusInfo.type">{{ statusInfo.label }}</NTag>
        <NTag v-if="clip.is_manual" size="small" round :bordered="false" type="default">重剪</NTag>
        <NTag size="small" round :bordered="false" :type="precisionInfo.type">{{ precisionInfo.label }}</NTag>
        <NTag size="small" round :bordered="false" type="default">v{{ clip.render_version }}</NTag>
      </div>
      <NText v-if="clip.error_message" depth="3" class="clip-card__error">{{ clip.error_message }}</NText>

      <NSpace class="clip-card__actions" justify="space-between" wrap>
        <NButton size="small" secondary @click="emit('preview', clip)">预览</NButton>
        <NSpace>
          <NButton
            v-if="clip.status === 'draft' && clip.video_path"
            :disabled="clip.subtitle_precision === 'segment_estimated'"
            size="small"
            type="primary"
            ghost
            @click="emit('approve', clip)"
          >
            确认
          </NButton>
          <NButton
            v-if="clip.status !== 'discarded'"
            size="small"
            quaternary
            @click="emit('regenerate', clip)"
          >
            重剪
          </NButton>
          <NButton
            v-if="clip.status === 'draft'"
            size="small"
            quaternary
            type="error"
            @click="emit('discard', clip)"
          >
            丢弃
          </NButton>
        </NSpace>
      </NSpace>
    </div>
  </NCard>
</template>

<style scoped>
.clip-card {
  overflow: hidden;
}

.clip-card--disabled {
  opacity: 0.55;
}

.clip-card__cover {
  /* 竖版 9:16 封面：宽度随卡片自适应，高度按比例 */
  position: relative;
  width: 100%;
  aspect-ratio: 9 / 16;
  cursor: pointer;
  overflow: hidden;
  border-radius: 6px;
  background-color: #000;
}

.clip-card__cover-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: rgba(255, 255, 255, 0.45);
  font-size: 12px;
  background: linear-gradient(160deg, #2c3e50 0%, #1a1a2e 100%);
}

.clip-card__duration {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 12px;
}

.clip-card__order {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 12px;
}

.clip-card__body {
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.clip-card__title {
  font-size: 14px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 39px;
}

.clip-card__topics {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.clip-card__footer {
  display: flex;
  gap: 6px;
  align-items: center;
}

.clip-card__error {
  font-size: 12px;
}

.clip-card__actions {
  margin-top: 4px;
}
</style>
