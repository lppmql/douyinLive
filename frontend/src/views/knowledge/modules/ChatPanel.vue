<!--
 知识库 — 聊天面板（2026-07-28 方案 C 全面升级）

  升级内容：
  - Markdown 渲染（markdown-it）
  - 流式打字光标动画 ▍
  - 停止生成按钮
  - 👍👎 反馈按钮
  - 来源迷你卡片（内联）
  - 全面 CSS 变量化 → 自动支持深色模式
  - 消息入场动效（stagger fadeInUp）
  - 品牌色用户气泡（替代微信绿）
  - 欢迎页升级（渐变背景 + 功能卡片）
  - 清空确认 NPopconfirm
  - 无障碍 aria-label
-->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { NButton, NInput, NScrollbar, NAlert, NPopconfirm } from 'naive-ui';
import type { ChatMessage } from '../composables/useKnowledgeChat';
import { renderMarkdown } from '../adapters/markdown-renderer';

defineOptions({ name: 'KnowledgeChatPanel' });

const props = defineProps<{
  messages: ChatMessage[];
  question: string;
  chatting: boolean;
  activeSourceMsgId: number | null;
  /** 当前对话 ID（保存消息用） */
  activeConvId: number | null;
  /** 是否正在加载历史消息 */
  loadingHistory: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:question', v: string): void;
  (e: 'send', preset?: string): void;
  (e: 'keydown', event: KeyboardEvent): void;
  (e: 'selectSources', msg: ChatMessage): void;
  (e: 'copyText', content: string): void;
  (e: 'clearConversation'): void;
  (e: 'stopGeneration'): void;
  (e: 'feedback', msg: ChatMessage, type: 'like' | 'dislike'): void;
}>();

/** 聊天区底部锚点（自动滚动用） */
const chatEndRef = ref<HTMLElement | null>(null);

/** 最后一条 AI 消息（用于判断流式状态 + 获取打字内容） */
const lastAiMsg = computed(() => {
  const msgs = props.messages;
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'ai') return msgs[i];
  }
  return null;
});

/** 是否正在流式输出中（有 AI 消息但还没收到 onDone） */
const isStreaming = computed(() => {
  return props.chatting && lastAiMsg.value && lastAiMsg.value.content.length > 0;
});

/**
 * 自动滚动到底部（仅在新消息出现时）
 *
 * 只监听消息数量变化，不监听内容长度变化。
 * 这样发送新消息时会自动滚到底部，但 AI 流式打字过程中不会强制跟随滚动，
 * 用户可以自由阅读已输出的内容。
 */
watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    chatEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }
);

/** 推荐问题列表（按话题分组 + 图标） */
const recommendedQuestions = [
  { text: '留资率突然下降，可能是什么原因？怎么排查？', icon: 'mdi:chart-line' },
  { text: '哪些避坑话题最容易让观众主动私信留资？', icon: 'mdi:chat-question-outline' },
  { text: '高意向用户的评论一般有哪些特征？怎么引导？', icon: 'mdi:account-search-outline' },
  { text: '直播开场前5分钟讲什么内容最能留住人？', icon: 'mdi:clock-start' },
];

/** 将键盘事件交给问答编排层，统一判断回车发送和换行 */
function handleKeydown(event: KeyboardEvent) {
  emit('keydown', event);
}

/** 停止生成（通过 composable 的 AbortController 取消流式请求） */
function handleStop() {
  emit('stopGeneration');
}

/** 点赞/踩 */
function handleFeedback(msg: ChatMessage, type: 'like' | 'dislike') {
  emit('feedback', msg, type);
}
</script>

