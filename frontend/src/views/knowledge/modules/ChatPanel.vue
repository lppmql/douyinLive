<!-- 知识库 — 聊天面板（Naive UI 组件替代手写 HTML） -->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { NButton, NInput, NScrollbar, NEmpty, NSkeleton } from 'naive-ui';
import type { ChatMessage } from '../composables/useKnowledgeChat';

defineOptions({ name: 'KnowledgeChatPanel' });

const props = defineProps<{
  messages: ChatMessage[];
  question: string;
  chatting: boolean;
  activeSourceMsgId: number | null;
}>();

const emit = defineEmits<{
  (e: 'update:question', v: string): void;
  (e: 'send', preset?: string): void;
  (e: 'keydown', event: KeyboardEvent): void;
  (e: 'selectSources', msg: ChatMessage): void;
  (e: 'copyText', content: string): void;
  (e: 'clearConversation'): void;
}>();

/** 聊天区底部锚点（自动滚动用） */
const chatEndRef = ref<HTMLElement | null>(null);

/** 消息变化时自动滚动到底部 */
watch(() => props.messages.length, async () => {
  await nextTick();
  chatEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' });
});

/** 推荐问题列表（预设，点击即发送） */
const recommendedQuestions = [
  '零食店直播怎么提高留资率？',
  '常见的直播违规话术有哪些？',
  '投流 ROI 太低怎么优化？',
  '哪些品类适合做直播引流？'
];
</script>

<template>
  <div class="chat-panel">
    <!-- 标题栏 -->
    <div class="chat-header">
      <span class="chat-header__title">直播经营知识问答</span>
      <NButton
        v-if="messages.length"
        text
        size="small"
        @click="emit('clearConversation')"
      >
        <template #icon><SvgIcon icon="mdi:plus" /></template>
        新对话
      </NButton>
    </div>

    <!-- 消息区域 -->
    <div class="chat-body">
      <NScrollbar class="chat-scroll">
        <div class="chat-messages">
          <!-- 欢迎提示 + 推荐问题 -->
          <div v-if="!messages.length" class="chat-welcome">
            <div class="chat-welcome__avatar">
              <SvgIcon icon="mdi:robot-outline" class="text-36px" />
            </div>
            <div class="mt-16px text-16px font-600 text-gray-700">零食店避坑 · 知识问答助手</div>
            <p class="mb-0 mt-6px max-w-300px text-center text-13px leading-20px text-gray-400">
              基于真实直播话术、评论和指标数据回答你的问题
            </p>
            <!-- 推荐问题 -->
            <div class="mt-16px flex flex-col gap-8px w-260px">
              <NButton
                v-for="q in recommendedQuestions"
                :key="q"
                secondary
                size="small"
                class="text-left"
                @click="emit('send', q)"
              >
                {{ q }}
              </NButton>
            </div>
          </div>

          <!-- 对话消息 -->
          <div v-for="chatMessage in messages" :key="chatMessage.id" class="msg-block">
            <!-- AI 消息（左侧） -->
            <div v-if="chatMessage.role === 'ai'" class="msg-row msg-row--ai">
              <div class="msg-avatar msg-avatar--ai">
                <SvgIcon icon="mdi:robot-outline" class="text-20px" />
              </div>
              <div class="msg-content">
                <!-- 错误消息用 NAlert -->
                <NAlert v-if="chatMessage.error" type="error" :bordered="false" class="mb-0!">
                  {{ chatMessage.content }}
                </NAlert>
                <!-- 正常消息 -->
                <div v-else class="msg-bubble msg-bubble--ai">
                  <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
                </div>
                <div v-if="!chatMessage.error" class="msg-actions">
                  <NButton text size="tiny" @click="emit('copyText', chatMessage.content)">复制</NButton>
                  <NButton
                    v-if="chatMessage.sources?.length"
                    text
                    size="tiny"
                    :type="activeSourceMsgId === chatMessage.id ? 'primary' : 'default'"
                    @click="emit('selectSources', chatMessage)"
                  >
                    <template #icon><SvgIcon icon="mdi:link-variant" class="text-13px" /></template>
                    {{ chatMessage.sources.length }} 条来源
                  </NButton>
                </div>
              </div>
            </div>

            <!-- 用户消息（右侧） -->
            <div v-else class="msg-row msg-row--user">
              <div class="msg-bubble msg-bubble--user">
                <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
              </div>
            </div>
          </div>

          <!-- 加载中（用 NSkeleton 替代手写动画） -->
          <div v-if="chatting" class="msg-row msg-row--ai">
            <div class="msg-avatar msg-avatar--ai">
              <SvgIcon icon="mdi:robot-outline" class="text-20px" />
            </div>
            <div class="msg-bubble msg-bubble--ai msg-bubble--loading">
              <NSkeleton text :repeat="2" :animated="true" />
            </div>
          </div>
          <div ref="chatEndRef" />
        </div>
      </NScrollbar>
    </div>

    <!-- 底部输入栏 -->
    <div class="chat-footer">
      <div class="chat-footer__inner">
        <NInput
          :value="question"
          type="text"
          maxlength="500"
          placeholder="输入问题..."
          :disabled="chatting"
          clearable
          round
          size="large"
          @keydown="(e: KeyboardEvent) => emit('keydown', e)"
          @update:value="(v: string) => emit('update:question', v)"
        />
        <NButton
          type="primary"
          :disabled="!question.trim() || chatting"
          :loading="chatting"
          @click="emit('send')"
        >
          <template #icon><SvgIcon icon="mdi:send" /></template>
        </NButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 布局 ── */
