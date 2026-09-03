<!--
  知识库 — 编排器（2026-07-28 方案 C 全面升级）

  新增：对话历史侧边栏 + 移动端来源抽屉 + 完整交互升级
  布局：侧边栏 | 聊天面板 | 来源面板（三栏）
-->
<script setup lang="ts">
import { onMounted } from 'vue';
import ChatPanel from './modules/ChatPanel.vue';
import SourcePanel from './modules/SourcePanel.vue';
import ConversationSidebar from './modules/ConversationSidebar.vue';
import { useKnowledgeChat } from './composables/useKnowledgeChat';
import SessionWorkflowNav from '@/components/business/session-workflow-nav.vue';
import SessionSelector from '@/components/business/session-selector.vue';

defineOptions({ name: 'Knowledge' });

const chat = useKnowledgeChat();

// 进入知识库页面时加载对话列表
onMounted(() => {
  chat.loadConversations();
  void chat.initializeSessionSelector();
});
</script>

<template>
  <div class="knowledge-page">
    <SessionWorkflowNav :session-id="chat.contextSessionId.value" active="knowledge" />

    <NCard :bordered="false" class="card-wrapper" size="small">
      <div class="mb-10px">
        <div class="text-14px font-700">问答资料范围</div>
        <div class="mt-3px text-12px text-gray-500">
          可按主播和日期查找场次；选择具体场次后，回答只引用该场真实资料。
        </div>
      </div>
      <SessionSelector
        :model-value="chat.selectedSessionId.value"
        :options="chat.sessionOptions.value"
        :anchor-options="chat.selectorAnchorOptions.value"
        :anchor-key="chat.selectorAnchorKey.value"
        :date-range="chat.selectorDateRange.value"
        :loading="chat.sessionLoading.value"
        :loading-more="chat.selectorLoadingMore.value"
        :has-more="chat.selectorHasMore.value"
        allow-global
        @update:model-value="chat.changeSession"
        @update:anchor-key="chat.updateSelectorAnchor"
        @update:date-range="chat.updateSelectorDateRange"
        @search="chat.searchSelectorSessions"
        @load-more="chat.loadMoreSelectorSessions"
        @reset="chat.resetSelectorFilters"
      />
    </NCard>

    <div class="knowledge-chat-page">
      <!-- 左侧：对话历史侧边栏 -->
      <ConversationSidebar
        :conversations="chat.conversations.value"
        :active-conv-id="chat.activeConvId.value"
        :loading="chat.listLoading.value"
        @select="chat.loadConversation"
        @delete="chat.removeConversation"
        @new="chat.startNewConversation"
      />

      <!-- 中间：聊天窗口 -->
      <ChatPanel
        :messages="chat.messages.value"
        :question="chat.question.value"
        :chatting="chat.chatting.value"
        :active-source-msg-id="chat.activeSourceMsgId.value"
        :loading-history="chat.detailLoading.value"
        @update:question="(v: string) => chat.question.value = v"
        @send="chat.sendQuestion"
        @keydown="chat.handleQuestionKeydown"
        @select-sources="chat.selectSources"
        @copy-text="chat.copyText"
        @clear-conversation="chat.clearConversation"
        @stop-generation="chat.stopGeneration"
        @feedback="chat.handleFeedback"
      />

      <!-- 右侧：引用来源 -->
      <SourcePanel :sources="chat.activeSources.value" />
    </div>
  </div>
</template>

<style>
.knowledge-page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.knowledge-chat-page {
  position: relative;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  display: flex;
  background: var(--page-bg, #fff);
}

/* 深色模式适配 — 通过 CSS 变量切换 */
html[theme="dark"] .knowledge-chat-page,
html[data-theme="dark"] .knowledge-chat-page {
  --page-bg: #1a1a1a;
  --chat-bg: #1e1e1e;
  --header-bg: #1e1e1e;
  --footer-bg: #1e1e1e;
  --sidebar-bg: #181818;
  --border-color: rgb(255 255 255 / 8%);
  --text-primary: #e0e0e0;
  --text-secondary: #999;
  --text-tertiary: #666;
  --bubble-ai-bg: #2a2a2a;
  --avatar-bg: #2a2a2a;
  --card-bg: #2a2a2a;
  --code-bg: rgb(255 255 255 / 8%);
  --code-block-bg: #252525;
  --hover-bg: rgb(255 255 255 / 5%);
  --active-bg: rgb(var(--primary-color) / 15%);
}
</style>