<template>
  <div class="chat-panel">
    <!-- 标题栏 -->
    <div class="chat-header">
      <span class="chat-header__title">直播经营知识问答</span>
      <NPopconfirm v-if="messages.length" @positive-click="emit('clearConversation')">
        <template #trigger>
          <NButton
            text
            size="small"
            aria-label="清空当前对话"
          >
            <template #icon><SvgIcon icon="mdi:plus" /></template>
            新对话
          </NButton>
        </template>
        确认清空当前对话？清空后消息无法恢复。
      </NPopconfirm>
    </div>

    <!-- 消息区域 -->
    <div class="chat-body">
      <NScrollbar class="chat-scroll">
        <div class="chat-messages">
          <!-- 欢迎提示 + 推荐问题 -->
          <div v-if="!messages.length && !loadingHistory" class="chat-welcome">
            <!-- 渐变头像装饰 -->
            <div class="chat-welcome__decoration">
              <div class="chat-welcome__avatar">
                <SvgIcon icon="mdi:robot-outline" class="text-40px" />
              </div>
            </div>

            <h2 class="chat-welcome__title">零食店避坑 · 知识问答助手</h2>
            <p class="chat-welcome__desc">
              基于真实直播话术、评论和指标数据，<br />智能回答你的经营问题
            </p>

            <!-- 功能提示卡 -->
            <div class="chat-welcome__features">
              <div class="feature-card">
                <SvgIcon icon="mdi:magnify" class="text-18px text-primary" />
                <span>检索真实场次</span>
              </div>
              <div class="feature-card">
                <SvgIcon icon="mdi:source-branch" class="text-18px text-primary" />
                <span>引用可追溯来源</span>
              </div>
              <div class="feature-card">
                <SvgIcon icon="mdi:message-processing-outline" class="text-18px text-primary" />
                <span>流式实时回答</span>
              </div>
            </div>

            <!-- 推荐问题 -->
            <div class="chat-welcome__questions">
              <p class="chat-welcome__questions-title">💡 试试这些问题</p>
              <NButton
                v-for="q in recommendedQuestions"
                :key="q.text"
                secondary
                size="small"
                class="question-btn"
                :aria-label="`推荐问题：${q.text}`"
                @click="emit('send', q.text)"
              >
                <template #icon><SvgIcon :icon="q.icon" class="text-14px flex-shrink-0" /></template>
                <span class="question-btn__text">{{ q.text }}</span>
              </NButton>
            </div>
          </div>

          <!-- 加载历史消息提示 -->
          <div v-if="loadingHistory" class="loading-history">
            <span class="loading-history__text">加载对话中…</span>
          </div>

          <!-- 对话消息（带动效） -->
          <div
            v-for="(chatMessage, idx) in messages"
            :key="chatMessage.id"
            class="msg-block"
            :style="{ animationDelay: `${Math.min(idx * 30, 300)}ms` }"
          >
            <!-- AI 消息（左侧） -->
            <div v-if="chatMessage.role === 'ai'" class="msg-row msg-row--ai">
              <div class="msg-avatar msg-avatar--ai" aria-label="AI 助手">
                <SvgIcon icon="mdi:robot-outline" class="text-20px" />
              </div>
              <div class="msg-content">
                <!-- 错误消息用 NAlert -->
                <NAlert
                  v-if="chatMessage.error"
                  type="error"
                  :bordered="false"
                  class="mb-0!"
                >
                  <template #header>
                    <span>回答失败</span>
                  </template>
                  {{ chatMessage.content }}
                </NAlert>

                <!-- 正常 AI 消息：Markdown 渲染 -->
                <div v-else class="msg-bubble msg-bubble--ai">
                  <!-- 使用 markdown-it 渲染，带打字光标 -->
                  <div
                    class="markdown-body"
                    v-html="renderMarkdown(chatMessage.content)"
                  />
                  <!-- 流式输出中的闪烁光标 -->
                  <span
                    v-if="chatting && chatMessage === lastAiMsg && !chatMessage.sources?.length"
                    class="typing-cursor"
                    aria-hidden="true"
                  >▍</span>
                </div>

                <!-- 来源迷你卡片 -->
                <div
                  v-if="chatMessage.sources?.length"
                  class="source-mini-cards"
                >
                  <div
                    v-for="(source, si) in chatMessage.sources.slice(0, 3)"
                    :key="si"
                    class="source-mini-card"
                    role="button"
                    tabindex="0"
                    aria-label="查看来源详情"
                    @click="emit('selectSources', chatMessage)"
                    @keydown.enter="emit('selectSources', chatMessage)"
                  >
                    <SvgIcon icon="mdi:link-variant" class="text-10px flex-shrink-0" />
                    <span>{{ source.title || '未命名来源' }}</span>
                  </div>
                  <NButton
                    v-if="chatMessage.sources.length > 3"
                    text
                    size="tiny"
                    class="source-more-btn"
                    @click="emit('selectSources', chatMessage)"
                  >
                    查看全部 {{ chatMessage.sources.length }} 条来源 →
                  </NButton>
                </div>

                <!-- 消息操作栏 -->
                <div v-if="!chatMessage.error" class="msg-actions">
                  <NButton
                    text
                    size="tiny"
                    aria-label="复制回答"
                    @click="emit('copyText', chatMessage.content)"
                  >
                    <template #icon><SvgIcon icon="mdi:content-copy" class="text-13px" /></template>
                    复制
                  </NButton>
                  <NButton
                    v-if="chatMessage.sources?.length"
                    text
                    size="tiny"
                    :type="activeSourceMsgId === chatMessage.id ? 'primary' : 'default'"
                    aria-label="查看引用来源"
                    @click="emit('selectSources', chatMessage)"
                  >
                    <template #icon><SvgIcon icon="mdi:link-variant" class="text-13px" /></template>
                    {{ chatMessage.sources.length }} 条来源
                  </NButton>
                  <!-- 赞/踩反馈 -->
                  <span class="msg-actions__feedback">
                    <NButton
                      text
                      size="tiny"
                      :type="chatMessage.feedback === 'like' ? 'primary' : 'default'"
                      aria-label="点赞"
                      @click="handleFeedback(chatMessage, 'like')"
                    >
                      <template #icon><SvgIcon icon="mdi:thumb-up-outline" class="text-14px" /></template>
                    </NButton>
                    <NButton
                      text
                      size="tiny"
                      :type="chatMessage.feedback === 'dislike' ? 'error' : 'default'"
                      aria-label="点踩"
                      @click="handleFeedback(chatMessage, 'dislike')"
                    >
                      <template #icon><SvgIcon icon="mdi:thumb-down-outline" class="text-14px" /></template>
                    </NButton>
                  </span>
                </div>
              </div>
            </div>

            <!-- 用户消息（右侧） -->
            <div v-else class="msg-row msg-row--user">
              <div class="msg-user-wrap">
                <div class="msg-bubble msg-bubble--user">
                  <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
                </div>
                <div v-if="chatMessage.timestamp" class="msg-time">{{ chatMessage.timestamp }}</div>
              </div>
            </div>
          </div>

          <!-- 等待知识库检索（还没收到第一个 token 时显示） -->
          <div v-if="chatting && lastAiMsg && !lastAiMsg.content" class="msg-row msg-row--ai">
            <div class="msg-avatar msg-avatar--ai">
              <SvgIcon icon="mdi:robot-outline" class="text-20px" />
            </div>
            <div class="msg-bubble msg-bubble--ai msg-bubble--loading">
              <span class="msg-searching">
                <span class="msg-searching__dot">●</span>
                <span class="msg-searching__dot" style="animation-delay: 0.2s">●</span>
                <span class="msg-searching__dot" style="animation-delay: 0.4s">●</span>
                <span class="ml-1">正在查找知识库</span>
              </span>
            </div>
          </div>
          <div ref="chatEndRef" />
        </div>
      </NScrollbar>
    </div>

    <!-- 底部输入栏 -->
    <div class="chat-footer">
      <!-- 流式输出中：停止生成按钮 -->
      <div v-if="isStreaming" class="chat-footer__streaming">
        <NButton
          type="warning"
          size="small"
          round
          aria-label="停止生成"
          @click="handleStop"
        >
          <template #icon><SvgIcon icon="mdi:stop" /></template>
          停止生成
        </NButton>
      </div>

      <div class="chat-footer__inner">
        <NInput
          :value="question"
          type="textarea"
          maxlength="500"
          placeholder="输入你的问题…"
          :disabled="chatting"
          :autosize="{ minRows: 1, maxRows: 4 }"
          round
          size="large"
          class="chat-input"
          aria-label="输入问题"
          @keydown="handleKeydown"
          @update:value="(v: string) => emit('update:question', v)"
        />
        <NButton
          type="primary"
          circle
          size="large"
          :disabled="!question.trim() || chatting"
          :loading="chatting"
          aria-label="发送消息"
          @click="emit('send')"
        >
          <template #icon><SvgIcon icon="mdi:send" /></template>
        </NButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════
   CSS 变量（浅色主题默认值 / 深色主题覆盖）
   ═══════════════════════════════════════════ */

