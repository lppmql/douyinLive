<!--
  知识库 — 编排器（方案 A 重构）
  职责：组合聊天面板 + 来源面板。所有状态和逻辑委托给 useKnowledgeChat composable。
  718 行 → ~100 行
-->
<script setup lang="ts">
import ChatPanel from './modules/ChatPanel.vue';
import SourcePanel from './modules/SourcePanel.vue';
import { useKnowledgeChat } from './composables/useKnowledgeChat';
import SessionWorkflowNav from '@/components/business/session-workflow-nav.vue';

defineOptions({ name: 'Knowledge' });

const chat = useKnowledgeChat();
</script>

<template>
  <div class="knowledge-page">
    <SessionWorkflowNav :session-id="chat.contextSessionId.value" active="knowledge" />
    <div class="knowledge-chat-page">
      <!-- 左侧：聊天窗口 -->
      <ChatPanel
        :messages="chat.messages.value"
        :question="chat.question.value"
        :chatting="chat.chatting.value"
        :active-source-msg-id="chat.activeSourceMsgId.value"
        @update:question="(v: string) => chat.question.value = v"
        @send="chat.sendQuestion"
        @keydown="chat.handleQuestionKeydown"
        @select-sources="chat.selectSources"
        @copy-text="chat.copyText"
        @clear-conversation="chat.clearConversation"
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
  background: #fff;
}
</style>
