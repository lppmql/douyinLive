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
const conversationTurnCount = computed(() => messages.value.filter(item => item.role === 'user').length);
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
  message.success('内容已复制');
}
</script>

<template>
  <div class="knowledge-chat-page">
    <NCard :bordered="false" class="chat-card">
      <template #header>
        <div class="flex items-center justify-between gap-12px">
          <div>
            <div class="flex items-center gap-8px text-18px font-800">
              <SvgIcon icon="mdi:message-processing-outline" class="text-primary" />
              直播经营知识问答
            </div>
            <div class="mt-3px text-12px font-normal text-gray-500">
              基于真实直播数据检索话术、评论、指标与复盘结论
            </div>
          </div>
          <NButton v-if="messages.length" secondary size="small" @click="clearConversation">
            <template #icon><SvgIcon icon="mdi:message-plus-outline" /></template>
            新对话
          </NButton>
        </div>
      </template>

      <div class="chat-body">
        <NScrollbar class="chat-scroll">
          <div class="chat-messages">
            <!-- 欢迎提示 -->
            <div v-if="!messages.length" class="chat-welcome">
              <span class="chat-welcome__icon"><SvgIcon icon="mdi:database-search-outline" /></span>
              <div class="mt-12px text-18px font-800">从真实直播数据里找答案</div>
              <p class="mb-0 mt-8px max-w-520px text-center text-13px leading-22px text-gray-500">
                可以直接询问主播话术、用户评论、开店地区与预算、高意向线索、分钟趋势或跨场次差异。
              </p>
              <div class="mt-12px flex flex-wrap justify-center gap-8px">
                <NButton
                  v-for="q in ['哪些用户问题最适合引导私信领取资料？', '最近场次中用户最常问哪些开店预算问题？', '找出有明确地区和预算的高意向评论']"
                  :key="q"
                  size="small"
                  secondary
                  :disabled="chatting"
                  @click="sendQuestion(q)"
                >
                  {{ q }}
                </NButton>
              </div>
            </div>

            <!-- 对话消息 -->
            <div v-for="chatMessage in messages" :key="chatMessage.id" class="mb-12px">
              <div :class="chatMessage.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
                <div
                  class="chat-bubble"
                  :class="[
                    chatMessage.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--ai',
                    { 'chat-bubble--error': chatMessage.error }
                  ]"
                >
                  <div class="whitespace-pre-wrap">{{ chatMessage.content }}</div>
                  <div v-if="chatMessage.role === 'ai' && !chatMessage.error" class="mt-8px flex justify-end">
                    <NButton text size="tiny" @click="copyText(chatMessage.content)">
                      <template #icon><SvgIcon icon="mdi:content-copy" /></template>
                      复制
                    </NButton>
                  </div>
                </div>
              </div>

              <!-- 引用来源 -->
              <NCollapse v-if="chatMessage.sources?.length" class="source-collapse" arrow-placement="right">
                <NCollapseItem :title="`查看 ${chatMessage.sources.length} 条真实来源`" :name="chatMessage.id">
                  <div class="grid grid-cols-2 gap-8px lt-lg:grid-cols-1">
                    <div
                      v-for="source in chatMessage.sources"
                      :key="`${source.source_type}-${source.id}`"
                      class="source-card"
                    >
                      <div class="min-w-0">
                        <div class="truncate text-12px font-700">{{ source.title || '未命名来源' }}</div>
                        <div class="mt-2px text-11px text-gray-400">
                          {{ source.anchor_name || source.source_type }}
                        </div>
                      </div>
                      <div
                        v-if="source.excerpt"
                        class="line-clamp-2 mt-5px text-11px leading-18px text-gray-500"
                      >
                        {{ source.excerpt }}
                      </div>
                    </div>
                  </div>
                </NCollapseItem>
              </NCollapse>
            </div>

            <!-- 加载中 -->
            <div v-if="chatting" class="mb-12px flex justify-start">
              <div class="chat-bubble chat-bubble--ai flex items-center gap-8px text-gray-500">
                <NSpin :size="14" />
                正在检索真实话术、评论和指标…
              </div>
            </div>
            <div ref="chatEndRef" />
          </div>
        </NScrollbar>
      </div>

      <!-- 输入区域 -->
      <div class="chat-composer">
        <div class="mb-8px flex items-center justify-between gap-8px">
          <span class="flex items-center gap-5px text-12px font-700">
            <SvgIcon icon="mdi:pencil-outline" class="text-primary" />
            输入你的问题
          </span>
          <span class="text-11px text-gray-400">Enter 发送，Shift+Enter 换行</span>
        </div>
        <NInput
          v-model:value="question"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          maxlength="500"
          show-count
          placeholder="输入复盘问题，Enter 发送，Shift+Enter 换行"
          :disabled="chatting"
          @keydown="handleQuestionKeydown"
        />
        <div class="mt-8px flex items-center justify-between gap-8px">
          <span class="text-11px text-gray-400">回答基于已同步的真实直播数据</span>
          <NButton
            type="primary"
            :loading="chatting"
            :disabled="!question.trim() || chatting"
            @click="sendQuestion()"
          >
            <template #icon><SvgIcon icon="mdi:send" /></template>
            发送
          </NButton>
        </div>
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.knowledge-chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
  padding: 16px;
}

.chat-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}

.chat-card :deep(.n-card__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  padding-top: 0;
}

.chat-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 14px;
  background: color-mix(in srgb, var(--card-color) 97%, rgb(var(--primary-color)) 3%);
  overflow: hidden;
}

.chat-scroll {
  flex: 1;
  min-height: 0;
}

.chat-messages {
  padding: 16px 12px 8px 16px;
}

.chat-welcome {
  display: flex;
  min-height: 260px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 18px;
}

.chat-welcome__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 58px;
  height: 58px;
  border-radius: 18px;
  color: rgb(var(--primary-color));
  background: linear-gradient(135deg, rgb(var(--primary-color) / 15%), rgb(24 160 88 / 10%));
  font-size: 28px;
}

.chat-composer {
  flex: none;
  border-top: 1px solid rgb(148 163 184 / 14%);
  background: var(--card-color);
  padding: 14px 16px 16px;
}

.chat-bubble {
  max-width: 92%;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 21px;
}

.chat-bubble--user {
  border-bottom-right-radius: 4px;
  background: rgb(var(--primary-color));
  color: white;
}

.chat-bubble--ai {
  border-bottom-left-radius: 4px;
  background: rgb(148 163 184 / 11%);
  color: var(--text-color-1);
}

.chat-bubble--error {
  background: rgb(208 48 80 / 9%);
  color: #d03050;
}

.source-collapse {
  margin-top: 7px;
  border-radius: 10px;
  background: rgb(148 163 184 / 6%);
  padding: 0 10px;
}

.source-collapse :deep(.n-collapse-item__header-main) {
  color: rgb(var(--primary-color));
  font-size: 12px;
  font-weight: 700;
}

.source-card {
  border: 1px solid rgb(148 163 184 / 16%);
  border-radius: 9px;
  background: var(--card-color);
  padding: 8px 10px;
}

@media (max-width: 640px) {
  .knowledge-chat-page {
    height: calc(100vh - 100px);
    padding: 10px;
  }

  .chat-messages {
    padding: 12px 8px 6px 12px;
  }

  .chat-composer {
    padding: 10px 12px 12px;
  }
}
</style>