/* 消息入场动效 */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 打字光标闪烁 */
@keyframes blinkCursor {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 搜索中圆点跳动 */
@keyframes searchDotBounce {
  0%, 80%, 100% { opacity: 0.3; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); }
}

/* ── 布局 ── */
.chat-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-color, rgb(0 0 0 / 6%));
  background: var(--chat-bg, #fff);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  height: 44px;
  background: var(--header-bg, #fff);
  border-bottom: 1px solid var(--border-color, rgb(0 0 0 / 6%));
  position: relative;
  padding: 0 16px;
}

.chat-header__title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary, #191919);
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
  padding: 32px 20px 48px;
}

.chat-welcome__decoration {
  position: relative;
  margin-bottom: 20px;
}

.chat-welcome__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg,
    rgb(var(--primary-color) / 15%),
    rgb(var(--primary-color) / 5%));
  color: rgb(var(--primary-color));
  box-shadow: 0 4px 24px rgb(var(--primary-color) / 15%);
}

.chat-welcome__title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary, #191919);
}

.chat-welcome__desc {
  margin: 0 0 20px;
  text-align: center;
  font-size: 14px;
  line-height: 22px;
  color: var(--text-secondary, #888);
}

/* 功能提示卡 */
.chat-welcome__features {
  display: flex;
  gap: 10px;
  margin-bottom: 24px;
}

.feature-card {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  background: var(--card-bg, #f8f8f8);
  font-size: 12px;
  color: var(--text-secondary, #666);
  white-space: nowrap;
}

/* 推荐问题 */
.chat-welcome__questions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  max-width: 340px;
}

.chat-welcome__questions-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #666);
  text-align: left;
}

.question-btn {
  justify-content: flex-start !important;
  width: 100%;
  text-align: left;
  padding: 10px 14px !important;
  border-radius: 10px !important;
  transition: all 0.15s;
}

.question-btn:hover {
  transform: translateX(2px);
}

.question-btn__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 加载历史 ── */
.loading-history {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.loading-history__text {
  font-size: 13px;
  color: var(--text-tertiary, #aaa);
}

/* ── 消息行 ── */
.msg-block {
  margin-bottom: 16px;
  animation: fadeInUp 0.3s ease-out both;
}

.msg-row {
  display: flex;
  align-items: flex-start;
}

.msg-row--ai {
  justify-content: flex-start;
  padding-right: 40px;
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
  border-radius: 10px;
  margin-right: 10px;
  margin-top: 2px;
}

.msg-avatar--ai {
  background: var(--avatar-bg, #f5f5f5);
  color: rgb(var(--primary-color));
  box-shadow: 0 1px 4px rgb(0 0 0 / 6%);
}

.msg-content {
  min-width: 0;
  flex: 1;
}

/* ── 气泡 ── */
.msg-bubble {
  display: inline-block;
  max-width: 100%;
  padding: 10px 14px;
  font-size: 15px;
  line-height: 24px;
  word-break: break-word;
}

/* 用户气泡：品牌主色 */
.msg-bubble--user {
  background: rgb(var(--primary-color));
  color: #fff;
  border-radius: 16px 4px 16px 16px;
}

/* AI 气泡：白底+阴影 */
.msg-bubble--ai {
  background: var(--bubble-ai-bg, #fff);
  color: var(--text-primary, #353535);
  border-radius: 4px 16px 16px 16px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
}

.msg-bubble--loading {
  /* 宽度自适应文字 */
}

/* ── Markdown 内容 ── */
.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin-bottom: 2px;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--code-bg, rgb(0 0 0 / 5%));
  font-size: 13px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
}

.markdown-body :deep(pre) {
  margin: 8px 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--code-block-bg, #f6f8fa);
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: none;
}

.markdown-body :deep(a) {
  color: rgb(var(--primary-color));
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid rgb(var(--primary-color) / 30%);
  color: var(--text-secondary, #666);
}

/* ── 打字光标 ── */
.typing-cursor {
  display: inline-block;
  color: rgb(var(--primary-color));
  font-weight: 700;
  font-size: 16px;
  animation: blinkCursor 0.8s infinite;
  vertical-align: text-bottom;
}

/* ── 搜索中提示 ── */
.msg-searching {
  display: flex;
  align-items: center;
  color: var(--text-tertiary, #999);
  font-size: 14px;
}

.msg-searching__dot {
  animation: searchDotBounce 1.2s infinite;
}

/* ── 来源迷你卡 ── */
.source-mini-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.source-mini-card {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--card-bg, #f8f8f8);
  font-size: 12px;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: background 0.15s;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-mini-card:hover {
  background: rgb(var(--primary-color) / 8%);
}

.source-more-btn {
  font-size: 11px;
}

/* ── 消息时间 ── */
.msg-user-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.msg-time {
  font-size: 11px;
  color: var(--text-tertiary, #999);
  margin-top: 3px;
  padding-right: 4px;
}

/* ── 消息操作 ── */
.msg-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 4px;
  padding-left: 2px;
}

.msg-actions__feedback {
  display: flex;
  align-items: center;
  gap: 0;
  margin-left: 4px;
  padding-left: 6px;
  border-left: 1px solid var(--border-color, rgb(0 0 0 / 8%));
}

/* ── 输入栏 ── */
.chat-footer {
  flex-shrink: 0;
  background: var(--footer-bg, #fff);
  border-top: 1px solid var(--border-color, rgb(0 0 0 / 6%));
  padding: 8px 12px;
  padding-bottom: max(8px, env(safe-area-inset-bottom));
}

.chat-footer__streaming {
  display: flex;
  justify-content: center;
  margin-bottom: 8px;
}

.chat-footer__inner {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

.chat-input {
  flex: 1;
}

/* ── 响应式 ── */
@media (max-width: 768px) {
  .chat-panel {
    border-right: none;
  }
  .msg-row--ai {
    padding-right: 20px;
  }
  .msg-row--user {
    padding-left: 40px;
  }
  .msg-bubble {
    font-size: 14px;
    padding: 8px 12px;
  }
  .chat-messages {
    padding: 10px 10px 16px;
  }
  .chat-welcome__features {
    flex-direction: column;
    gap: 6px;
  }
  .feature-card {
    justify-content: center;
  }
}
</style>
