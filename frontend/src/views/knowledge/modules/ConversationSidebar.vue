<!-- 知识库 — 对话历史侧边栏（2026-07-28 方案 C Chat UI 全面升级） -->
<script setup lang="ts">
import { NButton, NScrollbar, NPopconfirm, NSpin } from 'naive-ui';
import { formatRelativeTime } from '@/utils/format';

defineOptions({ name: 'KnowledgeConversationSidebar' });

defineProps<{
  conversations: Api.Douyin.ConversationListItem[];
  activeConvId: number | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', convId: number): void;
  (e: 'delete', convId: number): void;
  (e: 'new'): void;
}>();
</script>

<template>
  <aside class="conversation-sidebar" aria-label="对话历史侧边栏">
    <!-- 标题栏 -->
    <div class="sidebar-header">
      <span class="sidebar-header__title">对话历史</span>
      <NButton type="primary" size="small" round aria-label="新建对话" @click="emit('new')">
        <template #icon><SvgIcon icon="mdi:plus" /></template>
        新建
      </NButton>
    </div>

    <!-- 对话列表 -->
    <div class="sidebar-body">
      <NSpin :show="loading" size="small">
        <NScrollbar class="sidebar-scroll">
          <!-- conversations 可能为 null（组件初始化时），加空值保护 -->
          <div v-if="!conversations || (!conversations.length && !loading)" class="sidebar-empty">
            <SvgIcon icon="mdi:chat-outline" class="text-28px text-gray-300" />
            <span class="text-12px text-gray-400 mt-8px">暂无对话</span>
          </div>

          <div v-else class="conversation-list">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="conversation-item"
              :class="{ 'conversation-item--active': activeConvId === conv.id }"
              role="button"
              :aria-label="`对话：${conv.title || '未命名'}`"
              tabindex="0"
              @click="emit('select', conv.id)"
              @keydown.enter="emit('select', conv.id)"
            >
              <div class="conversation-item__icon">
                <SvgIcon icon="mdi:chat-outline" class="text-16px" />
              </div>
              <div class="conversation-item__body">
                <div class="conversation-item__title">
                  {{ conv.title || '新对话' }}
                </div>
                <div class="conversation-item__meta">
                  <span>{{ conv.session_id ? `场次 #${conv.session_id}` : '全部场次' }}</span>
                  <span class="mx-1">·</span>
                  <span>{{ conv.message_count || 0 }} 条消息</span>
                  <span class="mx-1">·</span>
                  <span>{{ formatRelativeTime(conv.updated_at) }}</span>
                </div>
              </div>
              <NPopconfirm @positive-click="emit('delete', conv.id)">
                <template #trigger>
                  <NButton
                    text
                    size="tiny"
                    class="conversation-item__delete"
                    aria-label="删除对话"
                    @click.stop
                  >
                    <template #icon><SvgIcon icon="mdi:delete-outline" class="text-14px" /></template>
                  </NButton>
                </template>
                确认删除该对话？
              </NPopconfirm>
            </div>
          </div>
        </NScrollbar>
      </NSpin>
    </div>
  </aside>
</template>

<style scoped>
/* ── 布局 ── */
.conversation-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color, rgb(0 0 0 / 6%));
  background: var(--sidebar-bg, #fafafa);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  height: 44px;
  padding: 0 14px;
  border-bottom: 1px solid var(--border-color, rgb(0 0 0 / 6%));
}

.sidebar-header__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.sidebar-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 修复 NSpin 包裹导致的高度断裂：
   NSpin 渲染 .n-spin-container > .n-spin-content，两者默认高度都由内容决定，
   必须逐层传递 100% 高度，里面的 NScrollbar (height:100%) 才能拿到正确高度 */
.sidebar-body :deep(.n-spin-container),
.sidebar-body :deep(.n-spin-content) {
  height: 100%;
}

.sidebar-scroll {
  height: 100%;
}

.sidebar-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
}

/* ── 对话列表 ── */
.conversation-list {
  padding: 8px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}

.conversation-item:hover {
  background: var(--hover-bg, rgb(0 0 0 / 4%));
}

.conversation-item--active {
  background: var(--active-bg, rgb(var(--primary-color) / 8%)) !important;
}

.conversation-item__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--icon-bg, rgb(0 0 0 / 4%));
  color: var(--text-secondary, #666);
}

.conversation-item--active .conversation-item__icon {
  background: rgb(var(--primary-color) / 15%);
  color: rgb(var(--primary-color));
}

.conversation-item__body {
  flex: 1;
  min-width: 0;
}

.conversation-item__title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #333);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 18px;
}

.conversation-item__meta {
  font-size: 11px;
  color: var(--text-tertiary, #999);
  margin-top: 2px;
}

/* ── 删除按钮 ── */
.conversation-item__delete {
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.conversation-item:hover .conversation-item__delete {
  opacity: 1;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .conversation-sidebar {
    width: 220px;
  }
}

@media (max-width: 768px) {
  .conversation-sidebar {
    display: none;
  }
}
</style>
