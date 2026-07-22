<!-- 知识库 — 引用来源面板（Naive UI 组件替代手写 HTML） -->
<script setup lang="ts">
import { NCard, NEmpty, NScrollbar, NSpace, NTag } from 'naive-ui';
import { getSourceTypeLabel, getSourceTypeColor } from '../adapters/knowledge-adapter';

defineOptions({ name: 'KnowledgeSourcePanel' });

defineProps<{
  sources: Api.Douyin.KnowledgeSource[];
}>();
</script>

<template>
  <aside class="sources-panel">
    <!-- 标题栏 -->
    <div class="sources-panel__header">
      <SvgIcon icon="mdi:link-variant" class="text-18px text-primary" />
      <span>引用来源</span>
      <span v-if="sources.length" class="sources-panel__count">{{ sources.length }}</span>
    </div>

    <NScrollbar class="sources-panel__body">
      <!-- 空状态 -->
      <div v-if="!sources.length" class="sources-panel__empty">
        <NEmpty description="发送问题后，AI 引用的真实数据来源会显示在这里" />
      </div>

      <!-- 来源卡片列表 -->
      <div v-else class="sources-list">
        <NCard
          v-for="(source, idx) in sources"
          :key="idx"
          size="small"
          :bordered="true"
          class="source-card"
        >
          <template #header>
            <NSpace align="center" justify="space-between">
              <NTag :type="getSourceTypeColor(source.source_type)" size="small" :bordered="false">
                {{ getSourceTypeLabel(source.source_type) }}
              </NTag>
              <span class="text-11px text-gray-400">#{{ idx + 1 }}</span>
            </NSpace>
          </template>
          <div class="source-card__title">{{ source.title || '未命名来源' }}</div>
          <div v-if="source.anchor_name" class="source-card__anchor">
            <SvgIcon icon="mdi:account-circle-outline" class="text-13px" />
            {{ source.anchor_name }}
          </div>
          <div v-if="source.excerpt" class="source-card__excerpt">
            {{ source.excerpt }}
          </div>
          <div v-if="source.time_range" class="source-card__time">
            <SvgIcon icon="mdi:clock-outline" class="text-12px" />
            {{ source.time_range }}
          </div>
        </NCard>
      </div>
    </NScrollbar>
  </aside>
</template>

<style scoped>
.sources-panel {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.sources-panel__header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 44px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid rgb(0 0 0 / 6%);
  background: #fff;
}

.sources-panel__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: rgb(var(--primary-color) / 10%);
  color: rgb(var(--primary-color));
  font-size: 11px;
  font-weight: 700;
}

.sources-panel__body {
  flex: 1;
  min-height: 0;
}

.sources-panel__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 24px;
}

.sources-list {
  padding: 12px 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-card {
  --n-padding-top: 10px;
  --n-padding-bottom: 10px;
  --n-padding-left: 14px;
  --n-title-font-size: 13px;
}

.source-card__title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  line-height: 19px;
  margin-bottom: 4px;
}

.source-card__anchor {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #888;
  margin-bottom: 6px;
}

.source-card__excerpt {
  font-size: 12px;
  color: #666;
  line-height: 18px;
  padding: 6px 8px;
  background: #f9f9f9;
  border-radius: 4px;
  border-left: 2px solid rgb(var(--primary-color) / 20%);
}

.source-card__time {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 11px;
  color: #aaa;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .sources-panel { width: 280px; }
}

@media (max-width: 768px) {
  .sources-panel { display: none; }
}
</style>
