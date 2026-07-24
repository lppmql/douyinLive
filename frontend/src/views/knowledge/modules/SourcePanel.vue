<!-- 知识库 — 引用来源面板（Naive UI 组件替代手写 HTML） -->
<script setup lang="ts">
import { useRouter } from 'vue-router';
import { NCard, NEmpty, NScrollbar, NSpace, NTag } from 'naive-ui';
import AnchorIdentity from '@/components/business/anchor-identity.vue';
import { getSourceTypeLabel, getSourceTypeColor } from '../adapters/knowledge-adapter';

defineOptions({ name: 'KnowledgeSourcePanel' });

defineProps<{
  sources: Api.Douyin.KnowledgeSource[];
}>();

const router = useRouter();

/** 点击来源卡片 → 跳转到对应场次详情页并定位到视频时间轴 */
function handleSourceClick(source: Api.Douyin.KnowledgeSource) {
  if (!source.session_id) return;
  const seekSeconds = source.slice_start_seconds ?? 0;
  void router.push({
    name: 'live-session-detail',
    params: { id: String(source.session_id) },
    query: { seek: String(seekSeconds) },
  });
}
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
          :class="{ 'source-card--clickable': !!source.session_id }"
          @click="handleSourceClick(source)"
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
          <AnchorIdentity
            v-if="source.anchor_name"
            class="source-card__anchor"
            :session-id="source.session_id"
            :avatar-url="source.anchor_avatar_url"
            :name="source.anchor_name"
            :nickname="source.anchor_nickname"
            :douyin-id="source.douyin_id"
            :size="30"
            dense
          />
          <div v-if="source.excerpt" class="source-card__excerpt">
            {{ source.excerpt }}
          </div>
          <div v-if="source.time_range" class="source-card__time">
            <SvgIcon icon="mdi:clock-outline" class="text-12px" />
            {{ source.time_range }}
          </div>
          <!-- 可跳转卡片：点击查看直播回放 -->
          <div v-if="source.session_id" class="source-card__jump">
            <SvgIcon icon="mdi:play-circle-outline" class="text-13px" />
            <span>点击查看回放</span>
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

/* 可点击卡片：有 session_id 的来源可以跳转到场次详情页 */
.source-card--clickable {
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.15s;
}

.source-card--clickable:hover {
  box-shadow: 0 2px 10px rgb(var(--primary-color) / 10%);
  transform: translateY(-1px);
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

.source-card__jump {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgb(0 0 0 / 5%);
  font-size: 12px;
  color: rgb(var(--primary-color));
  opacity: 0.8;
}

.source-card--clickable:hover .source-card__jump {
  opacity: 1;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .sources-panel { width: 280px; }
}

@media (max-width: 768px) {
  .sources-panel { display: none; }
}
</style>
