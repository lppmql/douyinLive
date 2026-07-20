<script setup lang="ts">
import { computed, nextTick, ref } from 'vue';
import { useMessage } from 'naive-ui';
import { unwrapServiceData } from '@/utils/service';
import { askKnowledge } from '@/service/api/douyin';

defineOptions({ name: 'Knowledge' });

type ChatMessage = {
  id: number;
  role: 'user' | 'ai';
  content: string;
  sources?: Api.Douyin.KnowledgeSource[];
  error?: boolean;
};

const message = useMessage();

const question = ref('');
const chatting = ref(false);
const messages = ref<ChatMessage[]>([]);
const chatEndRef = ref<HTMLElement | null>(null);
let messageId = 0;

async function scrollChatToEnd() {
  await nextTick();
  chatEndRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

async function sendQuestion(preset?: string) {
  const content = (preset || question.value).trim();
  if (!content || chatting.value) return;

  messages.value.push({ id: ++messageId, role: 'user', content });
  question.value = '';
  chatting.value = true;
  await scrollChatToEnd();

  try {
    const response = await askKnowledge(content);
    const answer = unwrapServiceData(response, '知识检索请求失败');
    messages.value.push({
      id: ++messageId,
      role: 'ai',
      content: answer.answer || '当前真实知识库没有返回可用结论。',
      sources: answer.sources || []
    });
  } catch (error) {
    messages.value.push({
      id: ++messageId,
      role: 'ai',
      content: error instanceof Error ? error.message : '知识检索请求失败，请确认 AI 服务状态后重试。',
      error: true
    });
  } finally {
    chatting.value = false;
    await scrollChatToEnd();
  }
}

function handleQuestionKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  void sendQuestion();
}

function clearConversation() {
  messages.value = [];
  message.success('对话已清空');
}

async function copyText(content: string) {
  await navigator.clipboard.writeText(content);
  message.success('已复制');
}
</script>