.chat-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgb(0 0 0 / 6%);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  height: 44px;
  background: #fff;
  border-bottom: 1px solid rgb(0 0 0 / 6%);
  position: relative;
  padding: 0 16px;
}

.chat-header__title {
  font-size: 17px;
  font-weight: 600;
  color: #191919;
}

.chat-header :deep(.n-button) {
  position: absolute;
  right: 12px;
}

/* ── 消息区 ── */
.chat-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.chat-scroll {
  height: 100%;
}

.chat-messages {
  padding: 12px 14px 20px;
}

/* ── 欢迎区 ── */
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.chat-welcome__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: white;
  color: rgb(var(--primary-color));
  box-shadow: 0 2px 12px rgb(0 0 0 / 6%);
}

/* ── 消息行 ── */
.msg-block { margin-bottom: 16px; }

.msg-row {
  display: flex;
  align-items: flex-start;
}

.msg-row--ai {
  justify-content: flex-start;
  padding-right: 20px;
}

.msg-row--user {
  justify-content: flex-end;
  padding-left: 60px;
}

/* ── 头像 ── */
.msg-avatar {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 6px;
  margin-right: 10px;
  margin-top: 2px;
}

.msg-avatar--ai {
  background: white;
  color: rgb(var(--primary-color));
  box-shadow: 0 1px 4px rgb(0 0 0 / 6%);
}

.msg-content { min-width: 0; }

/* ── 气泡 ── */
.msg-bubble {
  display: inline-block;
  max-width: 100%;
  padding: 10px 14px;
  font-size: 15px;
  line-height: 22px;
  word-break: break-word;
}

.msg-bubble--user {
  background: #95ec69;
  color: #000;
  border-radius: 4px;
}

.msg-bubble--ai {
  background: white;
  color: #353535;
  border-radius: 4px;
  box-shadow: 0 1px 1px rgb(0 0 0 / 4%);
}

.msg-bubble--loading {
  width: 260px;
}

/* ── 消息操作 ── */
.msg-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 4px;
  padding-left: 2px;
}

/* ── 输入栏 ── */
.chat-footer {
  flex-shrink: 0;
  background: #fff;
  border-top: 1px solid rgb(0 0 0 / 6%);
  padding: 8px 12px;
  padding-bottom: max(8px, env(safe-area-inset-bottom));
}

.chat-footer__inner {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .chat-panel { border-right: none; }
  .msg-row--ai { padding-right: 20px; }
  .msg-row--user { padding-left: 40px; }
  .msg-bubble { font-size: 14px; padding: 8px 12px; }
  .chat-messages { padding: 10px 10px 16px; }
}
</style>