<template>
  <div class="knowledge-chat-page">
    <div class="wechat-chat">
    <!-- 顶部标题栏 -->
    <header class="chat-header">
      <span class="chat-header__title">直播经营知识问答</span>
      <button
        v-if="messages.length"
        type="button"
        class="chat-header__action"
        @click="clearConversation"
      >
        <SvgIcon icon="mdi:plus" class="text-20px" />
      </button>
    </header>

    <!-- 消息区域 -->
    <div class="chat-body">
      <NScrollbar class="chat-scroll">
        <div class="chat-messages">
          <!-- 欢迎提示 -->
          <div v-if="!messages.length" class="chat-welcome">
            <div class="chat-welcome__avatar">
              <SvgIcon icon="mdi:robot-outline" class="text-36px" />
            </div>
            <div class="mt-16px text-16px font-600 text-gray-700">零食店避坑 · 知识问答助手</div>
            <p class="mb-0 mt-6px max-w-300px text-center text-13px leading-20px text-gray-400">
              基于真实直播话术、评论和指标数据回答你的问题
            </p>
          </div>

          <!-- 对话消息 -->
          <div v-for="chatMessage in messages" :key="chatMessage.id" class="msg-block">
            <!-- AI 消息（左侧，带头像） -->
            <div v-if="chatMessage.role === 'ai'" class="msg-row msg-row--ai">
              <div class="msg-avatar msg-avatar--ai">
                <SvgIcon icon="mdi:robot-outline" class="text-20px" />
              </div>
              <div class="msg-content msg-content--ai">
                <div
                  class="msg-bubble msg-bubble--ai"
                  :class="{ 'msg-bubble--error': chatMessage.error }"
                >
                  <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
                </div>
                <!-- 操作按钮 -->
                <div v-if="!chatMessage.error" class="msg-actions">
                  <button type="button" class="msg-action-btn" @click="copyText(chatMessage.content)">
                    复制
                  </button>
                </div>
                <!-- 引用来源 -->
                <div v-if="chatMessage.sources?.length" class="msg-sources">
                  <div class="msg-sources__title">
                    <SvgIcon icon="mdi:link-variant" class="text-13px" />
                    引用 {{ chatMessage.sources.length }} 条真实来源
                  </div>
                  <div
                    v-for="source in chatMessage.sources"
                    :key="`${source.source_type}-${source.id}`"
                    class="msg-source-item"
                  >
                    <span class="msg-source-item__name">{{ source.title || source.anchor_name || '未命名' }}</span>
                    <span v-if="source.excerpt" class="msg-source-item__excerpt">{{ source.excerpt }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 用户消息（右侧，无头像） -->
            <div v-else class="msg-row msg-row--user">
              <div class="msg-bubble msg-bubble--user">
                <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
              </div>
            </div>
          </div>

          <!-- 加载中 -->
          <div v-if="chatting" class="msg-row msg-row--ai">
            <div class="msg-avatar msg-avatar--ai">
              <SvgIcon icon="mdi:robot-outline" class="text-20px" />
            </div>
            <div class="msg-bubble msg-bubble--ai msg-bubble--typing">
              <span class="typing-dot" />
              <span class="typing-dot" />
              <span class="typing-dot" />
            </div>
          </div>
          <div ref="chatEndRef" />
        </div>
      </NScrollbar>
    </div>

    <!-- 底部输入栏 -->
    <footer class="chat-footer">
      <div class="chat-footer__inner">
        <input
          v-model="question"
          class="chat-input"
          type="text"
          maxlength="500"
          placeholder="输入问题..."
          :disabled="chatting"
          @keydown="handleQuestionKeydown"
        />
        <button
          type="button"
          class="chat-send-btn"
          :class="{ 'chat-send-btn--active': question.trim() && !chatting }"
          :disabled="!question.trim() || chatting"
          @click="sendQuestion()"
        >
          <SvgIcon icon="mdi:send" class="text-18px" />
        </button>
      </div>
    </footer>
    </div>
  </div>
</template>

<style>
/* 非 scoped：锁定路由容器，禁止外层页面滚动 */
.knowledge-chat-page {
  position: relative;
  height: 100%;
  overflow: hidden;
}
</style>

<style scoped>
/* 确保聊天页撑满父容器并禁止自身滚动，只有消息区滚动 */
.wechat-chat {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}

/* ── 顶部标题栏 ── */
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

.chat-header__action {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #191919;
  cursor: pointer;
}

.chat-header__action:active {
  background: rgb(0 0 0 / 6%);
}

/* ── 消息滚动区 ── */
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

/* ── 欢迎提示 ── */
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px 40px;
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
.msg-block {
  margin-bottom: 16px;
}

.msg-row {
  display: flex;
  align-items: flex-start;
}

.msg-row--ai {
  justify-content: flex-start;
  padding-right: 60px;
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

/* ── 消息内容区 ── */
.msg-content--ai {
  min-width: 0;
}

/* ── 气泡 ── */
.msg-bubble {
  display: inline-block;
  max-width: 100%;
  padding: 10px 14px;
  font-size: 15px;
  line-height: 22px;
  word-break: break-word;
  position: relative;
}

.msg-bubble--user {
  background: #95ec69;
  color: #000;
  border-radius: 4px;
  border-top-right-radius: 4px;
  border-top-left-radius: 4px;
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
}

.msg-bubble--ai {
  background: white;
  color: #353535;
  border-radius: 4px;
  box-shadow: 0 1px 1px rgb(0 0 0 / 4%);
}

.msg-bubble--error {
  background: #fff2f2;
  color: #d03050;
}

/* ── 正在输入动画 ── */
.msg-bubble--typing {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 14px 18px;
}

.typing-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #bbb;
  animation: typing-bounce 1.4s infinite ease-in-out both;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── 消息操作 ── */
.msg-actions {
  margin-top: 4px;
  padding-left: 2px;
}

.msg-action-btn {
  border: none;
  background: transparent;
  color: #888;
  font-size: 11px;
  padding: 2px 4px;
  cursor: pointer;
  border-radius: 3px;
}

.msg-action-btn:active {
  background: rgb(0 0 0 / 5%);
}

/* ── 引用来源 ── */
.msg-sources {
  margin-top: 6px;
  padding: 8px 10px;
  background: white;
  border-radius: 4px;
  box-shadow: 0 1px 1px rgb(0 0 0 / 4%);
  max-width: 100%;
}

.msg-sources__title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgb(var(--primary-color));
  font-weight: 600;
  margin-bottom: 6px;
  padding-bottom: 5px;
  border-bottom: 1px solid rgb(0 0 0 / 5%);
}

.msg-source-item {
  padding: 5px 0;
  border-bottom: 1px solid rgb(0 0 0 / 3%);
}

.msg-source-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.msg-source-item__name {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #555;
}

.msg-source-item__excerpt {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 底部输入栏 ── */
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

.chat-input {
  flex: 1;
  height: 36px;
  padding: 0 12px;
  border: 1px solid rgb(0 0 0 / 8%);
  border-radius: 6px;
  background: #f5f5f5;
  font-size: 15px;
  color: #333;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.chat-input:focus {
  border-color: rgb(var(--primary-color) / 30%);
  background: #fff;
}

.chat-input::placeholder {
  color: #bbb;
}

.chat-input:disabled {
  background: #fafafa;
  color: #999;
}

.chat-send-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: rgb(var(--primary-color) / 12%);
  color: rgb(var(--primary-color) / 40%);
  cursor: pointer;
  transition: all 0.15s ease;
}

.chat-send-btn--active {
  background: rgb(var(--primary-color));
  color: white;
  box-shadow: 0 2px 6px rgb(var(--primary-color) / 25%);
}

.chat-send-btn:active {
  transform: scale(0.95);
}

/* ── 响应式 ── */
@media (max-width: 640px) {
  .msg-row--ai {
    padding-right: 40px;
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
}
</style>
